# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from typing import Optional
import moderngl
import numpy as np
from core.foundation.logger import Logger
from core.assets.compute_shader import compile_compute_shader
from core.renderer.shaderp import program_with_fallback
from core.components.rendering.environment.radiance.shaders import _FULLSCREEN_VERT, _FULLSCREEN_FRAG
class RadianceResourcesMixin:
    @classmethod
    def _resolve_shader_path(cls, path: str) -> str:
        if path and not os.path.isabs(path) and not os.path.exists(os.path.abspath(path)):
            cand = "core/shaders/compute/" + os.path.basename(path).replace("\\", "/")
            if os.path.exists(os.path.abspath(cand)):
                return cand
        return path
    def _set_opt(self, prog, name, value) -> bool:
        try:
            prog[name] = value
            return True
        except KeyError:
            return False
        except Exception:
            return False
    def _compile_compute(self, ctx: moderngl.Context, path: str) -> Optional[moderngl.ComputeShader]:
        path = self._resolve_shader_path(path)
        self._compute_shader_path = path
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            Logger.error(f"Compute shader not found: {abs_path}")
            return None
        try:
            with open(abs_path) as f:
                src = f.read()
            glsl_start = src.find("GLSLPROGRAM")
            glsl_end = src.find("ENDGLSL", glsl_start)
            if glsl_start < 0 or glsl_end < 0:
                Logger.error("Invalid .compute file: no GLSLPROGRAM/ENDGLSL")
                return None
            source = src[glsl_start + len("GLSLPROGRAM"):glsl_end].strip()
            return compile_compute_shader(ctx, source, abs_path)
        except Exception as e:
            Logger.error(f"Failed to compile compute shader: {e}")
            return None
    def _cas_grid(self, rw: int, rh: int, c: int):
        stride = self.CASCADE_STRIDES[c]
        gw = (rw + stride - 1) // stride
        gh = (rh + stride - 1) // stride
        return gw, gh
    def _ensure_resources(self, ctx: moderngl.Context, width: int, height: int):
        rw = max(1, int(width * self._resolution_scale * 0.25))
        rh = max(1, int(height * self._resolution_scale * 0.25))
        if self._program is None:
            prog = self._compile_compute(ctx, self._compute_shader_path)
            if prog is None:
                return False
            self._program = prog
        if self._fullscreen_prog is None:
            self._fullscreen_prog = program_with_fallback(
                ctx,
                vertex_shader=_FULLSCREEN_VERT,
                fragment_shader=_FULLSCREEN_FRAG,
                label="radiance_fullscreen"
            )
        if self._fullscreen_quad is None:
            fs_verts = np.array([
                -1, -1, 0, 0,
                1, -1, 1, 0,
                1, 1, 1, 1,
                -1, -1, 0, 0,
                1, 1, 1, 1,
                -1, 1, 0, 1,
            ], dtype=np.float32)
            vbo = ctx.buffer(fs_verts.tobytes())
            self._fullscreen_quad = ctx.vertex_array(
                self._fullscreen_prog,
                [(vbo, "2f 2f", "in_position", "in_uv")],
            )
        if (self._gi_output_tex is None or self._prev_width != rw or self._prev_height != rh):
            for tex in [self._gi_output_tex, self._gi_temp_tex, self._history_tex, self._normal_tex]:
                if tex:
                    tex.release()
            self._normal_tex = None
            for fbo in [self._gi_output_fbo, self._gi_temp_fbo, self._history_fbo]:
                if fbo:
                    fbo.release()
            for t in self._cas_tex:
                if t:
                    t.release()
            self._cas_tex = [None] * self.NUM_CASCADES
            self._gi_output_tex = self._make_tex(ctx, rw, rh, moderngl.LINEAR, "f4")
            self._gi_temp_tex = self._make_tex(ctx, rw, rh, moderngl.LINEAR, "f4")
            self._history_tex = self._make_tex(ctx, rw, rh, moderngl.LINEAR, "f4")
            self._normal_tex = self._make_tex(ctx, rw, rh, moderngl.NEAREST, "f4")
            self._gi_output_fbo = ctx.framebuffer(color_attachments=[self._gi_output_tex])
            self._gi_temp_fbo = ctx.framebuffer(color_attachments=[self._gi_temp_tex])
            self._history_fbo = ctx.framebuffer(color_attachments=[self._history_tex])
            for c in range(self.NUM_CASCADES):
                gw, gh = self._cas_grid(rw, rh, c)
                self._cas_tex[c] = self._make_tex(ctx, gw * self.CASCADE_DIRS[c], gh, moderngl.NEAREST, "f2")
            self._prev_width = rw
            self._prev_height = rh
            self._frame = 0
            self._prev_view_proj = None
            try:
                self._history_fbo.clear(0.0, 0.0, 0.0, 0.0)
                self._gi_output_fbo.clear(0.0, 0.0, 0.0, 0.0)
                self._gi_temp_fbo.clear(0.0, 0.0, 0.0, 0.0)
            except Exception:
                pass
        if self._rt._albedo_array_tex is None:
            try:
                aw, ah = self._rt._albedo_array_size
                tex = ctx.texture_array((aw, ah, 32), 4, dtype="f1")
                tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                tex.repeat_x = False
                tex.repeat_y = False
                self._rt._albedo_array_tex = tex
            except Exception:
                pass
        return True
    def _make_tex(self, ctx, w, h, filter_mode, dtype="f4"):
        tex = ctx.texture((max(1, w), max(1, h)), 4, dtype=dtype)
        tex.filter = (filter_mode, filter_mode)
        tex.repeat_x = False
        tex.repeat_y = False
        return tex
    def _release_gl(self):
        for tex in [self._gi_output_tex, self._gi_temp_tex, self._history_tex, self._normal_tex]:
            if tex:
                tex.release()
        self._gi_output_tex = None
        self._gi_temp_tex = None
        self._history_tex = None
        self._normal_tex = None
        for t in self._cas_tex:
            if t:
                t.release()
        self._cas_tex = [None] * self.NUM_CASCADES
        for fbo in [self._gi_output_fbo, self._gi_temp_fbo, self._history_fbo]:
            if fbo:
                fbo.release()
        self._gi_output_fbo = None
        self._gi_temp_fbo = None
        self._history_fbo = None
        if self._program:
            self._program.release()
            self._program = None
        if self._fullscreen_prog:
            self._fullscreen_prog.release()
            self._fullscreen_prog = None
        if self._fullscreen_quad:
            self._fullscreen_quad.release()
            self._fullscreen_quad = None
        try:
            self._rt._release_gl()
        except Exception:
            pass
        self._prev_view_proj = None
        self._frame = 0
