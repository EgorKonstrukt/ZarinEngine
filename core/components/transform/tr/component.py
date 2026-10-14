# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from core.ecs import Component
from core.maths.math3d import Vec3, Quat, Mat4
from core.components.inspector_meta import FieldType, InspectorField
class TransformBase(Component):
    _icon = "Transform.png"
    _show_gizmo_icon: bool = False
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Transform", FieldType.HEADER),
            InspectorField("local_position", "Position", FieldType.VEC3),
            InspectorField("local_euler_angles", "Rotation", FieldType.VEC3),
            InspectorField("local_scale", "Scale", FieldType.VEC3),
        ]
    __slots__ = ("_local_pos", "_local_rot", "_local_scale", "_world_matrix", "_world_target", "_dirty", "_physics_dirty", "_soa")
    def __init__(self):
        super().__init__()
        self._local_pos: Vec3 = Vec3.zero()
        self._local_rot: Quat = Quat.identity()
        self._local_scale: Vec3 = Vec3.one()
        self._world_matrix: Mat4 = Mat4.identity()
        self._world_target: Mat4 | None = None
        self._dirty: bool = True
        self._physics_dirty: bool = False
        self._soa: int = -1
    def _soa_sync_self(self):
        if self._dirty:
            return
        ent = self._entity
        if ent is None:
            return
        sc = ent._scene
        if sc is None:
            return
        slot = self._soa
        if slot < 0 or slot >= sc._soa_cap:
            return
        sc._soa_world[slot] = self._world_matrix._d
    @property
    def local_position(self) -> Vec3: return self._local_pos
    @local_position.setter
    def local_position(self, v: Vec3):
        if type(v) is Vec3:
            self._local_pos = v
        elif isinstance(v, Vec3):
            self._local_pos = v
        elif isinstance(v, np.ndarray):
            self._local_pos = Vec3(float(v[0]), float(v[1]), float(v[2]))
        elif isinstance(v, (tuple, list)):
            self._local_pos = Vec3(float(v[0]), float(v[1]), float(v[2]))
        else:
            self._local_pos = v
        self._mark_dirty()
        self._physics_dirty = True
    def set_local_position_xyz(self, x: float, y: float, z: float):
        lp = self._local_pos
        lp._x = x
        lp._y = y
        lp._z = z
        self._mark_dirty()
        self._physics_dirty = True
    @property
    def local_rotation(self) -> Quat: return self._local_rot
    @local_rotation.setter
    def local_rotation(self, v: Quat):
        if type(v) is Quat:
            self._local_rot = v.normalized()
        else:
            self._local_rot = v
        self._mark_dirty()
        self._physics_dirty = True
    def set_local_rotation_raw(self, v: Quat):
        self._local_rot = v
        self._mark_dirty()
        self._physics_dirty = True
    @property
    def local_scale(self) -> Vec3: return self._local_scale
    @local_scale.setter
    def local_scale(self, v: Vec3):
        if type(v) is Vec3:
            self._local_scale = v
        elif isinstance(v, Vec3):
            self._local_scale = v
        elif isinstance(v, np.ndarray):
            self._local_scale = Vec3(float(v[0]), float(v[1]), float(v[2]))
        elif isinstance(v, (tuple, list)):
            self._local_scale = Vec3(float(v[0]), float(v[1]), float(v[2]))
        else:
            self._local_scale = v
        self._mark_dirty()
        self._physics_dirty = True
    def set_local_scale_xyz(self, x: float, y: float, z: float):
        ls = self._local_scale
        ls._x = x
        ls._y = y
        ls._z = z
        self._mark_dirty()
        self._physics_dirty = True
    @property
    def local_euler_angles(self) -> Vec3: return self._local_rot.to_euler()
    @local_euler_angles.setter
    def local_euler_angles(self, v: Vec3):
        if type(v) is Vec3:
            self._local_rot = Quat.from_euler(v._x, v._y, v._z)
        elif isinstance(v, Vec3):
            self._local_rot = Quat.from_euler(v._x, v._y, v._z)
        else:
            self._local_rot = Quat.from_euler(float(v[0]), float(v[1]), float(v[2]))
        self._mark_dirty()
        self._physics_dirty = True
