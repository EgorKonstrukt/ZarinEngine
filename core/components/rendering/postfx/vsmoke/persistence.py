# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.maths.math3d import Vec3


class VolumetricSmokePersistenceMixin:
    def serialize(self) -> dict:
        d = super().serialize()
        w = self._wind_dir
        if isinstance(w, Vec3):
            wv = [float(w.x), float(w.y), float(w.z)]
        else:
            wv = [float(w[0]), float(w[1]), float(w[2])]
        d.update({
            "_density": self._density,
            "_opacity": self._opacity,
            "_steps": self._steps,
            "_light_steps": self._light_steps,
            "_base_octaves": self._base_octaves,
            "_ridge_octaves": self._ridge_octaves,
            "_detail_octaves": self._detail_octaves,
            "_noise_scale": self._noise_scale,
            "_evolution": self._evolution,
            "_seed": self._seed,
            "_wind_dir": wv,
            "_wind_speed": self._wind_speed,
            "_fullness": self._fullness,
            "_filaments": self._filaments,
            "_erosion": self._erosion,
            "_cavity": self._cavity,
            "_edge_softness": self._edge_softness,
            "_fade_top": self._fade_top,
            "_fade_bottom": self._fade_bottom,
            "_color_deep": list(self._color_deep),
            "_color_mid": list(self._color_mid),
            "_color_core": list(self._color_core),
            "_core_size": self._core_size,
            "_emission": self._emission,
            "_ambient": self._ambient,
            "_scatter": self._scatter,
            "_anisotropy": self._anisotropy,
            "_self_shadow": self._self_shadow,
            "_shadow_strength": self._shadow_strength,
            "_absorption": self._absorption,
            "_depth_fade": self._depth_fade,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> VolumetricSmoke:
        inst = super().deserialize(data)
        inst._density = float(data.get("_density", 0.55))
        inst._opacity = float(data.get("_opacity", 1.0))
        inst._steps = int(data.get("_steps", 28))
        inst._light_steps = int(data.get("_light_steps", 5))
        inst._base_octaves = int(data.get("_base_octaves", 4))
        inst._ridge_octaves = int(data.get("_ridge_octaves", 3))
        inst._detail_octaves = int(data.get("_detail_octaves", 2))
        inst._noise_scale = float(data.get("_noise_scale", 0.35))
        inst._evolution = float(data.get("_evolution", 0.25))
        inst._seed = float(data.get("_seed", 0.0))
        inst._wind_dir = Vec3(*data.get("_wind_dir", [0.15, 1.0, 0.05]))
        inst._wind_speed = float(data.get("_wind_speed", 0.3))
        inst._fullness = float(data.get("_fullness", 0.75))
        inst._filaments = float(data.get("_filaments", 0.55))
        inst._erosion = float(data.get("_erosion", 0.45))
        inst._cavity = float(data.get("_cavity", 0.0))
        inst._edge_softness = float(data.get("_edge_softness", 0.5))
        inst._fade_top = float(data.get("_fade_top", 0.0))
        inst._fade_bottom = float(data.get("_fade_bottom", 0.0))
        inst._color_deep = tuple(data.get("_color_deep", [0.10, 0.08, 0.30]))
        inst._color_mid = tuple(data.get("_color_mid", [0.45, 0.15, 0.55]))
        inst._color_core = tuple(data.get("_color_core", [0.30, 0.75, 0.85]))
        inst._core_size = float(data.get("_core_size", 1.0))
        inst._emission = float(data.get("_emission", 1.2))
        inst._ambient = float(data.get("_ambient", 0.25))
        inst._scatter = float(data.get("_scatter", 1.0))
        inst._anisotropy = float(data.get("_anisotropy", 0.55))
        inst._self_shadow = bool(data.get("_self_shadow", True))
        inst._shadow_strength = float(data.get("_shadow_strength", 1.0))
        inst._absorption = float(data.get("_absorption", 1.0))
        inst._depth_fade = float(data.get("_depth_fade", 2.0))
        inst._ctx = None
        inst._prog = None
        inst._vao = None
        inst._vbo = None
        inst._ibo = None
        return inst
