# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3, Mat4
from .mathx import _tr_pos_xyz, _tr_fwd_xyz, _tr_up_xyz
class AreaMixin:
    def _create_area_shadow_resources(self):
        self._ensure_context()
        res = self._area_shadow_resolution
        try:
            tex = self._ctx.depth_texture((res, res))
        except Exception:
            return
        tex.repeat_x = False; tex.repeat_y = False
        try:
            self._area_shadow_map = tex; self._area_shadow_fbo = self._ctx.framebuffer(depth_attachment=self._area_shadow_map)
        except Exception:
            try:
                tex.release()
            except Exception:
                pass
            return
        try:
            btex = self._ctx.depth_texture((res, res))
        except Exception:
            return
        btex.repeat_x = False; btex.repeat_y = False
        try:
            self._area_shadow_map_back = btex; self._area_shadow_fbo_back = self._ctx.framebuffer(depth_attachment=self._area_shadow_map_back)
        except Exception:
            try:
                btex.release()
            except Exception:
                pass
        try:
            self._area_static_key = None
        except Exception:
            pass
    def _render_area_shadow(self, area_light, area_transform, shadow_groups, lights):
        if not self._area_shadow_map:
            self._create_area_shadow_resources()
            if not self._area_shadow_map:
                self._has_area_shadow = False
                return
        try:
            lp_x, lp_y, lp_z = _tr_pos_xyz(area_transform); light_pos = Vec3(lp_x, lp_y, lp_z)
            fdx, fdy, fdz = _tr_fwd_xyz(area_transform); light_dir = Vec3(fdx, fdy, fdz)
            udx, udy, udz = _tr_up_xyz(area_transform); light_up = Vec3(udx, udy, udz)
        except Exception:
            light_pos = area_transform.position; light_dir = area_transform.forward.normalized(); light_up = area_transform.up.normalized(); lp_x, lp_y, lp_z = light_pos.x, light_pos.y, light_pos.z
        try:
            if abs(light_dir.dot(light_up)) > 0.999:
                light_up = Vec3(0.0, 0.0, 1.0)
        except Exception:
            pass
        light_range = max(float(getattr(area_light, 'range', 10.0)), 0.1); near_plane = 0.1; far_plane = light_range
        self._area_light_near = near_plane; self._area_light_far = far_plane
        try:
            aw = float(getattr(area_light, 'area_width', 1.0)); ah = float(getattr(area_light, 'area_height', 1.0))
        except Exception:
            aw = 1.0; ah = 1.0
        fov = max(90.0, min(150.0, math.degrees(2.0 * math.atan2(max(aw, ah) * 0.5, near_plane))))
        fov_rad = math.radians(fov); tan_half_fov = math.tan(fov_rad * 0.5)
        self._area_light_fov_scale = float(1.0 / max(1e-6, (2.0 * tan_half_fov)))
        try:
            self._area_shadow_bias = float(getattr(area_light, 'area_shadow_bias', 0.005))
        except Exception:
            self._area_shadow_bias = 0.005
        self._area_light_vp_back = np.eye(4, dtype=np.float32); self._has_area_shadow_back = False
        try:
            self._area_shadow_two_sided = 1.0 if bool(getattr(area_light, "area_double_sided", False)) else 0.0
        except Exception:
            self._area_shadow_two_sided = 0.0
        try:
            view_d = Mat4.look_at(light_pos, light_pos + light_dir, light_up)._d; proj_d = Mat4.perspective(fov, 1.0, near_plane, far_plane)._d
            vp = (view_d @ proj_d).astype(np.float32)
        except Exception:
            self._has_area_shadow = False
            return
        self._area_light_vp = vp; self._has_area_shadow = True; self._area_light_pos = light_pos
        self._area_light_range = light_range; self._area_light_size = max(aw, ah) * 0.5
        self._area_light_idx = next((i for i, (l, lt) in enumerate(lights) if l is area_light and lt is area_transform), -1)
        lr2 = light_range * light_range
        if self._flat_n == 0:
            return
        try:
            _a_static = (not self._flat_rebuilt_frame) and (not self._pending_skinned) and (self._shadow_frame_key is not None) and (self._shadow_frame_key == self._last_static_frame_key)
        except Exception:
            _a_static = False
        try:
            _akey = (self._shadow_frame_key, self._area_shadow_resolution, id(area_light), id(area_transform), float(lp_x), float(lp_y), float(lp_z), float(fdx), float(fdy), float(fdz), float(udx), float(udy), float(udz), float(light_range), float(aw), float(ah), float(self._area_shadow_two_sided))
        except Exception:
            _akey = None
        try:
            _askip = bool(_a_static) and (_akey is not None) and (_akey == self._area_static_key)
        except Exception:
            _askip = False
        if _askip:
            try:
                if float(self._area_shadow_two_sided) > 0.5 and self._area_shadow_fbo_back is not None:
                    try:
                        _bview_d = Mat4.look_at(light_pos, light_pos + (-light_dir), light_up)._d; _bproj_d = Mat4.perspective(fov, 1.0, near_plane, far_plane)._d
                        self._area_light_vp_back = (_bview_d @ _bproj_d).astype(np.float32)
                    except Exception:
                        pass
                    self._has_area_shadow_back = True
            except Exception:
                pass
            return
        self._draw_area_shadow_side(vp, lp_x, lp_y, lp_z, lr2, self._area_shadow_fbo)
        try:
            if not (float(self._area_shadow_two_sided) > 0.5):
                self._area_static_key = _akey
        except Exception:
            pass
        if self._area_shadow_two_sided > 0.5:
            try:
                if self._area_shadow_fbo_back is None:
                    self._create_area_shadow_resources()
            except Exception:
                pass
            if self._area_shadow_fbo_back is None:
                return
            try:
                bview_d = Mat4.look_at(light_pos, light_pos + (-light_dir), light_up)._d; bproj_d = Mat4.perspective(fov, 1.0, near_plane, far_plane)._d
                bvp = (bview_d @ bproj_d).astype(np.float32)
            except Exception:
                return
            self._area_light_vp_back = bvp; self._has_area_shadow_back = True
            self._draw_area_shadow_side(bvp, lp_x, lp_y, lp_z, lr2, self._area_shadow_fbo_back, ("a", 1))
            try:
                self._area_static_key = _akey
            except Exception:
                pass
    def _draw_area_shadow_side(self, vp, px: float, py: float, pz: float, lr2: float, fbo, tag=("a", 0)) -> bool:
        try:
            cnt = self._cull_flat_range_count(vp, px, py, pz, lr2, 0.0)
        except Exception:
            cnt = 0
        if cnt > 0:
            try:
                self._draw_flat_visible(vp, fbo, self._area_shadow_resolution, cnt, tag); self._maybe_render_skinned(vp, fbo, self._area_shadow_resolution)
            except Exception:
                pass
            return True
        try:
            if fbo is not None:
                fbo.use(); self._ctx.viewport = (0, 0, self._area_shadow_resolution, self._area_shadow_resolution); fbo.clear(depth=1.0)
        except Exception:
            pass
        return False
