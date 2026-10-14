# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import threading
import time
import heapq
import uuid
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3
from core.spatial.octp import AABB
from .grid import NavGrid, NavRect
from .stats import _stat, _timed
from .epoch import _bump_epoch, _current_epoch, _grid_snapshot, _GRID_LOCK
from .raster import _rasterize_descs_fresh, _shared_grid_for, _coarse_cached, _get_nav_worker, _COLLIDER_TYPES
from .raster import _SHARED_GRIDS
try:
    from core import _nav_batch as _nb
    _HAS_NAV_CYTHON = True
except ImportError:
    _nb = None
    _HAS_NAV_CYTHON = False
from .rebuild import _DYN_SCAN_DT, _RASTER_MIN_DT, _RB_BUDGET


class RebuildMixin3:
    def _entity_descs(self, entity, grid):
        out = []
        try:
            tr = entity.transform
        except Exception:
            tr = None
        try:
            cols = self._collider_comps(entity)
        except Exception:
            return out
        for comp in cols:
            try:
                cname = type(comp).__name__
            except Exception:
                continue
            if cname not in _COLLIDER_TYPES:
                continue
            try:
                ab = self._get_collider_world_aabb(comp)
                if ab is None:
                    continue
                wa = (float(ab.min.x), float(ab.min.y), float(ab.min.z),
                      float(ab.max.x), float(ab.max.y), float(ab.max.z))
            except Exception:
                continue
            try:
                if cname == "BoxCollider" and tr is not None and _HAS_NAV_CYTHON:
                    tup = self._box_obb_tuple(comp, tr)
                    if tup is not None and not self._box_aligned(tup[2]):
                        out.append(("b", tup, wa))
                        continue
                x1, y1, z1, x2, y2, z2 = grid._aabb_to_cell_range(ab.min, ab.max)
                out.append(("a", (x1, y1, z1, x2, y2, z2), wa))
            except Exception:
                pass
        return out

    def _drive_rebuild_pump(self):
        try:
            sc = self._scene
            if sc is None:
                return
            grid = self._grid
            if grid._rb_job is None:
                return
            sv = int(getattr(sc, '_render_version', -1))
            key = (id(sc), int(grid.resolution), round(float(grid.world_size), 3))
            self._maybe_pump_rebuild(grid, key, sv, _RB_BUDGET)
        except Exception:
            pass

    @_timed("dyn")
    def _poll_dynamics(self) -> bool:
        try:
            sc = self._scene
            if sc is None:
                return False
            grid = self._grid
            try:
                self._poll_rebuild(grid)
            except Exception:
                pass
            try:
                self._drive_rebuild_pump()
            except Exception:
                pass
            try:
                self._release_held_paths(grid)
            except Exception:
                pass
            try:
                if grid._rb_job is not None or grid._rebuild_req is not None:
                    return False
            except Exception:
                pass
            now = time.perf_counter()
            try:
                pend = grid._raster_pending
                if pend is not None:
                    pseq, pmap, ptime = pend
                    if int(grid._raster_applied) >= int(pseq):
                        grid._raster_pending = None
                    elif now - float(ptime) > 3.0:
                        try:
                            base0 = grid._dyn_fp
                            dc0 = grid._dyn_descs
                            if isinstance(base0, dict):
                                for k, item in pmap.items():
                                    try:
                                        old, new, ent = item
                                        if new is None:
                                            if k not in base0 and old is not None:
                                                base0[k] = old
                                        else:
                                            try:
                                                same = base0.get(k, None) == new
                                            except Exception:
                                                same = False
                                            if same:
                                                if old is None:
                                                    try:
                                                        base0.pop(k, None)
                                                    except Exception:
                                                        pass
                                                else:
                                                    base0[k] = old
                                                if isinstance(dc0, dict):
                                                    try:
                                                        dc0.pop(k, None)
                                                    except Exception:
                                                        pass
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        try:
                            grid._raster_pending = None
                        except Exception:
                            pass
            except Exception:
                pass
            if now - float(grid._dyn_scan) < _DYN_SCAN_DT:
                return False
            grid._dyn_scan = now
            try:
                entities = sc.get_all_entities()
            except Exception:
                return False
            n = len(entities)
            base = grid._dyn_fp
            if base is None:
                base = {}
                grid._dyn_fp = base
            try:
                cs = grid.cell_size
                hw = grid.half_world
                rr = grid.resolution
            except Exception:
                return False
            ignore = grid._ignore_eids
            start = 0
            try:
                if n > 0:
                    start = int(grid._dyn_cursor) % n
            except Exception:
                start = 0
            changed = {}
            try:
                m = min(n, 512)
                for i in range(m):
                    ent = entities[(start + i) % n]
                    try:
                        key, entry = self._fp_entry(ent, grid, cs, hw, rr, ignore)
                    except Exception:
                        continue
                    if key is None:
                        continue
                    old = base.get(key, None)
                    if entry is None:
                        if old is not None:
                            changed[key] = (old, None, ent)
                    elif old != entry:
                        changed[key] = (old, entry, ent)
                try:
                    grid._dyn_cursor = (start + m) % max(1, n)
                except Exception:
                    pass
            except Exception:
                return False
            if not changed:
                return False
            if now - float(grid._raster_time) < _RASTER_MIN_DT:
                return True
            if int(grid._raster_done) < int(grid._raster_seq):
                return True
            try:
                ok = self._submit_raster(grid, changed, now)
            except Exception:
                ok = False
            if ok:
                try:
                    grid._raster_pending = (int(grid._raster_seq), changed, now)
                    grid._raster_pending_seq = int(grid._raster_seq)
                    grid._raster_pending_t = now
                except Exception:
                    pass
                try:
                    for key, item in changed.items():
                        try:
                            old, new, ent = item
                        except Exception:
                            continue
                        if new is None:
                            try:
                                base.pop(key, None)
                            except Exception:
                                pass
                        else:
                            base[key] = new
                except Exception:
                    pass
            return True
        except Exception:
            return False
