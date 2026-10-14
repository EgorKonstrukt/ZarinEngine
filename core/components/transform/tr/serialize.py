# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.maths.math3d import Vec3, Quat
from core.components.transform.tr.matrix import TransformMatrixBase
class TransformSerializeBase(TransformMatrixBase):
    __slots__ = ()
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "local_position": self._local_pos.to_list(),
            "local_rotation": self._local_rot.to_list(),
            "local_scale": self._local_scale.to_list()
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> Transform:
        t = cls()
        t.enabled = data.get("enabled", True)
        p = data.get("local_position", [0,0,0])
        r = data.get("local_rotation", [0,0,0,1])
        s = data.get("local_scale", [1,1,1])
        t._local_pos = Vec3(*p)
        t._local_rot = Quat(r[0],r[1],r[2],r[3])
        t._local_scale = Vec3(*s)
        return t
