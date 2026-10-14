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
class GizmoPlane(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "normal", "size", "color", "thickness", "show_in_play")
    _gizmo_icon_color = (150, 150, 150)
    _gizmo_icon_label = "PL"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Plane", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("normal", "Normal", FieldType.VEC3),
            InspectorField("size", "Size", FieldType.FLOAT, min_val=0.1, max_val=100.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.normal = Vec3(0, 1, 0)
        self.size = 5.0
        self.color = Vec4(0.8, 0.8, 0.8, 0.4)
        self.thickness = 1.0
        self.show_in_play = True
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "normal": _v3t(self.normal), "size": self.size, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.normal = Vec3(*data.get("normal", [0, 1, 0]))
        inst.size = data.get("size", 5.0)
        inst.color = Vec4(*data.get("color", [0.8, 0.8, 0.8, 0.4]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.GRID, _v3t(self.center), (*_v4t(self.color),),
                               normal=(*_v3t(self.normal),), size=self.size, segments=10, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoGrid(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "size", "divisions", "color", "thickness", "show_in_play", "normal")
    _gizmo_icon_color = (180, 180, 180)
    _gizmo_icon_label = "G"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Grid", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("size", "Size", FieldType.FLOAT, min_val=1.0, max_val=100.0),
            InspectorField("divisions", "Divisions", FieldType.INT, min_val=2, max_val=50),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("normal", "Normal", FieldType.VEC3),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.size = 10.0
        self.divisions = 10
        self.color = Vec4(0.5, 0.5, 0.5, 0.3)
        self.thickness = 1.0
        self.show_in_play = True
        self.normal = Vec3(0, 1, 0)
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "size": self.size, "divisions": self.divisions, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "normal": _v3t(self.normal)})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.size = data.get("size", 10.0)
        inst.divisions = data.get("divisions", 10)
        inst.color = Vec4(*data.get("color", [0.5, 0.5, 0.5, 0.3]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.normal = Vec3(*data.get("normal", [0, 1, 0]))
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.GRID, _v3t(self.center), (*_v4t(self.color),),
                               normal=(*_v3t(self.normal),), size=self.size, segments=self.divisions, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoCircle(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "radius", "color", "thickness", "show_in_play", "normal", "segments")
    _gizmo_icon_color = (220, 180, 50)
    _gizmo_icon_label = "O"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Circle", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("normal", "Normal", FieldType.VEC3),
            InspectorField("segments", "Segments", FieldType.INT, min_val=8, max_val=64),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.radius = 1.0
        self.color = Vec4(1, 0.8, 0.2, 1.0)
        self.thickness = 1.0
        self.show_in_play = True
        self.normal = Vec3(0, 1, 0)
        self.segments = 32
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "radius": self.radius, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "normal": _v3t(self.normal), "segments": self.segments})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.radius = data.get("radius", 1.0)
        inst.color = Vec4(*data.get("color", [1, 0.8, 0.2, 1.0]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.normal = Vec3(*data.get("normal", [0, 1, 0]))
        inst.segments = data.get("segments", 32)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.CIRCLE, _v3t(self.center), (*_v4t(self.color),),
                               normal=(*_v3t(self.normal),), size=self.radius, segments=self.segments, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoDisc(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "radius", "color", "thickness", "show_in_play", "normal")
    _gizmo_icon_color = (220, 180, 50)
    _gizmo_icon_label = "D"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Disc", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("normal", "Normal", FieldType.VEC3),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.radius = 1.0
        self.color = Vec4(1, 0.8, 0.2, 0.4)
        self.thickness = 1.0
        self.show_in_play = True
        self.normal = Vec3(0, 1, 0)
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "radius": self.radius, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "normal": _v3t(self.normal)})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.radius = data.get("radius", 1.0)
        inst.color = Vec4(*data.get("color", [1, 0.8, 0.2, 0.4]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.normal = Vec3(*data.get("normal", [0, 1, 0]))
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.CIRCLE, _v3t(self.center), (*_v4t(self.color),),
                               normal=(*_v3t(self.normal),), size=self.radius, segments=32, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)
