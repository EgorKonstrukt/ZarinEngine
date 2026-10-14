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
from .ground import _WIN_CAP, _COARSE_TGT, _FINE_WIN, _MAX_EXP_2D, _MAX_EXP_3D, _FLY_COARSE, _FINE_3D_WIN, _TIME_BUDGET
_FIELDS_SHARED: dict = {}


class GroundMixin2:
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

    def _derived_fields(self, arr, ep: int, cell: float, hc: int, cc: int, slope: float, rad: int, climb: float,
                      sx: int = 0, sz: int = 0, ref_y: int = 0) -> Optional[dict]:
        r = int(arr.shape[0])
        key = (int(ep), r, int(hc), int(cc), round(float(slope), 3), int(rad),
               round(float(climb), 3), int(sx), int(sz), int(ref_y))
        f = _FIELDS_SHARED.get(key)
        if f is not None:
            return f
        _ft0 = time.perf_counter()
        try:
            return self._derived_fields_build(arr, ep, cell, hc, cc, slope, rad, climb,
                                              sx, sz, ref_y, key)
        finally:
            try:
                _stat("fields_build", (time.perf_counter() - _ft0) * 1000.0)
            except Exception:
                pass

    def _derived_fields_build(self, arr, ep: int, cell: float, hc: int, cc: int, slope: float, rad: int,
                              climb: float, sx: int, sz: int, ref_y: int, key) -> Optional[dict]:
        r = int(arr.shape[0])
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
