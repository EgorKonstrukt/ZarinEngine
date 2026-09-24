# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from core.ecs.ecs import Component, ComponentRegistry, InstancePrimitive
from core.maths.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class SphereCollider(Component):
    _icon = "SphereCollider.png"
    _allow_multiple = True
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Collision", FieldType.HEADER),
            InspectorField("layer", "Layer", FieldType.LAYER),
            InspectorField("mask", "Collision Mask", FieldType.LAYER_MASK),
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
            InspectorField("", "Material", FieldType.HEADER),
            InspectorField("physic_material", "Physic Material", FieldType.ASSET, resource_type="physicmaterial"),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.center: Vec3 = Vec3.zero()
        self.radius: float = 0.5
        self.is_trigger: bool = False
        self.physic_material: str = ""
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

    def gizmo_instance_data(self):
        tr = self.transform
        if not tr:
            return None
        lp = tr.local_position
        lr = tr.local_rotation
        ls = tr.local_scale
        px, py, pz = lp.x, lp.y, lp.z
        qx, qy, qz, qw = lr.x, lr.y, lr.z, lr.w
        sx, sy, sz = ls.x, ls.y, ls.z
        cx, cy, cz = self.center.x, self.center.y, self.center.z
        rd = self.radius
        try:
            tv = self._entity._scene._transform_version
        except Exception:
            tv = None
        ck = getattr(self, "_gizmo_ck", None)
        if ck is not None and ck[0] == tv and ck[1] == px and ck[2] == py and ck[3] == pz and ck[4] == qx and ck[5] == qy and ck[6] == qz and ck[7] == qw and ck[8] == sx and ck[9] == sy and ck[10] == sz and ck[11] == cx and ck[12] == cy and ck[13] == cz and ck[14] == rd:
            return getattr(self, "_gizmo_prim", None)
        ms = sx
        if sy > ms:
            ms = sy
        if sz > ms:
            ms = sz
        r = rd * ms
        scx = cx * sx; scy = cy * sy; scz = cz * sz
        n = math.sqrt(qx*qx + qy*qy + qz*qz + qw*qw)
        if n > 1e-10:
            inv = 1.0/n; qx *= inv; qy *= inv; qz *= inv; qw *= inv
        xx, yy, zz = qx*qx, qy*qy, qz*qz
        xy, xz, yz = qx*qy, qx*qz, qy*qz
        wx, wy, wz = qw*qx, qw*qy, qw*qz
        r00 = 1.0-2.0*(yy+zz); r01 = 2.0*(xy-wz); r02 = 2.0*(xz+wy)
        r10 = 2.0*(xy+wz); r11 = 1.0-2.0*(xx+zz); r12 = 2.0*(yz-wx)
        r20 = 2.0*(xz-wy); r21 = 2.0*(yz+wx); r22 = 1.0-2.0*(xx+yy)
        a00 = r00*r; a01 = r01*r; a02 = r02*r
        a10 = r10*r; a11 = r11*r; a12 = r12*r
        a20 = r20*r; a21 = r21*r; a22 = r22*r
        t0 = r00*scx+r01*scy+r02*scz+px
        t1 = r10*scx+r11*scy+r12*scz+py
        t2 = r20*scx+r21*scy+r22*scz+pz
        flat = [a00,a10,a20,0.0, a01,a11,a21,0.0, a02,a12,a22,0.0, t0,t1,t2,1.0]
        prim = InstancePrimitive('sphere', flat, [0.0, 1.0, 0.0, 0.6])
        try:
            self._gizmo_ck = (tv, px, py, pz, lr.x, lr.y, lr.z, lr.w, sx, sy, sz, cx, cy, cz, rd)
            self._gizmo_prim = prim
        except Exception:
            pass
        return prim

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "center": self.center.to_list(), "radius": self.radius,
            "is_trigger": self.is_trigger, "friction": self.material_friction,
            "bounciness": self.material_bounciness,
            "physic_material": self.physic_material,
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
        sc.physic_material = data.get("physic_material", "") or ""
        sc.layer = data.get("layer", 0)
        sc.mask = data.get("mask", 0xFFFF)
        return sc
