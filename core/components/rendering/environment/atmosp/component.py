# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.components.rendering.environment.atmosp.compute import AtmosphereLutMixin
@ComponentRegistry.register
class Atmosphere(AtmosphereLutMixin, Component):
    _registry: list[Atmosphere] = []
    _allow_multiple = False
    _gizmo_icon_label = "ATMO"
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Atmosphere", FieldType.HEADER),
            InspectorField("enabled", "Enabled", FieldType.BOOL),
            InspectorField("_intensity", "Intensity", FieldType.SLIDER, min_val=1.0, max_val=60.0, step=1.0, decimals=0),
            InspectorField("", "Sun", FieldType.HEADER),
            InspectorField("_sun_intensity", "Sun Intensity", FieldType.SLIDER, min_val=0.0, max_val=10.0, step=0.1, decimals=1),
            InspectorField("_resolution_scale", "LUT Resolution", FieldType.SLIDER, min_val=0.25, max_val=1.0, step=0.25, decimals=2),
            InspectorField("_ozone_factor", "Ozone Factor", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.1, decimals=1),
            InspectorField("_aerosol_scale", "Aerosol Scale", FieldType.SLIDER, min_val=0.0, max_val=5.0, step=0.1, decimals=1),
            InspectorField("_rayleigh_scale", "Rayleigh Scale", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.05, decimals=2),
            InspectorField("_mie_anisotropy", "Mie Anisotropy", FieldType.SLIDER, min_val=0.0, max_val=0.95, step=0.01, decimals=2),
            InspectorField("_mie_albedo", "Mie Albedo", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
            InspectorField("_ground_albedo", "Ground Albedo", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
            InspectorField("_multiscatter_strength", "Multiscatter", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_horizon_haze", "Horizon Haze", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_planet_radius", "Planet Radius (km)", FieldType.SLIDER, min_val=6000.0, max_val=6500.0, step=1.0, decimals=0),
            InspectorField("_atmosphere_height", "Atmosphere Height (km)", FieldType.SLIDER, min_val=20.0, max_val=120.0, step=1.0, decimals=0),
            InspectorField("_camera_height_m", "Camera Height (m)", FieldType.SLIDER, min_val=0.0, max_val=8000.0, step=10.0, decimals=0),
            InspectorField("_sun_angular_radius", "Sun Angular Radius (deg)", FieldType.SLIDER, min_val=0.05, max_val=1.0, step=0.01, decimals=2),
            InspectorField("_sun_limb_darkening", "Sun Limb Darkening", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_sun_convergence", "Sun Edge Softness", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_color_temperature", "Sun Color Temp (K)", FieldType.SLIDER, min_val=2000, max_val=20000, step=100, decimals=0),
        ]
    def __init__(self):
        super().__init__()
        self._intensity: float = 20.0
        self._sun_intensity: float = 1.0
        self._resolution_scale: float = 1.0
        self._ozone_factor: float = 1.0
        self._aerosol_scale: float = 1.0
        self._rayleigh_scale: float = 1.0
        self._mie_anisotropy: float = 0.76
        self._mie_albedo: float = 0.9
        self._ground_albedo: float = 0.3
        self._multiscatter_strength: float = 1.0
        self._horizon_haze: float = 0.4
        self._planet_radius: float = 6360.0
        self._atmosphere_height: float = 60.0
        self._camera_height_m: float = 20.0
        self._sun_angular_radius: float = 0.27
        self._sun_limb_darkening: float = 0.7
        self._sun_convergence: float = 0.5
        self._color_temperature: float = 5778.0
        self._gl_states: dict = {}
    @classmethod
    def for_scene(cls, scene):
        try:
            found = None
            for a in cls._registry:
                try:
                    ok = a.enabled and a.entity and a.entity.active
                except Exception:
                    continue
                if not ok:
                    continue
                if found is None:
                    found = a
                try:
                    ent = a.entity
                    sc = ent._scene if ent is not None else None
                except Exception:
                    sc = None
                if sc is scene:
                    return a
            return found
        except Exception:
            return None
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_intensity": self._intensity,
            "_sun_intensity": self._sun_intensity,
            "_resolution_scale": self._resolution_scale,
            "_ozone_factor": self._ozone_factor,
            "_aerosol_scale": self._aerosol_scale,
            "_rayleigh_scale": self._rayleigh_scale,
            "_mie_anisotropy": self._mie_anisotropy,
            "_mie_albedo": self._mie_albedo,
            "_ground_albedo": self._ground_albedo,
            "_multiscatter_strength": self._multiscatter_strength,
            "_horizon_haze": self._horizon_haze,
            "_planet_radius": self._planet_radius,
            "_atmosphere_height": self._atmosphere_height,
            "_camera_height_m": self._camera_height_m,
            "_sun_angular_radius": self._sun_angular_radius,
            "_sun_limb_darkening": self._sun_limb_darkening,
            "_sun_convergence": self._sun_convergence,
            "_color_temperature": self._color_temperature,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> Atmosphere:
        inst = super().deserialize(data)
        inst._intensity = float(data.get("_intensity", 20.0))
        inst._sun_intensity = float(data.get("_sun_intensity", 1.0))
        inst._resolution_scale = float(data.get("_resolution_scale", 1.0))
        inst._ozone_factor = float(data.get("_ozone_factor", 1.0))
        inst._aerosol_scale = float(data.get("_aerosol_scale", 1.0))
        inst._rayleigh_scale = float(data.get("_rayleigh_scale", 1.0))
        inst._mie_anisotropy = float(data.get("_mie_anisotropy", 0.76))
        inst._mie_albedo = float(data.get("_mie_albedo", 0.9))
        inst._ground_albedo = float(data.get("_ground_albedo", 0.3))
        inst._multiscatter_strength = float(data.get("_multiscatter_strength", 1.0))
        inst._horizon_haze = float(data.get("_horizon_haze", 0.4))
        inst._planet_radius = float(data.get("_planet_radius", 6360.0))
        inst._atmosphere_height = float(data.get("_atmosphere_height", 60.0))
        inst._camera_height_m = float(data.get("_camera_height_m", 20.0))
        inst._sun_angular_radius = float(data.get("_sun_angular_radius", 0.27))
        inst._sun_limb_darkening = float(data.get("_sun_limb_darkening", 0.7))
        inst._sun_convergence = float(data.get("_sun_convergence", 0.5))
        inst._color_temperature = float(data.get("_color_temperature", 5778.0))
        inst._gl_states = {}
        return inst
    def on_awake(self):
        if self not in self._registry:
            self._registry.append(self)
    def on_destroy(self):
        if self in self._registry:
            self._registry.remove(self)
        self._release_gl()
    def on_disable(self):
        if self in self._registry:
            self._registry.remove(self)
    def on_enable(self):
        if self not in self._registry:
            self._registry.append(self)
    def ibl_key(self) -> tuple:
        return (
            round(float(self._intensity), 3),
            round(float(self._sun_intensity), 3),
            round(float(self._resolution_scale), 3),
            round(float(self._ozone_factor), 3),
            round(float(self._aerosol_scale), 3),
            round(float(self._rayleigh_scale), 3),
            round(float(self._mie_anisotropy), 3),
            round(float(self._mie_albedo), 3),
            round(float(self._ground_albedo), 3),
            round(float(self._multiscatter_strength), 3),
            round(float(self._horizon_haze), 3),
            round(float(self._planet_radius), 2),
            round(float(self._atmosphere_height), 2),
            round(float(self._camera_height_m), 1),
            round(float(self._sun_angular_radius), 3),
            round(float(self._sun_limb_darkening), 3),
            round(float(self._sun_convergence), 3),
            round(float(self._color_temperature), 1),
        )
