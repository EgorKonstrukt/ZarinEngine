# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
from core.maths.math3d import Vec3


_SUN_CACHE: dict = {}
_PLANCK_CACHE: dict = {}


def _planck_white(color_temp: float) -> list[float]:
    try:
        key = float(color_temp)
    except Exception:
        key = 5778.0
    try:
        hit = _PLANCK_CACHE.get(key)
        if hit is not None:
            return [hit[0], hit[1], hit[2]]
    except Exception:
        pass
    t = max(float(color_temp), 1000.0) / 100.0
    if t <= 66.0:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 138.5177312231 * math.log(t - 10.0) - 305.0447927307 if t > 19.0 else 0.0
    else:
        r = 329.698727446 * math.pow(t - 60.0, -0.1332047592)
        g = 288.1221695283 * math.pow(t - 60.0, -0.0755148492)
        b = 255.0
    r = max(0.0, min(255.0, r))
    g = max(0.0, min(255.0, g))
    b = max(0.0, min(255.0, b))
    m = max(r, g, b)
    if m <= 0.0:
        return [1.0, 1.0, 1.0]
    out = [r / m, g / m, b / m]
    try:
        if len(_PLANCK_CACHE) > 32:
            _PLANCK_CACHE.clear()
        _PLANCK_CACHE[key] = (out[0], out[1], out[2])
    except Exception:
        pass
    return out


def point_lumen_to_candela(lumens: float) -> float:
    return max(float(lumens), 0.0) / (4.0 * math.pi)


def spot_solid_angle(outer_angle_deg: float) -> float:
    half = math.radians(max(min(float(outer_angle_deg), 179.0), 1.0)) * 0.5
    return 2.0 * math.pi * (1.0 - math.cos(half))


def spot_lumen_to_candela(lumens: float, outer_angle_deg: float) -> float:
    return max(float(lumens), 0.0) / max(spot_solid_angle(outer_angle_deg), 1e-6)


def candela_to_lux(candela: float, distance: float) -> float:
    d = max(float(distance), 1e-3)
    return max(float(candela), 0.0) / (d * d)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def compute_sun_light(sun_dir: Vec3, color_temp: float = 5778.0, aerosol_scale: float = 1.0, use_atmosphere: bool = True, ozone_factor: float = 1.0, rayleigh_scale: float = 1.0, mie_albedo: float = 0.9) -> tuple[list[float], float]:
    try:
        _skey = (float(sun_dir.x), float(sun_dir.y), float(sun_dir.z), float(color_temp), float(aerosol_scale), bool(use_atmosphere), float(ozone_factor), float(rayleigh_scale), float(mie_albedo))
    except Exception:
        _skey = None
    if _skey is not None:
        try:
            _hit = _SUN_CACHE.get(_skey)
            if _hit is not None:
                return [_hit[0][0], _hit[0][1], _hit[0][2]], _hit[1]
        except Exception:
            pass
    color, intensity = _compute_sun_light_uncached(sun_dir, color_temp, aerosol_scale, use_atmosphere, ozone_factor, rayleigh_scale, mie_albedo)
    if _skey is not None:
        try:
            if len(_SUN_CACHE) > 128:
                _SUN_CACHE.clear()
            _SUN_CACHE[_skey] = ((float(color[0]), float(color[1]), float(color[2])), float(intensity))
        except Exception:
            pass
    return color, intensity


def _compute_sun_light_uncached(sun_dir: Vec3, color_temp: float = 5778.0, aerosol_scale: float = 1.0, use_atmosphere: bool = True, ozone_factor: float = 1.0, rayleigh_scale: float = 1.0, mie_albedo: float = 0.9) -> tuple[list[float], float]:
    elevation = float(sun_dir.y)
    vis = _smoothstep(-0.14, 0.05, elevation)
    day = _smoothstep(-0.08, 0.12, elevation)
    if use_atmosphere:
        refr = 0.0003 / max(math.tan(math.radians(max(math.degrees(max(elevation, -0.05)) + 7.31 / (math.degrees(max(elevation, -0.05)) + 4.4), 0.5))), 0.02)
        eff = max(elevation + refr * 0.3, 1e-4)
        airmass = 1.0 / (eff + 0.50572 * math.pow(math.degrees(eff) + 6.07995, -1.6364))
        airmass = min(airmass, 38.0)
        wp = _planck_white(color_temp)
        rs = max(float(rayleigh_scale), 0.0)
        ae = max(float(aerosol_scale), 0.0)
        oz = max(float(ozone_factor), 0.0)
        alb = min(max(float(mie_albedo), 0.0), 1.0)
        tau_r = [5.802e-6 * 8000.0 * rs * airmass, 13.558e-6 * 8000.0 * rs * airmass, 33.1e-6 * 8000.0 * rs * airmass]
        tau_m_ext = 3.996e-6 * 1200.0 * ae * airmass
        tau_o = [0.650e-6 * 15000.0 * oz * airmass, 1.881e-6 * 15000.0 * oz * airmass, 0.085e-6 * 15000.0 * oz * airmass]
        color = [wp[i] * math.exp(-(tau_r[i] + tau_m_ext + tau_o[i])) for i in range(3)]
        luma = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
        if luma > 1e-6:
            color = [c / luma for c in color]
        else:
            color = [1.0, 0.7, 0.4]
        tau_luma = (0.2126 * (tau_r[0] + tau_o[0]) + 0.7152 * (tau_r[1] + tau_o[1]) + 0.0722 * (tau_r[2] + tau_o[2]) + tau_m_ext * (1.0 - alb * 0.5))
        twilight = math.exp(-max(-elevation, 0.0) * 12.0) * (1.0 - day)
        sunset = [1.0, 0.32, 0.12]
        tw = min(max(twilight * 2.2, 0.0), 1.0)
        color = [color[i] + (sunset[i] - color[i]) * tw * 0.65 for i in range(3)]
    else:
        color = list(_planck_white(color_temp))
        tau_luma = 0.0
        twilight = 0.0
    intensity = 1.2 * vis * (0.55 + 0.45 * (1.0 - math.exp(-max(elevation, 0.0) * 4.0)))
    if use_atmosphere:
        intensity *= (0.5 + 0.5 * math.exp(-tau_luma))
        intensity += 0.35 * math.exp(-max(-elevation, 0.0) * 14.0) * (1.0 - day) * math.exp(-tau_luma * 0.25)
    night = 1.0 - vis
    moon_c = [0.3, 0.35, 0.55]
    k = 1.0 - night
    color = [moon_c[i] + (color[i] - moon_c[i]) * k for i in range(3)]
    intensity = max(intensity, 0.02 * (1.0 - night * 0.75))
    return color, intensity


def shader_radiance(light, transform) -> tuple[list[float], float]:
    from core.components.lighting.lightp.light import Light, DirectionalLight, SpotLight
    from core.components.lighting.lightp.shadows import AreaLight
    sc = Light._LIGHT_SCALE
    if isinstance(light, DirectionalLight) or (type(light) is Light):
        if getattr(light, "procedural_sky_lighting", False):
            color_temp = 5778.0
            aerosol = 1.0
            ozone = 1.0
            rayleigh = 1.0
            albedo = 0.9
            try:
                from core.components.rendering.environment.atmosp import Atmosphere
                try:
                    _ent = transform.entity if transform is not None else None
                    _sc = _ent._scene if _ent is not None else None
                except Exception:
                    _sc = None
                atmos = Atmosphere.for_scene(_sc)
                if atmos is not None:
                    color_temp = float(getattr(atmos, "_color_temperature", 5778.0))
                    aerosol = float(getattr(atmos, "_aerosol_scale", 1.0))
                    ozone = float(getattr(atmos, "_ozone_factor", 1.0))
                    rayleigh = float(getattr(atmos, "_rayleigh_scale", 1.0))
                    albedo = float(getattr(atmos, "_mie_albedo", 0.9))
            except Exception:
                pass
            c, i = compute_sun_light(-transform.forward, color_temp, aerosol, True, ozone, rayleigh, albedo)
            try:
                from core.components.rendering.environment.skyp import ProceduralSky
                sky = next((s for s in ProceduralSky._registry if s.enabled and s.entity and s.entity.active), None)
                if sky is not None:
                    i *= (1.0 - 0.95 * float(sky.eclipse_darkness))
            except Exception:
                pass
            return [c[0], c[1], c[2]], i * sc
        return list(light.color), light.intensity * Light.LUX_TO_RADIANCE * sc
    if isinstance(light, AreaLight):
        return list(light.color), max(float(light.intensity), 0.0) * Light.AREA_TO_RADIANCE * sc
    if isinstance(light, SpotLight):
        candela = spot_lumen_to_candela(light.intensity, light.spot_angle)
        return list(light.color), candela * Light.CANDELA_TO_RADIANCE * sc
    candela = point_lumen_to_candela(light.intensity)
    return list(light.color), candela * Light.CANDELA_TO_RADIANCE * sc
