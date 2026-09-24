# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from core.ecs.ecs import Component, ComponentRegistry
from core.maths.math3d import Vec3, Quat, Mat4, FLOAT_TYPE
from core.math_helpers import mat4_mul_fast, mat4_from_quaternion, mat4_translation, mat4_scale_mat, mat4_inv_fast
from core.components.inspector_meta import FieldType, InspectorField, ComponentInspectorMeta
try:
    from core._ecs_batch import batch_update_from_transforms as _batch_from_transforms
    from core._ecs_batch import batch_update_flat as _batch_flat
except ImportError:
    _batch_from_transforms = None
    _batch_flat = None
@ComponentRegistry.register
class Transform(Component):
    _icon = "Transform.png"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("local_position", "Position", FieldType.VEC3),
            InspectorField("local_euler_angles", "Rotation", FieldType.VEC3),
            InspectorField("local_scale", "Scale", FieldType.VEC3),
        ]

    __slots__ = ("_local_pos", "_local_rot", "_local_scale", "_world_matrix", "_world_target", "_dirty", "_physics_dirty")

    def __init__(self):
        super().__init__()
        self._local_pos: Vec3 = Vec3.zero()
        self._local_rot: Quat = Quat.identity()
        self._local_scale: Vec3 = Vec3.one()
        self._world_matrix: Mat4 = Mat4.identity()
        self._world_target: Mat4 | None = None
        self._dirty: bool = True
        self._physics_dirty: bool = False

    def _mark_dirty(self):
        if self._dirty:
            return
        ent = self._entity
        if ent is None:
            self._dirty = True
            return
        children = ent._children
        if not children:
            self._dirty = True
            scene = ent._scene
            if scene is not None:
                scene._dirty_roots.add(self)
                scene._spatial_dirty_entities.add(ent._id)
                scene._spatial_dirty = True
                scene._transform_version_pending = True
            return
        scene = ent._scene
        if scene is None:
            stack = [self]
            pop = stack.pop
            push = stack.append
            while stack:
                t = pop()
                if t._dirty:
                    continue
                t._dirty = True
                e = t._entity
                if e is None:
                    continue
                for child in e._children:
                    ct = child._transform
                    if ct is not None and not ct._dirty:
                        push(ct)
            return
        dirty_add = scene._dirty_roots.add
        spatial_set = scene._spatial_dirty_entities
        spatial_add = spatial_set.add
        stack = [self]
        pop = stack.pop
        push = stack.append
        while stack:
            t = pop()
            if t._dirty:
                continue
            t._dirty = True
            e = t._entity
            if e is None:
                continue
            dirty_add(t)
            spatial_add(e._id)
            for child in e._children:
                ct = child._transform
                if ct is not None and not ct._dirty:
                    push(ct)
        scene._spatial_dirty = True
        scene._transform_version_pending = True
    def _update_world_matrix(self):
        if not self._dirty:
            return
        if self._world_target is not None:
            self._resolve_world_target()
            return
        ent = self._entity
        parent = ent._parent if ent is not None else None
        if parent is None:
            if _batch_flat is not None:
                _batch_flat([self])
                return
            local = self._build_local_matrix()
            self._world_matrix._d[:, :] = local._d
            self._dirty = False
            return
        chain = [self]
        chain_append = chain.append
        p = parent
        while p is not None:
            pt = p._transform
            if pt is None:
                break
            if not pt._dirty and pt._world_target is None:
                break
            chain_append(pt)
            pe = pt._entity
            p = pe._parent if pe is not None else None
        nchain = len(chain)
        if nchain > 1 and _batch_from_transforms is not None:
            has_target = False
            for node in chain:
                if node._world_target is not None:
                    has_target = True
                    break
            if not has_target:
                chain.reverse()
                _batch_from_transforms(chain)
                return
        for node in reversed(chain):
            if node._world_target is not None:
                node._resolve_world_target()
                continue
            local = node._build_local_matrix()
            ne = node._entity
            parent_entity = ne._parent if ne is not None else None
            if parent_entity is not None:
                pt = parent_entity._transform
                if pt is not None:
                    np.matmul(local._d, pt._world_matrix._d, out=node._world_matrix._d)
                    node._dirty = False
                    continue
            node._world_matrix._d[:, :] = local._d
            node._dirty = False

    def _resolve_world_target(self):
        ent = self._entity
        parent_entity = ent._parent if ent is not None else None
        if parent_entity is not None:
            pt = parent_entity._transform
            if pt is None:
                pt = parent_entity.transform
            if pt is not None:
                pt._update_world_matrix()
                inv = mat4_inv_fast(pt._world_matrix._d)
                local = Mat4(mat4_mul_fast(self._world_target._d, inv))
                pos, rot, scale = local.decompose()
                self._local_pos = pos
                self._local_rot = rot
                self._local_scale = scale
        else:
            pos, rot, scale = self._world_target.decompose()
            self._local_pos = pos
            self._local_rot = rot
            self._local_scale = scale
        self._world_matrix._d[:, :] = self._world_target._d
        self._world_target = None
        self._dirty = False
    def _build_local_matrix(self) -> Mat4:
        lr = self._local_rot
        r = mat4_from_quaternion(lr._x, lr._y, lr._z, lr._w)
        ls = self._local_scale
        sx = ls._x; sy = ls._y; sz = ls._z
        lp = self._local_pos
        m = r
        if m.base is not None:
            m = m.copy()
        if sx != 1.0 or sy != 1.0 or sz != 1.0:
            m[0, 0] *= sx; m[0, 1] *= sx; m[0, 2] *= sx
            m[1, 0] *= sy; m[1, 1] *= sy; m[1, 2] *= sy
            m[2, 0] *= sz; m[2, 1] *= sz; m[2, 2] *= sz
        m[3, 0] = lp._x
        m[3, 1] = lp._y
        m[3, 2] = lp._z
        m[3, 3] = 1.0
        out = Mat4.__new__(Mat4)
        out._d = m
        return out
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
    @property
    def position(self) -> Vec3:
        wm = self._world_matrix
        if self._dirty:
            self._update_world_matrix()
            wm = self._world_matrix
        d = wm._d
        return Vec3(float(d[3, 0]), float(d[3, 1]), float(d[3, 2]))
    @position.setter
    def position(self, world_pos: Vec3):
        if type(world_pos) is Vec3:
            wp = world_pos
        elif isinstance(world_pos, Vec3):
            wp = world_pos
        elif isinstance(world_pos, np.ndarray):
            wp = Vec3(float(world_pos[0]), float(world_pos[1]), float(world_pos[2]))
        elif isinstance(world_pos, (tuple, list)):
            wp = Vec3(float(world_pos[0]), float(world_pos[1]), float(world_pos[2]))
        else:
            wp = world_pos
        ent = self._entity
        parent_entity = ent._parent if ent is not None else None
        if parent_entity is not None:
            pt = parent_entity._transform
            if pt is None:
                pt = parent_entity.transform
            if pt is not None:
                pt._update_world_matrix()
                inv = mat4_inv_fast(pt._world_matrix._d)
                world_arr = np.array([wp._x, wp._y, wp._z, 1.0], dtype=FLOAT_TYPE)
                local_arr = world_arr @ inv
                self._local_pos = Vec3(float(local_arr[0]), float(local_arr[1]), float(local_arr[2]))
                self._mark_dirty()
                self._physics_dirty = True
                return
        self._local_pos = wp
        self._mark_dirty()
        self._physics_dirty = True
    @property
    def world_matrix(self) -> Mat4:
        if self._dirty:
            self._update_world_matrix()
        return self._world_matrix

    @world_matrix.setter
    def world_matrix(self, m: Mat4):
        if isinstance(m, Mat4):
            self._world_target = Mat4.__new__(Mat4)
            self._world_target._d = m._d.copy()
        else:
            self._world_target = Mat4(m)
        self._dirty = True
        self._physics_dirty = True
        ent = self._entity
        if ent is not None:
            scene = ent._scene
            if scene is not None:
                scene._dirty_roots.add(self)
                scene._spatial_dirty_entities.add(ent._id)
                scene._spatial_dirty = True
                scene._transform_version_pending = True
    @property
    def forward(self) -> Vec3:
        wm = self._world_matrix
        if self._dirty:
            self._update_world_matrix()
            wm = self._world_matrix
        m = wm._d
        x = -float(m[2, 0]); y = -float(m[2, 1]); z = -float(m[2, 2])
        n = (x * x + y * y + z * z) ** 0.5
        if n > 1e-10:
            inv = 1.0 / n
            return Vec3(x * inv, y * inv, z * inv)
        return Vec3(0.0, 0.0, 0.0)
    @property
    def right(self) -> Vec3:
        wm = self._world_matrix
        if self._dirty:
            self._update_world_matrix()
            wm = self._world_matrix
        m = wm._d
        x = float(m[0, 0]); y = float(m[0, 1]); z = float(m[0, 2])
        n = (x * x + y * y + z * z) ** 0.5
        if n > 1e-10:
            inv = 1.0 / n
            return Vec3(x * inv, y * inv, z * inv)
        return Vec3(0.0, 0.0, 0.0)
    @property
    def up(self) -> Vec3:
        wm = self._world_matrix
        if self._dirty:
            self._update_world_matrix()
            wm = self._world_matrix
        m = wm._d
        x = float(m[1, 0]); y = float(m[1, 1]); z = float(m[1, 2])
        n = (x * x + y * y + z * z) ** 0.5
        if n > 1e-10:
            inv = 1.0 / n
            return Vec3(x * inv, y * inv, z * inv)
        return Vec3(0.0, 0.0, 0.0)
    def translate(self, delta: Vec3, world_space: bool = False):
        if world_space:
            p = self.position
            if type(delta) is Vec3:
                self.position = Vec3(p._x + delta._x, p._y + delta._y, p._z + delta._z)
            elif isinstance(delta, Vec3):
                self.position = Vec3(p._x + delta._x, p._y + delta._y, p._z + delta._z)
            else:
                self.position = Vec3(p._x + float(delta[0]), p._y + float(delta[1]), p._z + float(delta[2]))
        else:
            lp = self._local_pos
            if type(delta) is Vec3:
                lp._x += delta._x
                lp._y += delta._y
                lp._z += delta._z
            elif isinstance(delta, Vec3):
                lp._x += delta._x
                lp._y += delta._y
                lp._z += delta._z
            elif isinstance(delta, np.ndarray):
                lp._x += float(delta[0])
                lp._y += float(delta[1])
                lp._z += float(delta[2])
            else:
                try:
                    lp._x += float(delta[0])
                    lp._y += float(delta[1])
                    lp._z += float(delta[2])
                except Exception:
                    lp2 = self._local_pos + delta
                    self._local_pos = lp2
                    self._mark_dirty()
                    self._physics_dirty = True
                    return
            self._mark_dirty()
            self._physics_dirty = True
    def rotate(self, euler: Vec3):
        if type(euler) is Vec3:
            ex = euler._x; ey = euler._y; ez = euler._z
        elif isinstance(euler, Vec3):
            ex = euler._x; ey = euler._y; ez = euler._z
        else:
            ex = float(euler[0]); ey = float(euler[1]); ez = float(euler[2])
        hx = math.radians(ex) * 0.5
        hy = math.radians(ey) * 0.5
        hz = math.radians(ez) * 0.5
        sx = math.sin(hx); cx = math.cos(hx)
        sy = math.sin(hy); cy = math.cos(hy)
        sz = math.sin(hz); cz = math.cos(hz)
        qx = sx * cy * cz - cx * sy * sz
        qy = cx * sy * cz + sx * cy * sz
        qz = cx * cy * sz - sx * sy * cz
        qw = cx * cy * cz + sx * sy * sz
        lr = self._local_rot
        nx = lr._w * qx + lr._x * qw + lr._y * qz - lr._z * qy
        ny = lr._w * qy - lr._x * qz + lr._y * qw + lr._z * qx
        nz = lr._w * qz + lr._x * qy - lr._y * qx + lr._z * qw
        nw = lr._w * qw - lr._x * qx - lr._y * qy - lr._z * qz
        n = (nx * nx + ny * ny + nz * nz + nw * nw) ** 0.5
        if n > 1e-10:
            inv = 1.0 / n
            self._local_rot = Quat(nx * inv, ny * inv, nz * inv, nw * inv)
        else:
            self._local_rot = Quat(0.0, 0.0, 0.0, 1.0)
        self._mark_dirty()
        self._physics_dirty = True
    def look_at(self, target: Vec3, up: Vec3 = None):
        if up is None: up = Vec3.up()
        fwd = (target - self.position).normalized()
        self._local_rot = Quat.look_rotation(fwd, up)
        self._mark_dirty()
        self._physics_dirty = True
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

    @staticmethod
    def batch_update_world_matrices(transforms: list):
        n = len(transforms)
        if n == 0:
            return
        bft = _batch_from_transforms
        if bft is not None:
            need_py = False
            for t in transforms:
                if t._world_target is not None:
                    need_py = True
                    break
            if need_py:
                for t in transforms:
                    t._update_world_matrix()
            else:
                bft(transforms)
            return
        for t in transforms:
            t._update_world_matrix()

    @staticmethod
    def mark_many_dirty(transforms: list):
        n = len(transforms)
        if n == 0:
            return
        stack = []
        stack_append = stack.append
        for t in transforms:
            if not t._dirty:
                stack_append(t)
        pop = stack.pop
        while stack:
            t = pop()
            if t._dirty:
                continue
            t._dirty = True
            ent = t._entity
            if ent is None:
                continue
            sc = ent._scene
            if sc is not None:
                sc._dirty_roots.add(t)
                sc._spatial_dirty_entities.add(ent._id)
                sc._spatial_dirty = True
                sc._transform_version_pending = True
            children = ent._children
            for child in children:
                ct = child._transform
                if ct is not None and not ct._dirty:
                    stack_append(ct)
