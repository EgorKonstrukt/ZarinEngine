# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import random
import threading
import numpy as np
from typing import Optional, List, Tuple, Dict
from core.maths.math3d import Vec3
from core.gizmo.apiv.types import GizmoType, LineStyle
from core.gizmo.apiv.data import GizmoData
from core.gizmo.apiv.style import _GizmoStyleCtx, _register, _np_color
from core.gizmo.apiv.draw import _DrawMixin
from core.gizmo.apiv.collect import _CollectMixin


@_register(GizmoType.SPIRAL)
def _build_spiral(g: GizmoData):
    p = g.position; n = g.normal; max_r = g.size; h = g.height if g.height > 0 else 2.0
    turns = max(g.turns, 1); segs = g.segments
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(0,1,0) if abs(n[1])<0.9 else Vec3(1,0,0)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    total = segs * int(turns)
    theta = np.linspace(0, 2.0*math.pi*turns, total+1, dtype=np.float32)
    radius = np.linspace(0, max_r, total+1, dtype=np.float32)
    ct = np.cos(theta)*radius; st = np.sin(theta)*radius
    vz = np.linspace(0, h, total+1, dtype=np.float32)
    pts = np.empty((total+1, 3), dtype=np.float32)
    pts[:, 0] = p[0] + p1.x*ct + p2.x*st + n[0]*vz
    pts[:, 1] = p[1] + p1.y*ct + p2.y*st + n[1]*vz
    pts[:, 2] = p[2] + p1.z*ct + p2.z*st + n[2]*vz
    return pts[:-1], pts[1:], _np_color(g.color, total)


@_register(GizmoType.CHORD)
def _build_chord(g: GizmoData):
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
    starts = np.empty((segs+1, 3), dtype=np.float32); ends = np.empty((segs+1, 3), dtype=np.float32)
    starts[0] = arc[0]; ends[0] = arc[-1]
    starts[1:] = arc[:-1]; ends[1:] = arc[1:]
    return starts, ends, _np_color(g.color, segs+1)


@_register(GizmoType.HEMISPHERE)
def _build_hemisphere(g: GizmoData):
    p = g.position; n = g.normal; r = g.size; segs = max(g.segments // 2, 4)
    nv = Vec3(n[0], n[1], n[2])
    p1 = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(p1).normalized()
    p2 = nv.cross(p1).normalized()
    lats = np.linspace(0, math.pi*0.5, segs+1, dtype=np.float32)
    lons = np.linspace(0, 2.0*math.pi, segs+1, dtype=np.float32)
    verts = np.empty(((segs+1)*(segs+1), 3), dtype=np.float32)
    idx = 0
    for li in range(segs+1):
        la = lats[li]; cl = math.cos(la)*r; sl = math.sin(la)*r
        for lj in range(segs+1):
            lo = lons[lj]
            x = p1.x*cl*math.cos(lo) + p2.x*cl*math.sin(lo) + n[0]*sl
            y = p1.y*cl*math.cos(lo) + p2.y*cl*math.sin(lo) + n[1]*sl
            z = p1.z*cl*math.cos(lo) + p2.z*cl*math.sin(lo) + n[2]*sl
            verts[idx] = [p[0]+x, p[1]+y, p[2]+z]; idx += 1
    nv = segs+1
    lines_buf = []
    for li in range(segs):
        for lj in range(segs):
            i0=li*nv+lj; i1=li*nv+lj+1; i2=(li+1)*nv+lj; i3=(li+1)*nv+lj+1
            lines_buf.extend([i0,i1, i1,i2, i2,i3, i3,i0])
    lidx = np.array(lines_buf)
    return verts[lidx[0::2]], verts[lidx[1::2]], _np_color(g.color, len(lidx)//2)


@_register(GizmoType.PYRAMID)
def _build_pyramid(g: GizmoData):
    p = g.position; n = g.normal; r = g.size; h = g.height if g.height > 0 else r
    segs = max(g.segments, 4)
    nv = Vec3(n[0], n[1], n[2])
    ref = Vec3(1,0,0) if abs(n[1])<0.9 else Vec3(0,0,1)
    p1 = nv.cross(ref).normalized()
    p2 = nv.cross(p1).normalized()
    tip = np.array([p[0]+n[0]*h, p[1]+n[1]*h, p[2]+n[2]*h], dtype=np.float32)
    theta = np.linspace(0, 2.0*math.pi, segs+1, dtype=np.float32)[:-1]
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    base = np.empty((segs, 3), dtype=np.float32)
    base[:, 0] = p[0] + p1.x*ct + p2.x*st
    base[:, 1] = p[1] + p1.y*ct + p2.y*st
    base[:, 2] = p[2] + p1.z*ct + p2.z*st
    total = segs * 2
    starts = np.empty((total, 3), dtype=np.float32); ends = np.empty((total, 3), dtype=np.float32)
    for i in range(segs):
        j = (i+1)%segs
        starts[i] = base[i]; ends[i] = base[j]
        starts[segs+i] = base[i]; ends[segs+i] = tip
    return starts, ends, _np_color(g.color, total)


class GizmosManager(_DrawMixin, _CollectMixin):
    def __init__(self):
        self._lock = threading.Lock()
        self.draws: List[GizmoData] = []
        self.persistent_draws: List[GizmoData] = []
        self.unique_draws: Dict[str, GizmoData] = {}
        self.used_unique_keys: set = set()
        self.enabled: bool = True
        self.show_in_runtime: bool = True
        self._time: float = 0.0
        self._batches: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self._flat_starts = np.empty((0, 3), dtype=np.float32)
        self._flat_ends = np.empty((0, 3), dtype=np.float32)
        self._flat_colors = np.empty((0, 4), dtype=np.float32)
        self._flat_size = 0
        self._transform_stack: List[Optional[List[float]]] = []
        self._current_transform: Optional[List[float]] = None
        self._style_stack: List[dict] = []
        self._current_style: Optional[dict] = None
        self._revision: int = 0
        self._cached_revision: int = -1
        self._label_count: int = 0
        self._icon_count: int = 0
        self._cache_starts: Optional[np.ndarray] = None
        self._cache_ends: Optional[np.ndarray] = None
        self._cache_colors: Optional[np.ndarray] = None
    def _resolve_style(self) -> dict:
        return dict(self._current_style) if self._current_style else {}
    def push_style(self, **kwargs):
        self._style_stack.append(self._current_style)
        base = dict(self._current_style) if self._current_style else {}
        base.update(kwargs)
        self._current_style = base
    def pop_style(self):
        if self._style_stack:
            self._current_style = self._style_stack.pop()
    def style(self, **kwargs):
        return _GizmoStyleCtx(self, kwargs)
    def update(self, dt: float):
        with self._lock:
            self._time += dt
            if not self.unique_draws and not self.used_unique_keys:
                return
            old_unique = len(self.unique_draws)
            for key in set(self.unique_draws.keys()) - self.used_unique_keys:
                del self.unique_draws[key]
            if len(self.unique_draws) != old_unique:
                self._revision += 1
            self.used_unique_keys.clear()
    def _clear_internal(self):
        self.persistent_draws.clear()
        self.draws.clear()
        self._batches.clear()
        self._flat_size = 0
        self._label_count = 0
        self._icon_count = 0
    def clear(self):
        with self._lock:
            self._clear_internal()
            self._revision += 1
            self._clear_cache()
    def toggle(self, visible: bool = None):
        with self._lock:
            if visible is not None:
                self.enabled = visible
            else:
                self.enabled = not self.enabled
    def clear_persistent(self):
        with self._lock:
            self.persistent_draws.clear()
            self._label_count = 0
            self._icon_count = 0
            self._revision += 1
    def clear_unique(self):
        with self._lock:
            self.unique_draws.clear()
            self._revision += 1
    def clear_tag(self, tag: str):
        with self._lock:
            old = len(self.persistent_draws)
            kept = [g for g in self.persistent_draws if g.tag != tag]
            if len(kept) != old:
                lc = 0
                ic = 0
                for g in kept:
                    if g.gizmo_type == GizmoType.LABEL:
                        lc += 1
                    elif g.gizmo_type == GizmoType.ICON:
                        ic += 1
                self.persistent_draws[:] = kept
                self._label_count = lc
                self._icon_count = ic
                self._revision += 1
    def _add(self, g: GizmoData, **style_kw):
        s = self._resolve_style()
        s.update(style_kw)
        for k, v in s.items():
            if v is None:
                continue
            if k == 'color':
                g.color = self._resolve_color(v)
            elif hasattr(g, k):
                setattr(g, k, v)
        with self._lock:
            self.persistent_draws.append(g)
            if g.gizmo_type == GizmoType.LABEL:
                self._label_count += 1
            elif g.gizmo_type == GizmoType.ICON:
                self._icon_count += 1
            self._revision += 1
    def _resolve_color(self, color) -> Tuple[float, float, float, float]:
        if isinstance(color, str):
            named = {
                'red': (1,0,0,1), 'green': (0,1,0,1), 'blue': (0,0,1,1),
                'white': (1,1,1,1), 'black': (0,0,0,1), 'yellow': (1,1,0,1),
                'cyan': (0,1,1,1), 'magenta': (1,0,1,1), 'gray': (0.5,0.5,0.5,1),
                'orange': (1,0.65,0,1), 'purple': (0.5,0,0.5,1),
                'pink': (1,0.41,0.71,1), 'brown': (0.65,0.16,0.16,1),
                'lime': (0,1,0,1), 'teal': (0,0.5,0.5,1), 'navy': (0,0,0.5,1),
                'maroon': (0.5,0,0,1), 'olive': (0.5,0.5,0,1), 'coral': (1,0.5,0.31,1),
                'gold': (1,0.84,0,1), 'silver': (0.75,0.75,0.75,1),
            }
            return named.get(color.lower(), (1,1,1,1))
        c = tuple(color)
        if len(c) == 3:
            return c + (1.0,)
        return c
    def _resolve_pos(self, pos) -> Tuple[float, float, float]:
        if isinstance(pos, Vec3):
            return (pos.x, pos.y, pos.z)
        return tuple(pos)
    def set_transform(self, position=None, rotation=None, scale=None):
        m = []
        if position:
            m.extend(self._resolve_pos(position))
        else:
            m.extend([0,0,0])
        if rotation:
            if isinstance(rotation, (tuple, list)) and len(rotation) == 4:
                m.extend(rotation)
            elif hasattr(rotation, 'x') and hasattr(rotation, 'y') and hasattr(rotation, 'z') and hasattr(rotation, 'w'):
                m.extend([rotation.x, rotation.y, rotation.z, rotation.w])
            else:
                m.extend([0,0,0,1])
        else:
            m.extend([0,0,0,1])
        if scale:
            m.extend(self._resolve_pos(scale))
        else:
            m.extend([1,1,1])
        self._current_transform = m
    def reset_transform(self):
        self._current_transform = None
    def push_transform(self, position=None, rotation=None, scale=None):
        self._transform_stack.append(self._current_transform)
        self.set_transform(position, rotation, scale)
    def pop_transform(self):
        if self._transform_stack:
            self._current_transform = self._transform_stack.pop()
    def apply_rotation(self, rot):
        if isinstance(rot, (tuple, list)):
            self._current_transform = self._current_transform or [0,0,0,0,0,1,1,1,1]
            self._current_transform[3:7] = rot
        elif hasattr(rot, 'x'):
            self._current_transform = self._current_transform or [0,0,0,0,0,1,1,1,1]
            self._current_transform[3:7] = [rot.x, rot.y, rot.z, rot.w]
    def _apply_transform(self, g: GizmoData) -> GizmoData:
        t = self._current_transform
        if t is None:
            return g
        if len(t) >= 7:
            g.rotation = tuple(t[3:7])
        return g
    def _draw_gizmo(self, gizmo_type, position=None, end_position=None, color='white',
                    size=1.0, thickness=1.0, duration=0.0, layer=0, world_space=True,
                    **kw):
        g = self._apply_transform(GizmoData(gizmo_type=gizmo_type,
            position=self._resolve_pos(position) if position is not None else (0,0,0),
            color=self._resolve_color(color), size=size, thickness=thickness,
            duration=duration, layer=layer, world_space=world_space, **kw))
        if end_position is not None:
            g.end_position = self._resolve_pos(end_position)
        self._add(g)
    @staticmethod
    def color_rgb(r: float, g: float, b: float, a: float = 1.0) -> Tuple[float, float, float, float]:
        return (r, g, b, a)
    @staticmethod
    def color_hex(hex_str: str) -> Tuple[float, float, float, float]:
        h = hex_str.lstrip(chr(35))
        if len(h) == 6:
            r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
            return (r, g, b, 1.0)
        elif len(h) == 8:
            r, g, b, a = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255, int(h[6:8],16)/255
            return (r, g, b, a)
        return (1,1,1,1)
    @staticmethod
    def color_lerp(c1, c2, t: float) -> Tuple[float, float, float, float]:
        c1 = list(c1); c2 = list(c2)
        while len(c1) < 4: c1.append(1.0)
        while len(c2) < 4: c2.append(1.0)
        t = max(0, min(1, t))
        return tuple(a + (b-a)*t for a, b in zip(c1, c2))
    @staticmethod
    def color_random(alpha: float = 1.0) -> Tuple[float, float, float, float]:
        return (random.random(), random.random(), random.random(), alpha)
    @staticmethod
    def color_hsv(h: float, s: float, v: float, a: float = 1.0) -> Tuple[float, float, float, float]:
        h = h % 360
        c = v * s
        x = c * (1 - abs((h/60) % 2 - 1))
        m = v - c
        if h < 60: r,g,b=c,x,0
        elif h < 120: r,g,b=x,c,0
        elif h < 180: r,g,b=0,c,x
        elif h < 240: r,g,b=0,x,c
        elif h < 300: r,g,b=x,0,c
        else: r,g,b=c,0,x
        return (r+m, g+m, b+m, a)
