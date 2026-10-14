# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.maths.math3d import Vec3
from .astro import _ASTRO_DEFAULTS, _DEFAULT_YEAR, _DEFAULT_MONTH, _DEFAULT_DAY, _DEFAULT_HOUR, _DEFAULT_MINUTE, _DEFAULT_SECOND, _DEFAULT_LATITUDE, _DEFAULT_LONGITUDE, _DEFAULT_UTC_OFFSET
from .astro import ProceduralSkyAstroMixin
from .atmosphere import ProceduralSkyAtmosphereMixin
from .sun import ProceduralSkySunMixin
from .clouds import ProceduralSkyCloudsMixin


@ComponentRegistry.register
class ProceduralSky(ProceduralSkyAstroMixin, ProceduralSkyAtmosphereMixin, ProceduralSkySunMixin, ProceduralSkyCloudsMixin, Component):
    _icon = "Sky.png"
    _registry: list = []

    def on_awake(self):
        if self not in self._registry:
            self._registry.append(self)

    def on_destroy(self):
        if self in self._registry:
            self._registry.remove(self)

    def on_disable(self):
        if self in self._registry:
            self._registry.remove(self)

    def on_enable(self):
        if self not in self._registry:
            self._registry.append(self)

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Procedural Night Sky", FieldType.HEADER),
            InspectorField("night_sky_enabled", "Night Sky", FieldType.BOOL),
            InspectorField("night_exposure", "Night Exposure", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.1, decimals=1),
            InspectorField("", "Stars", FieldType.HEADER),
            InspectorField("star_enabled", "Stars", FieldType.BOOL),
            InspectorField("star_density", "Density", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
            InspectorField("star_intensity", "Intensity", FieldType.SLIDER, min_val=0.0, max_val=5.0, step=0.1, decimals=1),
            InspectorField("star_scale", "Scale", FieldType.SLIDER, min_val=20.0, max_val=200.0, step=1.0, decimals=0),
            InspectorField("star_twinkle", "Twinkle", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("star_twinkle_speed", "Twinkle Speed", FieldType.SLIDER, min_val=0.0, max_val=10.0, step=0.1, decimals=1),
            InspectorField("star_seed", "Seed", FieldType.SLIDER, min_val=0.0, max_val=100.0, step=0.1, decimals=1),
            InspectorField("star_color", "Tint", FieldType.COLOR),
            InspectorField("", "Milky Way", FieldType.HEADER),
            InspectorField("milky_way_enabled", "Milky Way", FieldType.BOOL),
            InspectorField("milky_way_intensity", "Intensity", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.1, decimals=1),
            InspectorField("milky_way_pole", "Band Pole", FieldType.VEC3),
            InspectorField("", "Time Controller", FieldType.HEADER),
            InspectorField("year", "Year", FieldType.INT, min_val=1, max_val=9999, step=1),
            InspectorField("month", "Month", FieldType.INT, min_val=1, max_val=12, step=1, on_set="_on_time_field_set"),
            InspectorField("day", "Day", FieldType.INT, min_val=1, max_val=31, step=1, on_set="_on_time_field_set"),
            InspectorField("hour", "Hour", FieldType.INT, min_val=0, max_val=23, step=1, on_set="_on_time_field_set"),
            InspectorField("minute", "Minute", FieldType.INT, min_val=0, max_val=59, step=1, on_set="_on_time_field_set"),
            InspectorField("second", "Second", FieldType.INT, min_val=0, max_val=59, step=1, on_set="_on_time_field_set"),
            InspectorField("time_speed", "Time Speed (game-sec/sec)", FieldType.FLOAT),
            InspectorField("_btn_nearest_solar_eclipse", "Nearest Solar Eclipse", FieldType.BUTTON),
            InspectorField("latitude", "Latitude (deg)", FieldType.SLIDER, min_val=-90.0, max_val=90.0, step=0.1, decimals=2),
            InspectorField("longitude", "Longitude (deg)", FieldType.SLIDER, min_val=-180.0, max_val=180.0, step=0.1, decimals=2),
            InspectorField("utc_offset", "UTC Offset (h)", FieldType.SLIDER, min_val=-12.0, max_val=14.0, step=0.5, decimals=1),
            InspectorField("", "Sun Light", FieldType.HEADER),
            InspectorField("sun_light_entity_id", "Sun Light", FieldType.GAMEOBJECT),
            InspectorField("", "Moon", FieldType.HEADER),
            InspectorField("moon_enabled", "Moon", FieldType.BOOL),
            InspectorField("moon_size", "Angular Radius (deg)", FieldType.SLIDER, min_val=0.05, max_val=1.5, step=0.01, decimals=2),
            InspectorField("moon_intensity", "Intensity", FieldType.SLIDER, min_val=0.0, max_val=5.0, step=0.1, decimals=1),
            InspectorField("moon_texture_path", "Texture", FieldType.RESOURCE_PATH, file_filter="Images (*.png *.jpg *.jpeg *.tga *.bmp)"),
            InspectorField("", "Celestial Model (Advanced)", FieldType.HEADER),
            InspectorField("_astro_obliquity_deg", "Axial Tilt (deg)", FieldType.SLIDER, min_val=0.0, max_val=90.0, step=0.001, decimals=3),
            InspectorField("_astro_obliquity_drift", "Tilt Drift (deg/day)", FieldType.SLIDER, min_val=0.0, max_val=0.001, step=0.0000001, decimals=7),
            InspectorField("", "Sun Orbit", FieldType.HEADER),
            InspectorField("_astro_sun_ml_epoch", "Mean Longitude (deg)", FieldType.SLIDER, min_val=0.0, max_val=360.0, step=0.1, decimals=2),
            InspectorField("_astro_sun_ml_rate", "Longitude Rate (deg/day)", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.000001, decimals=6),
            InspectorField("_astro_sun_ma_epoch", "Mean Anomaly (deg)", FieldType.SLIDER, min_val=0.0, max_val=360.0, step=0.1, decimals=2),
            InspectorField("_astro_sun_ma_rate", "Anomaly Rate (deg/day)", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.000001, decimals=6),
            InspectorField("_astro_sun_ecc", "Equation of Center", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.001, decimals=3),
            InspectorField("_astro_sun_ecc2", "Eccentricity Harmonic", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.001, decimals=3),
            InspectorField("", "Moon Orbit", FieldType.HEADER),
            InspectorField("_astro_moon_ml_epoch", "Mean Longitude (deg)", FieldType.SLIDER, min_val=0.0, max_val=360.0, step=0.1, decimals=2),
            InspectorField("_astro_moon_ml_rate", "Longitude Rate (deg/day)", FieldType.SLIDER, min_val=0.0, max_val=15.0, step=0.000001, decimals=6),
            InspectorField("_astro_moon_ma_epoch", "Mean Anomaly (deg)", FieldType.SLIDER, min_val=0.0, max_val=360.0, step=0.1, decimals=2),
            InspectorField("_astro_moon_ma_rate", "Anomaly Rate (deg/day)", FieldType.SLIDER, min_val=0.0, max_val=15.0, step=0.000001, decimals=6),
            InspectorField("_astro_moon_el_epoch", "Elongation (deg)", FieldType.SLIDER, min_val=0.0, max_val=360.0, step=0.1, decimals=2),
            InspectorField("_astro_moon_el_rate", "Elongation Rate (deg/day)", FieldType.SLIDER, min_val=0.0, max_val=15.0, step=0.000001, decimals=6),
            InspectorField("_astro_moon_af_epoch", "Arg of Latitude (deg)", FieldType.SLIDER, min_val=0.0, max_val=360.0, step=0.1, decimals=2),
            InspectorField("_astro_moon_af_rate", "Arg of Latitude Rate (deg/day)", FieldType.SLIDER, min_val=0.0, max_val=15.0, step=0.000001, decimals=6),
            InspectorField("_astro_moon_lat1", "Orbital Inclination (deg)", FieldType.SLIDER, min_val=0.0, max_val=15.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lon1", "Lon Amp sin(M)", FieldType.SLIDER, min_val=-10.0, max_val=10.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lon2", "Lon Amp sin(2D-M)", FieldType.SLIDER, min_val=-5.0, max_val=5.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lon3", "Lon Amp sin(2D)", FieldType.SLIDER, min_val=-5.0, max_val=5.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lon4", "Lon Amp sin(Ms)", FieldType.SLIDER, min_val=-5.0, max_val=5.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lon5", "Lon Amp sin(2M-2D)", FieldType.SLIDER, min_val=-5.0, max_val=5.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lat2", "Lat Amp sin(M+F)", FieldType.SLIDER, min_val=-5.0, max_val=5.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lat3", "Lat Amp sin(M-F)", FieldType.SLIDER, min_val=-5.0, max_val=5.0, step=0.001, decimals=3),
            InspectorField("_astro_moon_lat4", "Lat Amp sin(2D-F)", FieldType.SLIDER, min_val=-5.0, max_val=5.0, step=0.001, decimals=3),
            InspectorField("", "Phases & Sidereal Time", FieldType.HEADER),
            InspectorField("_astro_synodic_month", "Synodic Month (days)", FieldType.SLIDER, min_val=20.0, max_val=40.0, step=0.000001, decimals=6),
            InspectorField("_astro_new_moon_jd", "New Moon Epoch (JD)", FieldType.FLOAT, min_val=0.0, max_val=3000000.0, step=0.001, decimals=3),
            InspectorField("_astro_gmst_epoch", "GMST Epoch (hours)", FieldType.SLIDER, min_val=0.0, max_val=24.0, step=0.000001, decimals=6),
            InspectorField("_astro_gmst_rate", "GMST Rate (hours/day)", FieldType.SLIDER, min_val=23.0, max_val=25.0, step=0.000001, decimals=6),
        ]

    def __init__(self):
        super().__init__()
        self.material_path: str = "core/shaders/materials/Sky.shader"
        self.environment_path: str = ""
        self.night_sky_enabled: bool = True
        self.night_exposure: float = 1.0
        self.star_enabled: bool = True
        self.star_density: float = 0.45
        self.star_intensity: float = 1.0
        self.star_scale: float = 80.0
        self.star_twinkle: float = 0.5
        self.star_twinkle_speed: float = 1.0
        self.star_seed: float = 1.0
        self.star_color: list[float] = [0.9, 0.93, 1.0]
        self.milky_way_enabled: bool = True
        self.milky_way_intensity: float = 0.6
        self.milky_way_pole: Vec3 = Vec3(0.4, 0.3, 0.85)
        self.year: int = _DEFAULT_YEAR
        self.month: int = _DEFAULT_MONTH
        self.day: int = _DEFAULT_DAY
        self.hour: int = _DEFAULT_HOUR
        self.minute: int = _DEFAULT_MINUTE
        self.second: int = _DEFAULT_SECOND
        self.latitude: float = _DEFAULT_LATITUDE
        self.longitude: float = _DEFAULT_LONGITUDE
        self.utc_offset: float = _DEFAULT_UTC_OFFSET
        self.time_speed: float = 0.0
        self._time_frac: float = 0.0
        self._time_transition = None
        self.sun_light_entity_id: str = ""
        self.moon_enabled: bool = True
        self.moon_size: float = 0.27
        self.moon_intensity: float = 1.0
        self.moon_texture_path: str = "core/textures/moon.tga"
        self._sky_ibl = None
        self._sun_light_cache = None
        self._synced_sun = None
        self._time_cache_key = None
        self._sun_dir: Vec3 = Vec3(0.0, 0.3, 1.0)
        self._moon_dir: Vec3 = Vec3(0.25, 0.6, 0.75)
        self._moon_phase: float = 1.0
        self._day_seconds: float = 0.0
        self._sim_seconds: float = 0.0
        self._eclipse_darkness: float = 0.0
        self._star_pole: Vec3 = Vec3(0.0, 1.0, 0.0)
        self._star_rotation: float = 0.0
        for _k, _v in _ASTRO_DEFAULTS.items():
            setattr(self, "_astro_" + _k, _v)

    def live_inspector_fields(self) -> tuple:
        return ("year", "month", "day", "hour", "minute", "second")

    def on_update(self, dt: float):
        try:
            tr = self._time_transition
        except Exception:
            tr = None
        if tr is not None:
            try:
                start, end, dur, elapsed = tr[0], tr[1], tr[2], tr[3]
                smooth = tr[4] if len(tr) > 4 else True
            except Exception:
                tr = None
        if tr is not None:
            try:
                step = float(dt)
            except Exception:
                step = 0.0
            if step < 0.0:
                step = 0.0
            if dur <= 0.0:
                try:
                    self._apply_clock_total(end)
                except Exception:
                    pass
                try:
                    self._time_transition = None
                except Exception:
                    pass
                self._invalidate_time()
            else:
                elapsed += step
                if elapsed + 1e-9 >= dur:
                    try:
                        self._apply_clock_total(end)
                    except Exception:
                        pass
                    try:
                        self._time_transition = None
                    except Exception:
                        pass
                    self._invalidate_time()
                else:
                    k = elapsed / dur
                    if smooth:
                        k = k * k * (3.0 - 2.0 * k)
                    try:
                        self._apply_clock_total(start + (end - start) * k)
                    except Exception:
                        pass
                    try:
                        self._time_transition = (start, end, dur, elapsed, smooth)
                    except Exception:
                        pass
                    self._invalidate_time()
        else:
            try:
                spd = float(self.time_speed)
            except Exception:
                spd = 0.0
            if spd != 0.0:
                try:
                    self.advance_time(dt * spd)
                except Exception:
                    pass
        self._sync_sun_light()

    def serialize(self) -> dict:
        d = super().serialize()
        d["material_path"] = self.material_path
        d["environment_path"] = self.environment_path
        d["night_sky_enabled"] = self.night_sky_enabled
        d["night_exposure"] = self.night_exposure
        d["star_enabled"] = self.star_enabled
        d["star_density"] = self.star_density
        d["star_intensity"] = self.star_intensity
        d["star_scale"] = self.star_scale
        d["star_twinkle"] = self.star_twinkle
        d["star_twinkle_speed"] = self.star_twinkle_speed
        d["star_seed"] = self.star_seed
        d["star_color"] = self.star_color
        d["milky_way_enabled"] = self.milky_way_enabled
        d["milky_way_intensity"] = self.milky_way_intensity
        d["milky_way_pole"] = self.milky_way_pole.to_list()
        d["year"] = self.year
        d["month"] = self.month
        d["day"] = self.day
        d["hour"] = self.hour
        d["minute"] = self.minute
        d["second"] = self.second
        d["latitude"] = self.latitude
        d["longitude"] = self.longitude
        d["utc_offset"] = self.utc_offset
        d["time_speed"] = self.time_speed
        d["sun_light_entity_id"] = self.sun_light_entity_id
        d["moon_enabled"] = self.moon_enabled
        d["moon_size"] = self.moon_size
        d["moon_intensity"] = self.moon_intensity
        d["moon_texture_path"] = self.moon_texture_path
        for _k in _ASTRO_DEFAULTS:
            d["_astro_" + _k] = getattr(self, "_astro_" + _k)
        return d

    @classmethod
    def deserialize(cls, data: dict) -> ProceduralSky:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.material_path = data.get("material_path", "core/shaders/materials/Sky.shader")
        c.environment_path = data.get("environment_path", "")
        c.night_sky_enabled = data.get("night_sky_enabled", True)
        c.night_exposure = data.get("night_exposure", 1.0)
        c.star_enabled = data.get("star_enabled", True)
        c.star_density = data.get("star_density", 0.45)
        c.star_intensity = data.get("star_intensity", 1.0)
        c.star_scale = data.get("star_scale", 80.0)
        c.star_twinkle = data.get("star_twinkle", 0.5)
        c.star_twinkle_speed = data.get("star_twinkle_speed", 1.0)
        c.star_seed = data.get("star_seed", 1.0)
        c.star_color = data.get("star_color", [0.9, 0.93, 1.0])
        c.milky_way_enabled = data.get("milky_way_enabled", True)
        c.milky_way_intensity = data.get("milky_way_intensity", 0.6)
        c.milky_way_pole = Vec3(*data.get("milky_way_pole", [0.4, 0.3, 0.85]))
        c.year = data.get("year", _DEFAULT_YEAR)
        c.month = data.get("month", _DEFAULT_MONTH)
        c.day = data.get("day", _DEFAULT_DAY)
        c.hour = data.get("hour", _DEFAULT_HOUR)
        c.minute = data.get("minute", _DEFAULT_MINUTE)
        c.second = data.get("second", _DEFAULT_SECOND)
        c.latitude = data.get("latitude", _DEFAULT_LATITUDE)
        c.longitude = data.get("longitude", _DEFAULT_LONGITUDE)
        c.utc_offset = data.get("utc_offset", _DEFAULT_UTC_OFFSET)
        c.time_speed = float(data.get("time_speed", 0.0))
        c.sun_light_entity_id = data.get("sun_light_entity_id", "")
        c.moon_enabled = data.get("moon_enabled", True)
        c.moon_size = data.get("moon_size", 0.27)
        c.moon_intensity = data.get("moon_intensity", 1.0)
        c.moon_texture_path = data.get("moon_texture_path", "core/textures/moon.tga")
        for _k, _v in _ASTRO_DEFAULTS.items():
            setattr(c, "_astro_" + _k, data.get("_astro_" + _k, _v))
        return c

Sky = ProceduralSky
