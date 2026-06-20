from __future__ import annotations
import math
import numpy as np
from enum import Enum
from typing import Optional, List, Tuple, Dict, Callable, Any
from dataclasses import dataclass, field
from core.math3d import Vec3, Mat4

class GizmoType(Enum):
    POINT = "point"
    LINE = "line"
    CIRCLE = "circle"
    SPHERE = "sphere"
    BOX = "box"
    ARC = "arc"
    CAPSULE = "capsule"
    GRID = "grid"
    CONE = "cone"
    AXIS = "axis"
    TEXT = "text"
    RING = "ring"
    ARROW = "arrow"
    CROSS = "cross"
    DASHED = "dashed"
    BEZIER = "bezier"
    TRIANGLE = "triangle"
    POLY = "poly"

@dataclass
class GizmoData:
    gizmo_type: GizmoType
    position: Tuple[float, float, float]
    color: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    size: float = 1.0
    duration: float = 0.0
    layer: int = 0
    world_space: bool = True
    thickness: float = 1.0
    filled: bool = False
    alpha: float = 1.0
    text: str = ""
    end_position: Optional[Tuple[float, float, float]] = None
    normal: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    angle_start: float = 0.0
    angle_end: float = 360.0
    segments: int = 32
    inner_radius: float = 0.0
    points: Optional[List[Tuple[float, float, float]]] = None
    up: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    dash_length: float = 0.3
    gap_length: float = 0.15
    font_size: int = 14
    cull_distance: float = -1.0
    on_click: Optional[Callable] = None
    unique_id: Optional[str] = None
    _screen_pos: Optional[Tuple[int, int]] = None

class GizmosManager:
    def __init__(self):
        self.draws: List[GizmoData] = []
        self.persistent_draws: List[GizmoData] = []
        self.unique_draws: Dict[str, GizmoData] = {}
        self.used_unique_keys: set = set()
        self.enabled: bool = True
        self._time: float = 0.0
        self._batches: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []

    def update(self, dt: float):
        self._time += dt
        self.draws = [g for g in self.draws if g.duration <= 0 or self._time - g.duration < 1.0]
        for key in set(self.unique_draws.keys()) - self.used_unique_keys:
            del self.unique_draws[key]
        self.used_unique_keys.clear()

    def clear(self):
        self.draws.clear()
        self._batches.clear()

    def clear_persistent(self):
        self.persistent_draws.clear()

    def clear_unique(self):
        self.unique_draws.clear()

    def draw_lines(self, starts: np.ndarray, ends: np.ndarray, colors: np.ndarray):
        self._batches.append((starts, ends, colors))

    def _get_render_data(self):
        if not self._batches:
            return None
        s_list = [b[0] for b in self._batches]
        e_list = [b[1] for b in self._batches]
        c_list = [b[2] for b in self._batches]
        return (np.concatenate(s_list), np.concatenate(e_list), np.concatenate(c_list))

    def _add(self, g: GizmoData):
        if g.duration < 0:
            self.persistent_draws.append(g)
        else:
            self.draws.append(g)

    def _resolve_color(self, color) -> Tuple[float, float, float, float]:
        if isinstance(color, str):
            named = {
                'red': (1,0,0,1), 'green': (0,1,0,1), 'blue': (0,0,1,1),
                'white': (1,1,1,1), 'black': (0,0,0,1), 'yellow': (1,1,0,1),
                'cyan': (0,1,1,1), 'magenta': (1,0,1,1), 'gray': (0.5,0.5,0.5,1),
                'orange': (1,0.65,0,1), 'purple': (0.5,0,0.5,1),
            }
            return named.get(color, (1,1,1,1))
        c = tuple(color)
        if len(c) == 3:
            return c + (1.0,)
        return c

    def _resolve_pos(self, pos) -> Tuple[float, float, float]:
        if isinstance(pos, Vec3):
            return (pos.x, pos.y, pos.z)
        return tuple(pos)

    def draw_point(self, position, color='white', size=3.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.POINT, position=self._resolve_pos(position),
            color=self._resolve_color(color), size=size, duration=duration,
            layer=layer, world_space=world_space, cull_distance=cull_distance))

    def draw_line(self, start, end, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.LINE, position=self._resolve_pos(start),
            end_position=self._resolve_pos(end), color=self._resolve_color(color),
            thickness=thickness, duration=duration, layer=layer,
            world_space=world_space, cull_distance=cull_distance))

    def draw_circle(self, center, normal=(0,1,0), radius=1.0, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.CIRCLE, position=self._resolve_pos(center),
            normal=self._resolve_pos(normal), size=radius, color=self._resolve_color(color),
            filled=filled, thickness=thickness, duration=duration, layer=layer,
            world_space=world_space, cull_distance=cull_distance))

    def draw_sphere(self, center, radius=1.0, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.SPHERE, position=self._resolve_pos(center),
            size=radius, color=self._resolve_color(color), filled=filled,
            thickness=thickness, duration=duration, layer=layer,
            world_space=world_space, cull_distance=cull_distance))

    def draw_box(self, center, size=(1,1,1), color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.BOX, position=self._resolve_pos(center),
            size=size, color=self._resolve_color(color), filled=filled,
            thickness=thickness, duration=duration, layer=layer,
            world_space=world_space, cull_distance=cull_distance))

    def draw_arc(self, center, normal=(0,1,0), radius=1.0, angle_start=0.0, angle_end=360.0, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.ARC, position=self._resolve_pos(center),
            normal=self._resolve_pos(normal), size=radius, color=self._resolve_color(color),
            angle_start=angle_start, angle_end=angle_end, segments=segments,
            thickness=thickness, duration=duration, layer=layer,
            world_space=world_space, cull_distance=cull_distance))

    def draw_capsule(self, start, end, radius=0.5, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.CAPSULE, position=self._resolve_pos(start),
            end_position=self._resolve_pos(end), size=radius, color=self._resolve_color(color),
            thickness=thickness, duration=duration, layer=layer,
            world_space=world_space, cull_distance=cull_distance))

    def draw_grid(self, center, normal=(0,1,0), size=10.0, divisions=10, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.GRID, position=self._resolve_pos(center),
            normal=self._resolve_pos(normal), size=size, segments=divisions,
            color=self._resolve_color(color), thickness=thickness, duration=duration,
            layer=layer, world_space=world_space, cull_distance=cull_distance))

    def draw_cone(self, center, direction=(0,1,0), height=1.0, base_radius=0.5, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.CONE, position=self._resolve_pos(center),
            normal=self._resolve_pos(direction), size=base_radius, segments=int(height*10),
            color=self._resolve_color(color), filled=filled, thickness=thickness,
            duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance))

    def draw_axis(self, origin, rotation=None, length=1.0, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True):
        self._add(GizmoData(gizmo_type=GizmoType.AXIS, position=self._resolve_pos(origin),
            normal=(0,0,1), size=length, color=self._resolve_color(color),
            thickness=thickness, duration=duration, layer=layer, world_space=world_space))

    def draw_text(self, position, text, color='white', font_size=14, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.TEXT, position=self._resolve_pos(position),
            text=text, color=self._resolve_color(color), font_size=font_size,
            duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance))

    def draw_ring(self, center, inner_radius=0.5, outer_radius=1.0, color='white', filled=False, thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.RING, position=self._resolve_pos(center),
            size=outer_radius, inner_radius=inner_radius, color=self._resolve_color(color),
            filled=filled, thickness=thickness, segments=segments, duration=duration,
            layer=layer, world_space=world_space, cull_distance=cull_distance))

    def draw_arrow(self, start, end, color='white', thickness=2.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.ARROW, position=self._resolve_pos(start),
            end_position=self._resolve_pos(end), color=self._resolve_color(color),
            thickness=thickness, duration=duration, layer=layer,
            world_space=world_space, cull_distance=cull_distance))

    def draw_cross(self, center, size=1.0, color='white', thickness=1.0, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.CROSS, position=self._resolve_pos(center),
            size=size, color=self._resolve_color(color), thickness=thickness,
            duration=duration, layer=layer, world_space=world_space))

    def draw_dashed_line(self, start, end, color='white', thickness=1.0, dash_length=0.3, gap_length=0.15, duration=0.0, layer=0, world_space=True, cull_distance=-1.0):
        self._add(GizmoData(gizmo_type=GizmoType.DASHED, position=self._resolve_pos(start),
            end_position=self._resolve_pos(end), color=self._resolve_color(color),
            thickness=thickness, dash_length=dash_length, gap_length=gap_length,
            duration=duration, layer=layer, world_space=world_space, cull_distance=cull_distance))

    def draw_bezier(self, points, color='white', thickness=1.0, segments=32, duration=0.0, layer=0, world_space=True):
        self._add(GizmoData(gizmo_type=GizmoType.BEZIER, position=self._resolve_pos(points[0]),
            points=[self._resolve_pos(p) for p in points], color=self._resolve_color(color),
            thickness=thickness, segments=segments, duration=duration,
            layer=layer, world_space=world_space))

    def draw_triangle(self, p0, p1, p2, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True):
        self._add(GizmoData(gizmo_type=GizmoType.TRIANGLE, position=self._resolve_pos(p0),
            points=[self._resolve_pos(p) for p in (p0, p1, p2)], color=self._resolve_color(color),
            filled=filled, thickness=thickness, duration=duration, layer=layer, world_space=world_space))

    def draw_poly(self, points, color='white', filled=False, thickness=1.0, duration=0.0, layer=0, world_space=True):
        pts = [self._resolve_pos(p) for p in points]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        self._add(GizmoData(gizmo_type=GizmoType.POLY, position=(cx,cy,cz),
            points=pts, color=self._resolve_color(color), filled=filled,
            thickness=thickness, duration=duration, layer=layer, world_space=world_space))

_gizmos_instance: Optional[GizmosManager] = None

def get_gizmos():
    return _gizmos_instance
def set_gizmos(gm):
    global _gizmos_instance
    _gizmos_instance = gm

class Gizmos:
    @staticmethod
    def draw_point(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_point(*a, **kw)
    @staticmethod
    def draw_line(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_line(*a, **kw)
    @staticmethod
    def draw_circle(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_circle(*a, **kw)
    @staticmethod
    def draw_sphere(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_sphere(*a, **kw)
    @staticmethod
    def draw_box(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_box(*a, **kw)
    @staticmethod
    def draw_arc(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_arc(*a, **kw)
    @staticmethod
    def draw_capsule(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_capsule(*a, **kw)
    @staticmethod
    def draw_grid(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_grid(*a, **kw)
    @staticmethod
    def draw_cone(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_cone(*a, **kw)
    @staticmethod
    def draw_axis(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_axis(*a, **kw)
    @staticmethod
    def draw_text(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_text(*a, **kw)
    @staticmethod
    def draw_ring(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_ring(*a, **kw)
    @staticmethod
    def draw_arrow(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_arrow(*a, **kw)
    @staticmethod
    def draw_cross(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_cross(*a, **kw)
    @staticmethod
    def draw_dashed_line(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_dashed_line(*a, **kw)
    @staticmethod
    def draw_bezier(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_bezier(*a, **kw)
    @staticmethod
    def draw_triangle(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_triangle(*a, **kw)
    @staticmethod
    def draw_poly(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_poly(*a, **kw)
    @staticmethod
    def draw_lines(*a, **kw):
        if _gizmos_instance: _gizmos_instance.draw_lines(*a, **kw)
    @staticmethod
    def clear():
        if _gizmos_instance: _gizmos_instance.clear()
    @staticmethod
    def clear_persistent():
        if _gizmos_instance: _gizmos_instance.clear_persistent()
    @staticmethod
    def toggle():
        if _gizmos_instance: _gizmos_instance.enabled = not _gizmos_instance.enabled
    @staticmethod
    def update(dt):
        if _gizmos_instance: _gizmos_instance.update(dt)
