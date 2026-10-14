# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

try:
    from core import _raycast as _raycast_mod
except ImportError:
    _raycast_mod = None

def _ray_aabb_min(ox, oy, oz, dx, dy, dz, bmin_x, bmin_y, bmin_z, bmax_x, bmax_y, bmax_z):
    tmin = -1e30
    tmax = 1e30
    if abs(dx) > 1e-30:
        t1 = (bmin_x - ox) / dx
        t2 = (bmax_x - ox) / dx
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > tmin:
            tmin = t1
        if t2 < tmax:
            tmax = t2
    elif ox < bmin_x or ox > bmax_x:
        return -1.0
    if abs(dy) > 1e-30:
        t1 = (bmin_y - oy) / dy
        t2 = (bmax_y - oy) / dy
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > tmin:
            tmin = t1
        if t2 < tmax:
            tmax = t2
    elif oy < bmin_y or oy > bmax_y:
        return -1.0
    if abs(dz) > 1e-30:
        t1 = (bmin_z - oz) / dz
        t2 = (bmax_z - oz) / dz
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > tmin:
            tmin = t1
        if t2 < tmax:
            tmax = t2
    elif oz < bmin_z or oz > bmax_z:
        return -1.0
    if tmin > tmax:
        return -1.0
    return tmin if tmin > 0.0 else (tmax if tmax > 0.0 else -1.0)

def _moller_trumbore(ox, oy, oz, dx, dy, dz, ax, ay, az, bx, by, bz, cx, cy, cz):
    e1x = bx - ax
    e1y = by - ay
    e1z = bz - az
    e2x = cx - ax
    e2y = cy - ay
    e2z = cz - az
    px = dy * e2z - dz * e2y
    py = dz * e2x - dx * e2z
    pz = dx * e2y - dy * e2x
    det = e1x * px + e1y * py + e1z * pz
    if abs(det) < 1e-12:
        return -1.0
    inv_det = 1.0 / det
    tx = ox - ax
    ty = oy - ay
    tz = oz - az
    u = (tx * px + ty * py + tz * pz) * inv_det
    if u < 0.0 or u > 1.0:
        return -1.0
    qx = ty * e1z - tz * e1y
    qy = tz * e1x - tx * e1z
    qz = tx * e1y - ty * e1x
    v = (dx * qx + dy * qy + dz * qz) * inv_det
    if v < 0.0 or u + v > 1.0:
        return -1.0
    t = (e2x * qx + e2y * qy + e2z * qz) * inv_det
    return t if t > 0 else -1.0

class _QueryMixin:
    def intersect(self, ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, vertices: np.ndarray | None = None, indices: np.ndarray | None = None) -> float:
        nodes = self._nodes
        if len(nodes) == 0:
            return -1.0
        v_arr = self._vertices if vertices is None else vertices
        i_arr = self._indices if indices is None else indices
        if (_raycast_mod is not None and v_arr is self._vertices and i_arr is self._indices and v_arr.dtype == np.float32 and v_arr.flags.c_contiguous):
            return _raycast_mod.bvh_intersect(nodes, self._tri_v0, self._tri_v1, self._tri_v2, np.ascontiguousarray(v_arr).reshape(-1), ox, oy, oz, dx, dy, dz, self._root_idx)
        verts3 = v_arr.reshape(-1, 3)
        best_t = float('inf')
        stack = np.empty(64, dtype=np.intp)
        sp = 0
        stack[sp] = self._root_idx
        sp += 1
        while sp > 0:
            sp -= 1
            ni = stack[sp]
            nd = nodes[ni]
            t = _ray_aabb_min(ox, oy, oz, dx, dy, dz, nd[0], nd[1], nd[2], nd[3], nd[4], nd[5])
            if t < 0 or t >= best_t:
                continue
            left_or_start = int(nd[6])
            right_or_count = int(nd[7])
            is_leaf = right_or_count < 0
            if is_leaf:
                tri_start = left_or_start
                tri_end = tri_start + (-right_or_count - 1)
                for ti in range(tri_start, tri_end):
                    t_idx = int(self._tri_indices[ti])
                    vi0 = int(i_arr[t_idx * 3])
                    vi1 = int(i_arr[t_idx * 3 + 1])
                    vi2 = int(i_arr[t_idx * 3 + 2])
                    v0 = verts3[vi0]
                    v1 = verts3[vi1]
                    v2 = verts3[vi2]
                    tt = _moller_trumbore(ox, oy, oz, dx, dy, dz, v0[0], v0[1], v0[2], v1[0], v1[1], v1[2], v2[0], v2[1], v2[2])
                    if tt > 0 and tt < best_t:
                        best_t = tt
            else:
                n_left = left_or_start
                n_right = right_or_count
                ln = nodes[n_left]
                rn = nodes[n_right]
                tl = _ray_aabb_min(ox, oy, oz, dx, dy, dz, ln[0], ln[1], ln[2], ln[3], ln[4], ln[5])
                tr = _ray_aabb_min(ox, oy, oz, dx, dy, dz, rn[0], rn[1], rn[2], rn[3], rn[4], rn[5])
                if tl < 0 and tr < 0:
                    continue
                if tl < 0:
                    stack[sp] = n_right
                    sp += 1
                elif tr < 0:
                    stack[sp] = n_left
                    sp += 1
                else:
                    if tl < tr:
                        stack[sp] = n_right
                        sp += 1
                        stack[sp] = n_left
                        sp += 1
                    else:
                        stack[sp] = n_left
                        sp += 1
                        stack[sp] = n_right
                        sp += 1
        return -1.0 if best_t == float('inf') else best_t
    def intersect_any(self, ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, vertices: np.ndarray | None = None, indices: np.ndarray | None = None) -> bool:
        nodes = self._nodes
        if len(nodes) == 0:
            return False
        v_arr = self._vertices if vertices is None else vertices
        i_arr = self._indices if indices is None else indices
        if (_raycast_mod is not None and v_arr is self._vertices and i_arr is self._indices and v_arr.dtype == np.float32 and v_arr.flags.c_contiguous):
            return _raycast_mod.bvh_intersect_any(nodes, self._tri_v0, self._tri_v1, self._tri_v2, np.ascontiguousarray(v_arr).reshape(-1), ox, oy, oz, dx, dy, dz, self._root_idx)
        verts3 = v_arr.reshape(-1, 3)
        stack = np.empty(64, dtype=np.intp)
        sp = 0
        stack[sp] = self._root_idx
        sp += 1
        while sp > 0:
            sp -= 1
            ni = stack[sp]
            nd = nodes[ni]
            t = _ray_aabb_min(ox, oy, oz, dx, dy, dz, nd[0], nd[1], nd[2], nd[3], nd[4], nd[5])
            if t < 0:
                continue
            left_or_start = int(nd[6])
            right_or_count = int(nd[7])
            is_leaf = right_or_count < 0
            if is_leaf:
                tri_start = left_or_start
                tri_end = tri_start + (-right_or_count - 1)
                for ti in range(tri_start, tri_end):
                    t_idx = int(self._tri_indices[ti])
                    vi0 = int(i_arr[t_idx * 3])
                    vi1 = int(i_arr[t_idx * 3 + 1])
                    vi2 = int(i_arr[t_idx * 3 + 2])
                    v0 = verts3[vi0]
                    v1 = verts3[vi1]
                    v2 = verts3[vi2]
                    tt = _moller_trumbore(ox, oy, oz, dx, dy, dz, v0[0], v0[1], v0[2], v1[0], v1[1], v1[2], v2[0], v2[1], v2[2])
                    if tt > 0:
                        return True
            else:
                n_left = left_or_start
                n_right = right_or_count
                ln = nodes[n_left]
                rn = nodes[n_right]
                tl = _ray_aabb_min(ox, oy, oz, dx, dy, dz, ln[0], ln[1], ln[2], ln[3], ln[4], ln[5])
                tr = _ray_aabb_min(ox, oy, oz, dx, dy, dz, rn[0], rn[1], rn[2], rn[3], rn[4], rn[5])
                if tl < 0 and tr < 0:
                    continue
                if tl < 0:
                    stack[sp] = n_right
                    sp += 1
                elif tr < 0:
                    stack[sp] = n_left
                    sp += 1
                else:
                    if tl < tr:
                        stack[sp] = n_right
                        sp += 1
                        stack[sp] = n_left
                        sp += 1
                    else:
                        stack[sp] = n_left
                        sp += 1
                        stack[sp] = n_right
                        sp += 1
        return False

def _node_depth(bvh, ni):
    nodes = bvh._nodes
    if ni < 0 or ni >= len(nodes):
        return 0
    nd = nodes[ni]
    if nd[7] < 0:
        return 0
    return 1 + max(_node_depth(bvh, int(nd[6])), _node_depth(bvh, int(nd[7])))

def _compute_node_depths(bvh):
    nodes = bvh._nodes
    depths = [1 << 29] * len(nodes)
    def walk(ni, d):
        if ni < 0 or ni >= len(nodes):
            return
        depths[ni] = d
        nd = nodes[ni]
        if nd[7] >= 0:
            walk(int(nd[6]), d + 1)
            walk(int(nd[7]), d + 1)
    if len(nodes) > 0:
        walk(bvh._root_idx, 0)
    return depths

def _hsv_to_rgb(h, s, v):
    h_i = int(h * 6)
    f = h * 6 - h_i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    if h_i == 0:
        return v, t, p
    elif h_i == 1:
        return q, v, p
    elif h_i == 2:
        return p, v, t
    elif h_i == 3:
        return p, q, v
    elif h_i == 4:
        return t, p, v
    else:
        return v, p, q

def _build_bvh_lines(bvh, depth_filter: int = -1) -> list[tuple]:
    depths = _compute_node_depths(bvh) if depth_filter >= 0 else None
    lines = []
    from core.maths.math3d import Vec3
    n_nodes = len(bvh._nodes)
    for ni in range(n_nodes):
        if depth_filter >= 0 and depths[ni] != depth_filter:
            continue
        nd = bvh._nodes[ni]
        mn = nd[0:3]
        mx = nd[3:6]
        corners = [(mn[0], mn[1], mn[2]), (mx[0], mn[1], mn[2]), (mx[0], mx[1], mn[2]), (mn[0], mx[1], mn[2]), (mn[0], mn[1], mx[2]), (mx[0], mn[1], mx[2]), (mx[0], mx[1], mx[2]), (mn[0], mx[1], mx[2])]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        frac = ni / max(1, n_nodes)
        hue = frac * 0.66
        r, g, b = _hsv_to_rgb(hue, 0.8, 0.6 + 0.4 * (1.0 - frac))
        color = [r, g, b]
        for e in edges:
            s = Vec3(*corners[e[0]])
            t = Vec3(*corners[e[1]])
            lines.append((s, t, color))
    return lines

_EDGE_PAIRS = np.array([0, 1, 1, 2, 2, 3, 3, 0, 4, 5, 5, 6, 6, 7, 7, 4, 0, 4, 1, 5, 2, 6, 3, 7], dtype=np.intp).reshape(-1, 2)

def build_bvh_arrays(bvh, max_depth: int = -1):
    n = len(bvh._nodes)
    if n == 0:
        return None, None, None
    if max_depth < 0:
        mask = None
        count = n
    else:
        depths = bvh.node_depths
        mask = np.array([d <= max_depth for d in depths], dtype=bool)
        count = int(mask.sum())
        if count == 0:
            return None, None, None
    corners = np.empty((count, 8, 3), dtype=np.float32)
    if mask is None:
        for i in range(n):
            nd = bvh._nodes[i]
            mn, mx = nd[0:3], nd[3:6]
            corners[i, 0] = (mn[0], mn[1], mn[2])
            corners[i, 1] = (mx[0], mn[1], mn[2])
            corners[i, 2] = (mx[0], mx[1], mn[2])
            corners[i, 3] = (mn[0], mx[1], mn[2])
            corners[i, 4] = (mn[0], mn[1], mx[2])
            corners[i, 5] = (mx[0], mn[1], mx[2])
            corners[i, 6] = (mx[0], mx[1], mx[2])
            corners[i, 7] = (mn[0], mx[1], mx[2])
    else:
        idx = 0
        for i in range(n):
            if not mask[i]:
                continue
            nd = bvh._nodes[i]
            mn, mx = nd[0:3], nd[3:6]
            corners[idx, 0] = (mn[0], mn[1], mn[2])
            corners[idx, 1] = (mx[0], mn[1], mn[2])
            corners[idx, 2] = (mx[0], mx[1], mn[2])
            corners[idx, 3] = (mn[0], mx[1], mn[2])
            corners[idx, 4] = (mn[0], mn[1], mx[2])
            corners[idx, 5] = (mx[0], mn[1], mx[2])
            corners[idx, 6] = (mx[0], mx[1], mx[2])
            corners[idx, 7] = (mn[0], mx[1], mx[2])
            idx += 1
    starts = corners[:, _EDGE_PAIRS[:, 0], :].reshape(-1, 3)
    ends = corners[:, _EDGE_PAIRS[:, 1], :].reshape(-1, 3)
    frac = np.arange(count, dtype=np.float32) / max(1, count)
    hue = frac * 0.66
    sat = np.full(count, 0.8, dtype=np.float32)
    val = 0.6 + 0.4 * (1.0 - frac)
    h_i = (hue * 6).astype(np.intp)
    f = hue * 6 - h_i
    p = val * (1 - sat)
    q = val * (1 - f * sat)
    t = val * (1 - (1 - f) * sat)
    r = np.select([h_i == 0, h_i == 1, h_i == 2, h_i == 3, h_i == 4, h_i >= 5], [val, q, p, p, t, val])
    g = np.select([h_i == 0, h_i == 1, h_i == 2, h_i == 3, h_i == 4, h_i >= 5], [t, val, val, q, p, p])
    b = np.select([h_i == 0, h_i == 1, h_i == 2, h_i == 3, h_i == 4, h_i >= 5], [p, p, t, val, val, q])
    colors = np.column_stack([r, g, b])
    colors = np.repeat(colors[:, None, :], 12, axis=1).reshape(-1, 3)
    return starts, ends, colors
