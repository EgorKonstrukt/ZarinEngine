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
from core.foundation.logger import Logger
_SHADERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))), "core", "shaders", "compute")
_SHADER_PATH = os.path.join(_SHADERS_DIR, "Atmosphere.compute")
def _resolve_atmosphere_source() -> Optional[str]:
    try:
        with open(_SHADER_PATH) as _f:
            return _f.read()
    except Exception:
        pass
    try:
        from core.renderer.meshd import read_compute_source
        return read_compute_source("atmosphere")
    except Exception:
        return None
_TRANSMITTANCE_W = 128
_TRANSMITTANCE_H = 32
_SKY_W = 256
_SKY_H = 128
_SUN_DIR_QUANT = 10000.0
_SUN_COLOR_QUANT = 1000.0
_GL_STATES_MAX = 4
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
class AtmosphereLutMixin:
    def _gl_state(self, ctx):
        try:
            key = id(ctx)
        except Exception:
            return None
        try:
            st = self._gl_states.get(key)
        except Exception:
            return None
        if st is not None:
            try:
                if st.get("ctx") is ctx:
                    return st
            except Exception:
                pass
            try:
                self._release_state(st)
            except Exception:
                pass
        st = {"ctx": ctx, "program": None, "trans": None, "sky": None, "dummy": None, "sizes": (0, 0, 0, 0), "cache": None}
        try:
            if len(self._gl_states) >= _GL_STATES_MAX:
                old_key = next(iter(self._gl_states))
                old = self._gl_states.pop(old_key, None)
                if old is not None:
                    try:
                        self._release_state(old)
                    except Exception:
                        pass
            self._gl_states[key] = st
        except Exception:
            pass
        return st
    @staticmethod
    def _release_state(st):
        try:
            for tex in (st.get("trans"), st.get("sky"), st.get("dummy")):
                if tex is not None:
                    try:
                        tex.release()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            prog = st.get("program")
            if prog is not None:
                try:
                    prog.release()
                except Exception:
                    pass
        except Exception:
            pass
    def _gl_state_for_program(self, prog):
        try:
            ctx = prog.ctx
        except Exception:
            return None
        try:
            st = self._gl_states.get(id(ctx))
        except Exception:
            return None
        if st is None:
            return None
        try:
            if st.get("ctx") is not ctx:
                return None
        except Exception:
            return None
        return st
    def _lut_size(self, base: int) -> int:
        return max(8, int(base * self._resolution_scale))
    def _ensure_textures(self, ctx: moderngl.Context):
        st = self._gl_state(ctx)
        if st is None:
            return None
        tw, th = self._lut_size(_TRANSMITTANCE_W), self._lut_size(_TRANSMITTANCE_H)
        sw, sh = self._lut_size(_SKY_W), self._lut_size(_SKY_H)
        if st["trans"] is None or st["sizes"] != (tw, th, sw, sh):
            if st["trans"] is not None:
                try:
                    st["trans"].release()
                except Exception:
                    pass
            if st["sky"] is not None:
                try:
                    st["sky"].release()
                except Exception:
                    pass
            st["trans"] = ctx.texture((tw, th), 4, dtype='f4')
            st["trans"].filter = (moderngl.LINEAR, moderngl.LINEAR)
            st["sky"] = ctx.texture((sw, sh), 4, dtype='f4')
            st["sky"].filter = (moderngl.LINEAR, moderngl.LINEAR)
            st["sky"].repeat_x = True
            st["sky"].repeat_y = False
            st["sizes"] = (tw, th, sw, sh)
            st["cache"] = None
            try:
                st.pop("pkey", None)
            except Exception:
                pass
        return st
    def _dummy_image_tex(self, ctx: moderngl.Context) -> moderngl.Texture:
        st = self._gl_state(ctx)
        if st is None:
            return ctx.texture((1, 1), 4, dtype='f4')
        if st["dummy"] is None:
            st["dummy"] = ctx.texture((1, 1), 4, dtype='f4')
            st["dummy"].write(b"\x00" * 16)
        return st["dummy"]
    def _set_uniform(self, prog, name: str, value: float):
        try:
            if name in prog:
                prog[name].value = float(value)
        except Exception:
            pass
    def _dispatch(self, ctx: moderngl.Context, sun_dir, sun_color, sun_intensity, skip_transmittance: bool = False):
        st = self._gl_state(ctx)
        if st is None:
            return False
        tw, th, sw, sh = st["sizes"]
        if st["program"] is None:
            st["program"] = _compile_atmosphere_compute(ctx)
            if st["program"] is None:
                return False
        prog = st["program"]
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
        dummy = self._dummy_image_tex(ctx)
        if not skip_transmittance or st["trans"] is None:
            prog["u_pass"].value = 0
            dummy.bind_to_image(1, read=True, write=False)
            st["trans"].bind_to_image(0, read=True, write=True)
            prog.run((tw + 7) // 8, (th + 7) // 8, 1)
            ctx.memory_barrier(moderngl.SHADER_IMAGE_ACCESS_BARRIER_BIT)
        prog["u_pass"].value = 1
        prog["u_transmittance_lut"] = 2
        st["trans"].use(2)
        dummy.bind_to_image(0, read=True, write=False)
        st["sky"].bind_to_image(1, read=True, write=True)
        prog.run((sw + 7) // 8, (sh + 7) // 8, 1)
        ctx.memory_barrier(moderngl.SHADER_IMAGE_ACCESS_BARRIER_BIT)
        return True
    def ensure_luts(self, ctx: moderngl.Context, sun_dir, sun_color, sun_intensity) -> bool:
        if not self.enabled:
            return False
        st = self._ensure_textures(ctx)
        if st is None:
            return False
        key = (_quant_dir(sun_dir),
               _quant_color(sun_color),
               round(float(sun_intensity), 3),
               self.ibl_key(), st["sizes"])
        if key != st["cache"]:
            pkey = (self.ibl_key(), st["sizes"])
            sky_only = st["trans"] is not None and st.get("pkey") == pkey
            st["cache"] = key
            try:
                if not self._dispatch(ctx, sun_dir, sun_color, sun_intensity, skip_transmittance=sky_only):
                    st["cache"] = None
                    return False
            except Exception as e:
                Logger.error(f"Atmosphere dispatch error: {e}")
                st["cache"] = None
                return False
            try:
                st["pkey"] = pkey
            except Exception:
                pass
        return True
    def bind_sky(self, prog: moderngl.Program):
        st = self._gl_state_for_program(prog)
        if st is None or st["sky"] is None or st["trans"] is None:
            return
        try:
            st["sky"].use(3)
            if "u_sky_lut" in prog:
                prog["u_sky_lut"] = 3
            st["trans"].use(2)
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
        try:
            states = list(self._gl_states.values())
        except Exception:
            states = []
        for st in states:
            try:
                self._release_state(st)
            except Exception:
                pass
        try:
            self._gl_states.clear()
        except Exception:
            pass
