# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from core.foundation.logger import Logger


class _MeshOutline:

    def build_outline_vao(self, ctx: moderngl.Context, program: moderngl.Program):
        if len(self.vertices) == 0:
            return
        if self._outline_vbo is None and self._up_outline:
            raw = self._up_outline
        else:
            raw = self.vertices.astype(np.float32, copy=False).tobytes()
        if self._outline_vbo is None:
            self._outline_vbo = ctx.buffer(raw)
        else:
            try:
                if self._outline_vbo.size != len(raw):
                    try:
                        self._outline_vbo.release()
                    except Exception:
                        pass
                    self._outline_vbo = ctx.buffer(raw)
                else:
                    self._outline_vbo.write(raw)
            except Exception:
                try:
                    self._outline_vbo.release()
                except Exception:
                    pass
                self._outline_vbo = ctx.buffer(raw)
        self._create_outline_vao(program)

    def _create_outline_vao(self, program: moderngl.Program):
        if program is None or self._outline_vbo is None or self._ctx is None:
            return
        try:
            if self._outline_vao is not None:
                try:
                    self._outline_vao.release()
                except Exception:
                    pass
                self._outline_vao = None
            self._outline_vao = self._ctx.vertex_array(
                program,
                [(self._outline_vbo, "3f", "in_position")],
                self._ibo
            )
        except Exception:
            pass

    def render_outline(self):
        if not self._outline_vao:
            return
        if len(self.indices) // 3 > self.outline_max_triangles:
            return
        try:
            self._outline_vao.render()
        except Exception as e:
            Logger.error("MeshData.render_outline VAO render failed", e)

    def release(self):
        if self._vbo:
            try:
                self._vbo.release()
            except Exception:
                pass
        if self._ibo:
            try:
                self._ibo.release()
            except Exception:
                pass
        if self._bone_vbo:
            try:
                self._bone_vbo.release()
            except Exception:
                pass
            self._bone_vbo = None
        if self._color_vbo:
            try:
                self._color_vbo.release()
            except Exception:
                pass
            self._color_vbo = None
        if self._outline_vao:
            try:
                self._outline_vao.release()
            except Exception:
                pass
        if self._outline_vbo:
            try:
                self._outline_vbo.release()
            except Exception:
                pass
        for v in self._vao_cache.values():
            if v:
                try:
                    v.release()
                except Exception:
                    pass
        self._vao_cache.clear()
        self._vao = None
        self._vbo = None
        self._ibo = None
        self._outline_vao = None
        self._outline_vbo = None
        self._up_vbo = None
        self._up_ibo = None
        self._up_bone = None
        self._up_color = None
        self._up_outline = None
