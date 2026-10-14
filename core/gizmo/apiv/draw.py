# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3
from core.gizmo.apiv.types import GizmoType
from core.gizmo.apiv.data import GizmoData
from core.gizmo.apiv.style import _register, _np_color, _apply_rotation, _get_sphere_edges


@_register(GizmoType.POINT)
def _build_point(g: GizmoData):
    p = g.position; s = g.size * 0.5
    c = np.array([[p[0]], [p[0]], [p[1]], [p[1]], [p[2]], [p[2]]], dtype=np.float32)
    pts = np.array([
        [p[0]-s, p[1], p[2]], [p[0]+s, p[1], p[2]],
        [p[0], p[1]-s, p[2]], [p[0], p[1]+s, p[2]],
        [p[0], p[1], p[2]-s], [p[0], p[1], p[2]+s],
    ], dtype=np.float32)
    starts = pts[0::2]; ends = pts[1::2]
    return starts, ends, _np_color(g.color, 3)


@_register(GizmoType.LINE)
def _build_line(g: GizmoData):
    if g.end_position is None:
        return None
    s = np.array([[g.position[0], g.position[1], g.position[2]]], dtype=np.float32)
    e = np.array([[g.end_position[0], g.end_position[1], g.end_position[2]]], dtype=np.float32)
    return s, e, _np_color(g.color, 1)


@_register(GizmoType.CIRCLE)
def _build_circle(g: GizmoData):
    p = g.position; n = g.normal; r = g.size; segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(0, 2.0 * math.pi, segs + 1, dtype=np.float32)
    ct = np.cos(theta) * r; st = np.sin(theta) * r
    po = np.array([p[0], p[1], p[2]], dtype=np.float32)
    p1a = np.array([p1.x, p1.y, p1.z], dtype=np.float32)
    p2a = np.array([p2.x, p2.y, p2.z], dtype=np.float32)
    pts = po + p1a * ct[:, None] + p2a * st[:, None]
    return pts[:-1], pts[1:], _np_color(g.color, segs)


@_register(GizmoType.SPHERE)
def _build_sphere(g: GizmoData):
    p = g.position; r = g.size; segs = max(g.segments // 2, 4)
    starts, ends = _get_sphere_edges(segs)
    n = starts.shape[0]
    starts = starts * r + np.array([p[0], p[1], p[2]], dtype=np.float32)
    ends = ends * r + np.array([p[0], p[1], p[2]], dtype=np.float32)
    return starts, ends, _np_color(g.color, n)


@_register(GizmoType.BOX)
def _build_box(g: GizmoData):
    p = g.position; h = g.size if isinstance(g.size, (tuple, list)) else (g.size, g.size, g.size)
    hx, hy, hz = h[0]*0.5, h[1]*0.5, h[2]*0.5
    corners = np.array([
        [-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
        [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz],
    ], dtype=np.float32)
    corners = _apply_rotation(corners, g.rotation)
    corners += np.array([p[0], p[1], p[2]], dtype=np.float32)
    edges = np.array([(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)])
    return corners[edges[:, 0]], corners[edges[:, 1]], _np_color(g.color, 12)


@_register(GizmoType.ARC)
def _build_arc(g: GizmoData):
    p = g.position; n = g.normal; r = g.size
    a0 = math.radians(g.angle_start); a1 = math.radians(g.angle_end)
    segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(a0, a1, segs + 1, dtype=np.float32)
    ct = np.cos(theta) * r; st = np.sin(theta) * r
    po = np.array([p[0], p[1], p[2]], dtype=np.float32)
    p1a = np.array([p1.x, p1.y, p1.z], dtype=np.float32)
    p2a = np.array([p2.x, p2.y, p2.z], dtype=np.float32)
    pts = po + p1a * ct[:, None] + p2a * st[:, None]
    return pts[:-1], pts[1:], _np_color(g.color, segs)


@_register(GizmoType.GRID)
def _build_grid(g: GizmoData):
    p = g.position; n = g.normal; sz = g.size; divs = max(g.segments, 2)
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    half = sz * 0.5
    vals = np.linspace(-half, half, divs + 1, dtype=np.float32)
    total_lines = (divs + 1) * 2
    p1a = np.array([p1.x, p1.y, p1.z], dtype=np.float32)
    p2a = np.array([p2.x, p2.y, p2.z], dtype=np.float32)
    po = np.array([p[0], p[1], p[2]], dtype=np.float32)
    starts = np.empty((total_lines, 3), dtype=np.float32)
    ends = np.empty((total_lines, 3), dtype=np.float32)
    starts[:divs+1] = po + p1a * (-half) + p2a * vals[:, None]
    ends[:divs+1]   = po + p1a * half + p2a * vals[:, None]
    starts[divs+1:] = po + p1a * vals[:, None] + p2a * (-half)
    ends[divs+1:]   = po + p1a * vals[:, None] + p2a * half
    return starts, ends, _np_color(g.color, total_lines)


@_register(GizmoType.CONE)
def _build_cone(g: GizmoData):
    p = g.position; n = g.normal; r = g.size; h = g.height if g.height > 0 else g.size * 2
    segs = max(g.segments, 8)
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    tip = np.array([p[0] + n[0]*h, p[1] + n[1]*h, p[2] + n[2]*h], dtype=np.float32)
    theta = np.linspace(0, 2.0*math.pi, segs+1, dtype=np.float32)
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    base = np.empty((segs+1, 3), dtype=np.float32)
    base[:, 0] = p[0] + p1.x*ct + p2.x*st
    base[:, 1] = p[1] + p1.y*ct + p2.y*st
    base[:, 2] = p[2] + p1.z*ct + p2.z*st
    total = segs * 2
    starts = np.empty((total, 3), dtype=np.float32); ends = np.empty((total, 3), dtype=np.float32)
    starts[:segs] = base[:-1]; ends[:segs] = base[1:]
    starts[segs:2*segs] = base[:-1]; ends[segs:2*segs] = tip
    return starts, ends, _np_color(g.color, total)


@_register(GizmoType.AXIS)
def _build_axis(g: GizmoData):
    p = g.position; ln = g.size
    cols = [(1,0,0,1), (0,1,0,1), (0,0,1,1)]
    starts = np.array([[p[0],p[1],p[2]]]*3, dtype=np.float32)
    ends = np.array([
        [p[0]+ln, p[1], p[2]], [p[0], p[1]+ln, p[2]], [p[0], p[1], p[2]+ln],
    ], dtype=np.float32)
    colors = np.zeros((3, 4), dtype=np.float32)
    for i in range(3):
        colors[i] = cols[i]
    return starts, ends, colors


@_register(GizmoType.RING)
def _build_ring(g: GizmoData):
    p = g.position; outer = g.size; inner = g.inner_radius
    n = g.normal; segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    theta = np.linspace(0, 2.0*math.pi, segs+1, dtype=np.float32)
    ct = np.cos(theta); st = np.sin(theta)
    outer_pts = np.empty((segs+1, 3), dtype=np.float32)
    inner_pts = np.empty((segs+1, 3), dtype=np.float32)
    outer_pts[:, 0] = p[0] + p1.x*ct*outer + p2.x*st*outer
    outer_pts[:, 1] = p[1] + p1.y*ct*outer + p2.y*st*outer
    outer_pts[:, 2] = p[2] + p1.z*ct*outer + p2.z*st*outer
    inner_pts[:, 0] = p[0] + p1.x*ct*inner + p2.x*st*inner
    inner_pts[:, 1] = p[1] + p1.y*ct*inner + p2.y*st*inner
    inner_pts[:, 2] = p[2] + p1.z*ct*inner + p2.z*st*inner
    total = segs * 2
    starts = np.empty((total, 3), dtype=np.float32); ends = np.empty((total, 3), dtype=np.float32)
    starts[:segs] = outer_pts[:-1]; ends[:segs] = outer_pts[1:]
    starts[segs:] = inner_pts[:-1]; ends[segs:] = inner_pts[1:]
    return starts, ends, _np_color(g.color, total)


@_register(GizmoType.ARROW)
def _build_arrow(g: GizmoData):
    if g.end_position is None:
        return None
    s = np.array([[g.position[0], g.position[1], g.position[2]]], dtype=np.float32)
    e = np.array([[g.end_position[0], g.end_position[1], g.end_position[2]]], dtype=np.float32)
    dx = e[0,0] - s[0,0]; dy = e[0,1] - s[0,1]; dz = e[0,2] - s[0,2]
    ln = math.sqrt(dx*dx+dy*dy+dz*dz)
    if ln < 1e-8:
        return None
    head_sz = min(g.arrow_size if g.arrow_size > 0 else ln*0.2, ln*0.5)
    t = 1.0 - head_sz/ln
    hx = s[0,0] + dx*t; hy = s[0,1] + dy*t; hz = s[0,2] + dz*t
    nx, ny, nz = dx/ln, dy/ln, dz/ln
    ref = Vec3(0,1,0) if abs(ny)<0.9 else Vec3(1,0,0)
    ax = Vec3(nx, ny, nz)
    p1 = ax.cross(ref).normalized()
    p2 = ax.cross(p1).normalized()
    spread = head_sz * 0.5
    starts = np.empty((4, 3), dtype=np.float32)
    ends = np.empty((4, 3), dtype=np.float32)
    starts[0] = s[0]; ends[0] = e[0]
    for i in range(3):
        a = 2.0*math.pi*i/3
        ca, sa = math.cos(a)*spread, math.sin(a)*spread
        starts[i+1] = [hx, hy, hz]
        ends[i+1] = [e[0,0]+p1.x*ca+p2.x*sa, e[0,1]+p1.y*ca+p2.y*sa, e[0,2]+p1.z*ca+p2.z*sa]
    return starts, ends, _np_color(g.color, 4)


@_register(GizmoType.CROSS)
def _build_cross(g: GizmoData):
    p = g.position; s = g.size * 0.5
    starts = np.array([
        [p[0]-s, p[1], p[2]], [p[0], p[1]-s, p[2]], [p[0], p[1], p[2]-s],
    ], dtype=np.float32)
    ends = np.array([
        [p[0]+s, p[1], p[2]], [p[0], p[1]+s, p[2]], [p[0], p[1], p[2]+s],
    ], dtype=np.float32)
    return starts, ends, _np_color(g.color, 3)


@_register(GizmoType.DASHED)
def _build_dashed(g: GizmoData):
    if g.end_position is None:
        return None
    sx, sy, sz = g.position
    ex, ey, ez = g.end_position
    dx, dy, dz = ex-sx, ey-sy, ez-sz
    ln = math.sqrt(dx*dx+dy*dy+dz*dz)
    if ln < 1e-8:
        return None
    dash = g.dash_length; gap = g.gap_length
    step = dash + gap
    n = max(int(ln / step), 1)
    starts = np.empty((n, 3), dtype=np.float32); ends = np.empty((n, 3), dtype=np.float32)
    for i in range(n):
        t0 = i * step / ln; t1 = min((i * step + dash) / ln, 1.0)
        starts[i] = [sx+dx*t0, sy+dy*t0, sz+dz*t0]
        ends[i] = [sx+dx*t1, sy+dy*t1, sz+dz*t1]
    return starts, ends, _np_color(g.color, n)


@_register(GizmoType.BEZIER)
def _build_bezier(g: GizmoData):
    pts = g.points
    if not pts or len(pts) < 2:
        return None
    segs = max(int(g.segments), 1)
    p = np.array(pts, dtype=np.float32)
    n = len(p)
    if n == 2:
        curve = np.linspace(p[0], p[1], segs + 1, dtype=np.float32)
    else:
        pieces = []
        for i in range(n - 1):
            p0 = p[max(i - 1, 0)]
            p1 = p[i]
            p2 = p[i + 1]
            p3 = p[min(i + 2, n - 1)]
            u = np.linspace(0, 1, segs + 1, dtype=np.float32)[:, None]
            u2 = u * u; u3 = u2 * u
            h0 = 2*u3 - 3*u2 + 1
            h1 = -2*u3 + 3*u2
            h2 = u3 - 2*u2 + u
            h3 = u3 - u2
            piece = h0*p1 + h1*p2 + 0.5*(h2*(p2 - p0) + h3*(p3 - p1))
            if i == 0:
                pieces.append(piece)
            else:
                pieces.append(piece[1:])
        curve = np.concatenate(pieces, axis=0)
    return curve[:-1], curve[1:], _np_color(g.color, curve.shape[0] - 1)


@_register(GizmoType.TRIANGLE)
def _build_triangle(g: GizmoData):
    pts = g.points
    if not pts or len(pts) < 3:
        return None
    p = np.array(pts[:3], dtype=np.float32)
    starts = np.array([p[0], p[1], p[2]], dtype=np.float32)
    ends = np.array([p[1], p[2], p[0]], dtype=np.float32)
    return starts, ends, _np_color(g.color, 3)


@_register(GizmoType.POLY)
def _build_poly(g: GizmoData):
    pts = g.points
    if not pts or len(pts) < 3:
        return None
    p = np.array(pts, dtype=np.float32)
    n = len(pts)
    starts = p[:-1]; ends = p[1:]
    if not g.filled:
        starts = np.concatenate([starts, p[-1:]], axis=0)
        ends = np.concatenate([ends, p[:1]], axis=0)
    return starts, ends, _np_color(g.color, len(starts))


class _DrawMixin:
    def draw_point(self, position, color='white', size=3.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.POINT, position, color=color, size=size, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_line(self, start, end, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.LINE, start, end, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_circle(self, center, normal=(0,1,0), radius=1.0, color='white', filled=False, thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.CIRCLE, center, normal=self._resolve_pos(normal), size=radius, color=color, filled=filled, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_sphere(self, center, radius=1.0, color='white', filled=False, thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.SPHERE, center, size=radius, color=color, filled=filled, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_box(self, center, size=(1,1,1), color='white', filled=False, thickness=1.0, rotation=None, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.BOX, center, size=size, color=color, filled=filled, thickness=thickness, rotation=rotation, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_arc(self, center, normal=(0,1,0), radius=1.0, angle_start=0.0, angle_end=360.0, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.ARC, center, normal=self._resolve_pos(normal), size=radius, color=color, angle_start=angle_start, angle_end=angle_end, segments=segments, thickness=thickness, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_capsule(self, start, end, radius=0.5, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.CAPSULE, start, end, size=radius, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_grid(self, center, normal=(0,1,0), size=10.0, divisions=10, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.GRID, center, normal=self._resolve_pos(normal), size=size, segments=divisions, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_cone(self, center, direction=(0,1,0), height=1.0, base_radius=0.5, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.CONE, center, normal=self._resolve_pos(direction), size=base_radius, height=height, color=color, filled=filled, thickness=thickness, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_axis(self, origin, length=1.0, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.AXIS, origin, size=length, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_text(self, position, text, color='white', font_size=14, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.TEXT, position, text=text, color=color, font_size=font_size, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_ring(self, center, inner_radius=0.5, outer_radius=1.0, color='white', filled=False, thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.RING, center, size=outer_radius, inner_radius=inner_radius, color=color, filled=filled, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_arrow(self, start, end, color='white', thickness=2.0, arrow_size=0.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.ARROW, start, end, color=color, thickness=thickness, arrow_size=arrow_size, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_cross(self, center, size=1.0, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.CROSS, center, size=size, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_dashed_line(self, start, end, color='white', thickness=1.0, dash_length=0.3, gap_length=0.15, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.DASHED, start, end, color=color, thickness=thickness, dash_length=dash_length, gap_length=gap_length, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_bezier(self, points, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        pts = [self._resolve_pos(p) for p in points]
        self._draw_gizmo(GizmoType.BEZIER, pts[0], points=pts, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_triangle(self, p0, p1, p2, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True, **kw):
        pts = [self._resolve_pos(p) for p in (p0, p1, p2)]
        self._draw_gizmo(GizmoType.TRIANGLE, pts[0], points=pts, color=color, filled=filled, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_poly(self, points, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True, **kw):
        pts = [self._resolve_pos(p) for p in points]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        self._draw_gizmo(GizmoType.POLY, (cx, cy, cz), points=pts, color=color, filled=filled, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_cylinder(self, center, direction=(0,1,0), height=1.0, radius=0.5, color='white', filled=False, thickness=1.0, rotation=None, segments=32, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.CYLINDER, center, normal=self._resolve_pos(direction), size=radius, height=height, color=color, filled=filled, thickness=thickness, segments=segments, rotation=rotation, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_ellipse(self, center, normal=(0,1,0), radius_x=1.0, radius_y=0.5, color='white', thickness=1.0, segments=32, filled=False, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.ELLIPSE, center, normal=self._resolve_pos(normal), size=radius_x, radius_y=radius_y, color=color, thickness=thickness, segments=segments, filled=filled, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_rect(self, center, size=(1.0, 1.0), normal=(0, 0, 1), color='white', filled=False, thickness=1.0, rotation=None, duration=0.0, layer=0, world_space=True, cull_distance=-1.0, **kw):
        self._draw_gizmo(GizmoType.RECT, center, size=size, normal=self._resolve_pos(normal), color=color, filled=filled, thickness=thickness, rotation=rotation, duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance, **kw)
    def draw_ray(self, origin, direction, length=1.0, color='white', thickness=1.0, arrow_size=0.2, duration=0.0, layer=0, world_space=True, **kw):
        d = self._resolve_pos(direction)
        ln = math.sqrt(d[0]**2+d[1]**2+d[2]**2)
        if ln > 0:
            d = (d[0]/ln, d[1]/ln, d[2]/ln)
        self._draw_gizmo(GizmoType.RAY, origin, normal=d, size=length, color=color, thickness=thickness, arrow_size=arrow_size, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_bbox(self, min_point, max_point, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.BBOX, min_point=self._resolve_pos(min_point), max_point=self._resolve_pos(max_point), color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_frustum(self, origin, direction, fov=60.0, aspect=1.5, near=0.1, far=10.0, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.FRUSTUM, origin, normal=self._resolve_pos(direction), size=aspect, fov=fov, near_plane=near, far_plane=far, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_helix(self, center, direction=(0,1,0), height=2.0, radius=0.5, turns=3.0, color='white', thickness=1.0, segments=64, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.HELIX, center, normal=self._resolve_pos(direction), size=radius, height=height, turns=turns, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_parabola(self, start, end, height=1.0, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.PARABOLA, start, end, height=height, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_spline(self, points, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        pts = [self._resolve_pos(p) for p in points]
        self._draw_gizmo(GizmoType.SPLINE, pts[0], points=pts, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_icosphere(self, center, radius=1.0, color='white', subdivisions=1, thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.ICOSPHERE, center, size=radius, color=color, subdivisions=subdivisions, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_label(self, position, text, color='white', font_size=14, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.LABEL, position, text=text, color=color, font_size=font_size, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_icon(self, position, text='', texture_path='', color='white', font_size=14, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.ICON, position, text=text, texture_path=texture_path, color=color, font_size=font_size, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_torus(self, center, normal=(0,1,0), major_radius=1.0, minor_radius=0.3, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.TORUS, center, normal=self._resolve_pos(normal), size=major_radius, inner_radius=minor_radius, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_pipe(self, center, direction=(0,1,0), height=1.0, outer_radius=0.5, inner_radius=0.3, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.PIPE, center, normal=self._resolve_pos(direction), size=outer_radius, inner_radius=inner_radius, height=height, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_star(self, center, normal=(0,1,0), outer_radius=1.0, inner_radius=0.4, points=5, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.STAR, center, normal=self._resolve_pos(normal), size=outer_radius, inner_radius=inner_radius, segments=points, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_pie(self, center, normal=(0,1,0), radius=1.0, angle_start=0.0, angle_end=90.0, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.PIE, center, normal=self._resolve_pos(normal), size=radius, angle_start=angle_start, angle_end=angle_end, segments=segments, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_wedge(self, center, direction=(0,1,0), radius=1.0, height=1.0, angle_start=0.0, angle_end=90.0, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.WEDGE, center, normal=self._resolve_pos(direction), size=radius, height=height, angle_start=angle_start, angle_end=angle_end, segments=segments, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_spiral(self, center, direction=(0,1,0), max_radius=1.0, height=2.0, turns=3.0, color='white', thickness=1.0, segments=64, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.SPIRAL, center, normal=self._resolve_pos(direction), size=max_radius, height=height, turns=turns, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_chord(self, center, normal=(0,1,0), radius=1.0, angle_start=0.0, angle_end=90.0, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.CHORD, center, normal=self._resolve_pos(normal), size=radius, angle_start=angle_start, angle_end=angle_end, segments=segments, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_hemisphere(self, center, normal=(0,1,0), radius=1.0, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.HEMISPHERE, center, normal=self._resolve_pos(normal), size=radius, color=color, thickness=thickness, segments=segments, duration=duration, layer=layer, world_space=world_space, **kw)
    def draw_pyramid(self, center, direction=(0,1,0), base_radius=0.5, height=1.0, sides=4, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, **kw):
        self._draw_gizmo(GizmoType.PYRAMID, center, normal=self._resolve_pos(direction), size=base_radius, height=height, segments=sides, color=color, thickness=thickness, duration=duration, layer=layer, world_space=world_space, **kw)
