# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import numpy as np
from collections import OrderedDict
from typing import Optional


_MAX_CELLS = 12000000
_MERGE_CAP = 65536
_CACHE_SIZE = 8

try:
    from core._gs_volume import splat_occupancy as _cython_occupancy
    from core._gs_volume import dilate26 as _cython_dilate
    from core._gs_volume import greedy_merge_boxes as _cython_merge
except Exception:
    _cython_occupancy = None
    _cython_dilate = None
    _cython_merge = None


_VOLUME_CACHE: OrderedDict = OrderedDict()


def _volume_cache_get(key):
    entry = _VOLUME_CACHE.get(key)
    if entry is None:
        return None
    _VOLUME_CACHE.move_to_end(key)
    return entry


def _volume_cache_set(key, value):
    _VOLUME_CACHE[key] = value
    _VOLUME_CACHE.move_to_end(key)
    while len(_VOLUME_CACHE) > _CACHE_SIZE:
        _VOLUME_CACHE.popitem(last=False)


def _resolve_ply_path(path: str) -> Optional[str]:
    if not path:
        return None
    if os.path.isfile(path) or os.path.isdir(path):
        return os.path.abspath(path)
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        root = eng.project_root if eng and getattr(eng, "project_root", None) else os.getcwd()
    except Exception:
        root = os.getcwd()
    base = os.path.basename(path)
    for cand in (os.path.join(root, path), os.path.join(root, "assets", base), os.path.join(root, "assets", path)):
        if os.path.isfile(cand) or os.path.isdir(cand):
            return os.path.abspath(cand)
    return None


def _file_sig(resolved: str):
    try:
        st = os.stat(resolved)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return (0, 0)


def _build_volume_boxes(resolved: str, voxel: float, thr: float, dilation: int, max_boxes: int):
    try:
        from core.renderer.splat import try_get_splat_arrays
        shared = try_get_splat_arrays(resolved)
    except Exception:
        shared = None
    if shared is not None:
        try:
            pos = np.ascontiguousarray(shared[0], dtype=np.float32)
            scl = np.ascontiguousarray(shared[1], dtype=np.float32)
            opa = np.ascontiguousarray(shared[2], dtype=np.float32).reshape(-1)
            return _boxes_from_arrays(pos, scl, opa, voxel, thr, dilation, max_boxes)
        except Exception:
            pass
    try:
        from core.assets.sog import load_gaussian_splat as _load_any
        data = _load_any(resolved)
    except Exception:
        data = None
    if data is None:
        try:
            from core.assets.ply_loader import load_ply_gaussian_splat
            data = load_ply_gaussian_splat(resolved)
        except Exception:
            data = None
    if data is None or data.num_splats == 0:
        return np.zeros((0, 6), dtype=np.float32)
    try:
        pos = np.ascontiguousarray(data.positions, dtype=np.float32)
        scl = np.ascontiguousarray(data.scales, dtype=np.float32)
        opa = np.ascontiguousarray(data.opacity.reshape(-1), dtype=np.float32)
    except Exception:
        return np.zeros((0, 6), dtype=np.float32)
    return _boxes_from_arrays(pos, scl, opa, voxel, thr, dilation, max_boxes)


def _boxes_from_arrays(pos, scl, opa, voxel: float, thr: float, dilation: int, max_boxes: int):
    try:
        keep = np.isfinite(pos).all(axis=1) & np.isfinite(scl).all(axis=1) & (opa >= np.float32(thr))
    except Exception:
        return np.zeros((0, 6), dtype=np.float32)
    if not bool(keep.any()):
        return np.zeros((0, 6), dtype=np.float32)
    pts = pos[keep]
    try:
        mins = pts.min(axis=0).astype(np.float64)
        maxs = pts.max(axis=0).astype(np.float64)
    except Exception:
        return np.zeros((0, 6), dtype=np.float32)
    if not bool(np.isfinite(mins).all() and np.isfinite(maxs).all()):
        return np.zeros((0, 6), dtype=np.float32)
    vx = float(voxel)
    for _ in range(5):
        pad = (int(dilation) + 1) * vx
        origin = mins - pad
        dims = np.ceil((maxs - origin) / vx).astype(np.int64)
        dims = np.maximum(dims, 1)
        if int(dims.prod()) <= _MAX_CELLS:
            break
        vx *= 2.0
    for _ in range(4):
        origin = mins - (int(dilation) + 1) * vx
        dims = np.maximum(np.ceil((maxs - origin) / vx).astype(np.int64), 1)
        nx, ny, nz = int(dims[0]), int(dims[1]), int(dims[2])
        if nx * ny * nz > _MAX_CELLS:
            vx *= 2.0
            continue
        occ = np.zeros(nx * ny * nz, dtype=np.uint8)
        try:
            _cython_occupancy(
                np.ascontiguousarray(pos, dtype=np.float32),
                np.ascontiguousarray(scl, dtype=np.float32),
                np.ascontiguousarray(opa, dtype=np.float32),
                np.float32(thr), np.float32(vx), 2.0,
                float(origin[0]), float(origin[1]), float(origin[2]),
                nx, ny, nz, occ,
            )
        except Exception:
            return np.zeros((0, 6), dtype=np.float32)
        if int(occ.sum()) == 0:
            return np.zeros((0, 6), dtype=np.float32)
        cur = occ
        for _ in range(int(dilation)):
            nxt = np.zeros_like(cur)
            try:
                _cython_dilate(cur, nxt, nx, ny, nz)
            except Exception:
                break
            cur = nxt
        mask = np.zeros(nx * ny * nz, dtype=np.uint8)
        out = np.empty((_MERGE_CAP, 6), dtype=np.float32)
        try:
            cnt = int(_cython_merge(cur, nx, ny, nz, mask, out, _MERGE_CAP))
        except Exception:
            return np.zeros((0, 6), dtype=np.float32)
        if cnt < 0:
            vx *= 2.0
            continue
        if cnt == 0:
            return np.zeros((0, 6), dtype=np.float32)
        if cnt > int(max_boxes):
            vx *= 2.0
            continue
        cells = out[:cnt].copy()
        boxes = np.empty((cnt, 6), dtype=np.float32)
        boxes[:, 0] = origin[0] + cells[:, 0] * vx
        boxes[:, 1] = origin[1] + cells[:, 1] * vx
        boxes[:, 2] = origin[2] + cells[:, 2] * vx
        boxes[:, 3] = origin[0] + (cells[:, 3] + 1.0) * vx
        boxes[:, 4] = origin[1] + (cells[:, 4] + 1.0) * vx
        boxes[:, 5] = origin[2] + (cells[:, 5] + 1.0) * vx
        return np.ascontiguousarray(boxes)
    return np.zeros((0, 6), dtype=np.float32)


def get_volume_boxes(ply_path: str, voxel: float, thr: float, dilation: int, max_boxes: int):
    resolved = _resolve_ply_path(ply_path)
    if resolved is None:
        return np.zeros((0, 6), dtype=np.float32)
    key = (resolved, _file_sig(resolved), float(voxel), float(thr), int(dilation), int(max_boxes))
    cached = _volume_cache_get(key)
    if cached is not None:
        return cached
    boxes = _build_volume_boxes(resolved, float(voxel), float(thr), int(dilation), int(max_boxes))
    _volume_cache_set(key, boxes)
    return boxes


def _volume_box_edges_np(mins: np.ndarray, maxs: np.ndarray):
    n = mins.shape[0]
    corners = np.empty((n, 8, 3), dtype=np.float32)
    for i, (sx, sy, sz) in enumerate(((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1))):
        selx = np.where(sx, maxs[:, 0], mins[:, 0])
        sely = np.where(sy, maxs[:, 1], mins[:, 1])
        selz = np.where(sz, maxs[:, 2], mins[:, 2])
        corners[:, i, 0] = selx
        corners[:, i, 1] = sely
        corners[:, i, 2] = selz
    pairs = np.array([[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7]], dtype=np.int64)
    return np.ascontiguousarray(corners[:, pairs].reshape(n * 12, 2, 3))
