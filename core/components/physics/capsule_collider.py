from __future__ import annotations
import math
from core.ecs import Component, ComponentRegistry
from core.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class CapsuleCollider(Component):
    _icon = "CapsuleCollider.png"
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("layer", "Layer", FieldType.LAYER),
            InspectorField("mask", "Collision Mask", FieldType.LAYER_MASK),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.center: Vec3 = Vec3.zero()
        self.radius: float = 0.5
        self.height: float = 2.0
        self.direction: int = 1
        self.is_trigger: bool = False
        # ХУЙНЯ: нет material_friction и material_bounciness.
        # У BoxCollider и SphereCollider есть, у капсулы — похуй.
        # PhysicsScene._find_shape() для CapsuleCollider не читает friction/restitution,
        # так что по дефолту 0.6/0.0. Но в инспекторе полей нет — кастомизировать нельзя.
    @property
    def scaled_radius(self) -> float:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        return self.radius * max(s.x, s.y, s.z)
    @property
    def scaled_height(self) -> float:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        scale_val = s.y
        if self.direction == 0:
            scale_val = s.x
        elif self.direction == 2:
            scale_val = s.z
        return self.height * scale_val
    @property
    def scaled_center(self) -> Vec3:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        return Vec3(c.x * s.x, c.y * s.y, c.z * s.z)
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "center": self.center.to_list(), "radius": self.radius,
            "height": self.height, "direction": self.direction, "is_trigger": self.is_trigger,
            "layer": self.layer, "mask": self.mask,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> CapsuleCollider:
        cc = cls()
        cc.enabled = data.get("enabled", True)
        cc.center = Vec3(*data.get("center", [0,0,0]))
        cc.radius = data.get("radius", 0.5)
        cc.height = data.get("height", 2.0)
        cc.direction = data.get("direction", 1)
        cc.is_trigger = data.get("is_trigger", False)
        cc.layer = data.get("layer", 0)
        cc.mask = data.get("mask", 0xFFFF)
        return cc

    def gizmo_primitives(self):
        tr = self.transform
        if not tr:
            return None
        from core.math3d import Vec3
        from editor.gizmo.primitives import capsule_lines
        c = (self.scaled_center.x, self.scaled_center.y, self.scaled_center.z)
        color = [0.0, 1.0, 0.0, 0.6]
        dir_idx = getattr(self, "direction", 1)
        return capsule_lines(c, self.scaled_radius, self.scaled_height, dir_idx,
                             color, tr.local_position, tr.local_rotation, Vec3.one())

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
