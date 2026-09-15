# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import enum
import math
import numpy as np
from core.ecs.ecs import Component, ComponentRegistry, InstancePrimitive
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


@ComponentRegistry.register
class PhysBoneCollider(Component):
    _icon = "SphereCollider.png"
    _allow_multiple = True
    _gizmo_icon_color = (90, 200, 120)
    _gizmo_icon_label = "PBC"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

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

    def collide(self, pos: Vec3, particle_radius: float) -> Vec3:
        try:
            pr = max(0.0, float(particle_radius))
        except Exception:
            pr = 0.0
        try:
            st = self.shape_type
            if isinstance(st, str):
                try:
                    st = PhysBoneColliderType(st)
                except Exception:
                    st = PhysBoneColliderType.SPHERE
            if st == PhysBoneColliderType.PLANE:
                pl = self.world_plane()
                if pl is None:
                    return pos
                p0, n = pl
                dx = pos.x - p0.x
                dy = pos.y - p0.y
                dz = pos.z - p0.z
                d = dx * n.x + dy * n.y + dz * n.z
                if self.is_inside:
                    if d > -pr:
                        push = d + pr
                        return Vec3(pos.x - n.x * push, pos.y - n.y * push, pos.z - n.z * push)
                    return pos
                if d >= 0.0:
                    if d < pr:
                        push = pr - d
                        return Vec3(pos.x + n.x * push, pos.y + n.y * push, pos.z + n.z * push)
                    return pos
                nd = -d
                if nd < pr:
                    push = pr - nd
                    return Vec3(pos.x - n.x * push, pos.y - n.y * push, pos.z - n.z * push)
                return pos
            if st == PhysBoneColliderType.CAPSULE:
                cap = self.world_capsule()
                if cap is None:
                    return pos
                a, b, r = cap
                abx = b.x - a.x
                aby = b.y - a.y
                abz = b.z - a.z
                apx = pos.x - a.x
                apy = pos.y - a.y
                apz = pos.z - a.z
                denom = abx * abx + aby * aby + abz * abz
                if denom < 1e-12:
                    cx, cy, cz = a.x, a.y, a.z
                else:
                    t = (apx * abx + apy * aby + apz * abz) / denom
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                    cx = a.x + abx * t
                    cy = a.y + aby * t
                    cz = a.z + abz * t
                dx = pos.x - cx
                dy = pos.y - cy
                dz = pos.z - cz
                dist_sq = dx * dx + dy * dy + dz * dz
                rr = r + pr
                if self.is_inside:
                    dist = math.sqrt(dist_sq) if dist_sq > 1e-12 else 0.0
                    limit = r - pr
                    if limit <= 1e-9:
                        return Vec3(cx, cy, cz)
                    if dist > limit:
                        if dist < 1e-9:
                            return Vec3(cx + limit, cy, cz)
                        s = limit / dist
                        return Vec3(cx + dx * s, cy + dy * s, cz + dz * s)
                    return pos
                if dist_sq >= rr * rr:
                    return pos
                dist = math.sqrt(dist_sq) if dist_sq > 1e-12 else 0.0
                if dist < 1e-9:
                    return Vec3(pos.x + rr, pos.y, pos.z)
                s = rr / dist
                return Vec3(cx + dx * s, cy + dy * s, cz + dz * s)
            c = self.world_center()
            if c is None:
                return pos
            r = self.world_radius()
            dx = pos.x - c.x
            dy = pos.y - c.y
            dz = pos.z - c.z
            dist_sq = dx * dx + dy * dy + dz * dz
            if self.is_inside:
                dist = math.sqrt(dist_sq) if dist_sq > 1e-12 else 0.0
                limit = r - pr
                if limit <= 1e-9:
                    return Vec3(c.x, c.y, c.z)
                if dist > limit:
                    if dist < 1e-9:
                        return Vec3(c.x + limit, c.y, c.z)
                    s = limit / dist
                    return Vec3(c.x + dx * s, c.y + dy * s, c.z + dz * s)
                return pos
            rr = r + pr
            if dist_sq >= rr * rr:
                return pos
            dist = math.sqrt(dist_sq) if dist_sq > 1e-12 else 0.0
            if dist < 1e-9:
                return Vec3(c.x + rr, c.y, c.z)
            s = rr / dist
            return Vec3(c.x + dx * s, c.y + dy * s, c.z + dz * s)
        except Exception:
            return pos

    def gizmo_instance_data(self):
        if not self.show_gizmo:
            return None
        tr = self.transform
        if tr is None:
            return None
        try:
            st = self.shape_type
            if isinstance(st, str):
                try:
                    st = PhysBoneColliderType(st)
                except Exception:
                    st = PhysBoneColliderType.SPHERE
            if st == PhysBoneColliderType.PLANE:
                return None
            if st == PhysBoneColliderType.CAPSULE:
                cap = self.world_capsule()
                if cap is None:
                    return None
                a, b, r = cap
                cx = (a.x + b.x) * 0.5
                cy = (a.y + b.y) * 0.5
                cz = (a.z + b.z) * 0.5
                half = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2) * 0.5
                ax = _axis_index(self.direction)
                sc = np.array([r, r, r], dtype=np.float32)
                sc[ax] = half + r
                wq = _world_quat_of(tr)
                x, y, z, w = wq.x, wq.y, wq.z, wq.w
                nrm = math.sqrt(x * x + y * y + z * z + w * w)
                if nrm > 1e-10:
                    inv = 1.0 / nrm
                    x *= inv
                    y *= inv
                    z *= inv
                    w *= inv
                R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]], dtype=np.float32)
                combined = np.eye(4, dtype=np.float32)
                combined[:3, :3] = R * sc
                combined[:3, 3] = np.array([cx, cy, cz], dtype=np.float32)
                return InstancePrimitive("capsule", combined.ravel("F"), [0.2, 0.9, 0.5, 0.55])
            c = self.world_center()
            if c is None:
                return None
            r = self.world_radius()
            wq = _world_quat_of(tr)
            x, y, z, w = wq.x, wq.y, wq.z, wq.w
            nrm = math.sqrt(x * x + y * y + z * z + w * w)
            if nrm > 1e-10:
                inv = 1.0 / nrm
                x *= inv
                y *= inv
                z *= inv
                w *= inv
            R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]], dtype=np.float32)
            combined = np.eye(4, dtype=np.float32)
            combined[:3, :3] = R * r
            combined[:3, 3] = np.array([c.x, c.y, c.z], dtype=np.float32)
            return InstancePrimitive("sphere", combined.ravel("F"), [0.2, 0.9, 0.5, 0.55])
        except Exception:
            return None

    def gizmo_lines(self):
        if not self.show_gizmo:
            return []
        try:
            st = self.shape_type
            if isinstance(st, str):
                try:
                    st = PhysBoneColliderType(st)
                except Exception:
                    st = PhysBoneColliderType.SPHERE
            if st != PhysBoneColliderType.PLANE:
                return []
            pl = self.world_plane()
            if pl is None:
                return []
            p0, n = pl
            try:
                up = Vec3(0, 1, 0) if abs(n.y) < 0.9 else Vec3(1, 0, 0)
                u = n.cross(up).normalized()
                v = n.cross(u).normalized()
            except Exception:
                u = Vec3(1, 0, 0)
                v = Vec3(0, 0, 1)
            s = 0.5
            c00 = Vec3(p0.x - u.x * s - v.x * s, p0.y - u.y * s - v.y * s, p0.z - u.z * s - v.z * s)
            c10 = Vec3(p0.x + u.x * s - v.x * s, p0.y + u.y * s - v.y * s, p0.z + u.z * s - v.z * s)
            c11 = Vec3(p0.x + u.x * s + v.x * s, p0.y + u.y * s + v.y * s, p0.z + u.z * s + v.z * s)
            c01 = Vec3(p0.x - u.x * s + v.x * s, p0.y - u.y * s + v.y * s, p0.z - u.z * s + v.z * s)
            col = [0.2, 0.9, 0.5, 0.8]
            return [(c00, c10, col), (c10, c11, col), (c11, c01, col), (c01, c00, col), (p0, Vec3(p0.x + n.x * 0.3, p0.y + n.y * 0.3, p0.z + n.z * 0.3), col)]
        except Exception:
            return []

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
