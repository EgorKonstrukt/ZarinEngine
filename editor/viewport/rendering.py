# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import math
import numpy as np
from core.maths.math3d import Mat4, Vec3
from core.config.config import get_global_config
from core.ecs.ecs import _GIZMO_PASSES, _GIZMO_PASS_ORDER, Component
from core.gizmo.pipeline import GizmoPipeline
from core.assets.font_atlas import request_font_atlas, get_default_font_path as get_def_font


def render_component_gizmos(vp, vp_mat: Mat4, fw: int = None, fh: int = None):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    pipe = GizmoPipeline()
    meshes = []
    for pass_name in _GIZMO_PASS_ORDER:
        for ct in _GIZMO_PASSES.get(pass_name, []):
            ct.gizmo_collect(pipe, scene)
            try:
                meshes.extend(ct.gizmo_collect_meshes(scene))
            except Exception:
                pass
    pipe.flush_and_render(vp, vp_mat, fw=fw, fh=fh)
    if meshes:
        vp._renderer.render_gizmo_meshes(meshes, vp_mat)


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
    corner_pts = np.array([[c.x, c.y, c.z] for c in corners], dtype=np.float32)
    all_verts = corner_pts[:, None, :] + cverts[None, :, :] * radius
    all_verts = all_verts.reshape(-1, 3)
    n_total = nc * nv
    all_idx = np.tile(cidx, nc) + np.repeat(np.arange(nc, dtype=np.int32) * nv, len(cidx))
    v_data = np.empty((n_total, 7), dtype=np.float32)
    v_data[:, :3] = all_verts
    v_data[:, 3] = color[0]; v_data[:, 4] = color[1]
    v_data[:, 5] = color[2]; v_data[:, 6] = color[3]
    vp._renderer.render_gizmo_mesh_np(v_data, np.asarray(all_idx, dtype=np.uint32), vp_mat)


def _fast_aggregate_bounds(vp, entities):
    try:
        from editor.viewport.picking import _get_mesh_for
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
        from core.engine.engine import Engine
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


def _render_entity_bounds(vp, vp_mat, time_s, dt, entities, color, state, fw: int = None, fh: int = None, cam_pos=None):
    from core.components.transform import Transform
    from core.components.rendering.renderers.mesh_filter import MeshFilter
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.rendering.renderers.sprite_renderer import SpriteRenderer
    from core.components.rendering.renderers.video_renderer import VideoRenderer
    from core.components.rendering.renderers.text_renderer import TextRenderer
    from editor.viewport.picking import _get_mesh_for
    bmin_t = None
    bmax_t = None
    try:
        _n_sel = len(entities) if entities is not None else 0
    except Exception:
        _n_sel = 0
    if _n_sel > 200:
        try:
            _scene = vp._engine.scene if vp._engine else None
            _rv = getattr(_scene, "_render_version", 0) if _scene is not None else 0
            _tv = getattr(_scene, "_transform_version", 0) if _scene is not None else 0
            _ckey = (id(entities), _n_sel, _rv, _tv, id(_scene))
            _cached = getattr(vp, "_sel_agg_cache", None)
            if _cached is not None and _cached[0] == _ckey:
                bmin_t = _cached[1]
                bmax_t = _cached[2]
            else:
                bmin_t, bmax_t = _fast_aggregate_bounds(vp, entities)
                try:
                    vp._sel_agg_cache = (_ckey, bmin_t.copy() if bmin_t is not None else None, bmax_t.copy() if bmax_t is not None else None)
                except Exception:
                    pass
        except Exception:
            bmin_t = None
            bmax_t = None
        if bmin_t is None or bmax_t is None:
            if state is None:
                return
            if len(state) < 3:
                state.append(0.0)
            cur_min, cur_max, alpha = state[0], state[1], state[2]
            if cur_min is None:
                return
        else:
            if state is None:
                return
            if len(state) < 3:
                state.append(0.0)
            cur_min, cur_max, alpha = state[0], state[1], state[2]
            from core.config.config import get_global_config as _ggc
            _cfg = _ggc()
            _speed = _cfg.get("gizmo.selection_bounds_speed", 8.0)
            _fade_speed = _cfg.get("gizmo.selection_bounds_fade_speed", 4.0)
            _factor = 1.0 - np.exp(-_speed * dt) if dt > 0.0 else 1.0
            _fade_factor = 1.0 - np.exp(-_fade_speed * dt) if dt > 0.0 else 1.0
            if cur_min is None:
                center = (bmin_t + bmax_t) * 0.5
                cur_min = center.copy()
                cur_max = center.copy()
                state[0] = cur_min
                state[1] = cur_max
                alpha = 0.0
            else:
                np.add(cur_min, (bmin_t - cur_min) * _factor, out=cur_min)
                np.add(cur_max, (bmax_t - cur_max) * _factor, out=cur_max)
                alpha = min(1.0, alpha + _fade_factor)
            state[0], state[1], state[2] = cur_min, cur_max, alpha
            if cam_pos is None:
                cam_pos = vp._cam.position if vp._cam else Vec3(0, 0, 0)
            if fw is None or fh is None:
                fw, fh = vp._get_physical_dims()
            starts, ends = _box_edges_np(cur_min, cur_max)
            n_edges = starts.shape[0]
            colors_arr = np.empty((n_edges, 4), dtype=np.float32)
            colors_arr[:, 0] = color[0]; colors_arr[:, 1] = color[1]
            colors_arr[:, 2] = color[2]; colors_arr[:, 3] = color[3]
            dash_opts = {'dash_length': 0.3, 'gap_length': 0.15, 'time': time_s * 1.5}
            vp._renderer.render_gizmo_arrays(starts, ends, colors_arr, vp_mat, fw, fh, thickness_multiplier=1.5, dash_opts=dash_opts)
            cx = float(cur_min[0]); cy = float(cur_min[1]); cz = float(cur_min[2])
            dx = float(cur_max[0]); dy = float(cur_max[1]); dz = float(cur_max[2])
            verts_3d = [
                Vec3(cx, cy, cz), Vec3(dx, cy, cz), Vec3(dx, dy, cz), Vec3(cx, dy, cz),
                Vec3(cx, cy, dz), Vec3(dx, cy, dz), Vec3(dx, dy, dz), Vec3(cx, dy, dz),
            ]
            center = Vec3((cx + dx) * 0.5, (cy + dy) * 0.5, (cz + dz) * 0.5)
            dist = (center - cam_pos).length()
            fov_rad = math.radians(vp._cam.fov) if vp._cam else 1.0
            pixel_r = 6
            world_r = pixel_r * 2.0 * dist * math.tan(fov_rad * 0.5) / fh if fh > 0 else 0.05
            world_r = max(world_r, 0.01)
            if alpha < 1.0:
                faded = list(color)
                if len(faded) > 3:
                    faded[3] = faded[3] * alpha
                else:
                    faded.append(alpha)
                _render_corner_spheres_np(vp, vp_mat, verts_3d, world_r, faded)
            else:
                _render_corner_spheres_np(vp, vp_mat, verts_3d, world_r, color)
            return
    _corner_buf = np.empty((8, 4), dtype=np.float32)
    _corner_buf[:, 3] = 1.0
    for entity in entities:
        if entity is None:
            continue
        from core.components.rendering.skeleton.armature import Bone
        if entity.get_component(Bone):
            continue
        t = entity.transform
        if not t:
            continue
        wp = t.position
        bx = wp.x; by = wp.y; bz = wp.z
        bmin = np.array([bx, by, bz])
        bmax = np.array([bx, by, bz])
        expanded = False
        mf = entity.get_component(MeshFilter)
        mr = entity.get_component(MeshRenderer) if mf else None
        if mf and mr and mr.enabled:
            mesh_name = mf.mesh_name or "cube"
            mesh = _get_mesh_for(entity, mesh_name, mf.mesh_path)
            if mesh is not None:
                wm = t.world_matrix._d
                ax, ay, az = mesh.aabb_min
                bx2, by2, bz2 = mesh.aabb_max
                _corner_buf[0] = [ax, ay, az, 1]
                _corner_buf[1] = [bx2, ay, az, 1]
                _corner_buf[2] = [bx2, by2, az, 1]
                _corner_buf[3] = [ax, by2, az, 1]
                _corner_buf[4] = [ax, ay, bz2, 1]
                _corner_buf[5] = [bx2, ay, bz2, 1]
                _corner_buf[6] = [bx2, by2, bz2, 1]
                _corner_buf[7] = [ax, by2, bz2, 1]
                pts = _corner_buf @ wm
                np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
                np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
                expanded = True
        if not expanded:
            from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
            smr = entity.get_component(SkinnedMeshRenderer)
            if smr and smr.enabled:
                mesh_name = smr.mesh_name or "cube"
                mesh = _get_mesh_for(entity, mesh_name, smr.mesh_path)
                if mesh is not None:
                    wm = t.world_matrix._d
                    ax, ay, az = mesh.aabb_min
                    bx2, by2, bz2 = mesh.aabb_max
                    _corner_buf[0] = [ax, ay, az, 1]
                    _corner_buf[1] = [bx2, ay, az, 1]
                    _corner_buf[2] = [bx2, by2, az, 1]
                    _corner_buf[3] = [ax, by2, az, 1]
                    _corner_buf[4] = [ax, ay, bz2, 1]
                    _corner_buf[5] = [bx2, ay, bz2, 1]
                    _corner_buf[6] = [bx2, by2, bz2, 1]
                    _corner_buf[7] = [ax, by2, bz2, 1]
                    pts = _corner_buf @ wm
                    np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
                    np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
                    expanded = True
        if not expanded:
            sr = entity.get_component(SpriteRenderer)
            if sr and sr.enabled:
                wm = t.world_matrix._d
                corners = np.array([
                    [-0.5, -0.5, 0, 1], [0.5, -0.5, 0, 1], [0.5, 0.5, 0, 1], [-0.5, 0.5, 0, 1],
                ], dtype=np.float32)
                pts = corners @ wm
                np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
                np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
                expanded = True
        if not expanded:
            vr = entity.get_component(VideoRenderer)
            if vr and vr.enabled:
                wm = t.world_matrix._d
                corners = np.array([
                    [-0.5, -0.5, 0, 1], [0.5, -0.5, 0, 1], [0.5, 0.5, 0, 1], [-0.5, 0.5, 0, 1],
                ], dtype=np.float32)
                pts = corners @ wm
                np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
                np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
                expanded = True
        if not expanded:
                tr_comp = entity.get_component(TextRenderer)
                if tr_comp and tr_comp.enabled and tr_comp.text:
                    fp = tr_comp.font_path or get_def_font()
                    base_size = getattr(tr_comp, "atlas_resolution", 128)
                    atlas = request_font_atlas(fp, base_size)
                    if atlas is not None:
                        inv_lh = 1.0 / atlas.line_height if atlas.line_height > 0 else 1.0
                        scale = float(tr_comp.font_size) * inv_lh * 0.01
                        lines = tr_comp.text.split("\n")
                        total_w_raw = 0.0
                        for line in lines:
                            lw = 0.0
                            for c in line:
                                g = atlas.get_glyph(c)
                                if g:
                                    lw += g["advance"]
                            if lw > total_w_raw:
                                total_w_raw = lw
                        total_w = total_w_raw * scale
                        line_h = atlas.line_height * scale * tr_comp.line_spacing
                        total_h = (len(lines) - 1) * line_h + atlas.line_height * scale
                        hw = total_w * 0.5
                        hh = total_h * 0.5
                        wm = t.world_matrix._d
                        corners = np.array([
                            [-hw, -hh, 0, 1], [hw, -hh, 0, 1], [hw, hh, 0, 1], [-hw, hh, 0, 1],
                        ], dtype=np.float32)
                        pts = corners @ wm
                        np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
                        np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
                        expanded = True
        if not expanded:
            s = t.local_scale
            half = max(max(abs(s.x), abs(s.y), abs(s.z)) * 0.5, 0.5)
            bmin = np.array([bx - half, by - half, bz - half])
            bmax = np.array([bx + half, by + half, bz + half])
        if bmin_t is None:
            bmin_t, bmax_t = bmin.copy(), bmax.copy()
        else:
            np.minimum(bmin_t, bmin, out=bmin_t)
            np.maximum(bmax_t, bmax, out=bmax_t)
    if state is None:
        return
    if len(state) < 3:
        state.append(0.0)
    cur_min, cur_max, alpha = state[0], state[1], state[2]
    cfg = get_global_config()
    speed = cfg.get("gizmo.selection_bounds_speed", 8.0)
    fade_speed = cfg.get("gizmo.selection_bounds_fade_speed", 4.0)
    factor = 1.0 - np.exp(-speed * dt) if dt > 0.0 else 1.0
    fade_factor = 1.0 - np.exp(-fade_speed * dt) if dt > 0.0 else 1.0
    if bmin_t is not None:
        if cur_min is None:
            center = (bmin_t + bmax_t) * 0.5
            cur_min = center.copy()
            cur_max = center.copy()
            state[0] = cur_min
            state[1] = cur_max
            alpha = 0.0
        else:
            np.add(cur_min, (bmin_t - cur_min) * factor, out=cur_min)
            np.add(cur_max, (bmax_t - cur_max) * factor, out=cur_max)
            alpha = min(1.0, alpha + fade_factor)
    else:
        if cur_min is not None:
            alpha = max(0.0, alpha - fade_factor)
            if alpha <= 0.0:
                state[0] = None
                state[1] = None
                state[2] = 0.0
                return
            center = (cur_min + cur_max) * 0.5
            t = 1.0 - alpha
            np.add(cur_min, (center - cur_min) * t, out=cur_min)
            np.add(cur_max, (center - cur_max) * t, out=cur_max)
        else:
            return
    state[0], state[1], state[2] = cur_min, cur_max, alpha
    if cam_pos is None:
        cam_pos = vp._cam.position if vp._cam else Vec3(0, 0, 0)
    if fw is None or fh is None:
        fw, fh = vp._get_physical_dims()
    starts, ends = _box_edges_np(cur_min, cur_max)
    n_edges = starts.shape[0]
    colors_arr = np.empty((n_edges, 4), dtype=np.float32)
    colors_arr[:, 0] = color[0]; colors_arr[:, 1] = color[1]
    colors_arr[:, 2] = color[2]; colors_arr[:, 3] = color[3]
    dash_opts = {'dash_length': 0.3, 'gap_length': 0.15, 'time': time_s * 1.5}
    vp._renderer.render_gizmo_arrays(starts, ends, colors_arr, vp_mat, fw, fh, thickness_multiplier=1.5, dash_opts=dash_opts)
    cx = float(cur_min[0]); cy = float(cur_min[1]); cz = float(cur_min[2])
    dx = float(cur_max[0]); dy = float(cur_max[1]); dz = float(cur_max[2])
    verts_3d = [
        Vec3(cx, cy, cz), Vec3(dx, cy, cz), Vec3(dx, dy, cz), Vec3(cx, dy, cz),
        Vec3(cx, cy, dz), Vec3(dx, cy, dz), Vec3(dx, dy, dz), Vec3(cx, dy, dz),
    ]
    center = Vec3((cx + dx) * 0.5, (cy + dy) * 0.5, (cz + dz) * 0.5)
    dist = (center - cam_pos).length()
    fov_rad = math.radians(vp._cam.fov) if vp._cam else 1.0
    pixel_r = 6
    world_r = pixel_r * 2.0 * dist * math.tan(fov_rad * 0.5) / fh if fh > 0 else 0.05
    world_r = max(world_r, 0.01)
    if alpha < 1.0:
        faded = list(color)
        if len(faded) > 3:
            faded[3] = faded[3] * alpha
        else:
            faded.append(alpha)
        _render_corner_spheres_np(vp, vp_mat, verts_3d, world_r, faded)
    else:
        _render_corner_spheres_np(vp, vp_mat, verts_3d, world_r, color)


def render_selection_bounds(vp, vp_mat: Mat4, time_s: float, dt: float = 0.0, fw: int = None, fh: int = None, cam_pos=None):
    cfg = get_global_config()
    if not cfg.get("gizmo.selection_bounds", True):
        return
    if not hasattr(vp, '_sel_bounds_state'):
        old_min = getattr(vp, '_sel_bounds_min', None)
        old_max = getattr(vp, '_sel_bounds_max', None)
        vp._sel_bounds_state = [old_min, old_max]
    c = cfg.get("gizmo.selection_bounds_color", [0.25, 0.55, 1.0])
    color = [c[0], c[1], c[2], 1.0]
    selected = getattr(vp, '_selected_entities', None) or []
    _render_entity_bounds(vp, vp_mat, time_s, dt, selected, color, vp._sel_bounds_state, fw=fw, fh=fh, cam_pos=cam_pos)
    collab = vp._engine.collab_manager if hasattr(vp._engine, 'collab_manager') else None
    if not collab or not collab.connected:
        return
    scene = vp._engine.scene
    if not scene:
        return
    if not hasattr(vp, '_sel_bounds_peers'):
        vp._sel_bounds_peers = {}
    for peer_id, peer in collab.peers.items():
        if not peer.selected_entity_ids:
            vp._sel_bounds_peers.pop(peer_id, None)
            continue
        peer_entities = [scene.get_entity(eid) for eid in peer.selected_entity_ids]
        peer_entities = [e for e in peer_entities if e is not None]
        if not peer_entities:
            vp._sel_bounds_peers.pop(peer_id, None)
            continue
        peer_color = peer.color + [1.0]
        if peer_id not in vp._sel_bounds_peers:
            vp._sel_bounds_peers[peer_id] = [None, None]
        _render_entity_bounds(vp, vp_mat, time_s, dt, peer_entities, peer_color, vp._sel_bounds_peers[peer_id])
