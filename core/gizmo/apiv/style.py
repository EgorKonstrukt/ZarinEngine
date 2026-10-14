# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from typing import Optional, List, Tuple, Dict, Callable, Any
from core.maths.math3d import Vec3
from core.gizmo.apiv.types import GizmoType, LineStyle
from core.gizmo.apiv.data import GizmoData


class _GizmoStyleCtx:
    def __init__(self, mgr, kwargs: dict):
        self._mgr = mgr
        self._kwargs = kwargs
    def __enter__(self):
        self._mgr.push_style(**self._kwargs)
        return self
    def __exit__(self, *args):
        self._mgr.pop_style()


def _np_color(c: Tuple[float, float, float, float], n: int) -> np.ndarray:
    arr = np.empty((n, 4), dtype=np.float32)
    arr[:] = c
    return arr


def _quat_to_mat3(rot: Tuple[float, float, float, float]) -> np.ndarray:
    x, y, z, w = rot
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return np.array([
        [1-2*(yy+zz), 2*(xy-wz), 2*(xz+wy)],
        [2*(xy+wz), 1-2*(xx+zz), 2*(yz-wx)],
        [2*(xz-wy), 2*(yz+wx), 1-2*(xx+yy)],
    ], dtype=np.float32)


def _euler_to_mat3(rot: Tuple[float, float, float]) -> np.ndarray:
    cx, cy, cz = (math.cos(math.radians(a)) for a in rot)
    sx, sy, sz = (math.sin(math.radians(a)) for a in rot)
    Rx = np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]], dtype=np.float32)
    Ry = np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]], dtype=np.float32)
    Rz = np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]], dtype=np.float32)
    return Rz @ Ry @ Rx

def _apply_rotation(pts: np.ndarray, rot: Optional[Tuple[float, float, float, float]]) -> np.ndarray:
    if rot is None:
        return pts
    if len(rot) == 3:
        R = _euler_to_mat3(rot)
    else:
        R = _quat_to_mat3(rot)
    return pts @ R


def _apply_line_style(starts: np.ndarray, ends: np.ndarray, colors: np.ndarray,
                      style: 'LineStyle', dash_len: float = 0.3, gap_len: float = 0.15) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if style == LineStyle.SOLID or starts.shape[0] == 0:
        return starts, ends, colors
    if style == LineStyle.HIDDEN:
        return starts[:0], ends[:0], colors[:0]
    n = starts.shape[0]
    if style == LineStyle.DASHED:
        return _expand_dash_np(starts, ends, colors, dash_len + gap_len, dash_len)
    elif style == LineStyle.DOTTED:
        dot_len = max(gap_len * 0.15, 0.02)
        return _expand_dash_np(starts, ends, colors, dot_len + gap_len, dot_len)
    if not n:
        return starts[:0], ends[:0], colors[:0]
    return (np.array([], dtype=np.float32).reshape(0, 3), np.array([], dtype=np.float32).reshape(0, 3), np.array([], dtype=np.float32).reshape(0, 4))


def _expand_dash_np(starts: np.ndarray, ends: np.ndarray, colors: np.ndarray,
                    step: float, seg_len: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = starts.shape[0]
    if n == 0 or step <= 1e-12:
        return starts[:0], ends[:0], colors[:0]
    d = np.subtract(ends, starts, dtype=np.float64)
    ln = np.sqrt(np.einsum('ij,ij->i', d, d))
    valid = ln >= 1e-8
    nd = np.zeros(n, dtype=np.intp)
    nd[valid] = np.maximum((ln[valid] / step).astype(np.intp), 1)
    total = int(nd.sum())
    if total == 0:
        return starts[:0], ends[:0], colors[:0]
    idx = np.repeat(np.arange(n), nd)
    seg_start = np.cumsum(nd, dtype=np.intp) - nd
    j = np.arange(total, dtype=np.intp) - np.repeat(seg_start, nd)
    t0 = j * step
    t1 = np.minimum(j * step + seg_len, ln[idx])
    f0 = (t0 / ln[idx])[:, None]
    f1 = (t1 / ln[idx])[:, None]
    s0 = starts[idx].astype(np.float64, copy=False)
    new_s = np.add(s0, d[idx] * f0, dtype=np.float64).astype(np.float32)
    new_e = np.add(s0, d[idx] * f1, dtype=np.float64).astype(np.float32)
    return new_s, new_e, np.ascontiguousarray(colors[idx])


_GIZMO_LINE_BUILDERS: Dict[GizmoType, Callable[[GizmoData], Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]]] = {}


def _register(t: GizmoType):
    def wrapper(f):
        _GIZMO_LINE_BUILDERS[t] = f
        return f
    return wrapper


_SPHERE_CACHE: dict[int, tuple[np.ndarray, np.ndarray]] = {}

def _get_sphere_edges(segs: int):
    cached = _SPHERE_CACHE.get(segs)
    if cached is not None:
        return cached
    lats = np.linspace(0, math.pi, segs + 1, dtype=np.float32)
    lons = np.linspace(0, 2.0 * math.pi, segs + 1, dtype=np.float32)
    lat_sin, lat_cos = np.sin(lats), np.cos(lats)
    lon_sin, lon_cos = np.sin(lons), np.cos(lons)
    nv = segs + 1
    verts = np.empty(((segs + 1) * (segs + 1), 3), dtype=np.float32)
    idx = 0
    for li in range(segs + 1):
        for lj in range(segs + 1):
            verts[idx, 0] = lat_sin[li] * lon_cos[lj]
            verts[idx, 1] = lat_cos[li]
            verts[idx, 2] = lat_sin[li] * lon_sin[lj]
            idx += 1
    lines_buf = []
    for li in range(segs):
        for lj in range(segs):
            i0 = li * nv + lj; i1 = li * nv + lj + 1
            i2 = (li + 1) * nv + lj; i3 = (li + 1) * nv + lj + 1
            lines_buf.extend([i0, i1, i1, i2, i2, i3, i3, i0])
    lidx = np.array(lines_buf, dtype=np.int32)
    starts = verts[lidx[0::2]]
    ends = verts[lidx[1::2]]
    _SPHERE_CACHE[segs] = (starts, ends)
    return starts, ends


_ICOSPHERE_CACHE: dict[int, tuple[np.ndarray, np.ndarray]] = {}

def _get_icosphere_edges(subdivisions: int):
    cached = _ICOSPHERE_CACHE.get(subdivisions)
    if cached is not None:
        return cached
    phi = (1.0 + math.sqrt(5.0)) * 0.5
    verts = np.array([
        [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
        [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
        [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
    ], dtype=np.float32)
    faces = np.array([
        0,11,5, 0,5,1, 0,1,7, 0,7,10, 0,10,11,
        1,5,9, 5,11,4, 11,10,2, 10,7,6, 7,1,8,
        3,9,4, 3,4,2, 3,2,6, 3,6,8, 3,8,9,
        4,9,5, 2,4,11, 6,2,10, 8,6,7, 9,8,1,
    ], dtype=np.int32)
    verts = verts / np.linalg.norm(verts, axis=1, keepdims=True)
    for _ in range(subdivisions):
        edge_mid = {}
        new_faces = []
        n_verts = verts.shape[0]
        new_verts = []
        for i in range(0, len(faces), 3):
            a, b, c = int(faces[i]), int(faces[i+1]), int(faces[i+2])
            ab = (a, b) if a < b else (b, a)
            bc = (b, c) if b < c else (c, b)
            ca = (c, a) if c < a else (a, c)
            for pair in (ab, bc, ca):
                if pair not in edge_mid:
                    mid = (verts[pair[0]] + verts[pair[1]]) * 0.5
                    mid /= np.linalg.norm(mid)
                    edge_mid[pair] = n_verts + len(new_verts)
                    new_verts.append(mid)
            d, e, f = edge_mid[ab], edge_mid[bc], edge_mid[ca]
            new_faces.extend([a,d,f, d,b,e, f,e,c, d,e,f])
        if new_verts:
            verts = np.concatenate([verts, np.array(new_verts, dtype=np.float32)], axis=0)
        faces = np.array(new_faces, dtype=np.int32)
    edge_set = set()
    for i in range(0, len(faces), 3):
        a, b, c = int(faces[i]), int(faces[i+1]), int(faces[i+2])
        for pair in ((a,b),(b,c),(c,a)):
            edge_set.add((a,b) if a < b else (b,a))
    edge_list = np.array(list(edge_set), dtype=np.int32)
    result_starts = verts[edge_list[:, 0]]
    result_ends = verts[edge_list[:, 1]]
    _ICOSPHERE_CACHE[subdivisions] = (result_starts, result_ends)
    return result_starts, result_ends


def _get_label_render_data(g: GizmoData) -> Optional[dict]:
    if not g.text:
        return None
    return {
        'position': g.position,
        'text': g.text,
        'color': g.color,
        'font_size': g.font_size,
        'billboard': g.billboard,
        'world_space': g.world_space,
        'layer': g.layer,
        'duration': g.duration,
    }


@_register(GizmoType.LABEL)
def _build_label(g: GizmoData):
    return None


def _get_icon_render_data(g: GizmoData) -> Optional[dict]:
    if not g.text and not g.texture_path:
        return None
    return {
        'position': g.position,
        'text': g.text,
        'texture_path': g.texture_path,
        'color': g.color,
        'font_size': g.font_size,
        'billboard': g.billboard,
        'world_space': g.world_space,
        'layer': g.layer,
        'duration': g.duration,
    }


@_register(GizmoType.ICON)
def _build_icon(g: GizmoData):
    return None


@_register(GizmoType.TORUS)
def _build_torus(g: GizmoData):
    p = g.position; n = g.normal
    major = g.size; minor = g.inner_radius if g.inner_radius > 0 else major * 0.3
    segs_major = g.segments; segs_minor = max(g.segments // 2, 6)
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(0, 2.0*math.pi, segs_major+1, dtype=np.float32)
    phi = np.linspace(0, 2.0*math.pi, segs_minor+1, dtype=np.float32)
    ct, st = np.cos(theta), np.sin(theta)
    cp, sp = np.cos(phi), np.sin(phi)
    total = segs_major * segs_minor * 2
    starts = np.empty((total, 3), dtype=np.float32)
    ends = np.empty((total, 3), dtype=np.float32)
    idx = 0
    for i in range(segs_major):
        for j in range(segs_minor):
            cx = major * ct[i]; cy = 0; cz = major * st[i]
            for k in range(2):
                a = theta[i] if k == 0 else theta[i+1]
                ca, sa = math.cos(a), math.sin(a)
                rx = major + minor * cp[j]
                x = p1.x * rx * ca + p2.x * rx * sa + n[0] * (minor * sp[j])
                y = p1.y * rx * ca + p2.y * rx * sa + n[1] * (minor * sp[j])
                z = p1.z * rx * ca + p2.z * rx * sa + n[2] * (minor * sp[j])
                if k == 0:
                    starts[idx] = [p[0]+x, p[1]+y, p[2]+z]
                else:
                    ends[idx] = [p[0]+x, p[1]+y, p[2]+z]
                    idx += 1
    for i in range(segs_major):
        for j in range(segs_minor):
            a = theta[i]; ca, sa = math.cos(a), math.sin(a)
            rx = major + minor * cp[j]
            x0 = p1.x * rx * ca + p2.x * rx * sa + n[0] * minor * sp[j]
            y0 = p1.y * rx * ca + p2.y * rx * sa + n[1] * minor * sp[j]
            z0 = p1.z * rx * ca + p2.z * rx * sa + n[2] * minor * sp[j]
            rx2 = major + minor * cp[j+1]
            x1 = p1.x * rx2 * ca + p2.x * rx2 * sa + n[0] * minor * sp[j+1]
            y1 = p1.y * rx2 * ca + p2.y * rx2 * sa + n[1] * minor * sp[j+1]
            z1 = p1.z * rx2 * ca + p2.z * rx2 * sa + n[2] * minor * sp[j+1]
            starts[idx] = [p[0]+x0, p[1]+y0, p[2]+z0]
            ends[idx] = [p[0]+x1, p[1]+y1, p[2]+z1]
            idx += 1
    return starts, ends, _np_color(g.color, total)


@_register(GizmoType.PIPE)
def _build_pipe(g: GizmoData):
    p = g.position; n = g.normal; r = g.size
    h = g.height if g.height > 0 else 1.0
    inner = g.inner_radius
    segs = max(g.segments, 8)
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(0, 2.0*math.pi, segs+1, dtype=np.float32)
    ct, st = np.cos(theta), np.sin(theta)
    outer_bot = np.empty((segs+1, 3), dtype=np.float32)
    outer_top = np.empty((segs+1, 3), dtype=np.float32)
    inner_bot = np.empty((segs+1, 3), dtype=np.float32)
    inner_top = np.empty((segs+1, 3), dtype=np.float32)
    outer_bot[:,0] = p[0]+p1.x*ct*r+p2.x*st*r
    outer_bot[:,1] = p[1]+p1.y*ct*r+p2.y*st*r
    outer_bot[:,2] = p[2]+p1.z*ct*r+p2.z*st*r
    outer_top[:,0] = outer_bot[:,0]+n[0]*h; outer_top[:,1] = outer_bot[:,1]+n[1]*h; outer_top[:,2] = outer_bot[:,2]+n[2]*h
    if inner > 0:
        inner_bot[:,0] = p[0]+p1.x*ct*inner+p2.x*st*inner
        inner_bot[:,1] = p[1]+p1.y*ct*inner+p2.y*st*inner
        inner_bot[:,2] = p[2]+p1.z*ct*inner+p2.z*st*inner
        inner_top[:,0] = inner_bot[:,0]+n[0]*h; inner_top[:,1] = inner_bot[:,1]+n[1]*h; inner_top[:,2] = inner_bot[:,2]+n[2]*h
    total = segs * 4 + (segs * 2 if inner > 0 else 0)
    starts = np.empty((total, 3), dtype=np.float32); ends = np.empty((total, 3), dtype=np.float32)
    idx = 0
    for arr in (outer_bot, outer_top):
        starts[idx:idx+segs] = arr[:-1]; ends[idx:idx+segs] = arr[1:]; idx += segs
    starts[idx:idx+segs] = outer_bot[:-1]; ends[idx:idx+segs] = outer_top[:-1]; idx += segs
    if inner > 0:
        for arr in (inner_bot, inner_top):
            starts[idx:idx+segs] = arr[:-1]; ends[idx:idx+segs] = arr[1:]; idx += segs
        starts[idx:idx+segs] = inner_bot[:-1]; ends[idx:idx+segs] = inner_top[:-1]; idx += segs
    return starts, ends, _np_color(g.color, total)


@_register(GizmoType.STAR)
def _build_star(g: GizmoData):
    p = g.position; n = g.normal; outer = g.size; inner = g.inner_radius if g.inner_radius > 0 else outer * 0.4
    points = g.segments if g.segments >= 3 else 5
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    total_pts = points * 2
    theta = np.linspace(0, 2.0*math.pi, total_pts+1, dtype=np.float32)[:-1]
    r_vals = np.empty(total_pts, dtype=np.float32)
    r_vals[0::2] = outer; r_vals[1::2] = inner
    ct = np.cos(theta) * r_vals; st = np.sin(theta) * r_vals
    pts = np.empty((total_pts, 3), dtype=np.float32)
    pts[:, 0] = p[0] + p1.x*ct + p2.x*st
    pts[:, 1] = p[1] + p1.y*ct + p2.y*st
    pts[:, 2] = p[2] + p1.z*ct + p2.z*st
    starts = pts; ends = np.roll(pts, -1, axis=0)
    return starts, ends, _np_color(g.color, total_pts)


@_register(GizmoType.PIE)
def _build_pie(g: GizmoData):
    p = g.position; n = g.normal; r = g.size
    a0 = math.radians(g.angle_start); a1 = math.radians(g.angle_end)
    segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(a0, a1, segs+1, dtype=np.float32)
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    arc = np.empty((segs+1, 3), dtype=np.float32)
    arc[:, 0] = p[0] + p1.x*ct + p2.x*st
    arc[:, 1] = p[1] + p1.y*ct + p2.y*st
    arc[:, 2] = p[2] + p1.z*ct + p2.z*st
    center = np.array([[p[0], p[1], p[2]]], dtype=np.float32)
    total = segs + 2
    starts = np.empty((total, 3), dtype=np.float32); ends = np.empty((total, 3), dtype=np.float32)
    starts[0] = center[0]; ends[0] = arc[0]
    starts[1:1+segs] = arc[:-1]; ends[1:1+segs] = arc[1:]
    starts[1+segs] = center[0]; ends[1+segs] = arc[-1]
    return starts, ends, _np_color(g.color, total)


@_register(GizmoType.WEDGE)
def _build_wedge(g: GizmoData):
    p = g.position; n = g.normal; r = g.size
    h = g.height if g.height > 0 else 1.0
    a0 = math.radians(g.angle_start); a1 = math.radians(g.angle_end)
    segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(a0, a1, segs+1, dtype=np.float32)
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    bot_arc = np.empty((segs+1, 3), dtype=np.float32)
    bot_arc[:, 0] = p[0] + p1.x*ct + p2.x*st
    bot_arc[:, 1] = p[1] + p1.y*ct + p2.y*st
    bot_arc[:, 2] = p[2] + p1.z*ct + p2.z*st
    top_arc = bot_arc + np.array([[n[0]*h, n[1]*h, n[2]*h]], dtype=np.float32)
    center_bot = np.array([[p[0], p[1], p[2]]], dtype=np.float32)
    center_top = center_bot + np.array([[n[0]*h, n[1]*h, n[2]*h]], dtype=np.float32)
    total = segs*2 + 6
    starts = np.empty((total, 3), dtype=np.float32); ends = np.empty((total, 3), dtype=np.float32)
    idx = 0
    starts[idx:idx+segs] = bot_arc[:-1]; ends[idx:idx+segs] = bot_arc[1:]; idx += segs
    starts[idx:idx+segs] = top_arc[:-1]; ends[idx:idx+segs] = top_arc[1:]; idx += segs
    starts[idx]=center_bot[0]; ends[idx]=bot_arc[0]; idx+=1
    starts[idx]=center_bot[0]; ends[idx]=bot_arc[-1]; idx+=1
    starts[idx]=center_top[0]; ends[idx]=top_arc[0]; idx+=1
    starts[idx]=center_top[0]; ends[idx]=top_arc[-1]; idx+=1
    starts[idx]=bot_arc[0]; ends[idx]=top_arc[0]; idx+=1
    starts[idx]=bot_arc[-1]; ends[idx]=top_arc[-1]; idx+=1
    return starts, ends, _np_color(g.color, total)
