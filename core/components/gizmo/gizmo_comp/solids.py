# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.ecs import Component, ComponentRegistry, InstancePrimitive
from core.maths.math3d import Vec3, Vec4
from core.components.inspector_meta import FieldType, InspectorField, ListElementField
from core.gizmo.apiv import GizmoType, LineStyle
from .base import _apply_world, _box_instance, _build_primitive, _dash_animated, _gizmo_visible, _sig_points, _sphere_at, _sphere_instance, _v3, _v3t, _v4t, _wm


@ComponentRegistry.register
class GizmoCube(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "size", "color", "thickness", "show_in_play", "wireframe", "rotation")
    _gizmo_icon_color = (50, 150, 250)
    _gizmo_icon_label = "C"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Cube", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("size", "Size", FieldType.VEC3),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("wireframe", "Wireframe", FieldType.BOOL),
            InspectorField("rotation", "Rotation", FieldType.VEC3),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.size = Vec3.one()
        self.color = Vec4(0.2, 0.6, 1.0, 0.6)
        self.thickness = 1.0
        self.show_in_play = True
        self.wireframe = True
        self.rotation = Vec3.zero()
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "size": _v3t(self.size), "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "wireframe": self.wireframe, "rotation": _v3t(self.rotation)})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.size = Vec3(*data.get("size", [1, 1, 1]))
        inst.color = Vec4(*data.get("color", [0.2, 0.6, 1.0, 0.6]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.wireframe = data.get("wireframe", True)
        inst.rotation = Vec3(*data.get("rotation", [0, 0, 0]))
        return inst
    def gizmo_instance_data(self):
        if self.wireframe or not _gizmo_visible(self):
            return None
        tr = self.transform
        if not tr:
            return None
        return InstancePrimitive('box', _box_instance(self.center, self.size, tr).ravel('F'), [*_v4t(self.color)])
    def gizmo_primitives(self):
        if not self.wireframe or not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.BOX, _v3t(self.center), (*_v4t(self.color),),
                               size=(*_v3t(self.size),), rotation=(*_v3t(self.rotation),), thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoSphere(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "radius", "color", "thickness", "show_in_play", "wireframe", "segments")
    _gizmo_icon_color = (250, 150, 50)
    _gizmo_icon_label = "S"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Sphere", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("wireframe", "Wireframe", FieldType.BOOL),
            InspectorField("segments", "Segments", FieldType.INT, min_val=4, max_val=64),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.radius = 0.5
        self.color = Vec4(1.0, 0.6, 0.2, 0.6)
        self.thickness = 1.0
        self.show_in_play = True
        self.wireframe = True
        self.segments = 16
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "radius": self.radius, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "wireframe": self.wireframe, "segments": self.segments})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.radius = data.get("radius", 0.5)
        inst.color = Vec4(*data.get("color", [1, 0.6, 0.2, 0.6]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.wireframe = data.get("wireframe", True)
        inst.segments = data.get("segments", 16)
        return inst
    def gizmo_instance_data(self):
        if self.wireframe or not _gizmo_visible(self):
            return None
        tr = self.transform
        if not tr:
            return None
        return InstancePrimitive('sphere', _sphere_instance(self.center, self.radius, tr).ravel('F'), [*_v4t(self.color)])
    def gizmo_primitives(self):
        if not self.wireframe or not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.SPHERE, _v3t(self.center), (*_v4t(self.color),),
                               size=self.radius, segments=self.segments, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoCylinder(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "radius", "height", "color", "thickness", "show_in_play", "segments", "direction")
    _gizmo_icon_color = (100, 200, 100)
    _gizmo_icon_label = "Y"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Cylinder", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("segments", "Segments", FieldType.INT, min_val=4, max_val=64),
            InspectorField("direction", "Direction", FieldType.VEC3),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.radius = 0.5
        self.height = 1.0
        self.color = Vec4(0.5, 1.0, 0.5, 0.6)
        self.thickness = 1.0
        self.show_in_play = True
        self.segments = 16
        self.direction = Vec3(0, 1, 0)
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "radius": self.radius, "height": self.height, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "segments": self.segments, "direction": _v3t(self.direction)})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.radius = data.get("radius", 0.5)
        inst.height = data.get("height", 1.0)
        inst.color = Vec4(*data.get("color", [0.5, 1, 0.5, 0.6]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.segments = data.get("segments", 16)
        inst.direction = Vec3(*data.get("direction", [0, 1, 0]))
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.CYLINDER, _v3t(self.center), (*_v4t(self.color),),
                               size=self.radius, height=self.height, normal=(*_v3t(self.direction),), segments=self.segments, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoCone(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "radius", "height", "color", "thickness", "show_in_play", "direction")
    _gizmo_icon_color = (250, 200, 100)
    _gizmo_icon_label = "Co"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Cone", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("direction", "Direction", FieldType.VEC3),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.radius = 0.5
        self.height = 1.0
        self.color = Vec4(1, 0.8, 0.3, 0.8)
        self.thickness = 1.0
        self.show_in_play = True
        self.direction = Vec3(0, 1, 0)
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "radius": self.radius, "height": self.height, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "direction": _v3t(self.direction)})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.radius = data.get("radius", 0.5)
        inst.height = data.get("height", 1.0)
        inst.color = Vec4(*data.get("color", [1, 0.8, 0.3, 0.8]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.direction = Vec3(*data.get("direction", [0, 1, 0]))
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.CONE, _v3t(self.center), (*_v4t(self.color),),
                               normal=(*_v3t(self.direction),), size=self.radius, height=self.height, segments=16, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)
