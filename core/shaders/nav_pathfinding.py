# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import collections
import math
import threading
import time
import heapq
import uuid
import weakref
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3
from core.spatial.octree import AABB

try:
    from core import _nav_batch as _nb
    _HAS_NAV_CYTHON = True
except ImportError:
    _nb = None
    _HAS_NAV_CYTHON = False

_SHARED_GRIDS: dict = {}
_SHARED_ORDER: list = []

_WIN_CAP = 336
_COARSE_TGT = 224
_FINE_WIN = 112
_MAX_EXP_2D = 800000
_MAX_EXP_3D = 900000
_FLY_COARSE = 80
_FINE_3D_WIN = 56
_TIME_BUDGET = 1.5
_DYN_SCAN_DT = 0.25
_RASTER_MIN_DT = 0.3
_RB_BUDGET = 0.003
_GRID_EPOCH = 0
_EPOCH_LOCK = threading.Lock()
_GRID_LOCK = threading.RLock()
_FIELDS_SHARED: dict = {}
_CANDS_SHARED: dict = {}


def _bump_epoch():
    global _GRID_EPOCH
    with _EPOCH_LOCK:
        _GRID_EPOCH += 1
        return _GRID_EPOCH


def _current_epoch():
    return _GRID_EPOCH


def _grid_snapshot(grid):
    with _GRID_LOCK:
        return grid._grid, _GRID_EPOCH

_COLLIDER_TYPES = ("BoxCollider", "SphereCollider", "CapsuleCollider", "MeshCollider")


def _rasterize_descs_fresh(r: int, cell: float, half: float, descs) -> np.ndarray:
    fresh = np.zeros((r, r, r), dtype=np.uint8)
    try:
        for d in descs:
            try:
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
    except Exception:
        pass
    return fresh


def _shared_grid_for(scene, resolution: int, world_size: float):
    key = (id(scene), int(resolution), round(float(world_size), 3))
    e = _SHARED_GRIDS.get(key)
    if e is not None and e[0]() is scene:
        return e[2]
    g = NavGrid(int(resolution), float(world_size))
    _SHARED_GRIDS[key] = [weakref.ref(scene), -1, g]
    _SHARED_ORDER.append(key)
    while len(_SHARED_ORDER) > 6:
        _SHARED_GRIDS.pop(_SHARED_ORDER.pop(0), None)
    return g


_NAV_WORKER = None
_NAV_WORKER_LOCK = threading.Lock()
_COARSE_SHARED: dict = {}
_COARSE_LOCK = threading.Lock()


def _coarse_cached(base, f: int, dil: int, ep: int, res: int):
    key = (int(ep), int(res), int(f), int(dil))
    try:
        with _COARSE_LOCK:
            hit = _COARSE_SHARED.get(key)
        if hit is not None:
            return hit
    except Exception:
        pass
    coarse = _nb.downsample_any3d(np.ascontiguousarray(base), int(f))
    if dil > 0:
        coarse = _nb.dilate3d(coarse, int(dil))
    try:
        with _COARSE_LOCK:
            _COARSE_SHARED[key] = coarse
            while len(_COARSE_SHARED) > 4:
                _COARSE_SHARED.pop(next(iter(_COARSE_SHARED)))
    except Exception:
        pass
    return coarse


def _get_nav_worker():
    global _NAV_WORKER
    w = _NAV_WORKER
    if w is None:
        with _NAV_WORKER_LOCK:
            if _NAV_WORKER is None:
                _NAV_WORKER = _NavSolveWorker()
                _NAV_WORKER.start()
            w = _NAV_WORKER
    return w


class _NavSolveWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="zarin-navmesh")
        self._jobs = collections.deque()
        self._results: dict = {}
        self._cond = threading.Condition()
        self._solvers: dict = {}

    def submit(self, spec: dict):
        with self._cond:
            if len(self._jobs) >= 8:
                old = self._jobs.popleft()
                try:
                    self._results[old["req"]] = (old.get("gid"), None)
                except Exception:
                    pass
            self._jobs.append(spec)
            self._cond.notify()

    def take(self, req: str):
        with self._cond:
            return self._results.pop(req, None)

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
            s._los_ground = None
            s._los_climb = 0.0
            s._los_base = None
            s._los_base_gid = None
            s._los_fly_rad = 0
            s._t0 = 0.0
            self._solvers[key] = s
        return s

    def run(self):
        while True:
            try:
                with self._cond:
                    while not self._jobs:
                        self._cond.wait(0.5)
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
        if spec["fly"]:
            return s._find_path_fast_fly(a, b, float(spec["rad"]), spec["grid"], spec["gv"])
        return s._find_path_fast_ground(a, b, float(spec["rad"]), float(spec["h"]),
                                        float(spec["climb"]), float(spec["slope"]), spec["pad"],
                                        spec["grid"], spec["gv"])

_NEIGHBOR_OFFSETS_3D = [
    (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
]

_NEIGHBOR_OFFSETS_2D = [
    (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1),
]


class NavRect:
    __slots__ = ("gx", "gz", "gw", "gd", "ground_gy", "rid", "cx", "cz")
    def __init__(self, gx: int, gz: int, gw: int, gd: int, ground_gy: int, rid: int):
        self.gx = gx
        self.gz = gz
        self.gw = gw
        self.gd = gd
        self.ground_gy = ground_gy
        self.rid = rid
        self.cx = gx + gw * 0.5
        self.cz = gz + gd * 0.5

    def world_aabb(self, grid: "NavGrid") -> AABB:
        cs = grid.cell_size
        half = cs * 0.5
        c1 = grid.grid_to_world(self.gx, self.ground_gy, self.gz)
        c2 = grid.grid_to_world(self.gx + self.gw - 1, self.ground_gy, self.gz + self.gd - 1)
        return AABB(
            Vec3(c1.x - half, c1.y - half, c1.z - half),
            Vec3(c2.x + half, c2.y + half, c2.z + half),
        )

    def rect_aabb(self, grid: "NavGrid") -> AABB:
        cs = grid.cell_size
        c1 = grid.grid_to_world(self.gx, self.ground_gy, self.gz)
        c2 = grid.grid_to_world(self.gx + self.gw - 1, self.ground_gy, self.gz + self.gd - 1)
        return AABB(
            Vec3(c1.x, c1.y, c1.z),
            Vec3(c2.x, c2.y, c2.z),
        )


class NavGrid:
    def __init__(self, resolution: int = 48, world_size: float = 500.0):
        self.resolution = resolution
        self.world_size = world_size
        self.cell_size = world_size / resolution
        self.half_world = world_size * 0.5
        self._grid: np.ndarray = np.zeros((resolution, resolution, resolution), dtype=np.uint8)
        self._raw_grid: Optional[np.ndarray] = None
        self._built_once = False
        self._dirty = True
        self._dyn_fp: dict = {}
        self._dyn_cursor: int = 0
        self._dyn_descs: dict = {}
        self._dyn_scan = 0.0
        self._raster_time = 0.0
        self._raster_seq = 0
        self._raster_done = 0
        self._raster_applied = 0
        self._rebuild_seq = 0
        self._rebuild_done = 0
        self._rebuild_sv = -1
        self._rebuild_req = None
        self._grid_gen = 0
        self._nav_cache: dict = {}
        self._rb_job = None
        self._rb_pump_t = 0.0
        self._ignore_eids: set = set()

    def cell_aabb(self, gx: int, gy: int, gz: int) -> AABB:
        c = self.grid_to_world(gx, gy, gz)
        h = self.cell_size * 0.5
        return AABB(c - Vec3(h, h, h), c + Vec3(h, h, h))

    def world_to_grid(self, pos: Vec3) -> tuple[int, int, int]:
        gx = int((pos.x + self.half_world) / self.cell_size)
        gy = int((pos.y + self.half_world) / self.cell_size)
        gz = int((pos.z + self.half_world) / self.cell_size)
        return max(0, min(self.resolution - 1, gx)), max(0, min(self.resolution - 1, gy)), max(0, min(self.resolution - 1, gz))

    def grid_to_world(self, gx: int, gy: int, gz: int) -> Vec3:
        return Vec3(
            -self.half_world + (gx + 0.5) * self.cell_size,
            -self.half_world + (gy + 0.5) * self.cell_size,
            -self.half_world + (gz + 0.5) * self.cell_size,
        )

    def _aabb_to_cell_range(self, aabb_min: Vec3, aabb_max: Vec3) -> tuple[int, int, int, int, int, int]:
        r = self.resolution
        cs = self.cell_size
        hw = self.half_world
        if (aabb_max.x < -hw or aabb_min.x > hw or
                aabb_max.y < -hw or aabb_min.y > hw or
                aabb_max.z < -hw or aabb_min.z > hw):
            return (0, 0, 0, -1, -1, -1)
        gx1, gy1, gz1 = self.world_to_grid(aabb_min)
        gx2 = int(math.ceil((aabb_max.x + hw) / cs - 1e-9)) - 1
        gy2 = int(math.ceil((aabb_max.y + hw) / cs - 1e-9)) - 1
        gz2 = int(math.ceil((aabb_max.z + hw) / cs - 1e-9)) - 1
        if aabb_max.x <= -hw + 1e-9:
            gx2 = 0
        if aabb_min.x >= hw - 1e-9:
            gx1 = r - 1
        if aabb_max.y <= -hw + 1e-9:
            gy2 = 0
        if aabb_min.y >= hw - 1e-9:
            gy1 = r - 1
        if aabb_max.z <= -hw + 1e-9:
            gz2 = 0
        if aabb_min.z >= hw - 1e-9:
            gz1 = r - 1
        return (
            max(0, min(r - 1, gx1)), max(0, min(r - 1, gy1)), max(0, min(r - 1, gz1)),
            min(r - 1, gx2), min(r - 1, gy2), min(r - 1, gz2),
        )

    def mark_blocked(self, aabb_min: Vec3, aabb_max: Vec3):
        x1, y1, z1, x2, y2, z2 = self._aabb_to_cell_range(aabb_min, aabb_max)
        self._grid[x1:x2 + 1, y1:y2 + 1, z1:z2 + 1] = 1
        self._dirty = True

    def clear(self):
        self._grid.fill(0)
        self._dirty = True

    def is_blocked(self, gx: int, gy: int, gz: int) -> bool:
        if gx < 0 or gx >= self.resolution or gy < 0 or gy >= self.resolution or gz < 0 or gz >= self.resolution:
            return True
        return bool(self._grid[gx, gy, gz])

    def find_nearest_unblocked(self, gx: int, gy: int, gz: int, max_radius: int = 10) -> tuple[int, int, int]:
        if not self.is_blocked(gx, gy, gz):
            return (gx, gy, gz)
        if _HAS_NAV_CYTHON:
            try:
                return tuple(int(v) for v in _nb.nearest3d(np.ascontiguousarray(self._grid, dtype=np.uint8), int(gx), int(gy), int(gz), int(max_radius)))
            except Exception:
                pass
        r = self.resolution
        for radius in range(1, max_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    for dz in (-radius, radius):
                        nx, ny, nz = gx + dx, gy + dy, gz + dz
                        if 0 <= nx < r and 0 <= ny < r and 0 <= nz < r and not self._grid[nx, ny, nz]:
                            return (nx, ny, nz)
            for dx in range(-radius, radius + 1):
                for dz in range(-radius + 1, radius):
                    for dy in (-radius, radius):
                        nx, ny, nz = gx + dx, gy + dy, gz + dz
                        if 0 <= nx < r and 0 <= ny < r and 0 <= nz < r and not self._grid[nx, ny, nz]:
                            return (nx, ny, nz)
            for dy in range(-radius + 1, radius):
                for dz in range(-radius + 1, radius):
                    for dx in (-radius, radius):
                        nx, ny, nz = gx + dx, gy + dy, gz + dz
                        if 0 <= nx < r and 0 <= ny < r and 0 <= nz < r and not self._grid[nx, ny, nz]:
                            return (nx, ny, nz)
        return (gx, gy, gz)

    def find_ground_cell(self, gx: int, gy: int, gz: int) -> tuple[int, int, int]:
        r = self.resolution
        if not self.is_blocked(gx, gy, gz):
            return (gx, gy, gz)
        highest_blocked = -1
        for y in range(gy, -1, -1):
            if self._grid[gx, y, gz]:
                highest_blocked = y
                break
        for walk_y in range(highest_blocked + 1, r):
            if not self._grid[gx, walk_y, gz]:
                return (gx, walk_y, gz)
        for y in range(gy + 1, r):
            if not self._grid[gx, y, gz]:
                return (gx, y, gz)
        return (gx, gy, gz)

    @staticmethod
    def _dilate_2d(walkable: np.ndarray, radius: int) -> np.ndarray:
        if radius <= 0:
            return walkable
        if _HAS_NAV_CYTHON:
            try:
                out = np.empty_like(np.ascontiguousarray(walkable, dtype=np.uint8))
                _nb.dilate2d(np.ascontiguousarray(walkable, dtype=np.uint8), int(radius), out)
                return out
            except Exception:
                pass
        r = walkable.shape[0]
        dilated = walkable.copy()
        indices = np.where(dilated == 0)
        for idx in range(len(indices[0])):
            gx, gz = indices[0][idx], indices[1][idx]
            x1 = max(0, gx - radius)
            x2 = min(r, gx + radius + 1)
            z1 = max(0, gz - radius)
            z2 = min(r, gz + radius + 1)
            dilated[x1:x2, z1:z2] = 0
        return dilated

    def build_ground_obstacle_grid(self, agent_height_cells: int, max_climb_cells: int,
                                    max_slope_deg: float = 45.0,
                                    start_gx: int = 0, start_gy: int = 0, start_gz: int = 0) -> tuple[np.ndarray, np.ndarray, int]:
        r = self.resolution
        raw = self._raw_grid if self._raw_grid is not None else self._grid
        raw_bool = raw.astype(np.bool_)

        if _HAS_NAV_CYTHON:
            try:
                raw_c = np.ascontiguousarray(raw, dtype=np.uint8)
                walkable = np.zeros((r, r), dtype=np.uint8)
                ground_out = np.full((r, r), -1, dtype=np.int32)
                cost_out = np.ones((r, r), dtype=np.float32)
                if 0 < max_slope_deg < 90:
                    max_hdiff = math.tan(math.radians(max_slope_deg))
                else:
                    max_hdiff = 1e9
                _nb.build_ground_fields(raw_c, int(agent_height_cells + max_climb_cells), float(max_hdiff),
                                        float(self.cell_size), 0.15, 0.6, walkable, ground_out, cost_out)
                walk_gy = start_gy
                if 0 <= start_gx < r and 0 <= start_gz < r:
                    sg = ground_out[start_gx, start_gz]
                    if sg >= 0:
                        walk_gy = int(sg) + 1
                walk_gy = max(0, min(r - 1, walk_gy))
                return walkable, ground_out, walk_gy
            except Exception:
                pass
        walk_gy = start_gy
        for y in range(max(0, start_gy - 1), -1, -1):
            if raw[start_gx, y, start_gz]:
                walk_gy = y + 1
                break
        walk_gy = max(0, min(r - 1, walk_gy))

        hc = agent_height_cells + max_climb_cells
        ground_gy = np.full((r, r), -1, dtype=np.int32)
        for gy in range(r - 1, -1, -1):
            blocked_at_gy = raw_bool[:, gy, :]
            if not np.any(blocked_at_gy):
                continue
            top = min(r, gy + 2 + hc)
            if top > gy + 1:
                clear_above = ~np.any(raw_bool[:, gy + 1:top, :], axis=1)
            else:
                clear_above = np.ones((r, r), dtype=np.bool_)
            valid = blocked_at_gy & clear_above
            mask = valid & (ground_gy == -1)
            ground_gy[mask] = gy

        has_ground = ground_gy >= 0

        walkable = np.ones((r, r), dtype=np.uint32)
        walkable[~has_ground] = 0

        if 0 < max_slope_deg < 90:
            max_hdiff = math.tan(math.radians(max_slope_deg))
            if max_hdiff > 0:
                gv = ground_gy[has_ground]
                if gv.size > 0 and gv.max() - gv.min() > max_hdiff:
                    changed = True
                    while changed:
                        changed = False
                        for gx in range(r):
                            for gz in range(r):
                                if not walkable[gx, gz]:
                                    continue
                                h0 = ground_gy[gx, gz]
                                if h0 < 0:
                                    continue
                                for dx, dz in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                                    nx, nz = gx + dx, gz + dz
                                    if 0 <= nx < r and 0 <= nz < r and walkable[nx, nz]:
                                        h1 = ground_gy[nx, nz]
                                        if h1 >= 0 and abs(h1 - h0) > max_hdiff:
                                            walkable[gx, gz] = 0
                                            changed = True
                                            break

        return walkable, ground_gy, walk_gy

    def save_raw(self):
        self._raw_grid = self._grid.copy()

    def dilate_obstacles(self, radius_cells: int):
        if radius_cells <= 0:
            return
        self.save_raw()
        simple = self._grid.copy()
        r = self.resolution
        d = radius_cells
        indices = np.where(self._grid > 0)
        for idx in range(len(indices[0])):
            x, y, z = indices[0][idx], indices[1][idx], indices[2][idx]
            x1, x2 = max(0, x - d), min(r, x + d + 1)
            y1, y2 = max(0, y - d), min(r, y + d + 1)
            z1, z2 = max(0, z - d), min(r, z + d + 1)
            simple[x1:x2, y1:y2, z1:z2] = 1
        self._grid = simple
        self._dirty = True

    @property
    def flat_data(self) -> np.ndarray:
        return self._grid.ravel().astype(np.uint32)


class NavWorld:
    _instance: Optional[NavWorld] = None

    @classmethod
    def instance(cls) -> Optional[NavWorld]:
        return cls._instance

    def __init__(self, resolution: int = 48, world_size: float = 500.0):
        NavWorld._instance = self
        self._grid = NavGrid(resolution, world_size)
        self._scene = None
        self._last_grid_version = 0
        self._last_scene_version: int = -1
        self._pending_results: dict[str, Optional[list[Vec3]]] = {}
        self._path_cells: list[tuple[int, int, int]] = []
        self._raw_path_cells: list[tuple[int, int, int]] = []
        self._path_rects: list[NavRect] = []
        self._path_aabbs: list[tuple[AABB, int]] = []
        self._is_flying: bool = False
        self._fly_dilate: Optional[float] = None
        self._pending_jobs: dict = {}
        self._guard_params = None
        self._los_walk = None
        self._los_walk_gid = None
        self._los_ground = None
        self._los_climb = 0.0
        self._los_base = None
        self._los_base_gid = None
        self._los_fly_rad = 0
        self._t0: float = 0.0

    def find_path_gpu_deferred(self, start_world: Vec3, end_world: Vec3,
                                 agent_radius: float = 0.5, agent_height: float = 2.0,
                                 flying: bool = False,
                                 max_climb: float = 0.5, max_slope: float = 45.0,
                                 agent_padding: Optional[float] = None) -> str:
        req_id = uuid.uuid4().hex[:12]
        try:
            self._rebuild_grid()
        except Exception:
            pass
        try:
            self._poll_dynamics()
        except Exception:
            pass
        try:
            _pad = agent_padding if agent_padding is not None else agent_radius
            _gx, _gy, _gz = self._grid.world_to_grid(start_world)
            self._guard_params = (int(math.ceil(max(0.01, agent_height) / self._grid.cell_size)),
                                  int(math.ceil(max(0.0, max_climb) / self._grid.cell_size)),
                                  float(max_slope),
                                  int(max(0.0, _pad) / self._grid.cell_size + 0.5),
                                  float(max_climb),
                                  int(_gx), int(_gz),
                                  max(0, min(self._grid.resolution - 1, int(_gy))))
        except Exception:
            pass
        try:
            arr, gvep = _grid_snapshot(self._grid)
            spec = {
                "req": req_id,
                "grid": arr,
                "gid": id(arr),
                "gv": gvep,
                "res": self._grid.resolution,
                "size": self._grid.world_size,
                "fly": bool(flying),
                "a": (float(start_world.x), float(start_world.y), float(start_world.z)),
                "b": (float(end_world.x), float(end_world.y), float(end_world.z)),
                "rad": float(agent_radius),
                "h": float(agent_height),
                "climb": float(max_climb),
                "slope": float(max_slope),
                "pad": None if agent_padding is None else float(agent_padding),
                "fly_dil": self._fly_dilate,
            }
            self._pending_jobs[req_id] = (spec, 0)
            while len(self._pending_jobs) > 16:
                try:
                    self._pending_jobs.pop(next(iter(self._pending_jobs)))
                except Exception:
                    break
            _get_nav_worker().submit(spec)
            return req_id
        except Exception:
            pass
        try:
            path = self.find_path(start_world, end_world, agent_radius, agent_height, flying,
                                  max_climb, max_slope, agent_padding)
            self._pending_results[req_id] = path if path else []
        except Exception:
            self._pending_results[req_id] = []
        return req_id

    def poll_result(self, req_id: str) -> Optional[list[Vec3]]:
        try:
            self._poll_rebuild(self._grid)
        except Exception:
            pass
        try:
            r = _get_nav_worker().take(req_id)
            if r is not None:
                gid, payload = r
                slot = self._pending_jobs.pop(req_id, None)
                if payload is not None and (slot is None or gid == id(self._grid._grid)):
                    return payload if payload else []
                if slot is not None:
                    spec, tries = slot
                    if tries < 3:
                        spec2 = dict(spec)
                        try:
                            arr2, ep2 = _grid_snapshot(self._grid)
                            spec2["grid"] = arr2
                            spec2["gid"] = id(arr2)
                            spec2["gv"] = ep2
                        except Exception:
                            pass
                        self._pending_jobs[req_id] = (spec2, tries + 1)
                        try:
                            _get_nav_worker().submit(spec2)
                        except Exception:
                            pass
                        return None
                return []
        except Exception:
            pass
        return self._pending_results.pop(req_id, None)

    def has_los(self, a: Vec3, b: Vec3, flying: bool) -> bool:
        try:
            self._poll_dynamics()
        except Exception:
            pass
        try:
            grid = self._grid
            if flying:
                base = self._los_base
                if base is None or self._los_base_gid != id(grid._grid):
                    return True
                sa = grid.world_to_grid(a)
                sb = grid.world_to_grid(b)
                return bool(_nb.los3d_clear(np.ascontiguousarray(base), sa[0], sa[1], sa[2], sb[0], sb[1], sb[2],
                                            int(self._los_fly_rad)))
            walk = self._los_walk
            if walk is None or self._los_walk_gid != id(grid._grid):
                gp = getattr(self, "_guard_params", None)
                if gp is None or len(gp) < 8 or not _HAS_NAV_CYTHON:
                    return True
                try:
                    arr0, ep0 = _grid_snapshot(grid)
                    F = self._derived_fields(arr0, ep0, grid.cell_size, gp[0], gp[1], gp[2], gp[3], gp[4], gp[5], gp[6], gp[7])
                except Exception:
                    return True
                if F is None:
                    return True
                walk = F["walk"]
                self._los_walk = walk
                self._los_ground = F["ground"]
                try:
                    self._los_climb = max(0.0, float(gp[4])) / max(1e-6, float(grid.cell_size))
                except Exception:
                    self._los_climb = 0.0
                try:
                    self._los_walk_gid = id(arr0)
                except Exception:
                    self._los_walk_gid = None
            los_ground = self._los_ground
            if los_ground is None:
                sa = grid.world_to_grid(a)
                sb = grid.world_to_grid(b)
                return bool(_nb.los2d(np.ascontiguousarray(walk), sa[0], sa[2], sb[0], sb[2]))
            return self._segwalk_world(walk, los_ground, grid, float(self._los_climb), a, b)
        except Exception:
            return True

    def get_path_cells(self) -> list[tuple[int, int, int]]:
        return list(self._path_cells)

    def _build_path_aabbs(self):
        self._path_aabbs.clear()
        if self._path_rects:
            for rct in self._path_rects:
                self._path_aabbs.append((rct.world_aabb(self._grid), 0))
            for rct in self._path_rects:
                self._path_aabbs.append((rct.rect_aabb(self._grid), 1))
            return
        max_cells = 200
        n = min(len(self._raw_path_cells), max_cells)
        step = max(1, len(self._raw_path_cells) // max_cells) if len(self._raw_path_cells) > max_cells else 1
        for idx in range(0, len(self._raw_path_cells), step):
            gx, gy, gz = self._raw_path_cells[idx]
            self._path_aabbs.append((self._grid.cell_aabb(gx, gy, gz), 0))

    def get_path_aabbs(self) -> list[tuple[AABB, int]]:
        return self._path_aabbs

    def set_scene(self, scene):
        self._scene = scene
        try:
            self._grid._rb_job = None
        except Exception:
            pass
        if scene is not None:
            try:
                self._grid = _shared_grid_for(scene, self._grid.resolution, self._grid.world_size)
            except Exception:
                pass
            try:
                if not self._grid._built_once:
                    self._grid._grid.fill(1)
            except Exception:
                pass
            self._last_scene_version = -1
        self._rebuild_grid()

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

    def _is_grid_current(self) -> bool:
        try:
            if not self._scene:
                return True
            sv = int(getattr(self._scene, '_render_version', -1))
        except Exception:
            return True
        try:
            key = (id(self._scene), int(self._grid.resolution), round(float(self._grid.world_size), 3))
            e = _SHARED_GRIDS.get(key)
            return (e is not None and e[0]() is self._scene and e[1] == sv and not self._grid._dirty)
        except Exception:
            return True

    def wait_grid_ready(self, timeout: float = 30.0) -> bool:
        try:
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < float(timeout):
                try:
                    grid = self._grid
                except Exception:
                    return True
                try:
                    self._poll_rebuild(grid)
                except Exception:
                    pass
                if self._is_grid_current():
                    return True
                try:
                    if not self._scene:
                        return True
                    sv = int(getattr(self._scene, '_render_version', -1))
                    key = (id(self._scene), int(grid.resolution), round(float(grid.world_size), 3))
                except Exception:
                    return True
                try:
                    if grid._rebuild_req is None:
                        self._maybe_pump_rebuild(grid, key, sv, 0.050)
                except Exception:
                    pass
                time.sleep(0.005)
        except Exception:
            pass
        return False

    def _rebuild_grid(self):
        if not self._scene:
            return
        try:
            sv = int(getattr(self._scene, '_render_version', -1))
        except Exception:
            sv = -1
        key = (id(self._scene), int(self._grid.resolution), round(float(self._grid.world_size), 3))
        e = _SHARED_GRIDS.get(key)
        if e is not None and e[0]() is self._scene and e[1] == sv and not self._grid._dirty:
            self._last_scene_version = sv
            return
        if e is not None and e[0]() is self._scene:
            if e[2] is not self._grid:
                self._grid = e[2]
        grid = self._grid
        try:
            self._poll_rebuild(grid)
        except Exception:
            pass
        e = _SHARED_GRIDS.get(key)
        if e is not None and e[0]() is self._scene and e[1] == sv and not grid._dirty:
            self._last_scene_version = sv
            return
        self._last_scene_version = sv
        try:
            if grid._rebuild_req is not None and int(grid._rebuild_sv) == sv:
                return
        except Exception:
            pass
        try:
            self._maybe_pump_rebuild(grid, key, sv, _RB_BUDGET)
        except Exception:
            pass

    def _box_obb_tuple(self, comp, tr):
        scale = tr.local_scale
        hx = float(comp.size.x * scale.x * 0.5)
        hy = float(comp.size.y * scale.y * 0.5)
        hz = float(comp.size.z * scale.z * 0.5)
        if hx <= 0.0 or hy <= 0.0 or hz <= 0.0:
            return None
        pos = tr.local_position
        rot = tr.local_rotation
        cl = Vec3(float(comp.center.x * scale.x), float(comp.center.y * scale.y), float(comp.center.z * scale.z))
        c = pos + rot.rotate_vec3(cl)
        return ((float(c.x), float(c.y), float(c.z)), (hx, hy, hz),
                (float(rot._x), float(rot._y), float(rot._z), float(rot._w)))

    def _box_aligned(self, q) -> bool:
        try:
            qx, qy, qz, qw = float(q[0]), float(q[1]), float(q[2]), float(q[3])
            nq = qx * qx + qy * qy + qz * qz + qw * qw
            if nq > 1e-12:
                inv = 1.0 / math.sqrt(nq)
                qx *= inv
                qy *= inv
                qz *= inv
                qw *= inv
            rows = (
                (1.0 - 2.0 * (qy * qy + qz * qz), 2.0 * (qx * qy - qz * qw), 2.0 * (qx * qz + qy * qw)),
                (2.0 * (qx * qy + qz * qw), 1.0 - 2.0 * (qx * qx + qz * qz), 2.0 * (qy * qz - qx * qw)),
                (2.0 * (qx * qz - qy * qw), 2.0 * (qy * qz + qx * qw), 1.0 - 2.0 * (qx * qx + qy * qy)),
            )
            for row in rows:
                if sum(1 for v in row if abs(v) > 0.999999) != 1:
                    return False
            return True
        except Exception:
            return False

    def ignore_entity(self, eid, ignore: bool = True):
        try:
            if ignore:
                self._grid._ignore_eids.add(eid)
            else:
                self._grid._ignore_eids.discard(eid)
        except Exception:
            pass

    def _entity_nav_key(self, entity):
        try:
            eid = entity.id
            if eid is None:
                eid = id(entity)
        except Exception:
            eid = id(entity)
        return eid

    def _collider_comps(self, entity):
        try:
            tm = getattr(entity, "_type_map", None)
            if tm:
                cols = []
                for t, lst in tm.items():
                    try:
                        nm = t.__name__
                    except Exception:
                        continue
                    if nm in _COLLIDER_TYPES and lst:
                        try:
                            for c in lst:
                                if c is not None:
                                    cols.append(c)
                        except Exception:
                            pass
                return cols
            return [c for c in entity.get_all_components()
                    if type(c).__name__ in _COLLIDER_TYPES]
        except Exception:
            return []

    def _world_matrix_rows(self, tr):
        try:
            um = getattr(tr, "_update_world_matrix", None)
            if um is not None:
                um()
            d = tr._world_matrix._d
            return d
        except Exception:
            return None

    def _fp_entry(self, entity, grid, cs, hw, rr, ignore):
        try:
            key = self._entity_nav_key(entity)
        except Exception:
            return None, None
        if key in ignore:
            return key, None
        try:
            cols = self._collider_comps(entity)
        except Exception:
            return None, None
        if not cols:
            return key, None
        m = None
        px = py = pz = 0.0
        local_fallback = False
        try:
            tr = entity.transform
            if tr is None:
                return key, None
            d = self._world_matrix_rows(tr)
            if d is None:
                raise ValueError
            m = tuple(round(float(d[r][c]), 3) for r in range(4) for c in range(4))
            px, py, pz = float(m[12]), float(m[13]), float(m[14])
        except Exception:
            m = None
        if m is None:
            try:
                tr = entity.transform
                if tr is None:
                    return key, None
                lp = tr.local_position
                lr = tr.local_rotation
                ls = tr.local_scale
                px, py, pz = float(lp.x), float(lp.y), float(lp.z)
                m = (round(px, 3), round(py, 3), round(pz, 3),
                     round(float(lr._x), 4), round(float(lr._y), 4),
                     round(float(lr._z), 4), round(float(lr._w), 4),
                     round(float(ls.x), 3), round(float(ls.y), 3), round(float(ls.z), 3))
                local_fallback = True
            except Exception:
                return key, None
        try:
            act = bool(entity.active)
        except Exception:
            act = True
        parts = []
        maxd = 0.0
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
                    sx, sy, szv = float(sz.x), float(sz.y), float(sz.z)
                    parts.append(("b", round(sx, 3), round(sy, 3), round(szv, 3),
                                  round(float(cn.x), 3), round(float(cn.y), 3), round(float(cn.z), 3), en))
                    dd = (sx * sx + sy * sy + szv * szv) ** 0.5 * 0.5
                    if dd > maxd:
                        maxd = dd
                elif cname == "SphereCollider":
                    cn = comp.center
                    cr = float(comp.radius)
                    parts.append(("s", round(cr, 3),
                                  round(float(cn.x), 3), round(float(cn.y), 3), round(float(cn.z), 3), en))
                    if cr > maxd:
                        maxd = cr
                elif cname == "CapsuleCollider":
                    cn = comp.center
                    cr = float(comp.radius)
                    ch = float(comp.height)
                    parts.append(("c", round(cr, 3), round(ch, 3),
                                  int(getattr(comp, "direction", 1)),
                                  round(float(cn.x), 3), round(float(cn.y), 3), round(float(cn.z), 3), en))
                    dd = ((ch + cr * 2.0) ** 2 + (cr * 2.0) ** 2) ** 0.5 * 0.5
                    if dd > maxd:
                        maxd = dd
                elif cname == "MeshCollider":
                    parts.append(("m", str(getattr(comp, "mesh_path", "")), en))
                    try:
                        mab = self._get_collider_world_aabb(comp)
                        if mab is not None:
                            dd = ((float(mab.max.x - mab.min.x)) ** 2 +
                                  (float(mab.max.y - mab.min.y)) ** 2 +
                                  (float(mab.max.z - mab.min.z)) ** 2) ** 0.5 * 0.5
                            if dd > maxd:
                                maxd = dd
                        else:
                            maxd = 1e30
                    except Exception:
                        maxd = 1e30
            except Exception:
                parts.append((cname, en))
        if not parts:
            return key, None
        try:
            sm = maxd * 1.5 + cs
            if local_fallback:
                sm = sm * 2.0 + cs * 8.0
            gx = max(0, min(rr - 1, int((px + hw) / cs)))
            gy = max(0, min(rr - 1, int((py + hw) / cs)))
            gz = max(0, min(rr - 1, int((pz + hw) / cs)))
            rad = max(1, min(rr, int(sm / cs) + 2))
        except Exception:
            gx, gy, gz, rad = 0, 0, 0, rr
        return key, (act, m, tuple(parts), (gx, gy, gz, rad))

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
            now = time.perf_counter()
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

    def _submit_raster(self, grid, changed: dict, now: float):
        try:
            r = grid.resolution
            cs = grid.cell_size
            hw = grid.half_world
            try:
                descs_cache = grid._dyn_descs
            except Exception:
                descs_cache = {}
                grid._dyn_descs = descs_cache
            try:
                x1, y1, z1 = r, r, r
                x2, y2, z2 = -1, -1, -1
                descs = []
                for key, item in changed.items():
                    try:
                        old, new, ent = item
                    except Exception:
                        continue
                    for ce in (old[3] if old is not None else None,
                               new[3] if new is not None else None):
                        if ce is None:
                            continue
                        try:
                            x1 = min(x1, max(0, ce[0] - ce[3]))
                            y1 = min(y1, max(0, ce[1] - ce[3]))
                            z1 = min(z1, max(0, ce[2] - ce[3]))
                            x2 = max(x2, min(r - 1, ce[0] + ce[3]))
                            y2 = max(y2, min(r - 1, ce[1] + ce[3]))
                            z2 = max(z2, min(r - 1, ce[2] + ce[3]))
                        except Exception:
                            pass
                    try:
                        if new is None:
                            try:
                                descs_cache.pop(key, None)
                            except Exception:
                                pass
                        else:
                            ed = self._entity_descs(ent, grid)
                            descs_cache[key] = ed
                    except Exception:
                        pass
                if x1 > x2:
                    return False
                for dl in descs_cache.values():
                    try:
                        for d in dl:
                            descs.append(d)
                    except Exception:
                        pass
                vol = (x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1)
                region = None
                if len(changed) <= 200 and vol <= r * r * r // 4:
                    region = ((x1, y1, z1, x2, y2, z2),
                              (x1 * cs - hw, y1 * cs - hw, z1 * cs - hw,
                               (x2 + 1) * cs - hw, (y2 + 1) * cs - hw, (z2 + 1) * cs - hw))
                grid._raster_seq = int(grid._raster_seq) + 1
                try:
                    _gen = int(grid._grid_gen)
                except Exception:
                    _gen = 0
                spec = {"kind": "raster", "req": "__raster_%d" % int(grid._raster_seq),
                        "shell": grid, "descs": descs,
                        "res": int(r), "cell": float(cs), "half": float(hw),
                        "seq": int(grid._raster_seq), "region": region, "gen": _gen}
                _get_nav_worker().submit(spec)
                grid._raster_time = now
                return True
            except Exception:
                return False
        except Exception:
            return False


    def _get_collider_world_aabb(self, comp) -> Optional[AABB]:
        entity = comp._entity
        if not entity:
            return None
        tr = entity.transform
        if not tr:
            return None
        pos = tr.local_position
        rot = tr.local_rotation
        scale = tr.local_scale
        cname = type(comp).__name__

        if cname == "BoxCollider":
            try:
                d = self._world_matrix_rows(tr)
                if d is not None:
                    R = np.asarray(d[:3, :3], dtype=np.float64)
                    t = np.asarray(d[3, :3], dtype=np.float64).ravel()
                    if R.shape == (3, 3) and t.shape == (3,) and np.all(np.isfinite(R)) and np.all(np.isfinite(t)):
                        cl0 = np.array([float(comp.center.x), float(comp.center.y), float(comp.center.z)])
                        h0 = np.array([float(comp.size.x) * 0.5, float(comp.size.y) * 0.5, float(comp.size.z) * 0.5])
                        cw = cl0 @ R + t
                        e = np.abs(R).T @ h0
                        return AABB(Vec3(float(cw[0] - e[0]), float(cw[1] - e[1]), float(cw[2] - e[2])),
                                    Vec3(float(cw[0] + e[0]), float(cw[1] + e[1]), float(cw[2] + e[2])))
            except Exception:
                pass
            hx = comp.size.x * scale.x * 0.5
            hy = comp.size.y * scale.y * 0.5
            hz = comp.size.z * scale.z * 0.5
            cl = Vec3(comp.center.x * scale.x, comp.center.y * scale.y, comp.center.z * scale.z)
            c = pos + rot.rotate_vec3(cl)
            local_corners = [
                Vec3(-hx, -hy, -hz), Vec3(hx, -hy, -hz), Vec3(-hx, hy, -hz), Vec3(hx, hy, -hz),
                Vec3(-hx, -hy, hz), Vec3(hx, -hy, hz), Vec3(-hx, hy, hz), Vec3(hx, hy, hz),
            ]
            ws = [c + rot.rotate_vec3(lc) for lc in local_corners]
            bmin = Vec3(min(v.x for v in ws), min(v.y for v in ws), min(v.z for v in ws))
            bmax = Vec3(max(v.x for v in ws), max(v.y for v in ws), max(v.z for v in ws))
            return AABB(bmin, bmax)
        elif cname == "SphereCollider":
            r = comp.radius * max(scale.x, scale.y, scale.z)
            c = pos + rot.rotate_vec3(Vec3(comp.center.x * scale.x, comp.center.y * scale.y, comp.center.z * scale.z))
            return AABB(c - Vec3(r, r, r), c + Vec3(r, r, r))
        elif cname == "CapsuleCollider":
            r = comp.radius
            hh = comp.height * 0.5
            cl = Vec3(comp.center.x * scale.x, comp.center.y * scale.y, comp.center.z * scale.z)
            c = pos + rot.rotate_vec3(cl)
            if comp.direction == 1:
                axis_local = Vec3(0, hh * scale.y, 0)
            elif comp.direction == 0:
                axis_local = Vec3(hh * scale.x, 0, 0)
            else:
                axis_local = Vec3(0, 0, hh * scale.z)
            rs = r * max(scale.x, scale.y, scale.z)
            axis_world = rot.rotate_vec3(axis_local)
            a = c + axis_world
            b = c - axis_world
            rv = Vec3(rs, rs, rs)
            aabb_a = AABB(a - rv, a + rv)
            aabb_b = AABB(b - rv, b + rv)
            return AABB(
                Vec3(min(aabb_a.min.x, aabb_b.min.x), min(aabb_a.min.y, aabb_b.min.y), min(aabb_a.min.z, aabb_b.min.z)),
                Vec3(max(aabb_a.max.x, aabb_b.max.x), max(aabb_a.max.y, aabb_b.max.y), max(aabb_a.max.z, aabb_b.max.z)),
            )
        elif cname == "MeshCollider":
            if hasattr(comp, 'mesh_path') and comp.mesh_path:
                try:
                    from core.engine.engine import Engine
                    eng = Engine.instance()
                    if eng and hasattr(eng, '_renderer') and eng._renderer:
                        mesh = eng._renderer._meshes.get(comp.mesh_path)
                        if mesh and hasattr(mesh, 'aabb_min') and hasattr(mesh, 'aabb_max'):
                            corners = np.array([
                                [mesh.aabb_min[i] for i in range(3)] + [1],
                                [mesh.aabb_max[0], mesh.aabb_min[1], mesh.aabb_min[2], 1],
                                [mesh.aabb_max[0], mesh.aabb_max[1], mesh.aabb_min[2], 1],
                                [mesh.aabb_min[0], mesh.aabb_max[1], mesh.aabb_min[2], 1],
                                [mesh.aabb_min[0], mesh.aabb_min[1], mesh.aabb_max[2], 1],
                                [mesh.aabb_max[0], mesh.aabb_min[1], mesh.aabb_max[2], 1],
                                [mesh.aabb_max[0], mesh.aabb_max[1], mesh.aabb_max[2], 1],
                                [mesh.aabb_min[0], mesh.aabb_max[1], mesh.aabb_max[2], 1],
                            ], dtype=np.float32)
                            wm = tr.world_matrix._d
                            pts = corners @ wm
                            bmin = pts[:, :3].min(axis=0)
                            bmax = pts[:, :3].max(axis=0)
                            return AABB(Vec3(float(bmin[0]), float(bmin[1]), float(bmin[2])),
                                        Vec3(float(bmax[0]), float(bmax[1]), float(bmax[2])))
                except Exception:
                    pass
            return None
        return None

    def rebuild_grid(self):
        self._rebuild_grid()

    def dilate_for_agent(self, radius: float):
        try:
            self._fly_dilate = max(0.0, float(radius))
        except Exception:
            self._fly_dilate = None

    def get_path_cell_aabbs(self) -> list[AABB]:
        result = []
        for rct in self._path_rects:
            result.append(rct.world_aabb(self._grid))
        return result

    def get_path_rects(self) -> list[NavRect]:
        return list(self._path_rects)

    def _heuristic(self, ax: int, ay: int, az: int, bx: int, by: int, bz: int) -> float:
        dx = abs(ax - bx)
        dy = abs(ay - by)
        dz = abs(az - bz)
        return float(dx + dy + dz)

    def _astar(self, sx: int, sy: int, sz: int, ex: int, ey: int, ez: int, flying: bool) -> Optional[list[tuple[int, int, int]]]:
        res = self._grid.resolution
        if flying:
            sx, sy, sz = self._grid.find_nearest_unblocked(sx, sy, sz)
            ex, ey, ez = self._grid.find_nearest_unblocked(ex, ey, ez)

        offsets = _NEIGHBOR_OFFSETS_3D if flying else _NEIGHBOR_OFFSETS_2D
        start = (sx, sy, sz)
        end = (ex, ey, ez)

        open_heap = [(0.0, 0, start)]
        g_scores = {start: 0}
        came_from = {start: None}

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            cx, cy, cz = current

            if current == end:
                path = []
                while current is not None:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path

            for dx, dy, dz in offsets:
                nx, ny, nz = cx + dx, cy + dy, cz + dz
                neighbor = (nx, ny, nz)
                if nx < 0 or nx >= res or ny < 0 or ny >= res or nz < 0 or nz >= res:
                    continue
                if self._grid.is_blocked(nx, ny, nz):
                    continue

                ng = g_scores[current] + 1
                if neighbor not in g_scores or ng < g_scores[neighbor]:
                    g_scores[neighbor] = ng
                    f_score = ng + self._heuristic(nx, ny, nz, ex, ey, ez)
                    heapq.heappush(open_heap, (f_score, id(neighbor), neighbor))
                    came_from[neighbor] = current

        return None

    def _astar_2d(self, sx: int, sz: int, ex: int, ez: int,
                  walkable_2d: np.ndarray) -> Optional[list[tuple[int, int, int]]]:
        r = walkable_2d.shape[0]

        def snap(gx, gz):
            if 0 <= gx < r and 0 <= gz < r and walkable_2d[gx, gz]:
                return (gx, gz)
            for radius in range(1, min(r, 21)):
                for dx in range(-radius, radius + 1):
                    for dz in (-radius, radius):
                        nx, nz = gx + dx, gz + dz
                        if 0 <= nx < r and 0 <= nz < r and walkable_2d[nx, nz]:
                            return (nx, nz)
                for dz in range(-radius + 1, radius):
                    for dx in (-radius, radius):
                        nx, nz = gx + dx, gz + dz
                        if 0 <= nx < r and 0 <= nz < r and walkable_2d[nx, nz]:
                            return (nx, nz)
            return None

        start = snap(sx, sz)
        end = snap(ex, ez)
        if start is None or end is None:
            return None

        open_heap = [(0.0, 0, start)]
        g_scores = {start: 0}
        came_from = {start: None}

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            cx, cz = current

            if current == end:
                path = []
                while current is not None:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path

            for dx, dz in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, nz = cx + dx, cz + dz
                neighbor = (nx, nz)
                if nx < 0 or nx >= r or nz < 0 or nz >= r:
                    continue
                if not walkable_2d[nx, nz]:
                    continue

                ng = g_scores[current] + 1
                if neighbor not in g_scores or ng < g_scores[neighbor]:
                    g_scores[neighbor] = ng
                    f_score = ng + abs(nx - ex) + abs(nz - ez)
                    heapq.heappush(open_heap, (f_score, id(neighbor), neighbor))
                    came_from[neighbor] = current

        return None

    @staticmethod
    def _decompose_walkable(walkable: np.ndarray, ground_gy: np.ndarray) -> list[NavRect]:
        r = walkable.shape[0]
        assigned = np.zeros((r, r), dtype=np.bool_)
        rects = []
        rid = 0
        for gz in range(r):
            for gx in range(r):
                if not walkable[gx, gz] or assigned[gx, gz]:
                    continue
                cell_gy = ground_gy[gx, gz]
                if cell_gy < 0:
                    assigned[gx, gz] = True
                    continue
                gw = 1
                while gx + gw < r and walkable[gx + gw, gz] and not assigned[gx + gw, gz] and ground_gy[gx + gw, gz] == cell_gy:
                    gw += 1
                gd = 1
                while gz + gd < r:
                    row_ok = True
                    for dx in range(gw):
                        if not walkable[gx + dx, gz + gd] or assigned[gx + dx, gz + gd] or ground_gy[gx + dx, gz + gd] != cell_gy:
                            row_ok = False
                            break
                    if not row_ok:
                        break
                    gd += 1
                assigned[gx:gx + gw, gz:gz + gd] = True
                rects.append(NavRect(gx, gz, gw, gd, cell_gy, rid))
                rid += 1
        return rects

    @staticmethod
    def _build_rect_grid(rects: list[NavRect], r: int) -> np.ndarray:
        grid = np.full((r, r), -1, dtype=np.int32)
        for rect in rects:
            grid[rect.gx:rect.gx + rect.gw, rect.gz:rect.gz + rect.gd] = rect.rid
        return grid

    @staticmethod
    def _build_rect_adjacency(rects: list[NavRect], rect_grid: np.ndarray, r: int) -> dict[int, list[int]]:
        adj = {rect.rid: [] for rect in rects}
        for rect in rects:
            rid = rect.rid
            if rect.gx > 0:
                for dz in range(rect.gd):
                    nid = rect_grid[rect.gx - 1, rect.gz + dz]
                    if nid >= 0 and nid not in adj[rid]:
                        adj[rid].append(nid)
            right = rect.gx + rect.gw
            if right < r:
                for dz in range(rect.gd):
                    nid = rect_grid[right, rect.gz + dz]
                    if nid >= 0 and nid not in adj[rid]:
                        adj[rid].append(nid)
            if rect.gz > 0:
                for dx in range(rect.gw):
                    nid = rect_grid[rect.gx + dx, rect.gz - 1]
                    if nid >= 0 and nid not in adj[rid]:
                        adj[rid].append(nid)
            bottom = rect.gz + rect.gd
            if bottom < r:
                for dx in range(rect.gw):
                    nid = rect_grid[rect.gx + dx, bottom]
                    if nid >= 0 and nid not in adj[rid]:
                        adj[rid].append(nid)
        return adj

    @staticmethod
    def _astar_rects(start_rid: int, end_rid: int, rects: list[NavRect],
                      adj: dict[int, list[int]]) -> Optional[list[int]]:
        if start_rid == end_rid:
            return [start_rid]

        def heur(a: int, b: int) -> float:
            ra, rb = rects[a], rects[b]
            return math.sqrt((ra.cx - rb.cx) ** 2 + (ra.cz - rb.cz) ** 2)

        open_heap = [(0.0, 0, start_rid)]
        g_scores = {start_rid: 0.0}
        came_from = {start_rid: None}

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            if current == end_rid:
                path = []
                while current is not None:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path

            for nid in adj.get(current, []):
                dx = rects[current].cx - rects[nid].cx
                dz = rects[current].cz - rects[nid].cz
                ng = g_scores[current] + math.sqrt(dx * dx + dz * dz) + 0.001
                if nid not in g_scores or ng < g_scores[nid]:
                    g_scores[nid] = ng
                    f_score = ng + heur(nid, end_rid)
                    heapq.heappush(open_heap, (f_score, id(rects[nid]), nid))
                    came_from[nid] = current

        return None

    @staticmethod
    def _rect_path_to_waypoints(rect_path: list[int], rects: list[NavRect],
                                 ground_gy: np.ndarray, grid: NavGrid,
                                 start_world: Vec3, end_world: Vec3) -> list[Vec3]:
        if not rect_path:
            return [end_world]

        cs = grid.cell_size
        hw = grid.half_world
        r = ground_gy.shape[0] if ground_gy is not None else 0

        def get_gy(gx: int, gz: int) -> int:
            if ground_gy is not None and 0 <= gx < r and 0 <= gz < r and ground_gy[gx, gz] >= 0:
                return int(ground_gy[gx, gz])
            return 0

        def grid_xz(world_x: float, world_z: float) -> tuple[int, int]:
            return int(round((world_x + hw) / cs)), int(round((world_z + hw) / cs))

        def world_pt(gx: float, gz: float) -> Vec3:
            return Vec3(-hw + gx * cs, 0, -hw + gz * cs)

        def portal_endpoint(gx: float, gz: float) -> Vec3:
            wp = world_pt(gx, gz)
            ix, iz = grid_xz(wp.x, wp.z)
            gy = get_gy(ix, iz)
            wp.y = -hw + (gy + 1) * cs
            return wp

        def cross_xz(a: Vec3, b: Vec3, c: Vec3) -> float:
            return (b.x - a.x) * (c.z - a.z) - (b.z - a.z) * (c.x - a.x)

        portals = []
        for i in range(len(rect_path) - 1):
            a = rects[rect_path[i]]
            b = rects[rect_path[i + 1]]
            ox1 = max(a.gx, b.gx)
            ox2 = min(a.gx + a.gw, b.gx + b.gw)
            oz1 = max(a.gz, b.gz)
            oz2 = min(a.gz + a.gd, b.gz + b.gd)
            if oz2 > oz1:
                portals.append((portal_endpoint(ox1, oz1), portal_endpoint(ox1, oz2)))
            else:
                portals.append((portal_endpoint(ox1, oz1), portal_endpoint(ox2, oz1)))

        if not portals:
            return [start_world, end_world]

        waypoints = [start_world]
        apex = start_world
        i = 0
        while i < len(portals):
            left, right = portals[i]
            if cross_xz(apex, left, right) > 0:
                left, right = right, left
            found = False
            for j in range(i + 1, len(portals)):
                pl, pr = portals[j]
                if cross_xz(apex, pl, pr) > 0:
                    pl, pr = pr, pl
                if cross_xz(apex, right, pl) < 0:
                    waypoints.append(right)
                    apex = right
                    i = j
                    found = True
                    break
                if cross_xz(apex, left, pr) > 0:
                    waypoints.append(left)
                    apex = left
                    i = j
                    found = True
                    break
                if cross_xz(apex, left, pl) > 0:
                    left = pl
                if cross_xz(apex, right, pr) < 0:
                    right = pr
            if not found:
                break
        waypoints.append(end_world)
        return waypoints

    def _navmesh_path_to_world(self, path_indices: list) -> list[Vec3]:
        res = self._grid.resolution
        waypoints = []
        for gx, gy, gz in path_indices:
            waypoints.append(self._grid.grid_to_world(gx, gy, gz))
        return waypoints

    def _over_budget(self) -> bool:
        return (time.perf_counter() - self._t0) > _TIME_BUDGET

    def _level_candidates(self, arr, ep: int, hc: int, cc: int):
        r = int(arr.shape[0])
        key = (int(ep), r, int(hc), int(cc))
        hit = _CANDS_SHARED.get(key)
        if hit is not None:
            return hit
        raw = np.ascontiguousarray(arr, dtype=np.uint8)
        cands = np.zeros((r, r, 4), dtype=np.int32)
        ncnt = np.zeros((r, r), dtype=np.uint8)
        _nb.collect_candidates(raw, int(hc + cc), cands, ncnt)
        hit = (cands, ncnt)
        try:
            _CANDS_SHARED[key] = hit
            while len(_CANDS_SHARED) > 4:
                _CANDS_SHARED.pop(next(iter(_CANDS_SHARED)))
        except Exception:
            pass
        return hit

    def _derived_fields(self, arr, ep: int, cell: float, hc: int, cc: int, slope: float, rad: int, climb: float,
                      sx: int = 0, sz: int = 0, ref_y: int = 0) -> Optional[dict]:
        r = int(arr.shape[0])
        key = (int(ep), r, int(hc), int(cc), round(float(slope), 3), int(rad),
               round(float(climb), 3), int(sx), int(sz), int(ref_y))
        f = _FIELDS_SHARED.get(key)
        if f is not None:
            return f
        climb_cells = max(0.0, float(climb)) / max(1e-6, float(cell))
        if 0 < slope < 90:
            max_hdiff = max(math.tan(math.radians(slope)), climb_cells)
        else:
            max_hdiff = 1e9
        try:
            cands, ncnt = self._level_candidates(arr, ep, hc, cc)
            walkable = np.zeros((r, r), dtype=np.uint8)
            ground = np.full((r, r), -1, dtype=np.int32)
            cost = np.ones((r, r), dtype=np.float32)
            ok = bool(_nb.flood_levels(cands, ncnt, int(sx), int(sz), int(ref_y),
                                       float(cell), float(climb), ground, walkable))
            if not ok:
                return None
            _nb.finalize_ground(ground, walkable, float(max_hdiff), float(cell), 0.15, 0.6, cost)
        except Exception:
            return None
        if rad > 0:
            dw = np.empty_like(walkable)
            _nb.dilate2d(walkable, int(rad), dw)
            walkable = dw
        labels = np.full((r, r), -1, dtype=np.int32)
        sizes = np.zeros(r * r, dtype=np.int32)
        ncomp = int(_nb.label_components(walkable, ground, float(cell),
                                         float(climb) if climb >= 0 else -1.0, labels, sizes))
        f = {"walk": walkable, "ground": ground, "cost": cost, "labels": labels, "ncomp": ncomp}
        try:
            _FIELDS_SHARED[key] = f
            while len(_FIELDS_SHARED) > 6:
                _FIELDS_SHARED.pop(next(iter(_FIELDS_SHARED)))
        except Exception:
            pass
        return f

    def _snap_g(self, walk: np.ndarray, gx: int, gz: int) -> tuple[int, int]:
        try:
            r = walk.shape[0]
            sx = max(0, min(r - 1, int(gx)))
            sz = max(0, min(r - 1, int(gz)))
            q = _nb.snap2d(np.ascontiguousarray(walk), sx, sz, 24)
            return (int(q[0]), int(q[1]))
        except Exception:
            return (int(gx), int(gz))

    def _astar_win(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, climb_cells: float,
                   s: tuple[int, int], e: tuple[int, int], margin: int, exp_cap: int):
        r = walk.shape[0]
        x0 = max(0, min(s[0], e[0]) - margin)
        x1 = min(r - 1, max(s[0], e[0]) + margin)
        z0 = max(0, min(s[1], e[1]) - margin)
        z1 = min(r - 1, max(s[1], e[1]) + margin)
        try:
            st, path, exp = _nb.astar2d(np.ascontiguousarray(walk), np.ascontiguousarray(cost, dtype=np.float32),
                                        np.ascontiguousarray(ground), int(s[0]), int(s[1]), int(e[0]), int(e[1]),
                                        int(exp_cap), float(climb_cells), int(x0), int(x1), int(z0), int(z1))
        except Exception:
            return None, False
        if len(path) <= 1:
            return None, False
        return [(int(p) // r, int(p) % r) for p in path], (st == 0)

    def _seg_ok(self, walk: np.ndarray, ground: np.ndarray, climb: float,
                a: tuple[int, int], b: tuple[int, int]) -> bool:
        try:
            ga = int(ground[a[0], a[1]])
            gb = int(ground[b[0], b[1]])
            if ga < 0 or gb < 0:
                return False
            return bool(_nb.segwalk2d(np.ascontiguousarray(walk), np.ascontiguousarray(ground),
                                      a[0] + 0.5, float(ga + 1), a[1] + 0.5,
                                      b[0] + 0.5, float(gb + 1), b[1] + 0.5, float(climb)))
        except Exception:
            return False

    def _smooth_cells(self, cells: list[tuple[int, int]], walk: np.ndarray, ground: np.ndarray,
                      climb: float):
        if len(cells) <= 1:
            return None
        try:
            n = len(cells)
            out = [0]
            i = 0
            while i < n - 1:
                j = n - 1
                while j > i and not self._seg_ok(walk, ground, climb, cells[i], cells[j]):
                    j -= 1
                if j == i:
                    break
                out.append(j)
                i = j
            if len(out) < 2:
                return None
            return [cells[k] for k in out]
        except Exception:
            return None

    def _coarsen_2d(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, f: int):
        r = walk.shape[0]
        cr = (r + f - 1) // f
        pr = cr * f
        if pr != r:
            walk_p = np.zeros((pr, pr), dtype=np.uint8)
            cost_p = np.ones((pr, pr), dtype=np.float32)
            ground_p = np.full((pr, pr), -1, dtype=np.int32)
            walk_p[:r, :r] = walk
            cost_p[:r, :r] = cost
            ground_p[:r, :r] = ground
        else:
            walk_p, cost_p, ground_p = walk, cost, ground
        cw = (walk_p.reshape(cr, f, cr, f).max(axis=(1, 3)) > 0).astype(np.uint8)
        cc = cost_p.reshape(cr, f, cr, f).min(axis=(1, 3)).astype(np.float32)
        gg = ground_p.reshape(cr, f, cr, f).max(axis=(1, 3)).astype(np.int32)
        return np.ascontiguousarray(cw), np.ascontiguousarray(cc), np.ascontiguousarray(gg), cr

    def _coarse_ground_cells(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, climb_cells: float,
                             s: tuple[int, int], e: tuple[int, int]):
        r = walk.shape[0]
        dx = abs(e[0] - s[0])
        dz = abs(e[1] - s[1])
        f = max(1, int(math.ceil(max(dx, dz) / _COARSE_TGT)))
        cw, cc, gg, cr = self._coarsen_2d(walk, cost, ground, f)
        cs = (max(0, min(cr - 1, s[0] // f)), max(0, min(cr - 1, s[1] // f)))
        ce = (max(0, min(cr - 1, e[0] // f)), max(0, min(cr - 1, e[1] // f)))
        try:
            qs = _nb.snap2d(cw, cs[0], cs[1], 8)
            qe = _nb.snap2d(cw, ce[0], ce[1], 8)
            cs = (int(qs[0]), int(qs[1]))
            ce = (int(qe[0]), int(qe[1]))
        except Exception:
            pass
        if not cw[cs[0], cs[1]] or not cw[ce[0], ce[1]]:
            return None, False
        try:
            st, path, exp = _nb.astar2d(cw, cc, gg, cs[0], cs[1], ce[0], ce[1],
                                        min(_MAX_EXP_2D, 6 * cr * cr + 4096), float(climb_cells),
                                        0, cr - 1, 0, cr - 1)
        except Exception:
            return None, False
        if len(path) <= 1:
            return None, False
        cok = (st == 0)
        pts = []
        for p in path:
            p = int(p)
            pts.append((max(0, min(r - 1, (p // cr) * f + f // 2)), max(0, min(r - 1, (p % cr) * f + f // 2))))
        anchors = [s]
        fine_pts = [self._snap_g(walk, p[0], p[1]) for p in pts]
        i = 0
        rok = True
        while i < len(fine_pts) - 1 and not self._over_budget():
            j = len(fine_pts) - 1
            moved = False
            while j > i:
                try:
                    if self._seg_ok(walk, ground, climb_cells, anchors[-1], fine_pts[j]):
                        anchors.append(fine_pts[j])
                        i = j
                        moved = True
                        break
                except Exception:
                    pass
                j -= 1
            if moved:
                continue
            seg, sok = self._astar_win(walk, cost, ground, climb_cells, anchors[-1], fine_pts[i + 1],
                                       _FINE_WIN // 2, 200000)
            if seg is not None and len(seg) > 1:
                anchors.extend(seg[1:])
                if not sok:
                    rok = False
                    break
            else:
                rok = False
                break
            i += 1
        sm = self._smooth_cells(anchors, walk, ground, climb_cells)
        if sm is None:
            return anchors, False
        return sm, (cok and rok)

    def _ground_cells(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, labels: np.ndarray,
                      climb_cells: float, s: tuple[int, int], e: tuple[int, int]) -> Optional[list[tuple[int, int]]]:
        r = walk.shape[0]
        if int(labels[s[0], s[1]]) < 0 or int(labels[s[0], s[1]]) != int(labels[e[0], e[1]]):
            return None
        try:
            if self._seg_ok(walk, ground, climb_cells, s, e):
                return [s, e]
        except Exception:
            pass
        dx = abs(e[0] - s[0])
        dz = abs(e[1] - s[1])
        margin = max(16, max(dx, dz) // 3 + 8)
        wcells = None
        if (dx + 2 * margin + 1) * (dz + 2 * margin + 1) <= _WIN_CAP * _WIN_CAP:
            wcells, wok = self._astar_win(walk, cost, ground, climb_cells, s, e, margin,
                                          min(_MAX_EXP_2D, 4 * (dx + 2 * margin + 1) * (dz + 2 * margin + 1) + 4096))
            if wcells is not None and wok:
                sm = self._smooth_cells(wcells, walk, ground, climb_cells)
                return sm if sm is not None else wcells
        ccells, cok = self._coarse_ground_cells(walk, cost, ground, climb_cells, s, e)
        if ccells is not None and cok:
            return ccells
        best = None
        best_d = 1e30
        if wcells is not None and len(wcells) > 1:
            best = wcells
            best_d = abs(wcells[-1][0] - e[0]) + abs(wcells[-1][1] - e[1])
        if ccells is not None and len(ccells) > 1:
            dd = abs(ccells[-1][0] - e[0]) + abs(ccells[-1][1] - e[1])
            if best is None or dd < best_d:
                best = ccells
        if best is not None:
            sm = self._smooth_cells(best, walk, ground, climb_cells)
            return sm if sm is not None else best
        return None

    def _proj_y(self, walk: np.ndarray, ground: np.ndarray, r: int,
                  x: float, y: float, z: float, climb_cells: float):
        try:
            gx = int(x + 1e-4)
            gz = int(z + 1e-4)
            if gx < 0 or gx >= r or gz < 0 or gz >= r:
                return None
            if not walk[gx, gz]:
                return None
            gy = int(ground[gx, gz])
            if gy < 0:
                return None
            if abs(y - float(gy + 1)) <= 0.5:
                return float(gy + 1)
            return y
        except Exception:
            return None

    def _segwalk_world(self, walk: np.ndarray, ground: np.ndarray, grid: "NavGrid",
                         climb_cells: float, a: Vec3, b: Vec3) -> bool:
        try:
            hw = grid.half_world
            cs = grid.cell_size
            r = walk.shape[0]
            ax, ay, az = (float(a.x) + hw) / cs, (float(a.y) + hw) / cs, (float(a.z) + hw) / cs
            bx, by, bz = (float(b.x) + hw) / cs, (float(b.y) + hw) / cs, (float(b.z) + hw) / cs
            wc = np.ascontiguousarray(walk)
            gc = np.ascontiguousarray(ground)
            pa = self._proj_y(wc, gc, r, ax, ay, az, float(climb_cells))
            pb = self._proj_y(wc, gc, r, bx, by, bz, float(climb_cells))
            if pa is None or pb is None:
                return False
            return bool(_nb.segwalk2d(wc, gc, ax, pa, az, bx, pb, bz, float(climb_cells)))
        except Exception:
            return False

    def _cells_to_world_ground(self, cells: list[tuple[int, int]], walk: np.ndarray, ground: np.ndarray,
                               climb_cells: float, grid: "NavGrid", snap_tol: float,
                               start_world: Vec3, end_world: Vec3) -> list[Vec3]:
        pts = [start_world]
        hw = grid.half_world
        cs = grid.cell_size
        for gx, gz in cells[1:-1]:
            gy = int(ground[gx, gz])
            if gy < 0:
                continue
            pts.append(Vec3(-hw + (gx + 0.5) * cs, -hw + (gy + 1) * cs, -hw + (gz + 0.5) * cs))
        if len(cells) >= 2:
            b = cells[-1]
            gy = int(ground[b[0], b[1]])
            if gy < 0:
                return pts
            surf_y = -hw + (gy + 1) * cs
            ok = self._segwalk_world(walk, ground, grid, climb_cells, pts[-1], end_world)
            if ok and abs(float(end_world.y) - surf_y) <= max(0.5, float(snap_tol)):
                pts.append(end_world)
            else:
                pts.append(Vec3(-hw + (b[0] + 0.5) * cs, surf_y, -hw + (b[1] + 0.5) * cs))
        else:
            pts.append(end_world)
        return pts

    def _store_cells(self, cells: list[tuple[int, int]], ground: np.ndarray):
        n = len(cells)
        step = max(1, n // 3000) if n > 3000 else 1
        self._raw_path_cells = [(c[0], int(ground[c[0], c[1]]), c[1]) for c in cells[::step]]
        self._path_cells = list(self._raw_path_cells)
        self._path_rects = []

    def _fly_cells(self, base: np.ndarray, r: int, s: tuple[int, int, int], e: tuple[int, int, int],
                   rad_world: float, cell: float, ep: int = 0) -> Optional[list[tuple[int, int, int]]]:
        frad = int(round(rad_world / cell)) if cell > 0 else 0
        if frad < 0:
            frad = 0
        try:
            if bool(_nb.los3d_clear(base, s[0], s[1], s[2], e[0], e[1], e[2], frad)):
                return [s, e]
        except Exception:
            pass
        if r <= _FLY_COARSE:
            try:
                work = base if frad <= 0 else _nb.dilate3d(base, frad)
                st, path, exp = _nb.astar3d(work, s[0], s[1], s[2], e[0], e[1], e[2],
                                            min(_MAX_EXP_3D, 4 * r * r * r + 4096),
                                            0, r - 1, 0, r - 1, 0, r - 1)
            except Exception:
                return None
            if len(path) <= 1:
                return None
            cells = [((int(p) // (r * r)), (int(p) - (int(p) // (r * r)) * r * r) // r, int(p) % r) for p in path]
            try:
                enc = np.array([(c[0] * r + c[1]) * r + c[2] for c in cells], dtype=np.int32)
                sm = _nb.smooth3d_clear(enc, len(enc), work, 0)
                cells = [((int(p) // (r * r)), (int(p) - (int(p) // (r * r)) * r * r) // r, int(p) % r) for p in sm]
            except Exception:
                pass
            return cells
        f = max(1, int(math.ceil(r / _FLY_COARSE)))
        dil = int(rad_world / (cell * f)) if cell * f > 0 else 0
        try:
            coarse = _coarse_cached(base, f, dil, ep, r)
        except Exception:
            return None
        if coarse is None:
            return None
        cr = coarse.shape[0]
        cs = (max(0, min(cr - 1, s[0] // f)), max(0, min(cr - 1, s[1] // f)), max(0, min(cr - 1, s[2] // f)))
        ce = (max(0, min(cr - 1, e[0] // f)), max(0, min(cr - 1, e[1] // f)), max(0, min(cr - 1, e[2] // f)))
        try:
            qs = _nb.nearest3d(coarse, cs[0], cs[1], cs[2], 8)
            qe = _nb.nearest3d(coarse, ce[0], ce[1], ce[2], 8)
            cs = (int(qs[0]), int(qs[1]), int(qs[2]))
            ce = (int(qe[0]), int(qe[1]), int(qe[2]))
        except Exception:
            pass
        if coarse[cs[0], cs[1], cs[2]] or coarse[ce[0], ce[1], ce[2]]:
            return None
        try:
            st, path, exp = _nb.astar3d(coarse, cs[0], cs[1], cs[2], ce[0], ce[1], ce[2],
                                        min(_MAX_EXP_3D, 6 * cr * cr * cr + 4096),
                                        0, cr - 1, 0, cr - 1, 0, cr - 1)
        except Exception:
            return None
        if len(path) <= 1:
            return None
        anchors = [s]
        for p in path:
            p = int(p)
            cx, cy, cz = p // (cr * cr), (p - (p // (cr * cr)) * cr * cr) // cr, p % cr
            fx, fy, fz = max(0, min(r - 1, cx * f + f // 2)), max(0, min(r - 1, cy * f + f // 2)), max(0, min(r - 1, cz * f + f // 2))
            try:
                q = _nb.nearest3d(base, fx, fy, fz, f + 2)
                anchors.append((int(q[0]), int(q[1]), int(q[2])))
            except Exception:
                anchors.append((fx, fy, fz))
        out = [s]
        i = 0
        while i < len(anchors) - 1 and not self._over_budget():
            j = len(anchors) - 1
            moved = False
            while j > i:
                try:
                    if bool(_nb.los3d_clear(base, out[-1][0], out[-1][1], out[-1][2], anchors[j][0], anchors[j][1], anchors[j][2], frad)):
                        out.append(anchors[j])
                        i = j
                        moved = True
                        break
                except Exception:
                    pass
                j -= 1
            if moved:
                continue
            seg, sok = self._fly_win(base, r, out[-1], anchors[i + 1], frad)
            if seg is not None and len(seg) > 1:
                out.extend(seg[1:])
                if not sok:
                    break
            else:
                break
            i += 1
        try:
            enc = np.array([(c[0] * r + c[1]) * r + c[2] for c in out], dtype=np.int32)
            sm = _nb.smooth3d_clear(enc, len(enc), base, frad)
            out = [((int(p) // (r * r)), (int(p) - (int(p) // (r * r)) * r * r) // r, int(p) % r) for p in sm]
        except Exception:
            pass
        return out

    def _fly_win(self, base: np.ndarray, r: int, s: tuple[int, int, int], e: tuple[int, int, int],
                 frad: int = 0):
        m = _FINE_3D_WIN // 2
        pts = [s, e]
        depth = 0
        while depth < 6:
            a, b = pts[0], pts[-1]
            spans = [abs(b[0] - a[0]), abs(b[1] - a[1]), abs(b[2] - a[2])]
            if max(spans) <= _FINE_3D_WIN:
                break
            mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2, (a[2] + b[2]) // 2)
            try:
                q = _nb.nearest3d(base, mid[0], mid[1], mid[2], 6)
                mid = (int(q[0]), int(q[1]), int(q[2]))
            except Exception:
                pass
            pts = [a, mid, b] if len(pts) == 2 else pts[:1] + [mid] + pts[1:]
            if len(pts) > 8:
                break
            depth += 1
        result = [pts[0]]
        for k in range(1, len(pts)):
            a, b = result[-1], pts[k]
            lo = [max(0, min(a[0], b[0]) - m), max(0, min(a[1], b[1]) - m), max(0, min(a[2], b[2]) - m)]
            hi = [min(r - 1, max(a[0], b[0]) + m), min(r - 1, max(a[1], b[1]) + m), min(r - 1, max(a[2], b[2]) + m)]
            side = max(hi[0] - lo[0] + 1, hi[1] - lo[1] + 1, hi[2] - lo[2] + 1)
            side = max(2, min(side, r))
            org = []
            for ax in range(3):
                span = hi[ax] - lo[ax] + 1
                s0 = lo[ax] - (side - span) // 2
                s0 = max(0, min(s0, r - side))
                org.append(s0)
            try:
                win = np.ascontiguousarray(base[org[0]:org[0] + side, org[1]:org[1] + side, org[2]:org[2] + side])
                if frad > 0:
                    win = _nb.dilate3d(win, min(frad, 2))
                la = (a[0] - org[0], a[1] - org[1], a[2] - org[2])
                lb = (b[0] - org[0], b[1] - org[1], b[2] - org[2])
                st, path, exp = _nb.astar3d(win, la[0], la[1], la[2], lb[0], lb[1], lb[2], 400000,
                                            0, side - 1, 0, side - 1, 0, side - 1)
            except Exception:
                return (result if len(result) > 1 else None), False
            if len(path) <= 1:
                return (result if len(result) > 1 else None), False
            for p in path[1:]:
                p = int(p)
                qx = p // (side * side)
                qy = (p - qx * side * side) // side
                qz = p - qx * side * side - qy * side
                result.append((qx + org[0], qy + org[1], qz + org[2]))
            if st != 0:
                return result, False
        return result, True

    def _find_path_fast_ground(self, start_world: Vec3, end_world: Vec3,
                               agent_radius: float, agent_height: float,
                               max_climb: float, max_slope: float,
                               agent_padding: Optional[float], arr=None, ep=None) -> Optional[list[Vec3]]:
        grid = self._grid
        r = grid.resolution
        sx, sy, sz = grid.world_to_grid(start_world)
        ex, ey, ez = grid.world_to_grid(end_world)
        self._path_cells = []
        self._raw_path_cells = []
        self._path_aabbs.clear()
        self._path_rects = []
        self._is_flying = False
        padding = agent_padding if agent_padding is not None else agent_radius
        hc = int(math.ceil(max(0.01, agent_height) / grid.cell_size))
        cc = int(math.ceil(max(0.0, max_climb) / grid.cell_size))
        rad = int(max(0.0, padding) / grid.cell_size + 0.5)
        ref_y = max(0, min(r - 1, sy))
        if arr is None or ep is None:
            try:
                arr, ep = _grid_snapshot(grid)
            except Exception:
                arr, ep = grid._grid, _current_epoch()
        try:
            F = self._derived_fields(arr, ep, grid.cell_size, hc, cc, max_slope, rad, max_climb, sx, sz, ref_y)
        except Exception:
            return None
        if F is None:
            return None
        walk, ground, cost, labels = F["walk"], F["ground"], F["cost"], F["labels"]
        self._los_walk = walk
        self._los_ground = ground
        try:
            self._los_climb = max(0.0, float(max_climb)) / max(1e-6, float(grid.cell_size))
        except Exception:
            self._los_climb = 0.0
        try:
            self._los_walk_gid = id(arr)
        except Exception:
            self._los_walk_gid = None
        s = self._snap_g(walk, sx, sz)
        e = self._snap_g(walk, ex, ez)
        if not walk[s[0], s[1]] or not walk[e[0], e[1]]:
            return None
        if int(labels[s[0], s[1]]) != int(labels[e[0], e[1]]):
            return None
        if s == e:
            self._path_cells = [(s[0], sy, s[1])]
            self._raw_path_cells = [(s[0], sy, s[1])]
            return [start_world, end_world]
        climb_cells = max_climb / grid.cell_size
        try:
            cells = self._ground_cells(walk, cost, ground, labels, climb_cells, s, e)
        except Exception:
            return None
        if not cells or self._over_budget():
            return None
        pts = self._cells_to_world_ground(cells, walk, ground, climb_cells, grid,
                                          agent_height + max_climb + grid.cell_size, start_world, end_world)
        self._store_cells(cells, ground)
        self._build_path_aabbs()
        return pts

    def _find_path_fast_fly(self, start_world: Vec3, end_world: Vec3, agent_radius: float,
                            arr=None, ep=None) -> Optional[list[Vec3]]:
        grid = self._grid
        r = grid.resolution
        sx, sy, sz = grid.world_to_grid(start_world)
        ex, ey, ez = grid.world_to_grid(end_world)
        self._path_cells = []
        self._raw_path_cells = []
        self._path_aabbs.clear()
        self._path_rects = []
        self._is_flying = True
        if arr is None or ep is None:
            try:
                arr, ep = _grid_snapshot(grid)
            except Exception:
                arr, ep = grid._grid, _current_epoch()
        base = np.ascontiguousarray(arr)
        self._los_base = base
        try:
            self._los_fly_rad = max(0, int(round(max(0.0, float(agent_radius)) / float(grid.cell_size))))
        except Exception:
            self._los_fly_rad = 0
        try:
            self._los_base_gid = id(arr)
        except Exception:
            self._los_base_gid = None
        try:
            qs = _nb.nearest3d(base, sx, sy, sz, 16)
            qe = _nb.nearest3d(base, ex, ey, ez, 16)
            s = (int(qs[0]), int(qs[1]), int(qs[2]))
            e = (int(qe[0]), int(qe[1]), int(qe[2]))
        except Exception:
            return None
        if base[s[0], s[1], s[2]] or base[e[0], e[1], e[2]]:
            return None
        if s == e:
            self._path_cells = [s]
            self._raw_path_cells = [s]
            return [start_world, end_world]
        rad_w = self._fly_dilate if self._fly_dilate is not None else agent_radius
        try:
            cells = self._fly_cells(base, r, s, e, max(0.0, float(rad_w)), float(grid.cell_size), ep)
        except Exception:
            return None
        if not cells or self._over_budget():
            return None
        pts = [start_world]
        for cx, cy, cz in cells[1:-1]:
            pts.append(grid.grid_to_world(cx, cy, cz))
        pts.append(end_world)
        n = len(cells)
        step = max(1, n // 3000) if n > 3000 else 1
        self._raw_path_cells = [cells[i] for i in range(0, n, step)]
        self._path_cells = list(self._raw_path_cells)
        self._build_path_aabbs()
        return pts

    def find_path(self, start_world: Vec3, end_world: Vec3,
                  agent_radius: float = 0.5, agent_height: float = 2.0,
                  flying: bool = False,
                  max_climb: float = 0.5, max_slope: float = 45.0,
                  agent_padding: Optional[float] = None) -> Optional[list[Vec3]]:
        grid = self._grid
        self._t0 = time.perf_counter()
        if _HAS_NAV_CYTHON:
            try:
                if flying:
                    return self._find_path_fast_fly(start_world, end_world, agent_radius)
                return self._find_path_fast_ground(start_world, end_world, agent_radius, agent_height,
                                                   max_climb, max_slope, agent_padding)
            except Exception:
                pass
        return self._find_path_legacy(start_world, end_world, agent_radius, agent_height,
                                      flying, max_climb, max_slope, agent_padding)

    def _find_path_legacy(self, start_world: Vec3, end_world: Vec3,
                  agent_radius: float = 0.5, agent_height: float = 2.0,
                  flying: bool = False,
                  max_climb: float = 0.5, max_slope: float = 45.0,
                  agent_padding: Optional[float] = None) -> Optional[list[Vec3]]:
        grid = self._grid
        sx, sy, sz = grid.world_to_grid(start_world)
        ex, ey, ez = grid.world_to_grid(end_world)
        self._path_cells = []
        self._raw_path_cells = []
        self._path_aabbs.clear()
        self._path_rects = []
        self._is_flying = flying

        padding = agent_padding if agent_padding is not None else agent_radius

        if flying:
            sx, sy, sz = grid.find_nearest_unblocked(sx, sy, sz)
            ex, ey, ez = grid.find_nearest_unblocked(ex, ey, ez)
            path_cells = self._astar(sx, sy, sz, ex, ey, ez, True)
            if not path_cells:
                return None
            self._raw_path_cells = path_cells
            self._path_cells = path_cells
            waypoints = self._navmesh_path_to_world(path_cells)
            self._build_path_aabbs()
            return waypoints

        hc = int(math.ceil(agent_height / grid.cell_size))
        cc = int(math.ceil(max_climb / grid.cell_size))
        radius_cells = int(math.ceil(padding / grid.cell_size))
        walkable_2d, ground_gy, walk_gy = grid.build_ground_obstacle_grid(hc, cc, max_slope, sx, sy, sz)
        walkable_2d = NavGrid._dilate_2d(walkable_2d, radius_cells)
        walkable_2d = self._flood_fill_ground(walkable_2d, ground_gy, sx, sz, max_climb, grid.cell_size, grid.half_world)

        if self._has_line_of_sight_2d(walkable_2d, sx, sz, ex, ez):
            try:
                if _HAS_NAV_CYTHON:
                    ccells = max(0.0, float(max_climb)) / max(1e-6, float(grid.cell_size))
                    if not bool(_nb.los2d_climb(np.ascontiguousarray(walkable_2d, dtype=np.uint8),
                                                np.ascontiguousarray(ground_gy), sx, sz, ex, ez, float(ccells))):
                        raise ValueError
            except ValueError:
                pass
            else:
                self._path_cells = [(sx, sy, sz), (ex, ey, ez)]
                self._raw_path_cells = [(sx, sy, sz), (ex, ey, ez)]
                return [start_world, end_world]

        rects = self._decompose_walkable(walkable_2d, ground_gy)
        if not rects:
            return None
        rect_grid = self._build_rect_grid(rects, grid.resolution)
        adj = self._build_rect_adjacency(rects, rect_grid, grid.resolution)

        def find_rect(gx: int, gz: int) -> Optional[int]:
            if 0 <= gx < grid.resolution and 0 <= gz < grid.resolution:
                rid = rect_grid[gx, gz]
                if rid >= 0:
                    return int(rid)
            for radius in range(1, min(grid.resolution, 21)):
                for dx in range(-radius, radius + 1):
                    for dz in (-radius, radius):
                        ngx, ngz = gx + dx, gz + dz
                        if 0 <= ngx < grid.resolution and 0 <= ngz < grid.resolution:
                            rid = rect_grid[ngx, ngz]
                            if rid >= 0:
                                return int(rid)
                for dz in range(-radius + 1, radius):
                    for dx in (-radius, radius):
                        ngx, ngz = gx + dx, gz + dz
                        if 0 <= ngx < grid.resolution and 0 <= ngz < grid.resolution:
                            rid = rect_grid[ngx, ngz]
                            if rid >= 0:
                                return int(rid)
            return None

        start_rid = find_rect(sx, sz)
        end_rid = find_rect(ex, ez)
        if start_rid is None or end_rid is None:
            return None

        rect_path = self._astar_rects(start_rid, end_rid, rects, adj)
        if not rect_path:
            return None

        self._path_rects = [rects[rid] for rid in rect_path]
        self._build_path_aabbs()

        waypoints = self._rect_path_to_waypoints(rect_path, rects, ground_gy, grid, start_world, end_world)
        waypoints = self._simplify_path_los(waypoints, walkable_2d, grid)

        for rid in rect_path:
            rct = rects[rid]
            self._path_cells.append((rct.gx, max(0, rct.ground_gy), rct.gz))

        return waypoints

    @staticmethod
    def _has_line_of_sight_2d(walkable: np.ndarray, sx: int, sz: int, ex: int, ez: int) -> bool:
        res = walkable.shape[0]
        if not (0 <= sx < res and 0 <= sz < res and 0 <= ex < res and 0 <= ez < res):
            return False
        dx = ex - sx
        dz = ez - sz
        if dx == 0 and dz == 0:
            return bool(walkable[sx, sz])
        step_x = 1 if dx > 0 else -1
        step_z = 1 if dz > 0 else -1
        t_delta_x = 1.0 / abs(dx) if dx != 0 else float('inf')
        t_delta_z = 1.0 / abs(dz) if dz != 0 else float('inf')
        t_max_x = 0.5 * t_delta_x if dx != 0 else float('inf')
        t_max_z = 0.5 * t_delta_z if dz != 0 else float('inf')
        gx, gz = sx, sz
        while True:
            if not (0 <= gx < res and 0 <= gz < res) or not walkable[gx, gz]:
                return False
            if gx == ex and gz == ez:
                return True
            if t_max_x < t_max_z:
                gx += step_x
                t_max_x += t_delta_x
            elif t_max_z < t_max_x:
                gz += step_z
                t_max_z += t_delta_z
            else:
                gx += step_x
                t_max_x += t_delta_x

    @staticmethod
    def _flood_fill_ground(walkable: np.ndarray, ground_gy: np.ndarray,
                            start_gx: int, start_gz: int,
                            max_climb: float, cell_size: float, half_world: float) -> np.ndarray:
        r = ground_gy.shape[0]
        if not (0 <= start_gx < r and 0 <= start_gz < r) or ground_gy[start_gx, start_gz] < 0:
            return np.zeros((r, r), dtype=np.uint32)
        ground_y = -half_world + (ground_gy + 1) * cell_size
        result = np.zeros((r, r), dtype=np.uint32)
        from collections import deque
        q = deque()
        q.append((start_gx, start_gz))
        result[start_gx, start_gz] = 1
        while q:
            gx, gz = q.popleft()
            h0 = ground_y[gx, gz]
            for dx, dz in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, nz = gx + dx, gz + dz
                if 0 <= nx < r and 0 <= nz < r and result[nx, nz] == 0:
                    if ground_gy[nx, nz] >= 0 and walkable[nx, nz]:
                        h1 = ground_y[nx, nz]
                        if h1 > h0 and h1 - h0 > max_climb:
                            continue
                        result[nx, nz] = 1
                        q.append((nx, nz))
        return result

    def _simplify_path_los(self, waypoints: list[Vec3], walkable: np.ndarray, grid: "NavGrid") -> list[Vec3]:
        if len(waypoints) <= 2:
            return waypoints

        def to_grid(p: Vec3) -> tuple[int, int]:
            gx, _, gz = grid.world_to_grid(p)
            return gx, gz

        res = [waypoints[0]]
        for i in range(1, len(waypoints)):
            lx, lz = to_grid(res[-1])
            nx, nz = to_grid(waypoints[i])
            if not self._has_line_of_sight_2d(walkable, lx, lz, nx, nz):
                prev = waypoints[i - 1]
                if prev != res[-1]:
                    res.append(prev)
        res.append(waypoints[-1])
        return res

    def find_path_gpu(self, start_world: Vec3, end_world: Vec3,
                      agent_radius: float = 0.5, agent_height: float = 2.0,
                      flying: bool = False,
                      max_climb: float = 0.5, max_slope: float = 45.0,
                      agent_padding: Optional[float] = None) -> Optional[list[Vec3]]:
        return self.find_path(start_world, end_world, agent_radius, agent_height,
                              flying, max_climb, max_slope, agent_padding)

    @staticmethod
    def _backtrack(dist: np.ndarray, res: int, start_idx: int, end_idx: int) -> Optional[list[int]]:
        if dist[end_idx] == 0xFFFFFFFF:
            return None
        path = [end_idx]
        current = end_idx
        while current != start_idx:
            gz = current // (res * res)
            gy = (current - gz * res * res) // res
            gx = current - gz * res * res - gy * res
            best_n = -1
            best_d = dist[current]
            for dx, dy, dz in _NEIGHBOR_OFFSETS_3D:
                nx, ny, nz = gx + dx, gy + dy, gz + dz
                if nx < 0 or nx >= res or ny < 0 or ny >= res or nz < 0 or nz >= res:
                    continue
                nidx = nx + ny * res + nz * res * res
                d = dist[nidx]
                if d < best_d:
                    best_d = d
                    best_n = nidx
            if best_n < 0:
                if current == end_idx:
                    return [start_idx, end_idx]
                return None
            path.append(best_n)
            current = best_n
        path.reverse()
        return path

    def release(self):
        NavWorld._instance = None
