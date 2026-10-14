# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import math
import numpy as np
from core.maths.math3d import Vec3, Quat
from .types import PhysBoneIntegration, PhysBoneImmobileType
from .mathx import _clamp01, _world_quat_of, _quat_from_two_vecs
from .backend import _cy_step
def _apply_to_transforms_impl(self, final, anim_quat, weight):
    try:
        from core.math_helpers import mat4_inv_fast
    except Exception:
        mat4_inv_fast = None
    try:
        nodes = self._nodes
        scene = self._entity._scene if self._entity is not None else None
        if scene is None or not nodes or not final or len(final) != len(nodes):
            return
        new_wq = {}
        for i in range(len(nodes)):
            nd = nodes[i]
            if nd.is_virtual:
                continue
            try:
                ent = scene.get_entity(nd.entity_id)
                if ent is None or ent.transform is None:
                    continue
                tr = ent.transform
                if i == 0:
                    if nd.children:
                        try:
                            pp = final[0]
                            dx = 0.0
                            dy = 0.0
                            dz = 0.0
                            n = 0
                            for cix in nd.children:
                                cp = final[cix]
                                dx += cp.x - pp.x
                                dy += cp.y - pp.y
                                dz += cp.z - pp.z
                                n += 1
                            if n > 0:
                                dx /= n
                                dy /= n
                                dz /= n
                            l = math.sqrt(dx * dx + dy * dy + dz * dz)
                            if l > 1e-9:
                                desired = Vec3(dx / l, dy / l, dz / l)
                                ap = self._anim[0]
                                rest_dir = None
                                rdx = 0.0
                                rdy = 0.0
                                rdz = 0.0
                                rn2 = 0
                                for cix in nd.children:
                                    apc = self._anim[cix]
                                    rdx += apc.x - ap.x
                                    rdy += apc.y - ap.y
                                    rdz += apc.z - ap.z
                                    rn2 += 1
                                if rn2 > 0:
                                    rdx /= rn2
                                    rdy /= rn2
                                    rdz /= rn2
                                rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                                if rl > 1e-9:
                                    rest_dir = Vec3(rdx / rl, rdy / rl, rdz / rl)
                                if rest_dir is not None:
                                    arc = _quat_from_two_vecs(rest_dir, desired)
                                    base = anim_quat[0] if 0 < len(anim_quat) else _world_quat_of(tr)
                                    nq_world = arc * base
                                    try:
                                        nq_world = nq_world.normalized()
                                    except Exception:
                                        pass
                                    new_wq[i] = nq_world
                                    parent = ent.parent
                                    if parent is not None and parent.transform is not None:
                                        pwq = _world_quat_of(parent.transform)
                                        try:
                                            local = pwq.conjugate().normalized() * nq_world
                                            try:
                                                local = local.normalized()
                                            except Exception:
                                                pass
                                            tr.local_rotation = local
                                        except Exception:
                                            pass
                                    else:
                                        tr.local_rotation = nq_world
                        except Exception:
                            pass
                    continue
                p = nd.parent
                pent = scene.get_entity(nodes[p].entity_id) if p >= 0 else None
                if pent is None or pent.transform is None:
                    continue
                ptr = pent.transform
                fp = final[i]
                pp = final[p]
                handled = False
                try:
                    pwm = ptr.world_matrix._d
                    n0 = pwm[0, 0] * pwm[0, 0] + pwm[0, 1] * pwm[0, 1] + pwm[0, 2] * pwm[0, 2]
                    n1 = pwm[1, 0] * pwm[1, 0] + pwm[1, 1] * pwm[1, 1] + pwm[1, 2] * pwm[1, 2]
                    n2 = pwm[2, 0] * pwm[2, 0] + pwm[2, 1] * pwm[2, 1] + pwm[2, 2] * pwm[2, 2]
                    n3 = pwm[0, 0] * pwm[0, 0] + pwm[1, 0] * pwm[1, 0] + pwm[2, 0] * pwm[2, 0]
                    n4 = pwm[0, 1] * pwm[0, 1] + pwm[1, 1] * pwm[1, 1] + pwm[2, 1] * pwm[2, 1]
                    n5 = pwm[0, 2] * pwm[0, 2] + pwm[1, 2] * pwm[1, 2] + pwm[2, 2] * pwm[2, 2]
                    mxn = n0
                    mnn = n0
                    for _nv in (n1, n2, n3, n4, n5):
                        if _nv > mxn:
                            mxn = _nv
                        if _nv < mnn:
                            mnn = _nv
                    if mxn - mnn <= 1e-9 * (1.0 + mxn):
                        ssu = math.sqrt((n0 + n1 + n2 + n3 + n4 + n5) / 6.0)
                        if ssu < 1e-9:
                            ssu = 1.0
                        qp = new_wq.get(p)
                        if qp is None:
                            qp = _world_quat_of(ptr)
                        dx = (fp.x - pp.x) / ssu
                        dy = (fp.y - pp.y) / ssu
                        dz = (fp.z - pp.z) / ssu
                        qx = -qp.x
                        qy = -qp.y
                        qz = -qp.z
                        qw = qp.w
                        tx = 2.0 * (qy * dz - qz * dy)
                        ty = 2.0 * (qz * dx - qx * dz)
                        tz = 2.0 * (qx * dy - qy * dx)
                        lx = dx + qw * tx + (qy * tz - qz * ty)
                        ly = dy + qw * ty + (qz * tx - qx * tz)
                        lz = dz + qw * tz + (qx * ty - qy * tx)
                        tr.local_position = Vec3(float(lx), float(ly), float(lz))
                        handled = True
                except Exception:
                    handled = False
                if not handled:
                    try:
                        pwm = ptr.world_matrix._d
                    except Exception:
                        continue
                    if mat4_inv_fast is None:
                        continue
                    try:
                        inv = mat4_inv_fast(pwm)
                    except Exception:
                        continue
                    try:
                        wv = np.array([float(fp.x), float(fp.y), float(fp.z), 1.0], dtype=np.float64)
                        lv = wv @ inv
                        tr.local_position = Vec3(float(lv[0]), float(lv[1]), float(lv[2]))
                    except Exception:
                        continue
                if nd.children:
                    try:
                        pp2 = final[i]
                        dx = 0.0
                        dy = 0.0
                        dz = 0.0
                        n = 0
                        for cix in nd.children:
                            cp = final[cix]
                            dx += cp.x - pp2.x
                            dy += cp.y - pp2.y
                            dz += cp.z - pp2.z
                            n += 1
                        if n == 0:
                            continue
                        dx /= n
                        dy /= n
                        dz /= n
                        l = math.sqrt(dx * dx + dy * dy + dz * dz)
                        if l < 1e-9:
                            continue
                        desired = Vec3(dx / l, dy / l, dz / l)
                        ap = self._anim[i]
                        rdx = 0.0
                        rdy = 0.0
                        rdz = 0.0
                        rn2 = 0
                        for cix in nd.children:
                            apc = self._anim[cix]
                            rdx += apc.x - ap.x
                            rdy += apc.y - ap.y
                            rdz += apc.z - ap.z
                            rn2 += 1
                        if rn2 == 0:
                            continue
                        rdx /= rn2
                        rdy /= rn2
                        rdz /= rn2
                        rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                        if rl < 1e-9:
                            continue
                        rest_dir = Vec3(rdx / rl, rdy / rl, rdz / rl)
                        arc = _quat_from_two_vecs(rest_dir, desired)
                        base = anim_quat[i] if i < len(anim_quat) else _world_quat_of(tr)
                        nq_world = arc * base
                        try:
                            nq_world = nq_world.normalized()
                        except Exception:
                            pass
                        new_wq[i] = nq_world
                        pwq = new_wq.get(p)
                        if pwq is None:
                            pwq = _world_quat_of(ptr)
                        try:
                            local = pwq.conjugate().normalized() * nq_world
                            try:
                                local = local.normalized()
                            except Exception:
                                pass
                            tr.local_rotation = local
                        except Exception:
                            pass
                    except Exception:
                        pass
                else:
                    try:
                        rq = nd.rest_local_quat
                        tr.local_rotation = Quat(rq.x, rq.y, rq.z, rq.w)
                    except Exception:
                        pass
            except Exception:
                continue
    except Exception:
        pass
def _on_update_impl(self, dt: float):
    try:
        if self._entity is None or not self.enabled:
            return
        if not self._begin_frame():
            return
        try:
            fdt = float(dt)
        except Exception:
            fdt = 0.016
        if fdt <= 1e-6:
            return
        if fdt > 0.033:
            fdt = 0.033
        w = self._animator_weight()
        if w <= 0.001:
            try:
                self._pos = [Vec3(p.x, p.y, p.z) for p in self._anim]
                self._prev = [Vec3(p.x, p.y, p.z) for p in self._anim]
                self._apply_to_transforms(self._anim, self._anim_quat, 0.0)
            except Exception:
                pass
            return
        try:
            adv = self.integration_type
            if isinstance(adv, str):
                adv = PhysBoneIntegration(adv)
        except Exception:
            adv = PhysBoneIntegration.SIMPLIFIED
        if adv == PhysBoneIntegration.ADVANCED:
            iterations = 3
        else:
            iterations = 2
        try:
            substeps = int(math.ceil(fdt / (1.0 / 60.0)))
        except Exception:
            substeps = 1
        if substeps < 1:
            substeps = 1
        if substeps > 4:
            substeps = 4
        try:
            imt = self.immobile_type
            if isinstance(imt, str):
                imt = PhysBoneImmobileType(imt)
        except Exception:
            imt = PhysBoneImmobileType.ALL_MOTION
        nodes = self._nodes
        root_delta = Vec3.zero()
        try:
            r0 = self._anim[0]
            if self._prev_root_pos is not None and imt == PhysBoneImmobileType.WORLD_TRANSLATION:
                root_delta = Vec3(r0.x - self._prev_root_pos.x, r0.y - self._prev_root_pos.y, r0.z - self._prev_root_pos.z)
            self._prev_root_pos = Vec3(r0.x, r0.y, r0.z)
            try:
                self._prev_root_quat = Quat(self._anim_quat[0].x, self._anim_quat[0].y, self._anim_quat[0].z, self._anim_quat[0].w)
            except Exception:
                pass
        except Exception:
            pass
        if len(self._pos) != len(nodes) or len(self._prev) != len(nodes):
            self._pos = [Vec3(p.x, p.y, p.z) for p in self._anim]
            self._prev = [Vec3(p.x, p.y, p.z) for p in self._anim]
        if imt == PhysBoneImmobileType.WORLD_TRANSLATION:
            try:
                if root_delta.length_sq() > 1e-12:
                    for i in range(1, len(self._pos)):
                        p = self._pos[i]
                        self._pos[i] = Vec3(p.x + root_delta.x, p.y + root_delta.y, p.z + root_delta.z)
                        q = self._prev[i]
                        self._prev[i] = Vec3(q.x + root_delta.x, q.y + root_delta.y, q.z + root_delta.z)
            except Exception:
                pass
        sdt = fdt / float(substeps)
        try:
            colliders = self._resolve_colliders()
        except Exception:
            colliders = []
        fn = _cy_step()
        if fn is not None:
            try:
                final = self._step_cython(fn, fdt, substeps, iterations, colliders, w)
                try:
                    self._apply_to_transforms(final, self._anim_quat, w)
                except Exception:
                    pass
                try:
                    self._pos = final
                except Exception:
                    pass
                return
            except Exception:
                pass
        for _ in range(substeps):
            try:
                self._integrate(sdt)
            except Exception:
                pass
            for _it in range(iterations):
                try:
                    self._solve_lengths()
                except Exception:
                    pass
                try:
                    self._solve_limits()
                except Exception:
                    pass
                try:
                    if colliders:
                        self._solve_collisions(colliders)
                except Exception:
                    pass
        try:
            final = self._blend_final(w)
        except Exception:
            return
        try:
            self._apply_to_transforms(final, self._anim_quat, w)
        except Exception:
            pass
        try:
            self._pos = final
        except Exception:
            pass
    except Exception:
        pass
