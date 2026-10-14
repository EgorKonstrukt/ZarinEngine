# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
_GIZMO_INST_CACHE: dict = {}
_FAST_COLLIDER_NAMES = ("BoxCollider", "SphereCollider", "CapsuleCollider")
_FAST_D = None
_FAST_COL_CACHE: dict = {}
_FAST_COL_CACHE_MAX: int = 4
def _fast_buf():
    global _FAST_D
    try:
        d = _FAST_D
        if d is None:
            from array import array as _array
            d = _array("d")
            _FAST_D = d
        return d
    except Exception:
        return None
def _collider_row(shape, tr, comp):
    try:
        lp = tr._local_pos
        lr = tr._local_rot
        ls = tr._local_scale
        ce = comp.center
        if shape == "box":
            sz = comp.size
            ex = sz._x * 0.5
            ey = sz._y * 0.5
            ez = sz._z * 0.5
            cx = ce._x
            cy = ce._y
            cz = ce._z
        elif shape == "sphere":
            ms = ls._x
            if ls._y > ms:
                ms = ls._y
            if ls._z > ms:
                ms = ls._z
            r = comp.radius * ms
            ex = r
            ey = r
            ez = r
            cx = ce._x * ls._x
            cy = ce._y * ls._y
            cz = ce._z * ls._z
        else:
            hh = comp.height * 0.5 - comp.radius
            if hh < 0.0:
                hh = 0.0
            ex = comp.radius
            ey = comp.radius
            ez = comp.radius
            dd = comp.direction
            if dd == 0:
                ex = hh + comp.radius
            elif dd == 1:
                ey = hh + comp.radius
            else:
                ez = hh + comp.radius
            cx = ce._x
            cy = ce._y
            cz = ce._z
        return (lp._x, lp._y, lp._z, lr._x, lr._y, lr._z, lr._w,
                ls._x, ls._y, ls._z, cx, cy, cz, ex, ey, ez)
    except Exception:
        return None
_BOX_EDGE_IDXS = np.array([
    [0,1],[1,2],[2,3],[3,0],
    [4,5],[5,6],[6,7],[7,4],
    [0,4],[1,5],[2,6],[3,7]
], dtype=np.int32)
def _box_edges_np(bmin, bmax):
    cx, cy, cz = float(bmin[0]), float(bmin[1]), float(bmin[2])
    dx, dy, dz = float(bmax[0]), float(bmax[1]), float(bmax[2])
    corners = np.array([
        [cx, cy, cz], [dx, cy, cz], [dx, dy, cz], [cx, dy, cz],
        [cx, cy, dz], [dx, cy, dz], [dx, dy, dz], [cx, dy, dz],
    ], dtype=np.float32)
    return corners[_BOX_EDGE_IDXS[:, 0]], corners[_BOX_EDGE_IDXS[:, 1]]
def _build_unit_sphere_cache_np(segments=8):
    verts = []
    idx = []
    for lat in range(segments):
        theta1 = math.pi * lat / segments
        theta2 = math.pi * (lat + 1) / segments
        for lon in range(segments):
            phi1 = 2.0 * math.pi * lon / segments
            phi2 = 2.0 * math.pi * (lon + 1) / segments
            s = math.sin
            c = math.cos
            p0 = (s(theta1)*c(phi1), c(theta1), s(theta1)*s(phi1))
            p1 = (s(theta1)*c(phi2), c(theta1), s(theta1)*s(phi2))
            p2 = (s(theta2)*c(phi2), c(theta2), s(theta2)*s(phi2))
            p3 = (s(theta2)*c(phi1), c(theta2), s(theta2)*s(phi1))
            i0 = len(verts)
            verts.extend([p0, p1, p2, p3])
            idx.extend([i0, i0+1, i0+2, i0, i0+2, i0+3])
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.int32)
def _render_corner_spheres_np(vp, vp_mat, corners, radius, color):
    cache = getattr(_render_corner_spheres_np, '_cache', None)
    if cache is None:
        cache = _build_unit_sphere_cache_np(8)
        _render_corner_spheres_np._cache = cache
    cverts, cidx = cache
    nv = cverts.shape[0]
    nc = len(corners)
    corner_pts = np.array([[c.x, c.y, c.z] for c in corners], dtype=np.float64)
    all_verts = corner_pts[:, None, :] + cverts[None, :, :].astype(np.float64) * float(radius)
    all_verts = all_verts.reshape(-1, 3)
    n_total = nc * nv
    all_idx = np.tile(cidx, nc) + np.repeat(np.arange(nc, dtype=np.int32) * nv, len(cidx))
    v_data = np.empty((n_total, 7), dtype=np.float64)
    v_data[:, :3] = all_verts
    v_data[:, 3] = color[0]; v_data[:, 4] = color[1]
    v_data[:, 5] = color[2]; v_data[:, 6] = color[3]
    vp._renderer.render_gizmo_mesh_np(v_data, np.asarray(all_idx, dtype=np.uint32), vp_mat, cam_pos=vp._cam.position if vp._cam else None)
def _fast_aggregate_bounds(vp, entities):
    try:
        from editor.viewport.pick import _get_mesh_for
    except Exception:
        _get_mesh_for = None
    try:
        from core import _raycast as _rc
    except Exception:
        _rc = None
    n_in = len(entities)
    if n_in == 0:
        return None, None
    meshes = None
    prefix_map = None
    cube_mesh = None
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        renderer = getattr(eng, "_renderer", None)
        if renderer is None:
            vpe = getattr(eng, "viewport", None)
            if vpe is not None:
                renderer = getattr(vpe, "_renderer", None)
        if renderer is not None:
            meshes = getattr(renderer, "_meshes", None)
    except Exception:
        meshes = None
    if meshes:
        try:
            prefix_map = {}
            for mk in meshes.keys():
                base = mk.split("|", 1)[0]
                if base not in prefix_map:
                    prefix_map[base] = mk
            cube_mesh = meshes.get("cube")
        except Exception:
            prefix_map = None
    cache = getattr(vp, "_sel_mesh_cache", None)
    if cache is None:
        cache = {}
        vp._sel_mesh_cache = cache
    if len(cache) > 30000:
        cache.clear()
    filt_wm = []
    filt_scale = []
    batch_lmin = []
    batch_lmax = []
    batch_wm = []
    batch_pos = []
    fall_idx = []
    fall_min = []
    fall_max = []
    for entity in entities:
        if entity is None:
            continue
        try:
            comps = entity._components
        except Exception:
            continue
        skip = False
        try:
            for k in comps.keys():
                if k == "Bone" or k.startswith("Bone."):
                    skip = True
                    break
        except Exception:
            pass
        if skip:
            continue
        t = getattr(entity, "_transform", None)
        if t is None:
            try:
                t = entity.transform
            except Exception:
                continue
            if t is None:
                continue
        try:
            wm = t._world_matrix._d
            if getattr(t, "_dirty", False):
                wm = t.world_matrix._d
        except Exception:
            try:
                wm = t.world_matrix._d
            except Exception:
                continue
        eid = getattr(entity, "_id", None) or getattr(entity, "id", None)
        lmin = None
        lmax = None
        resolved = False
        try:
            mf = comps.get("MeshFilter")
            mr = comps.get("MeshRenderer")
            smr = comps.get("SkinnedMeshRenderer")
            use_mf = mf is not None and mr is not None and getattr(mr, "_enabled", True)
            use_smr = False
            if not use_mf:
                if smr is not None and getattr(smr, "_enabled", True):
                    use_smr = True
            if use_mf or use_smr:
                src = mf if use_mf else smr
                try:
                    mname = getattr(src, "mesh_name", None) or "cube"
                except Exception:
                    mname = "cube"
                try:
                    mpath = getattr(src, "mesh_path", None) or ""
                except Exception:
                    mpath = ""
                cached = cache.get(eid) if eid is not None else None
                if cached is not None and cached[0] == mname and cached[1] == mpath and cached[4]:
                    lmin = cached[2]
                    lmax = cached[3]
                    resolved = True
                elif meshes is not None:
                    mesh_obj = meshes.get(mname)
                    if mesh_obj is None and mpath:
                        mesh_obj = meshes.get(mpath)
                    if mesh_obj is None and prefix_map is not None and mname and mname != "cube":
                        pk = prefix_map.get(mname)
                        if pk is not None:
                            mesh_obj = meshes.get(pk)
                    if mesh_obj is None and mpath and prefix_map is not None:
                        pk = prefix_map.get(mpath)
                        if pk is not None:
                            mesh_obj = meshes.get(pk)
                    if mesh_obj is None:
                        mesh_obj = cube_mesh
                    if mesh_obj is not None:
                        try:
                            lmin = mesh_obj.aabb_min
                            lmax = mesh_obj.aabb_max
                            lmin = (float(lmin[0]), float(lmin[1]), float(lmin[2]))
                            lmax = (float(lmax[0]), float(lmax[1]), float(lmax[2]))
                            resolved = True
                        except Exception:
                            lmin = None
                            lmax = None
                            resolved = False
                    if eid is not None:
                        try:
                            cache[eid] = (mname, mpath, lmin, lmax, bool(resolved))
                        except Exception:
                            pass
            if not resolved:
                spr = comps.get("SpriteRenderer")
                if spr is not None and getattr(spr, "_enabled", True) and getattr(spr, "texture_path", None):
                    lmin = (-0.5, -0.5, 0.0)
                    lmax = (0.5, 0.5, 0.0)
                    resolved = True
                else:
                    vr = comps.get("VideoRenderer")
                    if vr is not None and getattr(vr, "_enabled", True) and getattr(vr, "video_path", None):
                        lmin = (-0.5, -0.5, 0.0)
                        lmax = (0.5, 0.5, 0.0)
                        resolved = True
        except Exception:
            resolved = False
            lmin = None
        if resolved and lmin is not None and lmax is not None:
            batch_lmin.append(lmin)
            batch_lmax.append(lmax)
            batch_wm.append(wm)
            batch_pos.append(len(filt_wm) + len(fall_idx) + len(batch_lmin) - 1)
        else:
            try:
                px = float(wm[3, 0])
                py = float(wm[3, 1])
                pz = float(wm[3, 2])
            except Exception:
                continue
            try:
                ls = t._local_scale
                hx = abs(float(ls.x)) * 0.5
                hy = abs(float(ls.y)) * 0.5
                hz = abs(float(ls.z)) * 0.5
                half = hx
                if hy > half:
                    half = hy
                if hz > half:
                    half = hz
                if half < 0.5:
                    half = 0.5
            except Exception:
                half = 0.5
                try:
                    px = float(wm[3, 0])
                    py = float(wm[3, 1])
                    pz = float(wm[3, 2])
                except Exception:
                    continue
            fall_idx.append(len(filt_wm) + len(batch_lmin) + len(fall_min))
            fall_min.append((px - half, py - half, pz - half))
            fall_max.append((px + half, py + half, pz + half))
    n_batch = len(batch_lmin)
    n_fall = len(fall_min)
    n_total = n_batch + n_fall
    if n_total == 0:
        return None, None
    wmins = np.empty((n_total, 3), dtype=np.float64)
    wmaxs = np.empty((n_total, 3), dtype=np.float64)
    if n_fall:
        wmins[n_batch:, 0] = [v[0] for v in fall_min]
        wmins[n_batch:, 1] = [v[1] for v in fall_min]
        wmins[n_batch:, 2] = [v[2] for v in fall_min]
        wmaxs[n_batch:, 0] = [v[0] for v in fall_max]
        wmaxs[n_batch:, 1] = [v[1] for v in fall_max]
        wmaxs[n_batch:, 2] = [v[2] for v in fall_max]
    if n_batch:
        try:
            bm = np.array(batch_lmin, dtype=np.float64)
            bx = np.array(batch_lmax, dtype=np.float64)
            mw = np.array(batch_wm, dtype=np.float64)
            if _rc is not None:
                rmn, rmx = _rc.world_aabbs(bm, bx, mw)
                wmins[:n_batch] = rmn
                wmaxs[:n_batch] = rmx
            else:
                for k in range(n_batch):
                    corners = np.array([
                        [bm[k, 0], bm[k, 1], bm[k, 2], 1.0],
                        [bx[k, 0], bm[k, 1], bm[k, 2], 1.0],
                        [bm[k, 0], bx[k, 1], bm[k, 2], 1.0],
                        [bm[k, 0], bm[k, 1], bx[k, 2], 1.0],
                        [bx[k, 0], bx[k, 1], bm[k, 2], 1.0],
                        [bx[k, 0], bm[k, 1], bx[k, 2], 1.0],
                        [bm[k, 0], bx[k, 1], bx[k, 2], 1.0],
                        [bx[k, 0], bx[k, 1], bx[k, 2], 1.0],
                    ], dtype=np.float64) @ mw[k]
                    wmins[k] = corners[:, :3].min(axis=0)
                    wmaxs[k] = corners[:, :3].max(axis=0)
        except Exception:
            for k in range(n_batch):
                try:
                    wm = batch_wm[k]
                    px = float(wm[3, 0])
                    py = float(wm[3, 1])
                    pz = float(wm[3, 2])
                    wmins[k, 0] = px - 0.5
                    wmins[k, 1] = py - 0.5
                    wmins[k, 2] = pz - 0.5
                    wmaxs[k, 0] = px + 0.5
                    wmaxs[k, 1] = py + 0.5
                    wmaxs[k, 2] = pz + 0.5
                except Exception:
                    continue
    bmin = wmins.min(axis=0)
    bmax = wmaxs.max(axis=0)
    return bmin, bmax
__all__ = ["_GIZMO_INST_CACHE", "_FAST_COLLIDER_NAMES", "_FAST_D", "_FAST_COL_CACHE", "_FAST_COL_CACHE_MAX", "_fast_buf", "_collider_row", "_BOX_EDGE_IDXS", "_box_edges_np", "_build_unit_sphere_cache_np", "_render_corner_spheres_np", "_fast_aggregate_bounds"]
