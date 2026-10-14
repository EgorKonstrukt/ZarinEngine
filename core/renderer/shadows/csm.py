# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math; import numpy as np; import moderngl
from core.maths.math3d import Vec3, Mat4
from core.renderer.origin import shift_vp_bytes, relativize_chunk_f32, relativize_model_f32
from .bind import compute_frustum_corners_out, build_directional_cascade_fast, frustum_cull_shadow_groups, compute_frustum_corners, _mat4_inv_fast
from .mathx import _tr_fwd_xyz
class CsmMixin:
    def _create_csm_resources(self):
        self._ensure_context()
        for sm in self._shadow_maps:
            try:
                sm.release()
            except Exception:
                pass
        for fbo in self._shadow_fbos:
            try:
                fbo.release()
            except Exception:
                pass
        self._shadow_maps = []; self._shadow_fbos = []
        self._cascade_valid = [False, False, False, False]; self._cascade_tile_x = [0, 0, 0, 0]
        self._cascade_tile_res = [0, 0, 0, 0]; self._cascade_atlas_w = 1; self._cascade_atlas_h = 1
        base = self._shadow_resolution; _tile_res = []
        for i in range(self._cascade_count):
            _tile_res.append(min(self._cascade_resolutions[i] if i < len(self._cascade_resolutions) else base, base))
        _w = sum(_tile_res); _h = max(_tile_res) if _tile_res else base
        if _w <= 0 or _h <= 0: return
        try:
            tex = self._ctx.depth_texture((_w, _h))
        except Exception:
            try:
                import time; time.sleep(0.01); tex = self._ctx.depth_texture((_w, _h))
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
        self._shadow_maps.append(tex); self._shadow_fbos.append(fbo); _x = 0
        for i, res in enumerate(_tile_res):
            if i < 4: self._cascade_tile_x[i] = _x; self._cascade_tile_res[i] = res
            _x += res
        self._cascade_atlas_w = _w; self._cascade_atlas_h = _h
    def _compute_cascade_splits(self, cam_near: float, cam_far: float) -> list[float]:
        if not self._cascade_splits_norm:
            return self._cascade_distances(cam_near, cam_far)
        near_z = max(cam_near, 0.01); far_z = max(near_z + 0.1, min(cam_far, self._shadow_distance)); norm = self._cascade_splits_norm; splits = []
        for i in range(self._cascade_count):
            splits.append(near_z + (far_z - near_z) * float(norm[i]) if i < len(norm) else far_z)
        return splits
    def _cascade_distances(self, cam_near: float, cam_far: float) -> list[float]:
        near_z = max(cam_near, 0.01); far_z = max(near_z + 0.1, min(cam_far, self._shadow_distance))
        if self._cascade_count <= 1:
            return [far_z, far_z, far_z, far_z]
        if self._cascade_count == 2:
            return [near_z + (far_z - near_z) * 0.2, far_z, far_z, far_z]
        if self._cascade_count == 3:
            return [near_z + (far_z - near_z) * 0.1, near_z + (far_z - near_z) * 0.3, far_z, far_z]
        span = far_z - near_z; lam = 0.9; splits = []
        for i in range(1, 5):
            p = i / 4.0
            log = near_z * (far_z / near_z) ** p if near_z > 0 else near_z + span * p
            uni = near_z + span * p; splits.append(lam * log + (1.0 - lam) * uni)
        splits[-1] = far_z
        return splits
    def _get_frustum_corners(self, near_z: float, far_z: float, cam_fov: float, aspect: float, inv_view: np.ndarray) -> list[np.ndarray]:
        if compute_frustum_corners is not None:
            return compute_frustum_corners(near_z, far_z, cam_fov, aspect, inv_view)
        tan_half_fov = math.tan(math.radians(cam_fov) * 0.5); corners = []
        for z in (near_z, far_z):
            half_h = tan_half_fov * z; half_w = half_h * aspect
            for y_sign in (-1, 1):
                for x_sign in (-1, 1):
                    view_pt = np.array([x_sign * half_w, y_sign * half_h, -z, 1.0], dtype=np.float64); world_pt = view_pt @ inv_view; world_pt = world_pt / world_pt[3]; corners.append(world_pt[:3])
        return corners
    def _build_directional_cascade(self, light_dir: Vec3, corners: list[np.ndarray], depth_span: float, shadow_res: int = None) -> np.ndarray:
        n = len(corners); cx = cy = cz = 0.0
        for c in corners:
            cx += c[0]; cy += c[1]; cz += c[2]
        cx /= n; cy /= n; cz /= n; radius2 = 0.0
        for c in corners:
            dx = c[0] - cx; dy = c[1] - cy; dz = c[2] - cz; r2 = dx * dx + dy * dy + dz * dz
            if r2 > radius2:
                radius2 = r2
        radius = max(math.sqrt(radius2), 0.25); radius = math.ceil(radius * 16.0) / 16.0
        light_pos = Vec3(cx, cy, cz) - light_dir * max(radius * 2.0, depth_span + 10.0); light_up = Vec3(0.0, 1.0, 0.0)
        if abs(light_dir.dot(light_up)) > 0.999:
            light_up = Vec3(0.0, 0.0, 1.0)
        view = Mat4.look_at(light_pos, Vec3(cx, cy, cz), light_up); m = [list(map(float, row)) for row in view._d.tolist()]
        center_light = (cx * m[0][0] + cy * m[1][0] + cz * m[2][0] + m[3][0], cx * m[0][1] + cy * m[1][1] + cz * m[2][1] + m[3][1], cx * m[0][2] + cy * m[1][2] + cz * m[2][2] + m[3][2], cx * m[0][3] + cy * m[1][3] + cz * m[2][3] + m[3][3])
        res = shadow_res if shadow_res is not None else self._shadow_resolution; texel_size = (radius * 2.0) / max(1, res)
        cx_l = math.floor(center_light[0] / texel_size) * texel_size; cy_l = math.floor(center_light[1] / texel_size) * texel_size
        left = cx_l - radius; right = cx_l + radius; bottom = cy_l - radius; top = cy_l + radius; min_z = 1e300; max_z = -1e300
        for c in corners:
            px = c[0] * m[0][0] + c[1] * m[1][0] + c[2] * m[2][0] + m[3][0]; py = c[0] * m[0][1] + c[1] * m[1][1] + c[2] * m[2][1] + m[3][1]; pz = c[0] * m[0][2] + c[1] * m[1][2] + c[2] * m[2][2] + m[3][2]; pw = c[0] * m[0][3] + c[1] * m[1][3] + c[2] * m[2][3] + m[3][3]
            pz = pz / pw if pw != 0.0 else 0.0
            if pz < min_z:
                min_z = pz
            if pz > max_z:
                max_z = pz
        z_margin = max(depth_span * 0.45, 6.0); n_val = max(-max_z - z_margin, 0.01); f_val = max(-min_z + z_margin, n_val + 0.01)
        proj = Mat4.orthographic(left, right, bottom, top, n_val, f_val)
        return view._d @ proj._d
    def _render_directional_shadow(self, sun_transform, shadow_groups, cam_near, cam_far, cam_fov, aspect, view_mat):
        try:
            ld_x, ld_y, ld_z = _tr_fwd_xyz(sun_transform)
        except Exception:
            try:
                light_dir = sun_transform.forward.normalized(); ld_x, ld_y, ld_z = light_dir.x, light_dir.y, light_dir.z
            except Exception:
                return
        try:
            vd = view_mat._d
            inv_view = _mat4_inv_fast(np.ascontiguousarray(vd, dtype=np.float64)) if _mat4_inv_fast is not None else np.linalg.inv(vd)
        except Exception:
            inv_view = np.linalg.inv(view_mat._d)
        splits = self._compute_cascade_splits(cam_near, cam_far)
        try:
            prev_splits = list(self._cascade_splits)
        except Exception:
            prev_splits = []
        self._cascade_splits = splits
        try:
            _vres = tuple(int(self._cascade_resolutions[ci]) if ci < len(self._cascade_resolutions) else int(self._shadow_resolution) for ci in range(self._cascade_count))
        except Exception:
            _vres = ()
        try:
            _vpkey = (vd.tobytes(), round(float(ld_x), 4), round(float(ld_y), 4), round(float(ld_z), 4), tuple(float(s) for s in splits), round(float(cam_fov), 3), round(float(aspect), 4), int(self._cascade_count), _vres)
        except Exception:
            _vpkey = None
        try:
            _reuse_vp = _vpkey is not None and _vpkey == self._cascade_vp_key
        except Exception:
            _reuse_vp = False; _vpkey = None
        near_z = max(cam_near, 0.01); prog = self._prog
        try:
            prog["u_light_vp"].write(shift_vp_bytes(self._vp_f32_buf, self._shadow_origin))
        except Exception:
            pass
        self._temporal_frame += 1; _gentle = False
        try:
            lv = self._last_view; cam_moved = True
            if self._last_view_valid and lv.shape == vd.shape:
                try:
                    views_equal = bool(np.allclose(lv, vd, rtol=0.0, atol=1e-7))
                except Exception:
                    views_equal = False
                if views_equal:
                    px, py, pz = self._last_light_dir_xyz
                    if abs(px - ld_x) < 0.002 and abs(py - ld_y) < 0.002 and abs(pz - ld_z) < 0.002:
                        cam_moved = False
            try:
                _cx = float(inv_view[3, 0]); _cy = float(inv_view[3, 1]); _cz = float(inv_view[3, 2])
                _fx = -float(inv_view[2, 0]); _fy = -float(inv_view[2, 1]); _fz = -float(inv_view[2, 2])
                _fl = math.sqrt(_fx * _fx + _fy * _fy + _fz * _fz)
                if _fl > 1e-12:
                    _fx /= _fl; _fy /= _fl; _fz /= _fl
                _lp = self._last_cam_pos; _lf = self._last_cam_fwd
                if _lp is not None and _lf is not None:
                    _dx = _cx - _lp[0]; _dy = _cy - _lp[1]; _dz = _cz - _lp[2]
                    _dd = math.sqrt(_dx * _dx + _dy * _dy + _dz * _dz); _dt = _fx * _lf[0] + _fy * _lf[1] + _fz * _lf[2]
                    if _dd < 0.25 and _dt > 0.9999:
                        _gentle = True
                self._last_cam_pos = (_cx, _cy, _cz); self._last_cam_fwd = (_fx, _fy, _fz)
            except Exception:
                pass
            try:
                np.copyto(self._last_view, vd)
            except Exception:
                try:
                    self._last_view = np.array(vd, dtype=np.float64, copy=True)
                except Exception:
                    pass
            self._last_view_valid = True; self._last_light_dir_xyz = (ld_x, ld_y, ld_z)
        except Exception:
            cam_moved = True
        if cam_moved:
            self._shadow_cache_valid = False
        use_flat = self._flat_n > 0
        try:
            if self._flat_n != self._prev_flat_n:
                scene_moved = True
            elif self._flat_n == 0:
                scene_moved = False
            elif not self._flat_rebuilt_frame and self._shadow_frame_key is not None and self._shadow_frame_key == self._flat_moved_key:
                scene_moved = False
            else:
                n_now = self._flat_n; dc = self._flat_centers[:n_now] - self._prev_flat_centers[:n_now]; dr = self._flat_radii[:n_now] - self._prev_flat_radii[:n_now]
                scene_moved = bool(np.any(np.abs(dc) > 1e-4) or np.any(np.abs(dr) > 1e-5)); self._flat_moved_key = self._shadow_frame_key
        except Exception:
            scene_moved = True
        if scene_moved:
            try:
                self._prev_flat_centers = self._flat_centers[:self._flat_n].copy(); self._prev_flat_radii = self._flat_radii[:self._flat_n].copy(); self._prev_flat_n = self._flat_n
            except Exception:
                pass
        else:
            try:
                self._prev_flat_n = self._flat_n
            except Exception:
                pass
        stagger_allowed = (not cam_moved) and (not scene_moved)
        try:
            light_dir_v = Vec3(ld_x, ld_y, ld_z)
        except Exception:
            light_dir_v = None
        if stagger_allowed and not self._pending_skinned:
            try:
                all_valid = True
                for _ci in range(self._cascade_count):
                    if not self._cascade_valid[_ci]:
                        all_valid = False
                        break
                try:
                    _any_stale = bool(any(self._cascade_stale))
                except Exception:
                    _any_stale = False
                if all_valid and not _any_stale:
                    return
            except Exception:
                pass
        try:
            _tframe0 = int(self._temporal_frame)
        except Exception:
            _tframe0 = 0
        try:
            _skip = set()
            for _ci in range(self._cascade_count):
                if not self._cascade_valid[_ci]:
                    continue
                if stagger_allowed:
                    if _ci == 3 and (_tframe0 % 3) != 0:
                        _skip.add(_ci)
                    elif _ci == 2 and (_tframe0 % 2) != 0:
                        _skip.add(_ci)
                elif _gentle and not scene_moved:
                    if _ci == 1 and (_tframe0 % 2) != 0:
                        _skip.add(_ci)
                        try:
                            self._cascade_stale[_ci] = True
                        except Exception:
                            pass
                    elif _ci == 2 and (_tframe0 % 3) != 0:
                        _skip.add(_ci)
                        try:
                            self._cascade_stale[_ci] = True
                        except Exception:
                            pass
                    elif _ci == 3 and (_tframe0 % 4) != 0:
                        _skip.add(_ci)
                        try:
                            self._cascade_stale[_ci] = True
                        except Exception:
                            pass
            for _ci in _skip:
                try:
                    if _ci < len(prev_splits):
                        splits[_ci] = float(prev_splits[_ci]); self._cascade_splits[_ci] = float(prev_splits[_ci])
                except Exception:
                    pass
        except Exception:
            _skip = set()
        first_cascade = True; supports_instancing = self._supports_instancing_cached(prog); names = self._uniform_names(prog)
        use_inst = "u_use_instancing" in names; umodel = "u_model" in names; prog_id = id(prog)
        try:
            _chg_scene = bool(scene_moved)
        except Exception:
            _chg_scene = False
        try:
            _single_clear = not stagger_allowed and self._shadow_fbos and self._shadow_fbos[0] is not None
        except Exception:
            _single_clear = False
        active_cis = []; active_res = []; active_vps = []; active_min = []
        for ci in range(self._cascade_count):
            res = self._cascade_resolutions[ci] if ci < len(self._cascade_resolutions) else self._shadow_resolution
            try:
                _skipped = ci in _skip
            except Exception:
                _skipped = False
            if _skipped:
                near_z = splits[ci]
                continue
            _ci_reuse = False
            if _reuse_vp:
                try:
                    _rk = self._cascade_raw_key[ci] if ci < len(self._cascade_raw_key) else None
                    _ci_reuse = _rk is not None and _vpkey is not None and _rk == _vpkey
                except Exception:
                    _ci_reuse = False
            if _ci_reuse:
                try:
                    np.copyto(self._vp_f32_buf, self._cascade_vps_raw[ci])
                except Exception:
                    _ci_reuse = False
            if not _ci_reuse and compute_frustum_corners_out is not None and build_directional_cascade_fast is not None:
                try:
                    compute_frustum_corners_out(near_z, splits[ci], cam_fov, aspect, inv_view, self._frustum_corners_buf)
                    build_directional_cascade_fast(ld_x, ld_y, ld_z, self._frustum_corners_buf, splits[ci] - near_z, res, self._cascade_vps_raw[ci])
                    np.copyto(self._vp_f32_buf, self._cascade_vps_raw[ci])
                    try:
                        self._cascade_raw_key[ci] = _vpkey
                    except Exception:
                        pass
                except Exception:
                    corners = self._get_frustum_corners(near_z, splits[ci], cam_fov, aspect, inv_view); vp = self._build_directional_cascade(light_dir_v, corners, splits[ci] - near_z, res); np.copyto(self._vp_f32_buf, vp)
                    try:
                        self._cascade_raw_key[ci] = None
                    except Exception:
                        pass
            elif not _ci_reuse:
                corners = self._get_frustum_corners(near_z, splits[ci], cam_fov, aspect, inv_view); vp = self._build_directional_cascade(light_dir_v, corners, splits[ci] - near_z, res); np.copyto(self._vp_f32_buf, vp)
                try:
                    self._cascade_raw_key[ci] = None
                except Exception:
                    pass
            self._light_space_matrices[ci] = self._vp_f32_buf.copy(); self._cascade_valid[ci] = True
            try:
                self._cascade_stale[ci] = False
            except Exception:
                pass
            try:
                _sx = float(self._vp_f32_buf[0, 0]); _sy = float(self._vp_f32_buf[1, 0]); _sz = float(self._vp_f32_buf[2, 0])
                _col = math.sqrt(_sx * _sx + _sy * _sy + _sz * _sz); _tex = (2.0 / (float(res) * _col)) if _col > 1e-12 else 0.0; active_min.append(_tex * float(self._small_caster_texels))
            except Exception:
                active_min.append(0.0)
            active_vps.append(self._light_space_matrices[ci]); active_cis.append(ci); active_res.append(res); near_z = splits[ci]
        try:
            if len(active_cis) < self._cascade_count:
                _single_clear = False
        except Exception:
            pass
        use_flat = self._flat_n > 0
        flat_counts = self._cull_flat_multi_rows(active_vps, active_min) if (use_flat and active_cis) else []
        try:
            _flat_mats_now = self._flat_mats
        except Exception:
            _flat_mats_now = None
        for _ak, ci in enumerate(active_cis):
            res = active_res[_ak]
            try:
                vp_ci = self._light_space_matrices[ci]
            except Exception:
                vp_ci = self._vp_f32_buf
            if use_flat:
                try:
                    cnt = int(flat_counts[_ak]) if _ak < len(flat_counts) else 0
                except Exception:
                    cnt = 0
                try:
                    if _single_clear and first_cascade:
                        try:
                            self._shadow_fbos[0].use(); self._ctx.viewport = (0, 0, self._cascade_atlas_w, self._cascade_atlas_h); self._shadow_fbos[0].clear(depth=1.0)
                        except Exception:
                            self._clear_atlas_tile(self._shadow_fbos[0], (self._cascade_tile_x[ci], 0, res, res))
                        self._shadow_fbos[0].use()
                    else:
                        self._clear_atlas_tile(self._shadow_fbos[0], (self._cascade_tile_x[ci], 0, res, res)); self._shadow_fbos[0].use()
                    self._ctx.viewport = (self._cascade_tile_x[ci], 0, res, res)
                    if first_cascade:
                        self._shadow_depth_state(); first_cascade = False
                    prog["u_light_vp"].write(shift_vp_bytes(vp_ci, self._shadow_origin))
                    if cnt > 0 and _flat_mats_now is not None:
                        vis = self._flat_out_multi[_ak, :cnt]
                        if supports_instancing:
                            if use_inst:
                                prog["u_use_instancing"].value = 1
                            for mesh, sel, chunk in self._iter_flat_groups_fast(vis, _flat_mats_now):
                                vbo = self._upload_instanced_mats((id(mesh), prog_id, ("d", ci)), chunk, sel, changed=_chg_scene); vao = self._get_shadow_vao(prog, mesh, vbo); vao.render(instances=int(sel.size))
                        else:
                            if use_inst:
                                prog["u_use_instancing"].value = 0
                            if umodel:
                                for mesh, sel, chunk in self._iter_flat_groups_fast(vis, _flat_mats_now):
                                    for j in range(int(sel.size)):
                                        prog["u_model"].write(relativize_chunk_f32(chunk[j], self._shadow_origin).tobytes()); mesh.render(prog)
                            else:
                                for mesh, sel, chunk in self._iter_flat_groups_fast(vis, _flat_mats_now):
                                    for _j in range(int(sel.size)):
                                        mesh.render(prog)
                except Exception:
                    pass
                try:
                    self._maybe_render_skinned(vp_ci, self._shadow_fbos[0], res, (self._cascade_tile_x[ci], 0, res, res))
                except Exception:
                    pass
                continue
            try:
                np.copyto(self._vp_f32_buf, np.ascontiguousarray(vp_ci, dtype=np.float32))
            except Exception:
                pass
            if frustum_cull_shadow_groups is not None and shadow_groups:
                try:
                    culled = frustum_cull_shadow_groups(shadow_groups, self._vp_f32_buf)
                except Exception:
                    culled = shadow_groups
            else:
                culled = shadow_groups
            if culled:
                if _single_clear and first_cascade:
                    try:
                        self._shadow_fbos[0].use(); self._ctx.viewport = (0, 0, self._cascade_atlas_w, self._cascade_atlas_h); self._shadow_fbos[0].clear(depth=1.0)
                    except Exception:
                        self._clear_atlas_tile(self._shadow_fbos[0], (self._cascade_tile_x[ci], 0, res, res))
                    self._shadow_fbos[0].use()
                else:
                    self._clear_atlas_tile(self._shadow_fbos[0], (self._cascade_tile_x[ci], 0, res, res)); self._shadow_fbos[0].use()
                self._ctx.viewport = (self._cascade_tile_x[ci], 0, res, res)
                if first_cascade:
                    self._shadow_depth_state(); first_cascade = False
                prog["u_light_vp"].write(shift_vp_bytes(self._vp_f32_buf, self._shadow_origin))
                for mesh_id, group in culled.items():
                    mesh, _ = group[0]; n = len(group)
                    if supports_instancing:
                        key = (mesh_id, prog_id); model_mats = [tr.world_matrix for _, tr in group]
                        vbo = self._build_shadow_instance_vbo(key, model_mats); vao = self._get_shadow_vao(prog, mesh, vbo)
                        if use_inst:
                            prog["u_use_instancing"].value = 1
                        vao.render(instances=n)
                    else:
                        if use_inst:
                            prog["u_use_instancing"].value = 0
                        for _, tr in group:
                            prog["u_model"].write(relativize_model_f32(tr.world_matrix, self._shadow_origin).tobytes()); mesh.render(prog)
            else:
                try:
                    self._clear_atlas_tile(self._shadow_fbos[0], (self._cascade_tile_x[ci], 0, res, res))
                except Exception:
                    pass
            try:
                self._maybe_render_skinned(self._vp_f32_buf, self._shadow_fbos[0], res, (self._cascade_tile_x[ci], 0, res, res))
            except Exception:
                pass
        if not first_cascade:
            self._ctx.enable(moderngl.CULL_FACE)
        try:
            if _vpkey is not None:
                self._cascade_vp_key = _vpkey
        except Exception:
            pass
