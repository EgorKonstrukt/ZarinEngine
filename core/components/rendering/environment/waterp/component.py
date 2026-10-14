# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField, ListElementField
from core.components.rendering.environment.waterp.surfacing import WaterSurfacingMixin


_DEFAULT_WAVES = [
    {"direction": 12.0,  "amplitude": 0.30, "wavelength": 31.0, "speed": 0.9, "steepness": 0.42},
    {"direction": 57.0,  "amplitude": 0.21, "wavelength": 19.0, "speed": 1.0, "steepness": 0.48},
    {"direction": 103.0, "amplitude": 0.14, "wavelength": 12.0, "speed": 1.1, "steepness": 0.55},
    {"direction": 149.0, "amplitude": 0.10, "wavelength": 8.0,  "speed": 1.2, "steepness": 0.60},
    {"direction": 201.0, "amplitude": 0.07, "wavelength": 5.4,  "speed": 1.3, "steepness": 0.62},
    {"direction": 256.0, "amplitude": 0.045, "wavelength": 3.6,  "speed": 1.4, "steepness": 0.68},
    {"direction": 309.0, "amplitude": 0.028, "wavelength": 2.4,  "speed": 1.5, "steepness": 0.72},
    {"direction": 338.0, "amplitude": 0.018, "wavelength": 1.5,  "speed": 1.6, "steepness": 0.78},
]


@ComponentRegistry.register
class Water(WaterSurfacingMixin, Component):
    _icon = "Water.png"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Water", FieldType.HEADER),
            InspectorField("material_path", "Water Shader", FieldType.RESOURCE_PATH, file_filter="Shader (*.shader)"),
            InspectorField("surface_type", "Surface Type", FieldType.ENUM, enum_options=["Ocean", "Pond"]),
            InspectorField("infinite_ocean", "Infinite Ocean", FieldType.BOOL),
            InspectorField("ocean_size", "Ocean Size", FieldType.FLOAT, min_val=10.0, max_val=5000.0, step=10.0, decimals=1),
            InspectorField("waves", "Waves", FieldType.LIST, element_fields=[
                ListElementField("direction", "Dir (deg)", FieldType.FLOAT, min_val=0.0, max_val=360.0, step=1.0, decimals=1),
                ListElementField("amplitude", "Amp", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.01, decimals=3),
                ListElementField("wavelength", "Length", FieldType.FLOAT, min_val=0.1, max_val=200.0, step=0.1, decimals=2),
                ListElementField("speed", "Speed", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.01, decimals=3),
                ListElementField("steepness", "Steep", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            ]),
            InspectorField("deep_color", "Deep Color", FieldType.COLOR),
            InspectorField("shallow_color", "Shallow Color", FieldType.COLOR),
            InspectorField("foam_color", "Foam Color", FieldType.COLOR),
            InspectorField("sss_color", "SSS Color", FieldType.COLOR),
            InspectorField("horizon_color", "Horizon Color", FieldType.COLOR),
            InspectorField("smoothness", "Smoothness", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("distortion", "Distortion", FieldType.SLIDER, min_val=0.0, max_val=0.3, step=0.005, decimals=3),
            InspectorField("normal_strength", "Detail Normal", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("wave_tiling", "Wave Tiling", FieldType.SLIDER, min_val=0.01, max_val=2.0, step=0.01, decimals=3),
            InspectorField("warp_amount", "Domain Warp", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.05, decimals=3),
            InspectorField("", "Surface", FieldType.HEADER),
            InspectorField("detail_speed", "Detail Speed", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.01, decimals=3),
            InspectorField("refract_strength", "Refraction Tint", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("fresnel_power", "Fresnel Power", FieldType.SLIDER, min_val=0.5, max_val=8.0, step=0.1, decimals=2),
            InspectorField("foam_strength", "Foam Strength", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.05, decimals=2),
            InspectorField("specular", "Specular", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.05, decimals=2),
            InspectorField("shore_fade", "Shore Fade", FieldType.FLOAT, min_val=0.1, max_val=20.0, step=0.1, decimals=2),
            InspectorField("choppiness", "Choppiness", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.01, decimals=3),
            InspectorField("caustics", "Caustics", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.01, decimals=3),
            InspectorField("", "Wind", FieldType.HEADER),
            InspectorField("wind_direction", "Wind Direction (deg)", FieldType.FLOAT, min_val=0.0, max_val=360.0, step=1.0, decimals=1),
            InspectorField("wind_speed", "Wind Speed (m/s)", FieldType.FLOAT, min_val=0.0, max_val=60.0, step=0.1, decimals=2),
            InspectorField("wind_turbulence", "Wind Turbulence", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("wind_influence", "Wind Influence", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("wind_gust", "Wind Gust", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("mesh_resolution", "Mesh Resolution", FieldType.SLIDER, min_val=2.0, max_val=400.0, step=1.0, decimals=0),
            InspectorField("chaos", "Chaos", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("macro_wave", "Macro Waves", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.01, decimals=3),
            InspectorField("detail_scale", "Detail Scale", FieldType.SLIDER, min_val=0.1, max_val=4.0, step=0.01, decimals=3),
            InspectorField("detail_octaves", "Detail Octaves", FieldType.SLIDER, min_val=1.0, max_val=12.0, step=1.0, decimals=0),
            InspectorField("detail_fade", "Detail Fade Dist", FieldType.FLOAT, min_val=20.0, max_val=2000.0, step=10.0, decimals=0),
            InspectorField("", "Interaction", FieldType.HEADER),
            InspectorField("interaction_enabled", "Object Interaction", FieldType.BOOL),
            InspectorField("interaction_strength", "Interaction Strength", FieldType.SLIDER, min_val=0.0, max_val=8.0, step=0.05, decimals=2),
            InspectorField("interaction_radius", "Interaction Radius", FieldType.SLIDER, min_val=0.1, max_val=4.0, step=0.05, decimals=2),
            InspectorField("", "Sim", FieldType.HEADER),
            InspectorField("sim_damping", "Wave Damping", FieldType.SLIDER, min_val=0.0, max_val=0.3, step=0.005, decimals=3),
            InspectorField("sim_propagation", "Wave Propagation", FieldType.SLIDER, min_val=2.0, max_val=60.0, step=0.5, decimals=1),
            InspectorField("sim_saturation", "Wave Saturation", FieldType.SLIDER, min_val=0.5, max_val=10.0, step=0.1, decimals=1),
            InspectorField("sim_disp_scale", "Ripple Height", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.05, decimals=2),
            InspectorField("sim_normal_scale", "Ripple Normal", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.05, decimals=2),
            InspectorField("pond_size", "Pond Size", FieldType.FLOAT, min_val=2.0, max_val=4000.0, step=1.0, decimals=1),
        ]

    def __init__(self):
        super().__init__()
        self._time_origin: float = time.time()
        self.material_path: str = "core/shaders/materials/Water.shader"
        self.surface_type: str = "Ocean"
        self.infinite_ocean: bool = True
        self.ocean_size: float = 2000.0
        self.waves: list[dict] = [dict(w) for w in _DEFAULT_WAVES]
        self.deep_color: list[float] = [0.02, 0.18, 0.28]
        self.shallow_color: list[float] = [0.10, 0.42, 0.52]
        self.foam_color: list[float] = [0.92, 0.97, 1.0]
        self.sss_color: list[float] = [0.0, 0.55, 0.45]
        self.horizon_color: list[float] = [0.62, 0.78, 0.86]
        self.smoothness: float = 0.96
        self.distortion: float = 0.04
        self.normal_strength: float = 0.35
        self.wave_tiling: float = 0.25
        self.warp_amount: float = 1.6
        self.detail_speed: float = 1.0
        self.refract_strength: float = 0.55
        self.fresnel_power: float = 4.0
        self.foam_strength: float = 1.0
        self.specular: float = 1.0
        self.shore_fade: float = 3.0
        self.choppiness: float = 1.0
        self.caustics: float = 0.6
        self.wind_direction: float = 45.0
        self.wind_speed: float = 8.0
        self.wind_turbulence: float = 0.4
        self.wind_influence: float = 0.0
        self.wind_gust: float = 0.4
        self.mesh_resolution: float = 128.0
        self.chaos: float = 0.5
        self.macro_wave: float = 0.5
        self.detail_scale: float = 1.0
        self.detail_octaves: float = 6.0
        self.detail_fade: float = 350.0
        self.interaction_enabled: bool = True
        self.interaction_strength: float = 1.5
        self.interaction_radius: float = 1.0
        self.sim_damping: float = 0.04
        self.sim_propagation: float = 18.0
        self.sim_saturation: float = 4.0
        self.sim_disp_scale: float = 1.0
        self.sim_normal_scale: float = 1.0
        self.pond_size: float = 200.0

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "material_path": self.material_path,
            "surface_type": self.surface_type,
            "infinite_ocean": self.infinite_ocean,
            "ocean_size": self.ocean_size,
            "waves": [dict(w) for w in self.waves],
            "deep_color": self.deep_color,
            "shallow_color": self.shallow_color,
            "foam_color": self.foam_color,
            "sss_color": self.sss_color,
            "horizon_color": self.horizon_color,
            "smoothness": self.smoothness,
            "distortion": self.distortion,
            "normal_strength": self.normal_strength,
            "wave_tiling": self.wave_tiling,
            "warp_amount": self.warp_amount,
            "detail_speed": self.detail_speed,
            "refract_strength": self.refract_strength,
            "fresnel_power": self.fresnel_power,
            "foam_strength": self.foam_strength,
            "specular": self.specular,
            "shore_fade": self.shore_fade,
            "choppiness": self.choppiness,
            "caustics": self.caustics,
            "wind_direction": self.wind_direction,
            "wind_speed": self.wind_speed,
            "wind_turbulence": self.wind_turbulence,
            "wind_influence": self.wind_influence,
            "wind_gust": self.wind_gust,
            "mesh_resolution": self.mesh_resolution,
            "chaos": self.chaos,
            "macro_wave": self.macro_wave,
            "detail_scale": self.detail_scale,
            "detail_octaves": self.detail_octaves,
            "detail_fade": self.detail_fade,
            "interaction_enabled": self.interaction_enabled,
            "interaction_strength": self.interaction_strength,
            "interaction_radius": self.interaction_radius,
            "sim_damping": self.sim_damping,
            "sim_propagation": self.sim_propagation,
            "sim_saturation": self.sim_saturation,
            "sim_disp_scale": self.sim_disp_scale,
            "sim_normal_scale": self.sim_normal_scale,
            "pond_size": self.pond_size,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> Water:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.material_path = data.get("material_path", "core/shaders/materials/Water.shader")
        c.surface_type = data.get("surface_type", "Ocean")
        c.infinite_ocean = data.get("infinite_ocean", True)
        c.ocean_size = data.get("ocean_size", 2000.0)
        raw_waves = data.get("waves")
        if raw_waves:
            c.waves = [dict(w) for w in raw_waves]
        else:
            c.waves = [dict(w) for w in _DEFAULT_WAVES]
        c.deep_color = data.get("deep_color", [0.02, 0.18, 0.28])
        c.shallow_color = data.get("shallow_color", [0.10, 0.42, 0.52])
        c.foam_color = data.get("foam_color", [0.92, 0.97, 1.0])
        c.sss_color = data.get("sss_color", [0.0, 0.55, 0.45])
        c.horizon_color = data.get("horizon_color", [0.62, 0.78, 0.86])
        c.smoothness = data.get("smoothness", 0.96)
        c.distortion = data.get("distortion", 0.04)
        c.normal_strength = data.get("normal_strength", 0.35)
        c.wave_tiling = data.get("wave_tiling", 0.25)
        c.warp_amount = data.get("warp_amount", 1.6)
        c.detail_speed = data.get("detail_speed", 1.0)
        c.refract_strength = data.get("refract_strength", 0.55)
        c.fresnel_power = data.get("fresnel_power", 4.0)
        c.foam_strength = data.get("foam_strength", 1.0)
        c.specular = data.get("specular", 1.0)
        c.shore_fade = data.get("shore_fade", 3.0)
        c.choppiness = data.get("choppiness", 1.0)
        c.caustics = data.get("caustics", 0.6)
        c.wind_direction = data.get("wind_direction", 45.0)
        c.wind_speed = data.get("wind_speed", 8.0)
        c.wind_turbulence = data.get("wind_turbulence", 0.4)
        c.wind_influence = data.get("wind_influence", 0.0)
        c.wind_gust = data.get("wind_gust", 0.4)
        c.mesh_resolution = data.get("mesh_resolution", 128.0)
        c.chaos = data.get("chaos", 0.5)
        c.macro_wave = data.get("macro_wave", 0.5)
        c.detail_scale = data.get("detail_scale", 1.0)
        c.detail_octaves = data.get("detail_octaves", 6.0)
        c.detail_fade = data.get("detail_fade", 350.0)
        c.interaction_enabled = data.get("interaction_enabled", True)
        c.interaction_strength = data.get("interaction_strength", 1.5)
        c.interaction_radius = data.get("interaction_radius", 1.0)
        c.sim_damping = data.get("sim_damping", 0.04)
        c.sim_propagation = data.get("sim_propagation", 18.0)
        c.sim_saturation = data.get("sim_saturation", 4.0)
        c.sim_disp_scale = data.get("sim_disp_scale", 1.0)
        c.sim_normal_scale = data.get("sim_normal_scale", 1.0)
        c.pond_size = data.get("pond_size", 200.0)
        return c
