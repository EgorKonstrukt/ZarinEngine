from __future__ import annotations

import numpy as np
from core.math3d import Vec3
from editor.viewport.projection import screen_to_ray


def pick_entity(vp, sx: int, sy: int):
    scene = vp._engine.scene
    if not scene:
        return None
    ray_origin, ray_dir = screen_to_ray(vp, sx, sy)
    from core.components.transform import Transform
    from core.components.rendering.mesh_filter import MeshFilter
    from core.components.rendering.mesh_renderer import MeshRenderer
    from core.components.physics.mesh_collider import MeshCollider
    from core.components.physics.box_collider import BoxCollider
    from core.components.physics.sphere_collider import SphereCollider
    from core.math_helpers import ray_mesh_intersect, ray_aabb_intersect
    ro = np.array([ray_origin.x, ray_origin.y, ray_origin.z, 1.0], dtype=np.float64)
    rd = np.array([ray_dir.x, ray_dir.y, ray_dir.z, 0.0], dtype=np.float64)
    all_ents = scene.get_all_entities()
    best_entity = None
    best_dist = float("inf")
    for entity in all_ents:
        if not entity.active:
            continue
        t = entity.get_component(Transform)
        if not t:
            continue
        mf = entity.get_component(MeshFilter)
        mr = entity.get_component(MeshRenderer)
        mesh = None
        if mf:
            mesh_name = mf.mesh_name or "cube"
            mesh = vp._renderer._meshes.get(mesh_name) if vp._renderer else None
            if mesh is None and mf.mesh_path and vp._renderer:
                mesh = vp._renderer._meshes.get(mf.mesh_path)
            if mesh is None and vp._renderer:
                mesh = vp._renderer._meshes.get("cube")
        if mesh and mr and mr.enabled:
            inv_world = t.world_matrix.inverted()
            inv_d = inv_world._d
            local_o = inv_d @ ro
            local_d = inv_d @ rd
            if abs(local_o[3]) > 1e-10:
                local_o = local_o / local_o[3]
            if mesh.indices is not None and len(mesh.indices) > 0:
                d = ray_mesh_intersect(local_o[0], local_o[1], local_o[2],
                                       local_d[0], local_d[1], local_d[2],
                                       mesh.vertices, mesh.indices)
            else:
                d = ray_aabb_intersect(local_o[0], local_o[1], local_o[2],
                                       local_d[0], local_d[1], local_d[2],
                                       mesh.aabb_min[0], mesh.aabb_min[1], mesh.aabb_min[2],
                                       mesh.aabb_max[0], mesh.aabb_max[1], mesh.aabb_max[2])
            if d > 0 and d < best_dist:
                best_dist = d
                best_entity = entity
                continue
        mc = entity.get_component(MeshCollider)
        if mc:
            mf2 = entity.get_component(MeshFilter)
            if mf2:
                mesh2 = vp._renderer._meshes.get(mf2.mesh_name or "cube") if vp._renderer else None
                if mesh2 and mesh2.indices is not None and len(mesh2.indices) > 0:
                    inv_world = t.world_matrix.inverted()
                    inv_d = inv_world._d
                    local_o = inv_d @ ro
                    local_d = inv_d @ rd
                    if abs(local_o[3]) > 1e-10:
                        local_o = local_o / local_o[3]
                    d = ray_mesh_intersect(local_o[0], local_o[1], local_o[2],
                                           local_d[0], local_d[1], local_d[2],
                                           mesh2.vertices, mesh2.indices)
                    if d > 0 and d < best_dist:
                        best_dist = d
                        best_entity = entity
                        continue
        bc = entity.get_component(BoxCollider)
        if bc:
            half = Vec3(bc.size.x * 0.5, bc.size.y * 0.5, bc.size.z * 0.5)
            inv_world = t.world_matrix.inverted()
            inv_d = inv_world._d
            local_o = inv_d @ ro
            local_d = inv_d @ rd
            if abs(local_o[3]) > 1e-10:
                local_o = local_o / local_o[3]
            d = ray_aabb_intersect(local_o[0], local_o[1], local_o[2],
                                   local_d[0], local_d[1], local_d[2],
                                   -half.x, -half.y, -half.z, half.x, half.y, half.z)
            if d > 0 and d < best_dist:
                best_dist = d
                best_entity = entity
                continue
        sc_comp = entity.get_component(SphereCollider)
        if sc_comp:
            pos = t.position
            oc = ray_origin - pos
            b = oc.dot(ray_dir)
            r2 = sc_comp.radius * sc_comp.radius
            c = oc.dot(oc) - r2
            disc = b * b - c
            if disc > 0:
                d = -b - disc ** 0.5
                if d > 0 and d < best_dist:
                    best_dist = d
                    best_entity = entity
                    continue
        pos = t.position
        sc = t.local_scale
        radius = max(sc.x, sc.y, sc.z) * 0.5
        oc = ray_origin - pos
        b = oc.dot(ray_dir)
        c = oc.dot(oc) - radius * radius
        disc = b * b - c
        if disc > 0:
            d = -b - disc ** 0.5
            if d > 0 and d < best_dist:
                best_dist = d
                best_entity = entity
    return best_entity


def pick_entities_in_rect(vp, rx: int, ry: int, rw: int, rh: int) -> list:
    scene = vp._engine.scene
    if not scene:
        return []
    result = []
    from core.components.transform import Transform
    from editor.viewport.projection import world_to_screen
    for entity in scene.get_all_entities():
        if not entity.active:
            continue
        t = entity.get_component(Transform)
        if not t:
            continue
        sp = world_to_screen(vp, t.position)
        if sp and rx <= sp[0] <= rx + rw and ry <= sp[1] <= ry + rh:
            result.append(entity)
    return result
