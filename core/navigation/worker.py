# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import collections
import threading
import time
import numpy as np
from core.maths.math3d import Vec3
try:
    from core import _nav_batch as _nb
    _HAS_NAV_CYTHON = True
except ImportError:
    _nb = None
    _HAS_NAV_CYTHON = False
from .stats import _stat, _timed
from .epoch import _bump_epoch, _GRID_LOCK
from .raster import _rasterize_descs_fresh
from .grid import NavGrid
from .world import NavWorld


class _NavSolveWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="zarin-navmesh")
        self._jobs = collections.deque()
        self._results: dict = {}
        self._cond = threading.Condition()
        self._solvers: dict = {}
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        try:
            with self._cond:
                self._cond.notify_all()
        except Exception:
            pass

    def submit(self, spec: dict):
        with self._cond:
            if len(self._jobs) >= 24:
                try:
                    drop = None
                    for i, old in enumerate(self._jobs):
                        try:
                            if old.get("kind") in ("raster", "rebuild"):
                                drop = i
                                break
                        except Exception:
                            continue
                    if drop is None:
                        old = self._jobs.popleft()
                    else:
                        old = self._jobs[drop]
                        try:
                            del self._jobs[drop]
                        except Exception:
                            pass
                    try:
                        self._results[old["req"]] = (old.get("gid"), None)
                    except Exception:
                        pass
                except Exception:
                    pass
            self._jobs.append(spec)
            self._cond.notify()

    def take(self, req: str):
        with self._cond:
            return self._results.pop(req, None)

    @_timed("w_raster")
    def _raster_apply(self, spec: dict):
        try:
            shell = spec["shell"]
        except Exception:
            return False
        try:
            if int(spec["seq"]) <= int(shell._raster_applied):
                return False
        except Exception:
            pass
        try:
            r = int(spec["res"])
            cell = float(spec["cell"])
            half = float(spec["half"])
            region = spec.get("region")
            descs = spec.get("descs") or []
            try:
                if int(spec.get("gen", shell._grid_gen)) != int(shell._grid_gen):
                    return False
            except Exception:
                pass
            if region is None:
                fresh = _rasterize_descs_fresh(r, cell, half, descs)
            else:
                try:
                    fresh = np.array(shell._grid, dtype=np.uint8, copy=True)
                except Exception:
                    return False
                cr, wr = region
                x1, y1, z1, x2, y2, z2 = cr
                try:
                    fresh[x1:x2 + 1, y1:y2 + 1, z1:z2 + 1] = 0
                except Exception:
                    pass
                for d in descs:
                    try:
                        wa = d[2]
                        if wa[3] < wr[0] or wa[0] > wr[3] or wa[4] < wr[1] or wa[1] > wr[4] or wa[5] < wr[2] or wa[2] > wr[5]:
                            continue
                        if d[0] == "b":
                            o = d[1]
                            _nb.raster_box_obb(np.ascontiguousarray(fresh), cell, half,
                                               o[0][0], o[0][1], o[0][2], o[1][0], o[1][1], o[1][2],
                                               o[2][0], o[2][1], o[2][2], o[2][3])
                        else:
                            c = d[1]
                            fresh[c[0]:c[3] + 1, c[1]:c[4] + 1, c[2]:c[5] + 1] = 1
                    except Exception:
                        pass
            try:
                with _GRID_LOCK:
                    if int(spec["seq"]) <= int(shell._raster_applied):
                        return False
                    shell._grid = fresh
                    shell._dirty = False
                    shell._raster_applied = int(spec["seq"])
                    if int(spec["seq"]) > int(shell._raster_done):
                        shell._raster_done = int(spec["seq"])
                    _bump_epoch()
            except Exception:
                return False
            return True
        except Exception:
            return False

    def _solver_for(self, res: int, size: float):
        key = (int(res), round(float(size), 3))
        s = self._solvers.get(key)
        if s is None:
            s = NavWorld.__new__(NavWorld)
            s._grid = NavGrid(int(res), float(size))
            s._scene = None
            s._last_grid_version = 0
            s._last_scene_version = -1
            s._pending_results = {}
            s._pending_jobs = {}
            s._path_cells = []
            s._raw_path_cells = []
            s._path_rects = []
            s._path_aabbs = []
            s._is_flying = False
            s._fly_dilate = None
            s._guard_params = None
            s._los_walk = None
            s._los_walk_gid = None
            s._los_seed = None
            s._los_ground = None
            s._los_climb = 0.0
            s._los_base = None
            s._los_base_gid = None
            s._los_fly_rad = 0
            s._t0 = 0.0
            self._solvers[key] = s
        return s

    def run(self):
        while not self._stop.is_set():
            try:
                with self._cond:
                    while not self._jobs and not self._stop.is_set():
                        self._cond.wait(0.5)
                    if self._stop.is_set():
                        break
                    spec = self._jobs.popleft()
                try:
                    out = self._solve(spec)
                except Exception:
                    out = None
                try:
                    with self._cond:
                        self._results[spec["req"]] = (spec.get("gid"), out)
                        while len(self._results) > 64:
                            try:
                                self._results.pop(next(iter(self._results)))
                            except Exception:
                                break
                except Exception:
                    pass
            except Exception:
                pass

    @_timed("w_rebuild")
    def _rebuild_apply(self, spec: dict):
        try:
            shell = spec["shell"]
        except Exception:
            return None
        try:
            if int(spec["seq"]) != int(shell._rebuild_seq):
                return None
        except Exception:
            pass
        try:
            r = int(spec["res"])
            cell = float(spec["cell"])
            half = float(spec["half"])
            fresh = _rasterize_descs_fresh(r, cell, half, spec.get("descs") or [])
            try:
                if int(spec["seq"]) != int(shell._rebuild_seq):
                    return None
            except Exception:
                pass
            return (fresh, spec.get("fp") or {}, spec.get("bykey") or {},
                    int(spec.get("sv", -1)), int(spec.get("seq", 0)), spec.get("key"))
        except Exception:
            return None

    def _solve(self, spec: dict):
        if spec.get("kind") == "raster":
            return self._raster_apply(spec)
        if spec.get("kind") == "rebuild":
            return self._rebuild_apply(spec)
        s = self._solver_for(spec["res"], spec["size"])
        g = s._grid
        g._grid = spec["grid"]
        s._last_grid_version = spec["gv"]
        s._fly_dilate = spec.get("fly_dil")
        s._t0 = time.perf_counter()
        a = Vec3(float(spec["a"][0]), float(spec["a"][1]), float(spec["a"][2]))
        b = Vec3(float(spec["b"][0]), float(spec["b"][1]), float(spec["b"][2]))
        _wt0 = time.perf_counter()
        try:
            if spec["fly"]:
                return s._find_path_fast_fly(a, b, float(spec["rad"]), spec["grid"], spec["gv"])
            return s._find_path_fast_ground(a, b, float(spec["rad"]), float(spec["h"]),
                                            float(spec["climb"]), float(spec["slope"]), spec["pad"],
                                            spec["grid"], spec["gv"])
        finally:
            try:
                _stat("w_path", (time.perf_counter() - _wt0) * 1000.0)
            except Exception:
                pass