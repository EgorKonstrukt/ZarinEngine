# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
from typing import Optional

import moderngl
import numpy as np

from core.components.inspector_meta import FieldType, InspectorField
from core.ecs.ecs import Component, ComponentRegistry
from core.foundation.logger import Logger
from core.assets.compute_shader import compile_compute_shader
from core.renderer.shaders import program_with_fallback


@ComponentRegistry.register
class RadianceCascadesGI(Component):
    _allow_multiple = False

    NUM_CASCADES = 6

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Radiance Cascades Gi", FieldType.HEADER),
            InspectorField("enabled", "Enabled", FieldType.BOOL),
            InspectorField("_compute_shader_path", "Compute Shader", FieldType.RESOURCE_PATH,
                           file_filter="Compute (*.compute)"),
            InspectorField("_resolution_scale", "Resolution Scale", FieldType.FLOAT, 0.25, 1.0),
            InspectorField("_intensity", "GI Intensity", FieldType.FLOAT, 0.0, 5.0),
            InspectorField("_step_size", "Step Size", FieldType.FLOAT, 0.1, 2.0),
            InspectorField("_depth_threshold", "Depth Threshold", FieldType.FLOAT, 0.01, 1.0),
            InspectorField("_temporal_factor", "Temporal Blend", FieldType.FLOAT, 0.0, 0.99),
            InspectorField("_sky_intensity", "Sky Intensity", FieldType.FLOAT, 0.0, 4.0),
            InspectorField("_show_overlay", "Show Overlay", FieldType.BOOL),
            InspectorField("_debug_mode", "Debug Mode", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self._compute_shader_path: str = "core/shaders/compute/RadianceCascades.compute"
        self._resolution_scale: float = 0.5
        self._intensity: float = 1.0
        self._step_size: float = 0.5
        self._depth_threshold: float = 0.15
        self._temporal_factor: float = 0.85
        self._sky_intensity: float = 1.0
        self._show_overlay: bool = False
        self._debug_mode: bool = False

        self._program: Optional[moderngl.ComputeShader] = None
        self._cascade_atlas: Optional[moderngl.Texture] = None
        self._gi_output_tex: Optional[moderngl.Texture] = None
        self._gi_temp_tex: Optional[moderngl.Texture] = None
        self._history_tex: Optional[moderngl.Texture] = None
        self._gi_output_fbo: Optional[moderngl.Framebuffer] = None
        self._gi_temp_fbo: Optional[moderngl.Framebuffer] = None
        self._history_fbo: Optional[moderngl.Framebuffer] = None
        self._fullscreen_quad: Optional[moderngl.VertexArray] = None
        self._fullscreen_prog: Optional[moderngl.Program] = None

        self._ctx_id = 0
        self._prev_width: int = 0
        self._prev_height: int = 0
        self._frame: int = 0
        self._prev_view_proj: Optional[np.ndarray] = None

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "compute_shader_path": self._compute_shader_path,
            "resolution_scale": self._resolution_scale,
            "intensity": self._intensity,
            "step_size": self._step_size,
            "depth_threshold": self._depth_threshold,
            "temporal_factor": self._temporal_factor,
            "sky_intensity": self._sky_intensity,
            "show_overlay": self._show_overlay,
            "debug_mode": self._debug_mode,
        })
        return d

    @classmethod
    def _resolve_shader_path(cls, path: str) -> str:
        if path and not os.path.isabs(path) and not os.path.exists(os.path.abspath(path)):
            cand = "core/shaders/compute/" + os.path.basename(path).replace("\\", "/")
            if os.path.exists(os.path.abspath(cand)):
                return cand
        return path

    @classmethod
    def deserialize(cls, data: dict) -> RadianceCascadesGI:
        r = cls()
        r.enabled = data.get("enabled", True)
        r._compute_shader_path = cls._resolve_shader_path(
            data.get("compute_shader_path", "core/shaders/compute/RadianceCascades.compute"))
        r._resolution_scale = float(data.get("resolution_scale", 0.5))
        r._intensity = float(data.get("intensity", 1.0))
        r._step_size = float(data.get("step_size", 0.5))
        r._depth_threshold = float(data.get("depth_threshold", 0.15))
        r._temporal_factor = float(data.get("temporal_factor", 0.85))
        r._sky_intensity = float(data.get("sky_intensity", 1.0))
        r._show_overlay = data.get("show_overlay", False)
        r._debug_mode = data.get("debug_mode", False)
        return r

    def _set_opt(self, prog, name, value) -> bool:
        try:
            prog[name] = value
            return True
        except KeyError:
            return False
        except Exception:
            return False

    def _write_opt(self, prog, name, data: bytes) -> bool:
        try:
            prog[name].write(data)
            return True
        except KeyError:
            return False
        except Exception:
            return False

    def _compile_compute(self, ctx: moderngl.Context, path: str) -> Optional[moderngl.ComputeShader]:
        path = self._resolve_shader_path(path)
        self._compute_shader_path = path
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            Logger.error(f"Compute shader not found: {abs_path}")
            return None
        try:
            with open(abs_path) as f:
                src = f.read()
            glsl_start = src.find("GLSLPROGRAM")
            glsl_end = src.find("ENDGLSL", glsl_start)
            if glsl_start < 0 or glsl_end < 0:
                Logger.error("Invalid .compute file: no GLSLPROGRAM/ENDGLSL")
                return None
            source = src[glsl_start + len("GLSLPROGRAM"):glsl_end].strip()
            return compile_compute_shader(ctx, source, abs_path)
        except Exception as e:
            Logger.error(f"Failed to compile compute shader: {e}")
            return None

    def _ensure_resources(self, ctx: moderngl.Context, width: int, height: int):
        rw = max(1, int(width * self._resolution_scale))
        rh = max(1, int(height * self._resolution_scale))

        if self._program is None:
            prog = self._compile_compute(ctx, self._compute_shader_path)
            if prog is None:
                return False
            self._program = prog

        if self._fullscreen_prog is None:
            self._fullscreen_prog = program_with_fallback(
                ctx,
                vertex_shader="""
                #version 330 core
                in vec2 in_position;
                in vec2 in_uv;
                out vec2 v_uv;
                void main() {
                    gl_Position = vec4(in_position, 0.0, 1.0);
                    v_uv = in_uv;
                }
                """,
                fragment_shader="""
                #version 330 core
                in vec2 v_uv;
                uniform sampler2D u_tex;
                out vec4 frag_color;
                void main() {
                    frag_color = texture(u_tex, v_uv);
                }
                """,
                label="radiance_fullscreen"
            )

        if self._fullscreen_quad is None:
            fs_verts = np.array([
                -1, -1, 0, 0,
                 1, -1, 1, 0,
                 1,  1, 1, 1,
                -1, -1, 0, 0,
                 1,  1, 1, 1,
                -1,  1, 0, 1,
            ], dtype=np.float32)
            vbo = ctx.buffer(fs_verts.tobytes())
            self._fullscreen_quad = ctx.vertex_array(
                self._fullscreen_prog,
                [(vbo, "2f 2f", "in_position", "in_uv")],
            )

        if (self._gi_output_tex is None or self._prev_width != rw or self._prev_height != rh):
            for tex in [self._gi_output_tex, self._gi_temp_tex, self._history_tex]:
                if tex:
                    tex.release()
            for fbo in [self._gi_output_fbo, self._gi_temp_fbo, self._history_fbo]:
                if fbo:
                    fbo.release()
            self._gi_output_tex = self._make_tex(ctx, rw, rh, moderngl.LINEAR)
            self._gi_temp_tex = self._make_tex(ctx, rw, rh, moderngl.LINEAR)
            self._history_tex = self._make_tex(ctx, rw, rh, moderngl.LINEAR)
            self._gi_output_fbo = ctx.framebuffer(color_attachments=[self._gi_output_tex])
            self._gi_temp_fbo = ctx.framebuffer(color_attachments=[self._gi_temp_tex])
            self._history_fbo = ctx.framebuffer(color_attachments=[self._history_tex])
            self._prev_width = rw
            self._prev_height = rh
            self._frame = 0
            self._prev_view_proj = None
            try:
                self._history_fbo.clear(0.0, 0.0, 0.0, 0.0)
                self._gi_output_fbo.clear(0.0, 0.0, 0.0, 0.0)
                self._gi_temp_fbo.clear(0.0, 0.0, 0.0, 0.0)
            except Exception:
                pass

        if (self._cascade_atlas is None or self._cascade_atlas.width != rw or self._cascade_atlas.height != rh):
            if self._cascade_atlas:
                self._cascade_atlas.release()
            self._cascade_atlas = self._make_tex(ctx, rw, rh, moderngl.NEAREST)

        return True

    def _make_tex(self, ctx, w, h, filter_mode):
        tex = ctx.texture((w, h), 4, dtype="f4")
        tex.filter = (filter_mode, filter_mode)
        tex.repeat_x = False
        tex.repeat_y = False
        return tex

    def _gather_environment(self, scene, renderer):
        sky_ambient = [0.26, 0.28, 0.34]
        try:
            amb = getattr(renderer, "_ambient", None)
            if amb is not None and len(amb) >= 3:
                sky_ambient = [float(amb[0]), float(amb[1]), float(amb[2])]
        except Exception:
            pass
        sun_dir = (0.0, 1.0, 0.0)
        sun_color = [1.0, 1.0, 1.0]
        sun_intensity = 0.0
        try:
            from core.components import LightType
            from core.components.lighting import Light
            ents = scene.get_entities_with_component(Light)
            for ent in ents:
                if not ent.active:
                    continue
                l = ent.get_component(Light)
                t = ent.transform
                if not l or not l.enabled or not t:
                    continue
                if l.light_type == LightType.DIRECTIONAL:
                    f = t.forward
                    sun_dir = (float(-f.x), float(-f.y), float(-f.z))
                    try:
                        c, ii = Light.shader_radiance(l, t)
                        sun_color = [float(c[0]), float(c[1]), float(c[2])]
                        sun_intensity = float(ii)
                    except Exception:
                        pass
                    break
        except Exception:
            pass
        return sky_ambient, sun_dir, sun_color, sun_intensity

    def _dispatch(self, ctx: moderngl.Context, width: int, height: int,
                  view_mat, proj_mat, cam_pos, scene, renderer,
                  cam_near: float = 0.01, cam_far: float = 1000.0) -> bool:
        ctx_id = id(ctx)
        if self._ctx_id != ctx_id:
            self._release_gl()
            self._ctx_id = ctx_id

        if not self._ensure_resources(ctx, width, height):
            return False

        rw = max(1, int(width * self._resolution_scale))
        rh = max(1, int(height * self._resolution_scale))

        prog = self._program
        if prog is None:
            return False

        cam_pos_tuple = (cam_pos.x, cam_pos.y, cam_pos.z)

        ctx.disable(moderngl.DEPTH_TEST)

        try:
            prog["u_screen_size"] = (float(rw), float(rh))
            prog["u_camera_pos"] = cam_pos_tuple
            prog["u_step_size"] = self._step_size
            prog["u_depth_threshold"] = self._depth_threshold
            prog["u_intensity"] = self._intensity
            prog["u_temporal_factor"] = self._temporal_factor
            prog["u_num_cascades"] = self.NUM_CASCADES
            prog["u_frame"] = self._frame
        except KeyError as e:
            Logger.warning(f"RadianceCascades uniform missing: {e}")
            return False

        sky_ambient, sun_dir, sun_color, sun_intensity = self._gather_environment(scene, renderer)
        self._set_opt(prog, "u_sky_ambient", (sky_ambient[0], sky_ambient[1], sky_ambient[2]))
        self._set_opt(prog, "u_sun_dir", sun_dir)
        self._set_opt(prog, "u_sun_color", (sun_color[0], sun_color[1], sun_color[2]))
        self._set_opt(prog, "u_sun_intensity", float(sun_intensity))
        self._set_opt(prog, "u_sky_intensity", float(self._sky_intensity))
        self._set_opt(prog, "u_cam_near", float(cam_near))
        self._set_opt(prog, "u_cam_far", float(cam_far))

        try:
            vp = (view_mat @ proj_mat)._d
            inv_vp = np.linalg.inv(vp)
            prog["u_inv_view_proj"].write(inv_vp.astype(np.float32).tobytes())
            prog["u_view_proj"].write(vp.astype(np.float32).tobytes())
            if self._prev_view_proj is not None:
                prog["u_prev_view_proj"].write(
                    self._prev_view_proj.astype(np.float32).tobytes()
                )
            else:
                prog["u_prev_view_proj"].write(vp.astype(np.float32).tobytes())
            self._prev_view_proj = vp.copy()
        except KeyError as e:
            Logger.warning(f"RadianceCascades uniform missing: {e}")
            return False
        except Exception as e:
            Logger.warning(f"RadianceCascades matrix setup failed: {e}")
            return False

        depth_tex = getattr(renderer, '_scene_depth_tex', None)
        color_tex = getattr(renderer, '_scene_color_tex', None)
        if depth_tex is None or color_tex is None:
            return False

        depth_tex.use(0)
        color_tex.use(1)
        try:
            prog["u_depth_tex"] = 0
            prog["u_color_tex"] = 1
        except KeyError as e:
            Logger.warning(f"RadianceCascades texture uniform missing: {e}")
            return False

        groups_x = (rw + 7) // 8
        groups_y = (rh + 7) // 8

        try:
            prog["u_mode"] = 0
        except KeyError as e:
            Logger.warning(f"RadianceCascades texture uniform missing: {e}")
            return False
        self._cascade_atlas.bind_to_image(2, read=False, write=True)
        prog.run(groups_x, groups_y, 1)
        ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)

        self._cascade_atlas.bind_to_image(2, read=True, write=False)
        self._gi_output_tex.bind_to_image(3, read=False, write=True)

        if self._debug_mode:
            if not self._set_opt(prog, "u_mode", 2):
                return False
            prog.run(groups_x, groups_y, 1)
            ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)
        elif self._show_overlay:
            if not self._set_opt(prog, "u_mode", 6):
                return False
            prog.run(groups_x, groups_y, 1)
            ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)
        else:
            if not self._set_opt(prog, "u_mode", 1):
                return False
            prog.run(groups_x, groups_y, 1)
            ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)

            if self._frame > 0:
                self._history_tex.use(4)
                if self._set_opt(prog, "u_history_tex", 4):
                    if not self._set_opt(prog, "u_mode", 5):
                        return False
                    prog.run(groups_x, groups_y, 1)
                    ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)

            self._gi_temp_tex.bind_to_image(3, read=False, write=True)
            self._gi_output_tex.use(5)
            if self._set_opt(prog, "u_gi_input_tex", 5):
                if not self._set_opt(prog, "u_mode", 3):
                    return False
                prog.run(groups_x, groups_y, 1)
                ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)

                self._gi_output_tex.bind_to_image(3, read=False, write=True)
                self._gi_temp_tex.use(5)
                if self._set_opt(prog, "u_gi_input_tex", 5):
                    if not self._set_opt(prog, "u_mode", 4):
                        return False
                    prog.run(groups_x, groups_y, 1)
                    ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)

            if self._history_fbo and self._gi_output_fbo:
                try:
                    ctx.copy_framebuffer(self._history_fbo, self._gi_output_fbo)
                except Exception:
                    pass

        self._frame += 1
        return True

    def _blit_to_fbo(self, ctx: moderngl.Context, target_fbo: moderngl.Framebuffer, width: int, height: int):
        if not self._gi_output_fbo or not self._fullscreen_prog:
            return
        old_fbo = ctx.fbo
        target_fbo.use()
        target_fbo.viewport = (0, 0, width, height)
        self._gi_output_tex.use(0)
        self._fullscreen_prog["u_tex"].value = 0
        ctx.viewport = (0, 0, width, height)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        self._fullscreen_quad.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)
        if old_fbo is not None:
            old_fbo.use()

    def blit_to_screen(self, ctx: moderngl.Context, width: int, height: int):
        if not self._gi_output_fbo or not self._fullscreen_prog:
            return
        self._gi_output_tex.use(0)
        self._fullscreen_prog["u_tex"].value = 0
        ctx.viewport = (0, 0, width, height)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        if self._show_overlay or self._debug_mode:
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        else:
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        self._fullscreen_quad.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)

    def on_destroy(self):
        self._release_gl()

    def on_disable(self):
        self._release_gl()

    def _release_gl(self):
        for tex in [self._cascade_atlas, self._gi_output_tex, self._gi_temp_tex, self._history_tex]:
            if tex:
                tex.release()
        self._cascade_atlas = None
        self._gi_output_tex = None
        self._gi_temp_tex = None
        self._history_tex = None
        for fbo in [self._gi_output_fbo, self._gi_temp_fbo, self._history_fbo]:
            if fbo:
                fbo.release()
        self._gi_output_fbo = None
        self._gi_temp_fbo = None
        self._history_fbo = None
        if self._program:
            self._program.release()
            self._program = None
        if self._fullscreen_prog:
            self._fullscreen_prog.release()
            self._fullscreen_prog = None
        if self._fullscreen_quad:
            self._fullscreen_quad.release()
            self._fullscreen_quad = None
        self._prev_view_proj = None
        self._frame = 0
