# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np
from core.renderer.origin import origin_for
from core.renderer.batch.instance import _supports_instancing

try:
    from core._culling import cull_group_instances as _cgi
except Exception:
    _cgi = None


def _extract_frustum_planes_f32(view_f32, proj_f32):
    view_4 = view_f32.reshape(4, 4).T
    proj_4 = proj_f32.reshape(4, 4).T
    vp = np.dot(proj_4, view_4)
    planes = np.empty((6, 4), dtype=np.float32)
    planes[0] = vp[3] + vp[0]
    planes[1] = vp[3] - vp[0]
    planes[2] = vp[3] + vp[1]
    planes[3] = vp[3] - vp[1]
    planes[4] = vp[3] + vp[2]
    planes[5] = vp[3] - vp[2]
    norms = np.linalg.norm(planes[:, :3], axis=1, keepdims=True)
    norms[norms < 1e-10] = 1.0
    planes /= norms
    return planes


def _frustum_cull_instances(group, planes, mesh_radius):
    n = len(group)
    if n == 0:
        return group
    if _cgi is not None:
        try:
            return _cgi(group, np.ascontiguousarray(planes, dtype=np.float32),
                        float(mesh_radius))
        except Exception:
            pass
    try:
        mats = [item[6]._d for item in group]
    except Exception:
        return group
    try:
        arr = np.stack(mats).astype(np.float64, copy=False)
    except Exception:
        return group
    try:
        centers = np.ascontiguousarray(arr[:, 3, :3], dtype=np.float64)
        sx = arr[:, 0, 0] * arr[:, 0, 0] + arr[:, 1, 0] * arr[:, 1, 0] + arr[:, 2, 0] * arr[:, 2, 0]
        sy = arr[:, 0, 1] * arr[:, 0, 1] + arr[:, 1, 1] * arr[:, 1, 1] + arr[:, 2, 1] * arr[:, 2, 1]
        sz = arr[:, 0, 2] * arr[:, 0, 2] + arr[:, 1, 2] * arr[:, 1, 2] + arr[:, 2, 2] * arr[:, 2, 2]
        np.sqrt(sx, out=sx)
        np.sqrt(sy, out=sy)
        np.sqrt(sz, out=sz)
        ms = sx
        np.maximum(ms, sy, out=ms)
        np.maximum(ms, sz, out=ms)
        radii = ms * float(mesh_radius)
        pl = np.ascontiguousarray(planes, dtype=np.float64)
        distances = pl[:, :3] @ centers.T + pl[:, 3, None]
        visible_mask = np.all(distances > -radii[None, :], axis=0)
        if bool(np.all(visible_mask)):
            return group
        indices = np.where(visible_mask)[0]
        return [group[int(i)] for i in indices]
    except Exception:
        return group


class GroupsMixin:

    _MAT_NONE = object()

    def _validate_topology(self, renderables, ck_keys, get_mat, get_prog, default_prog, none_id, mpath_cache):
        for _i, entry in enumerate(renderables):
            mr = entry[3]
            mesh = entry[2]
            sub_idx = entry[5]
            try:
                mats = mr.materials
            except Exception:
                mats = None
            if mats:
                try:
                    if sub_idx < len(mats):
                        mpath = mats[sub_idx].get("path", "")
                    else:
                        mpath = mats[-1].get("path", "")
                except Exception:
                    mpath = ""
            else:
                mpath = ""
            cached = mpath_cache.get(mpath)
            if cached is None:
                try:
                    mat = get_mat(mpath)
                except Exception:
                    mat = None
                try:
                    if mat is not None:
                        shader_path = mat.shader_path
                    else:
                        shader_path = ""
                except Exception:
                    shader_path = ""
                try:
                    if shader_path:
                        prog = get_prog(shader_path)
                    else:
                        prog = None
                except Exception:
                    prog = None
                if prog is None:
                    prog = default_prog
                cached = (mat, prog)
                mpath_cache[mpath] = cached
            else:
                mat, prog = cached
            if mat is not None:
                mat_key = id(mat)
            else:
                mat_key = none_id
            try:
                _uv = mr.uv_scale
                _usx = _uv._x
                _usy = _uv._y
                _uo = mr.uv_offset
                _uox = _uo._x
                _uoy = _uo._y
                _uw = mr.uv_scale_by_transform
                _sp = mr.sprite_texture
                if not _sp:
                    _sp = ""
                _rs = mr.receive_shadows
                _dr = mr.dynamic_reflections
            except Exception:
                return False
            if _usx == 1.0 and _usy == 1.0 and _uox == 0.0 and _uoy == 0.0 and not _uw and _sp == "":
                uv_key = 0
            else:
                uv_key = (_usx, _usy, _uox, _uoy, _uw, _sp)
            _t = ck_keys[_i]
            if _t[0] != id(prog) or _t[1] != mat_key or _t[2] != id(mesh) or _t[3] != _rs or _t[4] != sub_idx or _t[5] != _dr or _t[6] != uv_key:
                return False
        return True

    def collect_groups(self, renderables, materials, shaders):
        groups: dict = {}
        get_mat = materials.load_material
        get_prog = shaders.get_or_compile
        default_prog = self._default_prog
        none_id = id(self._MAT_NONE)
        mpath_cache: dict = {}
        get_cached = mpath_cache.get
        try:
            _tc = self._groups_topology
        except Exception:
            _tc = None
        _n = len(renderables)
        if _tc is not None and _tc[0] == _n:
            try:
                _hit = self._validate_topology(renderables, _tc[1], get_mat, get_prog, default_prog, none_id, mpath_cache)
            except Exception:
                _hit = False
            if _hit:
                return _tc[2]
        keys: list = []
        for entry in renderables:
            mr = entry[3]
            mesh = entry[2]
            wm = entry[4]
            sub_idx = entry[5]
            try:
                mats = mr.materials
            except Exception:
                mats = None
            if mats:
                try:
                    if sub_idx < len(mats):
                        mpath = mats[sub_idx].get("path", "")
                    else:
                        mpath = mats[-1].get("path", "")
                except Exception:
                    mpath = ""
            else:
                mpath = ""
            cached = get_cached(mpath)
            if cached is None:
                try:
                    mat = get_mat(mpath)
                except Exception:
                    mat = None
                try:
                    if mat is not None:
                        shader_path = mat.shader_path
                    else:
                        shader_path = ""
                except Exception:
                    shader_path = ""
                try:
                    if shader_path:
                        prog = get_prog(shader_path)
                    else:
                        prog = None
                except Exception:
                    prog = None
                if prog is None:
                    prog = default_prog
                cached = (mat, prog)
                mpath_cache[mpath] = cached
            else:
                mat, prog = cached
            if mat is not None:
                mat_key = id(mat)
            else:
                mat_key = none_id
            try:
                _uv = mr.uv_scale
                _usx = _uv._x
                _usy = _uv._y
                _uo = mr.uv_offset
                _uox = _uo._x
                _uoy = _uo._y
                _uw = mr.uv_scale_by_transform
                _sp = mr.sprite_texture
                if not _sp:
                    _sp = ""
                _rs = mr.receive_shadows
                _dr = mr.dynamic_reflections
            except Exception:
                _usx = 1.0
                _usy = 1.0
                _uox = 0.0
                _uoy = 0.0
                _uw = getattr(mr, "uv_scale_by_transform", False)
                _sp = getattr(mr, "sprite_texture", "") or ""
                _rs = bool(getattr(mr, "receive_shadows", False))
                _dr = bool(getattr(mr, "dynamic_reflections", False))
                try:
                    _uv2 = getattr(mr, "uv_scale", None)
                    if _uv2 is not None:
                        _usx = float(_uv2.x)
                        _usy = float(_uv2.y)
                except Exception:
                    pass
                try:
                    _uo2 = getattr(mr, "uv_offset", None)
                    if _uo2 is not None:
                        _uox = float(_uo2.x)
                        _uoy = float(_uo2.y)
                except Exception:
                    pass
            if _usx == 1.0 and _usy == 1.0 and _uox == 0.0 and _uoy == 0.0 and not _uw and _sp == "":
                uv_key = 0
            else:
                uv_key = (_usx, _usy, _uox, _uoy, _uw, _sp)
            key = (id(prog), mat_key, id(mesh), _rs, sub_idx, _dr, uv_key)
            keys.append(key)
            lst = groups.get(key)
            if lst is None:
                groups[key] = [(entry[0], entry[1], mesh, mr, mat, prog, wm, sub_idx)]
            else:
                lst.append((entry[0], entry[1], mesh, mr, mat, prog, wm, sub_idx))
        try:
            self._groups_topology = (_n, keys, groups)
        except Exception:
            pass
        return groups

    def _get_frustum_planes(self, view_f32, proj_f32):
        key = (view_f32.tobytes(), proj_f32.tobytes())
        if self._frustum_cache_key == key and self._frustum_planes_cache is not None:
            return self._frustum_planes_cache
        planes = _extract_frustum_planes_f32(view_f32, proj_f32)
        self._frustum_planes_cache = planes
        self._frustum_cache_key = key
        return planes

    def render_groups(self, groups: dict, view_f32, proj_f32, cam_pos, lights,
                      disable_shadows: bool, set_scene_uniforms_fn,
                      apply_material_fn, normal_cache: dict,
                      selected_entities: set, outline_queue: list,
                      gpu_storage=None, dynamic_cubemaps=None, sky_ibl=None, skip_cull=False, skip_inst_upload=False,
                      sort_groups=True, group_skip=None, group_patches=None, transparent_pass=False,
                      transmission_hook=None):
        self.reset_stats()
        try:
            if selected_entities is not None and len(selected_entities) > 256:
                selected_entities = frozenset()
        except Exception:
            pass
        scene_done = set()
        frustum_planes = None
        if not skip_cull:
            frustum_planes = self._get_frustum_planes(view_f32, proj_f32)
        skip_up = skip_inst_upload and len(groups) == 1 and origin_for(cam_pos) is None
        if sort_groups and len(groups) > 1:
            try:
                items = sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1]))
            except Exception:
                items = list(groups.items())
        else:
            items = list(groups.items())
        last_apply_key = None
        last_ibl_key = None
        real_apply = apply_material_fn

        def cached_apply(mat, prog, mr=None):
            nonlocal last_apply_key
            try:
                pid = id(prog)
                mid = id(mat) if mat is not None else 0
                if mr is None:
                    akey = (pid, mid, 0)
                else:
                    try:
                        _u = mr.uv_scale
                        _o = mr.uv_offset
                        akey = (pid, mid, _u.x, _u.y, _o.x, _o.y, mr.uv_scale_by_transform, mr.sprite_texture)
                    except Exception:
                        akey = (pid, mid, 0)
            except Exception:
                return real_apply(mat, prog, mr)
            if akey == last_apply_key:
                return
            last_apply_key = akey
            return real_apply(mat, prog, mr)

        apply_material_fn = cached_apply
        for key, group in items:
            _, _, mesh, _, mat, prog, _, _ = group[0]
            try:
                if transparent_pass and transmission_hook is not None and mat is not None:
                    try:
                        _tv = mat.properties.get("_Transmission", mat.properties.get("transmission", 0.0))
                    except Exception:
                        _tv = 0.0
                    try:
                        _tvf = float(_tv)
                    except Exception:
                        _tvf = 0.0
                    if _tvf > 0.001:
                        transmission_hook(mat)
            except Exception:
                pass
            dyn_ref = key[5] if len(key) > 5 else False
            self._stats_batches += 1
            n = len(group)
            group_disable_shadows = disable_shadows or not key[3]
            scene_key = (id(prog), group_disable_shadows)
            if scene_key not in scene_done:
                set_scene_uniforms_fn(prog, view_f32, proj_f32, cam_pos, lights,
                                      disable_shadows=group_disable_shadows)
                scene_done.add(scene_key)
            if dyn_ref and dynamic_cubemaps is not None:
                ikey = (id(prog), id(dynamic_cubemaps))
                if ikey != last_ibl_key:
                    dynamic_cubemaps.bind_ibl(prog)
                    last_ibl_key = ikey
            elif sky_ibl is not None and sky_ibl.ready:
                ikey = (id(prog), id(sky_ibl))
                if ikey != last_ibl_key:
                    sky_ibl.bind(prog)
                    last_ibl_key = ikey
            elif not dyn_ref:
                names = self._uniform_names(prog)
                try:
                    if "u_irradiance_map_Active" in names:
                        prog["u_irradiance_map_Active"].value = 0
                    if "u_prefilter_map_Active" in names:
                        prog["u_prefilter_map_Active"].value = 0
                    if "u_brdf_lut_Active" in names:
                        prog["u_brdf_lut_Active"].value = 0
                    if "u_irradiance_map" in names:
                        prog["u_irradiance_map"].value = 14
                    if "u_prefilter_map" in names:
                        prog["u_prefilter_map"].value = 15
                    if "u_brdf_lut" in names:
                        prog["u_brdf_lut"].value = 16
                except Exception:
                    pass
            if n == 1:
                self._render_single(group[0], prog, mesh, mat,
                                    view_f32, proj_f32, cam_pos, lights,
                                    group_disable_shadows, set_scene_uniforms_fn,
                                    apply_material_fn, normal_cache,
                                    selected_entities, outline_queue,
                                    set_scene=False, transparent_pass=transparent_pass)
            elif _supports_instancing(prog):
                gpu_eligible = (gpu_storage is not None
                                and gpu_storage.is_gpu_driven()
                                and len(group) >= self._gpu_driven_min_instances)
                if not gpu_eligible:
                    if skip_cull:
                        visible = group
                    else:
                        visible = _frustum_cull_instances(group, frustum_planes,
                                                          mesh.bounding_radius)
                    if len(visible) == 0:
                        self._stats_draw_calls += 1
                        continue
                    if len(visible) == 1:
                        self._render_single(visible[0], prog, mesh, mat,
                                            view_f32, proj_f32, cam_pos, lights,
                                            group_disable_shadows, set_scene_uniforms_fn,
                                            apply_material_fn, normal_cache,
                                            selected_entities, outline_queue,
                                            set_scene=False, transparent_pass=transparent_pass)
                        continue
                    if visible is group:
                        try:
                            _gp = group_patches.get(key) if group_patches else None
                        except Exception:
                            _gp = None
                        try:
                            _gs = key in group_skip if group_skip else False
                        except Exception:
                            _gs = False
                    else:
                        group = visible
                        _gp = None
                        _gs = False
                else:
                    _gp = None
                    _gs = False
                self._render_instanced(group, prog, mesh, mat,
                                       view_f32, proj_f32, cam_pos, lights,
                                       group_disable_shadows, set_scene_uniforms_fn,
                                       apply_material_fn,
                                       selected_entities, outline_queue,
                                       gpu_storage=gpu_storage, set_scene=False, skip_upload=skip_up,
                                       group_key=key, group_patches=_gp, group_skip=_gs,
                                       transparent_pass=transparent_pass)
            else:
                for item in group:
                    self._render_single(item, prog, mesh, mat,
                                        view_f32, proj_f32, cam_pos, lights,
                                        group_disable_shadows, set_scene_uniforms_fn,
                                        apply_material_fn, normal_cache,
                                        selected_entities, outline_queue,
                                        set_scene=False, transparent_pass=transparent_pass)
