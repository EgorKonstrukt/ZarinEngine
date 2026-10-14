# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import threading
import time
import heapq
import uuid
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3
from core.spatial.octp import AABB
from .grid import NavGrid, NavRect
from .stats import _stat, _timed
from .epoch import _bump_epoch, _current_epoch, _grid_snapshot, _GRID_LOCK
from .raster import _rasterize_descs_fresh, _shared_grid_for, _coarse_cached, _get_nav_worker, _COLLIDER_TYPES
from .raster import _SHARED_GRIDS
try:
    from core import _nav_batch as _nb
    _HAS_NAV_CYTHON = True
except ImportError:
    _nb = None
    _HAS_NAV_CYTHON = False
from .rebuild import _DYN_SCAN_DT, _RASTER_MIN_DT, _RB_BUDGET


class RebuildMixin4:
    def _submit_raster(self, grid, changed: dict, now: float):
        try:
            r = grid.resolution
            cs = grid.cell_size
            hw = grid.half_world
            try:
                descs_cache = grid._dyn_descs
            except Exception:
                descs_cache = {}
                grid._dyn_descs = descs_cache
            try:
                x1, y1, z1 = r, r, r
                x2, y2, z2 = -1, -1, -1
                descs = []
                for key, item in changed.items():
                    try:
                        old, new, ent = item
                    except Exception:
                        continue
                    for ce in (old[3] if old is not None else None,
                               new[3] if new is not None else None):
                        if ce is None:
                            continue
                        try:
                            x1 = min(x1, max(0, ce[0] - ce[3]))
                            y1 = min(y1, max(0, ce[1] - ce[3]))
                            z1 = min(z1, max(0, ce[2] - ce[3]))
                            x2 = max(x2, min(r - 1, ce[0] + ce[3]))
                            y2 = max(y2, min(r - 1, ce[1] + ce[3]))
                            z2 = max(z2, min(r - 1, ce[2] + ce[3]))
                        except Exception:
                            pass
                    try:
                        if new is None:
                            try:
                                descs_cache.pop(key, None)
                            except Exception:
                                pass
                        else:
                            ed = self._entity_descs(ent, grid)
                            descs_cache[key] = ed
                    except Exception:
                        pass
                if x1 > x2:
                    return False
                for dl in descs_cache.values():
                    try:
                        for d in dl:
                            descs.append(d)
                    except Exception:
                        pass
                vol = (x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1)
                region = None
                if len(changed) <= 200 and vol <= r * r * r // 4:
                    region = ((x1, y1, z1, x2, y2, z2),
                              (x1 * cs - hw, y1 * cs - hw, z1 * cs - hw,
                               (x2 + 1) * cs - hw, (y2 + 1) * cs - hw, (z2 + 1) * cs - hw))
                grid._raster_seq = int(grid._raster_seq) + 1
                try:
                    _gen = int(grid._grid_gen)
                except Exception:
                    _gen = 0
                spec = {"kind": "raster", "req": "__raster_%d" % int(grid._raster_seq),
                        "shell": grid, "descs": descs,
                        "res": int(r), "cell": float(cs), "half": float(hw),
                        "seq": int(grid._raster_seq), "region": region, "gen": _gen}
                _get_nav_worker().submit(spec)
                grid._raster_time = now
                return True
            except Exception:
                return False
        except Exception:
            return False

    def _get_collider_world_aabb(self, comp) -> Optional[AABB]:
        entity = comp._entity
        if not entity:
            return None
        tr = entity.transform
        if not tr:
            return None
        pos = tr.local_position
        rot = tr.local_rotation
        scale = tr.local_scale
        cname = type(comp).__name__

        if cname == "BoxCollider":
            try:
                d = self._world_matrix_rows(tr)
                if d is not None:
                    R = np.asarray(d[:3, :3], dtype=np.float64)
                    t = np.asarray(d[3, :3], dtype=np.float64).ravel()
                    if R.shape == (3, 3) and t.shape == (3,) and np.all(np.isfinite(R)) and np.all(np.isfinite(t)):
                        cl0 = np.array([float(comp.center.x), float(comp.center.y), float(comp.center.z)])
                        h0 = np.array([float(comp.size.x) * 0.5, float(comp.size.y) * 0.5, float(comp.size.z) * 0.5])
                        cw = cl0 @ R + t
                        e = np.abs(R).T @ h0
                        return AABB(Vec3(float(cw[0] - e[0]), float(cw[1] - e[1]), float(cw[2] - e[2])),
                                    Vec3(float(cw[0] + e[0]), float(cw[1] + e[1]), float(cw[2] + e[2])))
            except Exception:
                pass
            hx = comp.size.x * scale.x * 0.5
            hy = comp.size.y * scale.y * 0.5
            hz = comp.size.z * scale.z * 0.5
            cl = Vec3(comp.center.x * scale.x, comp.center.y * scale.y, comp.center.z * scale.z)
            c = pos + rot.rotate_vec3(cl)
            local_corners = [
                Vec3(-hx, -hy, -hz), Vec3(hx, -hy, -hz), Vec3(-hx, hy, -hz), Vec3(hx, hy, -hz),
                Vec3(-hx, -hy, hz), Vec3(hx, -hy, hz), Vec3(-hx, hy, hz), Vec3(hx, hy, hz),
            ]
            ws = [c + rot.rotate_vec3(lc) for lc in local_corners]
            bmin = Vec3(min(v.x for v in ws), min(v.y for v in ws), min(v.z for v in ws))
            bmax = Vec3(max(v.x for v in ws), max(v.y for v in ws), max(v.z for v in ws))
            return AABB(bmin, bmax)
        elif cname == "SphereCollider":
            r = comp.radius * max(scale.x, scale.y, scale.z)
            c = pos + rot.rotate_vec3(Vec3(comp.center.x * scale.x, comp.center.y * scale.y, comp.center.z * scale.z))
            return AABB(c - Vec3(r, r, r), c + Vec3(r, r, r))
        elif cname == "CapsuleCollider":
            r = comp.radius
            hh = comp.height * 0.5
            cl = Vec3(comp.center.x * scale.x, comp.center.y * scale.y, comp.center.z * scale.z)
            c = pos + rot.rotate_vec3(cl)
            if comp.direction == 1:
                axis_local = Vec3(0, hh * scale.y, 0)
            elif comp.direction == 0:
                axis_local = Vec3(hh * scale.x, 0, 0)
            else:
                axis_local = Vec3(0, 0, hh * scale.z)
            rs = r * max(scale.x, scale.y, scale.z)
            axis_world = rot.rotate_vec3(axis_local)
            a = c + axis_world
            b = c - axis_world
            rv = Vec3(rs, rs, rs)
            aabb_a = AABB(a - rv, a + rv)
            aabb_b = AABB(b - rv, b + rv)
            return AABB(
                Vec3(min(aabb_a.min.x, aabb_b.min.x), min(aabb_a.min.y, aabb_b.min.y), min(aabb_a.min.z, aabb_b.min.z)),
                Vec3(max(aabb_a.max.x, aabb_b.max.x), max(aabb_a.max.y, aabb_b.max.y), max(aabb_a.max.z, aabb_b.max.z)),
            )
        elif cname == "MeshCollider":
            if hasattr(comp, 'mesh_path') and comp.mesh_path:
                try:
                    from core.engine.eng import Engine
                    eng = Engine.instance()
                    if eng and hasattr(eng, '_renderer') and eng._renderer:
                        mesh = eng._renderer._meshes.get(comp.mesh_path)
                        if mesh and hasattr(mesh, 'aabb_min') and hasattr(mesh, 'aabb_max'):
                            corners = np.array([
                                [mesh.aabb_min[i] for i in range(3)] + [1],
                                [mesh.aabb_max[0], mesh.aabb_min[1], mesh.aabb_min[2], 1],
                                [mesh.aabb_max[0], mesh.aabb_max[1], mesh.aabb_min[2], 1],
                                [mesh.aabb_min[0], mesh.aabb_max[1], mesh.aabb_min[2], 1],
                                [mesh.aabb_min[0], mesh.aabb_min[1], mesh.aabb_max[2], 1],
                                [mesh.aabb_max[0], mesh.aabb_min[1], mesh.aabb_max[2], 1],
                                [mesh.aabb_max[0], mesh.aabb_max[1], mesh.aabb_max[2], 1],
                                [mesh.aabb_min[0], mesh.aabb_max[1], mesh.aabb_max[2], 1],
                            ], dtype=np.float32)
                            wm = tr.world_matrix._d
                            pts = corners @ wm
                            bmin = pts[:, :3].min(axis=0)
                            bmax = pts[:, :3].max(axis=0)
                            return AABB(Vec3(float(bmin[0]), float(bmin[1]), float(bmin[2])),
                                        Vec3(float(bmax[0]), float(bmax[1]), float(bmax[2])))
                except Exception:
                    pass
            return None
        return None

    def rebuild_grid(self):
        self._rebuild_grid()

    def dilate_for_agent(self, radius: float):
        try:
            self._fly_dilate = max(0.0, float(radius))
        except Exception:
            self._fly_dilate = None

    def _submit_or_hold(self, spec):
        grid = self._grid
        hold = False
        try:
            if not grid._built_once and (grid._rb_job is not None or grid._rebuild_req is not None):
                hold = True
        except Exception:
            hold = False
        if hold:
            try:
                hp = grid._held_paths
            except Exception:
                hp = None
            if hp is None:
                try:
                    grid._held_paths = hp = []
                except Exception:
                    hp = None
            if hp is not None:
                hp.append(spec)
                while len(hp) > 32:
                    try:
                        old = hp.pop(0)
                        try:
                            self._pending_results[old.get("req", "")] = []
                        except Exception:
                            pass
                        try:
                            self._pending_jobs.pop(old.get("req", ""), None)
                        except Exception:
                            pass
                    except Exception:
                        break
                return
        _get_nav_worker().submit(spec)

    def _release_held_paths(self, grid) -> bool:
        try:
            hp = grid._held_paths
            if not hp:
                return False
        except Exception:
            return False
        try:
            ready = bool(grid._built_once)
            if not ready:
                try:
                    ready = grid._rb_job is None and grid._rebuild_req is None
                except Exception:
                    ready = True
            if not ready:
                return False
        except Exception:
            return False
        try:
            arr, ep = _grid_snapshot(grid)
        except Exception:
            return False
        try:
            specs = list(hp)
            del hp[:]
        except Exception:
            return False
        for spec in specs:
            try:
                spec["grid"] = arr
                spec["gid"] = id(arr)
                spec["gv"] = ep
                _get_nav_worker().submit(spec)
            except Exception:
                pass
        return True
