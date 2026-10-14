# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import moderngl


OUTPUT_FRAG = """
\x23version 330 core
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


class BloomCompositeMixin:
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
