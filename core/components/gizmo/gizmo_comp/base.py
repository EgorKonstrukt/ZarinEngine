# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
from core.ecs import InstancePrimitive, _get_engine
from core.maths.math3d import Vec3, Vec4
from core.gizmo.apiv import GizmoData, LineStyle, _GIZMO_LINE_BUILDERS, _apply_line_style


def _vec3_to_tuple(v):
    if isinstance(v, Vec3):
        return (v.x, v.y, v.z)
    if isinstance(v, (list, tuple, np.ndarray)):
        return (float(v[0]), float(v[1]), float(v[2]))
    return (0.0, 0.0, 0.0)


def _color_to_tuple(c):
    if isinstance(c, Vec4):
        return (c.x, c.y, c.z, c.w)
    if isinstance(c, (list, tuple, np.ndarray)):
        if len(c) == 3:
            return (float(c[0]), float(c[1]), float(c[2]), 1.0)
        if len(c) >= 4:
            return (float(c[0]), float(c[1]), float(c[2]), float(c[3]))
    return (1.0, 1.0, 1.0, 1.0)


def _sig_points(points):
    out = []
    for p in points:
        if isinstance(p, Vec3):
            out.append((p.x, p.y, p.z))
        else:
            out.append(tuple(float(v) for v in p))
    return tuple(out)


def _v3(v):
    if isinstance(v, Vec3):
        return v
    return Vec3(*_vec3_to_tuple(v))


def _v4(v):
    if isinstance(v, Vec4):
        return v
    t = _color_to_tuple(v)
    return Vec4(*t)


def _v3t(v):
    return _vec3_to_tuple(v)


def _v4t(v):
    return _color_to_tuple(v)


def _is_play_mode():
    try:
        return bool(getattr(_get_engine(), "play_mode", False))
    except Exception:
        return False


def _gizmo_visible(comp):
    try:
        if not bool(getattr(comp, "show_in_play", True)) and _is_play_mode():
            return False
    except Exception:
        pass
    return True


def _wm(tr):
    try:
        if tr is None:
            return np.eye(4, dtype=np.float32)
        d = tr.world_matrix._d
        return np.asarray(d, dtype=np.float32)
    except Exception:
        return np.eye(4, dtype=np.float32)


def _apply_world(starts, ends, colors, tr=None):
    wm = _wm(tr)
    r = wm[:3, :3]
    t = wm[3, :3]
    return (starts @ r + t, ends @ r + t, colors)


def _box_instance(center, size, tr=None):
    c = np.array(_vec3_to_tuple(center), dtype=np.float32)
    h = np.array(_vec3_to_tuple(size), dtype=np.float32) * 0.5
    wm = _wm(tr)
    rs = wm[:3, :3]
    combined = np.eye(4, dtype=np.float32)
    combined[:3, :3] = rs * h
    combined[:3, 3] = rs @ c + wm[3, :3]
    return combined


def _sphere_instance(center, radius, tr=None):
    c = np.array(_vec3_to_tuple(center), dtype=np.float32)
    wm = _wm(tr)
    rs = wm[:3, :3]
    r = float(radius)
    m = max(np.linalg.norm(rs[:, i]) for i in range(3))
    if m > 0.0:
        r *= m
    combined = np.eye(4, dtype=np.float32)
    combined[0, 0] = combined[1, 1] = combined[2, 2] = r
    combined[:3, 3] = rs @ c + wm[3, :3]
    return combined


def _sphere_at(pos, radius, color):
    p = np.array(_vec3_to_tuple(pos), dtype=np.float32)
    r = float(radius)
    m = np.eye(4, dtype=np.float32)
    m[0, 0] = m[1, 1] = m[2, 2] = r
    m[:3, 3] = p
    return InstancePrimitive('sphere', m.ravel('F'), list(_v4t(color)))


def _dash_animated(starts, ends, colors, dash_len, gap_len, phase):
    step = dash_len + gap_len
    if step <= 0.0:
        return (starts, ends, colors)
    n0 = starts.shape[0]
    if n0 == 0:
        return (starts, ends, colors)
    dirs = ends - starts
    lens = np.sqrt((dirs * dirs).sum(axis=1))
    ph = phase % step
    out_s = []
    out_e = []
    out_c = []
    for i in range(n0):
        ln = lens[i]
        if ln <= 1e-6:
            continue
        dx = dirs[i]
        col = colors[i]
        kmax = int((ln + step - ph) / step) + 1
        for k in range(-1, kmax):
            t0 = k * step + ph
            t1 = t0 + dash_len
            if t1 <= 0.0 or t0 >= ln:
                continue
            c0 = max(t0, 0.0)
            c1 = min(t1, ln)
            if c1 - c0 < 1e-6:
                continue
            out_s.append(starts[i] + dx * (c0 / ln))
            out_e.append(starts[i] + dx * (c1 / ln))
            out_c.append(col)
    if not out_s:
        return (np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.float32), np.empty((0, 4), dtype=np.float32))
    return (np.stack(out_s), np.stack(out_e), np.stack(out_c))


def _build_primitive(gtype, pos, color, **kwargs):
    data = GizmoData(gizmo_type=gtype, position=_vec3_to_tuple(pos), color=_color_to_tuple(color), **kwargs)
    builder = _GIZMO_LINE_BUILDERS.get(gtype)
    if builder is None:
        return None
    result = builder(data)
    if result is None:
        return None
    starts, ends, colors = result
    style = kwargs.get("line_style", LineStyle.SOLID)
    if isinstance(style, str):
        try:
            style = LineStyle(style)
        except Exception:
            style = LineStyle.SOLID
    if style != LineStyle.SOLID:
        starts, ends, colors = _apply_line_style(starts, ends, colors, style, kwargs.get("dash_length", 0.3), kwargs.get("gap_length", 0.15))
        if starts.shape[0] == 0:
            return None
    return (starts, ends, colors)
