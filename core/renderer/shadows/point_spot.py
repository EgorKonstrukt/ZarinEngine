# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
import moderngl
from core.maths.math3d import Vec3, Mat4
from core.renderer.origin import shift_vp_bytes, relativize_chunk_f32
from .mathx import _tr_pos_xyz, _tr_fwd_xyz, _POINT_FACE_DIRS, _POINT_FACE_UPS, MAX_POINT_SHADOWS, MAX_SPOT_SHADOWS
class PointSpotMixin:
    def _create_point_shadow_resources(self):
        self._ensure_context()
        for sm in self._point_shadow_maps:
            try:
                sm.release()
            except Exception:
                pass
        for fbo in self._point_shadow_fbos:
            try:
                fbo.release()
            except Exception:
                pass
        self._point_shadow_maps = []; self._point_shadow_fbos = []
        res = self._point_shadow_resolution
        try:
            tex = self._ctx.depth_texture((res * 6, res * MAX_POINT_SHADOWS))
        except Exception:
            return
        tex.repeat_x = False; tex.repeat_y = False
        try:
            fbo = self._ctx.framebuffer(depth_attachment=tex)
        except Exception:
            try:
                tex.release()
            except Exception:
                pass
            return
        self._point_shadow_maps.append(tex); self._point_shadow_fbos.append(fbo)
        try:
            self._point_static_key = None
        except Exception:
            pass
    def _create_spot_shadow_resources(self):
        self._ensure_context()
        for sm in self._spot_shadow_maps:
            try:
                sm.release()
            except Exception:
                pass
        for fbo in self._spot_shadow_fbos:
            try:
                fbo.release()
            except Exception:
                pass
        self._spot_shadow_maps = []; self._spot_shadow_fbos = []
        res = self._spot_shadow_resolution
        try:
            tex = self._ctx.depth_texture((res * MAX_SPOT_SHADOWS, res))
        except Exception:
            return
        tex.repeat_x = False; tex.repeat_y = False
        try:
            fbo = self._ctx.framebuffer(depth_attachment=tex)
        except Exception:
            try:
                tex.release()
            except Exception:
                pass
            return
        self._spot_shadow_maps.append(tex); self._spot_shadow_fbos.append(fbo)
        try:
            self._spot_static_key = None
        except Exception:
            pass
    @staticmethod
    def _filter_by_range(shadow_groups: dict, light_x: float, light_y: float, light_z: float, range_sq: float) -> dict:
        try:
            base_range = math.sqrt(max(float(range_sq), 0.0))
        except Exception:
            base_range = 0.0
        result = {}
        for mid, group in shadow_groups.items():
            near = []
            for mesh, tr in group:
                try:
                    if tr._dirty:
                        tr._update_world_matrix()
                    p = tr._world_matrix._d
                except Exception:
                    continue
                dx = p[3][0] - light_x; dy = p[3][1] - light_y; dz = p[3][2] - light_z; dsq = dx * dx + dy * dy + dz * dz
                try:
                    br = float(mesh.bounding_radius)
                except Exception:
                    br = 1.0
                try:
                    wm = p
                    sx = math.sqrt(wm[0, 0] * wm[0, 0] + wm[1, 0] * wm[1, 0] + wm[2, 0] * wm[2, 0])
                    sy = math.sqrt(wm[0, 1] * wm[0, 1] + wm[1, 1] * wm[1, 1] + wm[2, 1] * wm[2, 1])
                    sz = math.sqrt(wm[0, 2] * wm[0, 2] + wm[1, 2] * wm[1, 2] + wm[2, 2] * wm[2, 2])
                    ms = sx
                    if sy > ms:
                        ms = sy
                    if sz > ms:
                        ms = sz
                except Exception:
                    ms = 1.0
                rr = base_range + ms * br
                if dsq <= rr * rr:
                    near.append((mesh, tr))
            if near:
                result[mid] = near
        return result
    def _point_proj(self, light_range: float):
        key = round(float(light_range), 3)
        p = self._point_proj_cache.get(key)
        if p is None:
            p = Mat4.perspective(90.0, 1.0, 0.1, max(float(light_range), 0.1))._d
            self._point_proj_cache[key] = p
            if len(self._point_proj_cache) > 16:
                try:
                    self._point_proj_cache.pop(next(iter(self._point_proj_cache)))
                except Exception:
                    pass
        return p
    def _render_point_shadow_for_slot(self, slot, point_light, point_transform, shadow_groups, lights):
        try:
            lp_x, lp_y, lp_z = _tr_pos_xyz(point_transform); light_pos = Vec3(lp_x, lp_y, lp_z)
        except Exception:
            light_pos = point_transform.position; lp_x, lp_y, lp_z = light_pos.x, light_pos.y, light_pos.z
        light_range = max(float(getattr(point_light, 'range', 10.0)), 0.1); lr2 = light_range * light_range
        self._point_shadow_light_positions[slot] = light_pos; self._point_shadow_light_ranges[slot] = light_range
        self._point_shadow_light_indices[slot] = next((i for i, (l, lt) in enumerate(lights) if l is point_light and lt is point_transform), -1)
        if self._flat_n == 0:
            return
        proj_np = self._point_proj(light_range); prog = self._prog; shadow_res = self._point_shadow_resolution
        supports_instancing = self._supports_instancing_cached(prog); names = self._uniform_names(prog)
        use_inst = "u_use_instancing" in names; umodel = "u_model" in names; prog_id = id(prog); base = slot * 6
        try:
            _flat_mats_now = self._flat_mats
        except Exception:
            _flat_mats_now = None
        try:
            self._point_shadow_fbos[0].use()
        except Exception:
            return
        self._shadow_depth_state()
        if use_inst:
            prog["u_use_instancing"].value = 1 if supports_instancing else 0
        for face_idx in range(6):
            self._ctx.viewport = (face_idx * shadow_res, slot * shadow_res, shadow_res, shadow_res)
            dx, dy, dz = _POINT_FACE_DIRS[face_idx]; ux, uy, uz = _POINT_FACE_UPS[face_idx]
            try:
                face_dir = Vec3(dx, dy, dz); face_up = Vec3(ux, uy, uz)
                vp = (Mat4.look_at(light_pos, light_pos + face_dir, face_up)._d @ proj_np).astype(np.float32)
            except Exception:
                continue
            self._point_light_vps[base + face_idx] = vp
            try:
                cnt = self._cull_flat_range_count(vp, lp_x, lp_y, lp_z, lr2, 0.0)
            except Exception:
                cnt = 0
            if cnt <= 0 or _flat_mats_now is None:
                continue
            try:
                vis = self._flat_out[:cnt]
            except Exception:
                continue
            prog["u_light_vp"].write(shift_vp_bytes(vp, self._shadow_origin))
            if supports_instancing:
                for mesh, sel, chunk in self._iter_flat_groups_fast(vis, _flat_mats_now):
                    vbo = self._upload_instanced_mats((id(mesh), prog_id, ("p", slot, face_idx)), chunk, sel); vao = self._get_shadow_vao(prog, mesh, vbo); vao.render(instances=int(sel.size))
            else:
                for mesh, sel, chunk in self._iter_flat_groups_fast(vis, _flat_mats_now):
                    if umodel:
                        for j in range(int(sel.size)):
                            prog["u_model"].write(relativize_chunk_f32(chunk[j], self._shadow_origin).tobytes()); mesh.render(prog)
                    else:
                        for _j in range(int(sel.size)):
                            mesh.render(prog)
        self._ctx.enable(moderngl.CULL_FACE)
    def _spot_proj(self, fov: float, far: float):
        key = (round(float(fov), 2), round(float(far), 2))
        p = self._spot_proj_cache.get(key)
        if p is None:
            p = Mat4.perspective(max(float(fov), 1.0), 1.0, 0.1, max(float(far), 0.2))._d
            self._spot_proj_cache[key] = p
            if len(self._spot_proj_cache) > 16:
                try:
                    self._spot_proj_cache.pop(next(iter(self._spot_proj_cache)))
                except Exception:
                    pass
        return p
    def _render_spot_shadow_for_slot(self, slot, spot_light, spot_transform, shadow_groups, lights):
        try:
            lp_x, lp_y, lp_z = _tr_pos_xyz(spot_transform); light_pos = Vec3(lp_x, lp_y, lp_z)
            fdx, fdy, fdz = _tr_fwd_xyz(spot_transform); light_dir = Vec3(fdx, fdy, fdz)
        except Exception:
            light_pos = spot_transform.position; light_dir = spot_transform.forward.normalized(); lp_x, lp_y, lp_z = light_pos.x, light_pos.y, light_pos.z
        light_range = max(float(getattr(spot_light, 'range', 10.0)), 0.1)
        spot_fov = max(float(getattr(spot_light, 'spot_angle', 30.0)) * 2.0, 1.0); lr2 = light_range * light_range
        if self._flat_n == 0:
            return
        proj_d = self._spot_proj(spot_fov, light_range)
        try:
            view_d = Mat4.look_at(light_pos, light_pos + light_dir, Vec3.up())._d
            vp = (view_d @ proj_d).astype(np.float32)
        except Exception:
            return
        self._spot_shadow_vps[slot] = vp
        self._spot_shadow_light_indices[slot] = next((i for i, (l, lt) in enumerate(lights) if l is spot_light and lt is spot_transform), -1)
        try:
            cnt = self._cull_flat_range_count(vp, lp_x, lp_y, lp_z, lr2, 0.0)
        except Exception:
            cnt = 0
        if cnt > 0:
            try:
                _res = self._spot_shadow_resolution; _tile = (slot * _res, 0, _res, _res)
                self._draw_flat_visible(vp, self._spot_shadow_fbos[0], _res, cnt, ("s", slot), _tile, False)
                self._maybe_render_skinned(vp, self._spot_shadow_fbos[0], _res, _tile)
            except Exception:
                pass
