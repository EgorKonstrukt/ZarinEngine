# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import numpy as np
from editor.viewport.projection import screen_to_ray
try:
    from core import _raycast as _raycast_cy
except ImportError:
    _raycast_cy = None
_MISS_CACHE: dict = {}
_MISS_CACHE_MAX: int = 4
_mesh_lookup_cache: dict[tuple[int, int], dict] = {}
_MESH_LOOKUP_SENTINEL = object()
_MESH_LOOKUP_MAX = 8
def _ray_aabb_min(ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, bmin_x: float, bmin_y: float, bmin_z: float, bmax_x: float, bmax_y: float, bmax_z: float) -> float:
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
def _accum_corners(bmin, bmax, wm, corners):
    pts = corners @ wm
    np.minimum(bmin, pts[:, :3].min(axis=0), out=bmin)
    np.maximum(bmax, pts[:, :3].max(axis=0), out=bmax)
def _world_aabb_of(entity, only_expanded: bool = False) -> tuple | None:
    from core.components.transform.tr import Transform
    from core.components.rendering.renderers.mesh_filter import MeshFilter
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.rendering.renderers.text_renderer import TextRenderer
    from core.components.physics.box_collider import BoxCollider
    from core.components.physics.sphere_collider import SphereCollider
    from core.components.rendering.skeleton.armp import Bone
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
            corners = np.array([[ax, ay, az, 1], [bx, ay, az, 1], [bx, by, az, 1], [ax, by, az, 1], [ax, ay, bz, 1], [bx, ay, bz, 1], [bx, by, bz, 1], [ax, by, bz, 1]], dtype=np.float32)
            _accum_corners(bmin, bmax, wm, corners)
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
            corners = np.array([[ax, ay, az, 1], [bx, ay, az, 1], [bx, by, az, 1], [ax, by, az, 1], [ax, ay, bz, 1], [bx, ay, bz, 1], [bx, by, bz, 1], [ax, by, bz, 1]], dtype=np.float32)
            _accum_corners(bmin, bmax, wm, corners)
            expanded = True
    from core.components.rendering.renderers.sprite_renderer import SpriteRenderer
    sr = entity.get_component(SpriteRenderer)
    if sr and sr.enabled and sr.texture_path:
        wm = t.world_matrix._d
        corners = np.array([[-0.5, -0.5, 0, 1], [0.5, -0.5, 0, 1], [0.5, 0.5, 0, 1], [-0.5, 0.5, 0, 1]], dtype=np.float32)
        _accum_corners(bmin, bmax, wm, corners)
        expanded = True
    from core.components.rendering.renderers.video_renderer import VideoRenderer
    vr = entity.get_component(VideoRenderer)
    if vr and vr.enabled and vr.video_path:
        wm = t.world_matrix._d
        corners = np.array([[-0.5, -0.5, 0, 1], [0.5, -0.5, 0, 1], [0.5, 0.5, 0, 1], [-0.5, 0.5, 0, 1]], dtype=np.float32)
        _accum_corners(bmin, bmax, wm, corners)
        expanded = True
    from core.components.rendering.renderers.text_renderer import TextRenderer
    from core.assets.fontatlas import request_font_atlas
    from core.assets.fontatlas import get_default_font_path as get_def_font
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
            corners = np.array([[-hw, -hh, 0, 1], [hw, -hh, 0, 1], [hw, hh, 0, 1], [-hw, hh, 0, 1]], dtype=np.float32)
            _accum_corners(bmin, bmax, wm, corners)
            expanded = True
    bc = entity.get_component(BoxCollider)
    if bc:
        hx, hy, hz = bc.size.x * 0.5, bc.size.y * 0.5, bc.size.z * 0.5
        wm = t.world_matrix._d
        corners = np.array([[-hx, -hy, -hz, 1], [hx, -hy, -hz, 1], [hx, hy, -hz, 1], [-hx, hy, -hz, 1], [-hx, -hy, hz, 1], [hx, -hy, hz, 1], [hx, hy, hz, 1], [-hx, hy, hz, 1]], dtype=np.float32)
        _accum_corners(bmin, bmax, wm, corners)
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
def _resolve_mesh_key(meshes, prefix: str):
    for key, m in meshes.items():
        if key == prefix or key.startswith(prefix + "|"):
            return key
    return _MESH_LOOKUP_SENTINEL
def _get_mesh_for(entity, mesh_name: str, mesh_path: str):
    from core.engine.eng import Engine
    engine = Engine.instance()
    if not engine:
        return None
    renderer = getattr(engine, "_renderer", None)
    if renderer is None:
        vp = getattr(engine, "viewport", None)
        if vp:
            renderer = getattr(vp, "_renderer", None)
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
        if len(_mesh_lookup_cache) >= _MESH_LOOKUP_MAX:
            _mesh_lookup_cache.pop(next(iter(_mesh_lookup_cache)))
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
    corners = np.array([[ax, ay, az, 1], [bx, ay, az, 1], [bx, by, az, 1], [ax, by, az, 1], [ax, ay, bz, 1], [bx, ay, bz, 1], [bx, by, bz, 1], [ax, by, bz, 1]], dtype=np.float32)
    pts = corners @ wm
    return pts[:, :3].min(axis=0), pts[:, :3].max(axis=0)
def _test_mesh_hit(wm, ro, rd, mesh):
    bmin, bmax = _world_aabb_from_mesh(mesh, wm)
    d = _ray_aabb_min(ro[0], ro[1], ro[2], rd[0], rd[1], rd[2], bmin[0], bmin[1], bmin[2], bmax[0], bmax[1], bmax[2])
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
        from core.spatial.bvhv import get_mesh_bvh
        bvh = get_mesh_bvh(verts, indices)
        if bvh and bvh.nodes:
            d = bvh.intersect(local_o[0], local_o[1], local_o[2], local_d[0], local_d[1], local_d[2], verts, indices)
            if d > 0:
                return d
        if _raycast_cy is not None:
            return _raycast_cy.triangles_intersect(verts.reshape(-1), indices, float(local_o[0]), float(local_o[1]), float(local_o[2]), float(local_d[0]), float(local_d[1]), float(local_d[2]))
    return _ray_aabb_min(local_o[0], local_o[1], local_o[2], local_d[0], local_d[1], local_d[2], mesh.aabb_min[0], mesh.aabb_min[1], mesh.aabb_min[2], mesh.aabb_max[0], mesh.aabb_max[1], mesh.aabb_max[2])
def _test_entity_pick(entity, ro, rd, ray_origin, ray_dir):
    from core.components.transform.tr import Transform
    from core.components.rendering.renderers.mesh_filter import MeshFilter
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.physics.meshcol import MeshCollider
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
        d = _ray_aabb_min(ray_origin.x, ray_origin.y, ray_origin.z, ray_dir.x, ray_dir.y, ray_dir.z, box[0][0], box[0][1], box[0][2], box[1][0], box[1][1], box[1][2])
        return d if d > 0 else -1.0
    wp = t.position
    half = 0.5
    d = _ray_aabb_min(ray_origin.x, ray_origin.y, ray_origin.z, ray_dir.x, ray_dir.y, ray_dir.z, wp.x - half, wp.y - half, wp.z - half, wp.x + half, wp.y + half, wp.z + half)
    return d if d > 0 else -1.0
def _mesh_of_entity(entity):
    from core.components.rendering.renderers.mesh_filter import MeshFilter
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
    from core.components.physics.meshcol import MeshCollider
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
def _batch_mesh_aabb_miss(entities, ro, rd, key=None) -> set:
    if _raycast_cy is None:
        return set()
    if key is not None:
        try:
            ck = _MISS_CACHE.get(key[2])
            if ck is not None and ck[0] == id(entities) and ck[1] == key and ck[2] == len(entities):
                return set(ck[3])
        except Exception:
            pass
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
    wmn, wmx = _raycast_cy.world_aabbs(np.array(bmins, dtype=np.float64), np.array(bmaxs, dtype=np.float64), np.array(wms, dtype=np.float64))
    hits = _raycast_cy.ray_aabbs(ro[0], ro[1], ro[2], rd[0], rd[1], rd[2], wmn, wmx)
    out = {idx[i] for i in range(len(idx)) if not hits[i]}
    if key is not None:
        try:
            if len(_MISS_CACHE) >= _MISS_CACHE_MAX:
                _MISS_CACHE.clear()
            _MISS_CACHE[key[2]] = (id(entities), key, len(entities), frozenset(out))
        except Exception:
            pass
    return out
def _best_pick(scene, ro, rd, ray_origin, ray_dir):
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
    try:
        _mkey = (scene._render_version, scene._transform_version, id(scene))
    except Exception:
        _mkey = None
    miss = _batch_mesh_aabb_miss(active, ro, rd, _mkey)
    for i, entity in enumerate(active):
        if entity.id in candidate_ids or i in miss:
            continue
        d = _test_entity_pick(entity, ro, rd, ray_origin, ray_dir)
        if d > 0 and d < best_dist:
            best_dist = d
            best_entity = entity
    return best_entity, best_dist
def pick_entity(vp, sx: int, sy: int):
    scene = vp._engine.scene
    if not scene:
        return None
    ray_origin, ray_dir = screen_to_ray(vp, sx, sy)
    ro = np.array([ray_origin.x, ray_origin.y, ray_origin.z, 1.0], dtype=np.float64)
    rd = np.array([ray_dir.x, ray_dir.y, ray_dir.z, 0.0], dtype=np.float64)
    best_entity, _ = _best_pick(scene, ro, rd, ray_origin, ray_dir)
    return best_entity
def pick_entity_hit(vp, sx: int, sy: int):
    scene = vp._engine.scene
    if not scene:
        return None, None
    ray_origin, ray_dir = screen_to_ray(vp, sx, sy)
    ro = np.array([ray_origin.x, ray_origin.y, ray_origin.z, 1.0], dtype=np.float64)
    rd = np.array([ray_dir.x, ray_dir.y, ray_dir.z, 0.0], dtype=np.float64)
    best_entity, best_dist = _best_pick(scene, ro, rd, ray_origin, ray_dir)
    if best_entity is None:
        return None, None
    hit_pos = ray_origin + ray_dir * best_dist
    return best_entity, hit_pos
