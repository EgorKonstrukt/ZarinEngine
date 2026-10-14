# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import time
import numpy as np
import moderngl
from core.maths.math3d import Vec3

_STAR_TWINKLE_ORIGIN: float = time.time()
_MOON_TEX_CACHE: dict[str, tuple[float, object]] = {}
_MOON_PENDING: dict[str, bool] = {}
_MOON_READY: dict[str, tuple[float, object]] = {}
_MOON_STAT_CACHE: dict[str, tuple[float, bool, float]] = {}
_MOON_STAT_TTL = 2.0
_WHITE_TEX: object = None


def _moon_stat(path: str) -> tuple[str, float, bool]:
    try:
        abs_path = os.path.abspath(path)
    except Exception:
        return path, 0.0, False
    try:
        import time as _time
        now = _time.monotonic()
    except Exception:
        now = 0.0
    try:
        hit = _MOON_STAT_CACHE.get(abs_path)
        if hit is not None and (now - hit[2]) < _MOON_STAT_TTL:
            return abs_path, hit[0], hit[1]
    except Exception:
        pass
    try:
        exists = os.path.exists(abs_path)
    except Exception:
        exists = False
    if not exists:
        try:
            if len(_MOON_STAT_CACHE) > 256:
                _MOON_STAT_CACHE.clear()
            _MOON_STAT_CACHE[abs_path] = (0.0, False, now)
        except Exception:
            pass
        return abs_path, 0.0, False
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError:
        mtime = 0.0
    try:
        if len(_MOON_STAT_CACHE) > 256:
            _MOON_STAT_CACHE.clear()
        _MOON_STAT_CACHE[abs_path] = (mtime, True, now)
    except Exception:
        pass
    return abs_path, mtime, True


def _load_moon_float(path: str):
    try:
        import imageio.v2 as iio
        img = iio.imread(path)
    except Exception:
        return None
    arr = np.asarray(img)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    if arr.shape[2] == 3:
        ones = np.ones((arr.shape[0], arr.shape[1], 1), dtype=arr.dtype)
        arr = np.concatenate([arr, ones], axis=2)
    else:
        arr = arr[:, :, :4]
    if arr.dtype == np.uint8:
        arr = arr.astype(np.float32) / 255.0
    elif arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    return np.ascontiguousarray(np.clip(arr, 0.0, 1.0))


def _get_moon_texture(ctx: moderngl.Context, path: str):
    if not path:
        return None
    abs_path, mtime, exists = _moon_stat(path)
    if not exists:
        return None
    cached = _MOON_TEX_CACHE.get(abs_path)
    if cached is not None:
        cm, tex = cached
        if abs(mtime - cm) < 0.001:
            return tex
        if tex is not None:
            try:
                tex.release()
            except Exception:
                pass
    try:
        ready = _MOON_READY.get(abs_path)
        if ready is not None and abs(mtime - ready[0]) < 0.001 and ready[1] is not None:
            arr = ready[1]
            try:
                _MOON_READY.pop(abs_path, None)
            except Exception:
                pass
            try:
                _MOON_PENDING.pop(abs_path, None)
            except Exception:
                pass
            h, w = arr.shape[:2]
            tex = ctx.texture((w, h), 4, arr.tobytes(), dtype="f4")
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            tex.repeat_x = False
            tex.repeat_y = False
            _MOON_TEX_CACHE[abs_path] = (mtime, tex)
            return tex
    except Exception:
        pass
    try:
        if _MOON_PENDING.get(abs_path):
            return None
        _MOON_PENDING[abs_path] = True
    except Exception:
        return None
    try:
        import threading as _threading

        def _decode():
            try:
                arr = _load_moon_float(abs_path)
            except Exception:
                arr = None
            try:
                if arr is None:
                    _MOON_TEX_CACHE[abs_path] = (mtime, None)
                else:
                    if len(_MOON_READY) > 4:
                        _MOON_READY.clear()
                    _MOON_READY[abs_path] = (mtime, arr)
            except Exception:
                pass
            finally:
                try:
                    _MOON_PENDING.pop(abs_path, None)
                except Exception:
                    pass

        _t = _threading.Thread(target=_decode, daemon=True)
        _t.start()
    except Exception:
        try:
            _MOON_PENDING.pop(abs_path, None)
        except Exception:
            pass
    return None


def _get_white_tex(ctx: moderngl.Context):
    global _WHITE_TEX
    if _WHITE_TEX is None:
        _WHITE_TEX = ctx.texture((1, 1), 3, b"\xff\xff\xff")
    return _WHITE_TEX


class ProceduralSkyCloudsMixin:

    @property
    def twinkle_time(self) -> float:
        return ((time.time() - _STAR_TWINKLE_ORIGIN) % 1000.0) * self.star_twinkle_speed

    @property
    def star_pole(self) -> Vec3:
        self._update_time_cache()
        return self._star_pole

    @property
    def star_rotation(self) -> float:
        self._update_time_cache()
        return self._star_rotation

    def _night_settings_key(self) -> tuple:
        self._update_time_cache()
        try:
            _md = self._moon_dir
            _mqt = (round(float(_md.x), 4), round(float(_md.y), 4), round(float(_md.z), 4))
        except Exception:
            _mqt = tuple(self._moon_dir)
        return (
            self.night_sky_enabled, self.night_exposure,
            self.star_enabled, self.star_density, self.star_intensity,
            self.star_scale, self.star_twinkle, self.star_twinkle_speed, self.star_seed,
            tuple(self.star_color),
            tuple(self.star_pole), round(self.star_rotation, 3),
            self.milky_way_enabled, self.milky_way_intensity,
            tuple(self.milky_way_pole),
            self.moon_enabled, _mqt,
            self.moon_size, self.moon_intensity,
            round(float(self._moon_phase), 4), self.moon_texture_path,
        )

    def _apply_night_sky(self, prog, ctx=None):
        self._sync_sun_light()
        def f(name, val):
            if name in prog:
                prog[name].value = float(val)

        def v3(name, val):
            if name in prog:
                if isinstance(val, Vec3):
                    val = [val.x, val.y, val.z]
                prog[name].write(np.array(val, dtype=np.float32).tobytes())

        f("_NightSkyEnabled", 1.0 if self.night_sky_enabled else 0.0)
        f("_NightExposure", self.night_exposure)
        f("_StarEnabled", 1.0 if self.star_enabled else 0.0)
        f("_StarDensity", self.star_density)
        f("_StarIntensity", self.star_intensity)
        f("_StarScale", self.star_scale)
        f("_StarTwinkle", self.star_twinkle)
        f("_StarSeed", self.star_seed)
        v3("_StarColor", self.star_color)
        v3("_StarPole", self.star_pole)
        f("_StarRotation", self.star_rotation)
        f("_MilkyWayEnabled", 1.0 if self.milky_way_enabled else 0.0)
        f("_MilkyWayIntensity", self.milky_way_intensity)
        v3("_MilkyWayPole", self.milky_way_pole)
        f("_MoonEnabled", 1.0 if self.moon_enabled else 0.0)
        v3("_MoonDirection", self._moon_dir)
        f("_MoonSize", self.moon_size)
        f("_MoonIntensity", self.moon_intensity)
        f("_MoonPhase", self._moon_phase)
        if ctx is not None and "u_moon_tex" in prog:
            moon_tex = _get_moon_texture(ctx, self.moon_texture_path)
            if moon_tex is None:
                moon_tex = _get_white_tex(ctx)
            moon_tex.use(4)
            prog["u_moon_tex"].value = 4
            prog["u_use_moon_tex"].value = 1.0 if self.moon_texture_path else 0.0
        if "u_time" in prog:
            prog["u_time"].value = self.twinkle_time
