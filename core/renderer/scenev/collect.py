# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from itertools import chain as _chain
from typing import Optional, Any
from core._render_utils import build_frustum_cull_inputs as _bfci
from core.renderer.culling import cpu_frustum_cull


class ScenevCollectMixin:
    def _build_struct_tr_index(self, groups):
        index = {}
        try:
            for gk, grp in groups.items():
                n = len(grp)
                for pos in range(n):
                    try:
                        tr = grp[pos][1]
                    except Exception:
                        continue
                    if tr is None:
                        continue
                    try:
                        tid = id(tr)
                    except Exception:
                        continue
                    e = index.get(tid)
                    if e is None:
                        index[tid] = {gk: [pos]}
                    else:
                        lst = e.get(gk)
                        if lst is None:
                            e[gk] = [pos]
                        else:
                            lst.append(pos)
        except Exception:
            pass
        return index

    def _scenev_cull_renderable(self, snap, renderable, view_mat, proj_mat):
        total = len(renderable) if renderable else 0
        try:
            self._culled_total = total
        except Exception:
            pass
        try:
            self._culled_visible = total
        except Exception:
            pass
        if not renderable:
            return renderable, None
        visible = None
        try:
            vp = proj_mat._d.T @ view_mat._d.T
        except Exception:
            vp = None
        try:
            _vpb = vp.tobytes() if vp is not None else None
        except Exception:
            _vpb = None
        try:
            _mgen = self._mesh_loader._loaded_generation if self._mesh_loader else 0
        except Exception:
            _mgen = 0
        try:
            _tv = snap.transform_version
        except Exception:
            _tv = None
        _vkey = None
        try:
            if _vpb is not None and _tv is not None:
                _vkey = (id(snap), _tv, _mgen, _vpb)
        except Exception:
            _vkey = None
        try:
            _vc = self._cull_vis_cache
        except Exception:
            _vc = None
        if _vkey is not None and _vc is not None and _vc[0] == _vkey:
            try:
                self._culled_visible = _vc[3]
            except Exception:
                pass
            return _vc[1], _vc[2]
        try:
            if vp is None:
                vp = proj_mat._d.T @ view_mat._d.T
            cull_entries = snap.cull_entries
            n_ent = len(cull_entries) if cull_entries is not None else 0
            if n_ent:
                try:
                    _mgen = self._mesh_loader._loaded_generation if self._mesh_loader else 0
                except Exception:
                    _mgen = 0
                try:
                    _tv = snap.transform_version
                except Exception:
                    _tv = None
                try:
                    _ckey = (id(snap), _tv, _mgen)
                    _cc = self._cull_inputs_cache
                except Exception:
                    _ckey = None
                    _cc = None
                if _ckey is not None and _cc is not None and _cc[0] == _ckey:
                    centers, radii = _cc[1], _cc[2]
                else:
                    centers, radii = _bfci(cull_entries)
                    try:
                        self._cull_inputs_cache = (_ckey, centers, radii)
                    except Exception:
                        pass
                visible = cpu_frustum_cull(centers, radii, vp)
                offsets = snap.cull_offsets
                counts = snap.cull_counts
                n_vis = len(visible)
                if n_vis == n_ent:
                    try:
                        self._culled_visible = total
                    except Exception:
                        pass
                else:
                    try:
                        cc_np = snap._cull_counts_np
                        if cc_np is None or len(cc_np) != len(counts):
                            raise ValueError
                    except Exception:
                        try:
                            cc_np = np.ascontiguousarray(counts, dtype=np.int64)
                        except Exception:
                            cc_np = None
                        try:
                            snap._cull_counts_np = cc_np
                        except Exception:
                            pass
                    try:
                        if cc_np is not None and n_vis:
                            self._culled_visible = int(cc_np[visible].sum())
                        else:
                            self._culled_visible = sum(counts[i] for i in visible) if n_vis else 0
                    except Exception:
                        self._culled_visible = sum(counts[i] for i in visible) if n_vis else 0
                    if n_vis == 0:
                        renderable = []
                    elif n_vis == 1:
                        i = int(visible[0])
                        renderable = renderable[offsets[i]:offsets[i] + counts[i]]
                    else:
                        parts = [renderable[offsets[i]:offsets[i] + counts[i]] for i in visible]
                        renderable = list(_chain.from_iterable(parts))
            else:
                n = len(renderable)
                centers, radii = _bfci(renderable)
                visible = cpu_frustum_cull(centers, radii, vp)
                try:
                    self._culled_visible = len(visible)
                except Exception:
                    pass
                if len(visible) < n:
                    renderable = [renderable[idx] for idx in visible]
        except Exception:
            import traceback
            traceback.print_exc()
        try:
            if _vkey is not None and visible is not None:
                self._cull_vis_cache = (_vkey, renderable, visible, self._culled_visible)
        except Exception:
            pass
        return renderable, visible

    def _scenev_partition_and_sort(self, renderable, cam_pos, scene=None):
        opaque_entries = None
        transparent_entries = []
        try:
            opaque_entries, transparent_entries = self._partition_transparent(renderable)
        except Exception:
            opaque_entries = renderable if renderable else []
            transparent_entries = []
        try:
            self._sort_transparent_far_first(transparent_entries, cam_pos)
        except Exception:
            pass
        try:
            if not transparent_entries:
                if len(opaque_entries) > 64 and getattr(self, "_triangles_drawn", 0) > 500000:
                    self._sort_opaque_front_first(opaque_entries, cam_pos)
        except Exception:
            pass
        return opaque_entries, transparent_entries

    def _scenev_collect_groups(self, entries):
        try:
            if self._batcher is None:
                return {}
        except Exception:
            return {}
        try:
            return self._batcher.collect_groups(entries, self._materials, self._shaders)
        except Exception:
            return {}
