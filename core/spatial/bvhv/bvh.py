# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import time
from concurrent.futures import Future
import numpy as np
from . import lru as _lru_mod
from .build import _BuildMixin
from .build import _get_bvh_build_mode
from .query import _QueryMixin
from .query import _compute_node_depths
from .lru import _NodeView

class BVH(_BuildMixin, _QueryMixin):
    __slots__ = ('_nodes', '_tri_indices', '_tri_bmin', '_tri_bmax', '_centroids', '_vertices', '_indices', '_vert_key', '_idx_key', '_task_id', '_cached_depths', '_node_views', '_tri_v0', '_tri_v1', '_tri_v2', '_root_idx')
    def __init__(self, vertices: np.ndarray, indices: np.ndarray, task_id: str | None = None):
        self._vertices = vertices
        self._indices = indices
        self._cached_depths: list[int] | None = None
        self._node_views: list | None = None
        self._vert_key = id(vertices)
        self._idx_key = id(indices)
        self._task_id = task_id or str(self._vert_key)
        n_tris = len(indices) // 3
        if n_tris == 0:
            self._nodes = np.empty((0, 8), dtype=np.float32)
            self._tri_indices = np.array([], dtype=np.uint32)
            self._tri_bmin = np.empty((0, 3), dtype=np.float32)
            self._tri_bmax = np.empty((0, 3), dtype=np.float32)
            self._centroids = np.empty((0, 3), dtype=np.float32)
            self._tri_v0 = np.array([], dtype=np.uint32)
            self._tri_v1 = np.array([], dtype=np.uint32)
            self._tri_v2 = np.array([], dtype=np.uint32)
            self._root_idx = 0
            return
        verts3 = vertices.reshape(-1, 3)
        tri_i = indices.reshape(n_tris, 3).astype(np.intp)
        v0 = verts3[tri_i[:, 0]]
        v1 = verts3[tri_i[:, 1]]
        v2 = verts3[tri_i[:, 2]]
        self._tri_bmin = np.minimum(np.minimum(v0, v1), v2)
        self._tri_bmax = np.maximum(np.maximum(v0, v1), v2)
        self._centroids = (v0 + v1 + v2) / 3.0
        tri_order = np.arange(n_tris, dtype=np.intp)
        if _get_bvh_build_mode() == "fast" and n_tris > 4096:
            self._build_lbvh(tri_order, n_tris)
        else:
            self._build(tri_order, n_tris)
        tri_u32 = np.asarray(indices, dtype=np.uint32)
        slot_idx = self._tri_indices.astype(np.intp) * 3
        self._tri_v0 = tri_u32[slot_idx]
        self._tri_v1 = tri_u32[slot_idx + 1]
        self._tri_v2 = tri_u32[slot_idx + 2]
    @classmethod
    def from_cache(cls, nodes: np.ndarray, tri_indices: np.ndarray, vertices: np.ndarray, indices: np.ndarray, root_idx: int = -1):
        bvh = object.__new__(cls)
        bvh._nodes = nodes
        bvh._tri_indices = tri_indices
        bvh._vertices = vertices
        bvh._indices = indices
        bvh._vert_key = id(vertices)
        bvh._idx_key = id(indices)
        bvh._task_id = ""
        bvh._cached_depths = None
        bvh._node_views = None
        bvh._tri_bmin = np.empty((0, 3), dtype=np.float32)
        bvh._tri_bmax = np.empty((0, 3), dtype=np.float32)
        bvh._centroids = np.empty((0, 3), dtype=np.float32)
        bvh._root_idx = root_idx if root_idx >= 0 else len(nodes) - 1
        tri_u32 = np.asarray(indices, dtype=np.uint32)
        slot_idx = tri_indices.astype(np.intp) * 3
        bvh._tri_v0 = tri_u32[slot_idx]
        bvh._tri_v1 = tri_u32[slot_idx + 1]
        bvh._tri_v2 = tri_u32[slot_idx + 2]
        return bvh
    def _apply_pair_layout(self) -> None:
        nodes = self._nodes
        n = len(nodes)
        if n == 0:
            return
        root_old = int(self._root_idx)
        out = np.zeros((n + 1, 8), dtype=np.float32)
        old2new = np.full(n, -1, dtype=np.intp)
        out[1] = nodes[root_old]
        old2new[root_old] = 1
        stack = [root_old]
        nxt = 2
        while stack:
            o = stack.pop()
            nd = nodes[o]
            if nd[7] >= 0:
                l = int(nd[6])
                r = int(nd[7])
                old2new[l] = nxt
                out[nxt] = nodes[l]
                nxt += 1
                old2new[r] = nxt
                out[nxt] = nodes[r]
                nxt += 1
                stack.append(r)
                stack.append(l)
        out[0, 6] = 0.0
        out[0, 7] = -1.0
        inner = out[:, 7] >= 0
        li = out[inner, 6].astype(np.intp)
        ri = out[inner, 7].astype(np.intp)
        out[inner, 6] = old2new[li].astype(np.float32)
        out[inner, 7] = old2new[ri].astype(np.float32)
        self._nodes = out
        self._root_idx = 1
        self._cached_depths = None
        self._node_views = None
    def flatten_for_gpu(self):
        return self._nodes
    def flatten_for_gpu_stackless(self) -> np.ndarray:
        nodes = self._nodes
        n = len(nodes)
        if n == 0:
            return np.empty((0, 8), dtype=np.float32)
        sizes = np.empty(n, dtype=np.int64)
        for i in range(n):
            right_or_count = nodes[i, 7]
            if right_or_count < 0:
                sizes[i] = 1
            else:
                l = int(nodes[i, 6])
                r = int(right_or_count)
                sizes[i] = 1 + sizes[l] + sizes[r]
        order = np.empty(n, dtype=np.int64)
        stack = [int(self._root_idx)]
        w = 0
        while stack:
            old = stack.pop()
            order[w] = old
            w += 1
            right_or_count = nodes[old, 7]
            if right_or_count >= 0:
                stack.append(int(right_or_count))
                stack.append(int(nodes[old, 6]))
        out = np.empty((n, 8), dtype=np.float32)
        out[:, 0:6] = nodes[order, 0:6]
        right_or_count_ord = nodes[order, 7]
        leaf_mask = right_or_count_ord < 0
        out[leaf_mask, 6] = nodes[order[leaf_mask], 6]
        out[leaf_mask, 7] = right_or_count_ord[leaf_mask]
        internal_new_idx = np.nonzero(~leaf_mask)[0]
        out[internal_new_idx, 6] = (internal_new_idx + sizes[order[internal_new_idx]]).astype(np.float32)
        out[internal_new_idx, 7] = 0.0
        return out
    @property
    def tri_indices(self) -> np.ndarray:
        return self._tri_indices
    def node_count(self) -> int:
        return len(self._nodes)
    def depth(self) -> int:
        nodes = self._nodes
        if len(nodes) == 0:
            return 0
        def _max_depth(ni, d):
            if ni < 0 or ni >= len(nodes):
                return d
            nd = nodes[ni]
            if nd[7] < 0:
                return d
            return max(_max_depth(int(nd[6]), d + 1), _max_depth(int(nd[7]), d + 1))
        return _max_depth(self._root_idx, 0)
    @property
    def node_depths(self) -> list[int]:
        if self._cached_depths is None:
            self._cached_depths = _compute_node_depths(self)
        return self._cached_depths
    @property
    def nodes(self):
        if self._node_views is None:
            self._node_views = [_NodeView(self._nodes[i]) for i in range(len(self._nodes))]
        return self._node_views
    def enumerate_nodes(self):
        for i in range(len(self._nodes)):
            yield i, self.nodes[i]

def get_mesh_bvh(vertices: np.ndarray, indices: np.ndarray):
    if vertices is None or len(vertices) < 3 or indices is None or len(indices) < 3:
        return None
    with _lru_mod._BVH_LOCK:
        if _lru_mod._BVH_CACHE_RUNTIME_VERSION != _lru_mod._BVH_CACHE_VERSION:
            _lru_mod._clear_bvh_cache_locked()
            _lru_mod._BVH_CACHE_RUNTIME_VERSION = _lru_mod._BVH_CACHE_VERSION
            _lru_mod._bvh_log(f"CACHE CLEAR version bump {_lru_mod._BVH_CACHE_RUNTIME_VERSION} -> {_lru_mod._BVH_CACHE_VERSION}")
    key = _lru_mod._bvh_key_memoized(vertices, indices)
    n_tris = len(indices) // 3
    with _lru_mod._BVH_LOCK:
        _cached_entry = _lru_mod._BVH_CACHE.get(key)
        if isinstance(_cached_entry, BVH):
            _lru_mod._BVH_FAILED.pop(key, None)
            return _cached_entry
        if key in _lru_mod._BVH_FAILED and time.monotonic() < _lru_mod._BVH_FAILED[key]:
            _lru_mod._BVH_CACHE[key] = None
            return None
        if key not in _lru_mod._BVH_CACHE:
            cache_dir = _lru_mod._bvh_cache_dir()
            if cache_dir:
                cached = _lru_mod._load_bvh_disk(key, cache_dir, vertices, indices)
                if cached is not None:
                    _lru_mod._BVH_CACHE[key] = cached
                    _lru_mod._bvh_log(f"GET key={key} DISK HIT")
                    return cached
            if n_tris <= 512:
                try:
                    nodes, tris, root = _lru_mod._build_bvh(vertices, indices, cache_key=key, progress_queue=None) or (None, None, None)
                    if nodes is not None:
                        bvh = BVH.from_cache(nodes, tris, vertices, indices, root)
                        _lru_mod._BVH_CACHE[key] = bvh
                        if cache_dir:
                            _lru_mod._save_bvh_disk(key, bvh, cache_dir)
                        _lru_mod._bvh_log(f"GET key={key} SYNC_BUILT nodes={bvh.node_count()}")
                        return bvh
                except Exception as exc:
                    _lru_mod._bvh_log(f"GET key={key} SYNC_FAIL {type(exc).__name__}")
            _lru_mod._bvh_log(f"GET key={key} SUBMIT verts={len(vertices)} idx={len(indices)}")
            try:
                from core.ecs.pool import bvh as _get_pool
                from core.foundation.progress import get_progress_queue as _gpq
                _lru_mod._BVH_CACHE[key] = _get_pool().submit(_lru_mod._build_bvh, vertices, indices, cache_key=key, progress_queue=_gpq())
            except Exception as exc:
                _lru_mod._bvh_log(f"GET key={key} SUBMIT FAIL {type(exc).__name__}: {exc}")
                try:
                    import core.ecs.pool as _pm
                    _pm._bvh_pool = None
                    from core.ecs.pool import bvh as _get_pool2
                    from core.foundation.progress import get_progress_queue as _gpq2
                    _lru_mod._BVH_CACHE[key] = _get_pool2().submit(_lru_mod._build_bvh, vertices, indices, cache_key=key, progress_queue=_gpq2())
                except Exception as exc2:
                    _lru_mod._bvh_log(f"GET key={key} RETRY FAIL {type(exc2).__name__}")
                    try:
                        nodes, tris, root = _lru_mod._build_bvh(vertices, indices, cache_key=key, progress_queue=None) or (None, None, None)
                        if nodes is not None:
                            bvh = BVH.from_cache(nodes, tris, vertices, indices, root)
                            _lru_mod._BVH_CACHE[key] = bvh
                            if cache_dir:
                                _lru_mod._save_bvh_disk(key, bvh, cache_dir)
                            return bvh
                    except Exception:
                        pass
                    _lru_mod._BVH_CACHE.pop(key, None)
                    return None
        entry = _lru_mod._BVH_CACHE[key]
    if isinstance(entry, Future):
        if n_tris <= 512:
            try:
                result = entry.result(timeout=0.25)
            except Exception as exc:
                _lru_mod._bvh_log(f"GET key={key} PENDING_SMALL {type(exc).__name__}")
                return None
            if isinstance(result, tuple) and len(result) == 3:
                result = BVH.from_cache(result[0], result[1], vertices, indices, result[2])
            elif isinstance(result, tuple):
                result = BVH.from_cache(result[0], result[1], vertices, indices)
            with _lru_mod._BVH_LOCK:
                _lru_mod._BVH_CACHE[key] = result
            if result is not None:
                cache_dir = _lru_mod._bvh_cache_dir()
                if cache_dir:
                    _lru_mod._save_bvh_disk(key, result, cache_dir)
                _lru_mod._bvh_log(f"GET key={key} BUILT_SYNC nodes={result.node_count()}")
            return result
        if entry.done():
            try:
                result = entry.result()
            except Exception as exc:
                _lru_mod._bvh_log(f"GET key={key} FUTURE FAIL: {type(exc).__name__}: {exc}")
                if type(exc).__name__ == "BrokenProcessPool":
                    with _lru_mod._BVH_LOCK:
                        _lru_mod._BVH_CACHE.pop(key, None)
                    try:
                        import core.ecs.pool as _pool_mod
                        if _pool_mod._bvh_pool is not None:
                            try:
                                _pool_mod._bvh_pool.shutdown(wait=False, cancel_futures=True)
                            except TypeError:
                                try:
                                    _pool_mod._bvh_pool.shutdown(wait=False)
                                except Exception:
                                    pass
                            _pool_mod._bvh_pool = None
                    except Exception:
                        pass
                    return None
                else:
                    with _lru_mod._BVH_LOCK:
                        _lru_mod._BVH_CACHE[key] = None
                    return None
            if isinstance(result, tuple) and len(result) == 3:
                result = BVH.from_cache(result[0], result[1], vertices, indices, result[2])
            elif isinstance(result, tuple):
                result = BVH.from_cache(result[0], result[1], vertices, indices)
            if result is None:
                with _lru_mod._BVH_LOCK:
                    _lru_mod._BVH_CACHE[key] = None
                _lru_mod._bvh_log(f"GET key={key} result=None")
                return None
            with _lru_mod._BVH_LOCK:
                _lru_mod._BVH_CACHE[key] = result
            cache_dir = _lru_mod._bvh_cache_dir()
            if cache_dir:
                _lru_mod._save_bvh_disk(key, result, cache_dir)
            _lru_mod._bvh_log(f"GET key={key} BUILT nodes={result.node_count()}")
            return result
        _lru_mod._bvh_log(f"GET key={key} PENDING")
        return None
    if entry is None:
        if key not in _lru_mod._bvh_none_logged:
            _lru_mod._bvh_none_logged.add(key)
            _lru_mod._bvh_log(f"GET key={key} CACHED_NONE")
        return None
    return entry

def get_mesh_bvh_sync(vertices: np.ndarray, indices: np.ndarray, timeout: float = 60.0):
    if vertices is None or len(vertices) < 3 or indices is None or len(indices) < 3:
        return None
    with _lru_mod._BVH_LOCK:
        if _lru_mod._BVH_CACHE_RUNTIME_VERSION != _lru_mod._BVH_CACHE_VERSION:
            _lru_mod._clear_bvh_cache_locked()
            _lru_mod._BVH_CACHE_RUNTIME_VERSION = _lru_mod._BVH_CACHE_VERSION
            _lru_mod._bvh_log(f"SYNC CACHE CLEAR version bump")
    key = _lru_mod._bvh_key_memoized(vertices, indices)
    with _lru_mod._BVH_LOCK:
        if key not in _lru_mod._BVH_CACHE:
            cache_dir = _lru_mod._bvh_cache_dir()
            if cache_dir:
                cached = _lru_mod._load_bvh_disk(key, cache_dir, vertices, indices)
                if cached is not None:
                    _lru_mod._BVH_CACHE[key] = cached
                    return cached
            _lru_mod._bvh_log(f"SYNC key={key} SUBMIT verts={len(vertices)} idx={len(indices)}")
            from core.ecs.pool import bvh as _get_pool
            from core.foundation.progress import get_progress_queue as _gpq
            _lru_mod._BVH_CACHE[key] = _get_pool().submit(_lru_mod._build_bvh, vertices, indices, cache_key=key, progress_queue=_gpq())
        entry = _lru_mod._BVH_CACHE[key]
    if isinstance(entry, Future):
        try:
            result = entry.result(timeout=timeout)
        except Exception as exc:
            _lru_mod._bvh_log(f"SYNC key={key} FUTURE FAIL: {type(exc).__name__}: {exc}")
            result = None
        if isinstance(result, tuple) and len(result) == 3:
            result = BVH.from_cache(result[0], result[1], vertices, indices, result[2])
        elif isinstance(result, tuple):
            result = BVH.from_cache(result[0], result[1], vertices, indices)
        with _lru_mod._BVH_LOCK:
            _lru_mod._BVH_CACHE[key] = result
        if result is not None:
            cache_dir = _lru_mod._bvh_cache_dir()
            if cache_dir:
                _lru_mod._save_bvh_disk(key, result, cache_dir)
            _lru_mod._bvh_log(f"SYNC key={key} BUILT nodes={result.node_count()}")
        return result
    return entry
