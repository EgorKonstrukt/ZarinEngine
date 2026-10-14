# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.maths.math3d import Vec3, Vec4
from core.components.inspector_meta import FieldType, InspectorField, ListElementField
from core.gizmo.apiv import GizmoType, LineStyle
from .base import _apply_world, _box_instance, _build_primitive, _dash_animated, _gizmo_visible, _sig_points, _sphere_at, _sphere_instance, _v3, _v3t, _v4t, _wm


@ComponentRegistry.register
class GizmoPoint(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "size", "color", "thickness", "show_in_play")
    _gizmo_icon_color = (250, 250, 50)
    _gizmo_icon_label = "P"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Point", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("size", "Size", FieldType.FLOAT, min_val=0.01, max_val=5.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.size = 0.1
        self.color = Vec4(1, 1, 0, 1)
        self.thickness = 3.0
        self.show_in_play = True
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "size": self.size, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.size = data.get("size", 0.1)
        inst.color = Vec4(*data.get("color", [1, 1, 0, 1]))
        inst.thickness = data.get("thickness", 3.0)
        inst.show_in_play = data.get("show_in_play", True)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.CROSS, _v3t(self.center), (*_v4t(self.color),),
                               size=self.size * 2.0, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoPoly(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("color", "thickness", "show_in_play", "closed", "points")
    _gizmo_icon_color = (100, 200, 200)
    _gizmo_icon_label = "Poly"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Poly", FieldType.HEADER),
            InspectorField("points", "Points", FieldType.LIST, element_fields=[ListElementField("point", "Point", FieldType.VEC3)]),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("closed", "Closed", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.points = [Vec3(-1, 0, 0), Vec3(0, 1, 0), Vec3(1, 0, 0)]
        self.color = Vec4(0.5, 0.8, 1.0, 1.0)
        self.thickness = 1.0
        self.show_in_play = True
        self.closed = True
    def serialize(self):
        d = super().serialize()
        d.update({"points": [_v3t(p) for p in self.points], "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "closed": self.closed})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.points = [Vec3(*p) for p in data.get("points", [[-1, 0, 0], [0, 1, 0], [1, 0, 0]])]
        inst.color = Vec4(*data.get("color", [0.5, 0.8, 1.0, 1.0]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.closed = data.get("closed", True)
        return inst
    def gizmo_cache_sig(self):
        tr = self.transform
        if tr is None:
            return None
        try:
            return (tr.world_matrix._d.tobytes(), _sig_points(self.points), tuple(_v4t(self.color)), self.thickness, self.closed)
        except Exception:
            return None
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        pts = [_v3t(p) for p in self.points]
        res = _build_primitive(GizmoType.POLY, (0, 0, 0), (*_v4t(self.color),),
                               points=pts, filled=not self.closed, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoBezier(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("points", "color", "thickness", "show_in_play", "segments")
    _gizmo_icon_color = (180, 100, 220)
    _gizmo_icon_label = "Bz"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Bezier", FieldType.HEADER),
            InspectorField("points", "Points", FieldType.LIST, element_fields=[ListElementField("point", "Point", FieldType.VEC3)]),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("segments", "Segments", FieldType.INT, min_val=4, max_val=64),
        ]
    def __init__(self):
        super().__init__()
        self.points = [Vec3(-1, 0, 0), Vec3(-0.5, 1, 0), Vec3(0.5, 1, 0), Vec3(1, 0, 0)]
        self.color = Vec4(0.8, 0.5, 1.0, 1.0)
        self.thickness = 1.0
        self.show_in_play = True
        self.segments = 20
    def serialize(self):
        d = super().serialize()
        d.update({"points": [_v3t(p) for p in self.points], "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "segments": self.segments})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        if "points" in data:
            pts = data.get("points", [])
        else:
            pts = []
            for key in ("p0", "p1", "p2", "p3"):
                if key in data:
                    pts.append(data[key])
            if not pts:
                pts = [[-1, 0, 0], [-0.5, 1, 0], [0.5, 1, 0], [1, 0, 0]]
        inst.points = [Vec3(*p) for p in pts]
        inst.color = Vec4(*data.get("color", [0.8, 0.5, 1.0, 1.0]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.segments = data.get("segments", 20)
        return inst
    def gizmo_cache_sig(self):
        tr = self.transform
        if tr is None:
            return None
        try:
            return (tr.world_matrix._d.tobytes(), _sig_points(self.points), tuple(_v4t(self.color)), self.thickness, self.segments)
        except Exception:
            return None
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        pts = [_v3t(p) for p in self.points]
        res = _build_primitive(GizmoType.BEZIER, (0, 0, 0), (*_v4t(self.color),),
                               points=pts, segments=self.segments, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)
