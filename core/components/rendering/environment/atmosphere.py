# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import numpy as np
import moderngl
from typing import Optional
from core.ecs.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.foundation.logger import Logger

_SHADERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))), "core", "shaders", "compute")
_SHADER_PATH = os.path.join(_SHADERS_DIR, "Atmosphere.compute")


def _resolve_atmosphere_source() -> Optional[str]:
    try:
        with open(_SHADER_PATH) as _f:
            return _f.read()
    except Exception:
        pass
    try:
        from core.renderer.mesh_data import read_compute_source
        return read_compute_source("atmosphere")
    except Exception:
        return None

_TRANSMITTANCE_W = 128
_TRANSMITTANCE_H = 32
_SKY_W = 256
_SKY_H = 128

_SUN_DIR_QUANT = 10000.0
_SUN_COLOR_QUANT = 1000.0


def _quant_dir(v) -> tuple:
    try:
        import math as _m
        x, y, z = float(v[0]), float(v[1]), float(v[2])
        n = _m.sqrt(x * x + y * y + z * z)
        if n < 1e-9:
            return (0.0, 1.0, 0.0)
        x, y, z = x / n, y / n, z / n
        return (round(x * _SUN_DIR_QUANT) / _SUN_DIR_QUANT,
                round(y * _SUN_DIR_QUANT) / _SUN_DIR_QUANT,
                round(z * _SUN_DIR_QUANT) / _SUN_DIR_QUANT)
    except Exception:
        return (0.0, 1.0, 0.0)


def _quant_color(v) -> tuple:
    try:
        return tuple(round(float(c) * _SUN_COLOR_QUANT) / _SUN_COLOR_QUANT for c in v)
    except Exception:
        return (1.0, 0.95, 0.85)


def _compile_atmosphere_compute(ctx: moderngl.Context) -> Optional[moderngl.ComputeShader]:
    src = _resolve_atmosphere_source()
    if not src:
        Logger.error(f"Atmosphere compute shader not found: {_SHADER_PATH}")
        return None
    try:
        start = src.find("GLSLPROGRAM")
        if start >= 0:
            end = src.find("ENDGLSL", start)
            if end < 0:
                Logger.error("Invalid Atmosphere.compute: no GLSLPROGRAM/ENDGLSL")
                return None
            body = src[start + len("GLSLPROGRAM"):end].strip()
        else:
            body = src.strip()
        if not body:
            Logger.error("Invalid Atmosphere.compute: no GLSLPROGRAM/ENDGLSL")
            return None
        return ctx.compute_shader(body)
    except Exception as e:
        Logger.error(f"Failed to compile Atmosphere.compute: {e}")
        return None


@ComponentRegistry.register
class Atmosphere(Component):
    _registry: list[Atmosphere] = []
    _allow_multiple = False
    _gizmo_icon_label = "ATMO"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Atmosphere", FieldType.HEADER),
            InspectorField("enabled", "Enabled", FieldType.BOOL),
            InspectorField("_intensity", "Intensity", FieldType.SLIDER, min_val=1.0, max_val=200.0, step=1.0, decimals=0),
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
        self._intensity: float = 40.0
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
        self._ctx: Optional[moderngl.Context] = None
        self._program: Optional[moderngl.ComputeShader] = None
        self._transmittance_tex: Optional[moderngl.Texture] = None
        self._sky_tex: Optional[moderngl.Texture] = None
        self._lut_sizes: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._cache_key: Optional[tuple] = None

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
        inst._intensity = float(data.get("_intensity", 40.0))
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
        inst._ctx = None
        inst._program = None
        inst._transmittance_tex = None
        inst._sky_tex = None
        inst._cache_key = None
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

    def _lut_size(self, base: int) -> int:
        return max(8, int(base * self._resolution_scale))

    def _ensure_textures(self, ctx: moderngl.Context):
        tw, th = self._lut_size(_TRANSMITTANCE_W), self._lut_size(_TRANSMITTANCE_H)
        sw, sh = self._lut_size(_SKY_W), self._lut_size(_SKY_H)
        if self._transmittance_tex is None or self._lut_sizes != (tw, th, sw, sh):
            if self._transmittance_tex is not None:
                self._transmittance_tex.release()
            if self._sky_tex is not None:
                self._sky_tex.release()
            self._transmittance_tex = ctx.texture((tw, th), 4, dtype='f4')
            self._transmittance_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._sky_tex = ctx.texture((sw, sh), 4, dtype='f4')
            self._sky_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._sky_tex.repeat_x = True
            self._sky_tex.repeat_y = False
            self._lut_sizes = (tw, th, sw, sh)
            self._cache_key = None

    def _set_uniform(self, prog, name: str, value: float):
        try:
            if name in prog:
                prog[name].value = float(value)
        except Exception:
            pass

    def _dispatch(self, ctx: moderngl.Context, sun_dir, sun_color, sun_intensity):
        tw, th, sw, sh = self._lut_sizes
        if self._program is None:
            self._program = _compile_atmosphere_compute(ctx)
            if self._program is None:
                return False
        prog = self._program
        prog["u_sun_direction"].write(np.array(sun_dir, dtype=np.float32).tobytes())
        prog["u_sun_color"].write(np.array(sun_color, dtype=np.float32).tobytes())
        prog["u_sun_intensity"].value = float(sun_intensity) * float(self._sun_intensity)
        self._set_uniform(prog, "u_ozone_factor", self._ozone_factor)
        self._set_uniform(prog, "u_aerosol_scale", self._aerosol_scale)
        self._set_uniform(prog, "u_planet_radius", self._planet_radius)
        self._set_uniform(prog, "u_atmosphere_height", self._atmosphere_height)
        self._set_uniform(prog, "u_rayleigh_scale", self._rayleigh_scale)
        self._set_uniform(prog, "u_mie_g", self._mie_anisotropy)
        self._set_uniform(prog, "u_mie_albedo", self._mie_albedo)
        self._set_uniform(prog, "u_ground_albedo", self._ground_albedo)
        self._set_uniform(prog, "u_ms_strength", self._multiscatter_strength)
        self._set_uniform(prog, "u_horizon_haze", self._horizon_haze)
        self._set_uniform(prog, "u_camera_height_km", max(float(self._camera_height_m) / 1000.0, 0.005))
        prog["u_pass"].value = 0
        self._transmittance_tex.bind_to_image(0, read=True, write=True)
        prog.run((tw + 7) // 8, (th + 7) // 8, 1)
        ctx.memory_barrier(moderngl.SHADER_IMAGE_ACCESS_BARRIER_BIT)
        prog["u_pass"].value = 1
        prog["u_transmittance_lut"] = 2
        self._transmittance_tex.use(2)
        self._sky_tex.bind_to_image(1, read=True, write=True)
        prog.run((sw + 7) // 8, (sh + 7) // 8, 1)
        ctx.memory_barrier(moderngl.SHADER_IMAGE_ACCESS_BARRIER_BIT)
        return True

    def ensure_luts(self, ctx: moderngl.Context, sun_dir, sun_color, sun_intensity) -> bool:
        if not self.enabled:
            return False
        self._ensure_textures(ctx)
        key = (_quant_dir(sun_dir),
               _quant_color(sun_color),
               round(float(sun_intensity), 3),
               self.ibl_key(), self._lut_sizes)
        if key != self._cache_key:
            self._cache_key = key
            try:
                if not self._dispatch(ctx, sun_dir, sun_color, sun_intensity):
                    self._cache_key = None
                    return False
            except Exception as e:
                Logger.error(f"Atmosphere dispatch error: {e}")
                self._cache_key = None
                return False
        return True

    def bind_sky(self, prog: moderngl.Program):
        if self._sky_tex is None or self._transmittance_tex is None:
            return
        try:
            self._sky_tex.use(3)
            if "u_sky_lut" in prog:
                prog["u_sky_lut"] = 3
            self._transmittance_tex.use(2)
            if "u_transmittance_lut" in prog:
                prog["u_transmittance_lut"] = 2
            if "u_use_atmosphere" in prog:
                prog["u_use_atmosphere"].value = 1
            if "u_atmosphere_intensity" in prog:
                prog["u_atmosphere_intensity"].value = self._intensity
            if "u_planet_radius" in prog:
                prog["u_planet_radius"].value = float(self._planet_radius)
            if "u_atmosphere_height" in prog:
                prog["u_atmosphere_height"].value = float(self._atmosphere_height)
            if "u_camera_height_km" in prog:
                prog["u_camera_height_km"].value = max(float(self._camera_height_m) / 1000.0, 0.005)
            if "u_mie_g" in prog:
                prog["u_mie_g"].value = float(self._mie_anisotropy)
            if "_SunIntensity" in prog:
                prog["_SunIntensity"].value = float(prog["_SunIntensity"].value) * self._sun_intensity
            if "_SunAngularRadius" in prog:
                prog["_SunAngularRadius"].value = float(self._sun_angular_radius)
            if "_SunLimbDarkening" in prog:
                prog["_SunLimbDarkening"].value = float(self._sun_limb_darkening)
            if "_SunConvergence" in prog:
                prog["_SunConvergence"].value = float(self._sun_convergence)
        except Exception as e:
            Logger.error(f"Atmosphere.bind_sky error: {e}")

    def _release_gl(self):
        for tex in (self._transmittance_tex, self._sky_tex):
            if tex is not None:
                try:
                    tex.release()
                except Exception:
                    pass
        if self._program is not None:
            try:
                self._program.release()
            except Exception:
                pass
        self._ctx = None
        self._transmittance_tex = None
        self._sky_tex = None
        self._program = None
        self._cache_key = None
