# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import os
import time
from enum import Enum

import moderngl
from dataclasses import dataclass
from typing import Any, Optional


_MTIME_CACHE: dict[str, tuple[float, float]] = {}
_MTIME_TTL = 2.0
_SETTINGS_CACHE: dict[str, tuple[float, TextureImportSettings]] = {}


class FilterMode(Enum):
    POINT = "point"
    BILINEAR = "bilinear"
    TRILINEAR = "trilinear"


class WrapMode(Enum):
    REPEAT = "repeat"
    CLAMP = "clamp"
    MIRRORED_REPEAT = "mirrored_repeat"


class CompressionQuality(Enum):
    NONE = "none"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


DEFAULT_SETTINGS = {
    "filter_mode": "trilinear",
    "anisotropic": 1,
    "max_size": 2048,
    "wrap_mode": "clamp",
    "compression": "none",
    "srgb": True,
}


@dataclass
class TextureImportSettings:
    filter_mode: str = "trilinear"
    anisotropic: int = 1
    max_size: int = 2048
    wrap_mode: str = "clamp"
    compression: str = "none"
    srgb: bool = True

    @classmethod
    def for_file(cls, path: str) -> TextureImportSettings:
        import_path = path + ".import"
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        try:
            mtime = cls.import_mtime(path)
        except Exception:
            mtime = 0.0
        try:
            hit = _SETTINGS_CACHE.get(import_path)
            if hit is not None and abs(hit[0] - mtime) < 0.001:
                cached_settings = hit[1]
                fresh = cls()
                fresh.filter_mode = cached_settings.filter_mode
                fresh.anisotropic = cached_settings.anisotropic
                fresh.max_size = cached_settings.max_size
                fresh.wrap_mode = cached_settings.wrap_mode
                fresh.compression = cached_settings.compression
                fresh.srgb = cached_settings.srgb
                return fresh
        except Exception:
            pass
        settings = cls()
        if os.path.exists(import_path):
            try:
                with open(import_path) as f:
                    data = json.load(f)
                settings.filter_mode = data.get("filter_mode", settings.filter_mode)
                settings.anisotropic = data.get("anisotropic", settings.anisotropic)
                settings.max_size = data.get("max_size", settings.max_size)
                settings.wrap_mode = data.get("wrap_mode", settings.wrap_mode)
                settings.compression = data.get("compression", settings.compression)
                settings.srgb = data.get("srgb", settings.srgb)
            except Exception:
                pass
        try:
            _SETTINGS_CACHE[import_path] = (mtime, settings)
            if len(_SETTINGS_CACHE) > 1024:
                _SETTINGS_CACHE.clear()
                _SETTINGS_CACHE[import_path] = (mtime, settings)
        except Exception:
            pass
        return settings

    @staticmethod
    def import_mtime(path: str) -> float:
        import_path = path + ".import"
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        try:
            hit = _MTIME_CACHE.get(import_path)
            if hit is not None and (now - hit[1]) < _MTIME_TTL:
                return hit[0]
        except Exception:
            pass
        try:
            mtime = os.path.getmtime(import_path)
        except OSError:
            mtime = 0.0
        try:
            _MTIME_CACHE[import_path] = (mtime, now)
            if len(_MTIME_CACHE) > 2048:
                _MTIME_CACHE.clear()
                _MTIME_CACHE[import_path] = (mtime, now)
        except Exception:
            pass
        return mtime

    def apply_to_texture(self, tex: moderngl.Texture) -> None:
        if self.filter_mode == "point":
            tex.build_mipmaps()
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        elif self.filter_mode == "bilinear":
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        else:
            tex.build_mipmaps()
            tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        # Anisotropic
        if self.anisotropic > 1:
            try:
                tex.anisotropy = float(self.anisotropic)
            except Exception:
                pass
        # Wrap
        repeat = self.wrap_mode != "clamp"
        tex.repeat_x = repeat
        tex.repeat_y = repeat

    def to_dict(self) -> dict:
        return {
            "filter_mode": self.filter_mode,
            "anisotropic": self.anisotropic,
            "max_size": self.max_size,
            "wrap_mode": self.wrap_mode,
            "compression": self.compression,
            "srgb": self.srgb,
        }
