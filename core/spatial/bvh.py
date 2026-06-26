from __future__ import annotations

import numpy as np

_MAX_TRI_PER_LEAF = 8
_MAX_DEPTH = 32


class BVHNode:
    __slots__ = ("bmin", "bmax", "left", "right", "tri_start", "tri_count")

    def __init__(self, bmin, bmax):
        self.bmin = np.asarray(bmin, dtype=np.float32)
        self.bmax = np.asarray(bmax, dtype=np.float32)
        self.left = -1
        self.right = -1
        self.tri_start = 0
        self.tri_count = 0

    @property
    def is_leaf(self) -> bool:
        return self.left < 0


def _surface_area(bmin, bmax) -> float:
    d = bmax - bmin
    return 2.0 * (d[0] * d[1] + d[0] * d[2] + d[1] * d[2])


class BVH:
    def __init__(self, vertices: np.ndarray, indices: np.ndarray):
        self.vertices = vertices
        self.indices = indices
        self.nodes: list[BVHNode] = []
        self.tri_indices: np.ndarray = np.array([], dtype=np.uint32)
        self._cached_depths: list[int] | None = None
        self._build(vertices, indices)

    def _build(self, vertices: np.ndarray, indices: np.ndarray):
        n_tris = len(indices) // 3
        if n_tris == 0:
            return
        verts3 = vertices.reshape(-1, 3)
        tri_i = indices.reshape(n_tris, 3).astype(np.intp)
        v0 = verts3[tri_i[:, 0]]
        v1 = verts3[tri_i[:, 1]]
        v2 = verts3[tri_i[:, 2]]
        tri_bmin = np.minimum(np.minimum(v0, v1), v2)
        tri_bmax = np.maximum(np.maximum(v0, v1), v2)
        centroids = (v0 + v1 + v2) / 3.0

        tri_order = np.arange(n_tris, dtype=np.intp)

        import sys
        sys.setrecursionlimit(1000000)
        tri_chunks: list[np.ndarray] = []

        def _build(indices_slice, depth=0):
            n = len(indices_slice)
            bmin = tri_bmin[indices_slice].min(axis=0)
            bmax = tri_bmax[indices_slice].max(axis=0)
            if n <= _MAX_TRI_PER_LEAF or depth >= _MAX_DEPTH:
                ni = len(self.nodes)
                node = BVHNode(bmin, bmax)
                node.tri_start = -1
                node.tri_count = n
                self.nodes.append(node)
                tri_chunks.append(indices_slice.astype(np.uint32))
                return ni
            axis = int(np.argmax(bmax - bmin))
            cent = centroids[indices_slice, axis]
            order = np.argsort(cent)
            s = indices_slice[order]
            mid = n // 2
            left = _build(s[:mid], depth + 1)
            right = _build(s[mid:], depth + 1)
            ni = len(self.nodes)
            node = BVHNode(bmin, bmax)
            node.left = left
            node.right = right
            self.nodes.append(node)
            return ni

        _build(tri_order)
        if tri_chunks:
            self.tri_indices = np.concatenate(tri_chunks)
            offset = 0
            for node in self.nodes:
                if node.is_leaf:
                    node.tri_start = offset
                    offset += node.tri_count

    def intersect(self, ox: float, oy: float, oz: float,
                  dx: float, dy: float, dz: float,
                  vertices: np.ndarray | None = None,
                  indices: np.ndarray | None = None) -> float:
        if not self.nodes:
            return -1.0
        v_arr = self.vertices if vertices is None else vertices
        i_arr = self.indices if indices is None else indices
        verts3 = v_arr.reshape(-1, 3)

        best_t = float("inf")
        stack = [len(self.nodes) - 1]

        while stack:
            ni = stack.pop()
            node = self.nodes[ni]
            d = _ray_aabb_min(ox, oy, oz, dx, dy, dz,
                              node.bmin[0], node.bmin[1], node.bmin[2],
                              node.bmax[0], node.bmax[1], node.bmax[2])
            if d < 0 or d >= best_t:
                continue
            if node.is_leaf:
                s = node.tri_start
                e = s + node.tri_count
                for ti_idx in range(s, e):
                    t = int(self.tri_indices[ti_idx])
                    vi0 = int(i_arr[t * 3])
                    vi1 = int(i_arr[t * 3 + 1])
                    vi2 = int(i_arr[t * 3 + 2])
                    v0 = verts3[vi0]
                    v1 = verts3[vi1]
                    v2 = verts3[vi2]
                    t_hit = _moller_trumbore(ox, oy, oz, dx, dy, dz,
                                             v0[0], v0[1], v0[2],
                                             v1[0], v1[1], v1[2],
                                             v2[0], v2[1], v2[2])
                    if t_hit > 0 and t_hit < best_t:
                        best_t = t_hit
            else:
                stack.append(node.right)
                stack.append(node.left)
        return -1.0 if best_t == float("inf") else best_t

    def flatten_for_gpu(self):
        if not self.nodes:
            return None
        n = len(self.nodes)
        buf = np.zeros((n, 8), dtype=np.float32)
        for i, node in enumerate(self.nodes):
            buf[i, 0] = node.bmin[0]
            buf[i, 1] = node.bmin[1]
            buf[i, 2] = node.bmin[2]
            buf[i, 3] = node.bmax[0]
            buf[i, 4] = node.bmax[1]
            buf[i, 5] = node.bmax[2]
            if node.is_leaf:
                buf[i, 6] = float(node.tri_start)
                buf[i, 7] = -float(node.tri_count) - 1.0
            else:
                buf[i, 6] = float(node.left)
                buf[i, 7] = float(node.right)
        return buf

    def node_count(self) -> int:
        return len(self.nodes)

    def depth(self) -> int:
        if not self.nodes:
            return 0

        def _max_depth(ni, d):
            if ni < 0 or ni >= len(self.nodes):
                return d
            node = self.nodes[ni]
            if node.is_leaf:
                return d
            return max(_max_depth(node.left, d + 1), _max_depth(node.right, d + 1))

        return _max_depth(len(self.nodes) - 1, 0)

    @property
    def node_depths(self) -> list[int]:
        if self._cached_depths is None:
            self._cached_depths = _compute_node_depths(self)
        return self._cached_depths

    def enumerate_nodes(self):
        for i, node in enumerate(self.nodes):
            yield i, node


def _ray_aabb_min(ox: float, oy: float, oz: float,
                  dx: float, dy: float, dz: float,
                  bmin_x: float, bmin_y: float, bmin_z: float,
                  bmax_x: float, bmax_y: float, bmax_z: float) -> float:
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


def _moller_trumbore(ox, oy, oz, dx, dy, dz,
                     ax, ay, az, bx, by, bz, cx, cy, cz):
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


_BVH_CACHE: dict[int, BVH] = {}


def get_mesh_bvh(vertices: np.ndarray, indices: np.ndarray) -> BVH | None:
    key = id(vertices)
    if key not in _BVH_CACHE:
        if vertices is None or len(vertices) < 3 or indices is None or len(indices) < 3:
            _BVH_CACHE[key] = None
        else:
            _BVH_CACHE[key] = BVH(vertices, indices)
    return _BVH_CACHE[key]


def _build_bvh_lines(bvh: BVH, depth_filter: int = -1) -> list[tuple]:
    depths = _compute_node_depths(bvh) if depth_filter >= 0 else None
    lines = []
    for ni, node in enumerate(bvh.nodes):
        if depth_filter >= 0:
            if depths[ni] != depth_filter:
                continue
        mn = node.bmin
        mx = node.bmax
        corners = [
            (mn[0], mn[1], mn[2]), (mx[0], mn[1], mn[2]),
            (mx[0], mx[1], mn[2]), (mn[0], mx[1], mn[2]),
            (mn[0], mn[1], mx[2]), (mx[0], mn[1], mx[2]),
            (mx[0], mx[1], mx[2]), (mn[0], mx[1], mx[2]),
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        from core.math3d import Vec3
        frac = ni / max(1, len(bvh.nodes))
        hue = frac * 0.66
        r, g, b = _hsv_to_rgb(hue, 0.8, 0.6 + 0.4 * (1.0 - frac))
        color = [r, g, b]
        for e in edges:
            s = Vec3(*corners[e[0]])
            t = Vec3(*corners[e[1]])
            lines.append((s, t, color))
    return lines


def _node_depth(bvh, ni):
    if ni < 0 or ni >= len(bvh.nodes):
        return 0
    node = bvh.nodes[ni]
    if node.is_leaf:
        return 0
    return 1 + max(_node_depth(bvh, node.left), _node_depth(bvh, node.right))


def _compute_node_depths(bvh):
    depths = [0] * len(bvh.nodes)

    def walk(ni, d):
        if ni < 0 or ni >= len(bvh.nodes):
            return
        depths[ni] = d
        node = bvh.nodes[ni]
        if not node.is_leaf:
            walk(node.left, d + 1)
            walk(node.right, d + 1)

    if bvh.nodes:
        walk(len(bvh.nodes) - 1, 0)
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


_EDGE_PAIRS = np.array([
    0, 1, 1, 2, 2, 3, 3, 0,
    4, 5, 5, 6, 6, 7, 7, 4,
    0, 4, 1, 5, 2, 6, 3, 7,
], dtype=np.intp).reshape(-1, 2)


def build_bvh_arrays(bvh, max_depth: int = -1):
    n = len(bvh.nodes)
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
        for i, node in enumerate(bvh.nodes):
            mn, mx = node.bmin, node.bmax
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
        for i, node in enumerate(bvh.nodes):
            if not mask[i]:
                continue
            mn, mx = node.bmin, node.bmax
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
    r = np.select([h_i == 0, h_i == 1, h_i == 2, h_i == 3, h_i == 4, h_i >= 5],
                  [val, q, p, p, t, val])
    g = np.select([h_i == 0, h_i == 1, h_i == 2, h_i == 3, h_i == 4, h_i >= 5],
                  [t, val, val, q, p, p])
    b = np.select([h_i == 0, h_i == 1, h_i == 2, h_i == 3, h_i == 4, h_i >= 5],
                  [p, p, t, val, val, q])
    colors = np.column_stack([r, g, b])
    colors = np.repeat(colors[:, None, :], 12, axis=1).reshape(-1, 3)
    return starts, ends, colors
