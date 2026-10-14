# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3, Mat4
class ProjectorMixin:
    def _create_projector_shadow_resources(self):
        self._ensure_context()
        res = self._shadow_resolution
        for _ in range(2):
            try:
                tex = self._ctx.depth_texture((res, res))
            except Exception:
                continue
            tex.repeat_x = False; tex.repeat_y = False
            try:
                self._projector_shadow_maps.append(tex); self._projector_shadow_fbos.append(self._ctx.framebuffer(depth_attachment=tex))
            except Exception:
                try:
                    tex.release()
                except Exception:
                    pass
                continue
    def render_projector_shadows(self, projectors, renderable_shadow, shadow_groups: dict = None):
        self._shadow_origin = None
        if self._flat_n == 0:
            try:
                if shadow_groups is None:
                    shadow_groups = self._build_shadow_groups(renderable_shadow)
            except Exception:
                shadow_groups = {}
            if not shadow_groups:
                for i in range(2):
                    self._has_projector_shadow[i] = False
                return
            for i, pj in enumerate(projectors[:2]):
                if not pj.cast_shadows:
                    self._has_projector_shadow[i] = False
                    continue
                if len(self._projector_shadow_maps) <= i:
                    self._create_projector_shadow_resources()
                try:
                    light_pos_vec = Vec3(float(pj.position[0]), float(pj.position[1]), float(pj.position[2]))
                    light_dir_vec = Vec3(float(pj.direction[0]), float(pj.direction[1]), float(pj.direction[2])).normalized()
                    up_vec = Vec3(float(pj.up[0]), float(pj.up[1]), float(pj.up[2]))
                    view = Mat4.look_at(light_pos_vec, light_pos_vec + light_dir_vec, up_vec)
                    proj = Mat4.perspective(max(float(pj.spot_angle), 1.0), float(pj.aspect_ratio), max(float(pj.near_plane), 0.01), max(float(pj.far_plane), max(float(pj.near_plane), 0.01) + 0.1))
                    vp = (view._d @ proj._d).astype(np.float32)
                except Exception:
                    continue
                self._projector_light_vps[i] = vp; self._has_projector_shadow[i] = True
                try:
                    lr2 = float(pj.far_plane) * float(pj.far_plane)
                    filtered = self._filter_by_range(shadow_groups, float(pj.position[0]), float(pj.position[1]), float(pj.position[2]), lr2)
                except Exception:
                    filtered = shadow_groups
                if filtered:
                    try:
                        self._render_geometry_with_groups(vp, self._projector_shadow_fbos[i], filtered, resolution=self._shadow_resolution)
                    except Exception:
                        pass
            return
        for i, pj in enumerate(projectors[:2]):
            if not pj.cast_shadows:
                self._has_projector_shadow[i] = False
                continue
            if len(self._projector_shadow_maps) <= i:
                self._create_projector_shadow_resources()
            try:
                lp_x = float(pj.position[0]); lp_y = float(pj.position[1]); lp_z = float(pj.position[2])
                dx = float(pj.direction[0]); dy = float(pj.direction[1]); dz = float(pj.direction[2])
                inv = 1.0 / max(1e-12, math.sqrt(dx * dx + dy * dy + dz * dz))
                light_pos_vec = Vec3(lp_x, lp_y, lp_z); light_dir_vec = Vec3(dx * inv, dy * inv, dz * inv)
                up_vec = Vec3(float(pj.up[0]), float(pj.up[1]), float(pj.up[2]))
                spot_fov = max(float(pj.spot_angle), 1.0); near_plane = max(float(pj.near_plane), 0.01); far_plane = max(float(pj.far_plane), near_plane + 0.1)
                view = Mat4.look_at(light_pos_vec, light_pos_vec + light_dir_vec, up_vec)
                proj = Mat4.perspective(spot_fov, float(pj.aspect_ratio), near_plane, far_plane)
                vp = (view._d @ proj._d).astype(np.float32)
            except Exception:
                continue
            self._projector_light_vps[i] = vp; self._has_projector_shadow[i] = True; lr2 = far_plane * far_plane
            try:
                cnt = self._cull_flat_range_count(vp, lp_x, lp_y, lp_z, lr2, 0.0)
            except Exception:
                cnt = 0
            if cnt > 0:
                try:
                    self._draw_flat_visible(vp, self._projector_shadow_fbos[i], self._shadow_resolution, cnt, ("j", i))
                except Exception:
                    pass
            else:
                try:
                    self._projector_shadow_fbos[i].use(); self._ctx.viewport = (0, 0, self._shadow_resolution, self._shadow_resolution); self._projector_shadow_fbos[i].clear(depth=1.0)
                except Exception:
                    pass
        for i in range(len(projectors[:2]), 2):
            try:
                self._has_projector_shadow[i] = False
            except Exception:
                pass
