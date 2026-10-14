# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import enum
import math
from core.maths.math3d import Vec3, Quat
from core.components.inspector_meta import FieldType, InspectorField


class PhysBoneColliderType(enum.Enum):
    SPHERE = "sphere"
    CAPSULE = "capsule"
    PLANE = "plane"


class PhysBoneColliderDirection(enum.Enum):
    X = "x"
    Y = "y"
    Z = "z"


def _as_vec3(value, default):
    if isinstance(value, Vec3):
        return value
    try:
        return Vec3(float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        return default


def _world_quat_of(tr):
    try:
        m = tr.world_matrix._d
        trace = float(m[0, 0] + m[1, 1] + m[2, 2])
        if trace > 0.0:
            s = 0.5 / math.sqrt(trace + 1.0)
            q = ((float(m[2, 1] - m[1, 2]) * s), (float(m[0, 2] - m[2, 0]) * s), (float(m[1, 0] - m[0, 1]) * s), (0.25 / s))
        elif float(m[0, 0]) > float(m[1, 1]) and float(m[0, 0]) > float(m[2, 2]):
            s = 2.0 * math.sqrt(1.0 + float(m[0, 0]) - float(m[1, 1]) - float(m[2, 2]))
            q = (((float(m[2, 1]) - float(m[1, 2])) / s), ((float(m[0, 1]) + float(m[1, 0])) / s), ((float(m[0, 2]) + float(m[2, 0])) / s), (0.25 * s))
        elif float(m[1, 1]) > float(m[2, 2]):
            s = 2.0 * math.sqrt(1.0 + float(m[1, 1]) - float(m[0, 0]) - float(m[2, 2]))
            q = (((float(m[0, 1]) + float(m[1, 0])) / s), (0.25 * s), ((float(m[1, 2]) + float(m[2, 1])) / s), ((float(m[0, 2]) - float(m[2, 0])) / s))
        else:
            s = 2.0 * math.sqrt(1.0 + float(m[2, 2]) - float(m[0, 0]) - float(m[1, 1]))
            q = (((float(m[0, 2]) + float(m[2, 0])) / s), ((float(m[1, 2]) + float(m[2, 1])) / s), (0.25 * s), ((float(m[1, 0]) - float(m[0, 1])) / s))
        return Quat(-q[0], -q[1], -q[2], q[3]).normalized()
    except Exception:
        try:
            return tr.local_rotation.normalized()
        except Exception:
            return Quat.identity()


def _axis_index(direction):
    try:
        v = direction.value if isinstance(direction, PhysBoneColliderDirection) else str(direction).lower()
    except Exception:
        v = "y"
    if v == "x":
        return 0
    if v == "z":
        return 2
    return 1


class ColliderBaseMixin:
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("shape_type", "Shape Type", FieldType.ENUM, enum_class=PhysBoneColliderType),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.001, max_val=10.0, step=0.005, decimals=4),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.001, max_val=10.0, step=0.01, decimals=4),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("direction", "Direction", FieldType.ENUM, enum_class=PhysBoneColliderDirection),
            InspectorField("plane_normal", "Plane Normal", FieldType.VEC3),
            InspectorField("", "Behavior", FieldType.HEADER),
            InspectorField("is_inside", "Inside Bounds", FieldType.BOOL),
            InspectorField("", "Gizmos", FieldType.HEADER),
            InspectorField("show_gizmo", "Show Gizmo", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.shape_type: PhysBoneColliderType = PhysBoneColliderType.SPHERE
        self.radius: float = 0.05
        self.height: float = 0.2
        self.center: Vec3 = Vec3.zero()
        self.direction: PhysBoneColliderDirection = PhysBoneColliderDirection.Y
        self.plane_normal: Vec3 = Vec3(0, 1, 0)
        self.is_inside: bool = False
        self.show_gizmo: bool = True

    def world_center(self) -> Vec3 | None:
        tr = self.transform
        if tr is None:
            return None
        try:
            wq = _world_quat_of(tr)
            off = self.center if isinstance(self.center, Vec3) else Vec3.zero()
            rotated = wq.rotate_vec3(off)
            p = tr.position
            return Vec3(p.x + rotated.x, p.y + rotated.y, p.z + rotated.z)
        except Exception:
            try:
                return tr.position
            except Exception:
                return None

    def world_radius(self) -> float:
        try:
            tr = self.transform
            if tr is None:
                return max(0.001, float(self.radius))
            s = tr.local_scale
            m = max(abs(s.x), abs(s.y), abs(s.z))
            if m < 1e-6:
                m = 1.0
            return max(0.001, float(self.radius) * float(m))
        except Exception:
            return max(0.001, float(self.radius))

    def world_capsule(self):
        c = self.world_center()
        if c is None:
            return None
        tr = self.transform
        r = self.world_radius()
        try:
            s = tr.local_scale if tr is not None else Vec3.one()
            ax = _axis_index(self.direction)
            s_axis = abs(float((s.x, s.y, s.z)[ax])) if isinstance(s, Vec3) else 1.0
            if s_axis < 1e-6:
                s_axis = 1.0
            h = max(float(self.height) * float(s_axis), r * 2.0)
        except Exception:
            h = max(float(self.height), r * 2.0)
            ax = _axis_index(self.direction)
        half = max(0.0, h * 0.5 - r)
        if half <= 1e-9:
            return (c, c, r)
        try:
            wq = _world_quat_of(tr) if tr is not None else Quat.identity()
            if ax == 0:
                axis = wq.rotate_vec3(Vec3(1, 0, 0))
            elif ax == 2:
                axis = wq.rotate_vec3(Vec3(0, 0, 1))
            else:
                axis = wq.rotate_vec3(Vec3(0, 1, 0))
            try:
                axis = axis.normalized()
            except Exception:
                pass
        except Exception:
            axis = Vec3(0, 1, 0)
        a = Vec3(c.x - axis.x * half, c.y - axis.y * half, c.z - axis.z * half)
        b = Vec3(c.x + axis.x * half, c.y + axis.y * half, c.z + axis.z * half)
        return (a, b, r)

    def world_plane(self):
        c = self.world_center()
        if c is None:
            return None
        tr = self.transform
        try:
            wq = _world_quat_of(tr) if tr is not None else Quat.identity()
            n = self.plane_normal if isinstance(self.plane_normal, Vec3) else Vec3(0, 1, 0)
            if n.length_sq() < 1e-12:
                n = Vec3(0, 1, 0)
            nw = wq.rotate_vec3(n).normalized()
            return (c, nw)
        except Exception:
            return (c, Vec3(0, 1, 0))

    def serialize(self) -> dict:
        d = super().serialize()
        try:
            st = self.shape_type.value if isinstance(self.shape_type, PhysBoneColliderType) else str(self.shape_type)
        except Exception:
            st = "sphere"
        try:
            dr = self.direction.value if isinstance(self.direction, PhysBoneColliderDirection) else str(self.direction)
        except Exception:
            dr = "y"
        d.update({
            "shape_type": st,
            "radius": float(self.radius),
            "height": float(self.height),
            "center": self.center.to_list() if isinstance(self.center, Vec3) else [0, 0, 0],
            "direction": dr,
            "plane_normal": self.plane_normal.to_list() if isinstance(self.plane_normal, Vec3) else [0, 1, 0],
            "is_inside": bool(self.is_inside),
            "show_gizmo": bool(self.show_gizmo),
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> PhysBoneCollider:
        inst = cls()
        inst.enabled = data.get("enabled", True)
        try:
            inst.shape_type = PhysBoneColliderType(data.get("shape_type", "sphere"))
        except Exception:
            inst.shape_type = PhysBoneColliderType.SPHERE
        try:
            inst.direction = PhysBoneColliderDirection(data.get("direction", "y"))
        except Exception:
            inst.direction = PhysBoneColliderDirection.Y
        inst.radius = float(data.get("radius", 0.05))
        inst.height = float(data.get("height", 0.2))
        inst.center = _as_vec3(data.get("center", [0, 0, 0]), Vec3.zero())
        inst.plane_normal = _as_vec3(data.get("plane_normal", [0, 1, 0]), Vec3(0, 1, 0))
        inst.is_inside = bool(data.get("is_inside", False))
        inst.show_gizmo = bool(data.get("show_gizmo", True))
        return inst
