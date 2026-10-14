# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import threading
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3
from core.spatial.octp import AABB
try:
    from core import _nav_batch as _nb
    _HAS_NAV_CYTHON = True
except ImportError:
    _nb = None
    _HAS_NAV_CYTHON = False


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
        self._raster_pending = None
        self._raster_pending_seq = 0
        self._raster_pending_t = 0.0
        self._held_paths: list = []
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