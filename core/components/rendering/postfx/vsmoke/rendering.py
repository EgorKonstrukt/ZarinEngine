# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import time
import numpy as np
import moderngl


class VolumetricSmokeRenderingMixin:
    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        self._ensure_resources(ctx)
        tex = input_tex if input_tex is not None else scene_color_tex
        prog = self._prog
        tr = self.transform
        bypass = 0.0
        inv_model = None
        radius = 1.0
        if tr is None:
            bypass = 1.0
        else:
            try:
                wm = tr.world_matrix
                inv_model = wm.inverted()
                d = wm._d
                sx = math.sqrt(float(d[0, 0] * d[0, 0] + d[0, 1] * d[0, 1] + d[0, 2] * d[0, 2]))
                sy = math.sqrt(float(d[1, 0] * d[1, 0] + d[1, 1] * d[1, 1] + d[1, 2] * d[1, 2]))
                sz = math.sqrt(float(d[2, 0] * d[2, 0] + d[2, 1] * d[2, 1] + d[2, 2] * d[2, 2]))
                radius = max(sx, sy, sz)
                if not (radius > 1e-6):
                    bypass = 1.0
            except Exception:
                bypass = 1.0
                inv_model = None
        if bypass > 0.5:
            try:
                inv_model = view_mat.inverted()
            except Exception:
                pass
        prog["u_input_tex"] = 0
        tex.use(0)
        prog["u_depth_tex"] = 1
        scene_depth_tex.use(1)
        prog["u_inv_view"].write(view_mat.inverted().to_f32().tobytes())
        prog["u_inv_proj"].write(proj_mat.inverted().to_f32().tobytes())
        if inv_model is not None:
            prog["u_inv_model"].write(inv_model.to_f32().tobytes())
        if "u_camera_pos" in prog:
            prog["u_camera_pos"].value = (float(cam_pos.x), float(cam_pos.y), float(cam_pos.z))
        if "u_time" in prog:
            prog["u_time"].value = float(time.perf_counter() % 3600.0)
        if "u_seed" in prog:
            prog["u_seed"].value = float(self._seed)
        if "u_density" in prog:
            prog["u_density"].value = max(float(self._density), 0.0)
        if "u_opacity" in prog:
            prog["u_opacity"].value = min(1.0, max(0.0, float(self._opacity)))
        if "u_steps" in prog:
            prog["u_steps"].value = max(1, min(64, int(self._steps)))
        if "u_light_steps" in prog:
            prog["u_light_steps"].value = max(1, min(10, int(self._light_steps)))
        if "u_base_oct" in prog:
            prog["u_base_oct"].value = max(1, min(8, int(self._base_octaves)))
        if "u_ridge_oct" in prog:
            prog["u_ridge_oct"].value = max(1, min(8, int(self._ridge_octaves)))
        if "u_detail_oct" in prog:
            prog["u_detail_oct"].value = max(1, min(8, int(self._detail_octaves)))
        if "u_noise_scale" in prog:
            prog["u_noise_scale"].value = max(float(self._noise_scale), 0.01)
        if "u_evolution" in prog:
            prog["u_evolution"].value = max(float(self._evolution), 0.0)
        if "u_wind" in prog:
            prog["u_wind"].value = self._wind_tuple()
        if "u_wind_speed" in prog:
            prog["u_wind_speed"].value = max(float(self._wind_speed), 0.0)
        if "u_fullness" in prog:
            prog["u_fullness"].value = min(1.0, max(0.0, float(self._fullness)))
        if "u_filaments" in prog:
            prog["u_filaments"].value = min(1.0, max(0.0, float(self._filaments)))
        if "u_erosion" in prog:
            prog["u_erosion"].value = min(1.0, max(0.0, float(self._erosion)))
        if "u_cavity" in prog:
            prog["u_cavity"].value = min(0.9, max(0.0, float(self._cavity)))
        if "u_edge_softness" in prog:
            prog["u_edge_softness"].value = min(1.0, max(0.0, float(self._edge_softness)))
        if "u_fade_top" in prog:
            prog["u_fade_top"].value = min(1.0, max(0.0, float(self._fade_top)))
        if "u_fade_bottom" in prog:
            prog["u_fade_bottom"].value = min(1.0, max(0.0, float(self._fade_bottom)))
        if "u_deep" in prog:
            prog["u_deep"].value = tuple(float(v) for v in self._color_deep)
        if "u_mid" in prog:
            prog["u_mid"].value = tuple(float(v) for v in self._color_mid)
        if "u_core" in prog:
            prog["u_core"].value = tuple(float(v) for v in self._color_core)
        if "u_core_size" in prog:
            prog["u_core_size"].value = min(1.0, max(0.05, float(self._core_size)))
        if "u_emission" in prog:
            prog["u_emission"].value = max(float(self._emission), 0.0)
        if "u_ambient" in prog:
            prog["u_ambient"].value = max(float(self._ambient), 0.0)
        sun_dir, sun_col = self._sun_light()
        if "u_sun_dir" in prog:
            prog["u_sun_dir"].value = sun_dir
        if "u_sun_color" in prog:
            prog["u_sun_color"].value = sun_col
        if "u_scatter" in prog:
            prog["u_scatter"].value = max(float(self._scatter), 0.0)
        if "u_aniso" in prog:
            prog["u_aniso"].value = min(0.95, max(0.0, float(self._anisotropy)))
        if "u_self_shadow" in prog:
            prog["u_self_shadow"].value = 1.0 if self._self_shadow else 0.0
        if "u_shadow_strength" in prog:
            prog["u_shadow_strength"].value = min(2.0, max(0.0, float(self._shadow_strength)))
        if "u_absorption" in prog:
            prog["u_absorption"].value = max(float(self._absorption), 0.0)
        if "u_radius" in prog:
            prog["u_radius"].value = max(float(radius), 1e-3)
        if "u_depth_fade" in prog:
            prog["u_depth_fade"].value = max(float(self._depth_fade), 0.0)
        if "u_bypass" in prog:
            prog["u_bypass"].value = bypass
        ctx.disable(moderngl.BLEND)
        self._vao.render()
