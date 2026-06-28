from __future__ import annotations
from core.ecs import Component, ComponentRegistry
import math
from core.math3d import Vec2, Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class CircleCollider2D(Component):
    _icon = "CircleCollider2D.png"
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C2"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("layer", "Layer", FieldType.LAYER),
            InspectorField("mask", "Collision Mask", FieldType.LAYER_MASK),
            InspectorField("offset", "Offset", FieldType.VEC2),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.offset: Vec2 = Vec2.zero()
        self.radius: float = 0.5
        self.is_trigger: bool = False
        self.material_friction: float = 0.6
        self.material_bounciness: float = 0.0

    @property
    def scaled_radius(self) -> float:
        tr = self.transform
        s = tr.local_scale if tr else Vec2.one()
        return self.radius * max(s.x, s.y)

    @property
    def scaled_offset(self) -> Vec2:
        tr = self.transform
        s = tr.local_scale if tr else Vec2.one()
        o = self.offset if isinstance(self.offset, Vec2) else Vec2(self.offset.x, self.offset.y)
        return Vec2(o.x * s.x, o.y * s.y)

    def gizmo_primitives(self):
        tr = self.transform
        if not tr:
            return None
        from core.math3d import Vec3
        from editor.gizmo.primitives import circle_lines
        off = self.scaled_offset
        c = (off.x, off.y, 0.0)
        color = [0.0, 1.0, 0.0, 0.6]
        return circle_lines(c, self.scaled_radius, color, tr.local_position, tr.local_rotation, Vec3.one())

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
            "offset": self.offset.to_list(), "radius": self.radius,
            "is_trigger": self.is_trigger, "friction": self.material_friction,
            "bounciness": self.material_bounciness,
            "layer": self.layer, "mask": self.mask,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> CircleCollider2D:
        cc = cls()
        cc.enabled = data.get("enabled", True)
        cc.offset = Vec2(*data.get("offset", [0, 0]))
        cc.radius = data.get("radius", 0.5)
        cc.is_trigger = data.get("is_trigger", False)
        cc.material_friction = data.get("friction", 0.6)
        cc.material_bounciness = data.get("bounciness", 0.0)
        cc.layer = data.get("layer", 0)
        cc.mask = data.get("mask", 0xFFFF)
        return cc
