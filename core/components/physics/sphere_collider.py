from __future__ import annotations
import math
from core.ecs import Component, ComponentRegistry
from core.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class SphereCollider(Component):
    _icon = "SphereCollider.png"
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False

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
    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        tr = self.transform
        if not tr:
            return []
        radius = self.scaled_radius
        c = tr.local_position + tr.local_rotation.rotate_vec3(self.scaled_center)
        segments = 24
        color = [0.0, 1.0, 0.0, 0.6]
        lines: list[tuple[Vec3, Vec3, list[float]]] = []
        for axis_idx in range(3):
            pts = []
            for i in range(segments + 1):
                theta = 2.0 * math.pi * i / segments
                if axis_idx == 0:
                    pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                elif axis_idx == 1:
                    pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                else:
                    pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                pts.append(c + tr.local_rotation.rotate_vec3(pt))
            for i in range(segments):
                lines.append((pts[i], pts[i + 1], color))
        return lines

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
