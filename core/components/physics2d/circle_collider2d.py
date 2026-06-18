from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.math3d import Vec2
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class CircleCollider2D(Component):
    _icon = "CircleCollider2D.png"
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C2"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("offset", "Offset", FieldType.VEC2),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
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

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "offset": self.offset.to_list(), "radius": self.radius,
            "is_trigger": self.is_trigger, "friction": self.material_friction,
            "bounciness": self.material_bounciness,
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
        return cc
