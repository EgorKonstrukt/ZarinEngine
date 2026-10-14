# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
class SnapshotRefreshMixin:
    def _ensure_snapshot_tr_index(self, snap):
        try:
            cached_id = self._snap_tr_index_snap
            if cached_id == id(snap):
                idx = self._snap_tr_index
                if idx is not None and len(idx) > 0:
                    return idx
        except Exception:
            pass
        index = {}
        try:
            renderable = snap.renderable
            for i, entry in enumerate(renderable):
                try:
                    tr = entry[1]
                except Exception:
                    continue
                if tr is None:
                    continue
                tid = id(tr)
                lst = index.get(tid)
                if lst is None:
                    index[tid] = [i]
                else:
                    lst.append(i)
        except Exception:
            pass
        try:
            self._snap_tr_index = index
            self._snap_tr_index_snap = id(snap)
        except Exception:
            pass
        return index
    def _refresh_snapshot_world_matrices(self, scene):
        snap = self._snap_cache
        if snap is None:
            return
        try:
            tv = scene._transform_version
        except Exception:
            tv = None
        try:
            no_soft = not scene._component_indices.get("SoftBody")
        except Exception:
            no_soft = False
        if no_soft and tv is not None and tv == getattr(self, "_snap_refresh_tv", None):
            try:
                if not scene._dirty_roots and not scene._transform_version_pending:
                    return
            except Exception:
                pass
        try:
            flushed = scene.peek_flushed_transforms() if hasattr(scene, "peek_flushed_transforms") else None
        except Exception:
            flushed = None
        try:
            overflow = bool(getattr(scene, "_flushed_overflow", False))
        except Exception:
            overflow = False
        if flushed is not None and not overflow and len(flushed) == 0:
            try:
                if not scene._dirty_roots and not scene._transform_version_pending:
                    try:
                        self._snap_refresh_tv = scene._transform_version
                    except Exception:
                        pass
                    return
            except Exception:
                pass
        try:
            _race = list(scene._dirty_roots) if scene._dirty_roots else []
        except Exception:
            _race = []
        if _race:
            for t in _race:
                try:
                    if t._dirty:
                        t._update_world_matrix()
                except Exception:
                    pass
        for item in snap.projectors:
            try:
                item.refresh_vp()
            except Exception:
                pass
        try:
            self._refresh_soft_snapshot_meshes(scene)
        except Exception:
            pass
        try:
            self._snap_refresh_tv = scene._transform_version
        except Exception:
            pass
