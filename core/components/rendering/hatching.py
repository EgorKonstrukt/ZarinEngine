# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.ecs import ComponentRegistry
from core.components.rendering.graphics_effect import GraphicsEffect
from core.components.inspector_meta import FieldType, InspectorField


HATCHING_VERT = """
#version 460 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

HATCHING_FRAG = """
#version 460 core
uniform sampler2D u_input_tex;
uniform vec2 u_pixel_size;
uniform float u_intensity;
uniform float u_spacing;
uniform float u_line_width;
uniform float u_wobble;
uniform float u_edge_threshold;
uniform float u_edge_strength;
uniform vec3 u_ink_color;
uniform vec3 u_paper_color;
uniform int u_layers;
in vec2 v_uv;
out vec4 frag_color;

float luma(vec3 c) {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

vec2 sobel_grad(vec2 uv, vec2 px) {
    float tl = luma(texture(u_input_tex, uv + vec2(-1.0, -1.0) * px).rgb);
    float t  = luma(texture(u_input_tex, uv + vec2( 0.0, -1.0) * px).rgb);
    float tr = luma(texture(u_input_tex, uv + vec2( 1.0, -1.0) * px).rgb);
    float l  = luma(texture(u_input_tex, uv + vec2(-1.0,  0.0) * px).rgb);
    float r  = luma(texture(u_input_tex, uv + vec2( 1.0,  0.0) * px).rgb);
    float bl = luma(texture(u_input_tex, uv + vec2(-1.0,  1.0) * px).rgb);
    float b  = luma(texture(u_input_tex, uv + vec2( 0.0,  1.0) * px).rgb);
    float br = luma(texture(u_input_tex, uv + vec2( 1.0,  1.0) * px).rgb);
    float gx = (tr + 2.0 * r + br) - (tl + 2.0 * l + bl);
    float gy = (bl + 2.0 * b + br) - (tl + 2.0 * t + tr);
    return vec2(gx, gy);
}

float hash1(float f) {
    return fract(sin(f * 127.1) * 43758.5453);
}

float stroke(vec2 pos, vec2 dir, float spacing, float width, float wobble, float seed) {
    float x = dot(pos, dir);
    float y = dot(pos, vec2(-dir.y, dir.x));
    float jitter = wobble * 0.5;
    float n1 = hash1(floor(y * 0.04) + seed);
    float n2 = hash1(floor(y * 0.04) + seed + 100.0);
    float wx = wobble * (n1 - 0.5);
    float d = abs(fract((x + wx) / spacing + n2 * 0.3) * spacing - spacing * 0.5);
    return 1.0 - smoothstep(0.0, width, d);
}

void main() {
    vec2 px = u_pixel_size;
    vec3 scene = texture(u_input_tex, v_uv).rgb;
    float lum = luma(scene);
    vec2 g = sobel_grad(v_uv, px);
    float edge_mag = length(g);

    float smoothness = 0.02;
    float angle = atan(g.y, g.x);
    vec2 flow_dir = vec2(-sin(angle), cos(angle));

    vec2 fixed_dir = vec2(1.0, 0.0);
    float blend = smoothstep(smoothness, smoothness * 5.0, edge_mag);
    vec2 dir = normalize(mix(fixed_dir, flow_dir, blend));

    vec2 pos = v_uv / u_pixel_size;
    float total = 0.0;
    float count = 0.0;

    for (int i = 0; i < 8; i++) {
        if (i >= u_layers) break;
        float fi = float(i);
        float th = (fi + 1.0) / (float(u_layers) + 1.0);
        if (lum > 1.0 - th) continue;

        float a = fi * 0.08;
        float ca = cos(a);
        float sa = sin(a);
        vec2 d = vec2(dir.x * ca - dir.y * sa, dir.x * sa + dir.y * ca);

        float s = u_spacing * (1.0 + fi * 0.1 + hash1(fi * 3.0) * u_wobble * 0.2);
        float w = u_line_width * (0.8 + hash1(fi * 7.0) * 0.4);
        float wob = u_wobble * (0.3 + hash1(fi * 11.0) * 0.7);
        float v = stroke(pos, d, s, w, wob, fi * 13.0);
        total += v;
        count += 1.0;
    }

    float hatch = count > 0.0 ? total / count : 0.0;

    float outline = smoothstep(u_edge_threshold * 0.5, u_edge_threshold * 2.0, edge_mag);
    float darkness = max(hatch, outline * u_edge_strength);
    darkness = clamp(darkness * u_intensity, 0.0, 1.0);

    frag_color = vec4(mix(u_paper_color, u_ink_color, darkness), 1.0);
}
"""


@ComponentRegistry.register
class Hatching(GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "Ht"
    render_type = "screen"
    _intensity_prop = "_intensity"

    def __init__(self):
        super().__init__()
        self._intensity: float = 1.0
        self._spacing: float = 8.0
        self._line_width: float = 2.0
        self._wobble: float = 0.5
        self._edge_threshold: float = 0.1
        self._edge_strength: float = 1.0
        self._layers: int = 5
        self._ink_color = (0.0, 0.0, 0.0)
        self._paper_color = (1.0, 1.0, 1.0)
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("_intensity", "Intensity", FieldType.FLOAT, min_val=0.0, max_val=3.0, step=0.05, decimals=3),
            InspectorField("_spacing", "Spacing", FieldType.FLOAT, min_val=1.0, max_val=32.0, step=1.0, decimals=0),
            InspectorField("_line_width", "Line Width", FieldType.FLOAT, min_val=0.5, max_val=8.0, step=0.5, decimals=1),
            InspectorField("_wobble", "Wobble", FieldType.FLOAT, min_val=0.0, max_val=3.0, step=0.1, decimals=2),
            InspectorField("_edge_threshold", "Edge Threshold", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.05, decimals=3),
            InspectorField("_edge_strength", "Edge Strength", FieldType.FLOAT, min_val=0.0, max_val=3.0, step=0.1, decimals=2),
            InspectorField("_layers", "Layers", FieldType.INT, min_val=1, max_val=8, step=1, decimals=0),
            InspectorField("_ink_color", "Ink Color", FieldType.COLOR),
            InspectorField("_paper_color", "Paper Color", FieldType.COLOR),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_intensity": self._intensity,
            "_spacing": self._spacing,
            "_line_width": self._line_width,
            "_wobble": self._wobble,
            "_edge_threshold": self._edge_threshold,
            "_edge_strength": self._edge_strength,
            "_layers": self._layers,
            "_ink_color": list(self._ink_color),
            "_paper_color": list(self._paper_color),
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> Hatching:
        inst = super().deserialize(data)
        inst._intensity = float(data.get("_intensity", 1.0))
        inst._spacing = float(data.get("_spacing", 8.0))
        inst._line_width = float(data.get("_line_width", 2.0))
        inst._wobble = float(data.get("_wobble", 0.5))
        inst._edge_threshold = float(data.get("_edge_threshold", 0.1))
        inst._edge_strength = float(data.get("_edge_strength", 1.0))
        inst._layers = int(data.get("_layers", 5))
        inst._ink_color = tuple(data.get("_ink_color", [0.0, 0.0, 0.0]))
        inst._paper_color = tuple(data.get("_paper_color", [1.0, 1.0, 1.0]))
        inst._ctx = None
        inst._prog = None
        inst._vao = None
        inst._vbo = None
        inst._ibo = None
        return inst

    _res_cache: dict[int, dict] = {}

    def _ensure_resources(self, ctx: moderngl.Context):
        ctx_id = id(ctx)
        cached = self._res_cache.get(ctx_id)
        if cached is not None:
            self._ctx = ctx
            self._prog = cached['_prog']
            self._vao = cached['_vao']
            self._vbo = cached['_vbo']
            self._ibo = cached['_ibo']
            return
        self._ctx = ctx
        self._prog = ctx.program(
            vertex_shader=HATCHING_VERT,
            fragment_shader=HATCHING_FRAG
        )
        verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._vao = ctx.vertex_array(
            self._prog,
            [(self._vbo, '2f', 'in_position')],
            self._ibo
        )
        self._res_cache[ctx_id] = {
            '_prog': self._prog,
            '_vao': self._vao,
            '_vbo': self._vbo,
            '_ibo': self._ibo,
        }
        if len(self._res_cache) > 4:
            oldest = next(iter(self._res_cache))
            for obj in self._res_cache[oldest].values():
                if obj is not None and hasattr(obj, 'release'):
                    try:
                        obj.release()
                    except Exception:
                        pass
            del self._res_cache[oldest]

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        self._ensure_resources(ctx)
        tex = input_tex if input_tex is not None else scene_color_tex
        self._prog["u_input_tex"] = 0
        tex.use(0)
        if "u_pixel_size" in self._prog:
            self._prog["u_pixel_size"].value = (1.0 / viewport_w, 1.0 / viewport_h)
        if "u_intensity" in self._prog:
            self._prog["u_intensity"].value = self._intensity
        if "u_spacing" in self._prog:
            self._prog["u_spacing"].value = self._spacing
        if "u_line_width" in self._prog:
            self._prog["u_line_width"].value = self._line_width
        if "u_wobble" in self._prog:
            self._prog["u_wobble"].value = self._wobble
        if "u_edge_threshold" in self._prog:
            self._prog["u_edge_threshold"].value = self._edge_threshold
        if "u_edge_strength" in self._prog:
            self._prog["u_edge_strength"].value = self._edge_strength
        if "u_layers" in self._prog:
            self._prog["u_layers"].value = self._layers
        if "u_ink_color" in self._prog:
            self._prog["u_ink_color"].value = tuple(self._ink_color)
        if "u_paper_color" in self._prog:
            self._prog["u_paper_color"].value = tuple(self._paper_color)
        ctx.disable(moderngl.BLEND)
        self._vao.render()

    def _release_gl(self):
        for obj in (self._prog, self._vao, self._vbo, self._ibo):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._ctx = None
        self._prog = None
        self._vao = None
        self._vbo = None
        self._ibo = None
