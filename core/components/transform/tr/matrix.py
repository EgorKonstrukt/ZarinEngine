# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3, Quat, Mat4, FLOAT_TYPE
from core.math_helpers import mat4_mul_fast, mat4_inv_fast
from core.components.transform.tr.hierarchy import TransformHierarchyBase
try:
    from core._ecs_batch import batch_update_from_transforms as _batch_from_transforms
    from core._ecs_batch import batch_update_flat as _batch_flat
except ImportError:
    _batch_from_transforms = None
    _batch_flat = None
try:
    from core._ecs_batch import batch_update_from_transforms_soa as _batch_from_soa
except ImportError:
    _batch_from_soa = None
class TransformMatrixBase(TransformHierarchyBase):
    __slots__ = ()
    def _write_local_into(self, out):
        lr = self._local_rot
        rx = lr._x
        ry = lr._y
        rz = lr._z
        rw = lr._w
        ls = self._local_scale
        sx = ls._x
        sy = ls._y
        sz = ls._z
        lp = self._local_pos
        x2 = rx + rx
        y2 = ry + ry
        z2 = rz + rz
        xx = rx * x2
        xy = rx * y2
        xz = rx * z2
        yy = ry * y2
        yz = ry * z2
        zz = rz * z2
        wx = rw * x2
        wy = rw * y2
        wz = rw * z2
        r00 = 1.0 - (yy + zz)
        r01 = xy + wz
        r02 = xz - wy
        r10 = xy - wz
        r11 = 1.0 - (xx + zz)
        r12 = yz + wx
        r20 = xz + wy
        r21 = yz - wx
        r22 = 1.0 - (xx + yy)
        out[0, 0] = sx * r00
        out[0, 1] = sx * r01
        out[0, 2] = sx * r02
        out[0, 3] = 0.0
        out[1, 0] = sy * r10
        out[1, 1] = sy * r11
        out[1, 2] = sy * r12
        out[1, 3] = 0.0
        out[2, 0] = sz * r20
        out[2, 1] = sz * r21
        out[2, 2] = sz * r22
        out[2, 3] = 0.0
        out[3, 0] = lp._x
        out[3, 1] = lp._y
        out[3, 2] = lp._z
        out[3, 3] = 1.0
    def _update_world_matrix(self):
        if not self._dirty:
            return
        if self._world_target is not None:
            self._resolve_world_target()
            return
        ent = self._entity
        parent = ent._parent if ent is not None else None
        if parent is None:
            wm_d = self._world_matrix._d
            lp = self._local_pos
            lr = self._local_rot
            ls = self._local_scale
            rx = lr._x
            ry = lr._y
            rz = lr._z
            rw = lr._w
            sx = ls._x
            sy = ls._y
            sz = ls._z
            x2 = rx + rx
            y2 = ry + ry
            z2 = rz + rz
            xx = rx * x2
            xy = rx * y2
            xz = rx * z2
            yy = ry * y2
            yz = ry * z2
            zz = rz * z2
            wx = rw * x2
            wy = rw * y2
            wz = rw * z2
            wm_d[0, 0] = sx * (1.0 - (yy + zz))
            wm_d[0, 1] = sx * (xy + wz)
            wm_d[0, 2] = sx * (xz - wy)
            wm_d[0, 3] = 0.0
            wm_d[1, 0] = sy * (xy - wz)
            wm_d[1, 1] = sy * (1.0 - (xx + zz))
            wm_d[1, 2] = sy * (yz + wx)
            wm_d[1, 3] = 0.0
            wm_d[2, 0] = sz * (xz + wy)
            wm_d[2, 1] = sz * (yz - wx)
            wm_d[2, 2] = sz * (1.0 - (xx + yy))
            wm_d[2, 3] = 0.0
            wm_d[3, 0] = lp._x
            wm_d[3, 1] = lp._y
            wm_d[3, 2] = lp._z
            wm_d[3, 3] = 1.0
            self._dirty = False
            ent2 = self._entity
            if ent2 is not None:
                sc = ent2._scene
                if sc is not None:
                    slot = self._soa
                    if slot >= 0 and slot < sc._soa_cap:
                        sc._soa_world[slot] = wm_d
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
                for node in chain:
                    if node._dirty:
                        continue
                    e2 = node._entity
                    if e2 is None:
                        continue
                    sc2 = e2._scene
                    if sc2 is None:
                        continue
                    slot2 = node._soa
                    if slot2 >= 0 and slot2 < sc2._soa_cap:
                        sc2._soa_world[slot2] = node._world_matrix._d
                return
        tmp = None
        for node in reversed(chain):
            if node._world_target is not None:
                node._resolve_world_target()
                continue
            ne = node._entity
            parent_entity = ne._parent if ne is not None else None
            if parent_entity is not None:
                pt = parent_entity._transform
                if pt is not None:
                    if tmp is None:
                        tmp = np.empty((4, 4), dtype=FLOAT_TYPE)
                    node._write_local_into(tmp)
                    np.matmul(tmp, pt._world_matrix._d, out=node._world_matrix._d)
                    node._dirty = False
                    e3 = node._entity
                    if e3 is not None:
                        sc3 = e3._scene
                        if sc3 is not None:
                            slot3 = node._soa
                            if slot3 >= 0 and slot3 < sc3._soa_cap:
                                sc3._soa_world[slot3] = node._world_matrix._d
                    continue
            node._write_local_into(node._world_matrix._d)
            node._dirty = False
            e4 = node._entity
            if e4 is not None:
                sc4 = e4._scene
                if sc4 is not None:
                    slot4 = node._soa
                    if slot4 >= 0 and slot4 < sc4._soa_cap:
                        sc4._soa_world[slot4] = node._world_matrix._d
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
        self._soa_sync_self()
    def _build_local_matrix(self) -> Mat4:
        out = Mat4.__new__(Mat4)
        out._d = np.empty((4, 4), dtype=FLOAT_TYPE)
        self._write_local_into(out._d)
        return out
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
            wt = Mat4.__new__(Mat4)
            wt._d = m._d.copy()
        else:
            wt = Mat4(m)
        self._world_target = wt
        self._physics_dirty = True
        self._dirty = False
        self._mark_dirty()
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
