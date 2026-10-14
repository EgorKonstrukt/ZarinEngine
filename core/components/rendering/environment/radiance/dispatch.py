# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
import numpy as np
from core.foundation.logger import Logger
class RadianceDispatchMixin:
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
    def _run(self, ctx, prog, mode, gx, gy):
        if not self._set_opt(prog, "u_mode", mode):
            return False
        prog.run((gx + 7) // 8, (gy + 7) // 8, 1)
        ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)
        return True
    def _dispatch(self, ctx: moderngl.Context, width: int, height: int, view_mat, proj_mat, cam_pos, scene, renderer, cam_near: float = 0.01, cam_far: float = 1000.0) -> bool:
        ctx_id = id(ctx)
        if self._ctx_id != ctx_id:
            self._release_gl()
            self._ctx_id = ctx_id
        if not self._ensure_resources(ctx, width, height):
            return False
        rw = max(1, int(width * self._resolution_scale * 0.25))
        rh = max(1, int(height * self._resolution_scale * 0.25))
        prog = self._program
        if prog is None:
            return False
        ctx.disable(moderngl.DEPTH_TEST)
        try:
            prog["u_screen_size"] = (float(rw), float(rh))
            prog["u_camera_pos"] = (cam_pos.x, cam_pos.y, cam_pos.z)
        except KeyError as e:
            Logger.warning(f"RadianceCascades uniform missing: {e}")
            return False
        try:
            collected = self._rt._collect_and_upload(ctx, scene, view_mat, proj_mat, cam_pos, renderer)
        except Exception as e:
            Logger.warning(f"RadianceCascades scene collection failed: {e}")
            collected = False
        if not collected:
            try:
                self._gi_output_fbo.clear(0.0, 0.0, 0.0, 0.0)
                if self._history_fbo and self._gi_output_fbo:
                    ctx.copy_framebuffer(self._history_fbo, self._gi_output_fbo)
            except Exception:
                pass
            self._frame += 1
            return True
        try:
            prog["u_instance_count"] = int(self._rt._inst_np.shape[0])
            prog["u_light_count"] = int(self._rt._light_np.shape[0])
        except KeyError as e:
            Logger.warning(f"RadianceCascades uniform missing: {e}")
            return False
        except Exception as e:
            Logger.warning(f"RadianceCascades scene data invalid: {e}")
            return False
        sky_ambient, sun_dir, sun_color, sun_intensity = self._gather_environment(scene, renderer)
        self._set_opt(prog, "u_sky_ambient", (sky_ambient[0], sky_ambient[1], sky_ambient[2]))
        self._set_opt(prog, "u_sun_dir", sun_dir)
        self._set_opt(prog, "u_sun_color", (sun_color[0], sun_color[1], sun_color[2]))
        self._set_opt(prog, "u_sun_intensity", float(sun_intensity))
        self._set_opt(prog, "u_sky_intensity", float(self._sky_intensity))
        self._set_opt(prog, "u_cam_near", float(cam_near))
        self._set_opt(prog, "u_cam_far", float(cam_far))
        self._set_opt(prog, "u_intensity", float(self._intensity))
        self._set_opt(prog, "u_temporal_factor", float(self._temporal_factor))
        self._set_opt(prog, "u_num_cascades", int(self.NUM_CASCADES))
        self._set_opt(prog, "u_frame", int(self._frame))
        self._set_opt(prog, "u_base_range", float(self._base_range))
        try:
            vp = (view_mat @ proj_mat)._d
            inv_vp = np.linalg.inv(vp)
            prog["u_inv_view_proj"].write(inv_vp.astype(np.float32).tobytes())
            self._set_opt(prog, "u_view_proj", vp.astype(np.float32).tobytes())
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
        depth_tex = getattr(renderer, "_scene_depth_tex", None)
        if depth_tex is None:
            return False
        depth_tex.use(0)
        try:
            prog["u_depth_tex"] = 0
        except KeyError as e:
            Logger.warning(f"RadianceCascades texture uniform missing: {e}")
            return False
        try:
            self._rt._bvh_buf.bind_to_storage_buffer(0)
            self._rt._vert_buf.bind_to_storage_buffer(1)
            self._rt._idx_buf.bind_to_storage_buffer(2)
            self._rt._mat_buf.bind_to_storage_buffer(3)
            self._rt._inst_buf.bind_to_storage_buffer(4)
            self._rt._light_buf.bind_to_storage_buffer(5)
        except Exception as e:
            Logger.warning(f"RadianceCascades buffer bind failed: {e}")
            return False
        if self._rt._albedo_array_tex is not None:
            self._rt._albedo_array_tex.use(6)
            self._set_opt(prog, "u_albedo_array", 6)
        self._set_opt(prog, "u_albedo_tex_count", int(self._rt._albedo_count))
        if self._debug_mode:
            self._gi_output_tex.bind_to_image(7, read=False, write=True)
            if not self._run(ctx, prog, self.MODE_DEBUG_TEST, rw, rh):
                return False
        elif self._show_overlay:
            for c in range(self.NUM_CASCADES):
                if not self._trace_cascade(ctx, prog, rw, rh, c):
                    return False
            if not self._run_normals(ctx, prog, rw, rh):
                return False
            self._bind_cascades_read()
            self._bind_normal_tex(prog)
            self._gi_output_tex.bind_to_image(7, read=False, write=True)
            if not self._run(ctx, prog, self.MODE_DEBUG_ATLAS, rw, rh):
                return False
        else:
            for c in range(self.NUM_CASCADES):
                if not self._trace_cascade(ctx, prog, rw, rh, c):
                    return False
            if not self._run_normals(ctx, prog, rw, rh):
                return False
            self._bind_cascades_read()
            self._bind_normal_tex(prog)
            self._gi_output_tex.bind_to_image(7, read=False, write=True)
            if not self._run(ctx, prog, self.MODE_RECONSTRUCT, rw, rh):
                return False
            if self._frame > 0:
                self._history_tex.use(4)
                if self._set_opt(prog, "u_history_tex", 4):
                    if not self._run(ctx, prog, self.MODE_TEMPORAL, rw, rh):
                        return False
            if not self._set_opt(prog, "u_gi_input_tex", 5):
                return False
            cur_out = True
            for step in (1, 2, 4):
                if not self._set_opt(prog, "u_blur_step", int(step)):
                    return False
                for mode in (self.MODE_BLUR_H, self.MODE_BLUR_V):
                    if cur_out:
                        self._gi_temp_tex.bind_to_image(7, read=False, write=True)
                        self._gi_output_tex.use(5)
                    else:
                        self._gi_output_tex.bind_to_image(7, read=False, write=True)
                        self._gi_temp_tex.use(5)
                    prog["u_gi_input_tex"] = 5
                    if not self._run(ctx, prog, mode, rw, rh):
                        return False
                    cur_out = not cur_out
            if self._history_fbo and self._gi_output_fbo:
                try:
                    ctx.copy_framebuffer(self._history_fbo, self._gi_output_fbo)
                except Exception:
                    pass
        self._frame += 1
        return True
    def _trace_cascade(self, ctx, prog, rw, rh, c) -> bool:
        gw, gh = self._cas_grid(rw, rh, c)
        tex = self._cas_tex[c]
        if tex is None:
            return False
        tex.bind_to_image(2, read=False, write=True)
        self._set_opt(prog, "u_cascade", int(c))
        self._set_opt(prog, "u_trace_stride", int(self.CASCADE_STRIDES[c]))
        self._set_opt(prog, "u_trace_dirs", int(self.CASCADE_DIRS[c]))
        return self._run(ctx, prog, self.MODE_TRACE, gw * self.CASCADE_DIRS[c], gh)
    def _bind_cascades_read(self):
        for c in range(self.NUM_CASCADES):
            tex = self._cas_tex[c]
            if tex is not None:
                tex.bind_to_image(2 + c, read=True, write=False)
    def _bind_normal_tex(self, prog) -> None:
        if self._normal_tex is not None:
            self._normal_tex.use(7)
            self._set_opt(prog, "u_normal_tex", 7)
    def _run_normals(self, ctx, prog, rw, rh) -> bool:
        if self._normal_tex is None:
            return False
        self._normal_tex.bind_to_image(7, read=False, write=True)
        return self._run(ctx, prog, self.MODE_NORMALS, rw, rh)
