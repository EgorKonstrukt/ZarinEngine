# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import math
from core.maths.math3d import Vec3
from .mathx import _clamp, _clamp01, _sample_curve, _GRAB_K, _SPRING_K, _PULL_RATE, _AIR_DAMP, _VMAX, _MU
class DynamicsMixin:
    def _integrate(self, dt):
        try:
            nodes = self._nodes
            anim = self._anim
            if not nodes or not anim or len(anim) != len(nodes):
                return
            if len(self._pos) != len(nodes):
                self._pos = [Vec3(p.x, p.y, p.z) for p in anim]
            if len(self._prev) != len(nodes):
                self._prev = [Vec3(p.x, p.y, p.z) for p in anim]
            dt2 = dt * dt
            for i in range(len(nodes)):
                if i == 0:
                    try:
                        a = anim[0]
                        self._pos[0] = Vec3(a.x, a.y, a.z)
                        self._prev[0] = Vec3(a.x, a.y, a.z)
                    except Exception:
                        pass
                    continue
                try:
                    nd = nodes[i]
                    t = nd.t
                    pull_i = self._pb_value(self.pull, self.pull_curve, t, 0.0, 1.0)
                    spring_i = self._pb_value(self.spring, self.spring_curve, t, 0.0, 1.0)
                    grav_i = _clamp(float(self.gravity) * float(_sample_curve(self.gravity_curve, t)), -1.0, 1.0)
                    try:
                        fall = self._pb_value(self.gravity_falloff, self.gravity_falloff_curve, t, 0.0, 1.0)
                    except Exception:
                        fall = 0.0
                    grav_i = grav_i * (1.0 - float(fall) * float(t))
                    p = self._pos[i]
                    pr = self._prev[i]
                    a = anim[i]
                    damp_i = self._pb_value(self.damping, self.damping_curve, t, 0.0, 1.0)
                    dd = _AIR_DAMP + float(damp_i)
                    if dd < 0.0:
                        dd = 0.0
                    if dd > 0.8:
                        dd = 0.8
                    keep = 1.0 - float(dd)
                    vx = (p.x - pr.x) * keep
                    vy = (p.y - pr.y) * keep
                    vz = (p.z - pr.z) * keep
                    try:
                        vl = math.sqrt(vx * vx + vy * vy + vz * vz)
                        vmax = _VMAX * float(dt)
                        if vl > vmax and vl > 1e-12:
                            sc = vmax / vl
                            vx *= sc
                            vy *= sc
                            vz *= sc
                    except Exception:
                        pass
                    ax = (a.x - p.x) * float(spring_i) * _SPRING_K
                    ay = (a.y - p.y) * float(spring_i) * _SPRING_K - float(grav_i) * 9.81
                    az = (a.z - p.z) * float(spring_i) * _SPRING_K
                    nx = p.x + vx + ax * dt2
                    ny = p.y + vy + ay * dt2
                    nz = p.z + vz + az * dt2
                    try:
                        pf = 1.0 - math.exp(-float(pull_i) * _PULL_RATE * float(dt))
                    except Exception:
                        pf = float(pull_i)
                    if pf < 0.0:
                        pf = 0.0
                    if pf > 1.0:
                        pf = 1.0
                    if pf > 1e-6:
                        nx = nx + (a.x - nx) * pf
                        ny = ny + (a.y - ny) * pf
                        nz = nz + (a.z - nz) * pf
                    try:
                        if self._grab_target is not None and self._grab_index == i and self.allow_grab:
                            gk = 1.0 - math.exp(-_GRAB_K * float(dt))
                            nx += (self._grab_target.x - nx) * gk
                            ny += (self._grab_target.y - ny) * gk
                            nz += (self._grab_target.z - nz) * gk
                    except Exception:
                        pass
                    self._prev[i] = Vec3(p.x, p.y, p.z)
                    self._pos[i] = Vec3(nx, ny, nz)
                except Exception:
                    continue
        except Exception:
            pass
    def _solve_lengths(self):
        try:
            nodes = self._nodes
            for i in range(1, len(nodes)):
                try:
                    nd = nodes[i]
                    p = nd.parent
                    if p < 0:
                        continue
                    rest = float(nd.rest_length)
                    if rest < 1e-9:
                        continue
                    t = nd.t
                    sm = self._pb_value(self.stretch_motion, self.stretch_motion_curve, t, 0.0, 1.0)
                    mx = self._pb_value(self.max_stretch, self.max_stretch_curve, t, 0.0, 2.0)
                    sq = self._pb_value(self.max_squish, self.max_squish_curve, t, 0.0, 1.0)
                    pp = self._pos[p]
                    cp = self._pos[i]
                    dx = cp.x - pp.x
                    dy = cp.y - pp.y
                    dz = cp.z - pp.z
                    cur = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if cur < 1e-9:
                        try:
                            a = self._anim[i]
                            b = self._anim[p]
                            ddx = a.x - b.x
                            ddy = a.y - b.y
                            ddz = a.z - b.z
                            l = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz)
                            if l < 1e-9:
                                ddx, ddy, ddz = 0.0, -1.0, 0.0
                                l = 1.0
                            inv = rest / l
                            self._pos[i] = Vec3(pp.x + ddx * inv, pp.y + ddy * inv, pp.z + ddz * inv)
                        except Exception:
                            pass
                        continue
                    lo = rest * (1.0 - float(sq))
                    hi = rest * (1.0 + float(mx))
                    if lo < 0.0:
                        lo = 0.0
                    clamped = cur
                    if clamped < lo:
                        clamped = lo
                    if clamped > hi:
                        clamped = hi
                    target = rest + (clamped - rest) * float(sm)
                    corr = target - cur
                    if abs(corr) < 1e-12:
                        continue
                    ux = dx / cur
                    uy = dy / cur
                    uz = dz / cur
                    try:
                        gi = int(self._grab_index)
                    except Exception:
                        gi = -1
                    wi = 0.0
                    wp = 0.0
                    if i != gi:
                        wi = 1.0
                    if p != 0 and p != gi:
                        wp = 1.0
                    ws = wi + wp
                    if ws < 1e-10:
                        continue
                    si = corr * (wi / ws)
                    sp = corr * (wp / ws)
                    self._pos[i] = Vec3(cp.x + ux * si, cp.y + uy * si, cp.z + uz * si)
                    pp = self._pos[p]
                    self._pos[p] = Vec3(pp.x - ux * sp, pp.y - uy * sp, pp.z - uz * sp)
                except Exception:
                    continue
        except Exception:
            pass
    def _solve_limits(self):
        from ._dyn_limits import _solve_limits_impl as _impl
        return _impl(self)
    def _solve_hinge(self, idx, max_angle, cur_dir_t, cur_len):
        from ._dyn_limits import _solve_hinge_impl as _impl
        return _impl(self, idx, max_angle, cur_dir_t, cur_len)
    def _solve_collisions(self, colliders):
        try:
            nodes = self._nodes
            for i in range(1, len(nodes)):
                try:
                    t = nodes[i].t
                    pr = self._pb_value(self.radius, self.radius_curve, t, 0.0, 2.0)
                    if pr <= 1e-9:
                        continue
                    p = self._pos[i]
                    for col in colliders:
                        try:
                            p = col.collide(p, float(pr))
                        except Exception:
                            continue
                    try:
                        old = self._pos[i]
                        dx = p.x - old.x
                        dy = p.y - old.y
                        dz = p.z - old.z
                        if dx * dx + dy * dy + dz * dz > 1e-18:
                            pv = self._prev[i]
                            vx = (p.x - pv.x) * (1.0 - _MU)
                            vy = (p.y - pv.y) * (1.0 - _MU)
                            vz = (p.z - pv.z) * (1.0 - _MU)
                            self._prev[i] = Vec3(p.x - vx, p.y - vy, p.z - vz)
                    except Exception:
                        pass
                    self._pos[i] = p
                except Exception:
                    continue
        except Exception:
            pass
    def _blend_final(self, weight):
        try:
            nodes = self._nodes
            anim = self._anim
            out = []
            w = _clamp01(weight)
            for i in range(len(nodes)):
                try:
                    t = nodes[i].t
                    im = self._pb_value(self.immobile, self.immobile_curve, t, 0.0, 1.0)
                    follow = 1.0 - (1.0 - float(im)) * float(w)
                    if follow < 0.0:
                        follow = 0.0
                    if follow > 1.0:
                        follow = 1.0
                    s = self._pos[i]
                    a = anim[i]
                    out.append(Vec3(s.x + (a.x - s.x) * follow, s.y + (a.y - s.y) * follow, s.z + (a.z - s.z) * follow))
                except Exception:
                    try:
                        out.append(Vec3(anim[i].x, anim[i].y, anim[i].z))
                    except Exception:
                        pass
            return out
        except Exception:
            return self._pos
    def _apply_to_transforms(self, final, anim_quat, weight):
        from ._dyn_apply import _apply_to_transforms_impl as _impl
        return _impl(self, final, anim_quat, weight)
    def on_update(self, dt: float):
        from ._dyn_apply import _on_update_impl as _impl
        return _impl(self, dt)
    def preview_step(self, dt):
        try:
            self.on_update(float(dt))
        except Exception:
            pass
