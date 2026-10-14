# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
from core.maths.math3d import Vec3, Quat
_GRAB_K = 22.0
_SPRING_K = 45.0
_PULL_RATE = 8.0
_AIR_DAMP = 0.02
_VMAX = 25.0
_MU = 0.35
def _clamp(v, lo, hi):
    try:
        f = float(v)
    except Exception:
        f = float(lo)
    if f < lo:
        return lo
    if f > hi:
        return hi
    return f
def _clamp01(v):
    return _clamp(v, 0.0, 1.0)
def _sample_curve(curve, t):
    try:
        if not curve or len(curve) < 2:
            return 1.0
        tt = _clamp01(t)
        pts = sorted(curve, key=lambda p: float(p[0]))
        if tt <= float(pts[0][0]):
            return float(pts[0][1])
        if tt >= float(pts[-1][0]):
            return float(pts[-1][1])
        for i in range(len(pts) - 1):
            t0 = float(pts[i][0])
            t1 = float(pts[i + 1][0])
            if t0 <= tt <= t1:
                v0 = float(pts[i][1])
                v1 = float(pts[i + 1][1])
                denom = t1 - t0
                s = (tt - t0) / denom if abs(denom) > 1e-10 else 0.0
                return v0 + (v1 - v0) * s
        return float(pts[-1][1])
    except Exception:
        return 1.0
def _as_vec3(value, default):
    if isinstance(value, Vec3):
        return value
    try:
        return Vec3(float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        return default
def _as_curve(value):
    try:
        if not value:
            return [[0.0, 1.0], [1.0, 1.0]]
        out = []
        for p in value:
            out.append([float(p[0]), float(p[1])])
        if len(out) < 2:
            return [[0.0, 1.0], [1.0, 1.0]]
        return out
    except Exception:
        return [[0.0, 1.0], [1.0, 1.0]]
def _normalize_id(v):
    try:
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            for k in ("entity_id", "value", "id", "entity"):
                if k in v and isinstance(v[k], str):
                    return v[k]
            return ""
        return str(v)
    except Exception:
        return ""
def _normalize_id_list(v):
    try:
        if not v:
            return []
        if isinstance(v, str):
            return [v] if v else []
        out = []
        for item in v:
            nid = _normalize_id(item)
            if nid:
                out.append(nid)
        return out
    except Exception:
        return []
def _quat_from_two_vecs(a, b):
    try:
        ax, ay, az = float(a.x), float(a.y), float(a.z)
        bx, by, bz = float(b.x), float(b.y), float(b.z)
    except Exception:
        return Quat.identity()
    na = math.sqrt(ax * ax + ay * ay + az * az)
    nb = math.sqrt(bx * bx + by * by + bz * bz)
    if na < 1e-10 or nb < 1e-12:
        return Quat.identity()
    ux, uy, uz = ax / na, ay / na, az / na
    wx, wy, wz = bx / nb, by / nb, bz / nb
    c = ux * wx + uy * wy + uz * wz
    if c > 0.999999:
        return Quat.identity()
    if c < -0.999999:
        px, py, pz = -uy, ux, 0.0
        if px * px + py * py + pz * pz < 1e-8:
            px, py, pz = 0.0, -uz, uy
        n = math.sqrt(px * px + py * py + pz * pz)
        if n < 1e-10:
            return Quat(0.0, 0.0, 1.0, 0.0)
        return Quat(px / n, py / n, pz / n, 0.0)
    crx = uy * wz - uz * wy
    cry = uz * wx - ux * wz
    crz = ux * wy - uy * wx
    den = math.sqrt(2.0 * (1.0 + c))
    if den < 1e-10:
        return Quat.identity()
    return Quat(crx / den, cry / den, crz / den, den * 0.5).normalized()
def _world_quat_of(tr):
    try:
        m = tr.world_matrix._d
        trace = float(m[0, 0] + m[1, 1] + m[2, 2])
        if trace > 0.0:
            s = 0.5 / math.sqrt(trace + 1.0)
            q = ((float(m[2, 1] - m[1, 2]) * s), (float(m[0, 2] - m[2, 0]) * s), (float(m[1, 0] - m[0, 1]) * s), (0.25 / s))
        elif float(m[0, 0]) > float(m[1, 1]) and float(m[0, 0]) > float(m[2, 2]):
            s = 2.0 * math.sqrt(1.0 + float(m[0, 0]) - float(m[1, 1]) - float(m[2, 2]))
            q = (((float(m[2, 1]) - float(m[1, 2])) / s), ((float(m[0, 1]) + float(m[1, 0])) / s), ((float(m[0, 2]) + float(m[2, 0])) / s), (0.25 * s))
        elif float(m[1, 1]) > float(m[2, 2]):
            s = 2.0 * math.sqrt(1.0 + float(m[1, 1]) - float(m[0, 0]) - float(m[2, 2]))
            q = (((float(m[0, 1]) + float(m[1, 0])) / s), (0.25 * s), ((float(m[1, 2]) + float(m[2, 1])) / s), ((float(m[0, 2]) - float(m[2, 0])) / s))
        else:
            s = 2.0 * math.sqrt(1.0 + float(m[2, 2]) - float(m[0, 0]) - float(m[1, 1]))
            q = (((float(m[0, 2]) + float(m[2, 0])) / s), ((float(m[1, 2]) + float(m[2, 1])) / s), (0.25 * s), ((float(m[1, 0]) - float(m[0, 1])) / s))
        return Quat(-q[0], -q[1], -q[2], q[3]).normalized()
    except Exception:
        try:
            return tr.local_rotation.normalized()
        except Exception:
            return Quat.identity()
def _resolve_entity(scene, eid):
    try:
        if scene is None or not eid:
            return None
        return scene.get_entity(eid)
    except Exception:
        return None
