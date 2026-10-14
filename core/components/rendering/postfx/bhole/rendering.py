# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
import moderngl


class BlackHoleRenderingMixin:
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
        hole = (0.0, 0.0, 0.0)
        normal = (0.0, 1.0, 0.0)
        if tr is None:
            bypass = 1.0
        else:
            try:
                p = tr.position
                hole = (float(p.x), float(p.y), float(p.z))
            except Exception:
                bypass = 1.0
            try:
                u = tr.up
                normal = (float(u.x), float(u.y), float(u.z))
            except Exception:
                normal = (0.0, 1.0, 0.0)
        rs = max(float(self._schwarzschild_radius), 0.05)
        inner_w = max(float(self._disk_inner) * rs, rs * 1.05)
        outer_w = max(float(self._disk_outer) * rs, inner_w + 0.01)
        prog["u_input_tex"] = 0
        tex.use(0)
        prog["u_depth_tex"] = 1
        scene_depth_tex.use(1)
        prog["u_view"].write(view_mat.to_f32().tobytes())
        prog["u_proj"].write(proj_mat.to_f32().tobytes())
        prog["u_inv_view"].write(view_mat.inverted().to_f32().tobytes())
        prog["u_inv_proj"].write(proj_mat.inverted().to_f32().tobytes())
        if "u_camera_pos" in prog:
            prog["u_camera_pos"].value = (float(cam_pos.x), float(cam_pos.y), float(cam_pos.z))
        if "u_hole_pos" in prog:
            prog["u_hole_pos"].value = hole
        if "u_disk_normal" in prog:
            prog["u_disk_normal"].value = normal
        if "u_rs" in prog:
            prog["u_rs"].value = rs
        if "u_lensing" in prog:
            prog["u_lensing"].value = max(float(self._lensing_strength), 0.0)
        if "u_disk_inner" in prog:
            prog["u_disk_inner"].value = inner_w
        if "u_disk_outer" in prog:
            prog["u_disk_outer"].value = outer_w
        if "u_inner_color" in prog:
            prog["u_inner_color"].value = tuple(float(v) for v in self._inner_color)
        if "u_outer_color" in prog:
            prog["u_outer_color"].value = tuple(float(v) for v in self._outer_color)
        if "u_disk_brightness" in prog:
            prog["u_disk_brightness"].value = float(self._disk_brightness)
        if "u_spin_speed" in prog:
            prog["u_spin_speed"].value = float(self._rotation_speed)
        if "u_doppler" in prog:
            prog["u_doppler"].value = float(self._doppler_strength)
        if "u_time" in prog:
            prog["u_time"].value = float(time.perf_counter() % 3600.0)
        if "u_photon_intensity" in prog:
            prog["u_photon_intensity"].value = float(self._photon_intensity)
        if "u_photon_width" in prog:
            prog["u_photon_width"].value = float(self._photon_width)
        if "u_fringe" in prog:
            prog["u_fringe"].value = float(self._fringe)
        if "u_noise_amount" in prog:
            prog["u_noise_amount"].value = float(self._turbulence)
        if "u_show_disk" in prog:
            prog["u_show_disk"].value = 1.0 if self._show_disk else 0.0
        if "u_bypass" in prog:
            prog["u_bypass"].value = bypass
        ctx.disable(moderngl.BLEND)
        self._vao.render()
