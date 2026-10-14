# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.maths.math3d import Vec3
from .geometry import AABB, OctreeNode


class Octree:
    def __init__(self, world_size: float = 500.0, max_depth: int = 8, max_objects: int = 8):
        half = world_size * 0.5
        self._root = OctreeNode(Vec3(0, 0, 0), Vec3(half, half, half),
                                0, max_depth, max_objects)
        self._object_count = 0
        self._index: dict = {}

    def update_xyz(self, entity_id: str, cx: float, cy: float, cz: float, rad: float) -> bool:
        node = self._index.get(entity_id)
        if node is None:
            return False
        cur = node.objects.get(entity_id)
        if cur is None:
            return False
        c = node.center
        h = node.half
        x0 = cx - rad
        x1 = cx + rad
        y0 = cy - rad
        y1 = cy + rad
        z0 = cz - rad
        z1 = cz + rad
        if x0 < c._x - h._x or x1 > c._x + h._x or y0 < c._y - h._y or y1 > c._y + h._y or z0 < c._z - h._z or z1 > c._z + h._z:
            return False
        mn = cur.min
        mx = cur.max
        mn._x = x0
        mn._y = y0
        mn._z = z0
        mx._x = x1
        mx._y = y1
        mx._z = z1
        return True

    def insert(self, entity_id: str, aabb: AABB) -> bool:
        old_node = self._index.get(entity_id)
        if old_node is not None:
            try:
                del old_node.objects[entity_id]
            except KeyError:
                pass
            else:
                self._object_count -= 1
            del self._index[entity_id]
        node = self._root
        while True:
            c = node.center
            h = node.half
            nmin = aabb.min
            nmax = aabb.max
            if (nmin._x < c._x - h._x or nmin._y < c._y - h._y or nmin._z < c._z - h._z or
                    nmax._x > c._x + h._x or nmax._y > c._y + h._y or nmax._z > c._z + h._z):
                ex = 0.001
                if (nmin._x < c._x - h._x - ex or nmin._y < c._y - h._y - ex or nmin._z < c._z - h._z - ex or
                        nmax._x > c._x + h._x + ex or nmax._y > c._y + h._y + ex or nmax._z > c._z + h._z + ex):
                    return False
            if node._is_leaf:
                node.objects[entity_id] = aabb
                self._index[entity_id] = node
                self._object_count += 1
                if len(node.objects) > node.max_objects and node.depth < node.max_depth:
                    moved = list(node.objects.items())
                    node.objects.clear()
                    h2 = Vec3(h._x * 0.5, h._y * 0.5, h._z * 0.5)
                    for ox, oy, oz in ((-1, -1, -1), (1, -1, -1), (-1, 1, -1), (1, 1, -1),
                                       (-1, -1, 1), (1, -1, 1), (-1, 1, 1), (1, 1, 1)):
                        node.children.append(OctreeNode(Vec3(c._x + ox * h2._x, c._y + oy * h2._y, c._z + oz * h2._z),
                                                        h2, node.depth + 1, node.max_depth, node.max_objects))
                    node._is_leaf = False
                    for eid, ea in moved:
                        mx = (ea.min._x + ea.max._x) * 0.5
                        my = (ea.min._y + ea.max._y) * 0.5
                        mz = (ea.min._z + ea.max._z) * 0.5
                        ci = 0
                        if mx >= c._x: ci |= 1
                        if my >= c._y: ci |= 2
                        if mz >= c._z: ci |= 4
                        ch = node.children[ci]
                        ch.objects[eid] = ea
                        self._index[eid] = ch
                return True
            mx = (nmin._x + nmax._x) * 0.5
            my = (nmin._y + nmax._y) * 0.5
            mz = (nmin._z + nmax._z) * 0.5
            ci = 0
            if mx >= c._x: ci |= 1
            if my >= c._y: ci |= 2
            if mz >= c._z: ci |= 4
            if ci < len(node.children):
                node = node.children[ci]
            else:
                node.objects[entity_id] = aabb
                self._index[entity_id] = node
                self._object_count += 1
                return True

    def remove(self, entity_id: str) -> bool:
        node = self._index.pop(entity_id, None)
        if node is not None:
            try:
                del node.objects[entity_id]
            except KeyError:
                pass
            else:
                self._object_count -= 1
                return True
            r = self._root.remove(entity_id)
            if r:
                self._object_count -= 1
            return r
        r = self._root.remove(entity_id)
        if r:
            self._object_count -= 1
        return r

    def query(self, aabb: AABB) -> list[str]:
        results = []
        self._root.query(aabb, results)
        return results

    def query_point(self, point: Vec3) -> list[str]:
        results = []
        self._root.query_point(point, results)
        return results

    def raycast(self, origin: Vec3, direction: Vec3, max_dist: float = 100.0) -> list[tuple[str, float]]:
        results = []
        self._root.raycast(origin, direction, max_dist, results)
        results.sort(key=lambda x: x[1])
        return results

    def clear(self):
        self._root.clear()
        self._object_count = 0
        try:
            self._index.clear()
        except AttributeError:
            self._index = {}

    def batch_query_aabb(
        self,
        q_min_x: list[float], q_min_y: list[float], q_min_z: list[float],
        q_max_x: list[float], q_max_y: list[float], q_max_z: list[float],
    ) -> list[list[str]]:
        import numpy as np
        from core._octree_batch import aabb_intersects_point_batch
        n = len(q_min_x)
        results = [[] for _ in range(n)]
        node_aabb = self._root.aabb()
        all_eids = []
        all_aabbs = []
        self._root._collect_all(all_eids, all_aabbs)
        if not all_eids:
            return results
        count = len(all_eids)
        ax = np.empty(count, dtype=np.float64)
        ay = np.empty(count, dtype=np.float64)
        az = np.empty(count, dtype=np.float64)
        bx = np.empty(count, dtype=np.float64)
        by = np.empty(count, dtype=np.float64)
        bz = np.empty(count, dtype=np.float64)
        for i, a in enumerate(all_aabbs):
            ax[i] = a.min.x; ay[i] = a.min.y; az[i] = a.min.z
            bx[i] = a.max.x; by[i] = a.max.y; bz[i] = a.max.z
        for qi in range(n):
            hits = aabb_intersects_point_batch(ax, ay, az, bx, by, bz, q_min_x[qi], q_min_y[qi], q_min_z[qi])
            for j in range(count):
                if hits[j]:
                    a = all_aabbs[j]
                    if (a.min.x <= q_max_x[qi] and a.min.y <= q_max_y[qi] and a.min.z <= q_max_z[qi] and
                            a.max.x >= q_min_x[qi] and a.max.y >= q_min_y[qi] and a.max.z >= q_min_z[qi]):
                        results[qi].append(all_eids[j])
        return results

    def batch_query_point(
        self,
        px: list[float], py: list[float], pz: list[float],
    ) -> list[list[str]]:
        import numpy as np
        from core._octree_batch import aabb_intersects_point_batch
        n = len(px)
        results = [[] for _ in range(n)]
        all_eids = []
        all_aabbs = []
        self._root._collect_all(all_eids, all_aabbs)
        if not all_eids:
            return results
        count = len(all_eids)
        ax = np.empty(count, dtype=np.float64)
        ay = np.empty(count, dtype=np.float64)
        az = np.empty(count, dtype=np.float64)
        bx = np.empty(count, dtype=np.float64)
        by = np.empty(count, dtype=np.float64)
        bz = np.empty(count, dtype=np.float64)
        for i, a in enumerate(all_aabbs):
            ax[i] = a.min.x; ay[i] = a.min.y; az[i] = a.min.z
            bx[i] = a.max.x; by[i] = a.max.y; bz[i] = a.max.z
        for qi in range(n):
            hits = aabb_intersects_point_batch(ax, ay, az, bx, by, bz, px[qi], py[qi], pz[qi])
            for j in range(count):
                if hits[j]:
                    results[qi].append(all_eids[j])
        return results

    def batch_raycast(
        self,
        ox: list[float], oy: list[float], oz: list[float],
        dx: list[float], dy: list[float], dz: list[float],
        max_dist: float = 100.0,
    ) -> list[list[tuple[str, float]]]:
        import numpy as np
        from core._octree_batch import aabb_ray_batch
        n = len(ox)
        results = [[] for _ in range(n)]
        all_eids = []
        all_aabbs = []
        self._root._collect_all(all_eids, all_aabbs)
        if not all_eids:
            return results
        count = len(all_eids)
        ax = np.empty(count, dtype=np.float64)
        ay = np.empty(count, dtype=np.float64)
        az = np.empty(count, dtype=np.float64)
        bx = np.empty(count, dtype=np.float64)
        by = np.empty(count, dtype=np.float64)
        bz = np.empty(count, dtype=np.float64)
        for i, a in enumerate(all_aabbs):
            ax[i] = a.min.x; ay[i] = a.min.y; az[i] = a.min.z
            bx[i] = a.max.x; by[i] = a.max.y; bz[i] = a.max.z
        for qi in range(n):
            dists = aabb_ray_batch(ax, ay, az, bx, by, bz,
                                   np.array([ox[qi]], dtype=np.float64),
                                   np.array([oy[qi]], dtype=np.float64),
                                   np.array([oz[qi]], dtype=np.float64),
                                   np.array([dx[qi]], dtype=np.float64),
                                   np.array([dy[qi]], dtype=np.float64),
                                   np.array([dz[qi]], dtype=np.float64),
                                   max_dist)
            for j in range(count):
                if dists[j] >= 0:
                    results[qi].append((all_eids[j], dists[j]))
            results[qi].sort(key=lambda x: x[1])
        return results

    @property
    def object_count(self) -> int:
        return self._object_count
