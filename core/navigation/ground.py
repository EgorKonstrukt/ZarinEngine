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
_WIN_CAP = 336
_COARSE_TGT = 224
_FINE_WIN = 112
_MAX_EXP_2D = 800000
_MAX_EXP_3D = 900000
_FLY_COARSE = 80
_FINE_3D_WIN = 56
_TIME_BUDGET = 1.5


class GroundMixin:
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
