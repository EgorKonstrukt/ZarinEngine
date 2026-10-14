# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
import numpy as np
from core.ecs import Component, ComponentRegistry
from core.maths.math3d import Vec3, Vec4
from core.components.inspector_meta import FieldType, InspectorField, ListElementField
from core.gizmo.apiv import GizmoType, LineStyle
from .base import _apply_world, _box_instance, _build_primitive, _dash_animated, _gizmo_visible, _sig_points, _sphere_at, _sphere_instance, _v3, _v3t, _v4t, _wm


@ComponentRegistry.register
class GizmoCapsule(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "radius", "height", "color", "thickness", "show_in_play", "segments")
    _gizmo_icon_color = (100, 150, 220)
    _gizmo_icon_label = "P"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Capsule", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
            InspectorField("segments", "Segments", FieldType.INT, min_val=4, max_val=64),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.radius = 0.5
        self.height = 1.0
        self.color = Vec4(0.5, 0.5, 1.0, 0.6)
        self.thickness = 1.0
        self.show_in_play = True
        self.segments = 16
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "radius": self.radius, "height": self.height, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play, "segments": self.segments})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.radius = data.get("radius", 0.5)
        inst.height = data.get("height", 1.0)
        inst.color = Vec4(*data.get("color", [0.5, 0.5, 1, 0.6]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        inst.segments = data.get("segments", 16)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.CAPSULE, _v3t(self.center), (*_v4t(self.color),),
                               end_position=(self.center.x, self.center.y + self.height, self.center.z), size=self.radius, segments=self.segments, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoPyramid(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "base_size", "height", "color", "thickness", "show_in_play")
    _gizmo_icon_color = (200, 180, 80)
    _gizmo_icon_label = "Py"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Pyramid", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("base_size", "Base Size", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.base_size = 1.0
        self.height = 1.0
        self.color = Vec4(0.9, 0.7, 0.2, 0.8)
        self.thickness = 1.0
        self.show_in_play = True
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "base_size": self.base_size, "height": self.height, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.base_size = data.get("base_size", 1.0)
        inst.height = data.get("height", 1.0)
        inst.color = Vec4(*data.get("color", [0.9, 0.7, 0.2, 0.8]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        res = _build_primitive(GizmoType.PYRAMID, _v3t(self.center), (*_v4t(self.color),),
                               size=self.base_size, height=self.height, segments=4, thickness=self.thickness)
        if res is None:
            return None
        return _apply_world(*res, tr)


@ComponentRegistry.register
class GizmoFrustum(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("center", "fov", "aspect", "near_plane", "far_plane", "color", "thickness", "show_in_play")
    _gizmo_icon_color = (100, 200, 220)
    _gizmo_icon_label = "F"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Frustum", FieldType.HEADER),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("fov", "FOV", FieldType.FLOAT, min_val=10.0, max_val=120.0),
            InspectorField("aspect", "Aspect", FieldType.FLOAT, min_val=0.1, max_val=3.0),
            InspectorField("near_plane", "Near", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("far_plane", "Far", FieldType.FLOAT, min_val=1.0, max_val=100.0),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.center = Vec3.zero()
        self.fov = 60.0
        self.aspect = 1.5
        self.near_plane = 0.3
        self.far_plane = 10.0
        self.color = Vec4(0.4, 0.8, 1.0, 0.6)
        self.thickness = 1.0
        self.show_in_play = True
    def serialize(self):
        d = super().serialize()
        d.update({"center": _v3t(self.center), "fov": self.fov, "aspect": self.aspect, "near_plane": self.near_plane, "far_plane": self.far_plane, "color": _v4t(self.color), "thickness": self.thickness, "show_in_play": self.show_in_play})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.center = Vec3(*data.get("center", [0, 0, 0]))
        inst.fov = data.get("fov", 60.0)
        inst.aspect = data.get("aspect", 1.5)
        inst.near_plane = data.get("near_plane", 0.3)
        inst.far_plane = data.get("far_plane", 10.0)
        inst.color = Vec4(*data.get("color", [0.4, 0.8, 1.0, 0.6]))
        inst.thickness = data.get("thickness", 1.0)
        inst.show_in_play = data.get("show_in_play", True)
        return inst
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        base = tr.position if tr else Vec3.zero()
        pos = base + _v3(self.center)
        fwd = tr.forward if tr else Vec3(0, 0, 1)
        return _build_primitive(GizmoType.FRUSTUM, (pos.x, pos.y, pos.z), (*_v4t(self.color),),
                                normal=(fwd.x, fwd.y, fwd.z), fov=self.fov, size=self.aspect, near_plane=self.near_plane, far_plane=self.far_plane, thickness=self.thickness)


@ComponentRegistry.register
class GizmoBounds(Component):
    _gizmo_pass = "gizmo"
    _gizmo_cache_attrs = ("min_point", "max_point", "color", "thickness", "dash_length", "gap_length", "corner_radius", "show_in_play")
    _gizmo_icon_color = (180, 180, 180)
    _gizmo_icon_label = "B"
    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Gizmo Bounds", FieldType.HEADER),
            InspectorField("min_point", "Min", FieldType.VEC3),
            InspectorField("max_point", "Max", FieldType.VEC3),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.1, max_val=10.0),
            InspectorField("dash_length", "Dash Length", FieldType.FLOAT, min_val=0.01, max_val=2.0),
            InspectorField("gap_length", "Gap Length", FieldType.FLOAT, min_val=0.01, max_val=2.0),
            InspectorField("corner_radius", "Corner Radius", FieldType.FLOAT, min_val=0.01, max_val=1.0),
            InspectorField("show_in_play", "Show in Play", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.min_point = Vec3(-1, -1, -1)
        self.max_point = Vec3(1, 1, 1)
        self.color = Vec4(0.25, 0.55, 1.0, 0.85)
        self.thickness = 1.0
        self.dash_length = 0.3
        self.gap_length = 0.15
        self.corner_radius = 0.08
        self.show_in_play = True
    def serialize(self):
        d = super().serialize()
        d.update({"min_point": _v3t(self.min_point), "max_point": _v3t(self.max_point), "color": _v4t(self.color), "thickness": self.thickness, "dash_length": self.dash_length, "gap_length": self.gap_length, "corner_radius": self.corner_radius, "show_in_play": self.show_in_play})
        return d
    @classmethod
    def deserialize(cls, data):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.min_point = Vec3(*data.get("min_point", [-1, -1, -1]))
        inst.max_point = Vec3(*data.get("max_point", [1, 1, 1]))
        inst.color = Vec4(*data.get("color", [0.25, 0.55, 1.0, 0.85]))
        inst.thickness = data.get("thickness", 1.0)
        inst.dash_length = data.get("dash_length", 0.3)
        inst.gap_length = data.get("gap_length", 0.15)
        inst.corner_radius = data.get("corner_radius", 0.08)
        inst.show_in_play = data.get("show_in_play", True)
        return inst
    def gizmo_cache_sig(self):
        return None
    def gizmo_instance_data(self):
        return None
    def gizmo_instances(self):
        if not _gizmo_visible(self):
            return None
        tr = self.transform
        if tr is None:
            return None
        wm = _wm(tr)
        rs = wm[:3, :3]
        t = wm[3, :3]
        mn = _v3(self.min_point)
        mx = _v3(self.max_point)
        corners = np.array([
            [mn.x, mn.y, mn.z], [mx.x, mn.y, mn.z], [mn.x, mx.y, mn.z], [mx.x, mx.y, mn.z],
            [mn.x, mn.y, mx.z], [mx.x, mn.y, mx.z], [mn.x, mx.y, mx.z], [mx.x, mx.y, mx.z],
        ], dtype=np.float32)
        world = corners @ rs + t
        r = max(float(self.corner_radius), 0.001)
        ms = max((np.linalg.norm(rs[:, i]) for i in range(3)), default=1.0)
        if ms <= 0.0:
            ms = 1.0
        radius = r * ms
        return [_sphere_at(w, radius, self.color) for w in world]
    def gizmo_primitives(self):
        if not _gizmo_visible(self):
            return None
        res = _build_primitive(GizmoType.BBOX, (0, 0, 0), (*_v4t(self.color),),
                               min_point=(*_v3t(self.min_point),), max_point=(*_v3t(self.max_point),), thickness=self.thickness)
        if res is None:
            return None
        s, e, c = _apply_world(*res, self.transform)
        dlen = max(float(self.dash_length), 0.01)
        glen = max(float(self.gap_length), 0.01)
        phase = time.time() * 1.5 * (dlen + glen)
        s, e, c = _dash_animated(s, e, c, dlen, glen, phase)
        if s.shape[0] == 0:
            return None
        return (s, e, c)
