# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from core.components.rendering.postfx.bloomp.threshold import BLOOM_VERT, PREFILTER_FRAG
from core.components.rendering.postfx.bloomp.composite import OUTPUT_FRAG


DOWN_FRAG = """
\x23version 330 core
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
\x23version 330 core
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


class BloomBlurMixin:
    def _ensure_resources(self, ctx: moderngl.Context, viewport_w: int, viewport_h: int):
        ctx_id = id(ctx)
        cached = self._res_prog_cache.get(ctx_id)
        if cached is not None and "_prefilter_prog" in cached:
            self._ctx = ctx
            self._prog = cached["_prog"]
            self._prefilter_prog = cached["_prefilter_prog"]
            self._output_prog = cached["_output_prog"]
            self._down_prog = cached["_down_prog"]
            self._up_prog = cached["_up_prog"]
            self._prefilter_vao = cached["_prefilter_vao"]
            self._output_vao = cached["_output_vao"]
            self._down_vao = cached["_down_vao"]
            self._up_vao = cached["_up_vao"]
            self._vbo = cached["_vbo"]
            self._ibo = cached["_ibo"]
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
                [(self._vbo, "2f", "in_position")],
                self._ibo
            )
            self._output_vao = ctx.vertex_array(
                self._output_prog,
                [(self._vbo, "2f", "in_position")],
                self._ibo
            )
            self._down_vao = ctx.vertex_array(
                self._down_prog,
                [(self._vbo, "2f", "in_position")],
                self._ibo
            )
            self._up_vao = ctx.vertex_array(
                self._up_prog,
                [(self._vbo, "2f", "in_position")],
                self._ibo
            )
            self._res_prog_cache[ctx_id] = {
                "_prog": self._prog,
                "_prefilter_prog": self._prefilter_prog,
                "_output_prog": self._output_prog,
                "_down_prog": self._down_prog,
                "_up_prog": self._up_prog,
                "_prefilter_vao": self._prefilter_vao,
                "_output_vao": self._output_vao,
                "_down_vao": self._down_vao,
                "_up_vao": self._up_vao,
                "_vbo": self._vbo,
                "_ibo": self._ibo,
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
            self._bloom_tex = ctx.texture((bw, bh), 4, dtype="f2")
            self._bloom_tex.repeat_x = False
            self._bloom_tex.repeat_y = False
            self._bloom_fbo = ctx.framebuffer(self._bloom_tex)
            self._bloom_temp_tex = ctx.texture((bw, bh), 4, dtype="f2")
            self._bloom_temp_tex.repeat_x = False
            self._bloom_temp_tex.repeat_y = False
            self._bloom_temp_fbo = ctx.framebuffer(self._bloom_temp_tex)
            self._acc_tex = ctx.texture((bw, bh), 4, dtype="f2")
            self._acc_tex.repeat_x = False
            self._acc_tex.repeat_y = False
            self._acc_fbo = ctx.framebuffer(self._acc_tex)
            mw, mh = bw, bh
            while len(self._mip_chain) < 5 and min(mw, mh) // 2 >= 8:
                mw = max(1, mw // 2)
                mh = max(1, mh // 2)
                tex = ctx.texture((mw, mh), 4, dtype="f2")
                tex.repeat_x = False
                tex.repeat_y = False
                self._mip_chain.append((mw, mh, tex, ctx.framebuffer(tex)))
            for uw, uh, _t, _f in self._mip_chain[:-1]:
                tex = ctx.texture((uw, uh), 4, dtype="f2")
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
