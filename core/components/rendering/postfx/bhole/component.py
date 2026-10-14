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
from core.components.rendering.postfx.bhole.inspector import BlackHoleInspectorMixin
from core.components.rendering.postfx.bhole.persistence import BlackHolePersistenceMixin
from core.components.rendering.postfx.bhole.rendering import BlackHoleRenderingMixin
from core.components.rendering.postfx.bhole.resources import BlackHoleResourcesMixin


@ComponentRegistry.register
class BlackHole(BlackHoleInspectorMixin, BlackHolePersistenceMixin, BlackHoleResourcesMixin, BlackHoleRenderingMixin, GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "BH"
    render_type = "screen"
    _res_cache: dict[int, dict] = {}

    def __init__(self):
        super().__init__()
        self._schwarzschild_radius: float = 2.0
        self._lensing_strength: float = 1.0
        self._show_disk: bool = True
        self._disk_inner: float = 3.0
        self._disk_outer: float = 8.0
        self._disk_brightness: float = 2.2
        self._inner_color: tuple[float, float, float] = (0.7, 0.82, 1.0)
        self._outer_color: tuple[float, float, float] = (1.0, 0.45, 0.12)
        self._rotation_speed: float = 0.6
        self._doppler_strength: float = 1.0
        self._turbulence: float = 0.7
        self._photon_intensity: float = 3.0
        self._photon_width: float = 0.08
        self._fringe: float = 0.02
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None

    @property
    def schwarzschild_radius(self) -> float:
        return getattr(self, "_schwarzschild_radius", 2.0)

    @schwarzschild_radius.setter
    def schwarzschild_radius(self, v: float):
        self._schwarzschild_radius = float(v)

    @property
    def lensing_strength(self) -> float:
        return getattr(self, "_lensing_strength", 1.0)

    @lensing_strength.setter
    def lensing_strength(self, v: float):
        self._lensing_strength = float(v)

    @property
    def show_disk(self) -> bool:
        return getattr(self, "_show_disk", True)

    @show_disk.setter
    def show_disk(self, v: bool):
        self._show_disk = bool(v)

    @property
    def disk_brightness(self) -> float:
        return getattr(self, "_disk_brightness", 2.2)

    @disk_brightness.setter
    def disk_brightness(self, v: float):
        self._disk_brightness = float(v)

    @property
    def rotation_speed(self) -> float:
        return getattr(self, "_rotation_speed", 0.6)

    @rotation_speed.setter
    def rotation_speed(self, v: float):
        self._rotation_speed = float(v)

    @property
    def photon_intensity(self) -> float:
        return getattr(self, "_photon_intensity", 3.0)

    @photon_intensity.setter
    def photon_intensity(self, v: float):
        self._photon_intensity = float(v)
