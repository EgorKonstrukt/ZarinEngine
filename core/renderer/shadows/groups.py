# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
import os
from collections import defaultdict
from typing import Optional, Any
import numpy as np
from core.maths.math3d import Mat4
from core.components.rendering.renderers.mesh_filter import MeshFilter
from core.components.rendering.renderers.mesh_renderer import MeshRenderer
from core.renderer.meshd import MeshData
from .bind import cy_build_shadow_groups
class GroupsMixin:
    def _build_renderable_shadow(self, scene) -> list[tuple[MeshData, Mat4]]:
        result = []
        get_entities = scene.get_entities_with_component
        for ent in get_entities(MeshFilter):
            if not ent._active:
                continue
            tm = ent._type_map
            mf_list = tm.get(MeshFilter)
            if not mf_list:
                continue
            mf = mf_list[0]
            mr_list = tm.get(MeshRenderer)
            if not mr_list:
                continue
            mr = mr_list[0]
            if not mr.enabled or not mr.cast_shadows:
                continue
            tt = ent._transform_type
            tr = tm.get(tt, [None])[0] if tt is not None and tt in tm else ent.transform
            if tr is None:
                continue
            mp = mf.mesh_path or mf.mesh_name or ""
            if not mp:
                continue
            _imp = mp + ".import"
            cached = self._import_cache.get(_imp)
            if cached is not None:
                mtime = self._import_cache_mtime.get(_imp, 0)
                try:
                    cur = os.path.getmtime(_imp)
                    if abs(cur - mtime) < 0.001:
                        _sk, _scp, _sfu = cached
                    else:
                        raise KeyError
                except Exception:
                    try:
                        with open(_imp) as _f:
                            _s = json.load(_f)
                        _sk, _scp, _sfu = _s.get("scale", 1.0), _s.get("center_pivot", False), _s.get("flip_uvs", False)
                    except Exception:
                        _sk, _scp, _sfu = 1.0, False, False
                    self._import_cache[_imp] = (_sk, _scp, _sfu)
                    try:
                        self._import_cache_mtime[_imp] = os.path.getmtime(_imp)
                    except Exception:
                        self._import_cache_mtime[_imp] = 0
            else:
                try:
                    with open(_imp) as _f:
                        _s = json.load(_f)
                    _sk, _scp, _sfu = _s.get("scale", 1.0), _s.get("center_pivot", False), _s.get("flip_uvs", False)
                except Exception:
                    _sk, _scp, _sfu = 1.0, False, False
                self._import_cache[_imp] = (_sk, _scp, _sfu)
                try:
                    self._import_cache_mtime[_imp] = os.path.getmtime(_imp)
                except Exception:
                    self._import_cache_mtime[_imp] = 0
            cache_key = f"{mp}|s={_sk}|cp={_scp}|fu={_sfu}"
            mesh = None
            gm = getattr(self, '_get_mesh', None)
            if gm is not None:
                mesh = gm(cache_key)
                if mesh is None and not mf.mesh_path:
                    mesh = gm(mf.mesh_name)
            if mesh is not None:
                result.append((mesh, tr))
        return result
    def _get_mesh(self, cache_key: str) -> Optional[MeshData]:
        return None
    def _build_shadow_groups(self, renderable_shadow: list) -> dict:
        key = id(renderable_shadow)
        if key == self._shadow_groups_key and self._shadow_groups_cache is not None:
            return self._shadow_groups_cache
        if cy_build_shadow_groups is not None:
            groups = cy_build_shadow_groups(renderable_shadow)
        else:
            groups = defaultdict(list)
            for mesh, tr in renderable_shadow:
                groups[id(mesh)].append((mesh, tr))
        self._shadow_groups_cache = groups
        self._shadow_groups_key = key
        self._shadow_groups_ref = renderable_shadow
        return groups
    def _rebuild_shadow_index(self, renderable_shadow, n):
        try:
            if n <= 0:
                try:
                    self._flat_row_base = np.zeros(0, dtype=np.float64)
                    self._flat_index_src = renderable_shadow
                    self._flat_index_n = 0
                except Exception:
                    pass
                return
            mids = self._flat_mesh_ids[:n]
            mmap = self._flat_mesh_map
            rc = self._mesh_radius_cache
            uniq_m, inv_m = np.unique(mids, return_inverse=True)
            rvals = np.empty(len(uniq_m), dtype=np.float64)
            for k, u in enumerate(uniq_m.tolist()):
                try:
                    mesh = mmap.get(int(u))
                    b = rc.get(mesh) if mesh is not None else None
                    if b is None:
                        b = float(mesh.bounding_radius)
                        try:
                            if mesh is not None:
                                rc[mesh] = b
                        except Exception:
                            pass
                except Exception:
                    b = 1.0
                rvals[k] = b
            base = np.ascontiguousarray(rvals[inv_m], dtype=np.float64)
            self._flat_row_base = base
            self._flat_index_src = renderable_shadow
            self._flat_index_n = n
        except Exception:
            try:
                self._flat_index_src = None
                self._flat_index_n = 0
            except Exception:
                pass
