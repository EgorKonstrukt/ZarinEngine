# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np; import moderngl
from core.maths.math3d import Mat4; from core.components.lighting.light import LightType
from core.renderer.origin import origin_from_view, relativize_chunk_f32, relativize_model_f32, shift_vp_bytes
from .bind import _HAS_CYTHON, _mat4_inv_fast; from .mathx import _tr_pos_xyz, _tr_fwd_xyz, MAX_POINT_SHADOWS, MAX_SPOT_SHADOWS
class PassesMixin:
    def _shadow_depth_state(self):
        try:
            self._ctx.enable(moderngl.DEPTH_TEST)
        except Exception:
            pass
        try:
            self._ctx.depth_mask = True
        except Exception:
            pass
        try:
            self._ctx.enable(moderngl.CULL_FACE); self._ctx.cull_face = 'back'
        except Exception:
            pass
    def _draw_flat_visible(self, vp: np.ndarray, fbo, resolution: int, visible_count: int, tag=("g", 0), viewport=None, clear=True):
        if visible_count <= 0:
            return
        vis = self._flat_out[:visible_count]; prog = self._prog
        supports_instancing = self._supports_instancing_cached(prog); names = self._uniform_names(prog)
        use_inst = "u_use_instancing" in names
        if clear:
            try:
                fbo.clear(depth=1.0)
            except Exception:
                pass
        fbo.use(); self._ctx.viewport = viewport if viewport is not None else (0, 0, resolution, resolution); self._shadow_depth_state()
        try:
            _so = self._shadow_origin
        except Exception:
            _so = None
        prog["u_light_vp"].write(shift_vp_bytes(vp, _so)); mats = self._flat_mats; prog_id = id(prog)
        if supports_instancing:
            if use_inst:
                prog["u_use_instancing"].value = 1
            for mesh, sel, chunk in self._iter_flat_groups_fast(vis, mats):
                key = (id(mesh), prog_id, tag); vbo = self._upload_instanced_mats(key, chunk, sel); vao = self._get_shadow_vao(prog, mesh, vbo); vao.render(instances=int(sel.size))
        else:
            if use_inst:
                prog["u_use_instancing"].value = 0
            umodel = "u_model" in names
            for mesh, sel, chunk in self._iter_flat_groups_fast(vis, mats):
                if umodel:
                    for j in range(int(sel.size)):
                        prog["u_model"].write(relativize_chunk_f32(chunk[j], _so).tobytes()); mesh.render(prog)
                else:
                    for _j in range(int(sel.size)):
                        mesh.render(prog)
        self._ctx.enable(moderngl.CULL_FACE)
    def render_geometry(self, vp: np.ndarray, fbo, renderable_shadow: list, resolution: int = 1024):
        self._shadow_frame_key = None; self._shadow_origin = None
        if _HAS_CYTHON and isinstance(renderable_shadow, list) and len(renderable_shadow) > 32:
            try:
                self._prepare_flat(renderable_shadow); vp32 = np.asarray(vp, dtype=np.float32); cnt = self._cull_flat_count(vp32)
                if cnt: self._draw_flat_visible(vp32, fbo, resolution, cnt)
                else:
                    try: fbo.clear(depth=1.0)
                    except Exception: pass
                return
            except Exception:
                pass
        groups = self._build_shadow_groups(renderable_shadow)
        if not groups:
            try: fbo.clear(depth=1.0)
            except Exception: pass
            return
        self._render_geometry_with_groups(vp, fbo, groups, resolution)
    def _render_geometry_with_groups(self, vp: np.ndarray, fbo, groups: dict, resolution: int = 1024):
        if not groups: return
        fbo.clear(depth=1.0); fbo.use(); self._ctx.viewport = (0, 0, resolution, resolution); self._shadow_depth_state()
        prog = self._prog; prog["u_light_vp"].write(vp.tobytes())
        supports_instancing = self._supports_instancing_cached(prog); names = self._uniform_names(prog)
        use_inst = "u_use_instancing" in names; umodel = "u_model" in names; prog_id = id(prog)
        if supports_instancing:
            if use_inst: prog["u_use_instancing"].value = 1
            for mesh_id, group in groups.items():
                mesh, _ = group[0]; n = len(group)
                if n == 1:
                    tr = group[0][1]
                    try:
                        if tr._dirty: tr._update_world_matrix()
                        wm = tr._world_matrix
                    except Exception:
                        continue
                    key = (mesh_id, prog_id); vbo = self._build_shadow_instance_vbo(key, [wm]); vao = self._get_shadow_vao(prog, mesh, vbo); vao.render(instances=1)
                    continue
                key = (mesh_id, prog_id)
                try:
                    model_mats = []
                    for _, tr in group:
                        if tr._dirty: tr._update_world_matrix()
                        model_mats.append(tr._world_matrix)
                except Exception:
                    continue
                vbo = self._build_shadow_instance_vbo(key, model_mats); vao = self._get_shadow_vao(prog, mesh, vbo); vao.render(instances=n)
        else:
            if use_inst: prog["u_use_instancing"].value = 0
            for _mesh_id, group in groups.items():
                mesh, _ = group[0]
                if umodel:
                    for _, tr in group:
                        try:
                            if tr._dirty: tr._update_world_matrix()
                            prog["u_model"].write(tr._world_matrix.to_f32().tobytes())
                        except Exception:
                            continue
                        mesh.render(prog)
                else:
                    for _, tr in group:
                        mesh.render(prog)
        self._ctx.enable(moderngl.CULL_FACE)
    def collect_shadow_data(self, scene, meshes: dict) -> list[tuple]:
        self._get_mesh = lambda k: meshes.get(k); result = self._build_renderable_shadow(scene); self._get_mesh = None
        return result
    def _bind_bone_ssbo(self, flat: np.ndarray):
        n = flat.shape[0]; needed = max(64, n) * 64
        if self._skinned_bone_ssbo is not None and self._skinned_bone_ssbo_cap >= needed:
            data = flat.tobytes()
            if self._skinned_bone_ssbo.size < len(data):
                try:
                    self._skinned_bone_ssbo.release()
                except Exception:
                    pass
                self._skinned_bone_ssbo = self._ctx.buffer(reserve=len(data) + 64); self._skinned_bone_ssbo_cap = len(data) + 64
            self._skinned_bone_ssbo.write(data)
        else:
            if self._skinned_bone_ssbo is not None:
                try:
                    self._skinned_bone_ssbo.release()
                except Exception:
                    pass
            self._skinned_bone_ssbo = self._ctx.buffer(reserve=needed); self._skinned_bone_ssbo_cap = needed; self._skinned_bone_ssbo.write(flat.tobytes())
        self._skinned_bone_ssbo.bind_to_storage_buffer(6)
    def _maybe_render_skinned(self, vp: np.ndarray, fbo, resolution: int, viewport=None):
        if not self._pending_skinned: return
        if self._pending_scene is None: return
        prog = self._prog; fbo.use(); fbo.viewport = viewport if viewport is not None else (0, 0, resolution, resolution); self._shadow_depth_state()
        try:
            _so = self._shadow_origin
        except Exception:
            _so = None
        prog["u_light_vp"].write(shift_vp_bytes(vp, _so)); names = self._uniform_names(prog)
        if "u_use_instancing" in names: prog["u_use_instancing"].value = 0
        if "u_use_skinning" in names: prog["u_use_skinning"].value = 1
        skinning_cache = self._skinning_cache
        for entry in self._pending_skinned:
            mesh, ent, armature, wm = entry[0], entry[1], entry[2], entry[3]
            if armature is None or len(armature.bone_offset_matrices) == 0: continue
            cache_key = ent._id; cached = skinning_cache.get(cache_key) if skinning_cache is not None else None
            if cached is not None: flat, n_bones = cached
            else:
                flat, n_bones = armature.compute_skinning_buffer(self._pending_scene, wm)
                if n_bones > 0 and skinning_cache is not None: skinning_cache[cache_key] = (flat, n_bones)
            if n_bones == 0: continue
            self._bind_bone_ssbo(flat)
            if "u_bone_count" in names: prog["u_bone_count"].value = int(n_bones)
            if "u_model" in names: prog["u_model"].write(relativize_model_f32(wm, _so).tobytes())
            mesh.render(prog)
        if "u_use_skinning" in names: prog["u_use_skinning"].value = 0
        self._ctx.enable(moderngl.CULL_FACE)
    def reset_shadow_state(self):
        self._cascade_splits = [0.0] * 4; self._cascade_valid = [False, False, False, False]
        self._cascade_stale = [False, False, False, False]; self._cascade_raw_key = [None, None, None, None]
        self._has_point_shadow = False; self._point_shadow_count = 0; self._has_spot_shadow = False; self._spot_shadow_count = 0
        self._has_area_shadow = False; self._has_area_shadow_back = False; self._area_shadow_two_sided = 0.0
        try:
            self._stained_valid = False
        except Exception:
            pass
        try:
            self._last_static_frame_key = None; self._point_static_key = None; self._spot_static_key = None; self._area_static_key = None
        except Exception:
            pass
    def render_shadow_pass(self, renderable_shadow, lights, cam_near: float, cam_far: float, cam_fov: float, aspect: float, view_mat: Mat4, meshes: object = None, skinned_entries: list = None, scene: object = None, skinning_cache: dict = None, tint_casters: list = None, material_manager: object = None) -> dict:
        if not self._prog:
            return {}
        self._pending_skinned = skinned_entries or []; self._pending_scene = scene; self._skinning_cache = skinning_cache
        try:
            _stv = scene._transform_version if scene is not None else -1
        except Exception:
            _stv = -1
        try:
            _srv = scene._render_version if scene is not None else None
        except Exception:
            _srv = None
        try:
            self._shadow_frame_key = (_stv, _srv)
        except Exception:
            self._shadow_frame_key = None
        self._flat_rebuilt_frame = False
        try:
            self._shadow_origin = origin_from_view(view_mat)
        except Exception:
            self._shadow_origin = None
        if not renderable_shadow:
            self._flat_n = 0; self._flat_mesh_map = {}; self._flat_sig = None; self._flat_src_list = None
            self.reset_shadow_state(); self._cache_uniform_bytes()
            try:
                _sun_only = None
                try:
                    for _l, _lt in lights:
                        if _l.light_type == LightType.DIRECTIONAL and _l.cast_shadows:
                            _sun_only = _lt
                            break
                except Exception:
                    _sun_only = None
                self._render_stained_pass(_sun_only, tint_casters, material_manager, cam_near, cam_far, cam_fov, aspect, view_mat)
            except Exception:
                pass
            return {}
        if self._flat_cache_valid(scene, renderable_shadow):
            shadow_groups = self._shadow_groups_cache
        elif self._try_shadow_partial(scene, renderable_shadow):
            shadow_groups = self._shadow_groups_cache
            if shadow_groups is None:
                self._flat_rebuilt_frame = True
                try:
                    self._prepare_flat(renderable_shadow)
                except Exception:
                    self._flat_n = 0; self._flat_mesh_map = {}
                shadow_groups = self._build_shadow_groups(renderable_shadow)
                try:
                    self._rebuild_shadow_index(renderable_shadow, len(renderable_shadow))
                except Exception:
                    pass
                try:
                    rv = scene._render_version if scene is not None else None; tv = scene._transform_version if scene is not None else None
                    self._flat_sig = (id(scene), rv, tv, len(renderable_shadow)); self._flat_src_list = renderable_shadow
                except Exception:
                    self._flat_sig = None; self._flat_src_list = None
        else:
            self._flat_rebuilt_frame = True
            try:
                self._prepare_flat(renderable_shadow)
            except Exception:
                self._flat_n = 0; self._flat_mesh_map = {}
            shadow_groups = self._build_shadow_groups(renderable_shadow)
            try:
                self._rebuild_shadow_index(renderable_shadow, len(renderable_shadow))
            except Exception:
                pass
            try:
                rv = scene._render_version if scene is not None else None; tv = scene._transform_version if scene is not None else None
                self._flat_sig = (id(scene), rv, tv, len(renderable_shadow)); self._flat_src_list = renderable_shadow
            except Exception:
                self._flat_sig = None; self._flat_src_list = None
        try:
            _static_frame = (not self._flat_rebuilt_frame) and (not self._pending_skinned) and (self._shadow_frame_key is not None) and (self._shadow_frame_key == self._last_static_frame_key)
        except Exception:
            _static_frame = False
        flags = self._type_flags
        if flags.get('directional', True):
            for l, lt in lights:
                if l.light_type == LightType.DIRECTIONAL and l.cast_shadows:
                    self._render_directional_shadow(lt, shadow_groups, cam_near, cam_far, cam_fov, aspect, view_mat)
                    break
            else:
                self._cascade_splits = [0.0] * 4
        else:
            self._cascade_splits = [0.0] * 4
        try:
            vd = view_mat._d
            inv_d = _mat4_inv_fast(np.ascontiguousarray(vd, dtype=np.float64)) if _mat4_inv_fast is not None else np.linalg.inv(vd)
            cam_x = float(inv_d[3, 0]); cam_y = float(inv_d[3, 1]); cam_z = float(inv_d[3, 2])
        except Exception:
            cam_x = 0.0; cam_y = 0.0; cam_z = 0.0
        if not self._point_shadow_maps:
            self._create_point_shadow_resources()
        _point_skip = False
        if flags.get('point', True):
            pc = []
            for l, lt in lights:
                if l.light_type == LightType.POINT and l.cast_shadows:
                    try:
                        px, py, pz = _tr_pos_xyz(lt)
                    except Exception:
                        continue
                    dx = px - cam_x; dy = py - cam_y; dz = pz - cam_z; pc.append((l, lt, dx * dx + dy * dy + dz * dz))
            pc.sort(key=lambda x: x[2]); self._point_shadow_count = min(len(pc), MAX_POINT_SHADOWS)
            try:
                _pe = []
                for _slot in range(self._point_shadow_count):
                    _l, _lt, _ = pc[_slot]
                    try: _qx, _qy, _qz = _tr_pos_xyz(_lt)
                    except Exception:
                        try: _pp = _lt.position; _qx, _qy, _qz = float(_pp.x), float(_pp.y), float(_pp.z)
                        except Exception: _qx, _qy, _qz = 0.0, 0.0, 0.0
                    try: _qr = max(float(getattr(_l, 'range', 10.0)), 0.1)
                    except Exception: _qr = 10.0
                    _pe.append((id(_l), id(_lt), _qx, _qy, _qz, _qr))
                _pkey = (self._shadow_frame_key, self._point_shadow_resolution, tuple(_pe))
            except Exception:
                _pkey = None
            try:
                _point_skip = bool(_static_frame) and (_pkey is not None) and (_pkey == self._point_static_key)
            except Exception:
                _point_skip = False
            if _point_skip:
                for slot in range(self._point_shadow_count):
                    l, lt, _ = pc[slot]
                    try:
                        self._point_shadow_light_indices[slot] = next((i for i, (_ll, _tt) in enumerate(lights) if _ll is l and _tt is lt), -1)
                    except Exception:
                        pass
                for slot in range(self._point_shadow_count, MAX_POINT_SHADOWS):
                    self._point_shadow_light_indices[slot] = -1
                self._has_point_shadow = self._point_shadow_count > 0
            else:
                try:
                    if self._point_shadow_fbos:
                        self._point_shadow_fbos[0].use(); self._point_shadow_fbos[0].clear(depth=1.0)
                except Exception:
                    pass
                for slot in range(self._point_shadow_count):
                    l, lt, _ = pc[slot]
                    self._render_point_shadow_for_slot(slot, l, lt, shadow_groups, lights)
                for slot in range(self._point_shadow_count, MAX_POINT_SHADOWS):
                    self._point_shadow_light_indices[slot] = -1
                self._has_point_shadow = self._point_shadow_count > 0
                try:
                    self._point_static_key = _pkey
                except Exception:
                    pass
        else:
            self._point_shadow_count = 0; self._has_point_shadow = False
            for slot in range(MAX_POINT_SHADOWS):
                self._point_shadow_light_indices[slot] = -1
            try:
                self._point_static_key = None
            except Exception:
                pass
        if not self._spot_shadow_maps:
            self._create_spot_shadow_resources()
        _spot_skip = False
        if flags.get('spot', True):
            sc = []
            for l, lt in lights:
                if l.light_type == LightType.SPOT and l.cast_shadows:
                    try:
                        px, py, pz = _tr_pos_xyz(lt)
                    except Exception:
                        continue
                    dx = px - cam_x; dy = py - cam_y; dz = pz - cam_z; sc.append((l, lt, dx * dx + dy * dy + dz * dz))
            sc.sort(key=lambda x: x[2]); self._spot_shadow_count = min(len(sc), MAX_SPOT_SHADOWS)
            try:
                _se = []
                for _slot in range(self._spot_shadow_count):
                    _l, _lt, _ = sc[_slot]
                    try: _qx, _qy, _qz = _tr_pos_xyz(_lt)
                    except Exception:
                        try: _pp = _lt.position; _qx, _qy, _qz = float(_pp.x), float(_pp.y), float(_pp.z)
                        except Exception: _qx, _qy, _qz = 0.0, 0.0, 0.0
                    try: _dx, _dy, _dz = _tr_fwd_xyz(_lt)
                    except Exception:
                        try: _fd = _lt.forward.normalized(); _dx, _dy, _dz = float(_fd.x), float(_fd.y), float(_fd.z)
                        except Exception: _dx, _dy, _dz = 0.0, 0.0, -1.0
                    try: _qr = max(float(getattr(_l, 'range', 10.0)), 0.1)
                    except Exception: _qr = 10.0
                    try: _qf = max(float(getattr(_l, 'spot_angle', 30.0)) * 2.0, 1.0)
                    except Exception: _qf = 60.0
                    _se.append((id(_l), id(_lt), _qx, _qy, _qz, _dx, _dy, _dz, _qr, _qf))
                _skey = (self._shadow_frame_key, self._spot_shadow_resolution, tuple(_se))
            except Exception:
                _skey = None
            try:
                _spot_skip = bool(_static_frame) and (_skey is not None) and (_skey == self._spot_static_key)
            except Exception:
                _spot_skip = False
            if _spot_skip:
                for slot in range(self._spot_shadow_count):
                    l, lt, _ = sc[slot]
                    try:
                        self._spot_shadow_light_indices[slot] = next((i for i, (_ll, _tt) in enumerate(lights) if _ll is l and _tt is lt), -1)
                    except Exception:
                        pass
                for slot in range(self._spot_shadow_count, MAX_SPOT_SHADOWS):
                    self._spot_shadow_light_indices[slot] = -1
                self._has_spot_shadow = self._spot_shadow_count > 0
            else:
                try:
                    if self._spot_shadow_fbos:
                        self._spot_shadow_fbos[0].use(); self._spot_shadow_fbos[0].clear(depth=1.0)
                except Exception:
                    pass
                for slot in range(self._spot_shadow_count):
                    l, lt, _ = sc[slot]
                    self._render_spot_shadow_for_slot(slot, l, lt, shadow_groups, lights)
                for slot in range(self._spot_shadow_count, MAX_SPOT_SHADOWS):
                    self._spot_shadow_light_indices[slot] = -1
                self._has_spot_shadow = self._spot_shadow_count > 0
                try:
                    self._spot_static_key = _skey
                except Exception:
                    pass
        else:
            self._spot_shadow_count = 0; self._has_spot_shadow = False
            for slot in range(MAX_SPOT_SHADOWS):
                self._spot_shadow_light_indices[slot] = -1
            try:
                self._spot_static_key = None
            except Exception:
                pass
        if flags.get('area', True):
            best_area = None; best_area_dist = float('inf')
            for l, lt in lights:
                if l.light_type == LightType.AREA and l.cast_shadows:
                    try:
                        px, py, pz = _tr_pos_xyz(lt)
                    except Exception:
                        continue
                    dx = px - cam_x; dy = py - cam_y; dz = pz - cam_z; d = dx * dx + dy * dy + dz * dz
                    if d < best_area_dist:
                        best_area_dist = d; best_area = (l, lt)
            if best_area: self._render_area_shadow(best_area[0], best_area[1], shadow_groups, lights)
            else: self._has_area_shadow = False
        else:
            self._has_area_shadow = False
        try:
            _sun_lt = None
            if flags.get('directional', True):
                for _l, _lt in lights:
                    if _l.light_type == LightType.DIRECTIONAL and _l.cast_shadows:
                        _sun_lt = _lt
                        break
            self._render_stained_pass(_sun_lt, tint_casters, material_manager, cam_near, cam_far, cam_fov, aspect, view_mat)
        except Exception:
            pass
        try: self._cache_uniform_bytes()
        except Exception: pass
        try: self._last_static_frame_key = self._shadow_frame_key
        except Exception: pass
        return shadow_groups
