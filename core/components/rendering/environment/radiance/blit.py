# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
class RadianceBlitMixin:
    def _blit_to_fbo(self, ctx: moderngl.Context, target_fbo: moderngl.Framebuffer, width: int, height: int):
        if not self._gi_output_fbo or not self._fullscreen_prog:
            return
        old_fbo = ctx.fbo
        target_fbo.use()
        target_fbo.viewport = (0, 0, width, height)
        self._gi_output_tex.use(0)
        self._fullscreen_prog["u_tex"].value = 0
        ctx.viewport = (0, 0, width, height)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        self._fullscreen_quad.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)
        if old_fbo is not None:
            old_fbo.use()
    def blit_to_screen(self, ctx: moderngl.Context, width: int, height: int):
        if not self._gi_output_fbo or not self._fullscreen_prog:
            return
        self._gi_output_tex.use(0)
        self._fullscreen_prog["u_tex"].value = 0
        ctx.viewport = (0, 0, width, height)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        if self._show_overlay or self._debug_mode:
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        else:
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        self._fullscreen_quad.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)
