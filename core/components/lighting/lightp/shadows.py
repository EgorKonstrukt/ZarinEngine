# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
from typing import Optional
from core.ecs import ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.components.lighting.lightp.light import Light, LightType, LightAreaType, DirectionalLight, PointLight, SpotLight


def get_for_entity(entity) -> Optional[Light]:
    if entity is None:
        return None
    for cls in (DirectionalLight, PointLight, SpotLight, AreaLight, Light):
        try:
            comp = entity.get_component(cls)
        except Exception:
            comp = None
        if comp is not None:
            return comp
    return None


def iter_scene_lights(scene) -> list:
    if scene is None:
        return []
    seen: set[str] = set()
    result: list = []
    for cls in (DirectionalLight, PointLight, SpotLight, AreaLight, Light):
        try:
            ents = scene.get_entities_with_component(cls)
        except Exception:
            continue
        for ent in ents:
            if ent.id in seen:
                continue
            if not ent.active:
                continue
            comp = None
            try:
                comp = ent.get_component(cls)
            except Exception:
                comp = None
            if comp is None:
                continue
            if not comp.enabled:
                continue
            tr = ent.transform
            if tr is None:
                continue
            seen.add(ent.id)
            result.append((comp, tr))
    return result


def find_directional(scene):
    if scene is None:
        return None
    for cls in (DirectionalLight, Light):
        try:
            ents = scene.get_entities_with_component(cls)
        except Exception:
            continue
        for ent in ents:
            comp = ent.get_component(cls)
            tr = ent.transform
            if comp is not None and comp.enabled and tr is not None and ent.active:
                if isinstance(comp, (DirectionalLight, Light)):
                    return (comp, tr)
    for comp, tr in iter_scene_lights(scene):
        if isinstance(comp, (DirectionalLight, Light)):
            return (comp, tr)
    return None


@ComponentRegistry.register
class AreaLight(Light):
    _icon = "Light.png"
    _editor_hidden = False
    _gizmo_icon_color = (200, 220, 255)
    _gizmo_icon_label = "A"
    _gizmo_pass = "light"
    _gizmo_cache_attrs = ("area_width", "area_height", "area_type", "area_double_sided", "color")
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Light", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("intensity", "Intensity (nits)", FieldType.FLOAT, min_val=0.0, max_val=200000.0, step=10.0, decimals=1, description="Surface brightness in nits (cd per sq m). Monitor 200, office panel 500, overcast sky 2000, softbox 10000. Same nits on a bigger panel lights the scene more"),
            InspectorField("range", "Range", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=0.5, decimals=2),
            InspectorField("", "Area", FieldType.HEADER),
            InspectorField("area_type", "Area Type", FieldType.ENUM, enum_class=LightAreaType),
            InspectorField("area_width", "Area Width", FieldType.FLOAT, min_val=0.01, max_val=100.0, step=0.1, decimals=2),
            InspectorField("area_height", "Area Height", FieldType.FLOAT, min_val=0.01, max_val=100.0, step=0.1, decimals=2),
            InspectorField("area_double_sided", "Double Sided", FieldType.BOOL),
            InspectorField("area_samples", "Samples", FieldType.INT, min_val=1, max_val=64, step=1),
            InspectorField("area_shadow_bias", "Shadow Bias", FieldType.FLOAT, min_val=0.0, max_val=0.1, step=0.001, decimals=4),
            InspectorField("", "Shadows", FieldType.HEADER),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.intensity = 100.0
        self.range = 10.0
        self.area_type = LightAreaType.RECT
        self.area_width = 1.0
        self.area_height = 1.0
        self.area_double_sided = False
        self.area_samples = 6
        self.area_shadow_bias = 0.005
        self.cast_shadows = True
    @property
    def light_type(self) -> LightType:
        return LightType.AREA
    def gizmo(self):
        tr = self.transform
        if not tr:
            return []
        from core.ecs import GizmoPrimitive
        pos = tr.position
        fwd = tr.forward
        up = tr.up
        right = tr.right
        col = Light._gizmo_color(self.color)
        lines = []
        segments = 32
        hw = float(self.area_width) * 0.5
        hh = float(self.area_height) * 0.5
        corners = [
            pos - right * hw - up * hh,
            pos + right * hw - up * hh,
            pos + right * hw + up * hh,
            pos - right * hw + up * hh,
        ]
        for i in range(4):
            lines.append((corners[i], corners[(i + 1) % 4], col))
        mid_r = pos + fwd * 0.1
        lines.append((pos, mid_r, col))
        if self.area_type == LightAreaType.DISK:
            disk_pts = []
            for i in range(segments):
                a = 2.0 * math.pi * i / segments
                disk_pts.append(pos + (right * math.cos(a) + up * math.sin(a)) * hw)
            for i in range(segments):
                lines.append((disk_pts[i], disk_pts[(i + 1) % segments], [col[0], col[1], col[2], 0.3]))
        if self.area_double_sided:
            back_corners = [
                pos - fwd * 0.02 - right * hw - up * hh,
                pos - fwd * 0.02 + right * hw - up * hh,
                pos - fwd * 0.02 + right * hw + up * hh,
                pos - fwd * 0.02 - right * hw + up * hh,
            ]
            dim_col = [col[0] * 0.4, col[1] * 0.4, col[2] * 0.4, col[3] * 0.5]
            for i in range(4):
                lines.append((back_corners[i], back_corners[(i + 1) % 4], dim_col))
        if not lines:
            return []
        return [GizmoPrimitive.from_lines(lines)]
    def serialize(self) -> dict:
        d = super().serialize()
        d["light_type"] = LightType.AREA.value
        return d
    @classmethod
    def deserialize(cls, data: dict) -> AreaLight:
        l = cls()
        l.enabled = data.get("enabled", True)
        l.color = data.get("color", [1.0, 1.0, 1.0])
        l.intensity = data.get("intensity", 100.0)
        if data.get("light_version", 2) < 2 and data.get("type") == "Light":
            l.intensity = l.intensity * Light.LEGACY_AREA_MULT
        l.range = data.get("range", 10.0)
        l.cast_shadows = data.get("cast_shadows", True)
        try:
            l.area_type = LightAreaType(data.get("area_type", "rect"))
        except Exception:
            l.area_type = LightAreaType.RECT
        l.area_width = data.get("area_width", 1.0)
        l.area_height = data.get("area_height", 1.0)
        l.area_double_sided = data.get("area_double_sided", False)
        l.area_samples = data.get("area_samples", 6)
        l.area_shadow_bias = data.get("area_shadow_bias", 0.005)
        return l
