# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import time
import numpy as np
import moderngl
from core.maths.math3d import Mat4, Vec3
from core.components.lighting.lightp import Light


def _set_vec3(prog, name, value):
    if name not in prog:
        return
    if isinstance(value, (list, tuple)):
        arr = np.array([float(value[0]), float(value[1]), float(value[2])], dtype=np.float32)
    else:
        arr = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    prog[name].write(arr.tobytes())


def _set_float(prog, name, value):
    if name in prog:
        prog[name].value = float(value)


class WaterSurfacingMixin:
    def _resolve_wind(self, wind_zones, wx, wz, t):
        best = None
        if wind_zones:
            for wz_comp in wind_zones:
                try:
                    s = wz_comp.sample(wx, wz, t)
                except Exception:
                    s = None
                if not s or s.get("strength", 0.0) <= 0.0:
                    continue
                strength = s.get("strength", 1.0)
                if best is None or strength > best[0]:
                    best = (strength, s)
        if best is not None:
            s = best[1]
            return {
                "dir": s.get("dir", (1.0, 0.0)),
                "speed": s.get("speed", 0.0),
                "turbulence": s.get("turbulence", 0.0),
                "gust": s.get("gust", 0.0),
                "influence": s.get("alignment", self.wind_influence),
            }
        ang = math.radians(self.wind_direction)
        dx, dz = math.cos(ang), math.sin(ang)
        gust = self.wind_gust * (0.5 + 0.5 * math.sin(2.0 * math.pi * 0.15 * t))
        return {
            "dir": (dx, dz),
            "speed": self.wind_speed,
            "turbulence": self.wind_turbulence,
            "gust": max(0.0, gust),
            "influence": self.wind_influence,
        }

    def get_wave_uniforms(self, t, wx, wz, wind_zones=None):
        wind = self._resolve_wind(wind_zones, wx, wz, t)
        wdir = wind["dir"]
        wind_speed = wind["speed"]
        wind_infl = wind["influence"]
        wind_norm = min(max(wind_speed / 60.0, 0.0), 1.0)
        wind_align = min(1.0, wind_infl + wind_norm * 0.8)
        n = min(len(self.waves), 8)
        dirs = np.zeros((8, 2), dtype=np.float32)
        params = np.zeros((8, 4), dtype=np.float32)
        for i in range(n):
            w = self.waves[i]
            ang = math.radians(float(w.get("direction", 0.0)))
            dirs[i] = [math.cos(ang), math.sin(ang)]
            params[i] = [
                float(w.get("amplitude", 0.0)),
                float(w.get("wavelength", 1.0)),
                float(w.get("speed", 1.0)),
                float(w.get("steepness", 0.0)),
            ]
        return {
            "wave_count": n,
            "dirs": dirs,
            "params": params,
            "wind_dir": (float(wdir[0]), float(wdir[1])),
            "wind_speed": float(wind_speed),
            "wind_gust": float(wind["gust"]),
            "wind_turbulence": float(wind["turbulence"]),
            "wind_align": float(wind_align),
            "choppiness": float(self.choppiness),
            "macro_wave": float(self.macro_wave),
            "chaos": float(self.chaos),
        }

    def render_water(self, ctx, shaders, view_mat, proj_mat, dir_light, cam_pos,
                      water_mesh, scene_color_tex, scene_depth_tex, viewport_size, cam_near, cam_far,
                      wind_zones=None, lights=None, chunk_models=None, is_box=False,
                      sim_tex=None, sim_grid_center=None, sim_grid_size=None, sim_disp_scale=1.0, sim_normal_scale=1.0):
        prog = shaders.get_or_compile(self.material_path) if shaders else None
        if not prog:
            return
        if dir_light:
            dl, dt = dir_light
            sun_dir = -dt.forward
            if "_SunDirection" in prog:
                prog["_SunDirection"].write(np.array([sun_dir.x, sun_dir.y, sun_dir.z], dtype=np.float32).tobytes())
            if "_SunColor" in prog:
                sc, si = Light.shader_radiance(dl, dt)
                prog["_SunColor"].write(np.array(sc, dtype=np.float32).tobytes())
                if "_SunIntensity" in prog:
                    prog["_SunIntensity"].value = si
        t = time.time() - self._time_origin
        if "u_time" in prog:
            prog["u_time"].value = t
        if "_Time" in prog:
            prog["_Time"].value = t
        tr = self.transform
        water_y = tr.position.y if tr else 0.0
        if chunk_models:
            models = list(chunk_models)
            water_wx, water_wz = cam_pos.x, cam_pos.z
        elif self.infinite_ocean and self.surface_type == "Ocean":
            models = [Mat4.scale(Vec3(self.ocean_size, 1.0, self.ocean_size)) * \
                      Mat4.translation(Vec3(cam_pos.x, water_y, cam_pos.z))]
            water_wx, water_wz = cam_pos.x, cam_pos.z
        else:
            models = [tr.world_matrix if tr else Mat4.identity()]
            water_wx = tr.position.x if tr else 0.0
            water_wz = tr.position.z if tr else 0.0
        if "u_view" in prog:
            prog["u_view"].write(view_mat.to_f32().tobytes())
        if "u_proj" in prog:
            prog["u_proj"].write(proj_mat.to_f32().tobytes())
        if "u_camera_pos" in prog:
            prog["u_camera_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        ws = self.get_wave_uniforms(t, water_wx, water_wz, wind_zones)
        if "_WaveCount" in prog:
            prog["_WaveCount"].value = ws["wave_count"]
            prog["_WaveDirection"].write(ws["dirs"].tobytes())
            prog["_WaveParams"].write(ws["params"].tobytes())
        if "_WindDir" in prog:
            prog["_WindDir"].write(np.array([ws["wind_dir"][0], ws["wind_dir"][1]], dtype=np.float32).tobytes())
        _set_float(prog, "_WindSpeed", ws["wind_speed"])
        _set_float(prog, "_WindGust", ws["wind_gust"])
        _set_float(prog, "_WindTurbulence", ws["wind_turbulence"])
        _set_float(prog, "_WindAlign", ws["wind_align"])
        _set_float(prog, "_Choppiness", self.choppiness)
        _set_float(prog, "_Caustics", self.caustics)
        _set_float(prog, "_MacroWave", self.macro_wave)
        _set_float(prog, "_Chaos", self.chaos)
        _set_float(prog, "_DetailScale", self.detail_scale)
        _set_float(prog, "_DetailOctaves", self.detail_octaves)
        _set_float(prog, "_DetailFade", self.detail_fade)
        if "_IsBox" in prog:
            prog["_IsBox"].value = 1 if is_box else 0
        if sim_tex is not None and "_SimTex" in prog and sim_grid_center is not None and sim_grid_size is not None:
            sim_tex.use(17)
            prog["_SimTex"] = 17
            prog["_HasSim"].value = 1.0
            prog["_SimGridCenter"] = (float(sim_grid_center[0]), float(sim_grid_center[2]))
            prog["_SimGridSize"].value = float(sim_grid_size)
            prog["_SimDispScale"].value = float(sim_disp_scale)
            prog["_SimNormalScale"].value = float(sim_normal_scale)
        elif "_HasSim" in prog:
            prog["_HasSim"].value = 0.0
        if "_LightCount" in prog:
            from core.components.lighting import LightType
            lpos = np.zeros((16, 3), dtype=np.float32)
            lcol = np.zeros((16, 3), dtype=np.float32)
            lint = np.zeros(16, dtype=np.float32)
            lrange = np.zeros(16, dtype=np.float32)
            ldir = np.zeros((16, 3), dtype=np.float32)
            lspot = np.full(16, -1.0, dtype=np.float32)
            count = 0
            if lights:
                for l, lt in lights:
                    if not l or not l.enabled or lt is None:
                        continue
                    if l.light_type == LightType.DIRECTIONAL:
                        continue
                    if count >= 16:
                        break
                    pos = lt.position
                    lpos[count] = [pos.x, pos.y, pos.z]
                    col = l.color if isinstance(l.color, (list, tuple)) else [1.0, 1.0, 1.0]
                    lcol[count] = [float(col[0]), float(col[1]), float(col[2])]
                    lint[count] = Light.shader_radiance(l, lt)[1]
                    lrange[count] = max(float(l.range), 0.001)
                    if l.light_type == LightType.SPOT:
                        fwd = lt.forward
                        ldir[count] = [fwd.x, fwd.y, fwd.z]
                        half = math.radians(max(float(l.spot_angle), 1.0)) * 0.5
                        lspot[count] = math.cos(half)
                    count += 1
            prog["_LightCount"].value = count
            prog["_LightPos"].write(lpos.tobytes())
            prog["_LightColor"].write(lcol.tobytes())
            prog["_LightIntensity"].write(lint.tobytes())
            prog["_LightRange"].write(lrange.tobytes())
            prog["_LightDir"].write(ldir.tobytes())
            prog["_LightSpotCos"].write(lspot.tobytes())
        _set_vec3(prog, "_DeepColor", self.deep_color)
        _set_vec3(prog, "_ShallowColor", self.shallow_color)
        _set_vec3(prog, "_FoamColor", self.foam_color)
        _set_vec3(prog, "_SSSColor", self.sss_color)
        _set_vec3(prog, "_HorizonColor", self.horizon_color)
        _set_float(prog, "_Smoothness", self.smoothness)
        _set_float(prog, "_Distortion", self.distortion)
        _set_float(prog, "_NormalStrength", self.normal_strength)
        _set_float(prog, "_WaveTiling", self.wave_tiling)
        _set_float(prog, "_WarpAmount", self.warp_amount)
        _set_float(prog, "_DetailSpeed", self.detail_speed)
        _set_float(prog, "_RefractStrength", self.refract_strength)
        _set_float(prog, "_FresnelPower", self.fresnel_power)
        _set_float(prog, "_FoamStrength", self.foam_strength)
        _set_float(prog, "_Specular", self.specular)
        _set_float(prog, "_ShoreFade", self.shore_fade)
        if scene_color_tex is not None and "_SceneColor" in prog:
            scene_color_tex.use(15)
            prog["_SceneColor"] = 15
            if "_HasScene" in prog:
                prog["_HasScene"].value = 1
        elif "_HasScene" in prog:
            prog["_HasScene"].value = 0
        if scene_depth_tex is not None and "_SceneDepth" in prog:
            scene_depth_tex.use(16)
            prog["_SceneDepth"] = 16
        if "_ViewportSize" in prog:
            prog["_ViewportSize"].value = (float(viewport_size[0]), float(viewport_size[1]))
        if "_CamNear" in prog:
            prog["_CamNear"].value = float(cam_near)
        if "_CamFar" in prog:
            prog["_CamFar"].value = float(cam_far)
        old_depth_mask = ctx.depth_mask
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        ctx.disable(moderngl.CULL_FACE)
        try:
            for model in models:
                if "u_model" in prog:
                    prog["u_model"].write(model.to_f32().tobytes())
                water_mesh.render(prog)
        finally:
            ctx.enable(moderngl.CULL_FACE)
            ctx.disable(moderngl.BLEND)
            ctx.depth_mask = old_depth_mask
