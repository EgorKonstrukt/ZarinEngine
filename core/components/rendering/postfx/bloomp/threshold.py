# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.components.inspector_meta import FieldType, InspectorField


BLOOM_VERT = """
\x23version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

PREFILTER_FRAG = """
\x23version 330 core
uniform sampler2D u_input_tex;
uniform float u_threshold;
uniform float u_max_color;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec3 color = texture(u_input_tex, v_uv).rgb;
    color = min(vec3(u_max_color), color);
    float brightness = max(max(color.r, color.g), color.b);
    float rq = clamp(brightness - (u_threshold - 0.2), 0.0, 0.4);
    rq = (rq * rq) * 1.25;
    color *= max(rq, brightness - u_threshold) / max(brightness, 0.0001);
    frag_color = vec4(color, 1.0);
}
"""


class BloomThresholdMixin:
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Bloom", FieldType.HEADER),
            InspectorField("_intensity", "Intensity", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.1, decimals=2),
            InspectorField("_threshold", "Threshold", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.05, decimals=3),
            InspectorField("_max_color", "Max Color", FieldType.FLOAT, min_val=0.5, max_val=10.0, step=0.1, decimals=2),
            InspectorField("_downsample", "Downsample", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("_diffusion", "Diffusion", FieldType.FLOAT, min_val=0.5, max_val=5.0, step=0.1, decimals=2),
            InspectorField("", "Dirt", FieldType.HEADER),
            InspectorField("_dirt_texture", "Dirt Texture", FieldType.RESOURCE_PATH, min_val=0.0, max_val=0.0, step=0.0, decimals=0, file_filter="Images (*.png *.jpg *.jpeg *.tga *.bmp)"),
            InspectorField("_dirt_intensity", "Dirt Intensity", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_intensity": self._intensity,
            "_threshold": self._threshold,
            "_max_color": self._max_color,
            "_downsample": self._downsample,
            "_diffusion": self._diffusion,
            "_dirt_texture": self._dirt_texture,
            "_dirt_intensity": self._dirt_intensity,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst._intensity = float(data.get("_intensity", 1.0))
        inst._threshold = float(data.get("_threshold", 1.5))
        inst._max_color = float(data.get("_max_color", 3.8))
        inst._downsample = int(data.get("_downsample", 2))
        inst._diffusion = float(data.get("_diffusion", 1.0))
        inst._dirt_texture = str(data.get("_dirt_texture", "") or "")
        inst._dirt_intensity = float(data.get("_dirt_intensity", 0.0))
        inst._prog = None
        inst._prefilter_prog = None
        inst._output_prog = None
        inst._down_prog = None
        inst._up_prog = None
        inst._prefilter_vao = None
        inst._output_vao = None
        inst._down_vao = None
        inst._up_vao = None
        inst._vbo = None
        inst._ibo = None
        inst._bloom_tex = None
        inst._bloom_fbo = None
        inst._bloom_temp_tex = None
        inst._bloom_temp_fbo = None
        inst._bloom_size = (0, 0)
        inst._mip_chain = []
        inst._up_chain = []
        inst._acc_tex = None
        inst._acc_fbo = None
        inst._dirt_tex = None
        return inst

    @property
    def intensity(self) -> float:
        return getattr(self, "_intensity", 1.0)

    @intensity.setter
    def intensity(self, v: float):
        self._intensity = v

    @property
    def threshold(self) -> float:
        return getattr(self, "_threshold", 0.8)

    @threshold.setter
    def threshold(self, v: float):
        self._threshold = v
