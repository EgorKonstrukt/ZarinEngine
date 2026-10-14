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
from core.components.rendering.postfx.bloomp.threshold import BLOOM_VERT, PREFILTER_FRAG, BloomThresholdMixin
from core.components.rendering.postfx.bloomp.blur import DOWN_FRAG, UP_FRAG, BloomBlurMixin
from core.components.rendering.postfx.bloomp.composite import OUTPUT_FRAG, BloomCompositeMixin


@ComponentRegistry.register
class Bloom(BloomThresholdMixin, BloomBlurMixin, BloomCompositeMixin, GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "\u2606"
    render_type = "additive"
    _intensity_prop = "_intensity"

    def __init__(self):
        super().__init__()
        self._intensity: float = 1.0
        self._threshold: float = 1.5
        self._max_color: float = 3.8
        self._downsample: int = 2
        self._diffusion: float = 1.0
        self._dirt_texture: str = ""
        self._dirt_intensity: float = 0.0
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._prefilter_prog: Optional[moderngl.Program] = None
        self._output_prog: Optional[moderngl.Program] = None
        self._down_prog: Optional[moderngl.Program] = None
        self._up_prog: Optional[moderngl.Program] = None
        self._prefilter_vao: Optional[moderngl.VertexArray] = None
        self._output_vao: Optional[moderngl.VertexArray] = None
        self._down_vao: Optional[moderngl.VertexArray] = None
        self._up_vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._bloom_tex: Optional[moderngl.Texture] = None
        self._bloom_fbo: Optional[moderngl.Framebuffer] = None
        self._bloom_temp_tex: Optional[moderngl.Texture] = None
        self._bloom_temp_fbo: Optional[moderngl.Framebuffer] = None
        self._bloom_size: tuple[int, int] = (0, 0)
        self._mip_chain: list = []
        self._up_chain: list = []
        self._acc_tex: Optional[moderngl.Texture] = None
        self._acc_fbo: Optional[moderngl.Framebuffer] = None
        self._dirt_tex: Optional[moderngl.Texture] = None

    _res_prog_cache: dict[int, dict] = {}


__all__ = ["BLOOM_VERT", "PREFILTER_FRAG", "OUTPUT_FRAG", "DOWN_FRAG", "UP_FRAG", "Bloom"]
