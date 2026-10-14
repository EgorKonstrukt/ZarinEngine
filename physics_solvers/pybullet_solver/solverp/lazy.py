# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
import numpy as np

class _LazyPybullet:
    _p = None
    _data = None

    def __getattr__(self, name):
        if self._p is None:
            import pybullet
            self._p = pybullet
        return getattr(self._p, name)

p = _LazyPybullet()

def _pybullet_data_path() -> str:
    if _LazyPybullet._data is None:
        import pybullet_data
        _LazyPybullet._data = pybullet_data
    return _LazyPybullet._data.getDataPath() if _LazyPybullet._data else ""

def _decimate_verts(verts: np.ndarray, max_vertices: int) -> np.ndarray:
    n = len(verts)
    if n <= max_vertices or max_vertices < 1:
        return verts
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    extent = maxs - mins
    extent = np.where(extent < 1e-8, 1.0, extent)
    target_cell_vol = extent.prod() / max_vertices
    cell_size = target_cell_vol ** (1.0 / 3.0)
    grid_res = np.maximum(1, np.ceil(extent / cell_size).astype(np.int32))
    indices = np.floor((verts - mins) / extent * grid_res).astype(np.int32)
    indices = np.clip(indices, 0, grid_res - 1)
    cell_ids = indices[:, 0] * grid_res[1] * grid_res[2] + indices[:, 1] * grid_res[2] + indices[:, 2]
    unique_ids, inverse = np.unique(cell_ids, return_inverse=True)
    centroids = np.zeros((len(unique_ids), 3), dtype=np.float32)
    np.add.at(centroids, inverse, verts)
    counts = np.bincount(inverse, minlength=len(unique_ids)).astype(np.float32)
    centroids /= counts[:, None]
    return centroids

def _load_mesh_verts(path: str) -> Optional[np.ndarray]:
    verts, _ = _load_mesh_geometry(path)
    return verts

def _load_mesh_geometry(path: str) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    try:
        from core.components.physics.meshcol import load_collision_geometry
        verts, indices, _ = load_collision_geometry(path)
        if verts is not None and len(verts) > 0:
            return verts, indices
    except Exception:
        pass
    return None, None

def _load_mesh_tscale(path: str) -> tuple[Optional[np.ndarray], Optional[np.ndarray], float]:
    try:
        from core.components.physics.meshcol import load_collision_geometry
        verts, indices, k = load_collision_geometry(path)
        if verts is not None and len(verts) > 0:
            return verts, indices, k
    except Exception:
        pass
    return None, None, 1.0

def _transform_scale(params_scale, import_scale: float) -> tuple[float, float, float]:
    try:
        k = float(import_scale or 1.0)
    except Exception:
        k = 1.0
    if abs(k) < 1e-9:
        k = 1.0
    try:
        return (float(params_scale[0]) / k, float(params_scale[1]) / k, float(params_scale[2]) / k)
    except Exception:
        return (1.0, 1.0, 1.0)

def _convex_hull_shape(cid: int, points: np.ndarray, max_vertices: int, cache: dict, cache_key: tuple) -> int:
    pts = points
    if len(pts) > 1:
        try:
            pts = np.unique(np.ascontiguousarray(pts, dtype=np.float32), axis=0)
        except Exception:
            pass
    if max_vertices >= 4 and len(pts) > max_vertices:
        pts = _decimate_verts(pts, max_vertices)
    if len(pts) < 4:
        return -1
    try:
        shape_id = p.createCollisionShape(
            p.GEOM_MESH, vertices=pts.tolist(), physicsClientId=cid,
        )
        cache[cache_key] = shape_id
        return shape_id
    except Exception:
        return -1

class _QueryMixin:
    def ray_cast(
        self,
        origin: tuple[float, float, float],
        direction: tuple[float, float, float],
        max_distance: float = 100.0,
    ) -> Optional[dict]:
        cid = self._cid()
        dx, dy, dz = direction
        mag = (dx * dx + dy * dy + dz * dz) ** 0.5
        if mag < 1e-10:
            return None
        norm_dir = (dx / mag, dy / mag, dz / mag)
        to_pos = (
            origin[0] + norm_dir[0] * max_distance,
            origin[1] + norm_dir[1] * max_distance,
            origin[2] + norm_dir[2] * max_distance,
        )
        result = p.rayTest(origin, to_pos, physicsClientId=cid)
        if result:
            hit_fraction = result[0][2]
            if hit_fraction < 1.0:
                hit_pos = result[0][3]
                return {
                    "body_id": result[0][0],
                    "position": (hit_pos[0], hit_pos[1], hit_pos[2]),
                    "fraction": hit_fraction,
                    "normal": (result[0][4][0], result[0][4][1], result[0][4][2]),
                }
        return None

    def get_collision_events(self) -> list[dict]:
        cid = self._cid()
        points = p.getContactPoints(physicsClientId=cid)
        events = []
        for pt in points:
            events.append(
                {
                    "body_a": pt[1],
                    "body_b": pt[2],
                    "position": (pt[5][0], pt[5][1], pt[5][2]),
                    "normal": (pt[6][0], pt[6][1], pt[6][2]),
                    "distance": pt[7],
                    "force": pt[8],
                }
            )
        return events
