from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class BoxCollider(Component):
    _icon = "BoxCollider.png"
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("size", "Size", FieldType.VEC3),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
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
            "bounciness": self.material_bounciness
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
        return bc

    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        tr = self.transform
        if not tr:
            return []
        pos = tr.local_position
        rot = tr.local_rotation
        sz = self.scaled_size
        h = Vec3(sz.x * 0.5, sz.y * 0.5, sz.z * 0.5)
        c = pos + rot.rotate_vec3(self.scaled_center)
        corners = [
            c + Vec3(-h.x, -h.y, -h.z),
            c + Vec3( h.x, -h.y, -h.z),
            c + Vec3( h.x,  h.y, -h.z),
            c + Vec3(-h.x,  h.y, -h.z),
            c + Vec3(-h.x, -h.y,  h.z),
            c + Vec3( h.x, -h.y,  h.z),
            c + Vec3( h.x,  h.y,  h.z),
            c + Vec3(-h.x,  h.y,  h.z),
        ]
        color = [0.0, 1.0, 0.0, 0.6]
        edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        return [(corners[a], corners[b], color) for a, b in edges]
