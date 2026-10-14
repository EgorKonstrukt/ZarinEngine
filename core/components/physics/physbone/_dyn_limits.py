# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import math
from core.maths.math3d import Vec3, Quat
from .types import PhysBoneLimitType
from .mathx import _quat_from_two_vecs
def _solve_limits_impl(self):
    try:
        lt = self.limit_type
        if isinstance(lt, str):
            try:
                lt = PhysBoneLimitType(lt)
            except Exception:
                lt = PhysBoneLimitType.NONE
        if lt == PhysBoneLimitType.NONE:
            return
        nodes = self._nodes
        anim = self._anim
        for i in range(1, len(nodes)):
            try:
                nd = nodes[i]
                p = nd.parent
                if p < 0:
                    continue
                t = nd.t
                ma = self._pb_value(self.max_angle, self.max_angle_curve, t, 0.0, 180.0)
                if ma >= 179.9:
                    continue
                if ma <= 1e-6:
                    try:
                        ap = anim[p]
                        ac = anim[i]
                        pp = self._pos[p]
                        dx = ac.x - ap.x
                        dy = ac.y - ap.y
                        dz = ac.z - ap.z
                        l = math.sqrt(dx * dx + dy * dy + dz * dz)
                        cp = self._pos[i]
                        cl = math.sqrt((cp.x - pp.x) ** 2 + (cp.y - pp.y) ** 2 + (cp.z - pp.z) ** 2)
                        if l < 1e-9 or cl < 1e-9:
                            continue
                        inv = cl / l
                        self._pos[i] = Vec3(pp.x + dx * inv, pp.y + dy * inv, pp.z + dz * inv)
                    except Exception:
                        pass
                    continue
                pp = self._pos[p]
                cp = self._pos[i]
                cdx = cp.x - pp.x
                cdy = cp.y - pp.y
                cdz = cp.z - pp.z
                clen = math.sqrt(cdx * cdx + cdy * cdy + cdz * cdz)
                if clen < 1e-9:
                    continue
                cdx /= clen
                cdy /= clen
                cdz /= clen
                if lt == PhysBoneLimitType.HINGE:
                    self._solve_hinge(i, ma, (cdx, cdy, cdz), clen)
                    continue
                gp = nodes[p].parent
                if gp < 0:
                    try:
                        ap = anim[p]
                        ac = anim[i]
                        rdx = ac.x - ap.x
                        rdy = ac.y - ap.y
                        rdz = ac.z - ap.z
                        rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                        if rl < 1e-9:
                            continue
                        rdx /= rl
                        rdy /= rl
                        rdz /= rl
                        dot = cdx * rdx + cdy * rdy + cdz * rdz
                        if dot > 1.0:
                            dot = 1.0
                        if dot < -1.0:
                            dot = -1.0
                        ang = math.degrees(math.acos(dot))
                        if ang <= ma + 1e-6:
                            continue
                        arc = _quat_from_two_vecs(Vec3(cdx, cdy, cdz), Vec3(rdx, rdy, rdz))
                        try:
                            back = arc.conjugate().normalized()
                        except Exception:
                            back = Quat.identity()
                        excess = ang - ma
                        corr = Quat.from_axis_angle(Vec3(back.x, back.y, back.z) if (abs(back.x) + abs(back.y) + abs(back.z)) > 1e-9 else Vec3(1, 0, 0), 0.0)
                        try:
                            axis = Vec3(cdy * rdz - cdz * rdy, cdz * rdx - cdx * rdz, cdx * rdy - cdy * rdx)
                            if axis.length_sq() < 1e-12:
                                axis = Vec3(1, 0, 0)
                            else:
                                axis = axis.normalized()
                            corr = Quat.from_axis_angle(axis, excess)
                        except Exception:
                            continue
                        nd2 = corr.rotate_vec3(Vec3(cdx, cdy, cdz))
                        try:
                            nd2 = nd2.normalized()
                        except Exception:
                            pass
                        self._pos[i] = Vec3(pp.x + nd2.x * clen, pp.y + nd2.y * clen, pp.z + nd2.z * clen)
                    except Exception:
                        continue
                else:
                    try:
                        gpp = self._pos[gp]
                        pdx = pp.x - gpp.x
                        pdy = pp.y - gpp.y
                        pdz = pp.z - gpp.z
                        plen = math.sqrt(pdx * pdx + pdy * pdy + pdz * pdz)
                        ap = anim[p]
                        ag = anim[gp]
                        ac = anim[i]
                        rdx = ac.x - ap.x
                        rdy = ac.y - ap.y
                        rdz = ac.z - ap.z
                        rpx = ap.x - ag.x
                        rpy = ap.y - ag.y
                        rpz = ap.z - ag.z
                        rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                        rpl = math.sqrt(rpx * rpx + rpy * rpy + rpz * rpz)
                        if plen < 1e-9 or rl < 1e-9 or rpl < 1e-9:
                            continue
                        pdx /= plen
                        pdy /= plen
                        pdz /= plen
                        rdx /= rl
                        rdy /= rl
                        rdz /= rl
                        rpx /= rpl
                        rpy /= rpl
                        rpz /= rpl
                        align = _quat_from_two_vecs(Vec3(pdx, pdy, pdz), Vec3(rpx, rpy, rpz))
                        cal = align.rotate_vec3(Vec3(cdx, cdy, cdz))
                        try:
                            cal = cal.normalized()
                        except Exception:
                            pass
                        restv = Vec3(rdx, rdy, rdz)
                        dot = cal.x * restv.x + cal.y * restv.y + cal.z * restv.z
                        if dot > 1.0:
                            dot = 1.0
                        if dot < -1.0:
                            dot = -1.0
                        ang = math.degrees(math.acos(dot))
                        if ang <= ma + 1e-6:
                            continue
                        try:
                            axis = Vec3(cal.y * restv.z - cal.z * restv.y, cal.z * restv.x - cal.x * restv.z, cal.x * restv.y - cal.y * restv.x)
                            if axis.length_sq() < 1e-12:
                                continue
                            axis = axis.normalized()
                            corr = Quat.from_axis_angle(axis, ang - ma)
                            fixed = corr.rotate_vec3(cal)
                            try:
                                fixed = fixed.normalized()
                            except Exception:
                                pass
                            try:
                                back = align.conjugate().normalized()
                            except Exception:
                                back = Quat.identity()
                            world_fixed = back.rotate_vec3(fixed)
                            try:
                                world_fixed = world_fixed.normalized()
                            except Exception:
                                pass
                            self._pos[i] = Vec3(pp.x + world_fixed.x * clen, pp.y + world_fixed.y * clen, pp.z + world_fixed.z * clen)
                        except Exception:
                            continue
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
def _solve_hinge_impl(self, idx, max_angle, cur_dir_t, cur_len):
    try:
        nodes = self._nodes
        anim = self._anim
        anim_q = self._anim_quat
        nd = nodes[idx]
        p = nd.parent
        pp = self._pos[p]
        cdx, cdy, cdz = cur_dir_t
        cur = Vec3(cdx, cdy, cdz)
        try:
            ap = anim[p]
            ac = anim[idx]
            rdx = ac.x - ap.x
            rdy = ac.y - ap.y
            rdz = ac.z - ap.z
            rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
            if rl < 1e-9:
                return
            rest = Vec3(rdx / rl, rdy / rl, rdz / rl)
        except Exception:
            return
        try:
            hx = self.hinge_axis if isinstance(self.hinge_axis, Vec3) else Vec3(1, 0, 0)
            if hx.length_sq() < 1e-10:
                hx = Vec3(1, 0, 0)
            pq = anim_q[p] if p < len(anim_q) else Quat.identity()
            axis = pq.rotate_vec3(hx.normalized())
        except Exception:
            axis = Vec3(1, 0, 0)
        try:
            axis = axis.normalized()
        except Exception:
            return
        rp = rest.x * axis.x + rest.y * axis.y + rest.z * axis.z
        cp = cur.x * axis.x + cur.y * axis.y + cur.z * axis.z
        rpx = rest.x - axis.x * rp
        rpy = rest.y - axis.y * rp
        rpz = rest.z - axis.z * rp
        cpx = cur.x - axis.x * cp
        cpy = cur.y - axis.y * cp
        cpz = cur.z - axis.z * cp
        rpl = math.sqrt(rpx * rpx + rpy * rpy + rpz * rpz)
        cpl = math.sqrt(cpx * cpx + cpy * cpy + cpz * cpz)
        if rpl < 1e-8:
            try:
                up = Vec3(0, 1, 0) if abs(axis.y) < 0.9 else Vec3(1, 0, 0)
                tmp = Vec3(axis.y * up.z - axis.z * up.y, axis.z * up.x - axis.x * up.z, axis.x * up.y - axis.y * up.x).normalized()
                rpx, rpy, rpz = tmp.x, tmp.y, tmp.z
                rpl = 1.0
            except Exception:
                return
        if cpl < 1e-8:
            cpx, cpy, cpz = rpx / rpl, rpy / rpl, rpz / rpl
            cpl = 1.0
        rpx /= rpl
        rpy /= rpl
        rpz /= rpl
        cpx /= cpl
        cpy /= cpl
        cpz /= cpl
        dot = rpx * cpx + rpy * cpy + rpz * cpz
        if dot > 1.0:
            dot = 1.0
        if dot < -1.0:
            dot = -1.0
        ang = math.degrees(math.acos(dot))
        cx = rpy * cpz - rpz * cpy
        cy = rpz * cpx - rpx * cpz
        cz = rpx * cpy - rpy * cpx
        s = cx * axis.x + cy * axis.y + cz * axis.z
        signed = ang if s >= 0.0 else -ang
        lim = float(max_angle)
        cs = signed
        if cs > lim:
            cs = lim
        if cs < -lim:
            cs = -lim
        try:
            rot = Quat.from_axis_angle(axis, cs)
            npx = rot.rotate_vec3(Vec3(rpx, rpy, rpz))
            try:
                npx = npx.normalized()
            except Exception:
                pass
        except Exception:
            npx = Vec3(rpx, rpy, rpz)
        rplen = math.sqrt(max(0.0, 1.0 - rp * rp))
        ndir = Vec3(axis.x * rp + npx.x * rplen, axis.y * rp + npx.y * rplen, axis.z * rp + npx.z * rplen)
        try:
            ndir = ndir.normalized()
        except Exception:
            pass
        self._pos[idx] = Vec3(pp.x + ndir.x * cur_len, pp.y + ndir.y * cur_len, pp.z + ndir.z * cur_len)
    except Exception:
        pass
