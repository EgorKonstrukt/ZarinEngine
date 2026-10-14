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
class GizmoArc(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "radius", "color", "thickness", "show_in_play", "normal", "angle_start", "angle_end")
    _gizmo_icon_color = (220, 100, 100)
    _gizmo_icon_label = "Arc"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Arc", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("normal", "Normal", FieldType.VEC3),
            InspectorField("", "Angle", FieldType.HEADER),
            InspectorField("angle_start", "Angle Start", FieldType.FLOAT, min_val=0.0, max_val=360.0),
            InspectorField("angle_end", "Angle End", FieldType.FLOAT, min_val=0.0, max_val=360.0),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.radius = 1.0
        self.color = Vec4(1, 0.4, 0.4, 1.0)
        self.thickness = 1.0
        self.show_in_play = True
        self.normal = Vec3(0, 1, 0)
        self.angle_start = 0.0
        self.angle_end = 90.0
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "radius": self.radius, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "normal": _v3t(self.normal), "angle_start": self.angle_start, "angle_end": self.angle_end})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.radius = data.get("radius", 1.0)
        inst.color = Vec4(*data.get("color", [1, 0.4, 0.4, 1.0]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.normal = Vec3(*data.get("normal", [0, 1, 0]))
        inst.angle_start = data.get("angle_start", 0.0)
        inst.angle_end = data.get("angle_end", 90.0)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.ARC, _v3t(self.center), (*_v4t(self.color),),
                               normal=(*_v3t(self.normal),), size=self.radius, angle_start=self.angle_start, angle_end=self.angle_end, segments=32, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoTorus(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "major_radius", "minor_radius", "color", "thickness", "show_in_play", "segments", "normal")
    _gizmo_icon_color = (150, 100, 220)
    _gizmo_icon_label = "T"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Torus", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("major_radius", "Major Radius", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("minor_radius", "Minor Radius", FieldType.FLOAT, min_val=0.01, max_val=5.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("segments", "Segments", FieldType.INT, min_val=8, max_val=64),
            InspectorField("normal", "Normal", FieldType.VEC3),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.major_radius = 1.0
        self.minor_radius = 0.2
        self.color = Vec4(0.8, 0.4, 1.0, 0.8)
        self.thickness = 1.0
        self.show_in_play = True
        self.segments = 24
        self.normal = Vec3(0, 1, 0)
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "major_radius": self.major_radius, "minor_radius": self.minor_radius, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "segments": self.segments, "normal": _v3t(self.normal)})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.major_radius = data.get("major_radius", 1.0)
        inst.minor_radius = data.get("minor_radius", 0.2)
        inst.color = Vec4(*data.get("color", [0.8, 0.4, 1.0, 0.8]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.segments = data.get("segments", 24)
        inst.normal = Vec3(*data.get("normal", [0, 1, 0]))
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.TORUS, _v3t(self.center), (*_v4t(self.color),),
                               size=self.major_radius, inner_radius=self.minor_radius, normal=(*_v3t(self.normal),), segments=self.segments, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoCross(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "size", "color", "thickness", "show_in_play")
    _gizmo_icon_color = (200, 50, 50)
    _gizmo_icon_label = "X"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Cross", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("size", "Size", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.size = 1.0
        self.color = Vec4(1, 0.2, 0.2, 1.0)
        self.thickness = 1.0
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
        inst.size = data.get("size", 1.0)
        inst.color = Vec4(*data.get("color", [1, 0.2, 0.2, 1.0]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
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
