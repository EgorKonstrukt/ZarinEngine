# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
import moderngl
from core.ecs import ComponentRegistry
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.maths.math3d import Vec3
from core.components.rendering.postfx.vsmoke.inspector import VolumetricSmokeInspectorMixin
from core.components.rendering.postfx.vsmoke.lighting import VolumetricSmokeLightingMixin
from core.components.rendering.postfx.vsmoke.persistence import VolumetricSmokePersistenceMixin
from core.components.rendering.postfx.vsmoke.rendering import VolumetricSmokeRenderingMixin
from core.components.rendering.postfx.vsmoke.resources import VolumetricSmokeResourcesMixin


@ComponentRegistry.register
class VolumetricSmoke(VolumetricSmokeInspectorMixin, VolumetricSmokePersistenceMixin, VolumetricSmokeResourcesMixin, VolumetricSmokeLightingMixin, VolumetricSmokeRenderingMixin, GraphicsEffect):
    _allow_multiple = True
    _gizmo_icon_label = "Sm"
    render_type = "screen"
    _intensity_prop = "_density"
    _res_cache: dict[int, dict] = {}

    def __init__(self):
        super().__init__()
        self._density: float = 0.55
        self._opacity: float = 1.0
        self._steps: int = 28
        self._light_steps: int = 5
        self._base_octaves: int = 4
        self._ridge_octaves: int = 3
        self._detail_octaves: int = 2
        self._noise_scale: float = 0.35
        self._evolution: float = 0.25
        self._seed: float = 0.0
        self._wind_dir: Vec3 = Vec3(0.15, 1.0, 0.05)
        self._wind_speed: float = 0.3
        self._fullness: float = 0.75
        self._filaments: float = 0.55
        self._erosion: float = 0.45
        self._cavity: float = 0.0
        self._edge_softness: float = 0.5
        self._fade_top: float = 0.0
        self._fade_bottom: float = 0.0
        self._color_deep: tuple[float, float, float] = (0.10, 0.08, 0.30)
        self._color_mid: tuple[float, float, float] = (0.45, 0.15, 0.55)
        self._color_core: tuple[float, float, float] = (0.30, 0.75, 0.85)
        self._core_size: float = 1.0
        self._emission: float = 1.2
        self._ambient: float = 0.25
        self._scatter: float = 1.0
        self._anisotropy: float = 0.55
        self._self_shadow: bool = True
        self._shadow_strength: float = 1.0
        self._absorption: float = 1.0
        self._depth_fade: float = 2.0
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None

    @property
    def density(self) -> float:
        return getattr(self, "_density", 0.55)

    @density.setter
    def density(self, v: float):
        self._density = float(v)

    @property
    def opacity(self) -> float:
        return getattr(self, "_opacity", 1.0)

    @opacity.setter
    def opacity(self, v: float):
        self._opacity = float(v)

    @property
    def march_steps(self) -> int:
        return getattr(self, "_steps", 28)

    @march_steps.setter
    def march_steps(self, v: int):
        self._steps = int(v)

    @property
    def emission(self) -> float:
        return getattr(self, "_emission", 1.2)

    @emission.setter
    def emission(self, v: float):
        self._emission = float(v)
