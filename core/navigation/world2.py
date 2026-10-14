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
from . import path as _path_mod


class WorldPathMixin:
    def _heuristic(self, ax: int, ay: int, az: int, bx: int, by: int, bz: int) -> float:
        return _path_mod._heuristic(self, ax, ay, az, bx, by, bz)

    def _astar(self, sx: int, sy: int, sz: int, ex: int, ey: int, ez: int, flying: bool) -> Optional[list[tuple[int, int, int]]]:
        return _path_mod._astar(self, sx, sy, sz, ex, ey, ez, flying)

    def _astar_2d(self, sx: int, sz: int, ex: int, ez: int,
                  walkable_2d: np.ndarray) -> Optional[list[tuple[int, int, int]]]:
        return _path_mod._astar_2d(self, sx, sz, ex, ez, walkable_2d)

    @staticmethod
    def _astar_rects(start_rid: int, end_rid: int, rects: list[NavRect],
                      adj: dict[int, list[int]]) -> Optional[list[int]]:
        return _path_mod._astar_rects(start_rid, end_rid, rects, adj)

    @staticmethod
    def _backtrack(dist: np.ndarray, res: int, start_idx: int, end_idx: int) -> Optional[list[int]]:
        return _path_mod._backtrack(dist, res, start_idx, end_idx)

    def _over_budget(self) -> bool:
        return _path_mod._over_budget(self)

    def _level_candidates(self, arr, ep: int, hc: int, cc: int):
        return _path_mod._level_candidates(self, arr, ep, hc, cc)

    def _snap_g(self, walk: np.ndarray, gx: int, gz: int) -> tuple[int, int]:
        return _path_mod._snap_g(self, walk, gx, gz)

    def _astar_win(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, climb_cells: float,
                   s: tuple[int, int], e: tuple[int, int], margin: int, exp_cap: int):
        return _path_mod._astar_win(self, walk, cost, ground, climb_cells, s, e, margin, exp_cap)

    def _seg_ok(self, walk: np.ndarray, ground: np.ndarray, climb: float,
                a: tuple[int, int], b: tuple[int, int]) -> bool:
        return _path_mod._seg_ok(self, walk, ground, climb, a, b)

    def _smooth_cells(self, cells: list[tuple[int, int]], walk: np.ndarray, ground: np.ndarray,
                      climb: float):
        return _path_mod._smooth_cells(self, cells, walk, ground, climb)

    def _coarsen_2d(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, f: int):
        return _path_mod._coarsen_2d(self, walk, cost, ground, f)
