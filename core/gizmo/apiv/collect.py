# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3
from core.gizmo.apiv.types import GizmoType, LineStyle
from core.gizmo.apiv.data import GizmoData
from core.gizmo.apiv.style import _register, _np_color, _apply_rotation, _apply_line_style, _get_icosphere_edges, _get_label_render_data, _get_icon_render_data, _GIZMO_LINE_BUILDERS


@_register(GizmoType.CAPSULE)
def _build_capsule(g: GizmoData):
    p = g.position; ep = g.end_position; r = g.size
    if ep is None:
        ep = (p[0], p[1] + 1.0, p[2])
    segs = max(g.segments // 2, 8)
    dx, dy, dz = ep[0]-p[0], ep[1]-p[1], ep[2]-p[2]
    h = math.sqrt(dx*dx + dy*dy + dz*dz)
    if h < 1e-8:
        return None
    nx, ny, nz = dx/h, dy/h, dz/h
    ref = Vec3(0,1,0)
    axis = Vec3(nx, ny, nz)
    if abs(axis.dot(ref)) > 0.99:
        ref = Vec3(1,0,0)
    p1 = axis.cross(ref).normalized()
    p2 = axis.cross(p1).normalized()
    theta = np.linspace(0, 2.0 * math.pi, segs + 1, dtype=np.float32)
    ct = np.cos(theta) * r; st = np.sin(theta) * r
    n_verts = 3 * segs + 2 * segs * (segs // 2)
    starts = np.empty((n_verts, 3), dtype=np.float32)
    ends = np.empty((n_verts, 3), dtype=np.float32)
    idx = 0
    for top in (False, True):
        base_y = 0.0 if not top else h
        for i in range(segs):
            a0 = theta[i]; a1 = theta[i+1]
            c0, s0 = math.cos(a0), math.sin(a0)
            c1, s1 = math.cos(a1), math.sin(a1)
            for side in range(2):
                a = a0 if side == 0 else a1
                ca, sa = math.cos(a), math.sin(a)
                px = p[0] + r * (p1.x * ca + p2.x * sa)
                py = (p[1] + base_y) + r * (p1.y * ca + p2.y * sa)
                pz = p[2] + r * (p1.z * ca + p2.z * sa)
                if side == 0:
                    starts[idx, 0], starts[idx, 1], starts[idx, 2] = px, py, pz
                else:
                    ends[idx, 0], ends[idx, 1], ends[idx, 2] = px, py, pz
                    idx += 1
    for i in range(segs):
        a = theta[i]
        ca, sa = math.cos(a), math.sin(a)
        bx = p[0] + r * (p1.x * ca + p2.x * sa)
        by = p[1] + r * (p1.y * ca + p2.y * sa)
        bz = p[2] + r * (p1.z * ca + p2.z * sa)
        tx = p[0] + r * (p1.x * ca + p2.x * sa)
        ty = p[1] + h + r * (p1.y * ca + p2.y * sa)
        tz = p[2] + r * (p1.z * ca + p2.z * sa)
        starts[idx] = [bx, by, bz]; ends[idx] = [tx, ty, tz]; idx += 1
    theta_h = np.linspace(0, math.pi, segs // 2 + 1, dtype=np.float32)
    for hemi_top in (False, True):
        base_y = 0.0 if not hemi_top else h
        sign = 1 if hemi_top else -1
        for i in range(len(theta_h) - 1):
            for j in range(segs):
                a0 = theta_h[i]; a1 = theta_h[i+1]
                b0 = 2.0 * math.pi * j / segs
                r0 = r * math.sin(a0); y0 = sign * r * (1 - math.cos(a0))
                r1 = r * math.sin(a1); y1 = sign * r * (1 - math.cos(a1))
                x0 = r0 * math.cos(b0); z0 = r0 * math.sin(b0)
                x1 = r1 * math.cos(b0); z1 = r1 * math.sin(b0)
                starts[idx] = [p[0]+x0, p[1]+base_y+y0, p[2]+z0]
                ends[idx] = [p[0]+x1, p[1]+base_y+y1, p[2]+z1]
                idx += 1
    return starts, ends, _np_color(g.color, n_verts)


@_register(GizmoType.CYLINDER)
def _build_cylinder(g: GizmoData):
    p = g.position; n = g.normal; r = g.size; h = g.height if g.height > 0 else 1.0
    segs = max(g.segments, 8)
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(0, 2.0*math.pi, segs+1, dtype=np.float32)
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    bot = np.empty((segs+1, 3), dtype=np.float32)
    top = np.empty((segs+1, 3), dtype=np.float32)
    bot[:, 0] = p[0] + p1.x*ct + p2.x*st
    bot[:, 1] = p[1] + p1.y*ct + p2.y*st
    bot[:, 2] = p[2] + p1.z*ct + p2.z*st
    top[:, 0] = p[0] + p1.x*ct + p2.x*st + n[0]*h
    top[:, 1] = p[1] + p1.y*ct + p2.y*st + n[1]*h
    top[:, 2] = p[2] + p1.z*ct + p2.z*st + n[2]*h
    total = segs * 3
    starts = np.empty((total, 3), dtype=np.float32); ends = np.empty((total, 3), dtype=np.float32)
    starts[:segs] = bot[:-1]; ends[:segs] = bot[1:]
    starts[segs:2*segs] = top[:-1]; ends[segs:2*segs] = top[1:]
    starts[2*segs:] = bot[:-1]; ends[2*segs:] = top[:-1]
    return starts, ends, _np_color(g.color, total)


@_register(GizmoType.ELLIPSE)
def _build_ellipse(g: GizmoData):
    p = g.position; n = g.normal; rx = g.size; ry = g.radius_y if g.radius_y > 0 else rx * 0.5
    segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(0, 2.0*math.pi, segs+1, dtype=np.float32)
    ct = np.cos(theta); st = np.sin(theta)
    pts = np.empty((segs+1, 3), dtype=np.float32)
    pts[:, 0] = p[0] + p1.x*ct*rx + p2.x*st*ry
    pts[:, 1] = p[1] + p1.y*ct*rx + p2.y*st*ry
    pts[:, 2] = p[2] + p1.z*ct*rx + p2.z*st*ry
    return pts[:-1], pts[1:], _np_color(g.color, segs)


@_register(GizmoType.RECT)
def _build_rect(g: GizmoData):
    p = g.position; n = g.normal
    sz = g.size if isinstance(g.size, (tuple, list)) else (g.size, g.size)
    hw, hh = sz[0]*0.5 if isinstance(sz, (tuple,list)) else sz*0.5, (sz[1] if isinstance(sz,(tuple,list)) else sz)*0.5
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    corners = np.array([[-hw, -hh, 0], [hw, -hh, 0], [hw, hh, 0], [-hw, hh, 0]], dtype=np.float32)
    corners = _apply_rotation(corners, g.rotation)
    pts = np.empty((4, 3), dtype=np.float32)
    pts[:, 0] = p[0] + p1.x*corners[:,0] + p2.x*corners[:,1] + n[0]*corners[:,2]
    pts[:, 1] = p[1] + p1.y*corners[:,0] + p2.y*corners[:,1] + n[1]*corners[:,2]
    pts[:, 2] = p[2] + p1.z*corners[:,0] + p2.z*corners[:,1] + n[2]*corners[:,2]
    edges = np.array([(0,1),(1,2),(2,3),(3,0)])
    return pts[edges[:,0]], pts[edges[:,1]], _np_color(g.color, 4)


@_register(GizmoType.RAY)
def _build_ray(g: GizmoData):
    p = g.position; n = g.normal; ln = g.size
    ex = p[0] + n[0]*ln; ey = p[1] + n[1]*ln; ez = p[2] + n[2]*ln
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(0,1,0) if abs(n[1])<0.9 else Vec3(1,0,0)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    head_sz = g.arrow_size if g.arrow_size > 0 else ln*0.15
    spread = head_sz * 0.5
    starts = np.empty((4, 3), dtype=np.float32); ends = np.empty((4, 3), dtype=np.float32)
    starts[0] = [p[0], p[1], p[2]]; ends[0] = [ex, ey, ez]
    for i in range(3):
        a = 2.0*math.pi*i/3
        ca, sa = math.cos(a)*spread, math.sin(a)*spread
        hx = ex - n[0]*head_sz; hy = ey - n[1]*head_sz; hz = ez - n[2]*head_sz
        starts[i+1] = [hx, hy, hz]
        ends[i+1] = [ex+p1.x*ca+p2.x*sa, ey+p1.y*ca+p2.y*sa, ez+p1.z*ca+p2.z*sa]
    return starts, ends, _np_color(g.color, 4)


@_register(GizmoType.BBOX)
def _build_bbox(g: GizmoData):
    mn = g.min_point; mx = g.max_point
    corners = np.array([
        [mn[0], mn[1], mn[2]], [mx[0], mn[1], mn[2]], [mx[0], mx[1], mn[2]], [mn[0], mx[1], mn[2]],
        [mn[0], mn[1], mx[2]], [mx[0], mn[1], mx[2]], [mx[0], mx[1], mx[2]], [mn[0], mx[1], mx[2]],
    ], dtype=np.float32)
    edges = np.array([(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)])
    return corners[edges[:,0]], corners[edges[:,1]], _np_color(g.color, 12)


@_register(GizmoType.FRUSTUM)
def _build_frustum(g: GizmoData):
    p = g.position; n = g.normal; fov = g.fov; aspect = g.size if g.size > 0 else 1.5
    near = g.near_plane; far = g.far_plane
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(0,1,0) if abs(n[1])<0.9 else Vec3(1,0,0)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    fov_rad = math.radians(fov)
    nh = math.tan(fov_rad * 0.5) * near; nw = nh * aspect
    fh = math.tan(fov_rad * 0.5) * far; fw = fh * aspect
    near_c = np.array([[-nw, -nh, near], [nw, -nh, near], [nw, nh, near], [-nw, nh, near]], dtype=np.float32)
    far_c = np.array([[-fw, -fh, far], [fw, -fh, far], [fw, fh, far], [-fw, fh, far]], dtype=np.float32)
    all_c = np.concatenate([near_c, far_c], axis=0)
    transformed = np.empty_like(all_c)
    transformed[:, 0] = p[0] + p1.x*all_c[:,0] + p2.x*all_c[:,1] + n[0]*all_c[:,2]
    transformed[:, 1] = p[1] + p1.y*all_c[:,0] + p2.y*all_c[:,1] + n[1]*all_c[:,2]
    transformed[:, 2] = p[2] + p1.z*all_c[:,0] + p2.z*all_c[:,1] + n[2]*all_c[:,2]
    edges = np.array([(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)])
    return transformed[edges[:,0]], transformed[edges[:,1]], _np_color(g.color, 12)


@_register(GizmoType.HELIX)
def _build_helix(g: GizmoData):
    p = g.position; n = g.normal; h = g.height if g.height > 0 else 2.0; r = g.size
    turns = max(g.turns, 1); segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(0,1,0) if abs(n[1])<0.9 else Vec3(1,0,0)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    total = segs * int(turns)
    theta = np.linspace(0, 2.0*math.pi*turns, total + 1, dtype=np.float32)
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    vz = np.linspace(0, h, total + 1, dtype=np.float32)
    pts = np.empty((total + 1, 3), dtype=np.float32)
    pts[:, 0] = p[0] + p1.x*ct + p2.x*st + n[0]*vz
    pts[:, 1] = p[1] + p1.y*ct + p2.y*st + n[1]*vz
    pts[:, 2] = p[2] + p1.z*ct + p2.z*st + n[2]*vz
    return pts[:-1], pts[1:], _np_color(g.color, total)


@_register(GizmoType.PARABOLA)
def _build_parabola(g: GizmoData):
    s = g.position; ep = g.end_position
    if ep is None:
        return None
    h = g.height; segs = g.segments
    sx, sy, sz = s; ex, ey, ez = ep
    dx, dy, dz = ex-sx, ey-sy, ez-sz
    t = np.linspace(0, 1, segs+1, dtype=np.float32)
    x = sx + dx*t; y = sy + dy*t + h * 4 * t * (1-t); z = sz + dz*t
    pts = np.column_stack([x, y, z])
    return pts[:-1], pts[1:], _np_color(g.color, segs)


@_register(GizmoType.SPLINE)
def _build_spline(g: GizmoData):
    pts = g.points
    if not pts or len(pts) < 2:
        return None
    segs = g.segments
    p = np.array(pts, dtype=np.float32)
    n = len(p)
    total_segs = (n - 1) * segs
    t = np.linspace(0, 1, segs + 1, dtype=np.float32)[:, None]
    result = np.empty((total_segs + 1, 3), dtype=np.float32)
    idx = 0
    for i in range(n - 1):
        p0 = p[max(0, i-1)]
        p1 = p[i]; p2 = p[min(n-1, i+1)]; p3 = p[min(n-1, i+2)]
        t2 = t*t; t3 = t2*t
        mt = 1-t; mt2 = mt*mt; mt3 = mt2*mt
        catmull = 0.5 * (
            2*p1 + (-p0+p2)*t + (2*p0-5*p1+4*p2-p3)*t2 + (-p0+3*p1-3*p2+p3)*t3
        )
        if i < n - 2:
            result[idx:idx+segs+1] = catmull
        else:
            result[idx:] = catmull
            break
        idx += segs
    return result[:-1], result[1:], _np_color(g.color, total_segs)


@_register(GizmoType.ICOSPHERE)
def _build_icosphere(g: GizmoData):
    p = g.position; r = g.size
    starts, ends = _get_icosphere_edges(g.subdivisions)
    n = starts.shape[0]
    po = np.array([p[0], p[1], p[2]], dtype=np.float32)
    starts = starts * r + po
    ends = ends * r + po
    return starts, ends, _np_color(g.color, n)


class _CollectMixin:
    def get_label_data(self) -> list[dict]:
        with self._lock:
            if self._label_count == 0:
                return []
            labels = []
            gizmos = list(self.persistent_draws)
            if self.unique_draws:
                gizmos.extend(self.unique_draws.values())
            for g in gizmos:
                if g.gizmo_type == GizmoType.LABEL and g.text:
                    data = _get_label_render_data(g)
                    if data:
                        labels.append(data)
            return labels
    def get_icon_data(self) -> list[dict]:
        with self._lock:
            if self._icon_count == 0:
                return []
            icons = []
            gizmos = list(self.persistent_draws)
            if self.unique_draws:
                gizmos.extend(self.unique_draws.values())
            for g in gizmos:
                if g.gizmo_type == GizmoType.ICON:
                    data = _get_icon_render_data(g)
                    if data:
                        icons.append(data)
            return icons
    def _clear_cache(self):
        self._cache_starts = None
        self._cache_ends = None
        self._cache_colors = None
        self._cached_revision = -1
    def build_render_arrays(self):
        with self._lock:
            if self._revision == self._cached_revision:
                if self._cache_starts is not None:
                    return (self._cache_starts, self._cache_ends, self._cache_colors)
                return (None, None, None)
            gizmos = list(self.persistent_draws)
            if self.unique_draws:
                gizmos.extend(self.unique_draws.values())
            current_revision = self._revision
            np_data = None
            if self.enabled:
                np_data = self._get_render_data()
            self._batches.clear()
            self._flat_size = 0
        s_list = []
        e_list = []
        c_list = []
        if self.enabled:
            if np_data is not None:
                s_list.append(np_data[0])
                e_list.append(np_data[1])
                c_list.append(np_data[2])
            for g in gizmos:
                builder = _GIZMO_LINE_BUILDERS.get(g.gizmo_type)
                if builder is None:
                    continue
                try:
                    result = builder(g)
                except Exception:
                    continue
                if result is None:
                    continue
                s, e, c = result
                if g.line_style is not LineStyle.SOLID:
                    s, e, c = _apply_line_style(s, e, c, g.line_style, g.dash_length, g.gap_length)
                if s.shape[0] > 0:
                    s_list.append(s)
                    e_list.append(e)
                    c_list.append(c)
        if s_list:
            if len(s_list) == 1:
                self._cache_starts = s_list[0]
                self._cache_ends = e_list[0]
                self._cache_colors = c_list[0]
            else:
                self._cache_starts = np.concatenate(s_list)
                self._cache_ends = np.concatenate(e_list)
                self._cache_colors = np.concatenate(c_list)
        else:
            self._cache_starts = None
            self._cache_ends = None
            self._cache_colors = None
        self._cached_revision = current_revision
        return (self._cache_starts, self._cache_ends, self._cache_colors)
    def draw_lines(self, starts: np.ndarray, ends: np.ndarray, colors: np.ndarray):
        if starts.shape[0] == 0:
            return
        with self._lock:
            old_sz = self._flat_size
            n = starts.shape[0]
            new_sz = old_sz + n
            if new_sz > self._flat_starts.shape[0]:
                new_cap = int(new_sz * 1.5 + 4096)
                self._flat_starts = np.resize(self._flat_starts, (new_cap, 3))
                self._flat_ends = np.resize(self._flat_ends, (new_cap, 3))
                self._flat_colors = np.resize(self._flat_colors, (new_cap, 4))
            self._flat_starts[old_sz:new_sz] = starts
            self._flat_ends[old_sz:new_sz] = ends
            if colors.shape[1] >= 4:
                self._flat_colors[old_sz:new_sz] = colors[:, :4]
            elif colors.shape[1] == 3:
                self._flat_colors[old_sz:new_sz, :3] = colors
                self._flat_colors[old_sz:new_sz, 3] = 1.0
            else:
                self._flat_colors[old_sz:new_sz] = 1.0
            self._flat_size = new_sz
            self._revision += 1
    def _get_render_data(self):
        if self._flat_size > 0:
            return (self._flat_starts[:self._flat_size],
                    self._flat_ends[:self._flat_size],
                    self._flat_colors[:self._flat_size])
        if self._batches:
            b = self._batches
            if len(b) == 1:
                return b[0]
            s_list, e_list, c_list = zip(*b)
            return (np.concatenate(s_list), np.concatenate(e_list), np.concatenate(c_list))
        return None


def collect_builders():
    return dict(_GIZMO_LINE_BUILDERS)


def collect_render_arrays(mgr):
    return mgr.build_render_arrays()
