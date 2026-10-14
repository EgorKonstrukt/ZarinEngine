# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import math
import numpy as np
import os
from typing import Optional
from .cache import _SENTINEL, _mesh_data, _decimated_hull_cache_np, _convex_hull_cache_np, _PROJECT_ROOT


def _resolve_mesh_path(path: str) -> Optional[str]:
    if not path:
        return None
    if os.path.exists(path):
        return path
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        project_root = eng.project_root if eng and getattr(eng, "project_root", None) else ""
    except Exception:
        project_root = ""
    if os.path.isabs(path):
        if project_root and path[1:2] == ":":
            parts = path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(project_root, sub))
                    if os.path.exists(c):
                        return c.replace("\\", "/")
        return path if os.path.exists(path) else None
    candidates = []
    if project_root:
        candidates.append(os.path.normpath(os.path.join(project_root, path)))
    candidates.append(os.path.normpath(os.path.join(os.getcwd(), path)))
    candidates.append(os.path.normpath(os.path.join(_PROJECT_ROOT, path)))
    base = os.path.basename(path)
    for root in ([project_root] if project_root else []):
        for sub in ("", "assets/", "assets/models/", "models/"):
            candidates.append(os.path.normpath(os.path.join(root, sub, path)))
            if base != path:
                candidates.append(os.path.normpath(os.path.join(root, sub, base)))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _load_mesh_data(path: str) -> Optional[dict]:
    resolved = _resolve_mesh_path(path)
    if not resolved:
        return None
    try:
        from core.assets.importer import _import_meta_signature
        sig = _import_meta_signature(resolved)
    except Exception:
        sig = None
    cache_key = resolved.lower() + "|" + (sig[1] if sig else "-")
    cached = _mesh_data.get(cache_key)
    if cached is not _SENTINEL:
        return cached
    try:
        from core.assets.importer import load_mesh, load_obj
        lower_path = resolved.lower()
        if lower_path.endswith(".obj"):
            data = load_obj(resolved)
        else:
            data = load_mesh(resolved)
    except Exception:
        return None
    scale = 1.0
    center_pivot = False
    from core.assets.importer import _resolve_mesh_import_path
    import_path = _resolve_mesh_import_path(resolved)
    if os.path.exists(import_path):
        try:
            with open(import_path) as f:
                settings = json.load(f)
            scale = settings.get("scale", 1.0)
            center_pivot = bool(settings.get("center_pivot", False))
        except Exception:
            pass
    if data is None or len(data.vertices) == 0:
        result = {"verts": np.empty((0, 3), dtype=np.float32), "edges": [], "num_verts": 0, "indices": None, "import_scale": scale,
                  "mins": np.zeros(3, dtype=np.float32), "maxs": np.zeros(3, dtype=np.float32),
                  "center": np.zeros(3, dtype=np.float32), "radius": 0.0}
        _mesh_data.set(cache_key, result)
        return result
    verts = data.vertices.reshape(-1, 3).astype(np.float32)
    if scale != 1.0:
        verts = verts * scale
    if center_pivot and len(verts) > 0:
        try:
            mean = verts.mean(axis=0)
            if np.all(np.isfinite(mean)):
                verts = verts - mean
        except Exception:
            pass
    try:
        raw_idx = np.asarray(data.indices)
        indices = np.ascontiguousarray(raw_idx.reshape(-1).astype(np.int64)) if raw_idx.size >= 3 else None
    except Exception:
        indices = None
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    center = verts.mean(axis=0)
    radius = float(np.max(np.linalg.norm(verts - center, axis=1)))
    if len(data.indices) == 0:
        result = {"verts": verts,
                  "mins": mins, "maxs": maxs, "num_verts": len(verts), "center": center, "radius": radius,
                  "indices": indices, "import_scale": scale}
        _mesh_data.set(cache_key, result)
        return result
    result = {"verts": verts,
              "mins": mins, "maxs": maxs, "num_verts": len(verts), "center": center, "radius": radius,
              "indices": indices, "import_scale": scale}
    _mesh_data.set(cache_key, result)
    return result


def _decimate_verts(verts: np.ndarray, max_vertices: int) -> np.ndarray:
    n = len(verts)
    if n <= max_vertices or max_vertices < 1:
        return verts
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    extent = np.where(maxs - mins < 1e-8, 1.0, maxs - mins)
    cell_vol = extent.prod() / max_vertices
    cell_size = cell_vol ** (1.0 / 3.0)
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
        from core.maths.convex_hull import convex_hull_simplices
        simplices = convex_hull_simplices(verts)
        if len(simplices) == 0:
            return None
        edges_set = set()
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


def _import_sig_of(path: str) -> str:
    try:
        from core.assets.importer import _import_meta_signature, _resolve_mesh_import_path
        resolved = _resolve_mesh_path(path)
        if resolved:
            sig = _import_meta_signature(resolved)
            if sig:
                return sig[1]
            ip = _resolve_mesh_import_path(resolved)
            if not os.path.exists(ip):
                return "-"
    except Exception:
        pass
    return "-"


def load_collision_geometry(path: str) -> tuple[Optional[np.ndarray], Optional[np.ndarray], float]:
    try:
        md = _load_mesh_data(path)
    except Exception:
        return None, None, 1.0
    if md is None or md.get("num_verts", 0) == 0:
        return None, None, 1.0
    try:
        k = float(md.get("import_scale", 1.0) or 1.0)
    except Exception:
        k = 1.0
    if abs(k) < 1e-9:
        k = 1.0
    try:
        verts = np.ascontiguousarray(md["verts"].reshape(-1, 3), dtype=np.float32)
    except Exception:
        return None, None, k
    indices = md.get("indices")
    try:
        if indices is not None:
            raw = np.asarray(indices)
            indices = np.ascontiguousarray(raw.reshape(-1).astype(np.int64)) if raw.size >= 3 else None
        else:
            indices = None
    except Exception:
        indices = None
    return verts, indices, k


def _get_convex_hull_edges_np(path: str) -> Optional[np.ndarray]:
    cache_key = (path.lower().replace("\\", "/"), _import_sig_of(path))
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
    cache_key = (path.lower().replace("\\", "/"), max_verts, _import_sig_of(path))
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


def _triangle_edges_np(verts: np.ndarray, indices: np.ndarray, max_tris: int = 15000) -> Optional[np.ndarray]:
    try:
        tris = np.asarray(indices).reshape(-1, 3)
        if len(tris) == 0:
            return None
        n = len(verts)
        tris = tris[((tris >= 0) & (tris < n)).all(axis=1)]
        if len(tris) == 0:
            return None
        if len(tris) > max_tris:
            tris = tris[::int(np.ceil(len(tris) / max_tris))]
        pairs = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
        return np.ascontiguousarray(verts[pairs].astype(np.float32))
    except Exception:
        return None


def _box_edges_np(mins: np.ndarray, maxs: np.ndarray) -> np.ndarray:
    x0, y0, z0 = float(mins[0]), float(mins[1]), float(mins[2])
    x1, y1, z1 = float(maxs[0]), float(maxs[1]), float(maxs[2])
    corners = np.array([
        [x0, y0, z0], [x1, y0, z0], [x0, y1, z0], [x1, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x0, y1, z1], [x1, y1, z1],
    ], dtype=np.float32)
    pairs = np.array([
        [0, 1], [1, 3], [3, 2], [2, 0],
        [4, 5], [5, 7], [7, 6], [6, 4],
        [0, 4], [1, 5], [2, 6], [3, 7],
    ], dtype=np.int64)
    return np.ascontiguousarray(corners[pairs])


def _sphere_edges_np(center: np.ndarray, radius: float, segments: int = 24) -> np.ndarray:
    r = max(float(radius), 1e-6)
    t = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False, dtype=np.float32)
    c = np.cos(t) * r
    s = np.sin(t) * r
    z = np.zeros_like(t)
    rings = [
        np.stack([center[0] + c, center[1] + z, center[2] + s], axis=1),
        np.stack([center[0] + c, center[1] + s, center[2] + z], axis=1),
        np.stack([center[0] + z, center[1] + s, center[2] + c], axis=1),
    ]
    out = []
    for ring in rings:
        out.append(np.stack([ring, np.roll(ring, -1, axis=0)], axis=1))
    return np.ascontiguousarray(np.concatenate(out, axis=0).astype(np.float32))


def _edge_pairs_np(edge_verts_np: np.ndarray, color: list, pos, rot, sc):
    q = rot
    x, y, z, w = q.x, q.y, q.z, q.w
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n > 1e-10:
        inv = 1.0/n; x *= inv; y *= inv; z *= inv; w *= inv
    R = np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                   [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                   [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]], dtype=np.float32)
    T = np.array([pos.x, pos.y, pos.z], dtype=np.float32)
    S = np.array([sc.x, sc.y, sc.z], dtype=np.float32)
    n_edges = edge_verts_np.shape[0]
    verts = edge_verts_np.reshape(-1, 3)
    transformed = verts * S @ R.T + T
    starts = transformed[0::2].reshape(n_edges, 3)
    ends = transformed[1::2].reshape(n_edges, 3)
    c_arr = np.empty((n_edges, 4), dtype=np.float32)
    c_arr[:] = color
    return starts, ends, c_arr
