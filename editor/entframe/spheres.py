# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.maths.math3d import Vec3
from editor.entframe.base import _find_mesh_data
from editor.entframe.base import _mesh_data_local_center
from editor.entframe.base import _mesh_data_radius
from editor.entframe.base import _resolve_meshes
from editor.entframe.base import _transform_local_point
from editor.entframe.base import _vec_len
from editor.entframe.base import _world_scale_factor


def _mesh_spheres(comp, meshes, t, sf: float):
    try:
        md = _find_mesh_data(comp, meshes)
        if md is None:
            return []
        r = _mesh_data_radius(md)
        if r <= 1e-08:
            return []
        cx, cy, cz = _mesh_data_local_center(md)
        wc = _transform_local_point(t, cx, cy, cz)
        return [(wc, float(r * sf))]
    except Exception:
        return []


def _probuilder_spheres(comp, t, sf: float):
    try:
        pos = getattr(comp, "positions", None)
        if pos is None:
            return []
        try:
            if int(getattr(pos, "size", 0)) == 0:
                return []
        except Exception:
            pass
        bmin = pos.min(axis=0)
        bmax = pos.max(axis=0)
        dx = float(bmax[0] - bmin[0])
        dy = float(bmax[1] - bmin[1])
        dz = float(bmax[2] - bmin[2])
        cx = float((bmax[0] + bmin[0]) * 0.5)
        cy = float((bmax[1] + bmin[1]) * 0.5)
        cz = float((bmax[2] + bmin[2]) * 0.5)
        rad = float((dx * dx + dy * dy + dz * dz) ** 0.5 * 0.5)
        if rad <= 1e-08:
            return []
        wc = _transform_local_point(t, cx, cy, cz)
        return [(wc, float(rad * sf))]
    except Exception:
        return []


def _terrain_spheres(comp, t, sf: float):
    try:
        ws = float(getattr(comp, "world_size", 0.0))
        if ws <= 1e-08:
            return []
        hs = 0.0
        try:
            hf = getattr(comp, "_heightfield", None)
            if hf is not None:
                try:
                    hmin = float(hf.min())
                    hmax = float(hf.max())
                    hs = float(hmax - hmin)
                except Exception:
                    hs = 0.0
        except Exception:
            hs = 0.0
        if hs < 0.0 or hs > ws:
            hs = 0.0
        try:
            p = t.position
        except Exception:
            p = Vec3.zero()
        try:
            half = float(ws * 0.5)
            base = float((half * half + half * half) ** 0.5)
            if hs > 1e-08:
                base = float((base * base + (hs * 0.5) * (hs * 0.5)) ** 0.5)
            return [(p, float(base * sf))]
        except Exception:
            return [(p, float(ws * 0.70710678 * sf))]
    except Exception:
        return []


def _tree_spheres(comp, t, sf: float):
    try:
        h = float(getattr(comp, "height", 0.0))
        if h <= 1e-08:
            return []
        try:
            wc = _transform_local_point(t, 0.0, float(h * 0.5), 0.0)
        except Exception:
            try:
                wc = t.position
            except Exception:
                wc = Vec3.zero()
        return [(wc, float(h * 0.5 * sf))]
    except Exception:
        return []


def _collider_spheres(comp, t, sf: float):
    try:
        n = type(comp).__name__
        if n == "BoxCollider":
            try:
                size = getattr(comp, "size", None)
                center = getattr(comp, "center", None)
                cx = float(center.x) if hasattr(center, "x") else float(center[0])
                cy = float(center.y) if hasattr(center, "y") else float(center[1])
                cz = float(center.z) if hasattr(center, "z") else float(center[2])
                wc = _transform_local_point(t, cx, cy, cz)
                return [(wc, float(_vec_len(size) * 0.5 * sf))]
            except Exception:
                return []
        if n == "BoxCollider2D":
            try:
                size = getattr(comp, "size", None)
                off = getattr(comp, "offset", None)
                ox = float(off.x) if hasattr(off, "x") else float(off[0])
                oy = float(off.y) if hasattr(off, "y") else float(off[1])
                wc = _transform_local_point(t, ox, oy, 0.0)
                return [(wc, float(_vec_len(size) * 0.5 * sf))]
            except Exception:
                return []
        if n == "SphereCollider":
            try:
                r = float(getattr(comp, "radius", 0.0))
                center = getattr(comp, "center", None)
                cx = float(center.x) if hasattr(center, "x") else float(center[0])
                cy = float(center.y) if hasattr(center, "y") else float(center[1])
                cz = float(center.z) if hasattr(center, "z") else float(center[2])
                wc = _transform_local_point(t, cx, cy, cz)
                return [(wc, float(r * sf))]
            except Exception:
                return []
        if n == "CircleCollider2D":
            try:
                r = float(getattr(comp, "radius", 0.0))
                off = getattr(comp, "offset", None)
                ox = float(off.x) if hasattr(off, "x") else float(off[0])
                oy = float(off.y) if hasattr(off, "y") else float(off[1])
                wc = _transform_local_point(t, ox, oy, 0.0)
                return [(wc, float(r * sf))]
            except Exception:
                return []
        if n == "CapsuleCollider":
            try:
                r = float(getattr(comp, "radius", 0.0))
                h = float(getattr(comp, "height", 0.0))
                center = getattr(comp, "center", None)
                cx = float(center.x) if hasattr(center, "x") else float(center[0])
                cy = float(center.y) if hasattr(center, "y") else float(center[1])
                cz = float(center.z) if hasattr(center, "z") else float(center[2])
                wc = _transform_local_point(t, cx, cy, cz)
                half = float(h * 0.5)
                ext = float((half * half + r * r) ** 0.5)
                return [(wc, float(ext * sf))]
            except Exception:
                return []
    except Exception:
        pass
    return []


def _light_spheres(comp, t, sf: float):
    try:
        n = type(comp).__name__
        if n not in ("Light", "DirectionalLight", "PointLight", "SpotLight", "AreaLight"):
            return []
        try:
            aw = float(getattr(comp, "area_width", 0.0))
        except Exception:
            aw = 0.0
        try:
            ah = float(getattr(comp, "area_height", 0.0))
        except Exception:
            ah = 0.0
        if aw > 1e-08 or ah > 1e-08:
            try:
                p = t.position
            except Exception:
                p = Vec3.zero()
            return [(p, float(((aw * aw + ah * ah) ** 0.5 * 0.5) * sf))]
        return []
    except Exception:
        return []


def _entity_spheres(ent, meshes):
    try:
        t = ent.transform
    except Exception:
        return []
    if t is None:
        return []
    try:
        sf = _world_scale_factor(t)
    except Exception:
        sf = 1.0
    if sf <= 1e-08 or sf != sf or sf == float("inf"):
        sf = 1.0
    out = []
    try:
        comps = list(getattr(ent, "_components", {}).values())
    except Exception:
        comps = []
    for c in comps:
        try:
            if not getattr(c, "enabled", True):
                continue
        except Exception:
            pass
        try:
            n = type(c).__name__
        except Exception:
            continue
        try:
            if n == "MeshFilter" or n == "SkinnedMeshRenderer":
                out.extend(_mesh_spheres(c, meshes, t, sf))
            elif n == "ProBuilderMesh":
                out.extend(_probuilder_spheres(c, t, sf))
            elif n == "Terrain":
                out.extend(_terrain_spheres(c, t, sf))
            elif n == "Tree":
                out.extend(_tree_spheres(c, t, sf))
            elif n == "BoxCollider" or n == "BoxCollider2D" or n == "SphereCollider" or n == "CircleCollider2D" or n == "CapsuleCollider":
                out.extend(_collider_spheres(c, t, sf))
            elif n == "Light" or n == "DirectionalLight" or n == "PointLight" or n == "SpotLight" or n == "AreaLight":
                out.extend(_light_spheres(c, t, sf))
            else:
                continue
        except Exception:
            continue
    return out


def compute_entity_frame(entity, renderer=None):
    try:
        root_t = entity.transform
    except Exception:
        root_t = None
    try:
        root_pos = root_t.position if root_t is not None else Vec3.zero()
    except Exception:
        root_pos = Vec3.zero()
    try:
        root_sf = _world_scale_factor(root_t) if root_t is not None else 1.0
    except Exception:
        root_sf = 1.0
    try:
        meshes = _resolve_meshes(renderer)
    except Exception:
        meshes = None
    spheres = []
    try:
        stack = [entity]
        seen = {id(entity)}
        while stack:
            ent = stack.pop()
            try:
                spheres.extend(_entity_spheres(ent, meshes))
            except Exception:
                pass
            try:
                for ch in getattr(ent, "children", []):
                    try:
                        if id(ch) not in seen:
                            seen.add(id(ch))
                            stack.append(ch)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass
    if not spheres:
        try:
            return root_pos, float(max(1.0 * root_sf, 0.3))
        except Exception:
            return Vec3.zero(), 1.0
    try:
        center = spheres[0][0]
        radius = float(spheres[0][1])
    except Exception:
        return root_pos, float(max(1.0 * root_sf, 0.3))
    for i in range(1, len(spheres)):
        try:
            c = spheres[i][0]
            r = float(spheres[i][1])
            if r <= 1e-08:
                continue
            try:
                d = float(center.distance_to(c))
            except Exception:
                dx = float(c.x - center.x)
                dy = float(c.y - center.y)
                dz = float(c.z - center.z)
                d = float((dx * dx + dy * dy + dz * dz) ** 0.5)
            if d + r <= radius:
                continue
            if d + radius <= r:
                center = c
                radius = r
                continue
            nr = float((radius + d + r) * 0.5)
            if d > 1e-08:
                k = float((nr - radius) / d)
                center = Vec3(float(center.x + (c.x - center.x) * k), float(center.y + (c.y - center.y) * k), float(center.z + (c.z - center.z) * k))
            radius = nr
        except Exception:
            continue
    try:
        if radius != radius or radius == float("inf"):
            return root_pos, float(max(1.0 * root_sf, 0.3))
        if radius < 0.15:
            radius = 0.15
    except Exception:
        return root_pos, 1.0
    return center, float(radius)
