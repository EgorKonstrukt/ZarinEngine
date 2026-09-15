# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import numpy as np
cimport numpy as cnp
from libc.math cimport sqrt, acos, sin, cos, exp, fabs, atan2

cnp.import_array()

cdef double _PI = 3.141592653589793
cdef double _DEG = 57.29577951308232
cdef double _EPS = 1e-10
cdef double _GRAV = 9.81
cdef double _SPRING_K = 45.0
cdef double _PULL_RATE = 8.0
cdef double _AIR = 0.02
cdef double _VMAX = 25.0
cdef double _MU = 0.35


cdef inline double _len3(double x, double y, double z) noexcept nogil:
    return sqrt(x * x + y * y + z * z)


cdef inline void _norm3(double* x, double* y, double* z) noexcept nogil:
    cdef double n = sqrt(x[0] * x[0] + y[0] * y[0] + z[0] * z[0])
    cdef double inv
    if n > _EPS:
        inv = 1.0 / n
        x[0] *= inv
        y[0] *= inv
        z[0] *= inv


cdef inline void _quat_from_two(double ax, double ay, double az,
                                double bx, double by, double bz,
                                double* ox, double* oy, double* oz, double* ow) noexcept nogil:
    cdef double na = sqrt(ax * ax + ay * ay + az * az)
    cdef double nb = sqrt(bx * bx + by * by + bz * bz)
    cdef double ux, uy, uz, wx, wy, wz, c, cx, cy, cz, den, n
    if na < _EPS or nb < _EPS:
        ox[0] = 0.0
        oy[0] = 0.0
        oz[0] = 0.0
        ow[0] = 1.0
        return
    ux = ax / na
    uy = ay / na
    uz = az / na
    wx = bx / nb
    wy = by / nb
    wz = bz / nb
    c = ux * wx + uy * wy + uz * wz
    if c > 0.99999999:
        ox[0] = 0.0
        oy[0] = 0.0
        oz[0] = 0.0
        ow[0] = 1.0
        return
    if c < -0.99999999:
        ux = -uy
        uy = ax / na
        uz = 0.0
        n = sqrt(ux * ux + uy * uy)
        if n < 1e-8:
            ux = 0.0
            uy = -az / na
            uz = ay / na
            n = sqrt(ux * ux + uy * uy + uz * uz)
        if n < _EPS:
            ox[0] = 0.0
            oy[0] = 0.0
            oz[0] = 1.0
            ow[0] = 0.0
            return
        ox[0] = ux / n
        oy[0] = uy / n
        oz[0] = uz / n
        ow[0] = 0.0
        return
    cx = uy * wz - uz * wy
    cy = uz * wx - ux * wz
    cz = ux * wy - uy * wx
    den = sqrt(2.0 * (1.0 + c))
    if den < _EPS:
        ox[0] = 0.0
        oy[0] = 0.0
        oz[0] = 0.0
        ow[0] = 1.0
        return
    ox[0] = cx / den
    oy[0] = cy / den
    oz[0] = cz / den
    ow[0] = den * 0.5


cdef inline void _quat_from_axis(double ax, double ay, double az, double ang,
                                 double* ox, double* oy, double* oz, double* ow) noexcept nogil:
    cdef double n = sqrt(ax * ax + ay * ay + az * az)
    cdef double s
    if n < _EPS:
        ox[0] = 0.0
        oy[0] = 0.0
        oz[0] = 0.0
        ow[0] = 1.0
        return
    s = sin(ang * 0.5) / n
    ox[0] = ax * s
    oy[0] = ay * s
    oz[0] = az * s
    ow[0] = cos(ang * 0.5)


cdef inline void _quat_rot(double qx, double qy, double qz, double qw,
                           double vx, double vy, double vz,
                           double* ox, double* oy, double* oz) noexcept nogil:
    cdef double tx = 2.0 * (qy * vz - qz * vy)
    cdef double ty = 2.0 * (qz * vx - qx * vz)
    cdef double tz = 2.0 * (qx * vy - qy * vx)
    ox[0] = vx + qw * tx + (qy * tz - qz * ty)
    oy[0] = vy + qw * ty + (qz * tx - qx * tz)
    oz[0] = vz + qw * tz + (qx * ty - qy * tx)


cdef inline void _quat_conj(double x, double y, double z, double w,
                            double* ox, double* oy, double* oz, double* ow) noexcept nogil:
    ox[0] = -x
    oy[0] = -y
    oz[0] = -z
    ow[0] = w


def step_physbone(cnp.ndarray[cnp.float64_t, ndim=2] pos,
                  cnp.ndarray[cnp.float64_t, ndim=2] prev,
                  cnp.ndarray[cnp.float64_t, ndim=2] anim,
                  cnp.ndarray[cnp.float64_t, ndim=1] pull,
                  cnp.ndarray[cnp.float64_t, ndim=1] spring,
                  cnp.ndarray[cnp.float64_t, ndim=1] grav,
                  cnp.ndarray[cnp.float64_t, ndim=1] damp,
                  cnp.ndarray[cnp.float64_t, ndim=1] radius,
                  cnp.ndarray[cnp.float64_t, ndim=1] sm,
                  cnp.ndarray[cnp.float64_t, ndim=1] mx,
                  cnp.ndarray[cnp.float64_t, ndim=1] sq,
                  cnp.ndarray[cnp.float64_t, ndim=1] max_ang,
                  cnp.ndarray[cnp.float64_t, ndim=1] follow,
                  cnp.ndarray[cnp.int64_t, ndim=1] parent,
                  cnp.ndarray[cnp.float64_t, ndim=1] rest_len,
                  cnp.ndarray[cnp.int64_t, ndim=1] limit_type,
                  cnp.ndarray[cnp.float64_t, ndim=2] hinge_axis,
                  cnp.ndarray[cnp.float64_t, ndim=2] rest_dir,
                  cnp.ndarray[cnp.int64_t, ndim=1] col_type,
                  cnp.ndarray[cnp.float64_t, ndim=2] col_a,
                  cnp.ndarray[cnp.float64_t, ndim=2] col_b,
                  cnp.ndarray[cnp.float64_t, ndim=1] col_r,
                  cnp.ndarray[cnp.float64_t, ndim=2] col_n,
                  cnp.ndarray[cnp.int64_t, ndim=1] col_inside,
                  double dt, int substeps, int iters,
                  long long grab_index,
                  double grab_x, double grab_y, double grab_z, double grab_k):
    cdef double[:, ::1] P = pos
    cdef double[:, ::1] Q = prev
    cdef double[:, ::1] A = anim
    cdef double[::1] v_pull = pull
    cdef double[::1] v_spring = spring
    cdef double[::1] v_grav = grav
    cdef double[::1] v_damp = damp
    cdef double[::1] v_radius = radius
    cdef double[::1] v_sm = sm
    cdef double[::1] v_mx = mx
    cdef double[::1] v_sq = sq
    cdef double[::1] v_maxa = max_ang
    cdef double[::1] v_follow = follow
    cdef long long[::1] v_parent = parent
    cdef double[::1] v_rest = rest_len
    cdef long long[::1] v_lim = limit_type
    cdef double[:, ::1] v_hinge = hinge_axis
    cdef double[:, ::1] v_rdir = rest_dir
    cdef long long[::1] v_ctype = col_type
    cdef double[:, ::1] v_ca = col_a
    cdef double[:, ::1] v_cb = col_b
    cdef double[::1] v_cr = col_r
    cdef double[:, ::1] v_cn = col_n
    cdef long long[::1] v_cin = col_inside
    cdef Py_ssize_t n = P.shape[0]
    cdef Py_ssize_t m = v_ctype.shape[0]
    cdef double h = dt / substeps if substeps > 0 else dt
    cdef double h2 = h * h
    cdef Py_ssize_t s, it, i, k, p, gp
    cdef double keep, dd, kx, vx, vy, vz, ax, ay, az, nx, ny, nz, pf, gk
    cdef double dx, dy, dz, cur, lo, hi, cl, target, sc, rl
    cdef double cdx, cdy, cdz, clen, dot, ang, ma, excess
    cdef double qx, qy, qz, qw, bx, by, bz, bw, rx, ry, rz, rw
    cdef double ex, ey, ez, fx, fy, fz, calx, caly, calz
    cdef double pdx, pdy, pdz, plen, alx, aly, alz, alw
    cdef double aax, aay, aaz, rp, rpx, rpy, rpz, rpl, cpx, cpy, cpz, cpl
    cdef double cx, cy, cz, sg, signed, cs, rplen, ndx, ndy, ndz, nl
    cdef double ox, oy, oz, px, py, pz, qx2, qy2, qz2, L, rr, lim, t
    cdef double abx, aby, abz, apx, apy, apz, denom
    cdef double ddn, push, vvx, vvy, vvz, vn, mu
    cdef double pr
    cdef double corr, ux, uy, uz, wi, wp, ws, si, sp
    with nogil:
        for s in range(substeps):
            P[0, 0] = A[0, 0]
            P[0, 1] = A[0, 1]
            P[0, 2] = A[0, 2]
            Q[0, 0] = A[0, 0]
            Q[0, 1] = A[0, 1]
            Q[0, 2] = A[0, 2]
            for i in range(1, n):
                dd = _AIR + v_damp[i]
                if dd < 0.0:
                    dd = 0.0
                if dd > 0.8:
                    dd = 0.8
                keep = 1.0 - dd
                vx = (P[i, 0] - Q[i, 0]) * keep
                vy = (P[i, 1] - Q[i, 1]) * keep
                vz = (P[i, 2] - Q[i, 2]) * keep
                cur = sqrt(vx * vx + vy * vy + vz * vz)
                rl = _VMAX * h
                if cur > rl and cur > _EPS:
                    sc = rl / cur
                    vx *= sc
                    vy *= sc
                    vz *= sc
                kx = v_spring[i] * _SPRING_K
                ax = (A[i, 0] - P[i, 0]) * kx
                ay = (A[i, 1] - P[i, 1]) * kx - v_grav[i] * _GRAV
                az = (A[i, 2] - P[i, 2]) * kx
                ox = P[i, 0]
                oy = P[i, 1]
                oz = P[i, 2]
                nx = ox + vx + ax * h2
                ny = oy + vy + ay * h2
                nz = oz + vz + az * h2
                pf = 1.0 - exp(-v_pull[i] * _PULL_RATE * h)
                if pf > 1e-9:
                    nx += (A[i, 0] - nx) * pf
                    ny += (A[i, 1] - ny) * pf
                    nz += (A[i, 2] - nz) * pf
                Q[i, 0] = ox
                Q[i, 1] = oy
                Q[i, 2] = oz
                P[i, 0] = nx
                P[i, 1] = ny
                P[i, 2] = nz
            if grab_index > 0 and grab_index < n and grab_k > 0.0:
                gk = 1.0 - exp(-grab_k * h)
                P[grab_index, 0] += (grab_x - P[grab_index, 0]) * gk
                P[grab_index, 1] += (grab_y - P[grab_index, 1]) * gk
                P[grab_index, 2] += (grab_z - P[grab_index, 2]) * gk
            for it in range(iters):
                for i in range(1, n):
                    p = v_parent[i]
                    if p < 0:
                        continue
                    rl = v_rest[i]
                    if rl < 1e-9:
                        continue
                    dx = P[i, 0] - P[p, 0]
                    dy = P[i, 1] - P[p, 1]
                    dz = P[i, 2] - P[p, 2]
                    cur = sqrt(dx * dx + dy * dy + dz * dz)
                    if cur < 1e-9:
                        P[i, 0] = P[p, 0] + v_rdir[i, 0] * rl
                        P[i, 1] = P[p, 1] + v_rdir[i, 1] * rl
                        P[i, 2] = P[p, 2] + v_rdir[i, 2] * rl
                        continue
                    lo = rl * (1.0 - v_sq[i])
                    if lo < 0.0:
                        lo = 0.0
                    hi = rl * (1.0 + v_mx[i])
                    cl = cur
                    if cl < lo:
                        cl = lo
                    if cl > hi:
                        cl = hi
                    target = rl + (cl - rl) * v_sm[i]
                    corr = target - cur
                    if fabs(corr) < 1e-12:
                        continue
                    ux = dx / cur
                    uy = dy / cur
                    uz = dz / cur
                    wi = 0.0
                    wp = 0.0
                    if i != grab_index:
                        wi = 1.0
                    if p != 0 and p != grab_index:
                        wp = 1.0
                    ws = wi + wp
                    if ws < _EPS:
                        continue
                    si = corr * (wi / ws)
                    sp = corr * (wp / ws)
                    P[i, 0] += ux * si
                    P[i, 1] += uy * si
                    P[i, 2] += uz * si
                    P[p, 0] -= ux * sp
                    P[p, 1] -= uy * sp
                    P[p, 2] -= uz * sp
                for i in range(1, n):
                    if v_lim[i] == 0:
                        continue
                    p = v_parent[i]
                    if p < 0:
                        continue
                    ma = v_maxa[i] / _DEG
                    if ma >= _PI - 0.002:
                        continue
                    dx = P[i, 0] - P[p, 0]
                    dy = P[i, 1] - P[p, 1]
                    dz = P[i, 2] - P[p, 2]
                    clen = sqrt(dx * dx + dy * dy + dz * dz)
                    if clen < 1e-9:
                        continue
                    cdx = dx / clen
                    cdy = dy / clen
                    cdz = dz / clen
                    if ma <= 1e-9:
                        P[i, 0] = P[p, 0] + v_rdir[i, 0] * clen
                        P[i, 1] = P[p, 1] + v_rdir[i, 1] * clen
                        P[i, 2] = P[p, 2] + v_rdir[i, 2] * clen
                        continue
                    if v_lim[i] == 2:
                        aax = v_hinge[i, 0]
                        aay = v_hinge[i, 1]
                        aaz = v_hinge[i, 2]
                        cur = sqrt(aax * aax + aay * aay + aaz * aaz)
                        if cur < 1e-8:
                            aax = 1.0
                            aay = 0.0
                            aaz = 0.0
                            cur = 1.0
                        aax /= cur
                        aay /= cur
                        aaz /= cur
                        ex = v_rdir[i, 0]
                        ey = v_rdir[i, 1]
                        ez = v_rdir[i, 2]
                        rp = ex * aax + ey * aay + ez * aaz
                        rpx = ex - aax * rp
                        rpy = ey - aay * rp
                        rpz = ez - aaz * rp
                        rpl = sqrt(rpx * rpx + rpy * rpy + rpz * rpz)
                        if rpl < 1e-8:
                            if fabs(aay) < 0.9:
                                rpx = -aay
                                rpy = aax
                                rpz = 0.0
                            else:
                                rpx = 0.0
                                rpy = -aaz
                                rpz = aay
                            rpl = sqrt(rpx * rpx + rpy * rpy + rpz * rpz)
                            if rpl < _EPS:
                                continue
                        rpx /= rpl
                        rpy /= rpl
                        rpz /= rpl
                        cpx = cdx - aax * (cdx * aax + cdy * aay + cdz * aaz)
                        cpy = cdy - aay * (cdx * aax + cdy * aay + cdz * aaz)
                        cpz = cdz - aaz * (cdx * aax + cdy * aay + cdz * aaz)
                        cpl = sqrt(cpx * cpx + cpy * cpy + cpz * cpz)
                        if cpl < 1e-8:
                            cpx = rpx
                            cpy = rpy
                            cpz = rpz
                            cpl = 1.0
                        cpx /= cpl
                        cpy /= cpl
                        cpz /= cpl
                        dot = rpx * cpx + rpy * cpy + rpz * cpz
                        if dot > 1.0:
                            dot = 1.0
                        if dot < -1.0:
                            dot = -1.0
                        ang = acos(dot)
                        cx = rpy * cpz - rpz * cpy
                        cy = rpz * cpx - rpx * cpz
                        cz = rpx * cpy - rpy * cpx
                        sg = cx * aax + cy * aay + cz * aaz
                        signed = ang if sg >= 0.0 else -ang
                        cs = signed
                        if cs > ma:
                            cs = ma
                        if cs < -ma:
                            cs = -ma
                        _quat_from_axis(aax, aay, aaz, cs, &qx, &qy, &qz, &qw)
                        _quat_rot(qx, qy, qz, qw, rpx, rpy, rpz, &ex, &ey, &ez)
                        rplen = sqrt(0.0 if (1.0 - rp * rp) < 0.0 else (1.0 - rp * rp))
                        ndx = aax * rp + ex * rplen
                        ndy = aay * rp + ey * rplen
                        ndz = aaz * rp + ez * rplen
                        nl = sqrt(ndx * ndx + ndy * ndy + ndz * ndz)
                        if nl < _EPS:
                            continue
                        P[i, 0] = P[p, 0] + ndx / nl * clen
                        P[i, 1] = P[p, 1] + ndy / nl * clen
                        P[i, 2] = P[p, 2] + ndz / nl * clen
                        continue
                    gp = v_parent[p]
                    if gp < 0:
                        ex = v_rdir[i, 0]
                        ey = v_rdir[i, 1]
                        ez = v_rdir[i, 2]
                        dot = cdx * ex + cdy * ey + cdz * ez
                        if dot > 1.0:
                            dot = 1.0
                        if dot < -1.0:
                            dot = -1.0
                        ang = acos(dot)
                        if ang <= ma + 1e-9:
                            continue
                        excess = ang - ma
                        aax = cdy * ez - cdz * ey
                        aay = cdz * ex - cdx * ez
                        aaz = cdx * ey - cdy * ex
                        cur = sqrt(aax * aax + aay * aay + aaz * aaz)
                        if cur < 1e-12:
                            continue
                        _quat_from_axis(aax / cur, aay / cur, aaz / cur, excess, &qx, &qy, &qz, &qw)
                        _quat_rot(qx, qy, qz, qw, cdx, cdy, cdz, &ex, &ey, &ez)
                        P[i, 0] = P[p, 0] + ex * clen
                        P[i, 1] = P[p, 1] + ey * clen
                        P[i, 2] = P[p, 2] + ez * clen
                    else:
                        pdx = P[p, 0] - P[gp, 0]
                        pdy = P[p, 1] - P[gp, 1]
                        pdz = P[p, 2] - P[gp, 2]
                        plen = sqrt(pdx * pdx + pdy * pdy + pdz * pdz)
                        if plen < 1e-9:
                            continue
                        pdx /= plen
                        pdy /= plen
                        pdz /= plen
                        _quat_from_two(pdx, pdy, pdz, v_rdir[p, 0], v_rdir[p, 1], v_rdir[p, 2], &alx, &aly, &alz, &alw)
                        _quat_rot(alx, aly, alz, alw, cdx, cdy, cdz, &calx, &caly, &calz)
                        cur = sqrt(calx * calx + caly * caly + calz * calz)
                        if cur < _EPS:
                            continue
                        calx /= cur
                        caly /= cur
                        calz /= cur
                        ex = v_rdir[i, 0]
                        ey = v_rdir[i, 1]
                        ez = v_rdir[i, 2]
                        dot = calx * ex + caly * ey + calz * ez
                        if dot > 1.0:
                            dot = 1.0
                        if dot < -1.0:
                            dot = -1.0
                        ang = acos(dot)
                        if ang <= ma + 1e-9:
                            continue
                        excess = ang - ma
                        aax = caly * ez - calz * ey
                        aay = calz * ex - calx * ez
                        aaz = calx * ey - caly * ex
                        cur = sqrt(aax * aax + aay * aay + aaz * aaz)
                        if cur < 1e-12:
                            continue
                        _quat_from_axis(aax / cur, aay / cur, aaz / cur, excess, &qx, &qy, &qz, &qw)
                        _quat_rot(qx, qy, qz, qw, calx, caly, calz, &fx, &fy, &fz)
                        _quat_conj(alx, aly, alz, alw, &bx, &by, &bz, &bw)
                        _quat_rot(bx, by, bz, bw, fx, fy, fz, &ex, &ey, &ez)
                        P[i, 0] = P[p, 0] + ex * clen
                        P[i, 1] = P[p, 1] + ey * clen
                        P[i, 2] = P[p, 2] + ez * clen
                if m > 0:
                    for i in range(1, n):
                        pr = v_radius[i]
                        if pr <= 1e-12:
                            continue
                        for k in range(m):
                            if v_ctype[k] == 2:
                                ox = P[i, 0] - v_ca[k, 0]
                                oy = P[i, 1] - v_ca[k, 1]
                                oz = P[i, 2] - v_ca[k, 2]
                                ddn = ox * v_cn[k, 0] + oy * v_cn[k, 1] + oz * v_cn[k, 2]
                                if v_cin[k] != 0:
                                    if ddn > -pr:
                                        push = ddn + pr
                                        P[i, 0] -= v_cn[k, 0] * push
                                        P[i, 1] -= v_cn[k, 1] * push
                                        P[i, 2] -= v_cn[k, 2] * push
                                        vvx = P[i, 0] - Q[i, 0]
                                        vvy = P[i, 1] - Q[i, 1]
                                        vvz = P[i, 2] - Q[i, 2]
                                        vn = vvx * v_cn[k, 0] + vvy * v_cn[k, 1] + vvz * v_cn[k, 2]
                                        if vn > 0.0:
                                            vvx -= v_cn[k, 0] * vn
                                            vvy -= v_cn[k, 1] * vn
                                            vvz -= v_cn[k, 2] * vn
                                        vvx *= (1.0 - _MU)
                                        vvy *= (1.0 - _MU)
                                        vvz *= (1.0 - _MU)
                                        Q[i, 0] = P[i, 0] - vvx
                                        Q[i, 1] = P[i, 1] - vvy
                                        Q[i, 2] = P[i, 2] - vvz
                                    continue
                                if ddn >= 0.0:
                                    if ddn < pr:
                                        push = pr - ddn
                                        P[i, 0] += v_cn[k, 0] * push
                                        P[i, 1] += v_cn[k, 1] * push
                                        P[i, 2] += v_cn[k, 2] * push
                                        vvx = P[i, 0] - Q[i, 0]
                                        vvy = P[i, 1] - Q[i, 1]
                                        vvz = P[i, 2] - Q[i, 2]
                                        vn = vvx * v_cn[k, 0] + vvy * v_cn[k, 1] + vvz * v_cn[k, 2]
                                        if vn < 0.0:
                                            vvx -= v_cn[k, 0] * vn
                                            vvy -= v_cn[k, 1] * vn
                                            vvz -= v_cn[k, 2] * vn
                                        vvx *= (1.0 - _MU)
                                        vvy *= (1.0 - _MU)
                                        vvz *= (1.0 - _MU)
                                        Q[i, 0] = P[i, 0] - vvx
                                        Q[i, 1] = P[i, 1] - vvy
                                        Q[i, 2] = P[i, 2] - vvz
                                    continue
                                if -ddn < pr:
                                    push = pr + ddn
                                    P[i, 0] -= v_cn[k, 0] * push
                                    P[i, 1] -= v_cn[k, 1] * push
                                    P[i, 2] -= v_cn[k, 2] * push
                                    vvx = P[i, 0] - Q[i, 0]
                                    vvy = P[i, 1] - Q[i, 1]
                                    vvz = P[i, 2] - Q[i, 2]
                                    vn = vvx * v_cn[k, 0] + vvy * v_cn[k, 1] + vvz * v_cn[k, 2]
                                    if vn > 0.0:
                                        vvx -= v_cn[k, 0] * vn
                                        vvy -= v_cn[k, 1] * vn
                                        vvz -= v_cn[k, 2] * vn
                                    vvx *= (1.0 - _MU)
                                    vvy *= (1.0 - _MU)
                                    vvz *= (1.0 - _MU)
                                    Q[i, 0] = P[i, 0] - vvx
                                    Q[i, 1] = P[i, 1] - vvy
                                    Q[i, 2] = P[i, 2] - vvz
                                continue
                            if v_ctype[k] == 1:
                                abx = v_cb[k, 0] - v_ca[k, 0]
                                aby = v_cb[k, 1] - v_ca[k, 1]
                                abz = v_cb[k, 2] - v_ca[k, 2]
                                apx = P[i, 0] - v_ca[k, 0]
                                apy = P[i, 1] - v_ca[k, 1]
                                apz = P[i, 2] - v_ca[k, 2]
                                denom = abx * abx + aby * aby + abz * abz
                                if denom < 1e-18:
                                    px = v_ca[k, 0]
                                    py = v_ca[k, 1]
                                    pz = v_ca[k, 2]
                                else:
                                    t = (apx * abx + apy * aby + apz * abz) / denom
                                    if t < 0.0:
                                        t = 0.0
                                    if t > 1.0:
                                        t = 1.0
                                    px = v_ca[k, 0] + abx * t
                                    py = v_ca[k, 1] + aby * t
                                    pz = v_ca[k, 2] + abz * t
                            else:
                                px = v_ca[k, 0]
                                py = v_ca[k, 1]
                                pz = v_ca[k, 2]
                            ox = P[i, 0] - px
                            oy = P[i, 1] - py
                            oz = P[i, 2] - pz
                            L = sqrt(ox * ox + oy * oy + oz * oz)
                            rr = v_cr[k] + pr
                            if v_cin[k] != 0:
                                lim = v_cr[k] - pr
                                if lim <= 1e-9:
                                    P[i, 0] = px
                                    P[i, 1] = py
                                    P[i, 2] = pz
                                    Q[i, 0] = px
                                    Q[i, 1] = py
                                    Q[i, 2] = pz
                                    continue
                                if L > lim:
                                    if L < 1e-9:
                                        ox = lim
                                        oy = 0.0
                                        oz = 0.0
                                        L = lim
                                    else:
                                        sc = lim / L
                                        ox *= sc
                                        oy *= sc
                                        oz *= sc
                                    P[i, 0] = px + ox
                                    P[i, 1] = py + oy
                                    P[i, 2] = pz + oz
                                continue
                            if L >= rr:
                                continue
                            if L < 1e-9:
                                ox = rr
                                oy = 0.0
                                oz = 0.0
                                L = rr
                            else:
                                sc = rr / L
                                ox *= sc
                                oy *= sc
                                oz *= sc
                            P[i, 0] = px + ox
                            P[i, 1] = py + oy
                            P[i, 2] = pz + oz
                            L = sqrt(ox * ox + oy * oy + oz * oz)
                            if L < _EPS:
                                continue
                            ox /= L
                            oy /= L
                            oz /= L
                            vvx = P[i, 0] - Q[i, 0]
                            vvy = P[i, 1] - Q[i, 1]
                            vvz = P[i, 2] - Q[i, 2]
                            vn = vvx * ox + vvy * oy + vvz * oz
                            if vn < 0.0:
                                vvx -= ox * vn
                                vvy -= oy * vn
                                vvz -= oz * vn
                            vvx *= (1.0 - _MU)
                            vvy *= (1.0 - _MU)
                            vvz *= (1.0 - _MU)
                            Q[i, 0] = P[i, 0] - vvx
                            Q[i, 1] = P[i, 1] - vvy
                            Q[i, 2] = P[i, 2] - vvz
        for i in range(n):
            if v_follow[i] > 1e-9:
                P[i, 0] += (A[i, 0] - P[i, 0]) * v_follow[i]
                P[i, 1] += (A[i, 1] - P[i, 1]) * v_follow[i]
                P[i, 2] += (A[i, 2] - P[i, 2]) * v_follow[i]
