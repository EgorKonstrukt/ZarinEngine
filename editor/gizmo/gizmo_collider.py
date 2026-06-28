from __future__ import annotations
from typing import Optional
from collections import OrderedDict
import json
import math
import os
import numpy as np
from core.math3d import Vec3
from core.components.physics.mesh_collider import CollisionMode
from core.engine import Engine


def quat_to_mat3(rot) -> np.ndarray:
    x, y, z, w = rot.x, rot.y, rot.z, rot.w
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n > 1e-10:
        inv = 1.0 / n; x *= inv; y *= inv; z *= inv; w *= inv
    return np.array([
        [1-2*y*y-2*z*z, 2*x*y+2*w*z, 2*x*z-2*w*y],
        [2*x*y-2*w*z, 1-2*x*x-2*z*z, 2*y*z+2*w*x],
        [2*x*z+2*w*y, 2*y*z-2*w*x, 1-2*x*x-2*y*y],
    ], dtype=np.float32)


_SENTINEL = object()

class _LRU:
    def __init__(self, maxsize: int = 512):
        self._data: OrderedDict = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key not in self._data:
            return _SENTINEL
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key, value):
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def __contains__(self, key):
        return key in self._data


_mesh_data = _LRU(256)
_decimated_hull_cache_np = _LRU(128)
_convex_hull_cache_np = _LRU(128)
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "../.."))


def _resolve_mesh_path(path: str) -> Optional[str]:
    if not path:
        return None
    if os.path.exists(path):
        return path
    if os.path.isabs(path):
        eng = Engine.instance()
        root = eng.project_root if eng and eng.project_root else _PROJECT_ROOT
        if path[1:2] == ":":
            parts = path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(c):
                        return c.replace("\\", "/")
        return path if os.path.exists(path) else None
    resolved = os.path.normpath(os.path.join(_PROJECT_ROOT, path))
    if os.path.exists(resolved):
        return resolved
    return None


def _load_mesh_data(path: str) -> Optional[dict]:
    resolved = _resolve_mesh_path(path)
    if not resolved:
        return None
    cache_key = resolved.lower()
    cached = _mesh_data.get(cache_key)
    if cached is not _SENTINEL:
        return cached

    from core.renderer.mesh_loader import MeshLoader
    if cache_key in MeshLoader._shared_import_cache:
        data = MeshLoader._shared_import_cache[cache_key]
    else:
        try:
            from core.asset_importer import load_mesh_future
            fut = load_mesh_future(resolved)
            data = fut.result(timeout=0.01)
        except Exception:
            return None

    scale = 1.0
    import_path = resolved + ".import"
    if os.path.exists(import_path):
        try:
            with open(import_path) as f:
                settings = json.load(f)
            scale = settings.get("scale", 1.0)
        except Exception:
            pass

    if data is None or len(data.vertices) == 0:
        result = {"verts": np.empty((0, 3), dtype=np.float32), "edges": [], "num_verts": 0}
        _mesh_data.set(cache_key, result)
        return result

    verts = data.vertices.reshape(-1, 3)
    if scale != 1.0:
        verts = verts * scale

    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    center = verts.mean(axis=0)
    radius = float(np.max(np.linalg.norm(verts - center, axis=1)))

    if len(data.indices) == 0:
        result = {
            "verts": verts, "edges": [], "edge_verts_np": np.empty((0, 2, 3), dtype=np.float32),
            "mins": mins, "maxs": maxs,
            "num_verts": len(verts),
            "center": center, "radius": radius,
        }
        _mesh_data.set(cache_key, result)
        return result

    idxs = data.indices
    edges_set: set[tuple[int, int]] = set()
    for i in range(0, len(idxs), 3):
        if i + 2 >= len(idxs):
            break
        a, b, c = int(idxs[i]), int(idxs[i + 1]), int(idxs[i + 2])
        for ia, ib in ((a, b), (b, c), (c, a)):
            if ia < ib:
                edges_set.add((ia, ib))
            else:
                edges_set.add((ib, ia))

    edges: list[tuple[Vec3, Vec3]] = []
    edge_indices = np.array(list(edges_set), dtype=np.int32)
    edge_verts_np = verts[edge_indices]
    for ia, ib in edges_set:
        r0 = verts[ia]
        r1 = verts[ib]
        edges.append((Vec3(float(r0[0]), float(r0[1]), float(r0[2])),
                      Vec3(float(r1[0]), float(r1[1]), float(r1[2]))))

    result = {
        "verts": verts, "edges": edges, "edge_verts_np": edge_verts_np,
        "mins": mins, "maxs": maxs,
        "num_verts": len(verts),
        "center": center, "radius": radius,
    }
    _mesh_data.set(cache_key, result)
    return result


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


def _compute_hull_edges_np(verts: np.ndarray) -> Optional[np.ndarray]:
    try:
        from core.convex_hull import convex_hull_simplices
        simplices = convex_hull_simplices(verts)
        if len(simplices) == 0:
            return None
        edges_set: set[tuple[int, int]] = set()
        for simplex in simplices:
            a, b, c = int(simplex[0]), int(simplex[1]), int(simplex[2])
            for ia, ib in ((a, b), (b, c), (c, a)):
                edges_set.add((ia, ib) if ia < ib else (ib, ia))
        if not edges_set:
            return None
        edge_indices = np.array(list(edges_set), dtype=np.int32)
        return verts[edge_indices]
    except Exception:
        return None


def _get_convex_hull_edges_np(path: str) -> Optional[np.ndarray]:
    cache_key = path.lower().replace("\\", "/")
    cached = _convex_hull_cache_np.get(cache_key)
    if cached is not _SENTINEL:
        return cached
    md = _load_mesh_data(path)
    if md is None or md["num_verts"] == 0:
        return None
    result = _compute_hull_edges_np(md["verts"])
    _convex_hull_cache_np.set(cache_key, result)
    return result


def _get_decimated_hull_edges_np(path: str, max_verts: int) -> Optional[np.ndarray]:
    cache_key = (path.lower().replace("\\", "/"), max_verts)
    cached = _decimated_hull_cache_np.get(cache_key)
    if cached is not _SENTINEL:
        return cached
    try:
        md = _load_mesh_data(path)
        if md is None or md["num_verts"] == 0:
            return None
        verts = md["verts"]
        if len(verts) <= max_verts:
            return None
        dv = _decimate_verts(verts, max_verts)
        if len(dv) < 3:
            _decimated_hull_cache_np.set(cache_key, None)
            return None
        result = _compute_hull_edges_np(dv)
        _decimated_hull_cache_np.set(cache_key, result)
        return result
    except Exception:
        _decimated_hull_cache_np.set(cache_key, None)
        return None
