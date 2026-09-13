# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np
from core.maths.math3d import Vec3
from editor.viewport.projection import screen_to_ray, world_to_screen

try:
    from core import _raycast as _raycast_cy
except ImportError:
    _raycast_cy = None


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


def _world_aabb_of(entity, only_expanded: bool = False) -> tuple | None:
    from core.components.transform import Transform
    from core.components.rendering.renderers.mesh_filter import MeshFilter
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.rendering.renderers.text_renderer import TextRenderer
    from core.components.physics.box_collider import BoxCollider
    from core.components.physics.sphere_collider import SphereCollider
    from core.components.rendering.skeleton.armature import Bone
    if entity.get_component(Bone):
        return None
    t = entity.transform
    if not t:
        return None
    wp = t.position
    bmin = np.array([wp.x, wp.y, wp.z])
    bmax = np.array([wp.x, wp.y, wp.z])
    expanded = False
    mf = entity.get_component(MeshFilter)
    mr = entity.get_component(MeshRenderer)
    if mf and mr and mr.enabled:
        mesh_name = mf.mesh_name or "cube"
        mesh = _get_mesh_for(entity, mesh_name, mf.mesh_path)
        if mesh is not None:
            wm = t.world_matrix._d
            ax, ay, az = mesh.aabb_min
            bx, by, bz = mesh.aabb_max
            corners = np.array([
                [ax, ay, az, 1], [bx, ay, az, 1], [bx, by, az, 1], [ax, by, az, 1],
                [ax, ay, bz, 1], [bx, ay, bz, 1], [bx, by, bz, 1], [ax, by, bz, 1],
            ], dtype=np.float32)
            pts = corners @ wm
            np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
            np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
            expanded = True
    from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
    smr = entity.get_component(SkinnedMeshRenderer)
    if smr and smr.enabled:
        mesh_name = smr.mesh_name or "cube"
        mesh = _get_mesh_for(entity, mesh_name, smr.mesh_path)
        if mesh is not None:
            wm = t.world_matrix._d
            ax, ay, az = mesh.aabb_min
            bx, by, bz = mesh.aabb_max
            corners = np.array([
                [ax, ay, az, 1], [bx, ay, az, 1], [bx, by, az, 1], [ax, by, az, 1],
                [ax, ay, bz, 1], [bx, ay, bz, 1], [bx, by, bz, 1], [ax, by, bz, 1],
            ], dtype=np.float32)
            pts = corners @ wm
            np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
            np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
            expanded = True
    from core.components.rendering.renderers.sprite_renderer import SpriteRenderer
    sr = entity.get_component(SpriteRenderer)
    if sr and sr.enabled and sr.texture_path:
        wm = t.world_matrix._d
        corners = np.array([
            [-0.5, -0.5, 0, 1], [0.5, -0.5, 0, 1], [0.5, 0.5, 0, 1], [-0.5, 0.5, 0, 1],
        ], dtype=np.float32)
        pts = corners @ wm
        np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
        np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
        expanded = True
    from core.components.rendering.renderers.video_renderer import VideoRenderer
    vr = entity.get_component(VideoRenderer)
    if vr and vr.enabled and vr.video_path:
        wm = t.world_matrix._d
        corners = np.array([
            [-0.5, -0.5, 0, 1], [0.5, -0.5, 0, 1], [0.5, 0.5, 0, 1], [-0.5, 0.5, 0, 1],
        ], dtype=np.float32)
        pts = corners @ wm
        np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
        np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
        expanded = True
    from core.components.rendering.renderers.text_renderer import TextRenderer
    from core.assets.font_atlas import request_font_atlas
    from core.assets.font_atlas import get_default_font_path as get_def_font
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
    bc = entity.get_component(BoxCollider)
    if bc:
        hx, hy, hz = bc.size.x * 0.5, bc.size.y * 0.5, bc.size.z * 0.5
        wm = t.world_matrix._d
        corners = np.array([
            [-hx, -hy, -hz, 1], [hx, -hy, -hz, 1], [hx, hy, -hz, 1], [-hx, hy, -hz, 1],
            [-hx, -hy, hz, 1], [hx, -hy, hz, 1], [hx, hy, hz, 1], [-hx, hy, hz, 1],
        ], dtype=np.float32)
        pts = corners @ wm
        np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
        np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
        expanded = True
    sc = entity.get_component(SphereCollider)
    if sc:
        r = sc.radius
        wm = t.world_matrix._d
        center = (np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32) @ wm)[:3]
        np.minimum(bmin, center - r, out=bmin)
        np.maximum(bmax, center + r, out=bmax)
        expanded = True
    for child in entity.children:
        child_box = _world_aabb_of(child)
        if child_box:
            np.minimum(bmin, child_box[0], out=bmin)
            np.maximum(bmax, child_box[1], out=bmax)
            expanded = True
    if not expanded:
        if only_expanded:
            return None
        s = t.local_scale
        half = max(max(abs(s.x), abs(s.y), abs(s.z)) * 0.5, 0.5)
        bmin = np.array([wp.x - half, wp.y - half, wp.z - half])
        bmax = np.array([wp.x + half, wp.y + half, wp.z + half])
    return (bmin, bmax)


_mesh_lookup_cache: dict[tuple[int, int], dict] = {}
_MESH_LOOKUP_SENTINEL = object()


def _resolve_mesh_key(meshes, prefix: str):
    for key, m in meshes.items():
        if key == prefix or key.startswith(prefix + "|"):
            return key
    return _MESH_LOOKUP_SENTINEL


def _get_mesh_for(entity, mesh_name: str, mesh_path: str):
    from core.engine.engine import Engine
    engine = Engine.instance()
    if not engine:
        return None
    renderer = getattr(engine, '_renderer', None)
    if renderer is None:
        vp = getattr(engine, 'viewport', None)
        if vp:
            renderer = getattr(vp, '_renderer', None)
    if renderer is None:
        return None
    meshes = renderer._meshes
    if not meshes:
        return None
    mesh = meshes.get(mesh_name)
    if mesh is not None:
        return mesh
    if mesh_path:
        mesh = meshes.get(mesh_path)
        if mesh is not None:
            return mesh
    sig = (id(meshes), len(meshes))
    cache = _mesh_lookup_cache.get(sig)
    if cache is None:
        cache = {}
        _mesh_lookup_cache[sig] = cache
    if mesh_path:
        key = cache.get(("p", mesh_path))
        if key is None:
            key = _resolve_mesh_key(meshes, mesh_path)
            cache[("p", mesh_path)] = key
        if key is not _MESH_LOOKUP_SENTINEL:
            return meshes[key]
    if mesh_name and mesh_name != "cube":
        key = cache.get(("n", mesh_name))
        if key is None:
            key = _resolve_mesh_key(meshes, mesh_name)
            cache[("n", mesh_name)] = key
        if key is not _MESH_LOOKUP_SENTINEL:
            return meshes[key]
    return meshes.get("cube")


def _world_aabb_from_mesh(mesh, wm):
    ax, ay, az = mesh.aabb_min
    bx, by, bz = mesh.aabb_max
    corners = np.array([
        [ax, ay, az, 1], [bx, ay, az, 1], [bx, by, az, 1], [ax, by, az, 1],
        [ax, ay, bz, 1], [bx, ay, bz, 1], [bx, by, bz, 1], [ax, by, bz, 1],
    ], dtype=np.float32)
    pts = corners @ wm
    return pts[:, :3].min(axis=0), pts[:, :3].max(axis=0)


def _test_mesh_hit(wm, ro, rd, mesh):
    bmin, bmax = _world_aabb_from_mesh(mesh, wm)
    d = _ray_aabb_min(ro[0], ro[1], ro[2], rd[0], rd[1], rd[2],
                      bmin[0], bmin[1], bmin[2], bmax[0], bmax[1], bmax[2])
    if d < 0:
        return -1.0
    wm_inv = _raycast_cy.inv_affine4(wm) if _raycast_cy is not None else np.linalg.inv(wm)
    local_o = ro @ wm_inv
    local_d = rd @ wm_inv
    if mesh.indices is not None and len(mesh.indices) > 0:
        verts = mesh.vertices
        if verts.dtype != np.float32 or not verts.flags.c_contiguous:
            verts = np.ascontiguousarray(verts, dtype=np.float32)
            if verts is not mesh.vertices:
                mesh.vertices = verts
        indices = mesh.indices
        if indices.dtype != np.uint32:
            indices = indices.astype(np.uint32)
            mesh.indices = indices
        elif not indices.flags.c_contiguous:
            indices = np.ascontiguousarray(indices)
            mesh.indices = indices
        from core.spatial.bvh import get_mesh_bvh
        bvh = get_mesh_bvh(verts, indices)
        if bvh and bvh.nodes:
            d = bvh.intersect(local_o[0], local_o[1], local_o[2],
                              local_d[0], local_d[1], local_d[2],
                              verts, indices)
            if d > 0:
                return d
        if _raycast_cy is not None:
            return _raycast_cy.triangles_intersect(
                verts.reshape(-1), indices,
                float(local_o[0]), float(local_o[1]), float(local_o[2]),
                float(local_d[0]), float(local_d[1]), float(local_d[2]))
    return _ray_aabb_min(local_o[0], local_o[1], local_o[2],
                         local_d[0], local_d[1], local_d[2],
                         mesh.aabb_min[0], mesh.aabb_min[1], mesh.aabb_min[2],
                         mesh.aabb_max[0], mesh.aabb_max[1], mesh.aabb_max[2])


def _test_entity_pick(entity, ro, rd, ray_origin, ray_dir):
    from core.components.transform import Transform
    from core.components.rendering.renderers.mesh_filter import MeshFilter
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.physics.mesh_collider import MeshCollider
    t = entity.transform
    if not t:
        return -1.0
    mf = entity.get_component(MeshFilter)
    mr = entity.get_component(MeshRenderer)
    mesh = None
    has_mesh = False
    if mf:
        mesh_name = mf.mesh_name or "cube"
        mesh = _get_mesh_for(entity, mesh_name, mf.mesh_path)
        has_mesh = bool(mesh and mr and mr.enabled)
    if has_mesh:
        wm = t.world_matrix._d
        d = _test_mesh_hit(wm, ro, rd, mesh)
        return d if d > 0 else -1.0
    from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
    smr = entity.get_component(SkinnedMeshRenderer)
    if smr and smr.enabled:
        mesh_name = smr.mesh_name or "cube"
        mesh = _get_mesh_for(entity, mesh_name, smr.mesh_path)
        if mesh is not None:
            wm = t.world_matrix._d
            d = _test_mesh_hit(wm, ro, rd, mesh)
            return d if d > 0 else -1.0
    mc = entity.get_component(MeshCollider)
    if mc:
        mf2 = entity.get_component(MeshFilter)
        if mf2:
            mesh2 = _get_mesh_for(entity, mf2.mesh_name or "cube", mf2.mesh_path)
            if mesh2 is not None and mesh2.indices is not None and len(mesh2.indices) > 0:
                wm = t.world_matrix._d
                d = _test_mesh_hit(wm, ro, rd, mesh2)
                return d if d > 0 else -1.0
    box = _world_aabb_of(entity, only_expanded=True)
    if box is not None:
        d = _ray_aabb_min(ray_origin.x, ray_origin.y, ray_origin.z,
                          ray_dir.x, ray_dir.y, ray_dir.z,
                          box[0][0], box[0][1], box[0][2],
                          box[1][0], box[1][1], box[1][2])
        return d if d > 0 else -1.0
    wp = t.position
    half = 0.5
    d = _ray_aabb_min(ray_origin.x, ray_origin.y, ray_origin.z,
                      ray_dir.x, ray_dir.y, ray_dir.z,
                      wp.x - half, wp.y - half, wp.z - half,
                      wp.x + half, wp.y + half, wp.z + half)
    return d if d > 0 else -1.0


def _mesh_of_entity(entity):
    from core.components.rendering.renderers.mesh_filter import MeshFilter
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
    from core.components.physics.mesh_collider import MeshCollider
    mf = entity.get_component(MeshFilter)
    mr = entity.get_component(MeshRenderer)
    mesh = None
    if mf:
        m = _get_mesh_for(entity, mf.mesh_name or "cube", mf.mesh_path)
        if m is not None and mr and mr.enabled:
            mesh = m
    if mesh is None:
        smr = entity.get_component(SkinnedMeshRenderer)
        if smr and smr.enabled:
            m = _get_mesh_for(entity, smr.mesh_name or "cube", smr.mesh_path)
            if m is not None:
                mesh = m
    if mesh is None:
        mc = entity.get_component(MeshCollider)
        if mc:
            mf2 = entity.get_component(MeshFilter)
            if mf2:
                m = _get_mesh_for(entity, mf2.mesh_name or "cube", mf2.mesh_path)
                if m is not None and m.indices is not None and len(m.indices) > 0:
                    mesh = m
    return mesh


def _batch_mesh_aabb_miss(entities, ro, rd) -> set:
    if _raycast_cy is None:
        return set()
    idx = []
    bmins = []
    bmaxs = []
    wms = []
    for i, entity in enumerate(entities):
        mesh = _mesh_of_entity(entity)
        if mesh is None:
            continue
        t = entity.transform
        if not t:
            continue
        idx.append(i)
        bmins.append(mesh.aabb_min)
        bmaxs.append(mesh.aabb_max)
        wms.append(t.world_matrix._d)
    if not idx:
        return set()
    wmn, wmx = _raycast_cy.world_aabbs(
        np.array(bmins, dtype=np.float64),
        np.array(bmaxs, dtype=np.float64),
        np.array(wms, dtype=np.float64),
    )
    hits = _raycast_cy.ray_aabbs(ro[0], ro[1], ro[2], rd[0], rd[1], rd[2], wmn, wmx)
    return {idx[i] for i in range(len(idx)) if not hits[i]}


def pick_entity(vp, sx: int, sy: int):
    scene = vp._engine.scene
    if not scene:
        return None
    ray_origin, ray_dir = screen_to_ray(vp, sx, sy)
    ro = np.array([ray_origin.x, ray_origin.y, ray_origin.z, 1.0], dtype=np.float64)
    rd = np.array([ray_dir.x, ray_dir.y, ray_dir.z, 0.0], dtype=np.float64)
    candidates = scene.spatial_raycast(ray_origin, ray_dir, 1000.0)
    candidate_ids = {eid for eid, _ in candidates}
    best_entity = None
    best_dist = float("inf")
    for eid, _ in candidates:
        entity = scene.get_entity(eid)
        if not entity or not entity.active:
            continue
        d = _test_entity_pick(entity, ro, rd, ray_origin, ray_dir)
        if d > 0 and d < best_dist:
            best_dist = d
            best_entity = entity
    all_ents = scene.get_all_entities()
    active = [e for e in all_ents if e.active]
    miss = _batch_mesh_aabb_miss(active, ro, rd)
    for i, entity in enumerate(active):
        if entity.id in candidate_ids or i in miss:
            continue
        d = _test_entity_pick(entity, ro, rd, ray_origin, ray_dir)
        if d > 0 and d < best_dist:
            best_dist = d
            best_entity = entity
    return best_entity


def pick_entity_hit(vp, sx: int, sy: int):
    """Returns (entity, hit_world_pos) or (None, None)."""
    scene = vp._engine.scene
    if not scene:
        return None, None
    ray_origin, ray_dir = screen_to_ray(vp, sx, sy)
    ro = np.array([ray_origin.x, ray_origin.y, ray_origin.z, 1.0], dtype=np.float64)
    rd = np.array([ray_dir.x, ray_dir.y, ray_dir.z, 0.0], dtype=np.float64)
    candidates = scene.spatial_raycast(ray_origin, ray_dir, 1000.0)
    candidate_ids = {eid for eid, _ in candidates}
    best_entity = None
    best_dist = float("inf")
    for eid, _ in candidates:
        entity = scene.get_entity(eid)
        if not entity or not entity.active:
            continue
        d = _test_entity_pick(entity, ro, rd, ray_origin, ray_dir)
        if d > 0 and d < best_dist:
            best_dist = d
            best_entity = entity
    all_ents = scene.get_all_entities()
    active = [e for e in all_ents if e.active]
    miss = _batch_mesh_aabb_miss(active, ro, rd)
    for i, entity in enumerate(active):
        if entity.id in candidate_ids or i in miss:
            continue
        d = _test_entity_pick(entity, ro, rd, ray_origin, ray_dir)
        if d > 0 and d < best_dist:
            best_dist = d
            best_entity = entity
    if best_entity is None:
        return None, None
    hit_pos = ray_origin + ray_dir * best_dist
    return best_entity, hit_pos


def _screen_aabb_of(vp, entity) -> tuple | None:
    box = _world_aabb_of(entity)
    if box is None:
        return None
    corners = [
        (box[0][0], box[0][1], box[0][2]),
        (box[1][0], box[0][1], box[0][2]),
        (box[0][0], box[1][1], box[0][2]),
        (box[0][0], box[0][1], box[1][2]),
        (box[1][0], box[1][1], box[0][2]),
        (box[1][0], box[0][1], box[1][2]),
        (box[0][0], box[1][1], box[1][2]),
        (box[1][0], box[1][1], box[1][2]),
    ]
    sx_min = sy_min = float('inf')
    sx_max = sy_max = float('-inf')
    for c in corners:
        sp = world_to_screen(vp, Vec3(*c))
        if sp is None:
            continue
        sx, sy = sp
        sx_min = min(sx_min, sx)
        sy_min = min(sy_min, sy)
        sx_max = max(sx_max, sx)
        sy_max = max(sy_max, sy)
    if sx_min == float('inf'):
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
        bits = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0], [1.0, 1.0, 1.0],
        ], dtype=np.float64)
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
