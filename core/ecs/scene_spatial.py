# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.spatial import AABB
from .query import _batch_flat, _batch_from_transforms, _collect_dirty, _batch_flat_soa, _batch_from_soa


def _get_entity_depth(scene, e: Entity) -> int:
    eid = e._id
    cached = scene._depth_cache.get(eid)
    if cached is not None:
        return cached
    depth = 0
    p = e._parent
    while p is not None:
        depth += 1
        p = p._parent
    scene._depth_cache[eid] = depth
    return depth


def _get_entity_depth_key(scene, t):
    e = t._entity
    if e is None:
        return 0
    d = scene._depth_cache.get(e._id)
    if d is not None:
        return d
    return 0


def take_flushed_transforms(scene):
    lst = scene._last_flushed
    if not lst:
        return lst
    scene._last_flushed = []
    scene._last_flushed_set.clear()
    return lst


def peek_flushed_transforms(scene):
    return scene._last_flushed


def flush_transforms(scene):
    dr = scene._dirty_roots
    if not dr:
        if scene._transform_version_pending:
            scene._transform_version += 1
            scene._transform_version_pending = False
        return 0
    if scene._transform_version_pending:
        scene._transform_version += 1
        scene._transform_version_pending = False
    roots = list(dr)
    dr.clear()
    flat = []
    hier = []
    flat_tgt = []
    flat_append = flat.append
    hier_append = hier.append
    flat_tgt_append = flat_tgt.append
    for t in roots:
        if not t._dirty:
            continue
        ent = t._entity
        if ent is None:
            continue
        if ent._parent is not None or ent._children:
            hier_append(t)
        elif t._world_target is not None:
            flat_tgt_append(t)
        else:
            flat_append(t)
    count = 0
    bf = _batch_flat
    bft = _batch_from_transforms
    need_soa = scene._soa_cap > 0 and scene._soa_needed()
    if flat:
        nflat = len(flat)
        if nflat == 1:
            flat[0]._update_world_matrix()
        elif bf is not None:
            if need_soa and _batch_flat_soa is not None:
                _batch_flat_soa(flat, scene._soa_world, scene._soa_cap)
            else:
                bf(flat)
                if need_soa:
                    scene._soa_sync_many_flushed(flat)
        else:
            for t in flat:
                t._update_world_matrix()
        count += nflat
    if flat_tgt:
        for t in flat_tgt:
            t._update_world_matrix()
        count += len(flat_tgt)
    if hier:
        nhier = len(hier)
        if nhier == 1:
            hier[0]._update_world_matrix()
        else:
            if _collect_dirty is not None:
                try:
                    hier = _collect_dirty(hier)
                except Exception:
                    dc = scene._depth_cache
                    dc_get = dc.get
                    for t in hier:
                        e = t._entity
                        if e is None:
                            continue
                        eid = e._id
                        if dc_get(eid) is None:
                            depth = 0
                            p = e._parent
                            while p is not None:
                                depth += 1
                                p = p._parent
                            dc[eid] = depth
                    hier.sort(key=lambda t: _get_entity_depth_key(scene, t))
            else:
                dc = scene._depth_cache
                dc_get = dc.get
                for t in hier:
                    e = t._entity
                    if e is None:
                        continue
                    eid = e._id
                    if dc_get(eid) is None:
                        depth = 0
                        p = e._parent
                        while p is not None:
                            depth += 1
                            p = p._parent
                        dc[eid] = depth
                hier.sort(key=lambda t: _get_entity_depth_key(scene, t))
            has_target = False
            for t in hier:
                if t._world_target is not None:
                    has_target = True
                    break
            if has_target:
                for t in hier:
                    t._update_world_matrix()
            elif bft is not None:
                if need_soa and _batch_from_soa is not None:
                    _batch_from_soa(hier, scene._soa_world, scene._soa_cap)
                else:
                    bft(hier)
                    if need_soa:
                        scene._soa_sync_many_flushed(hier)
            else:
                for t in hier:
                    t._update_world_matrix()
        count += nhier
    if roots:
        nroots = len(roots)
        lf = scene._last_flushed
        lfs = scene._last_flushed_set
        total = len(lf) + nroots
        if total > 32768:
            scene._last_flushed = []
            lfs.clear()
            scene._flushed_overflow = True
        else:
            for t in roots:
                if t not in lfs:
                    lfs.add(t)
                    lf.append(t)
    return count


def _insert_spatial_single(scene, e):
    from core.maths.math3d import Vec3
    tr = e._transform
    if tr is None:
        tr = e.transform
        if tr is None:
            return
    if tr._dirty:
        tr._update_world_matrix()
    d = tr._world_matrix._d
    cx = float(d[3, 0])
    cy = float(d[3, 1])
    cz = float(d[3, 2])
    scene._spatial.insert(e._id, AABB(Vec3(cx - 2.5, cy - 2.5, cz - 2.5), Vec3(cx + 2.5, cy + 2.5, cz + 2.5)))


def rebuild_spatial(scene):
    if not scene._spatial_dirty:
        return
    flush_transforms(scene)
    from core.maths.math3d import Vec3
    try:
        from core.components.rendering.renderers.mesh_filter import MeshFilter as _MF
        from core.components.rendering.renderers.mesh_renderer import MeshRenderer as _MR
    except ImportError:
        _MF = None
        _MR = None
    meshes = None
    try:
        from core.engine.eng import Engine as _Eng
        _eng = _Eng.instance()
        _r = getattr(_eng, "_renderer", None) if _eng else None
        if _r is None and _eng is not None:
            _vp = getattr(_eng, "viewport", None)
            if _vp is not None:
                _r = getattr(_vp, "_renderer", None)
        if _r is not None:
            meshes = getattr(_r, "_meshes", None)
    except Exception:
        meshes = None
    radius_cache: dict = {}
    spatial = scene._spatial
    dirty = scene._spatial_dirty_entities
    flushed = scene._last_flushed
    try:
        overflow = bool(scene._flushed_overflow)
    except Exception:
        overflow = False
    nent = len(scene._entities)
    use_flushed = flushed and not overflow
    nd = len(dirty) if dirty else 0
    nf = len(flushed) if use_flushed else 0
    if (nd + nf) > 0 and (nd + nf) < nent * 0.6:
        get_e = scene._entities.get
        done = set()
        done_add = done.add
        if dirty:
            for eid in list(dirty):
                e = get_e(eid)
                if e is None or not e._active:
                    continue
                tr = e._transform
                if tr is None:
                    tr = e.transform
                    if tr is None:
                        continue
                d = tr._world_matrix._d
                cx = float(d[3, 0])
                cy = float(d[3, 1])
                cz = float(d[3, 2])
                rad = 2.5
                if _MF is not None and meshes is not None:
                    ml = e._type_map.get(_MF)
                    if ml:
                        mf = ml[0]
                        rl = e._type_map.get(_MR)
                        mr = rl[0] if rl else None
                        if mr is not None and mr.enabled:
                            name = mf.mesh_name or "cube"
                            r0 = radius_cache.get(name)
                            if r0 is None:
                                m = meshes.get(name)
                                if m is None and mf.mesh_path:
                                    m = meshes.get(mf.mesh_path)
                                try:
                                    r0 = float(getattr(m, "bounding_radius", 2.5)) if m is not None else 2.5
                                except Exception:
                                    r0 = 2.5
                                radius_cache[name] = r0
                            sx = d[0, 0] * d[0, 0] + d[1, 0] * d[1, 0] + d[2, 0] * d[2, 0]
                            sy = d[0, 1] * d[0, 1] + d[1, 1] * d[1, 1] + d[2, 1] * d[2, 1]
                            sz = d[0, 2] * d[0, 2] + d[1, 2] * d[1, 2] + d[2, 2] * d[2, 2]
                            ms = sx
                            if sy > ms:
                                ms = sy
                            if sz > ms:
                                ms = sz
                            ms = ms ** 0.5
                            rad = r0 * ms + 0.5
                if spatial.update_xyz(eid, cx, cy, cz, rad):
                    done_add(eid)
                    continue
                spatial.remove(eid)
                spatial.insert(eid, AABB(Vec3(cx - rad, cy - rad, cz - rad), Vec3(cx + rad, cy + rad, cz + rad)))
                done_add(eid)
        if use_flushed:
            for t in flushed:
                e = t._entity
                if e is None:
                    continue
                eid = e._id
                if eid in done:
                    continue
                if not e._active:
                    continue
                d = t._world_matrix._d
                cx = float(d[3, 0])
                cy = float(d[3, 1])
                cz = float(d[3, 2])
                rad = 2.5
                if _MF is not None and meshes is not None:
                    ml = e._type_map.get(_MF)
                    if ml:
                        mf = ml[0]
                        rl = e._type_map.get(_MR)
                        mr = rl[0] if rl else None
                        if mr is not None and mr.enabled:
                            name = mf.mesh_name or "cube"
                            r0 = radius_cache.get(name)
                            if r0 is None:
                                m = meshes.get(name)
                                if m is None and mf.mesh_path:
                                    m = meshes.get(mf.mesh_path)
                                try:
                                    r0 = float(getattr(m, "bounding_radius", 2.5)) if m is not None else 2.5
                                except Exception:
                                    r0 = 2.5
                                radius_cache[name] = r0
                            sx = d[0, 0] * d[0, 0] + d[1, 0] * d[1, 0] + d[2, 0] * d[2, 0]
                            sy = d[0, 1] * d[0, 1] + d[1, 1] * d[1, 1] + d[2, 1] * d[2, 1]
                            sz = d[0, 2] * d[0, 2] + d[1, 2] * d[1, 2] + d[2, 2] * d[2, 2]
                            ms = sx
                            if sy > ms:
                                ms = sy
                            if sz > ms:
                                ms = sz
                            ms = ms ** 0.5
                            rad = r0 * ms + 0.5
                if spatial.update_xyz(eid, cx, cy, cz, rad):
                    continue
                spatial.remove(eid)
                spatial.insert(eid, AABB(Vec3(cx - rad, cy - rad, cz - rad), Vec3(cx + rad, cy + rad, cz + rad)))
        dirty.clear()
        if not dirty:
            scene._spatial_dirty = False
        return
    scene._spatial.clear()
    scene._spatial_known_entities.clear()
    known_add = scene._spatial_known_entities.add
    for e in scene._ensure_entities_cache():
        if not e._active:
            continue
        tr = e._transform
        if tr is None:
            tr = e.transform
            if tr is None:
                continue
        d = tr._world_matrix._d
        cx = float(d[3, 0])
        cy = float(d[3, 1])
        cz = float(d[3, 2])
        rad = 2.5
        if _MF is not None and meshes is not None:
            ml = e._type_map.get(_MF)
            if ml:
                mf = ml[0]
                rl = e._type_map.get(_MR)
                mr = rl[0] if rl else None
                if mr is not None and mr.enabled:
                    name = mf.mesh_name or "cube"
                    r0 = radius_cache.get(name)
                    if r0 is None:
                        m = meshes.get(name)
                        if m is None and mf.mesh_path:
                            m = meshes.get(mf.mesh_path)
                        try:
                            r0 = float(getattr(m, "bounding_radius", 2.5)) if m is not None else 2.5
                        except Exception:
                            r0 = 2.5
                        radius_cache[name] = r0
                    try:
                        sx = d[0, 0] * d[0, 0] + d[1, 0] * d[1, 0] + d[2, 0] * d[2, 0]
                        sy = d[0, 1] * d[0, 1] + d[1, 1] * d[1, 1] + d[2, 1] * d[2, 1]
                        sz = d[0, 2] * d[0, 2] + d[1, 2] * d[1, 2] + d[2, 2] * d[2, 2]
                        ms = sx
                        if sy > ms:
                            ms = sy
                        if sz > ms:
                            ms = sz
                        ms = ms ** 0.5
                    except Exception:
                        ms = 1.0
                    rad = r0 * ms + 0.5
        spatial.insert(e._id, AABB(Vec3(cx - rad, cy - rad, cz - rad), Vec3(cx + rad, cy + rad, cz + rad)))
        known_add(e._id)
    dirty.clear()
    scene._spatial_dirty = False


def spatial_query(scene, aabb) -> list:
    if scene._spatial_dirty:
        rebuild_spatial(scene)
    return scene._spatial.query(aabb)


def spatial_raycast(scene, origin, direction, max_dist: float = 100.0) -> list:
    if scene._spatial_dirty:
        rebuild_spatial(scene)
    return scene._spatial.raycast(origin, direction, max_dist)


def mark_spatial_dirty(scene):
    scene._spatial_dirty = True
