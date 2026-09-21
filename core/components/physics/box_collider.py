# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.ecs.ecs import Component, ComponentRegistry, InstancePrimitive
from core.maths.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class BoxCollider(Component):
    _icon = "BoxCollider.png"
    _allow_multiple = True
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
            InspectorField("physic_material", "Physic Material", FieldType.ASSET, resource_type="physicmaterial"),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.center: Vec3 = Vec3.zero()
        self.size: Vec3 = Vec3.one()
        self.is_trigger: bool = False
        self.physic_material: str = ""
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
            "physic_material": self.physic_material,
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
        bc.physic_material = data.get("physic_material", "") or ""
        bc.layer = data.get("layer", 0)
        bc.mask = data.get("mask", 0xFFFF)
        return bc

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
        hx, hy, hz = self.size.x * 0.5, self.size.y * 0.5, self.size.z * 0.5
        try:
            tv = self._entity._scene._transform_version
        except Exception:
            tv = None
        ck = getattr(self, "_gizmo_ck", None)
        if ck is not None and ck[0] == tv and ck[1] == px and ck[2] == py and ck[3] == pz and ck[4] == qx and ck[5] == qy and ck[6] == qz and ck[7] == qw and ck[8] == sx and ck[9] == sy and ck[10] == sz and ck[11] == cx and ck[12] == cy and ck[13] == cz and ck[14] == hx and ck[15] == hy and ck[16] == hz:
            return getattr(self, "_gizmo_prim", None)
        n = m.sqrt(qx*qx + qy*qy + qz*qz + qw*qw)
        if n > 1e-10:
            inv = 1.0/n; qx *= inv; qy *= inv; qz *= inv; qw *= inv
        xx, yy, zz = qx*qx, qy*qy, qz*qz
        xy, xz, yz = qx*qy, qx*qz, qy*qz
        wx, wy, wz = qw*qx, qw*qy, qw*qz
        r00 = 1.0-2.0*(yy+zz); r01 = 2.0*(xy-wz); r02 = 2.0*(xz+wy)
        r10 = 2.0*(xy+wz); r11 = 1.0-2.0*(xx+zz); r12 = 2.0*(yz-wx)
        r20 = 2.0*(xz-wy); r21 = 2.0*(yz+wx); r22 = 1.0-2.0*(xx+yy)
        a00 = r00*sx*hx; a01 = r01*sy*hy; a02 = r02*sz*hz
        a10 = r10*sx*hx; a11 = r11*sy*hy; a12 = r12*sz*hz
        a20 = r20*sx*hx; a21 = r21*sy*hy; a22 = r22*sz*hz
        b00 = r00*sx; b01 = r01*sy; b02 = r02*sz
        b10 = r10*sx; b11 = r11*sy; b12 = r12*sz
        b20 = r20*sx; b21 = r21*sy; b22 = r22*sz
        t0 = b00*cx+b01*cy+b02*cz+px
        t1 = b10*cx+b11*cy+b12*cz+py
        t2 = b20*cx+b21*cy+b22*cz+pz
        flat = [a00,a10,a20,0.0, a01,a11,a21,0.0, a02,a12,a22,0.0, t0,t1,t2,1.0]
        prim = InstancePrimitive('box', flat, [0.0, 1.0, 0.0, 0.6])
        try:
            self._gizmo_ck = (tv, px, py, pz, lr.x, lr.y, lr.z, lr.w, sx, sy, sz, cx, cy, cz, hx, hy, hz)
            self._gizmo_prim = prim
        except Exception:
            pass
        return prim


