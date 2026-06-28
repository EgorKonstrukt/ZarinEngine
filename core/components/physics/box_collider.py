from __future__ import annotations
from core.ecs import Component, ComponentRegistry, InstancePrimitive
from core.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class BoxCollider(Component):
    _icon = "BoxCollider.png"
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
            InspectorField("size", "Size", FieldType.VEC3),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.center: Vec3 = Vec3.zero()
        self.size: Vec3 = Vec3.one()
        self.is_trigger: bool = False
        self.material_friction: float = 0.6
        self.material_bounciness: float = 0.0
    @property
    def scaled_size(self) -> Vec3:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        sz = self.size if isinstance(self.size, Vec3) else Vec3(*self.size)
        return Vec3(sz.x * s.x, sz.y * s.y, sz.z * s.z)
    @property
    def scaled_center(self) -> Vec3:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        return Vec3(c.x * s.x, c.y * s.y, c.z * s.z)
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "center": self.center.to_list(), "size": self.size.to_list(),
            "is_trigger": self.is_trigger, "friction": self.material_friction,
            "bounciness": self.material_bounciness,
            "layer": self.layer, "mask": self.mask,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> BoxCollider:
        bc = cls()
        bc.enabled = data.get("enabled", True)
        bc.center = Vec3(*data.get("center", [0,0,0]))
        bc.size = Vec3(*data.get("size", [1,1,1]))
        bc.is_trigger = data.get("is_trigger", False)
        bc.material_friction = data.get("friction", 0.6)
        bc.material_bounciness = data.get("bounciness", 0.0)
        bc.layer = data.get("layer", 0)
        bc.mask = data.get("mask", 0xFFFF)
        return bc

    def gizmo_primitives(self):
        tr = self.transform
        if not tr:
            return None
        from core.math3d import Vec3
        from editor.gizmo.primitives import box_lines
        c = (self.scaled_center.x, self.scaled_center.y, self.scaled_center.z)
        sz = (self.scaled_size.x, self.scaled_size.y, self.scaled_size.z)
        color = [0.0, 1.0, 0.0, 0.6]
        return box_lines(c, sz, color, tr.local_position, tr.local_rotation, Vec3.one())

    def gizmo_instance_data(self):
        tr = self.transform
        if not tr:
            return None
        import numpy as np
        from editor.gizmo.primitives import _quat_to_mat3
        R = _quat_to_mat3(tr.local_rotation)
        T = np.array([tr.local_position.x, tr.local_position.y, tr.local_position.z], dtype=np.float32)
        S = np.array([tr.local_scale.x, tr.local_scale.y, tr.local_scale.z], dtype=np.float32)
        c = np.array([self.center.x, self.center.y, self.center.z], dtype=np.float32)
        h = np.array([self.size.x * 0.5, self.size.y * 0.5, self.size.z * 0.5], dtype=np.float32)
        RS = R * S
        combined = np.eye(4, dtype=np.float32)
        combined[:3, :3] = RS * h
        combined[:3, 3] = RS @ c + T
        return InstancePrimitive('box', combined.ravel('F'), [0.0, 1.0, 0.0, 0.6])

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


