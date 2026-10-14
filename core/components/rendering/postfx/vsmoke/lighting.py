# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.components.lighting.lightp import Light, LightType
from core.maths.math3d import Vec3


class VolumetricSmokeLightingMixin:
    def _sun_light(self):
        sun_dir = (0.4, 0.6, 0.3)
        sun_col = (1.0, 0.95, 0.9)
        try:
            ent = self._entity
            scene = ent._scene if ent is not None else None
            if scene is None:
                return sun_dir, sun_col
            for e in scene.get_entities_with_component(Light):
                li = e.get_component(Light)
                t = e.transform
                if li is not None and t is not None and li.enabled and li.light_type == LightType.DIRECTIONAL:
                    f = t.forward
                    sun_dir = (-float(f.x), -float(f.y), -float(f.z))
                    c = li.color or [1.0, 1.0, 1.0]
                    sun_col = (float(c[0]), float(c[1]), float(c[2]))
                    break
        except Exception:
            pass
        return sun_dir, sun_col

    def _wind_tuple(self) -> tuple[float, float, float]:
        w = self._wind_dir
        try:
            if isinstance(w, Vec3):
                return (float(w.x), float(w.y), float(w.z))
            return (float(w[0]), float(w[1]), float(w[2]))
        except Exception:
            return (0.0, 1.0, 0.0)
