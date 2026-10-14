# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import numpy as np
from core.maths.math3d import Vec3
from editor.viewport.projection import world_to_screen
from editor.viewport.pick.ray import _world_aabb_of
try:
    from core import _raycast as _raycast_cy
except ImportError:
    _raycast_cy = None
def _screen_aabb_of(vp, entity) -> tuple | None:
    box = _world_aabb_of(entity)
    if box is None:
        return None
    corners = [(box[0][0], box[0][1], box[0][2]), (box[1][0], box[0][1], box[0][2]), (box[0][0], box[1][1], box[0][2]), (box[0][0], box[0][1], box[1][2]), (box[1][0], box[1][1], box[0][2]), (box[1][0], box[0][1], box[1][2]), (box[0][0], box[1][1], box[1][2]), (box[1][0], box[1][1], box[1][2])]
    sx_min = sy_min = float("inf")
    sx_max = sy_max = float("-inf")
    for c in corners:
        sp = world_to_screen(vp, Vec3(*c))
        if sp is None:
            continue
        sx, sy = sp
        sx_min = min(sx_min, sx)
        sy_min = min(sy_min, sy)
        sx_max = max(sx_max, sx)
        sy_max = max(sy_max, sy)
    if sx_min == float("inf"):
        return None
    return (sx_min, sy_min, sx_max, sy_max)
def pick_entities_in_rect(vp, rx: int, ry: int, rw: int, rh: int) -> list:
    scene = vp._engine.scene
    if not scene:
        return []
    if rw < 0:
        rx += rw
        rw = -rw
    if rh < 0:
        ry += rh
        rh = -rh
    if rw < 3 and rh < 3:
        return []
    try:
        scene.flush_transforms()
    except Exception:
        pass
    w = float(vp.width())
    h = float(vp.height())
    if w <= 0 or h <= 0:
        return []
    try:
        fw, fh = vp._get_physical_dims()
        crw, crh = vp._cam.compute_render_size(int(fw), int(fh))
        aspect = float(crw) / max(1.0, float(crh))
    except Exception:
        aspect = w / max(1.0, h)
    try:
        vp_mat = (vp._cam.get_view_matrix() * vp._cam.get_projection_matrix(aspect))._d.astype(np.float64, copy=False)
    except Exception:
        return []
    try:
        all_ents = scene.get_all_entities()
    except Exception:
        return []
    meshes = None
    prefix_map = None
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
            cube_mesh = None
    else:
        cube_mesh = None
    filt = []
    wm_list = []
    lmin_list = []
    lmax_list = []
    mesh_idx = []
    wmin_arr = []
    wmax_arr = []
    for entity in all_ents:
        try:
            if not entity._active:
                continue
        except Exception:
            try:
                if not entity.active:
                    continue
            except Exception:
                continue
        comps = getattr(entity, "_components", None)
        if comps is not None:
            skip = False
            for k in comps.keys():
                if k == "Bone" or k.startswith("Bone."):
                    skip = True
                    break
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
        filt.append(entity)
        wm_list.append(wm)
        local_min = None
        local_max = None
        mesh_obj = None
        use_sprite_quad = False
        box_half = None
        box_center = None
        sphere_r = None
        sphere_center = None
        if comps is not None and meshes is not None and prefix_map is not None:
            try:
                mf = comps.get("MeshFilter")
                if mf is None:
                    for k, v in comps.items():
                        if k.startswith("MeshFilter."):
                            mf = v
                            break
                mr = comps.get("MeshRenderer")
                if mr is None:
                    for k, v in comps.items():
                        if k.startswith("MeshRenderer."):
                            mr = v
                            break
                if mf is not None and mr is not None and getattr(mr, "_enabled", True):
                    mname = getattr(mf, "mesh_name", None) or "cube"
                    mpath = getattr(mf, "mesh_path", None) or ""
                    mesh_obj = meshes.get(mname)
                    if mesh_obj is None and mpath:
                        mesh_obj = meshes.get(mpath)
                    if mesh_obj is None and mname and mname != "cube":
                        pk = prefix_map.get(mname)
                        if pk is not None:
                            mesh_obj = meshes.get(pk)
                    if mesh_obj is None and mpath:
                        pk = prefix_map.get(mpath)
                        if pk is not None:
                            mesh_obj = meshes.get(pk)
                    if mesh_obj is None:
                        mesh_obj = cube_mesh
                if mesh_obj is None:
                    smr = comps.get("SkinnedMeshRenderer")
                    if smr is None:
                        for k, v in comps.items():
                            if k.startswith("SkinnedMeshRenderer."):
                                smr = v
                                break
                    if smr is not None and getattr(smr, "_enabled", True):
                        mname = getattr(smr, "mesh_name", None) or "cube"
                        mpath = getattr(smr, "mesh_path", None) or ""
                        mesh_obj = meshes.get(mname)
                        if mesh_obj is None and mpath:
                            mesh_obj = meshes.get(mpath)
                        if mesh_obj is None and mname and mname != "cube":
                            pk = prefix_map.get(mname)
                            if pk is not None:
                                mesh_obj = meshes.get(pk)
                        if mesh_obj is None:
                            mesh_obj = cube_mesh
                if mesh_obj is None:
                    has_mc = False
                    for k in comps.keys():
                        if k == "MeshCollider" or k.startswith("MeshCollider."):
                            has_mc = True
                            break
                    if has_mc and mf is not None:
                        mname = getattr(mf, "mesh_name", None) or "cube"
                        mpath = getattr(mf, "mesh_path", None) or ""
                        mesh_obj = meshes.get(mname)
                        if mesh_obj is None and mpath:
                            mesh_obj = meshes.get(mpath)
                        if mesh_obj is None:
                            mesh_obj = cube_mesh
                if mesh_obj is not None:
                    try:
                        local_min = mesh_obj.aabb_min
                        local_max = mesh_obj.aabb_max
                    except Exception:
                        mesh_obj = None
            except Exception:
                mesh_obj = None
                local_min = None
        if local_min is None and comps is not None:
            try:
                bc = None
                for k, v in comps.items():
                    if k == "BoxCollider" or k.startswith("BoxCollider."):
                        bc = v
                        break
                if bc is not None:
                    try:
                        sz = bc.size
                        cx0 = bc.center
                        sx = float(sz.x)
                        sy = float(sz.y)
                        szv = float(sz.z)
                        ccx = float(cx0.x)
                        ccy = float(cx0.y)
                        ccz = float(cx0.z)
                        local_min = (-sx * 0.5 + ccx, -sy * 0.5 + ccy, -szv * 0.5 + ccz)
                        local_max = (sx * 0.5 + ccx, sy * 0.5 + ccy, szv * 0.5 + ccz)
                    except Exception:
                        local_min = None
                if local_min is None:
                    sc = None
                    for k, v in comps.items():
                        if k == "SphereCollider" or k.startswith("SphereCollider."):
                            sc = v
                            break
                    if sc is not None:
                        try:
                            sphere_r = float(sc.radius)
                            cc = sc.center
                            sphere_center = (float(cc.x), float(cc.y), float(cc.z))
                        except Exception:
                            sphere_r = None
                if local_min is None and sphere_r is None:
                    spr = None
                    for k, v in comps.items():
                        if k == "SpriteRenderer" or k.startswith("SpriteRenderer."):
                            spr = v
                            break
                    if spr is not None and getattr(spr, "_enabled", True) and getattr(spr, "texture_path", None):
                        use_sprite_quad = True
                    else:
                        vr = None
                        for k, v in comps.items():
                            if k == "VideoRenderer" or k.startswith("VideoRenderer."):
                                vr = v
                                break
                        if vr is not None and getattr(vr, "_enabled", True) and getattr(vr, "video_path", None):
                            use_sprite_quad = True
            except Exception:
                pass
        if local_min is not None and local_max is not None:
            try:
                lmin_list.append((float(local_min[0]), float(local_min[1]), float(local_min[2])))
                lmax_list.append((float(local_max[0]), float(local_max[1]), float(local_max[2])))
                mesh_idx.append(len(filt) - 1)
            except Exception:
                pass
        elif use_sprite_quad:
            lmin_list.append((-0.5, -0.5, 0.0))
            lmax_list.append((0.5, 0.5, 0.0))
            mesh_idx.append(len(filt) - 1)
        elif sphere_r is not None and sphere_center is not None:
            try:
                cx = wm[3, 0] + sphere_center[0] * wm[0, 0] + sphere_center[1] * wm[1, 0] + sphere_center[2] * wm[2, 0]
                cy = wm[3, 1] + sphere_center[0] * wm[0, 1] + sphere_center[1] * wm[1, 1] + sphere_center[2] * wm[2, 1]
                cz = wm[3, 2] + sphere_center[0] * wm[0, 2] + sphere_center[1] * wm[1, 2] + sphere_center[2] * wm[2, 2]
                scx = abs(wm[0, 0]) + abs(wm[1, 0]) + abs(wm[2, 0])
                scy = abs(wm[0, 1]) + abs(wm[1, 1]) + abs(wm[2, 1])
                scz = abs(wm[0, 2]) + abs(wm[1, 2]) + abs(wm[2, 2])
                rr = float(sphere_r) * max(1.0, max(scx, scy, scz) * 0.34)
                wmin_arr.append(None)
                wmax_arr.append(None)
                if len(wmin_arr) <= len(filt) - 1:
                    pass
                while len(wmin_arr) < len(filt):
                    wmin_arr.append(None)
                    wmax_arr.append(None)
                wmin_arr[len(filt) - 1] = (cx - rr, cy - rr, cz - rr)
                wmax_arr[len(filt) - 1] = (cx + rr, cy + rr, cz + rr)
            except Exception:
                pass
        if len(wmin_arr) < len(filt):
            wmin_arr.append(None)
            wmax_arr.append(None)
    n = len(filt)
    if n == 0:
        return []
    wmins = np.empty((n, 3), dtype=np.float64)
    wmaxs = np.empty((n, 3), dtype=np.float64)
    need_fallback = np.zeros(n, dtype=bool)
    for i in range(n):
        v0 = wmin_arr[i]
        if v0 is not None:
            v1 = wmax_arr[i]
            wmins[i, 0] = v0[0]
            wmins[i, 1] = v0[1]
            wmins[i, 2] = v0[2]
            wmaxs[i, 0] = v1[0]
            wmaxs[i, 1] = v1[1]
            wmaxs[i, 2] = v1[2]
        else:
            need_fallback[i] = True
    has_mesh_batch = len(mesh_idx) > 0
    if has_mesh_batch:
        try:
            bm = np.array([lmin_list[k] for k in range(len(mesh_idx))], dtype=np.float64)
            bx = np.array([lmax_list[k] for k in range(len(mesh_idx))], dtype=np.float64)
            mw = np.array([wm_list[mesh_idx[k]] for k in range(len(mesh_idx))], dtype=np.float64)
            if _raycast_cy is not None:
                rmn, rmx = _raycast_cy.world_aabbs(bm, bx, mw)
                for k, ei in enumerate(mesh_idx):
                    wmins[ei, 0] = rmn[k, 0]
                    wmins[ei, 1] = rmn[k, 1]
                    wmins[ei, 2] = rmn[k, 2]
                    wmaxs[ei, 0] = rmx[k, 0]
                    wmaxs[ei, 1] = rmx[k, 1]
                    wmaxs[ei, 2] = rmx[k, 2]
                    need_fallback[ei] = False
            else:
                for k, ei in enumerate(mesh_idx):
                    corners = np.array([[bm[k, 0], bm[k, 1], bm[k, 2], 1.0], [bx[k, 0], bm[k, 1], bm[k, 2], 1.0], [bm[k, 0], bx[k, 1], bm[k, 2], 1.0], [bm[k, 0], bm[k, 1], bx[k, 2], 1.0], [bx[k, 0], bx[k, 1], bm[k, 2], 1.0], [bx[k, 0], bm[k, 1], bx[k, 2], 1.0], [bm[k, 0], bx[k, 1], bx[k, 2], 1.0], [bx[k, 0], bx[k, 1], bx[k, 2], 1.0]], dtype=np.float64) @ mw[k]
                    wmins[ei] = corners[:, :3].min(axis=0)
                    wmaxs[ei] = corners[:, :3].max(axis=0)
                    need_fallback[ei] = False
        except Exception:
            for ei in mesh_idx:
                need_fallback[ei] = True
    if np.any(need_fallback):
        for i in range(n):
            if not need_fallback[i]:
                continue
            try:
                wm = wm_list[i]
                px = float(wm[3, 0])
                py = float(wm[3, 1])
                pz = float(wm[3, 2])
                t = filt[i]._transform
                if t is None:
                    t = filt[i].transform
                half = 0.5
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
                wmins[i, 0] = px - half
                wmins[i, 1] = py - half
                wmins[i, 2] = pz - half
                wmaxs[i, 0] = px + half
                wmaxs[i, 1] = py + half
                wmaxs[i, 2] = pz + half
            except Exception:
                wmins[i, 0] = 0.0
                wmins[i, 1] = 0.0
                wmins[i, 2] = 0.0
                wmaxs[i, 0] = 0.0
                wmaxs[i, 1] = 0.0
                wmaxs[i, 2] = 0.0
    try:
        bits = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0], [1.0, 1.0, 1.0]], dtype=np.float64)
        corners = wmins[:, None, :] * (1.0 - bits[None, :, :]) + wmaxs[:, None, :] * bits[None, :, :]
        pts = corners.reshape(n * 8, 3)
        ones = np.ones((n * 8, 1), dtype=np.float64)
        pts_h = np.concatenate([pts, ones], axis=1)
        clip = pts_h @ vp_mat
        cw = clip[:, 3]
        valid = np.abs(cw) > 1e-9
        ndc = np.empty((n * 8, 3), dtype=np.float64)
        ndc[valid] = clip[valid][:, :3] / cw[valid][:, None]
        ndc[~valid] = 0.0
        ok = valid & (ndc[:, 2] >= -1.0) & (ndc[:, 2] <= 1.0)
        sx = (ndc[:, 0] + 1.0) * 0.5 * w
        sy = (1.0 - ndc[:, 1]) * 0.5 * h
        sx = sx.reshape(n, 8)
        sy = sy.reshape(n, 8)
        okm = ok.reshape(n, 8)
        any_ok = np.any(okm, axis=1)
        sx_min = np.where(okm, sx, np.inf).min(axis=1)
        sy_min = np.where(okm, sy, np.inf).min(axis=1)
        sx_max = np.where(okm, sx, -np.inf).max(axis=1)
        sy_max = np.where(okm, sy, -np.inf).max(axis=1)
        rx2 = float(rx + rw)
        ry2 = float(ry + rh)
        mask = any_ok & (sx_min <= rx2) & (sx_max >= float(rx)) & (sy_min <= ry2) & (sy_max >= float(ry))
        idx = np.flatnonzero(mask)
        return [filt[int(k)] for k in idx.tolist()]
    except Exception:
        return []
