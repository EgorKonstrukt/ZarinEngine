# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from enum import Enum
import math
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField


class LightType(Enum):
    DIRECTIONAL = "directional"
    POINT = "point"
    SPOT = "spot"
    AREA = "area"


class LightAreaType(Enum):
    RECT = "rect"
    DISK = "disk"


@ComponentRegistry.register
class Light(Component):
    _icon = "Light.png"
    _gizmo_icon_color = (255, 220, 50)
    _gizmo_icon_label = "L"
    _gizmo_pass = "light"
    _editor_hidden = True
    _gizmo_cache_attrs = ("color",)
    LUX_TO_RADIANCE = 1e-5
    CANDELA_TO_RADIANCE = 1e-2
    AREA_TO_RADIANCE = 1e-2
    LEGACY_DIRECTIONAL_MULT = 100000.0
    LEGACY_POINT_MULT = 2000.0
    LEGACY_AREA_MULT = 100.0
    _LIGHT_SCALE = 1.0
    LUX_REFERENCE = {
        "direct_sun": 100000.0,
        "full_daylight": 15000.0,
        "overcast_day": 5000.0,
        "sunrise_sunset": 400.0,
        "office": 500.0,
        "twilight": 10.0,
        "full_moon": 0.2,
    }
    LUMEN_REFERENCE = {
        "candle": 12.57,
        "decorative_led": 100.0,
        "desk_lamp": 300.0,
        "room_ceiling": 800.0,
        "bulb_100w": 1600.0,
        "street_light": 15000.0,
        "stadium_floodlight": 100000.0,
    }
    NIT_REFERENCE = {
        "monitor_sdr": 200.0,
        "office_panel": 500.0,
        "overcast_sky": 2000.0,
        "clear_sky": 5000.0,
        "led_softbox": 10000.0,
    }
    @classmethod
    def set_light_scale(cls, scale: float) -> None:
        cls._LIGHT_SCALE = max(float(scale), 0.0)
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Light", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("intensity", "Intensity", FieldType.FLOAT, min_val=0.0, max_val=200000.0, step=10.0, decimals=1),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.color: list[float] = [1.0, 1.0, 1.0]
        self.intensity: float = 100000.0
        self.cast_shadows: bool = True
        self.range: float = 10.0
        self.spot_angle: float = 30.0
        self.spot_inner_angle: float = 20.0
        self.procedural_sky_lighting: bool = False
        self.area_type: LightAreaType = LightAreaType.RECT
        self.area_width: float = 1.0
        self.area_height: float = 1.0
        self.area_double_sided: bool = False
        self.area_samples: int = 6
        self.area_shadow_bias: float = 0.005
    @property
    def light_type(self) -> LightType:
        return LightType.DIRECTIONAL
    @staticmethod
    def _gizmo_color(color) -> list[float]:
        c = color or [1.0, 1.0, 1.0]
        brightness = max(c[0], c[1], c[2])
        if brightness < 0.01:
            return [1.0, 1.0, 1.0, 0.8]
        return [c[0] / brightness, c[1] / brightness, c[2] / brightness, 0.8]
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
        r = 0.3
        ray_len = 1.5
        pts = []
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            pts.append(pos + (right * math.cos(a) + up * math.sin(a)) * r)
        for i in range(segments):
            lines.append((pts[i], pts[(i + 1) % segments], col))
        spacing = 0.2
        for i in (-1, 0, 1):
            dx = right * (i * spacing)
            for j in (-1, 0, 1):
                origin = pos + dx + up * (j * spacing)
                tip = origin + fwd * ray_len
                lines.append((origin, tip, col))
        if not lines:
            return []
        return [GizmoPrimitive.from_lines(lines)]
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "light_version": 2, "light_type": self.light_type.value, "color": self.color,
            "intensity": self.intensity,
            "cast_shadows": self.cast_shadows,
            "procedural_sky_lighting": self.procedural_sky_lighting,
            "range": self.range,
            "spot_angle": self.spot_angle, "spot_inner_angle": self.spot_inner_angle,
            "area_type": self.area_type.value if isinstance(self.area_type, LightAreaType) else str(self.area_type),
            "area_width": self.area_width,
            "area_height": self.area_height, "area_double_sided": self.area_double_sided,
            "area_samples": self.area_samples, "area_shadow_bias": self.area_shadow_bias,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> Light:
        if cls is Light:
            raw = data.get("light_type", "directional")
            try:
                kind = LightType(str(raw))
            except Exception:
                kind = LightType.DIRECTIONAL
            if kind == LightType.POINT:
                return PointLight.deserialize(data)
            if kind == LightType.SPOT:
                return SpotLight.deserialize(data)
            if kind == LightType.AREA:
                from core.components.lighting.lightp.shadows import AreaLight
                return AreaLight.deserialize(data)
            return DirectionalLight.deserialize(data)
        l = cls()
        l.enabled = data.get("enabled", True)
        l.color = data.get("color", [1.0, 1.0, 1.0])
        l.intensity = data.get("intensity", 1.0)
        if data.get("light_version", 1) < 2:
            l.intensity = l.intensity * Light.LEGACY_DIRECTIONAL_MULT
        l.procedural_sky_lighting = data.get("procedural_sky_lighting", False)
        l.range = data.get("range", 10.0)
        l.spot_angle = data.get("spot_angle", 30.0)
        l.spot_inner_angle = data.get("spot_inner_angle", 20.0)
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


@ComponentRegistry.register
class DirectionalLight(Light):
    _icon = "Light.png"
    _editor_hidden = False
    _gizmo_icon_color = (255, 220, 50)
    _gizmo_icon_label = "D"
    _gizmo_pass = "light"
    _gizmo_cache_attrs = ("color", "procedural_sky_lighting")
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Light", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("intensity", "Intensity (lux)", FieldType.FLOAT, min_val=0.0, max_val=200000.0, step=100.0, decimals=1, description="Illuminance in lux. Direct sun 100000, daylight 10000-25000, overcast 1000-10000, sunrise 400, office 500, twilight 10, full moon 0.2"),
            InspectorField("procedural_sky_lighting", "Procedural Sky Lighting", FieldType.BOOL),
            InspectorField("", "Shadows", FieldType.HEADER),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.intensity = 100000.0
        self.procedural_sky_lighting = False
        self.cast_shadows = True
    @property
    def light_type(self) -> LightType:
        return LightType.DIRECTIONAL
    def serialize(self) -> dict:
        d = super().serialize()
        d["light_type"] = LightType.DIRECTIONAL.value
        return d
    @classmethod
    def deserialize(cls, data: dict) -> DirectionalLight:
        l = cls()
        l.enabled = data.get("enabled", True)
        l.color = data.get("color", [1.0, 1.0, 1.0])
        l.intensity = data.get("intensity", 100000.0)
        if data.get("light_version", 2) < 2 and data.get("type") == "Light":
            l.intensity = l.intensity * Light.LEGACY_DIRECTIONAL_MULT
        l.procedural_sky_lighting = data.get("procedural_sky_lighting", False)
        l.cast_shadows = data.get("cast_shadows", True)
        return l


@ComponentRegistry.register
class PointLight(Light):
    _icon = "Light.png"
    _editor_hidden = False
    _gizmo_icon_color = (255, 200, 80)
    _gizmo_icon_label = "P"
    _gizmo_pass = "light"
    _gizmo_cache_attrs = ("range", "color")
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Light", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("intensity", "Intensity (lumens)", FieldType.FLOAT, min_val=0.0, max_val=200000.0, step=10.0, decimals=1, description="Total flux in lumens. Candle 13, desk lamp 300, room ceiling 800, 100W bulb 1600, street 1000-40000, stadium 100000"),
            InspectorField("range", "Range", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=0.5, decimals=2),
            InspectorField("", "Shadows", FieldType.HEADER),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.intensity = 1000.0
        self.range = 10.0
        self.cast_shadows = True
    @property
    def light_type(self) -> LightType:
        return LightType.POINT
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
        rng = max(float(self.range), 0.1)
        for axis_idx in range(3):
            pts = []
            for i in range(segments):
                a = 2.0 * math.pi * i / segments
                if axis_idx == 0:
                    pt = right * 0.0 + up * (math.cos(a) * rng) + fwd * (math.sin(a) * rng)
                elif axis_idx == 1:
                    pt = right * (math.cos(a) * rng) + up * 0.0 + fwd * (math.sin(a) * rng)
                else:
                    pt = right * (math.cos(a) * rng) + up * (math.sin(a) * rng) + fwd * 0.0
                pts.append(pos + pt)
            for i in range(segments):
                lines.append((pts[i], pts[(i + 1) % segments], col))
        half = rng * 0.15
        for d in [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]:
            end = pos + right * d[0] * half + up * d[1] * half + fwd * d[2] * half
            lines.append((pos, end, col))
        if not lines:
            return []
        return [GizmoPrimitive.from_lines(lines)]
    def serialize(self) -> dict:
        d = super().serialize()
        d["light_type"] = LightType.POINT.value
        return d
    @classmethod
    def deserialize(cls, data: dict) -> PointLight:
        l = cls()
        l.enabled = data.get("enabled", True)
        l.color = data.get("color", [1.0, 1.0, 1.0])
        l.intensity = data.get("intensity", 1000.0)
        if data.get("light_version", 2) < 2 and data.get("type") == "Light":
            l.intensity = l.intensity * Light.LEGACY_POINT_MULT
        l.range = data.get("range", 10.0)
        l.cast_shadows = data.get("cast_shadows", True)
        return l


@ComponentRegistry.register
class SpotLight(Light):
    _icon = "Light.png"
    _editor_hidden = False
    _gizmo_icon_color = (255, 200, 80)
    _gizmo_icon_label = "S"
    _gizmo_pass = "light"
    _gizmo_cache_attrs = ("range", "spot_angle", "color")
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Light", FieldType.HEADER),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("intensity", "Intensity (lumens)", FieldType.FLOAT, min_val=0.0, max_val=200000.0, step=10.0, decimals=1, description="Total flux in lumens inside the cone. Narrow cones concentrate the same lumens, wide cones spread them. Flashlight 100-1000, street 1000-40000"),
            InspectorField("range", "Range", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=0.5, decimals=2),
            InspectorField("", "Spot", FieldType.HEADER),
            InspectorField("spot_angle", "Spot Angle", FieldType.FLOAT, min_val=1.0, max_val=179.0, step=1.0, decimals=1),
            InspectorField("spot_inner_angle", "Inner Angle", FieldType.FLOAT, min_val=0.0, max_val=179.0, step=1.0, decimals=1),
            InspectorField("", "Shadows", FieldType.HEADER),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.intensity = 1000.0
        self.range = 10.0
        self.spot_angle = 30.0
        self.spot_inner_angle = 20.0
        self.cast_shadows = True
    @property
    def light_type(self) -> LightType:
        return LightType.SPOT
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
        rng = max(float(self.range), 0.1)
        half_angle = float(self.spot_angle) * 0.5 * math.pi / 180.0
        cone_r = rng * math.tan(half_angle)
        base_center = pos + fwd * rng
        base_pts = []
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            base_pts.append(base_center + (right * math.cos(a) + up * math.sin(a)) * cone_r)
        for i in range(segments):
            lines.append((base_pts[i], base_pts[(i + 1) % segments], col))
        for i in range(8):
            a = 2.0 * math.pi * i / 8
            bp = base_center + (right * math.cos(a) + up * math.sin(a)) * cone_r
            lines.append((pos, bp, col))
        lines.append((pos, base_center, col))
        if not lines:
            return []
        return [GizmoPrimitive.from_lines(lines)]
    def serialize(self) -> dict:
        d = super().serialize()
        d["light_type"] = LightType.SPOT.value
        return d
    @classmethod
    def deserialize(cls, data: dict) -> SpotLight:
        l = cls()
        l.enabled = data.get("enabled", True)
        l.color = data.get("color", [1.0, 1.0, 1.0])
        l.intensity = data.get("intensity", 1000.0)
        if data.get("light_version", 2) < 2 and data.get("type") == "Light":
            l.intensity = l.intensity * Light.LEGACY_POINT_MULT
        l.range = data.get("range", 10.0)
        l.spot_angle = data.get("spot_angle", 30.0)
        l.spot_inner_angle = data.get("spot_inner_angle", 20.0)
        l.cast_shadows = data.get("cast_shadows", True)
        return l
