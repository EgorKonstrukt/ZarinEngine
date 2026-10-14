# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import numpy as np
import moderngl
from core.maths.math3d import Mat4, Vec3
from core.foundation.logger import Logger
from core.assets.compute_shader import compile_compute_shader
from core.components.lighting.lightp import Light, LightType
from core.components.rendering.renderers.raytrace.component import _MAX_ALBEDO_LAYERS
class RaytraceDispatchMixin:
    def _ensure_resources(self, ctx: moderngl.Context, width: int, height: int):
        rw = max(1, int(width * self._resolution_scale))
        rh = max(1, int(height * self._resolution_scale))
        if self._program is None:
            self._compute_shader_path = self._resolve_shader_path(self._compute_shader_path)
            path = os.path.abspath(self._compute_shader_path)
            if not os.path.exists(path):
                Logger.error(f"Raytracing compute shader not found: {path}")
                return False
            try:
                with open(path) as f:
                    src = f.read()
                glsl_start = src.find("GLSLPROGRAM")
                glsl_end = src.find("ENDGLSL", glsl_start)
                if glsl_start < 0 or glsl_end < 0:
                    Logger.error("Invalid .compute file: no GLSLPROGRAM/ENDGLSL")
                    return False
                source = src[glsl_start + len("GLSLPROGRAM"):glsl_end].strip()
                self._program = compile_compute_shader(ctx, source, path)
                if self._program is None:
                    return False
            except Exception as e:
                Logger.error(f"Failed to compile compute shader: {e}")
                return False
        if self._fullscreen_prog is None:
            h = chr(35)
            vsrc = h + "version 330 core\nin vec2 in_position;\nin vec2 in_uv;\nout vec2 v_uv;\nvoid main() {\ngl_Position = vec4(in_position, 0.0, 1.0);\nv_uv = in_uv;\n}\n"
            fsrc = h + "version 330 core\nin vec2 v_uv;\nuniform sampler2D u_tex;\nout vec4 frag_color;\nvoid main() {\nfrag_color = texture(u_tex, v_uv);\n}\n"
            self._fullscreen_prog = ctx.program(vertex_shader=vsrc, fragment_shader=fsrc)
        if self._fullscreen_quad is None:
            fs_verts = np.array([
                -1, -1, 0, 0,
                1, -1, 1, 0,
                1, 1, 1, 1,
                -1, -1, 0, 0,
                1, 1, 1, 1,
                -1, 1, 0, 1,
            ], dtype=np.float32)
            vbo = ctx.buffer(fs_verts.tobytes())
            self._fullscreen_quad = ctx.vertex_array(
                self._fullscreen_prog,
                [(vbo, "2f 2f", "in_position", "in_uv")],
            )
        if self._output_tex is None or self._prev_width != rw or self._prev_height != rh:
            if self._output_tex:
                self._output_tex.release()
            if self._output_fbo:
                self._output_fbo.release()
            if self._emissive_tex:
                self._emissive_tex.release()
            self._output_tex = ctx.texture((rw, rh), 4, dtype="f4")
            self._output_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._output_tex.repeat_x = False
            self._output_tex.repeat_y = False
            self._output_fbo = ctx.framebuffer(color_attachments=[self._output_tex])
            self._emissive_tex = ctx.texture((rw, rh), 4, dtype="f4")
            self._emissive_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._emissive_tex.repeat_x = False
            self._emissive_tex.repeat_y = False
            self._prev_width = rw
            self._prev_height = rh
            self._accum_frame = 1
        if self._albedo_array_tex is None:
            self._albedo_array_tex = ctx.texture_array((*self._albedo_array_size, _MAX_ALBEDO_LAYERS), 4, dtype="f1")
            self._albedo_array_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._albedo_array_tex.repeat_x = False
            self._albedo_array_tex.repeat_y = False
        if self._sky_env_tex is None:
            self._sky_env_tex = ctx.texture((256, 128), 4, dtype="f4")
            self._sky_env_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._sky_env_tex.repeat_x = False
            self._sky_env_tex.repeat_y = False
        if self._sky_env_prog is None:
            env_path = os.path.abspath("core/shaders/compute/SkyEnv.compute")
            if not os.path.exists(env_path):
                Logger.error(f"SkyEnv compute shader not found: {env_path}")
                return False
            try:
                with open(env_path) as f:
                    src = f.read()
                glsl_start = src.find("GLSLPROGRAM")
                glsl_end = src.find("ENDGLSL", glsl_start)
                if glsl_start < 0 or glsl_end < 0:
                    Logger.error("Invalid SkyEnv.compute: no GLSLPROGRAM/ENDGLSL")
                    return False
                source = src[glsl_start + len("GLSLPROGRAM"):glsl_end].strip()
                self._sky_env_prog = compile_compute_shader(ctx, source, env_path)
                if self._sky_env_prog is None:
                    return False
            except Exception as e:
                Logger.error(f"Failed to compile SkyEnv compute shader: {e}")
                return False
        return True
    def _upload_or_realloc(self, ctx: moderngl.Context, buf_attr: str, data: np.ndarray) -> None:
        buf = getattr(self, buf_attr)
        nbytes = data.nbytes
        if buf is None or nbytes > buf.size:
            if buf:
                buf.release()
            nbuf = ctx.buffer(data, dynamic=True)
            setattr(self, buf_attr, nbuf)
        else:
            buf.write(data)
    def _dispatch(self, ctx: moderngl.Context, width: int, height: int, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3, scene, renderer) -> bool:
        ctx_id = id(ctx)
        if self._ctx_id != ctx_id:
            self._release_gl()
            self._ctx_id = ctx_id
        rw = max(1, int(width * self._resolution_scale))
        rh = max(1, int(height * self._resolution_scale))
        if self._accumulate:
            cur_vp = (proj_mat.to_f32().reshape(4, 4) @ view_mat.to_f32().reshape(4, 4))
            if self._prev_view_proj is not None:
                if np.max(np.abs(cur_vp - self._prev_view_proj)) > 1e-5:
                    self._accum_frame = 1
            self._prev_view_proj = cur_vp.copy()
        if not self._ensure_resources(ctx, width, height):
            return False
        if not self._collect_and_upload(ctx, scene, view_mat, proj_mat, cam_pos, renderer):
            return False
        if self._sky_env_tex is None or self._sky_env_prog is None:
            return False
        view_f32 = view_mat.to_f32().reshape(4, 4).T
        proj_f32 = proj_mat.to_f32().reshape(4, 4).T
        rectified, _ = np.linalg.qr(view_f32)
        if np.linalg.det(rectified) < 0:
            rectified[:, 0] = -rectified[:, 0]
        inv_vp = np.linalg.inv(proj_f32 @ view_f32)
        prog = self._program
        try:
            prog["u_camera_pos"] = (cam_pos.x, cam_pos.y, cam_pos.z)
            prog["u_inv_view_proj"].write(inv_vp.astype(np.float32, copy=False).flatten(order="F").tobytes())
            prog["u_screen_width"] = rw
            prog["u_screen_height"] = rh
            prog["u_instance_count"] = self._inst_np.shape[0]
            prog["u_light_count"] = self._light_np.shape[0]
            prog["u_max_bounces"] = self._max_bounces
            prog["u_accum_frame"] = self._accum_frame
            prog["u_frame"] = self._frame
            prog["u_accumulate"] = 1 if self._accumulate else 0
            prog["u_samples_per_pixel"] = self._samples_per_pixel
            if "u_heatmap_mode" in prog:
                prog["u_heatmap_mode"] = int(self._heatmap_mode)
            if "u_heatmap_scale" in prog:
                prog["u_heatmap_scale"] = float(self._heatmap_scale)
        except KeyError as e:
            Logger.warning(f"Raytracing uniform missing: {e}")
            return False
        sky_comp = None
        try:
            from core.components.rendering.environment.skyp import ProceduralSky, _get_moon_texture, _get_white_tex
            for ent in scene.get_entities_with_component(ProceduralSky):
                sc = ent.get_component(ProceduralSky)
                if sc and sc.enabled:
                    sky_comp = sc
                    break
            if sky_comp is not None:
                sky_comp._sync_sun_light()
        except Exception:
            sky_comp = None
        sun_dir = Vec3(0, -0.3, -1)
        sky_color, sky_intensity = [1.0, 0.95, 0.85], 1.0
        sl = sky_comp.get_sun_light() if sky_comp is not None else None
        if sl is not None:
            l, t = sl
            sun_dir = -t.forward
            sky_color, sky_intensity = Light.shader_radiance(l, t)
        else:
            for ent in scene.get_entities_with_component(Light):
                l = ent.get_component(Light)
                t = ent.transform
                if l and l.enabled and t and l.light_type == LightType.DIRECTIONAL:
                    sun_dir = -t.forward
                    sky_color, sky_intensity = Light.shader_radiance(l, t)
                    break
        sun_radius = 0.27
        sun_limb = 0.7
        sun_conv = 0.5
        try:
            from core.components.rendering.environment.atmosp import Atmosphere
            atmos = Atmosphere.for_scene(scene)
            if atmos is not None:
                sky_intensity = sky_intensity * float(getattr(atmos, "_sun_intensity", 1.0))
                sun_radius = float(getattr(atmos, "_sun_angular_radius", 0.27))
                sun_limb = float(getattr(atmos, "_sun_limb_darkening", 0.7))
                sun_conv = float(getattr(atmos, "_sun_convergence", 0.5))
        except Exception:
            pass
        try:
            self._sky_env_prog["u_sun_direction"] = (sun_dir.x, sun_dir.y, sun_dir.z)
            self._sky_env_prog["u_sun_color"] = (sky_color[0], sky_color[1], sky_color[2])
            self._sky_env_prog["u_sun_intensity"] = sky_intensity
            self._sky_env_prog["u_sun_angular_radius"] = sun_radius
            self._sky_env_prog["u_sun_limb_darkening"] = sun_limb
            self._sky_env_prog["u_sun_convergence"] = sun_conv
        except KeyError as e:
            Logger.warning(f"SkyEnv uniform missing: {e}")
        if sky_comp is not None:
            try:
                self._sky_env_prog["u_night_sky_enabled"] = 1.0 if sky_comp.night_sky_enabled else 0.0
                self._sky_env_prog["u_night_exposure"] = sky_comp.night_exposure
                self._sky_env_prog["u_star_enabled"] = 1.0 if sky_comp.star_enabled else 0.0
                self._sky_env_prog["u_star_density"] = sky_comp.star_density
                self._sky_env_prog["u_star_intensity"] = sky_comp.star_intensity
                self._sky_env_prog["u_star_scale"] = sky_comp.star_scale
                self._sky_env_prog["u_star_twinkle"] = sky_comp.star_twinkle
                self._sky_env_prog["u_star_seed"] = sky_comp.star_seed
                self._sky_env_prog["u_star_color"] = (sky_comp.star_color[0], sky_comp.star_color[1], sky_comp.star_color[2])
                self._sky_env_prog["u_star_pole"] = (sky_comp.star_pole.x, sky_comp.star_pole.y, sky_comp.star_pole.z)
                self._sky_env_prog["u_star_rotation"] = sky_comp.star_rotation
                self._sky_env_prog["u_milkyway_enabled"] = 1.0 if sky_comp.milky_way_enabled else 0.0
                self._sky_env_prog["u_milkyway_intensity"] = sky_comp.milky_way_intensity
                self._sky_env_prog["u_milkyway_pole"] = (sky_comp.milky_way_pole[0], sky_comp.milky_way_pole[1], sky_comp.milky_way_pole[2])
                self._sky_env_prog["u_moon_enabled"] = 1.0 if sky_comp.moon_enabled else 0.0
                self._sky_env_prog["u_moon_direction"] = (sky_comp.moon_direction[0], sky_comp.moon_direction[1], sky_comp.moon_direction[2])
                self._sky_env_prog["u_moon_size"] = sky_comp.moon_size
                self._sky_env_prog["u_moon_intensity"] = sky_comp.moon_intensity
                self._sky_env_prog["u_moon_phase"] = sky_comp.moon_phase
                self._sky_env_prog["u_time"] = sky_comp.twinkle_time
                moon_tex = _get_moon_texture(ctx, sky_comp.moon_texture_path)
                if moon_tex is None:
                    moon_tex = _get_white_tex(ctx)
                moon_tex.use(7)
                self._sky_env_prog["u_moon_tex"] = 7
                self._sky_env_prog["u_use_moon_tex"] = 1.0 if sky_comp.moon_texture_path else 0.0
            except KeyError as e:
                Logger.warning(f"SkyEnv night uniform missing: {e}")
            except Exception as e:
                Logger.warning(f"Failed to apply night sky: {e}")
        self._sky_env_tex.bind_to_image(0, read=False, write=True)
        self._sky_env_prog.run(group_x=(256 + 7) // 8, group_y=(128 + 7) // 8, group_z=1)
        ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)
        self._sky_env_tex.use(1)
        try:
            prog["u_sky_env"] = 1
        except KeyError:
            pass
        self._bvh_buf.bind_to_storage_buffer(0)
        self._vert_buf.bind_to_storage_buffer(1)
        self._idx_buf.bind_to_storage_buffer(2)
        self._mat_buf.bind_to_storage_buffer(3)
        self._inst_buf.bind_to_storage_buffer(4)
        self._light_buf.bind_to_storage_buffer(5)
        self._output_tex.bind_to_image(0, read=False, write=True)
        self._emissive_tex.bind_to_image(1, read=False, write=True)
        self._albedo_array_tex.use(2)
        try:
            prog["u_albedo_array"] = 2
            prog["u_albedo_tex_count"] = self._albedo_count
        except KeyError:
            pass
        if hasattr(renderer, "_raytracing_emissive_tex"):
            renderer._raytracing_emissive_tex = self._emissive_tex
        prog.run(group_x=(rw + 7) // 8, group_y=(rh + 7) // 8, group_z=1)
        ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)
        self._rays_per_frame = rw * rh * self._samples_per_pixel * (self._max_bounces + 1)
        self._frame += 1
        if self._accumulate:
            self._accum_frame += 1
        return True
    def _blit_to_fbo(self, ctx: moderngl.Context, target_fbo: moderngl.Framebuffer, width: int, height: int):
        if not self._output_fbo or not self._fullscreen_prog:
            return
        old_fbo = ctx.fbo
        target_fbo.use()
        target_fbo.viewport = (0, 0, width, height)
        self._output_tex.use(0)
        self._fullscreen_prog["u_tex"].value = 0
        ctx.viewport = (0, 0, width, height)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._fullscreen_quad.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)
        if old_fbo is not None:
            old_fbo.use()
    def blit_to_screen(self, ctx: moderngl.Context, width: int, height: int):
        if not self._show_overlay or not self._output_fbo or not self._fullscreen_prog:
            return
        self._output_tex.use(0)
        self._fullscreen_prog["u_tex"].value = 0
        ctx.viewport = (0, 0, width, height)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._fullscreen_quad.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)
