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
from .ground import GroundMixin
from .ground2 import GroundMixin2
from .rebuild import RebuildMixin
from .rebuild2 import RebuildMixin2
from .rebuild3 import RebuildMixin3
from .rebuild4 import RebuildMixin4
from .world2 import WorldPathMixin
from . import path as _path_mod


class NavWorld(GroundMixin, GroundMixin2, RebuildMixin, RebuildMixin2, RebuildMixin3, RebuildMixin4, WorldPathMixin):
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

    @_timed("deferred")
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
            self._submit_or_hold(spec)
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

    @_timed("poll")
    def poll_result(self, req_id: str) -> Optional[list[Vec3]]:
        try:
            self._poll_rebuild(self._grid)
        except Exception:
            pass
        try:
            self._drive_rebuild_pump()
        except Exception:
            pass
        try:
            self._release_held_paths(self._grid)
        except Exception:
            pass
        try:
            r = _get_nav_worker().take(req_id)
            if r is not None:
                gid, payload = r
                slot = self._pending_jobs.pop(req_id, None)
                try:
                    _sh = self._grid
                    prebuild = ((not _sh._built_once) and gid == id(_sh._grid)
                                and (_sh._rb_job is not None or _sh._rebuild_req is not None))
                except Exception:
                    prebuild = False
                if payload is not None and not prebuild and (slot is None or gid == id(self._grid._grid)):
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
                            self._submit_or_hold(spec2)
                        except Exception:
                            pass
                        return None
                return []
        except Exception:
            pass
        return self._pending_results.pop(req_id, None)

    @_timed("los")
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
            try:
                _tbx, _tby, _tbz = grid.world_to_grid(b)
            except Exception:
                _tbx = _tby = _tbz = 0
            try:
                _seed = (int(_tbx), int(_tby), int(_tbz))
            except Exception:
                _seed = (0, 0, 0)
            if walk is None or self._los_walk_gid != id(grid._grid) or getattr(self, "_los_seed", None) != _seed:
                gp = getattr(self, "_guard_params", None)
                if gp is None or len(gp) < 8 or not _HAS_NAV_CYTHON:
                    return True
                try:
                    arr0, ep0 = _grid_snapshot(grid)
                    F = self._derived_fields(arr0, ep0, grid.cell_size, gp[0], gp[1], gp[2], gp[3], gp[4],
                                             _seed[0], _seed[2], _seed[1])
                except Exception:
                    return True
                if F is None:
                    return True
                walk = F["walk"]
                self._los_walk = walk
                self._los_ground = F["ground"]
                self._los_seed = _seed
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

    def get_path_cell_aabbs(self) -> list[AABB]:
        result = []
        for rct in self._path_rects:
            result.append(rct.world_aabb(self._grid))
        return result

    def get_path_rects(self) -> list[NavRect]:
        return list(self._path_rects)

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

    def find_path_gpu(self, start_world: Vec3, end_world: Vec3,
                      agent_radius: float = 0.5, agent_height: float = 2.0,
                      flying: bool = False,
                      max_climb: float = 0.5, max_slope: float = 45.0,
                      agent_padding: Optional[float] = None) -> Optional[list[Vec3]]:
        return self.find_path(start_world, end_world, agent_radius, agent_height,
                              flying, max_climb, max_slope, agent_padding)

    def release(self):
        NavWorld._instance = None
