from __future__ import annotations
import math
from core.ecs import Component, ComponentRegistry, InstancePrimitive
from core.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class SphereCollider(Component):
    _icon = "SphereCollider.png"
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("layer", "Layer", FieldType.LAYER),
            InspectorField("mask", "Collision Mask", FieldType.LAYER_MASK),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.center: Vec3 = Vec3.zero()
        self.radius: float = 0.5
        self.is_trigger: bool = False
        self.material_friction: float = 0.6
        self.material_bounciness: float = 0.0
    @property
    def scaled_radius(self) -> float:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        return self.radius * max(s.x, s.y, s.z)
    @property
    def scaled_center(self) -> Vec3:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        return Vec3(c.x * s.x, c.y * s.y, c.z * s.z)
    def gizmo_primitives(self):
        tr = self.transform
        if not tr:
            return None
        from core.math3d import Vec3
        from editor.gizmo.primitives import sphere_rings
        c = (self.scaled_center.x, self.scaled_center.y, self.scaled_center.z)
        color = [0.0, 1.0, 0.0, 0.6]
        return sphere_rings(c, self.scaled_radius, color, tr.local_position, tr.local_rotation, Vec3.one())

    def gizmo_instance_data(self):
        tr = self.transform
        if not tr:
            return None
        import numpy as np
        from editor.gizmo.primitives import _quat_to_mat3
        R = _quat_to_mat3(tr.local_rotation)
        T = np.array([tr.local_position.x, tr.local_position.y, tr.local_position.z], dtype=np.float32)
        sc = tr.local_scale
        max_s = max(sc.x, sc.y, sc.z)
        c = self.center
        scaled_c = np.array([c.x * sc.x, c.y * sc.y, c.z * sc.z], dtype=np.float32)
        r = self.radius * max_s
        combined = np.eye(4, dtype=np.float32)
        combined[:3, :3] = R * r
        combined[:3, 3] = R @ scaled_c + T
        return InstancePrimitive('sphere', combined.ravel('F'), [0.0, 1.0, 0.0, 0.6])

    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        prim = self.gizmo_primitives()
        if prim is None:
            return []
        s, e, c = prim
        n = s.shape[0]
        color = [float(c[0, 0]), float(c[0, 1]), float(c[0, 2]), float(c[0, 3])]
        return [(Vec3(float(s[i, 0]), float(s[i, 1]), float(s[i, 2])),
                 Vec3(float(e[i, 0]), float(e[i, 1]), float(e[i, 2])),
                 color) for i in range(n)]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "center": self.center.to_list(), "radius": self.radius,
            "is_trigger": self.is_trigger, "friction": self.material_friction,
            "bounciness": self.material_bounciness,
            "layer": self.layer, "mask": self.mask,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> SphereCollider:
        sc = cls()
        sc.enabled = data.get("enabled", True)
        sc.center = Vec3(*data.get("center", [0,0,0]))
        sc.radius = data.get("radius", 0.5)
        sc.is_trigger = data.get("is_trigger", False)
        sc.material_friction = data.get("friction", 0.6)
        sc.material_bounciness = data.get("bounciness", 0.0)
        sc.layer = data.get("layer", 0)
        sc.mask = data.get("mask", 0xFFFF)
        return sc
