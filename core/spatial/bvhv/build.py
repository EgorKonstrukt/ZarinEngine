# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import threading
import time
import numpy as np
from core.ecs.pool import bvh_parallel as _get_bvh_parallel_pool
from .lru import _bvh_log
from .lru import _bvh_task_update
from .lru import _fmt_count
from .lru import _report_build_progress

_LEAF_SIZE = 32
_MAX_DEPTH = 48
_SAH_BINS = 12
_SAH_TRAV = 1.0
_SAH_HIT = 1.0
_PAR_THRESH = 50000
_BINNED_THRESH = 4096

def _spread_bits_vec(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.uint64)
    v = (v | (v << 16)) & np.uint64(0x0000FFFF0000FFFF)
    v = (v | (v << 8)) & np.uint64(0x00FF00FF00FF00FF)
    v = (v | (v << 4)) & np.uint64(0x0F0F0F0F0F0F0F0F)
    v = (v | (v << 2)) & np.uint64(0x3333333333333333)
    v = (v | (v << 1)) & np.uint64(0x5555555555555555)
    return v.astype(np.uint32)

def _get_bvh_build_mode() -> str:
    try:
        from core.config.config import get_global_config
        return get_global_config().get("rendering.bvh_build_mode", "fast")
    except Exception:
        return "fast"

class _BuildCtx:
    __slots__ = ('last_frac', 'last_t', 'lock', 'n_verts', 'node_count', 'nodes', 'progress_done', 'task_id', 'total_tris', 'tri_indices', 'tri_offset')
    def __init__(self, max_nodes, max_tris):
        self.nodes = np.empty((max_nodes, 8), dtype=np.float32)
        self.tri_indices = np.empty(max_tris, dtype=np.uint32)
        self.node_count = 0
        self.tri_offset = 0
        self.lock = threading.Lock()
        self.progress_done = 0
        self.total_tris = 0
        self.n_verts = 0
        self.task_id = ""
        self.last_frac = 0.0
        self.last_t = 0.0

def _surface_area(bmin, bmax):
    d = bmax - bmin
    return 2.0 * (d[0] * d[1] + d[0] * d[2] + d[1] * d[2])

def _find_morton_split(sorted_morton: np.ndarray, start: int, end: int) -> int:
    common = int(sorted_morton[start] ^ sorted_morton[end - 1])
    if common == 0:
        return (start + end) // 2
    split_bit = 63 - (common.bit_length() - 1)
    split_mask = np.uint64(1 << split_bit)
    masks = sorted_morton[start:end] & split_mask
    indices = np.flatnonzero(masks)
    if len(indices) > 0:
        return start + int(indices[0])
    return (start + end) // 2

try:
    from core._bvh_build import sah_compute_best_split as _sah_cython_split
    _USE_CYTHON_BVH = True
except ImportError:
    _USE_CYTHON_BVH = False

class _BuildMixin:
    def _build(self, tri_order, n_tris):
        import sys
        sys.setrecursionlimit(1000000)
        leaves_est = (n_tris + _LEAF_SIZE - 1) // _LEAF_SIZE
        max_nodes = max(4, leaves_est * 2 + 1)
        ctx = _BuildCtx(max_nodes, n_tris)
        ctx.total_tris = n_tris
        ctx.n_verts = len(self._vertices.reshape(-1, 3))
        ctx.task_id = self._task_id
        ctx.last_t = time.monotonic()
        _bvh_task_update(ctx.task_id, 0.0, detail=f"0 / {_fmt_count(n_tris)} tris · {_fmt_count(ctx.n_verts)} verts", total=n_tris, units="tris")
        def _alloc_node(ctx):
            with ctx.lock:
                ni = ctx.node_count
                ctx.node_count += 1
                if ni >= len(ctx.nodes):
                    new_nodes = np.empty((max(len(ctx.nodes) * 2, 2), 8), dtype=np.float32)
                    new_nodes[:len(ctx.nodes)] = ctx.nodes
                    ctx.nodes = new_nodes
            return ni
        def _make_leaf(ctx, tris):
            ni = _alloc_node(ctx)
            bmin = self._tri_bmin[tris].min(axis=0)
            bmax = self._tri_bmax[tris].max(axis=0)
            ctx.nodes[ni, 0:3] = bmin
            ctx.nodes[ni, 3:6] = bmax
            with ctx.lock:
                tri_start = ctx.tri_offset
                ctx.tri_offset += len(tris)
                ctx.progress_done += len(tris)
            ctx.nodes[ni, 6] = float(tri_start)
            ctx.nodes[ni, 7] = -float(len(tris)) - 1.0
            ctx.tri_indices[tri_start:tri_start + len(tris)] = tris.astype(np.uint32)
            _report_build_progress(ctx)
            return ni
        def _binned_best_split(tris, parent_sa):
            n = len(tris)
            c_cent = self._centroids[tris]
            c_bmin = c_cent.min(axis=0)
            c_bmax = c_cent.max(axis=0)
            c_range = c_bmax - c_bmin
            best_axis = -1
            best_split = 0.0
            best_cost = float('inf')
            for axis in range(3):
                if c_range[axis] < 1e-12:
                    continue
                bins = _SAH_BINS
                scale = bins / c_range[axis]
                cent_vals = c_cent[:, axis]
                bin_idx = np.floor((cent_vals - c_bmin[axis]) * scale).astype(np.intp)
                bin_idx = np.clip(bin_idx, 0, bins - 1)
                bin_cnt = np.bincount(bin_idx, minlength=bins).astype(np.intp)
                sort_idx = np.argsort(bin_idx, kind='stable')
                sorted_bin = bin_idx[sort_idx]
                sorted_tris = tris[sort_idx]
                tri_bm = self._tri_bmin[sorted_tris]
                tri_bx = self._tri_bmax[sorted_tris]
                boundaries = np.searchsorted(sorted_bin, np.arange(bins))
                bin_bmin = np.full((bins, 3), 1e30, dtype=np.float32)
                bin_bmax = np.full((bins, 3), -1e30, dtype=np.float32)
                for bi in range(bins):
                    s = boundaries[bi]
                    e = boundaries[bi + 1] if bi + 1 < bins else n
                    if s < e:
                        bin_bmin[bi] = tri_bm[s:e].min(axis=0)
                        bin_bmax[bi] = tri_bx[s:e].max(axis=0)
                left_cs = np.cumsum(bin_cnt[:-1])
                right_cs = n - left_cs
                valid = (left_cs > 0) & (right_cs > 0)
                pmin_acc = np.minimum.accumulate(bin_bmin[:-1], axis=0)
                pmax_acc = np.maximum.accumulate(bin_bmax[:-1], axis=0)
                d_l = pmax_acc - pmin_acc
                left_sa_arr = 2.0 * (d_l[:, 0] * d_l[:, 1] + d_l[:, 0] * d_l[:, 2] + d_l[:, 1] * d_l[:, 2])
                left_cost = left_sa_arr * left_cs
                smin_rev = np.minimum.accumulate(bin_bmin[:0:-1], axis=0)[::-1]
                smax_rev = np.maximum.accumulate(bin_bmax[:0:-1], axis=0)[::-1]
                d_r = smax_rev - smin_rev
                right_sa_arr = 2.0 * (d_r[:, 0] * d_r[:, 1] + d_r[:, 0] * d_r[:, 2] + d_r[:, 1] * d_r[:, 2])
                right_cost = right_sa_arr * right_cs
                costs = np.full(bins - 1, np.inf, dtype=np.float64)
                costs[valid] = _SAH_TRAV + (left_cost[valid] + right_cost[valid]) / parent_sa
                i_best = int(np.argmin(costs))
                if costs[i_best] < best_cost:
                    best_cost = float(costs[i_best])
                    best_axis = axis
                    best_split = c_bmin[axis] + (i_best + 1) * c_range[axis] / bins
            return best_axis, best_split, best_cost
        def _sweep_best_split(tris, parent_sa):
            n = len(tris)
            bmin_sub = self._tri_bmin[tris]
            bmax_sub = self._tri_bmax[tris]
            centroids = self._centroids[tris]
            best_cost = float('inf')
            best_axis = -1
            best_idx = -1
            best_sorted = None
            for axis in range(3):
                order = np.argsort(centroids[:, axis], kind='stable')
                sbmin = bmin_sub[order]
                sbmax = bmax_sub[order]
                sorted_tris = tris[order]
                left_min = np.minimum.accumulate(sbmin, axis=0)
                left_max = np.maximum.accumulate(sbmax, axis=0)
                right_min = np.minimum.accumulate(sbmin[::-1], axis=0)[::-1]
                right_max = np.maximum.accumulate(sbmax[::-1], axis=0)[::-1]
                dl = left_max[:-1] - left_min[:-1]
                dr = right_max[1:] - right_min[1:]
                l_sa = 2.0 * (dl[:, 0] * dl[:, 1] + dl[:, 0] * dl[:, 2] + dl[:, 1] * dl[:, 2])
                r_sa = 2.0 * (dr[:, 0] * dr[:, 1] + dr[:, 0] * dr[:, 2] + dr[:, 1] * dr[:, 2])
                lc = np.arange(1, n, dtype=np.float64)
                rc = float(n) - lc
                costs = _SAH_TRAV + (l_sa * lc + r_sa * rc) / parent_sa
                idx = int(np.argmin(costs))
                c = float(costs[idx])
                if c < best_cost:
                    best_cost = c
                    best_axis = axis
                    best_idx = idx + 1
                    best_sorted = sorted_tris
            return best_axis, best_idx, best_sorted, best_cost
        def _sah_build(tris, depth=0):
            n = len(tris)
            bmin = self._tri_bmin[tris].min(axis=0)
            bmax = self._tri_bmax[tris].max(axis=0)
            if n <= _LEAF_SIZE or depth >= _MAX_DEPTH:
                return _make_leaf(ctx, tris)
            parent_sa = _surface_area(bmin, bmax)
            if parent_sa < 1e-12:
                return _make_leaf(ctx, tris)
            if n > _BINNED_THRESH:
                if _USE_CYTHON_BVH:
                    best_axis, best_split, lmask = _sah_cython_split(np.asarray(tris, dtype=np.intp), self._tri_bmin, self._tri_bmax, self._centroids, n, parent_sa, _SAH_BINS)
                    if best_axis < 0:
                        return _make_leaf(ctx, tris)
                    left_mask = lmask
                else:
                    best_axis, best_split, best_cost = _binned_best_split(tris, parent_sa)
                    if best_axis < 0:
                        return _make_leaf(ctx, tris)
                    leaf_cost = n * _SAH_HIT
                    if best_cost >= leaf_cost:
                        return _make_leaf(ctx, tris)
                    c_cent = self._centroids[tris]
                    left_mask = c_cent[:, best_axis] < best_split
                left_n = int(left_mask.sum())
                if left_n == 0 or left_n == n:
                    c_cent = self._centroids[tris]
                    cent_axis = c_cent[:, best_axis] if best_axis >= 0 else self._centroids[tris, 0]
                    mid = n // 2
                    order = np.argsort(cent_axis, kind='stable')
                    left_tris = tris[order[:mid]]
                    right_tris = tris[order[mid:]]
                else:
                    left_tris = tris[left_mask]
                    right_tris = tris[~left_mask]
            else:
                best_axis, best_idx, best_sorted, best_cost = _sweep_best_split(tris, parent_sa)
                leaf_cost = n * _SAH_HIT
                if best_axis < 0 or best_sorted is None or best_idx <= 0 or best_idx >= n or best_cost >= leaf_cost:
                    return _make_leaf(ctx, tris)
                left_tris = best_sorted[:best_idx].copy()
                right_tris = best_sorted[best_idx:].copy()
                if len(left_tris) == 0 or len(right_tris) == 0:
                    return _make_leaf(ctx, tris)
            use_parallel = depth == 0 and n >= _PAR_THRESH
            if use_parallel:
                pool = _get_bvh_parallel_pool()
                lf = pool.submit(_sah_build, left_tris, depth + 1)
                rf = pool.submit(_sah_build, right_tris, depth + 1)
                lc = lf.result()
                rc = rf.result()
                ni = _alloc_node(ctx)
                ctx.nodes[ni, 0:3] = bmin
                ctx.nodes[ni, 3:6] = bmax
                ctx.nodes[ni, 6] = float(lc)
                ctx.nodes[ni, 7] = float(rc)
            else:
                lc = _sah_build(left_tris, depth + 1)
                rc = _sah_build(right_tris, depth + 1)
                ni = _alloc_node(ctx)
                ctx.nodes[ni, 0:3] = bmin
                ctx.nodes[ni, 3:6] = bmax
                ctx.nodes[ni, 6] = float(lc)
                ctx.nodes[ni, 7] = float(rc)
            return ni
        _sah_build(tri_order)
        self._nodes = ctx.nodes[:ctx.node_count]
        self._tri_indices = ctx.tri_indices[:ctx.tri_offset]
        self._root_idx = ctx.node_count - 1
        self._apply_pair_layout()
    def _build_lbvh(self, tri_order, n_tris):
        verts3 = self._vertices.reshape(-1, 3)
        tri_i = self._indices.reshape(n_tris, 3).astype(np.intp)
        v0 = verts3[tri_i[:, 0]]
        v1 = verts3[tri_i[:, 1]]
        v2 = verts3[tri_i[:, 2]]
        scene_min = np.minimum(np.minimum(v0, v1), v2).min(axis=0)
        scene_max = np.maximum(np.maximum(v0, v1), v2).max(axis=0)
        scene_ext = np.maximum(scene_max - scene_min, 1e-10)
        centroids = (v0 + v1 + v2) * (1.0 / 3.0)
        norm = (centroids - scene_min) / scene_ext
        bits = 10
        scale = float((1 << bits) - 1)
        cx = np.floor(norm[:, 0] * scale).astype(np.uint32)
        cy = np.floor(norm[:, 1] * scale).astype(np.uint32)
        cz = np.floor(norm[:, 2] * scale).astype(np.uint32)
        morton = _spread_bits_vec(cx) | (_spread_bits_vec(cy) << 1) | (_spread_bits_vec(cz) << 2)
        morton_u64 = morton.astype(np.uint64)
        order = np.argsort(morton_u64, kind='stable')
        sorted_tris = tri_order[order]
        sorted_morton = morton_u64[order]
        if n_tris == 1:
            ctx = _BuildCtx(1, 1)
            ctx.total_tris = 1
            ctx.n_verts = len(self._vertices.reshape(-1, 3))
            ctx.task_id = self._task_id
            ctx.tri_indices[0] = sorted_tris[0]
            ctx.progress_done = 1
            _report_build_progress(ctx)
            bmin, bmax = self._tri_bmin[0], self._tri_bmax[0]
            self._nodes = np.array([[bmin[0], bmin[1], bmin[2], bmax[0], bmax[1], bmax[2], 0.0, -2.0]], dtype=np.float32)
            self._tri_indices = ctx.tri_indices[:1]
            self._root_idx = 0
            self._apply_pair_layout()
            return
        leaves_est = (n_tris + _LEAF_SIZE - 1) // _LEAF_SIZE
        max_nodes = max(4, leaves_est * 2)
        node_bmin = np.empty((max_nodes, 3), dtype=np.float32)
        node_bmax = np.empty((max_nodes, 3), dtype=np.float32)
        left_child = np.full(max_nodes, -1, dtype=np.int32)
        right_child = np.full(max_nodes, -1, dtype=np.int32)
        leaf_flag = np.ones(max_nodes, dtype=bool)
        leaf_tri_start = np.full(max_nodes, -1, dtype=np.int32)
        leaf_tri_count = np.zeros(max_nodes, dtype=np.int32)
        node_count = 0
        ctx = _BuildCtx(max_nodes, n_tris)
        ctx.total_tris = n_tris
        ctx.n_verts = len(self._vertices.reshape(-1, 3))
        ctx.task_id = self._task_id
        ctx.last_t = time.monotonic()
        _bvh_task_update(ctx.task_id, 0.0, detail=f"0 / {_fmt_count(n_tris)} tris · {_fmt_count(ctx.n_verts)} verts", total=n_tris, units="tris")
        def _grow_lbvh_arrays(cap):
            nonlocal max_nodes, node_bmin, node_bmax, left_child, right_child, leaf_flag, leaf_tri_start, leaf_tri_count
            node_bmin = _grow_arr(node_bmin, cap)
            node_bmax = _grow_arr(node_bmax, cap)
            left_child = _grow_arr(left_child, cap)
            right_child = _grow_arr(right_child, cap)
            leaf_flag = _grow_arr(leaf_flag, cap)
            leaf_tri_start = _grow_arr(leaf_tri_start, cap)
            leaf_tri_count = _grow_arr(leaf_tri_count, cap)
            max_nodes = cap
        def _grow_arr(arr, cap):
            grown = np.empty((cap,) + arr.shape[1:], dtype=arr.dtype)
            grown[:len(arr)] = arr
            return grown
        td_build_stack = [(0, n_tris, -1, False)]
        while td_build_stack:
            start, end, parent_idx, is_right = td_build_stack.pop()
            count = end - start
            ni = node_count
            node_count += 1
            if ni >= max_nodes:
                _grow_lbvh_arrays(max(max_nodes * 2, 2))
            if parent_idx >= 0:
                if is_right:
                    right_child[parent_idx] = ni
                else:
                    left_child[parent_idx] = ni
            if count <= _LEAF_SIZE:
                leaf_flag[ni] = True
                tri_range = sorted_tris[start:end]
                node_bmin[ni] = self._tri_bmin[tri_range].min(axis=0)
                node_bmax[ni] = self._tri_bmax[tri_range].max(axis=0)
                leaf_tri_start[ni] = start
                leaf_tri_count[ni] = count
                ctx.progress_done += count
                _report_build_progress(ctx)
            else:
                leaf_flag[ni] = False
                split = _find_morton_split(sorted_morton, start, end)
                td_build_stack.append((split, end, ni, True))
                td_build_stack.append((start, split, ni, False))
        root = 0
        nodes_out = np.empty((node_count, 8), dtype=np.float32)
        tri_offset = 0
        _flatten_stack = [(root, False)]
        while _flatten_stack:
            ni, visited_right = _flatten_stack.pop()
            if leaf_flag[ni]:
                tc = int(leaf_tri_count[ni])
                nodes_out[ni, 0:3] = node_bmin[ni]
                nodes_out[ni, 3:6] = node_bmax[ni]
                nodes_out[ni, 6] = float(tri_offset)
                nodes_out[ni, 7] = float(-tc - 1)
                ts = int(leaf_tri_start[ni])
                ctx.tri_indices[tri_offset:tri_offset + tc] = sorted_tris[ts:ts + tc]
                tri_offset += tc
                continue
            lc = int(left_child[ni])
            rc = int(right_child[ni])
            if not visited_right:
                nodes_out[ni, 6] = float(lc)
                nodes_out[ni, 7] = float(rc)
                _flatten_stack.append((ni, True))
                _flatten_stack.append((rc, False))
                _flatten_stack.append((lc, False))
            else:
                np.minimum(nodes_out[lc, 0:3], nodes_out[rc, 0:3], out=nodes_out[ni, 0:3])
                np.maximum(nodes_out[lc, 3:6], nodes_out[rc, 3:6], out=nodes_out[ni, 3:6])
        self._nodes = nodes_out[:node_count]
        self._tri_indices = ctx.tri_indices[:tri_offset]
        self._root_idx = 0
        self._apply_pair_layout()
