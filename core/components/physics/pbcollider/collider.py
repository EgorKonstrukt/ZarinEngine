# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from core.ecs import Component, ComponentRegistry, InstancePrimitive
from core.maths.math3d import Vec3
from .base import ColliderBaseMixin, PhysBoneColliderType, _world_quat_of, _axis_index


@ComponentRegistry.register
class PhysBoneCollider(ColliderBaseMixin, Component):
    _icon = "SphereCollider.png"
    _allow_multiple = True
    _gizmo_icon_color = (90, 200, 120)
    _gizmo_icon_label = "PBC"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

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
