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
class CapsuleCollider(Component):
    _icon = "CapsuleCollider.png"
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
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.001, max_val=10000.0, step=0.01),
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
        self.height: float = 2.0
        self.direction: int = 1
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
            "physic_material": self.physic_material,
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
        cc.physic_material = data.get("physic_material", "") or ""
        cc.layer = data.get("layer", 0)
        cc.mask = data.get("mask", 0xFFFF)
        return cc

    def gizmo_instance_data(self):
        tr = self.transform
        if not tr:
            return None
        import math as m
        lp = tr.local_position
        lr = tr.local_rotation
        ls = tr.local_scale
        px, py, pz = lp.x, lp.y, lp.z
        qx, qy, qz, qw = lr.x, lr.y, lr.z, lr.w
        sx, sy, sz = ls.x, ls.y, ls.z
        cx, cy, cz = self.center.x, self.center.y, self.center.z
        rd = self.radius
        ht = self.height
        dd = self.direction
        try:
            tv = self._entity._scene._transform_version
        except Exception:
            tv = None
        ck = getattr(self, "_gizmo_ck", None)
        if ck is not None and ck[0] == tv and ck[1] == px and ck[2] == py and ck[3] == pz and ck[4] == qx and ck[5] == qy and ck[6] == qz and ck[7] == qw and ck[8] == sx and ck[9] == sy and ck[10] == sz and ck[11] == cx and ck[12] == cy and ck[13] == cz and ck[14] == rd and ck[15] == ht and ck[16] == dd:
            return getattr(self, "_gizmo_prim", None)
        hh = ht * 0.5 - rd
        if hh < 0.0:
            hh = 0.0
        ex = rd; ey = rd; ez = rd
        if dd == 0:
            ex = hh + rd
        elif dd == 1:
            ey = hh + rd
        else:
            ez = hh + rd
        n = m.sqrt(qx*qx + qy*qy + qz*qz + qw*qw)
        if n > 1e-10:
            inv = 1.0/n; qx *= inv; qy *= inv; qz *= inv; qw *= inv
        xx, yy, zz = qx*qx, qy*qy, qz*qz
        xy, xz, yz = qx*qy, qx*qz, qy*qz
        wx, wy, wz = qw*qx, qw*qy, qw*qz
        r00 = 1.0-2.0*(yy+zz); r01 = 2.0*(xy-wz); r02 = 2.0*(xz+wy)
        r10 = 2.0*(xy+wz); r11 = 1.0-2.0*(xx+zz); r12 = 2.0*(yz-wx)
        r20 = 2.0*(xz-wy); r21 = 2.0*(yz+wx); r22 = 1.0-2.0*(xx+yy)
        b00 = r00*sx; b01 = r01*sy; b02 = r02*sz
        b10 = r10*sx; b11 = r11*sy; b12 = r12*sz
        b20 = r20*sx; b21 = r21*sy; b22 = r22*sz
        a00 = b00*ex; a01 = b01*ey; a02 = b02*ez
        a10 = b10*ex; a11 = b11*ey; a12 = b12*ez
        a20 = b20*ex; a21 = b21*ey; a22 = b22*ez
        t0 = b00*cx+b01*cy+b02*cz+px
        t1 = b10*cx+b11*cy+b12*cz+py
        t2 = b20*cx+b21*cy+b22*cz+pz
        flat = [a00,a10,a20,0.0, a01,a11,a21,0.0, a02,a12,a22,0.0, t0,t1,t2,1.0]
        prim = InstancePrimitive('capsule', flat, [0.0, 1.0, 0.0, 0.6])
        try:
            self._gizmo_ck = (tv, px, py, pz, lr.x, lr.y, lr.z, lr.w, sx, sy, sz, cx, cy, cz, rd, ht, dd)
            self._gizmo_prim = prim
        except Exception:
            pass
        return prim
