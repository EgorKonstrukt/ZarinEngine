from __future__ import annotations
import json
import math
import os
import numpy as np
from typing import Optional
from core.math3d import Vec3

_mesh_data: dict[str, dict] = {}
_decimated_hull_cache: dict[tuple[str, int], Optional[list]] = {}
_convex_hull_cache: dict[str, Optional[list]] = {}

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_mesh_path(path: str) -> Optional[str]:
    if not path:
        return None
    if os.path.isabs(path):
        resolved = path
    else:
        resolved = os.path.normpath(os.path.join(_PROJECT_ROOT, path))
    if os.path.exists(resolved):
        return resolved
    return None


def _load_mesh_data(path: str) -> Optional[dict]:
    resolved = _resolve_mesh_path(path)
    if not resolved:
        return None
    cache_key = resolved.lower()
    if cache_key in _mesh_data:
        return _mesh_data[cache_key]

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
        _mesh_data[cache_key] = {"verts": np.empty((0, 3), dtype=np.float32), "edges": [], "num_verts": 0}
        return _mesh_data[cache_key]

    verts = data.vertices.reshape(-1, 3)
    if scale != 1.0:
        verts = verts * scale

    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    center = verts.mean(axis=0)
    radius = float(np.max(np.linalg.norm(verts - center, axis=1)))

    if len(data.indices) == 0:
        result = {
            "verts": verts, "edges": [],
            "mins": mins, "maxs": maxs,
            "num_verts": len(verts),
            "center": center, "radius": radius,
        }
        _mesh_data[cache_key] = result
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
    for ia, ib in edges_set:
        r0 = verts[ia]
        r1 = verts[ib]
        edges.append((Vec3(float(r0[0]), float(r0[1]), float(r0[2])),
                      Vec3(float(r1[0]), float(r1[1]), float(r1[2]))))

    result = {
        "verts": verts, "edges": edges,
        "mins": mins, "maxs": maxs,
        "num_verts": len(verts),
        "center": center, "radius": radius,
    }
    _mesh_data[cache_key] = result
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


def _compute_hull_edges_from_verts(verts: np.ndarray) -> Optional[list]:
    try:
        from scipy.spatial import ConvexHull
        hull = ConvexHull(verts)
        edges_set: set[tuple[int, int]] = set()
        for simplex in hull.simplices:
            a, b, c = int(simplex[0]), int(simplex[1]), int(simplex[2])
            for ia, ib in ((a, b), (b, c), (c, a)):
                edges_set.add((ia, ib) if ia < ib else (ib, ia))
        edges: list[tuple[Vec3, Vec3]] = []
        for ia, ib in edges_set:
            r0 = verts[ia]
            r1 = verts[ib]
            edges.append((Vec3(float(r0[0]), float(r0[1]), float(r0[2])),
                          Vec3(float(r1[0]), float(r1[1]), float(r1[2]))))
        return edges
    except Exception:
        return None


def _get_convex_hull_edges(path: str) -> Optional[list]:
    cache_key = path.lower().replace("\\", "/")
    if cache_key in _convex_hull_cache:
        return _convex_hull_cache[cache_key]
    md = _load_mesh_data(path)
    if md is None or md["num_verts"] == 0:
        return None
    result = _compute_hull_edges_from_verts(md["verts"])
    _convex_hull_cache[cache_key] = result
    return result


def _get_decimated_hull_edges(path: str, max_verts: int) -> Optional[list]:
    cache_key = (path.lower().replace("\\", "/"), max_verts)
    if cache_key in _decimated_hull_cache:
        return _decimated_hull_cache[cache_key]
    try:
        md = _load_mesh_data(path)
        if md is None or md["num_verts"] == 0:
            return None
        verts = md["verts"]
        if len(verts) <= max_verts:
            return None
        dv = _decimate_verts(verts, max_verts)
        if len(dv) < 3:
            _decimated_hull_cache[cache_key] = None
            return None
        result = _compute_hull_edges_from_verts(dv)
        _decimated_hull_cache[cache_key] = result
        return result
    except Exception:
        _decimated_hull_cache[cache_key] = None
        return None
