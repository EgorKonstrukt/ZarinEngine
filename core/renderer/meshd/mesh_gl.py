# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional, Any
from core.foundation.logger import Logger


class _MeshGl:

    def build_gl(self, ctx: moderngl.Context, program: moderngl.Program):
        self._ctx = ctx
        verts = self.vertices
        if verts.size == 0:
            if self._shadow_vbo is not None:
                try:
                    self._shadow_vbo.release()
                except Exception:
                    pass
                self._shadow_vbo = None
            return
        n_verts = verts.size // 3
        prebuilt = self._up_vbo if self._vbo is None else None
        b = prebuilt if prebuilt is not None else self._interleaved_vbo_bytes()
        _buffers_recreated = False
        if self._vbo is None:
            self._vbo = ctx.buffer(b)
            _buffers_recreated = True
        else:
            if self._vbo.size != len(b):
                try:
                    self._vbo.release()
                except Exception:
                    pass
                self._vbo = ctx.buffer(b)
                _buffers_recreated = True
            else:
                self._vbo.write(b)
        try:
            pos = np.ascontiguousarray(verts.reshape(-1, 3), dtype=np.float32).tobytes()
        except Exception:
            pos = b""
        if pos:
            if self._shadow_vbo is None:
                self._shadow_vbo = ctx.buffer(pos)
                _buffers_recreated = True
            else:
                if self._shadow_vbo.size != len(pos):
                    try:
                        self._shadow_vbo.release()
                    except Exception:
                        pass
                    self._shadow_vbo = ctx.buffer(pos)
                    _buffers_recreated = True
                else:
                    self._shadow_vbo.write(pos)
        idx = self.indices
        if idx.size > 0:
            ib = self._up_ibo if (self._ibo is None and self._up_ibo) else idx.astype(np.uint32, copy=False).tobytes()
            if self._ibo is None:
                self._ibo = ctx.buffer(ib)
                _buffers_recreated = True
            else:
                if self._ibo.size != len(ib):
                    try:
                        self._ibo.release()
                    except Exception:
                        pass
                    self._ibo = ctx.buffer(ib)
                    _buffers_recreated = True
                else:
                    self._ibo.write(ib)
        elif self._ibo is not None:
            try:
                self._ibo.release()
            except Exception:
                pass
            self._ibo = None
            _buffers_recreated = True
        if self.has_skeleton and self.bone_indices.size > 0:
            bb = self._up_bone if (self._bone_vbo is None and self._up_bone) else None
            if bb is None:
                nb = self.bone_indices.shape[0]
                bone_data = np.empty((nb, 8), dtype=np.float32)
                bone_data[:, 0:4] = self.bone_indices.reshape(-1, 4).astype(np.float32, copy=False)
                bone_data[:, 4:8] = self.bone_weights.reshape(-1, 4)
                bb = bone_data.tobytes()
            if self._bone_vbo is None:
                self._bone_vbo = ctx.buffer(bb)
            else:
                if self._bone_vbo.size != len(bb):
                    try:
                        self._bone_vbo.release()
                    except Exception:
                        pass
                    self._bone_vbo = ctx.buffer(bb)
                else:
                    self._bone_vbo.write(bb)
            self.bone_count = len(self.bone_offset_matrices)
        cols = self.colors
        if cols.size == n_verts * 4:
            cb = self._up_color if (self._color_vbo is None and self._up_color) else cols.astype(np.float32, copy=False).tobytes()
            if self._color_vbo is None:
                self._color_vbo = ctx.buffer(cb)
                _buffers_recreated = True
            else:
                if self._color_vbo.size != len(cb):
                    try:
                        self._color_vbo.release()
                    except Exception:
                        pass
                    self._color_vbo = ctx.buffer(cb)
                    _buffers_recreated = True
                else:
                    self._color_vbo.write(cb)
        if _buffers_recreated:
            self._invalidate_vaos()
            self._gpu_version += 1
        if prebuilt is not None:
            self._consume_upload_bytes()
        self._build_vao_for_program(program)
        self._vao = self._vao_cache.get(id(program))

    def _build_vao_for_program(self, program: moderngl.Program):
        if program is None or self._ctx is None or self._vbo is None:
            return
        key = id(program)
        if key in self._vao_cache:
            return
        has_pos = "in_position" in program
        has_nrm = "in_normal" in program
        has_uv = "in_uv" in program
        has_col = "in_color" in program
        has_bone_idx = "in_bone_indices" in program
        has_bone_w = "in_bone_weights" in program
        fmt_parts = []
        attrib_names = []
        if has_pos:
            fmt_parts.append("3f")
            attrib_names.append("in_position")
        else:
            fmt_parts.append("3x4")
        if has_nrm:
            fmt_parts.append("3f")
            attrib_names.append("in_normal")
        else:
            fmt_parts.append("3x4")
        if has_uv:
            fmt_parts.append("2f")
            attrib_names.append("in_uv")
        else:
            fmt_parts.append("2x4")
        buffers = [(self._vbo, " ".join(fmt_parts), *attrib_names)]
        if has_col and self._color_vbo is None and len(self.vertices) > 0:
            n = len(self.vertices) // 3
            self._color_vbo = self._ctx.buffer(np.full((n, 4), 1.0, dtype=np.float32).tobytes())
        if self._bone_vbo is not None and has_bone_idx and has_bone_w:
            buffers.append((self._bone_vbo, "4f 4f", "in_bone_indices", "in_bone_weights"))
        if self._color_vbo is not None and has_col:
            buffers.append((self._color_vbo, "4f", "in_color"))
        self._vao_cache[key] = self._ctx.vertex_array(
            program,
            buffers,
            self._ibo
        )

    def render(self, program: Optional[moderngl.Program] = None):
        if program is not None:
            self._build_vao_for_program(program)
            vao = self._vao_cache.get(id(program))
        else:
            vao = self._vao
        if vao:
            try:
                vao.render()
            except Exception as e:
                Logger.error("MeshData.render VAO render failed", e)

    def render_range(self, program: moderngl.Program, start: int, count: int):
        self._build_vao_for_program(program)
        vao = self._vao_cache.get(id(program))
        if vao:
            try:
                vao.render(vertices=count, first=start)
            except Exception as e:
                Logger.error("MeshData.render_range VAO render failed", e)
