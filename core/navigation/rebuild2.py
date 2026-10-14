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


class RebuildMixin2:
    def _is_grid_current(self) -> bool:
        try:
            if not self._scene:
                return True
            sv = int(getattr(self._scene, '_render_version', -1))
        except Exception:
            return True
        try:
            key = (id(self._scene), int(self._grid.resolution), round(float(self._grid.world_size), 3))
            e = _SHARED_GRIDS.get(key)
            return (e is not None and e[0]() is self._scene and e[1] == sv and not self._grid._dirty)
        except Exception:
            return True

    def wait_grid_ready(self, timeout: float = 30.0) -> bool:
        try:
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < float(timeout):
                try:
                    grid = self._grid
                except Exception:
                    return True
                try:
                    self._poll_rebuild(grid)
                except Exception:
                    pass
                if self._is_grid_current():
                    return True
                try:
                    if not self._scene:
                        return True
                    sv = int(getattr(self._scene, '_render_version', -1))
                    key = (id(self._scene), int(grid.resolution), round(float(grid.world_size), 3))
                except Exception:
                    return True
                try:
                    if grid._rebuild_req is None:
                        self._maybe_pump_rebuild(grid, key, sv, 0.050)
                except Exception:
                    pass
                time.sleep(0.005)
        except Exception:
            pass
        return False

    @_timed("rebuild")
    def _rebuild_grid(self):
        if not self._scene:
            return
        try:
            sv = int(getattr(self._scene, '_render_version', -1))
        except Exception:
            sv = -1
        key = (id(self._scene), int(self._grid.resolution), round(float(self._grid.world_size), 3))
        e = _SHARED_GRIDS.get(key)
        if e is not None and e[0]() is self._scene and e[1] == sv and not self._grid._dirty:
            self._last_scene_version = sv
            return
        if e is not None and e[0]() is self._scene:
            if e[2] is not self._grid:
                self._grid = e[2]
        grid = self._grid
        try:
            self._poll_rebuild(grid)
        except Exception:
            pass
        e = _SHARED_GRIDS.get(key)
        if e is not None and e[0]() is self._scene and e[1] == sv and not grid._dirty:
            self._last_scene_version = sv
            return
        self._last_scene_version = sv
        try:
            if grid._rebuild_req is not None and int(grid._rebuild_sv) == sv:
                return
        except Exception:
            pass
        try:
            self._maybe_pump_rebuild(grid, key, sv, _RB_BUDGET)
        except Exception:
            pass
        try:
            self._release_held_paths(grid)
        except Exception:
            pass

    def _box_obb_tuple(self, comp, tr):
        scale = tr.local_scale
        hx = float(comp.size.x * scale.x * 0.5)
        hy = float(comp.size.y * scale.y * 0.5)
        hz = float(comp.size.z * scale.z * 0.5)
        if hx <= 0.0 or hy <= 0.0 or hz <= 0.0:
            return None
        pos = tr.local_position
        rot = tr.local_rotation
        cl = Vec3(float(comp.center.x * scale.x), float(comp.center.y * scale.y), float(comp.center.z * scale.z))
        c = pos + rot.rotate_vec3(cl)
        return ((float(c.x), float(c.y), float(c.z)), (hx, hy, hz),
                (float(rot._x), float(rot._y), float(rot._z), float(rot._w)))

    def _box_aligned(self, q) -> bool:
        try:
            qx, qy, qz, qw = float(q[0]), float(q[1]), float(q[2]), float(q[3])
            nq = qx * qx + qy * qy + qz * qz + qw * qw
            if nq > 1e-12:
                inv = 1.0 / math.sqrt(nq)
                qx *= inv
                qy *= inv
                qz *= inv
                qw *= inv
            rows = (
                (1.0 - 2.0 * (qy * qy + qz * qz), 2.0 * (qx * qy - qz * qw), 2.0 * (qx * qz + qy * qw)),
                (2.0 * (qx * qy + qz * qw), 1.0 - 2.0 * (qx * qx + qz * qz), 2.0 * (qy * qz - qx * qw)),
                (2.0 * (qx * qz - qy * qw), 2.0 * (qy * qz + qx * qw), 1.0 - 2.0 * (qx * qx + qy * qy)),
            )
            for row in rows:
                if sum(1 for v in row if abs(v) > 0.999999) != 1:
                    return False
            return True
        except Exception:
            return False

    def ignore_entity(self, eid, ignore: bool = True):
        try:
            if ignore:
                self._grid._ignore_eids.add(eid)
            else:
                self._grid._ignore_eids.discard(eid)
        except Exception:
            pass

    def _entity_nav_key(self, entity):
        try:
            eid = entity.id
            if eid is None:
                eid = id(entity)
        except Exception:
            eid = id(entity)
        return eid

    def _collider_comps(self, entity):
        try:
            tm = getattr(entity, "_type_map", None)
            if tm:
                cols = []
                for t, lst in tm.items():
                    try:
                        nm = t.__name__
                    except Exception:
                        continue
                    if nm in _COLLIDER_TYPES and lst:
                        try:
                            for c in lst:
                                if c is not None:
                                    cols.append(c)
                        except Exception:
                            pass
                return cols
            return [c for c in entity.get_all_components()
                    if type(c).__name__ in _COLLIDER_TYPES]
        except Exception:
            return []

    def _world_matrix_rows(self, tr):
        try:
            um = getattr(tr, "_update_world_matrix", None)
            if um is not None:
                um()
            d = tr._world_matrix._d
            return d
        except Exception:
            return None

    def _fp_entry(self, entity, grid, cs, hw, rr, ignore):
        try:
            key = self._entity_nav_key(entity)
        except Exception:
            return None, None
        if key in ignore:
            return key, None
        try:
            cols = self._collider_comps(entity)
        except Exception:
            return None, None
        if not cols:
            return key, None
        m = None
        px = py = pz = 0.0
        local_fallback = False
        try:
            tr = entity.transform
            if tr is None:
                return key, None
            d = self._world_matrix_rows(tr)
            if d is None:
                raise ValueError
            m = tuple(round(float(d[r][c]), 3) for r in range(4) for c in range(4))
            px, py, pz = float(m[12]), float(m[13]), float(m[14])
        except Exception:
            m = None
        if m is None:
            try:
                tr = entity.transform
                if tr is None:
                    return key, None
                lp = tr.local_position
                lr = tr.local_rotation
                ls = tr.local_scale
                px, py, pz = float(lp.x), float(lp.y), float(lp.z)
                m = (round(px, 3), round(py, 3), round(pz, 3),
                     round(float(lr._x), 4), round(float(lr._y), 4),
                     round(float(lr._z), 4), round(float(lr._w), 4),
                     round(float(ls.x), 3), round(float(ls.y), 3), round(float(ls.z), 3))
                local_fallback = True
            except Exception:
                return key, None
        try:
            act = bool(entity.active)
        except Exception:
            act = True
        parts = []
        maxd = 0.0
        for comp in cols:
            try:
                cname = type(comp).__name__
            except Exception:
                continue
            if cname not in _COLLIDER_TYPES:
                continue
            try:
                en = bool(comp.enabled)
            except Exception:
                en = True
            try:
                if cname == "BoxCollider":
                    sz = comp.size
                    cn = comp.center
                    sx, sy, szv = float(sz.x), float(sz.y), float(sz.z)
                    parts.append(("b", round(sx, 3), round(sy, 3), round(szv, 3),
                                  round(float(cn.x), 3), round(float(cn.y), 3), round(float(cn.z), 3), en))
                    dd = (sx * sx + sy * sy + szv * szv) ** 0.5 * 0.5
                    if dd > maxd:
                        maxd = dd
                elif cname == "SphereCollider":
                    cn = comp.center
                    cr = float(comp.radius)
                    parts.append(("s", round(cr, 3),
                                  round(float(cn.x), 3), round(float(cn.y), 3), round(float(cn.z), 3), en))
                    if cr > maxd:
                        maxd = cr
                elif cname == "CapsuleCollider":
                    cn = comp.center
                    cr = float(comp.radius)
                    ch = float(comp.height)
                    parts.append(("c", round(cr, 3), round(ch, 3),
                                  int(getattr(comp, "direction", 1)),
                                  round(float(cn.x), 3), round(float(cn.y), 3), round(float(cn.z), 3), en))
                    dd = ((ch + cr * 2.0) ** 2 + (cr * 2.0) ** 2) ** 0.5 * 0.5
                    if dd > maxd:
                        maxd = dd
                elif cname == "MeshCollider":
                    parts.append(("m", str(getattr(comp, "mesh_path", "")), en))
                    try:
                        mab = self._get_collider_world_aabb(comp)
                        if mab is not None:
                            dd = ((float(mab.max.x - mab.min.x)) ** 2 +
                                  (float(mab.max.y - mab.min.y)) ** 2 +
                                  (float(mab.max.z - mab.min.z)) ** 2) ** 0.5 * 0.5
                            if dd > maxd:
                                maxd = dd
                        else:
                            maxd = 1e30
                    except Exception:
                        maxd = 1e30
            except Exception:
                parts.append((cname, en))
        if not parts:
            return key, None
        try:
            sm = maxd * 1.5 + cs
            if local_fallback:
                sm = sm * 2.0 + cs * 8.0
            gx = max(0, min(rr - 1, int((px + hw) / cs)))
            gy = max(0, min(rr - 1, int((py + hw) / cs)))
            gz = max(0, min(rr - 1, int((pz + hw) / cs)))
            rad = max(1, min(rr, int(sm / cs) + 2))
        except Exception:
            gx, gy, gz, rad = 0, 0, 0, rr
        return key, (act, m, tuple(parts), (gx, gy, gz, rad))
