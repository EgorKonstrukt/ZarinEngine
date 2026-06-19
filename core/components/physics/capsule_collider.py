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

    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        tr = self.transform
        if not tr:
            return []
        radius = self.scaled_radius
        total_height = self.scaled_height
        half_h = max(0, total_height * 0.5 - radius)
        c = tr.local_position + tr.local_rotation.rotate_vec3(self.scaled_center)
        dir_idx = getattr(self, "direction", 1)
        axis_vecs = [Vec3.right(), Vec3.up(), Vec3.forward()]
        axis = axis_vecs[dir_idx] if dir_idx < 3 else Vec3.up()
        segments = 20
        color = [0.0, 1.0, 0.0, 0.6]
        top_center = c + tr.local_rotation.rotate_vec3(axis * half_h)
        bottom_center = c - tr.local_rotation.rotate_vec3(axis * half_h)
        lines: list[tuple[Vec3, Vec3, list[float]]] = []
        for ring_axis in range(3):
            if ring_axis == dir_idx:
                continue
            pts_top = []
            pts_bot = []
            for i in range(segments + 1):
                theta = 2.0 * math.pi * i / segments
                u = Vec3.right()
                v = Vec3.forward()
                if ring_axis == 0:
                    u = Vec3(0, 1, 0)
                    v = Vec3(0, 0, 1)
                elif ring_axis == 1:
                    u = Vec3(1, 0, 0)
                    v = Vec3(0, 0, 1)
                ring_pt = (u * math.cos(theta) + v * math.sin(theta)) * radius
                pts_top.append(top_center + tr.local_rotation.rotate_vec3(ring_pt))
                pts_bot.append(bottom_center + tr.local_rotation.rotate_vec3(ring_pt))
            for i in range(segments):
                lines.append((pts_top[i], pts_top[i + 1], color))
                lines.append((pts_bot[i], pts_bot[i + 1], color))
        for i in range(8):
            theta = 2.0 * math.pi * i / 8
            u = Vec3.right()
            v = Vec3.forward()
            if dir_idx == 0:
                u = Vec3(0, 1, 0)
                v = Vec3(0, 0, 1)
            elif dir_idx == 1:
                u = Vec3(1, 0, 0)
                v = Vec3(0, 0, 1)
            ring_pt = (u * math.cos(theta) + v * math.sin(theta)) * radius
            top_pt = top_center + tr.local_rotation.rotate_vec3(ring_pt)
            bot_pt = bottom_center + tr.local_rotation.rotate_vec3(ring_pt)
            lines.append((top_pt, bot_pt, color))
        return lines
