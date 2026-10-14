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
from core.spatial.octree import AABB
from .grid import NavGrid, NavRect
from .stats import _stat, _timed
from .epoch import _bump_epoch, _current_epoch, _grid_snapshot, _GRID_LOCK
from . import path as _path_mod
from . import ground as _ground_mod
from . import rebuild as _rebuild_mod


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
        self._los_seed = None
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
        from .nav_world import NavWorld as _O
        return _O.find_path_gpu_deferred(self, start_world, end_world, agent_radius, agent_height, flying, max_climb, max_slope, agent_padding)

    def _submit_or_hold(self, spec):
        from .nav_world import NavWorld as _O
        return _O._submit_or_hold(self, spec)

    def _release_held_paths(self, grid) -> bool:
        from .nav_world import NavWorld as _O
        return _O._release_held_paths(self, grid)

    def poll_result(self, req_id: str) -> Optional[list[Vec3]]:
        from .nav_world import NavWorld as _O
        return _O.poll_result(self, req_id)

    def has_los(self, a: Vec3, b: Vec3, flying: bool) -> bool:
        from .nav_world import NavWorld as _O
        return _O.has_los(self, a, b, flying)

    def get_path_cells(self) -> list[tuple[int, int, int]]:
        from .nav_world import NavWorld as _O
        return _O.get_path_cells(self)

    def _build_path_aabbs(self):
        from .nav_world import NavWorld as _O
        return _O._build_path_aabbs(self)

    def get_path_aabbs(self) -> list[tuple[AABB, int]]:
        from .nav_world import NavWorld as _O
        return _O.get_path_aabbs(self)

    def set_scene(self, scene):
        from .nav_world import NavWorld as _O
        return _O.set_scene(self, scene)

    def get_path_cell_aabbs(self) -> list[AABB]:
        from .nav_world import NavWorld as _O
        return _O.get_path_cell_aabbs(self)

    def get_path_rects(self) -> list[NavRect]:
        from .nav_world import NavWorld as _O
        return _O.get_path_rects(self)

    def find_path(self, start_world: Vec3, end_world: Vec3,
                  agent_radius: float = 0.5, agent_height: float = 2.0,
                  flying: bool = False,
                  max_climb: float = 0.5, max_slope: float = 45.0,
                  agent_padding: Optional[float] = None) -> Optional[list[Vec3]]:
        from .nav_world import NavWorld as _O
        return _O.find_path(self, start_world, end_world, agent_radius, agent_height, flying, max_climb, max_slope, agent_padding)

    def _find_path_legacy(self, start_world: Vec3, end_world: Vec3,
                  agent_radius: float = 0.5, agent_height: float = 2.0,
                  flying: bool = False,
                  max_climb: float = 0.5, max_slope: float = 45.0,
                  agent_padding: Optional[float] = None) -> Optional[list[Vec3]]:
        from .nav_world import NavWorld as _O
        return _O._find_path_legacy(self, start_world, end_world, agent_radius, agent_height, flying, max_climb, max_slope, agent_padding)

    @staticmethod
    def _has_line_of_sight_2d(walkable: np.ndarray, sx: int, sz: int, ex: int, ez: int) -> bool:
        from .nav_world import NavWorld as _O
        return _O._has_line_of_sight_2d(walkable, sx, sz, ex, ez)

    def _simplify_path_los(self, waypoints: list[Vec3], walkable: np.ndarray, grid: "NavGrid") -> list[Vec3]:
        from .nav_world import NavWorld as _O
        return _O._simplify_path_los(self, waypoints, walkable, grid)

    def find_path_gpu(self, start_world: Vec3, end_world: Vec3,
                      agent_radius: float = 0.5, agent_height: float = 2.0,
                      flying: bool = False,
                      max_climb: float = 0.5, max_slope: float = 45.0,
                      agent_padding: Optional[float] = None) -> Optional[list[Vec3]]:
        from .nav_world import NavWorld as _O
        return _O.find_path_gpu(self, start_world, end_world, agent_radius, agent_height, flying, max_climb, max_slope, agent_padding)

    def _derived_fields(self, arr, ep: int, cell: float, hc: int, cc: int, slope: float, rad: int, climb: float,
                      sx: int = 0, sz: int = 0, ref_y: int = 0) -> Optional[dict]:
        from .nav_world import NavWorld as _O
        return _O._derived_fields(self, arr, ep, cell, hc, cc, slope, rad, climb, sx, sz, ref_y)

    def _derived_fields_build(self, arr, ep: int, cell: float, hc: int, cc: int, slope: float, rad: int,
                              climb: float, sx: int, sz: int, ref_y: int, key) -> Optional[dict]:
        from .nav_world import NavWorld as _O
        return _O._derived_fields_build(self, arr, ep, cell, hc, cc, slope, rad, climb, sx, sz, ref_y, key)

    def _store_cells(self, cells: list[tuple[int, int]], ground: np.ndarray):
        from .nav_world import NavWorld as _O
        return _O._store_cells(self, cells, ground)

    def release(self):
        from .nav_world import NavWorld as _O
        return _O.release(self)
