# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Scene and auxiliary framebuffers."""

from __future__ import annotations
import moderngl


class FramebuffersMixin:
    """Scene and auxiliary framebuffers."""


    def _ensure_scene_fbo(self, w: int, h: int):
        if self._scene_fbo_size == (w, h) and self._scene_fbo:
            return
        self._release_scene_fbo()
        self._scene_color_tex = self._ctx.texture((w, h), 4, dtype='f2')
        self._scene_color_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._scene_depth_tex = self._ctx.depth_texture((w, h))
        self._scene_fbo = self._ctx.framebuffer(self._scene_color_tex, self._scene_depth_tex)
        self._scene_fbo_size = (w, h)


    def _release_scene_fbo(self):
        for obj in [self._scene_fbo, self._scene_color_tex, self._scene_depth_tex]:
            if obj:
                try:
                    obj.release()
                except Exception:
                    pass
        self._scene_fbo = None
        self._scene_color_tex = None
        self._scene_depth_tex = None
        self._scene_fbo_size = (0, 0)


    def _ensure_pp_fbo(self, w: int, h: int):
        if self._pp_fbo_size == (w, h) and self._pp_fbo_a:
            return
        self._release_pp_fbo()
        self._pp_color_tex_a = self._ctx.texture((w, h), 4, dtype='f2')
        self._pp_color_tex_a.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._pp_color_tex_a.repeat_x = False
        self._pp_color_tex_a.repeat_y = False
        self._pp_fbo_a = self._ctx.framebuffer(self._pp_color_tex_a)
        self._pp_color_tex_b = self._ctx.texture((w, h), 4, dtype='f2')
        self._pp_color_tex_b.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._pp_color_tex_b.repeat_x = False
        self._pp_color_tex_b.repeat_y = False
        self._pp_fbo_b = self._ctx.framebuffer(self._pp_color_tex_b)
        self._pp_fbo_size = (w, h)


    def _release_pp_fbo(self):
        for obj in [self._pp_fbo_a, self._pp_color_tex_a, self._pp_fbo_b, self._pp_color_tex_b]:
            if obj:
                try:
                    obj.release()
                except Exception:
                    pass
        self._pp_fbo_a = None
        self._pp_color_tex_a = None
        self._pp_fbo_b = None
        self._pp_color_tex_b = None
        self._pp_fbo_size = (0, 0)


    def _ensure_se_fbo(self, w: int, h: int):
        if self._se_fbo_size == (w, h) and self._se_fbo_a:
            return
        self._release_se_fbo()
        self._se_color_tex_a = self._ctx.texture((w, h), 4, dtype='f2')
        self._se_color_tex_a.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._se_color_tex_a.repeat_x = False
        self._se_color_tex_a.repeat_y = False
        self._se_fbo_a = self._ctx.framebuffer(self._se_color_tex_a)
        self._se_color_tex_b = self._ctx.texture((w, h), 4, dtype='f2')
        self._se_color_tex_b.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._se_color_tex_b.repeat_x = False
        self._se_color_tex_b.repeat_y = False
        self._se_fbo_b = self._ctx.framebuffer(self._se_color_tex_b)
        self._se_fbo_size = (w, h)


    def _release_se_fbo(self):
        for obj in [self._se_fbo_a, self._se_color_tex_a, self._se_fbo_b, self._se_color_tex_b]:
            if obj:
                try:
                    obj.release()
                except Exception:
                    pass
        self._se_fbo_a = None
        self._se_color_tex_a = None
        self._se_fbo_b = None
        self._se_color_tex_b = None
        self._se_fbo_size = (0, 0)


    def _ensure_water_fbo(self, w: int, h: int):
        if self._water_fbo_size == (w, h) and self._water_fbo:
            return
        self._release_water_fbo()
        self._water_color_tex = self._ctx.texture((w, h), 4, dtype='f2')
        self._water_color_tex.repeat_x = False
        self._water_color_tex.repeat_y = False
        self._water_depth_rb = self._ctx.depth_renderbuffer((w, h))
        self._water_fbo = self._ctx.framebuffer(self._water_color_tex, depth_attachment=self._water_depth_rb)
        self._water_fbo_size = (w, h)


    def _release_water_fbo(self):
        for obj in [self._water_fbo, self._water_color_tex, self._water_depth_rb]:
            if obj:
                try:
                    obj.release()
                except Exception:
                    pass
        self._water_fbo = None
        self._water_color_tex = None
        self._water_depth_rb = None
        self._water_fbo_size = (0, 0)


    def _ensure_velocity_fbo(self, w: int, h: int):
        if self._velocity_fbo_size == (w, h) and self._velocity_fbo:
            return
        self._release_velocity_fbo()
        self._velocity_tex = self._ctx.texture((w, h), 2, dtype='f2')
        self._velocity_tex.repeat_x = False
        self._velocity_tex.repeat_y = False
        self._velocity_depth = self._ctx.depth_renderbuffer((w, h))
        self._velocity_fbo = self._ctx.framebuffer(self._velocity_tex, depth_attachment=self._velocity_depth)
        self._velocity_fbo_size = (w, h)


    def _release_velocity_fbo(self):
        for obj in [self._velocity_fbo, self._velocity_tex, self._velocity_depth]:
            if obj:
                try:
                    obj.release()
                except Exception:
                    pass
        self._velocity_fbo = None
        self._velocity_tex = None
        self._velocity_depth = None
        self._velocity_fbo_size = (0, 0)
