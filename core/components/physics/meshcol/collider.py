# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from core.maths.math3d import Vec3
from core.ecs import Component, ComponentRegistry, GizmoPrimitive
from core.components.inspector_meta import FieldType, InspectorField
from .mode import CollisionMode
from .geometry import _load_mesh_data, _triangle_edges_np, _box_edges_np, _sphere_edges_np, _get_convex_hull_edges_np, _get_decimated_hull_edges_np, _edge_pairs_np


@ComponentRegistry.register
class MeshCollider(Component):
    _icon = "MeshCollider.png"
    _allow_multiple = True
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Mesh", FieldType.HEADER),
            InspectorField("mesh_path", "Mesh", FieldType.RESOURCE_PATH, file_filter="Collision Meshes (*.obj *.stl *.gltf *.glb *.stp *.step)"),
            InspectorField("collision_mode", "Collision Mode", FieldType.ENUM, enum_class=CollisionMode),
            InspectorField("max_vertices", "Max Vertices", FieldType.INT, min_val=0, max_val=100000, step=100, decimals=0),
            InspectorField("", "Collision", FieldType.HEADER),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
            InspectorField("layer", "Layer", FieldType.LAYER),
            InspectorField("mask", "Collision Mask", FieldType.LAYER_MASK),
            InspectorField("", "Material", FieldType.HEADER),
            InspectorField("physic_material", "Physic Material", FieldType.ASSET, resource_type="physicmaterial"),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.center: Vec3 = Vec3.zero()
        self.mesh_path: str = ""
        self.collision_mode: CollisionMode = CollisionMode.AUTO
        self.max_vertices: int = 2000
        self.is_trigger: bool = False
        self.physic_material: str = ""
        self.material_friction: float = 0.6
        self.material_bounciness: float = 0.0

    @property
    def scaled_center(self) -> Vec3:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        return Vec3(c.x * s.x, c.y * s.y, c.z * s.z)

    def _is_dynamic_body(self) -> bool:
        try:
            if self.is_trigger:
                return False
            ent = self.entity
            if ent is None:
                return False
            from core.components.physics.rigidbody import Rigidbody
            rb = ent.get_component(Rigidbody)
            if rb is None or not getattr(rb, "enabled", True):
                return False
            if getattr(rb, "is_kinematic", False):
                return True
            return float(getattr(rb, "mass", 0.0) or 0.0) > 0.0
        except Exception:
            return False

    def _effective_mode(self) -> CollisionMode:
        if self.collision_mode == CollisionMode.AUTO:
            return CollisionMode.MESH if not self._is_dynamic_body() else CollisionMode.CONVEX_HULL
        if self.collision_mode == CollisionMode.MESH and self._is_dynamic_body():
            return CollisionMode.CONVEX_HULL
        return self.collision_mode

    def _gizmo_sig(self):
        tr = self.transform
        if tr is None:
            return None
        c = self.center
        if isinstance(c, Vec3):
            cx, cy, cz = c.x, c.y, c.z
        else:
            cx, cy, cz = c[0], c[1], c[2]
        return (
            self.mesh_path, self.collision_mode.value, self.max_vertices,
            cx, cy, cz, self._is_dynamic_body(),
            tr.local_position.x, tr.local_position.y, tr.local_position.z,
            tr.local_rotation.x, tr.local_rotation.y, tr.local_rotation.z, tr.local_rotation.w,
            tr.local_scale.x, tr.local_scale.y, tr.local_scale.z,
        )

    def gizmo_primitives(self):
        if not self.mesh_path:
            return None
        tr = self.transform
        if not tr:
            return None
        sig = self._gizmo_sig()
        cached = getattr(self, "_mc_gizmo_cache", None)
        if cached is not None and cached[0] == sig:
            return cached[1]
        path = self.mesh_path
        md = _load_mesh_data(path)
        if md is None or md["num_verts"] == 0:
            return None
        c = self.center
        if isinstance(c, Vec3):
            co = np.array([c.x, c.y, c.z], dtype=np.float32)
        else:
            co = np.array([c[0], c[1], c[2]], dtype=np.float32)
        mode = self._effective_mode()
        edges_np = None
        if mode == CollisionMode.MESH:
            idx = md.get("indices")
            if idx is not None and len(idx) >= 3:
                edges_np = _triangle_edges_np(md["verts"], idx)
            if edges_np is None:
                edges_np = _get_convex_hull_edges_np(path)
        elif mode == CollisionMode.BOX:
            edges_np = _box_edges_np(md["mins"], md["maxs"])
        elif mode == CollisionMode.SPHERE:
            edges_np = _sphere_edges_np(md["center"], md["radius"])
        else:
            if self.max_vertices > 0:
                edges_np = _get_decimated_hull_edges_np(path, self.max_vertices)
            if edges_np is None:
                edges_np = _get_convex_hull_edges_np(path)
        if edges_np is None or len(edges_np) == 0:
            return None
        edges_np = np.ascontiguousarray(edges_np.astype(np.float32) + co)
        color = [0.0, 1.0, 0.0, 0.6]
        result = _edge_pairs_np(edges_np, color, tr.local_position, tr.local_rotation, tr.local_scale)
        self._mc_gizmo_cache = (sig, result)
        return result

    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        prim = self.gizmo_primitives()
        if prim is None:
            return []
        s, e, c = prim
        n = s.shape[0]
        color = [float(c[0, 0]), float(c[0, 1]), float(c[0, 2]), float(c[0, 3])]
        result = []
        for i in range(n):
            result.append((
                Vec3(float(s[i, 0]), float(s[i, 1]), float(s[i, 2])),
                Vec3(float(e[i, 0]), float(e[i, 1]), float(e[i, 2])),
                color,
            ))
        return result

    def gizmo(self):
        try:
            from core.engine.eng import Engine
            from core.components.physics.rigidbody import Rigidbody
            eng = Engine.instance()
            if eng and getattr(eng, 'play_mode', False) and self.entity:
                if self.entity.get_component(Rigidbody):
                    return []
            if eng:
                vp = eng.viewport
                cam = getattr(vp, '_cam', None) if vp else None
                cam_pos = cam.position if cam else None
                if cam_pos and self.entity:
                    tr = self.transform
                    if tr and (tr.position - cam_pos).length() > 20.0:
                        return []
        except Exception:
            pass
        prims = self.gizmo_primitives()
        if prims is None:
            return []
        s, e, c = prims
        if s.shape[0] == 0:
            return []
        return [GizmoPrimitive(s, e, c)]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "center": self.center.to_list(), "mesh_path": self.mesh_path,
            "collision_mode": self.collision_mode.value,
            "max_vertices": self.max_vertices,
            "is_trigger": self.is_trigger,
            "friction": self.material_friction,
            "bounciness": self.material_bounciness,
            "physic_material": self.physic_material,
            "layer": self.layer, "mask": self.mask,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> MeshCollider:
        mc = cls()
        mc.enabled = data.get("enabled", True)
        mc.center = Vec3(*data.get("center", [0, 0, 0]))
        mc.mesh_path = data.get("mesh_path", "") or ""
        mc.collision_mode = CollisionMode(data.get("collision_mode", "auto"))
        mc.max_vertices = data.get("max_vertices", 2000)
        mc.is_trigger = data.get("is_trigger", False)
        mc.material_friction = data.get("friction", 0.6)
        mc.material_bounciness = data.get("bounciness", 0.0)
        mc.physic_material = data.get("physic_material", "") or ""
        mc.layer = data.get("layer", 0)
        mc.mask = data.get("mask", 0xFFFF)
        return mc
