# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import heapq
import math
import threading
import time
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3
try:
    from core import _nav_batch as _nb
    _HAS_NAV_CYTHON = True
except ImportError:
    _nb = None
    _HAS_NAV_CYTHON = False
from .stats import _stat
from .grid import NavRect
_NEIGHBOR_OFFSETS_3D = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
_NEIGHBOR_OFFSETS_2D = [(1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]
_TIME_BUDGET = 1.5
_CANDS_SHARED: dict = {}


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

def _snap_g(self, walk: np.ndarray, gx: int, gz: int) -> tuple[int, int]:
    try:
        r = walk.shape[0]
        sx = max(0, min(r - 1, int(gx)))
        sz = max(0, min(r - 1, int(gz)))
        q = _nb.snap2d(np.ascontiguousarray(walk), sx, sz, 24)
        return (int(q[0]), int(q[1]))
    except Exception:
        return (int(gx), int(gz))

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