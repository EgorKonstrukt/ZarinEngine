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
from core.ecs.ecs import ComponentRegistry
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.components.inspector_meta import FieldType, InspectorField


BLOOM_VERT = """
#version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

PREFILTER_FRAG = """
#version 330 core
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

OUTPUT_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
uniform sampler2D u_dirt_tex;
uniform float u_intensity;
uniform float u_dirt_intensity;
uniform int u_has_dirt;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec3 bloom = texture(u_input_tex, v_uv).rgb;
    if (u_has_dirt != 0) {
        vec3 dirt = texture(u_dirt_tex, v_uv).rgb;
        bloom += dirt * u_dirt_intensity;
    }
    frag_color = vec4(bloom * u_intensity, 1.0);
}
"""

DOWN_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
uniform vec2 u_texel;
uniform float u_diffusion;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec2 h = u_texel * u_diffusion;
    vec2 h2 = h * 2.0;
    vec3 center = texture(u_input_tex, v_uv).rgb;
    vec3 red = texture(u_input_tex, v_uv + vec2(-h.x,  h.y)).rgb
             + texture(u_input_tex, v_uv + vec2( h.x,  h.y)).rgb
             + texture(u_input_tex, v_uv + vec2( h.x, -h.y)).rgb
             + texture(u_input_tex, v_uv + vec2(-h.x, -h.y)).rgb;
    vec3 yellow = texture(u_input_tex, v_uv + vec2(-h2.x,  h2.y)).rgb
                + texture(u_input_tex, v_uv + vec2( 0.0,   h2.y)).rgb
                + center
                + texture(u_input_tex, v_uv + vec2(-h2.x,  0.0)).rgb;
    vec3 green = texture(u_input_tex, v_uv + vec2(0.0,  h2.y)).rgb
               + texture(u_input_tex, v_uv + vec2(h2.x, h2.y)).rgb
               + texture(u_input_tex, v_uv + vec2(h2.x, 0.0)).rgb
               + center;
    vec3 blue = center
              + texture(u_input_tex, v_uv + vec2(h2.x,  0.0)).rgb
              + texture(u_input_tex, v_uv + vec2(h2.x, -h2.y)).rgb
              + texture(u_input_tex, v_uv + vec2(0.0,  -h2.y)).rgb;
    vec3 lila = texture(u_input_tex, v_uv + vec2(-h2.x, 0.0)).rgb
              + center
              + texture(u_input_tex, v_uv + vec2(0.0,  -h2.y)).rgb
              + texture(u_input_tex, v_uv + vec2(-h2.x, -h2.y)).rgb;
    vec3 acc = red * 0.5 + (yellow + green + blue + lila) * 0.125;
    frag_color = vec4(acc * 0.25, 1.0);
}
"""

UP_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
uniform sampler2D u_down_tex;
uniform vec2 u_half_texel;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec2 h = u_half_texel;
    vec3 acc = texture(u_input_tex, v_uv + vec2(-2.0 * h.x, 0.0)).rgb;
    acc += texture(u_input_tex, v_uv + vec2(-h.x,  h.y)).rgb * 2.0;
    acc += texture(u_input_tex, v_uv + vec2(0.0, 2.0 * h.y)).rgb;
    acc += texture(u_input_tex, v_uv + vec2( h.x,  h.y)).rgb * 2.0;
    acc += texture(u_input_tex, v_uv + vec2(2.0 * h.x, 0.0)).rgb;
    acc += texture(u_input_tex, v_uv + vec2( h.x, -h.y)).rgb * 2.0;
    acc += texture(u_input_tex, v_uv + vec2(0.0, -2.0 * h.y)).rgb;
    acc += texture(u_input_tex, v_uv + vec2(-h.x, -h.y)).rgb * 2.0;
    acc *= 0.0625;
    acc += texture(u_down_tex, v_uv).rgb;
    frag_color = vec4(acc, 1.0);
}
"""


@ComponentRegistry.register
class Bloom(GraphicsEffect):
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
    def deserialize(cls, data: dict) -> Bloom:
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

    _res_prog_cache: dict[int, dict] = {}

    def _ensure_resources(self, ctx: moderngl.Context, viewport_w: int, viewport_h: int):
        ctx_id = id(ctx)
        cached = self._res_prog_cache.get(ctx_id)
        if cached is not None and '_prefilter_prog' in cached:
            self._ctx = ctx
            self._prog = cached['_prog']
            self._prefilter_prog = cached['_prefilter_prog']
            self._output_prog = cached['_output_prog']
            self._down_prog = cached['_down_prog']
            self._up_prog = cached['_up_prog']
            self._prefilter_vao = cached['_prefilter_vao']
            self._output_vao = cached['_output_vao']
            self._down_vao = cached['_down_vao']
            self._up_vao = cached['_up_vao']
            self._vbo = cached['_vbo']
            self._ibo = cached['_ibo']
        else:
            self._ctx = ctx
            verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
            indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
            self._vbo = ctx.buffer(verts.tobytes())
            self._ibo = ctx.buffer(indices.tobytes())

            self._prog = ctx.program(vertex_shader=BLOOM_VERT, fragment_shader=PREFILTER_FRAG)
            self._prefilter_prog = ctx.program(vertex_shader=BLOOM_VERT, fragment_shader=PREFILTER_FRAG)
            self._output_prog = ctx.program(vertex_shader=BLOOM_VERT, fragment_shader=OUTPUT_FRAG)
            self._down_prog = ctx.program(vertex_shader=BLOOM_VERT, fragment_shader=DOWN_FRAG)
            self._up_prog = ctx.program(vertex_shader=BLOOM_VERT, fragment_shader=UP_FRAG)

            self._prefilter_vao = ctx.vertex_array(
                self._prefilter_prog,
                [(self._vbo, '2f', 'in_position')],
                self._ibo
            )
            self._output_vao = ctx.vertex_array(
                self._output_prog,
                [(self._vbo, '2f', 'in_position')],
                self._ibo
            )
            self._down_vao = ctx.vertex_array(
                self._down_prog,
                [(self._vbo, '2f', 'in_position')],
                self._ibo
            )
            self._up_vao = ctx.vertex_array(
                self._up_prog,
                [(self._vbo, '2f', 'in_position')],
                self._ibo
            )
            self._res_prog_cache[ctx_id] = {
                '_prog': self._prog,
                '_prefilter_prog': self._prefilter_prog,
                '_output_prog': self._output_prog,
                '_down_prog': self._down_prog,
                '_up_prog': self._up_prog,
                '_prefilter_vao': self._prefilter_vao,
                '_output_vao': self._output_vao,
                '_down_vao': self._down_vao,
                '_up_vao': self._up_vao,
                '_vbo': self._vbo,
                '_ibo': self._ibo,
            }
            if len(self._res_prog_cache) > 4:
                oldest = next(iter(self._res_prog_cache))
                self._release_cache_objects({oldest: self._res_prog_cache[oldest]})
                del self._res_prog_cache[oldest]

        ds = max(1, self._downsample)
        bw = max(1, viewport_w // ds)
        bh = max(1, viewport_h // ds)
        if self._bloom_size != (bw, bh):
            self._release_bloom_resources()
            self._bloom_tex = ctx.texture((bw, bh), 4, dtype='f2')
            self._bloom_tex.repeat_x = False
            self._bloom_tex.repeat_y = False
            self._bloom_fbo = ctx.framebuffer(self._bloom_tex)
            self._bloom_temp_tex = ctx.texture((bw, bh), 4, dtype='f2')
            self._bloom_temp_tex.repeat_x = False
            self._bloom_temp_tex.repeat_y = False
            self._bloom_temp_fbo = ctx.framebuffer(self._bloom_temp_tex)
            self._acc_tex = ctx.texture((bw, bh), 4, dtype='f2')
            self._acc_tex.repeat_x = False
            self._acc_tex.repeat_y = False
            self._acc_fbo = ctx.framebuffer(self._acc_tex)
            mw, mh = bw, bh
            while len(self._mip_chain) < 5 and min(mw, mh) // 2 >= 8:
                mw = max(1, mw // 2)
                mh = max(1, mh // 2)
                tex = ctx.texture((mw, mh), 4, dtype='f2')
                tex.repeat_x = False
                tex.repeat_y = False
                self._mip_chain.append((mw, mh, tex, ctx.framebuffer(tex)))
            for uw, uh, _t, _f in self._mip_chain[:-1]:
                tex = ctx.texture((uw, uh), 4, dtype='f2')
                tex.repeat_x = False
                tex.repeat_y = False
                self._up_chain.append((uw, uh, tex, ctx.framebuffer(tex)))
            self._bloom_size = (bw, bh)

        if self._dirt_texture and self._dirt_intensity > 0.0:
            if self._dirt_tex is None:
                try:
                    from PIL import Image
                    img = Image.open(self._dirt_texture).convert("RGBA")
                    img = img.resize((viewport_w, viewport_h), Image.LANCZOS)
                    self._dirt_tex = ctx.texture((viewport_w, viewport_h), 4, data=img.tobytes())
                    self._dirt_tex.repeat_x = False
                    self._dirt_tex.repeat_y = False
                except Exception:
                    self._dirt_tex = None
        else:
            self._dirt_tex = None

    def _release_bloom_resources(self):
        for obj in [self._bloom_fbo, self._bloom_tex, self._bloom_temp_fbo, self._bloom_temp_tex,
                    self._acc_fbo, self._acc_tex]:
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        for _mw, _mh, tex, fbo in self._mip_chain + self._up_chain:
            for obj in (fbo, tex):
                if obj is not None:
                    try:
                        obj.release()
                    except Exception:
                        pass
        self._bloom_fbo = None
        self._bloom_tex = None
        self._bloom_temp_fbo = None
        self._bloom_temp_tex = None
        self._mip_chain = []
        self._up_chain = []
        self._acc_fbo = None
        self._acc_tex = None
        self._bloom_size = (0, 0)

    def _release_dirt(self):
        if self._dirt_tex is not None:
            try:
                self._dirt_tex.release()
            except Exception:
                pass
            self._dirt_tex = None

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        self._ensure_resources(ctx, viewport_w, viewport_h)

        bw, bh = self._bloom_size
        prev_fbo = ctx.fbo
        diff = max(0.25, float(self._diffusion))
        ctx.disable(moderngl.BLEND)

        self._bloom_temp_fbo.use()
        self._bloom_temp_fbo.viewport = (0, 0, bw, bh)
        self._down_prog["u_input_tex"] = 0
        self._down_prog["u_texel"].value = (1.0 / viewport_w, 1.0 / viewport_h)
        self._down_prog["u_diffusion"].value = diff
        scene_color_tex.use(0)
        self._down_vao.render()

        self._bloom_fbo.use()
        self._bloom_fbo.viewport = (0, 0, bw, bh)
        self._prefilter_prog["u_input_tex"] = 0
        self._prefilter_prog["u_threshold"].value = float(self._threshold)
        self._prefilter_prog["u_max_color"].value = max(0.5, float(self._max_color))
        self._bloom_temp_tex.use(0)
        self._prefilter_vao.render()

        src_tex = self._bloom_tex
        sw, sh = bw, bh
        for mw, mh, mtex, mfbo in self._mip_chain:
            mfbo.use()
            mfbo.viewport = (0, 0, mw, mh)
            self._down_prog["u_input_tex"] = 0
            self._down_prog["u_texel"].value = (1.0 / sw, 1.0 / sh)
            self._down_prog["u_diffusion"].value = diff
            src_tex.use(0)
            self._down_vao.render()
            src_tex = mtex
            sw, sh = mw, mh

        self._up_prog["u_input_tex"] = 0
        self._up_prog["u_down_tex"] = 1
        down_levels = [(bw, bh, self._bloom_tex)] + [(mw, mh, mtex) for mw, mh, mtex, _mfbo in self._mip_chain]
        up_levels = self._up_chain
        n_down = len(down_levels)
        if n_down == 1:
            comp_tex = self._bloom_tex
        elif n_down == 2:
            lw, lh, ltex = down_levels[1]
            self._acc_fbo.use()
            self._acc_fbo.viewport = (0, 0, bw, bh)
            self._up_prog["u_half_texel"].value = (0.5 / lw * diff, 0.5 / lh * diff)
            ltex.use(0)
            self._bloom_tex.use(1)
            self._up_vao.render()
            comp_tex = self._acc_tex
        else:
            lw, lh, ltex = down_levels[n_down - 1]
            _uw, _uh, _utex, _ufbo = up_levels[n_down - 3]
            _ufbo.use()
            _ufbo.viewport = (0, 0, _uw, _uh)
            self._up_prog["u_half_texel"].value = (0.5 / lw * diff, 0.5 / lh * diff)
            ltex.use(0)
            down_levels[n_down - 2][2].use(1)
            self._up_vao.render()
            for i in range(n_down - 3, 0, -1):
                lw, lh, _ltex = down_levels[i + 1]
                _uw, _uh, _utex, _ufbo = up_levels[i - 1]
                _utex_up = up_levels[i][2]
                _ufbo.use()
                _ufbo.viewport = (0, 0, _uw, _uh)
                self._up_prog["u_half_texel"].value = (0.5 / lw * diff, 0.5 / lh * diff)
                _utex_up.use(0)
                down_levels[i][2].use(1)
                self._up_vao.render()
            lw, lh, _ltex = down_levels[1]
            self._acc_fbo.use()
            self._acc_fbo.viewport = (0, 0, bw, bh)
            self._up_prog["u_half_texel"].value = (0.5 / lw * diff, 0.5 / lh * diff)
            up_levels[0][2].use(0)
            self._bloom_tex.use(1)
            self._up_vao.render()
            comp_tex = self._acc_tex

        if prev_fbo is not None:
            prev_fbo.use()
            prev_fbo.viewport = (0, 0, viewport_w, viewport_h)
        elif ctx.screen is not None:
            ctx.screen.use()
        self._output_prog["u_input_tex"] = 0
        self._output_prog["u_intensity"].value = self._intensity
        if self._dirt_tex is not None and self._dirt_intensity > 0.0:
            self._output_prog["u_dirt_tex"] = 1
            self._dirt_tex.use(1)
            self._output_prog["u_dirt_intensity"].value = self._dirt_intensity
            self._output_prog["u_has_dirt"].value = 1
        else:
            self._output_prog["u_has_dirt"].value = 0
        comp_tex.use(0)
        self._output_vao.render()
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def _release_gl(self):
        self._release_bloom_resources()
        self._release_dirt()
        for obj in (self._prog, self._prefilter_prog, self._output_prog,
                    self._down_prog, self._up_prog,
                    self._prefilter_vao, self._output_vao,
                    self._down_vao, self._up_vao,
                    self._vbo, self._ibo):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._prog = None
        self._prefilter_prog = None
        self._output_prog = None
        self._down_prog = None
        self._up_prog = None
        self._prefilter_vao = None
        self._output_vao = None
        self._down_vao = None
        self._up_vao = None
        self._vbo = None
        self._ibo = None
        self._bloom_tex = None
        self._bloom_fbo = None
        self._bloom_temp_tex = None
        self._bloom_temp_fbo = None
        self._acc_tex = None
        self._acc_fbo = None
        self._bloom_size = (0, 0)

    @property
    def intensity(self) -> float:
        return getattr(self, '_intensity', 1.0)

    @intensity.setter
    def intensity(self, v: float):
        self._intensity = v

    @property
    def threshold(self) -> float:
        return getattr(self, '_threshold', 0.8)

    @threshold.setter
    def threshold(self, v: float):
        self._threshold = v