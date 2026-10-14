# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from core.components.rendering.postfx.vsmoke.shaders import VOLUMETRIC_SMOKE_FRAG, VOLUMETRIC_SMOKE_VERT


class VolumetricSmokeResourcesMixin:
    def _ensure_resources(self, ctx: moderngl.Context):
        ctx_id = id(ctx)
        cached = self._res_cache.get(ctx_id)
        if cached is not None:
            self._ctx = ctx
            self._prog = cached["_prog"]
            self._vao = cached["_vao"]
            self._vbo = cached["_vbo"]
            self._ibo = cached["_ibo"]
            return
        self._ctx = ctx
        self._prog = ctx.program(
            vertex_shader=VOLUMETRIC_SMOKE_VERT,
            fragment_shader=VOLUMETRIC_SMOKE_FRAG
        )
        verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._vao = ctx.vertex_array(
            self._prog,
            [(self._vbo, "2f", "in_position")],
            self._ibo
        )
        self._res_cache[ctx_id] = {
            "_prog": self._prog,
            "_vao": self._vao,
            "_vbo": self._vbo,
            "_ibo": self._ibo,
        }
        if len(self._res_cache) > 4:
            oldest = next(iter(self._res_cache))
            for obj in self._res_cache[oldest].values():
                if obj is not None and hasattr(obj, "release"):
                    try:
                        obj.release()
                    except Exception:
                        pass
            del self._res_cache[oldest]

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
