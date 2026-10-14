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
class GizmoStar(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "outer_radius", "inner_radius", "color", "thickness", "show_in_play", "points", "normal")
    _gizmo_icon_color = (255, 215, 0)
    _gizmo_icon_label = "St"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Star", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("outer_radius", "Outer", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("inner_radius", "Inner", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("points", "Points", FieldType.INT, min_val=3, max_val=12),
            InspectorField("normal", "Normal", FieldType.VEC3),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.outer_radius = 1.0
        self.inner_radius = 0.4
        self.color = Vec4(1, 0.85, 0.0, 1.0)
        self.thickness = 1.0
        self.show_in_play = True
        self.points = 5
        self.normal = Vec3(0, 1, 0)
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "outer_radius": self.outer_radius, "inner_radius": self.inner_radius, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "points": self.points, "normal": _v3t(self.normal)})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.outer_radius = data.get("outer_radius", 1.0)
        inst.inner_radius = data.get("inner_radius", 0.4)
        inst.color = Vec4(*data.get("color", [1, 0.85, 0.0, 1.0]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.points = data.get("points", 5)
        inst.normal = Vec3(*data.get("normal", [0, 1, 0]))
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.STAR, _v3t(self.center), (*_v4t(self.color),),
                               size=self.outer_radius, inner_radius=self.inner_radius, normal=(*_v3t(self.normal),), segments=self.points, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoIcon(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "icon", "color", "size", "thickness", "show_in_play")
    _gizmo_icon_color = (100, 100, 100)
    _gizmo_icon_label = "Ic"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Icon", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("icon", "Icon", FieldType.STRING),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("size", "Size", FieldType.FLOAT, min_val=0.1, max_val=5.0),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.icon = "star"
        self.color = Vec4(1, 1, 1, 1)
        self.thickness = 1.0
        self.show_in_play = True
        self.size = 1.0
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "icon": self.icon, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "size": self.size})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.icon = data.get("icon", "star")
        inst.color = Vec4(*data.get("color", [1, 1, 1, 1]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.size = data.get("size", 1.0)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.CROSS, _v3t(self.center), (*_v4t(self.color),),
                               size=self.size, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoLabel(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "text", "color", "font_size", "thickness", "show_in_play")
    _gizmo_icon_color = (200, 200, 200)
    _gizmo_icon_label = "Lb"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Label", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("text", "Text", FieldType.STRING),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("font_size", "Font Size", FieldType.INT, min_val=8, max_val=48),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3(0, 1, 0)
        self.text = "Label"
        self.color = Vec4(1, 1, 1, 1)
        self.thickness = 1.0
        self.show_in_play = True
        self.font_size = 14
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "text": self.text, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "font_size": self.font_size})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 1, 0]))
        inst.text = data.get("text", "Label")
        inst.color = Vec4(*data.get("color", [1, 1, 1, 1]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.font_size = data.get("font_size", 14)
        return inst
    def gizmo_primitives(self):
        return None
