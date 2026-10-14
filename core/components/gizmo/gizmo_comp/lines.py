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
class GizmoLine(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("start", "end", "color", "thickness", "show_in_play", "line_style")
    _gizmo_icon_color = (200, 200, 200)
    _gizmo_icon_label = "L"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("start", "Start", FieldType.VEC3),
            InspectorField("end", "End", FieldType.VEC3),
            InspectorField("", "Appearance", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("line_style", "Line Style", FieldType.ENUM, enum_class=LineStyle),
        ]
    def __init__(self):
        super().__init__()
        self.start = Vec3(-1, 0, 0)
        self.end = Vec3(1, 0, 0)
        self.color = Vec4(1, 1, 1, 1)
        self.thickness = 1.0
        self.show_in_play = True
        self.line_style = LineStyle.SOLID
    def serialize(self):
        d = super().serialize()
        d.update({
            "start": _v3t(self.start), "end": _v3t(self.end),
            "color": _v4t(self.color), "thickness": self.thickness,
            "show_in_play": self.show_in_play,
            "line_style": self.line_style.value if isinstance(self.line_style, LineStyle) else str(self.line_style),
        })
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.start = Vec3(*data.get("start", [-1, 0, 0]))
        inst.end = Vec3(*data.get("end", [1, 0, 0]))
        inst.color = Vec4(*data.get("color", [1, 1, 1, 1]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        try:
            inst.line_style = LineStyle(data.get("line_style", "solid"))
        except Exception:
            inst.line_style = LineStyle.SOLID
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.LINE, _v3t(self.start), (*_v4t(self.color),),
                               end_position=_v3t(self.end), thickness=self.thickness, line_style=self.line_style)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoRay(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("direction", "length", "color", "thickness", "show_in_play", "arrow_size")
    _gizmo_icon_color = (200, 200, 50)
    _gizmo_icon_label = "R"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("direction", "Direction", FieldType.VEC3),
            InspectorField("length", "Length", FieldType.FLOAT, min_val=0.1, max_val=100.0),
            InspectorField("", "Appearance", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("arrow_size", "Arrow Size", FieldType.FLOAT, min_val=0.0, max_val=1.0),
        ]
    def __init__(self):
        super().__init__()
        self.direction = Vec3(0, 1, 0)
        self.length = 2.0
        self.color = Vec4(1, 1, 0, 1)
        self.thickness = 1.0
        self.show_in_play = True
        self.arrow_size = 0.2
    def serialize(self):
        d = super().serialize()
        d.update({"direction": _v3t(self.direction), "length": self.length, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "arrow_size": self.arrow_size})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.direction = Vec3(*data.get("direction", [0, 1, 0]))
        inst.length = data.get("length", 2.0)
        inst.color = Vec4(*data.get("color", [1, 1, 0, 1]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.arrow_size = data.get("arrow_size", 0.2)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        d = _v3(self.direction).normalized()
        res = _build_primitive(GizmoType.RAY, (0, 0, 0), (*_v4t(self.color),),
                               normal=(d.x, d.y, d.z), size=self.length, arrow_size=self.arrow_size, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoArrow(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("start", "end", "color", "thickness", "show_in_play", "arrow_size")
    _gizmo_icon_color = (50, 200, 50)
    _gizmo_icon_label = "A"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("start", "Start", FieldType.VEC3),
            InspectorField("end", "End", FieldType.VEC3),
            InspectorField("", "Appearance", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("arrow_size", "Arrow Size", FieldType.FLOAT, min_val=0.0, max_val=1.0),
        ]
    def __init__(self):
        super().__init__()
        self.start = Vec3(0, 0, 0)
        self.end = Vec3(0, 2, 0)
        self.color = Vec4(0, 1, 0, 1)
        self.thickness = 1.0
        self.show_in_play = True
        self.arrow_size = 0.2
    def serialize(self):
        d = super().serialize()
        d.update({"start": _v3t(self.start), "end": _v3t(self.end), "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "arrow_size": self.arrow_size})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.start = Vec3(*data.get("start", [0, 0, 0]))
        inst.end = Vec3(*data.get("end", [0, 2, 0]))
        inst.color = Vec4(*data.get("color", [0, 1, 0, 1]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.arrow_size = data.get("arrow_size", 0.2)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.ARROW, _v3t(self.start), (*_v4t(self.color),),
                               end_position=_v3t(self.end), arrow_size=self.arrow_size, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)
