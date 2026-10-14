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
_DYN_SCAN_DT = 0.25
_RASTER_MIN_DT = 0.3
_RB_BUDGET = 0.003


class RebuildMixin:
    def _nav_sig(self, entity, tr, cols):
        try:
            t = tr
            depth = 0
            while t is not None and depth < 8:
                try:
                    if t._dirty:
                        return None
                except Exception:
                    pass
                try:
                    ent = t._entity
                    p = ent.parent if ent is not None else None
                    t = p.transform if p is not None else None
                except Exception:
                    break
                depth += 1
            lp = tr.local_position
            lr = tr.local_rotation
            ls = tr.local_scale
            sig = [float(lp.x), float(lp.y), float(lp.z),
                   float(lr._x), float(lr._y), float(lr._z), float(lr._w),
                   float(ls.x), float(ls.y), float(ls.z)]
            for comp in cols:
                try:
                    cname = type(comp).__name__
                except Exception:
                    continue
                if cname not in _COLLIDER_TYPES:
                    continue
                try:
                    en = bool(comp.enabled)
                except Exception:
                    en = True
                try:
                    if cname == "BoxCollider":
                        sz = comp.size
                        cn = comp.center
                        sig.append(("b", float(sz.x), float(sz.y), float(sz.z),
                                            float(cn.x), float(cn.y), float(cn.z), en))
                    elif cname == "SphereCollider":
                        cn = comp.center
                        sig.append(("s", float(comp.radius),
                                            float(cn.x), float(cn.y), float(cn.z), en))
                    elif cname == "CapsuleCollider":
                        cn = comp.center
                        sig.append(("c", float(comp.radius), float(comp.height),
                                            int(getattr(comp, "direction", 1)),
                                            float(cn.x), float(cn.y), float(cn.z), en))
                    else:
                        return None
                except Exception:
                    return None
            return tuple(sig)
        except Exception:
            return None

    def _rb_begin(self, grid, key, sv):
        try:
            entities = list(self._scene.get_all_entities())
        except Exception:
            return None
        try:
            cap = len(entities) + 64
        except Exception:
            cap = 8192
        return {"key": key, "sv": int(sv), "ents": entities, "i": 0,
                "fp": {}, "bykey": {}, "flat": [], "fcache": {}, "cap": cap}

    def _rb_process_entity(self, grid, job, entity):
        try:
            key = self._entity_nav_key(entity)
        except Exception:
            return
        try:
            if key in grid._ignore_eids:
                return
        except Exception:
            pass
        try:
            tr = entity.transform
            if tr is None:
                return
            cols = self._collider_comps(entity)
        except Exception:
            return
        if not cols:
            return
        fp = job["fp"]
        bykey = job["bykey"]
        flat = job["flat"]
        fcache = job["fcache"]
        try:
            cache = grid._nav_cache
            if not isinstance(cache, dict):
                cache = {}
        except Exception:
            cache = {}
        sig = None
        try:
            sig = self._nav_sig(entity, tr, cols)
            if sig is not None:
                hit = cache.get((key, sig), None)
                if hit is not None:
                    entry, dl = hit
                    fp[key] = entry
                    bykey[key] = dl
                    for d in dl:
                        flat.append(d)
                    if len(fcache) < job["cap"]:
                        fcache[(key, sig)] = hit
                    return
        except Exception:
            pass
        try:
            cs = grid.cell_size
            hw = grid.half_world
            rr = grid.resolution
            _k, entry = self._fp_entry(entity, grid, cs, hw, rr, grid._ignore_eids)
        except Exception:
            return
        if _k is None or entry is None:
            return
        fp[key] = entry
        dl = []
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
                        d = ("b", tup, wa)
                        dl.append(d)
                        flat.append(d)
                        continue
                x1, y1, z1, x2, y2, z2 = grid._aabb_to_cell_range(ab.min, ab.max)
                d = ("a", (x1, y1, z1, x2, y2, z2), wa)
                dl.append(d)
                flat.append(d)
            except Exception:
                pass
        bykey[key] = dl
        if sig is not None and len(fcache) < job["cap"]:
            try:
                fcache[(key, sig)] = (entry, dl)
            except Exception:
                pass

    def _rb_pump(self, grid, job, budget: float) -> bool:
        try:
            deadline = time.perf_counter() + max(0.0005, float(budget))
        except Exception:
            deadline = time.perf_counter() + 0.003
        try:
            ents = job["ents"]
            i = int(job["i"])
            n = len(ents)
        except Exception:
            return True
        while i < n:
            try:
                self._rb_process_entity(grid, job, ents[i])
            except Exception:
                pass
            i += 1
            if (i & 63) == 0 and time.perf_counter() >= deadline:
                break
        try:
            job["i"] = i
        except Exception:
            pass
        return i >= n

    def _rb_finish(self, grid, job, key, sv) -> bool:
        try:
            try:
                grid._nav_cache = job["fcache"]
            except Exception:
                pass
            grid._rebuild_seq = int(grid._rebuild_seq) + 1
            grid._rebuild_sv = int(sv)
            req = "rb_%s" % uuid.uuid4().hex[:12]
            try:
                _gen = int(grid._grid_gen)
            except Exception:
                _gen = 0
            spec = {"kind": "rebuild", "req": req, "shell": grid, "key": key,
                    "descs": job["flat"], "fp": job["fp"], "bykey": job["bykey"],
                    "res": int(grid.resolution), "cell": float(grid.cell_size),
                    "half": float(grid.half_world),
                    "seq": int(grid._rebuild_seq), "sv": int(sv), "gen": _gen}
            grid._rebuild_req = req
            _get_nav_worker().submit(spec)
            return True
        except Exception:
            try:
                grid._rebuild_req = None
            except Exception:
                pass
            return False

    def _maybe_pump_rebuild(self, grid, key, sv, budget: float):
        try:
            now = time.perf_counter()
            if now - float(grid._rb_pump_t) < 0.016 and float(budget) < 0.010:
                return
            grid._rb_pump_t = now
        except Exception:
            pass
        try:
            job = grid._rb_job
        except Exception:
            job = None
        try:
            if job is None or int(job.get("sv", -999)) != int(sv) or job.get("key") != key:
                job = self._rb_begin(grid, key, sv)
                try:
                    grid._rb_job = job
                except Exception:
                    pass
            if job is None:
                return
            if self._rb_pump(grid, job, budget):
                try:
                    grid._rb_job = None
                except Exception:
                    pass
                self._rb_finish(grid, job, key, sv)
        except Exception:
            pass

    def _poll_rebuild(self, grid) -> bool:
        try:
            req = grid._rebuild_req
        except Exception:
            return False
        if not req:
            return False
        try:
            r = _get_nav_worker().take(req)
        except Exception:
            return False
        if r is None:
            return False
        try:
            grid._rebuild_req = None
        except Exception:
            pass
        try:
            _gid, payload = r
        except Exception:
            return False
        if payload is None:
            return False
        try:
            fresh, fp, bykey, sv, seq, key = payload
        except Exception:
            return False
        try:
            if int(seq) != int(grid._rebuild_seq):
                return False
            if int(sv) != int(grid._rebuild_sv):
                return False
        except Exception:
            return False
        try:
            now = time.perf_counter()
            with _GRID_LOCK:
                grid._grid = fresh
                grid._raw_grid = None
                grid._dirty = False
                grid._dyn_fp = fp if isinstance(fp, dict) else {}
                grid._dyn_descs = bykey if isinstance(bykey, dict) else {}
                grid._dyn_cursor = 0
                grid._dyn_scan = now
                grid._raster_time = 0.0
                grid._raster_seq = 0
                grid._raster_done = 0
                grid._raster_applied = 0
                grid._raster_pending = None
                grid._rebuild_done = int(seq)
                grid._built_once = True
                try:
                    grid._grid_gen = int(grid._grid_gen) + 1
                except Exception:
                    grid._grid_gen = 1
                self._last_grid_version = _bump_epoch()
            try:
                self._last_scene_version = int(sv)
            except Exception:
                pass
            try:
                ce = _SHARED_GRIDS.get(key)
                if ce is not None and ce[2] is grid:
                    try:
                        if ce[0]() is not None:
                            ce[1] = int(sv)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            return False
        self._los_walk = None
        self._los_base = None
        return True
