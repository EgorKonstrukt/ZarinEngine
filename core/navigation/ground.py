# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3


def _coarse_ground_cells(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, climb_cells: float,
                         s: tuple[int, int], e: tuple[int, int]):
    from .nav_world import NavWorld as _O
    return _O._coarse_ground_cells(self, walk, cost, ground, climb_cells, s, e)

def _ground_cells(self, walk: np.ndarray, cost: np.ndarray, ground: np.ndarray, labels: np.ndarray,
                  climb_cells: float, s: tuple[int, int], e: tuple[int, int]) -> Optional[list[tuple[int, int]]]:
    from .nav_world import NavWorld as _O
    return _O._ground_cells(self, walk, cost, ground, labels, climb_cells, s, e)

def _proj_y(self, walk: np.ndarray, ground: np.ndarray, r: int,
              x: float, y: float, z: float, climb_cells: float):
    from .nav_world import NavWorld as _O
    return _O._proj_y(self, walk, ground, r, x, y, z, climb_cells)

def _segwalk_world(self, walk: np.ndarray, ground: np.ndarray, grid: "NavGrid",
                     climb_cells: float, a: Vec3, b: Vec3) -> bool:
    from .nav_world import NavWorld as _O
    return _O._segwalk_world(self, walk, ground, grid, climb_cells, a, b)

def _cells_to_world_ground(self, cells: list[tuple[int, int]], walk: np.ndarray, ground: np.ndarray,
                           climb_cells: float, grid: "NavGrid", snap_tol: float,
                           start_world: Vec3, end_world: Vec3) -> list[Vec3]:
    from .nav_world import NavWorld as _O
    return _O._cells_to_world_ground(self, cells, walk, ground, climb_cells, grid, snap_tol, start_world, end_world)

def _fly_cells(self, base: np.ndarray, r: int, s: tuple[int, int, int], e: tuple[int, int, int],
               rad_world: float, cell: float, ep: int = 0) -> Optional[list[tuple[int, int, int]]]:
    from .nav_world import NavWorld as _O
    return _O._fly_cells(self, base, r, s, e, rad_world, cell, ep)

def _fly_win(self, base: np.ndarray, r: int, s: tuple[int, int, int], e: tuple[int, int, int],
             frad: int = 0):
    from .nav_world import NavWorld as _O
    return _O._fly_win(self, base, r, s, e, frad)

def _find_path_fast_ground(self, start_world: Vec3, end_world: Vec3,
                           agent_radius: float, agent_height: float,
                           max_climb: float, max_slope: float,
                           agent_padding: Optional[float], arr=None, ep=None) -> Optional[list[Vec3]]:
    from .nav_world import NavWorld as _O
    return _O._find_path_fast_ground(self, start_world, end_world, agent_radius, agent_height, max_climb, max_slope, agent_padding, arr, ep)

def _find_path_fast_fly(self, start_world: Vec3, end_world: Vec3, agent_radius: float,
                        arr=None, ep=None) -> Optional[list[Vec3]]:
    from .nav_world import NavWorld as _O
    return _O._find_path_fast_fly(self, start_world, end_world, agent_radius, arr, ep)

@staticmethod
def _decompose_walkable(walkable: np.ndarray, ground_gy: np.ndarray) -> list[NavRect]:
    from .nav_world import NavWorld as _O
    return _O._decompose_walkable(walkable, ground_gy)

@staticmethod
def _build_rect_grid(rects: list[NavRect], r: int) -> np.ndarray:
    from .nav_world import NavWorld as _O
    return _O._build_rect_grid(rects, r)

@staticmethod
def _build_rect_adjacency(rects: list[NavRect], rect_grid: np.ndarray, r: int) -> dict[int, list[int]]:
    from .nav_world import NavWorld as _O
    return _O._build_rect_adjacency(rects, rect_grid, r)

@staticmethod
def _rect_path_to_waypoints(rect_path: list[int], rects: list[NavRect],
                             ground_gy: np.ndarray, grid: NavGrid,
                             start_world: Vec3, end_world: Vec3) -> list[Vec3]:
    from .nav_world import NavWorld as _O
    return _O._rect_path_to_waypoints(rect_path, rects, ground_gy, grid, start_world, end_world)

def _navmesh_path_to_world(self, path_indices: list) -> list[Vec3]:
    from .nav_world import NavWorld as _O
    return _O._navmesh_path_to_world(self, path_indices)

@staticmethod
def _flood_fill_ground(walkable: np.ndarray, ground_gy: np.ndarray,
                        start_gx: int, start_gz: int,
                        max_climb: float, cell_size: float, half_world: float) -> np.ndarray:
    from .nav_world import NavWorld as _O
    return _O._flood_fill_ground(walkable, ground_gy, start_gx, start_gz, max_climb, cell_size, half_world)