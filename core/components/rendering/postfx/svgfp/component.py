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
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.components.inspector_meta import FieldType, InspectorField
from .vert import SVGF_VERT
from .reproj import SVGF_REPROJ_FRAG
from .atrous import SVGF_ATROUS_FRAG
from .final import SVGF_FINAL_FRAG


@ComponentRegistry.register
class SpatiotemporalVarianceGuidedFilter(GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "SVGF"
    render_type = "screen"
    _use_velocity = True

    def __init__(self):
        super().__init__()
        self._stability: float = 0.9
        self._disocclusion: float = 0.08
        self._phi_depth: float = 1.0
        self._phi_normal: float = 128.0
        self._phi_luma: float = 4.0
        self._iterations: int = 5
        self._ctx: Optional[moderngl.Context] = None
        self._reproj_prog: Optional[moderngl.Program] = None
        self._atrous_prog: Optional[moderngl.Program] = None
        self._final_prog: Optional[moderngl.Program] = None
        self._vao_reproj: Optional[moderngl.VertexArray] = None
        self._vao_atrous: Optional[moderngl.VertexArray] = None
        self._vao_final: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._history: list = [None, None]
        self._history_fbo: list = [None, None]
        self._moment: list = [None, None]
        self._moment_fbo: list = [None, None]
        self._atrous_buf: list = [None, None]
        self._atrous_fbo: list = [None, None]
        self._buf_w: int = 0
        self._buf_h: int = 0
        self._cur_index: int = 0
        self._history_valid: bool = False
        self._frame_count: int = 0

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Spatiotemporal Variance Guided Filter", FieldType.HEADER),
            InspectorField("_stability", "Temporal Stability", FieldType.FLOAT, min_val=0.0, max_val=0.99, step=0.01, decimals=3),
            InspectorField("_disocclusion", "Disocclusion Depth", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.005, decimals=3),
            InspectorField("", "Phi", FieldType.HEADER),
            InspectorField("_phi_depth", "Phi Depth", FieldType.FLOAT, min_val=0.01, max_val=10.0, step=0.05, decimals=3),
            InspectorField("_phi_normal", "Phi Normal", FieldType.FLOAT, min_val=1.0, max_val=512.0, step=1.0, decimals=1),
            InspectorField("_phi_luma", "Phi Luminance", FieldType.FLOAT, min_val=0.1, max_val=16.0, step=0.1, decimals=2),
            InspectorField("_iterations", "Iterations", FieldType.INT, min_val=1, max_val=8, step=1),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_stability": self._stability,
            "_disocclusion": self._disocclusion,
            "_phi_depth": self._phi_depth,
            "_phi_normal": self._phi_normal,
            "_phi_luma": self._phi_luma,
            "_iterations": self._iterations,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> SpatiotemporalVarianceGuidedFilter:
        inst = super().deserialize(data)
        inst._stability = float(data.get("_stability", 0.9))
        inst._disocclusion = float(data.get("_disocclusion", 0.08))
        inst._phi_depth = float(data.get("_phi_depth", 1.0))
        inst._phi_normal = float(data.get("_phi_normal", 128.0))
        inst._phi_luma = float(data.get("_phi_luma", 4.0))
        inst._iterations = int(data.get("_iterations", 5))
        inst._ctx = None
        inst._reproj_prog = None
        inst._atrous_prog = None
        inst._final_prog = None
        inst._vao_reproj = None
        inst._vao_atrous = None
        inst._vao_final = None
        inst._vbo = None
        inst._ibo = None
        inst._history = [None, None]
        inst._history_fbo = [None, None]
        inst._moment = [None, None]
        inst._moment_fbo = [None, None]
        inst._atrous_buf = [None, None]
        inst._atrous_fbo = [None, None]
        inst._buf_w = 0
        inst._buf_h = 0
        inst._cur_index = 0
        inst._history_valid = False
        inst._frame_count = 0
        return inst

    _res_cache: dict[int, dict] = {}

    def _ensure_resources(self, ctx: moderngl.Context):
        ctx_id = id(ctx)
        cached = self._res_cache.get(ctx_id)
        if cached is not None:
            self._ctx = ctx
            self._reproj_prog = cached['_reproj_prog']
            self._atrous_prog = cached['_atrous_prog']
            self._final_prog = cached['_final_prog']
            self._vao_reproj = cached['_vao_reproj']
            self._vao_atrous = cached['_vao_atrous']
            self._vao_final = cached['_vao_final']
            self._vbo = cached['_vbo']
            self._ibo = cached['_ibo']
            return
        self._ctx = ctx
        self._reproj_prog = ctx.program(vertex_shader=SVGF_VERT, fragment_shader=SVGF_REPROJ_FRAG)
        self._atrous_prog = ctx.program(vertex_shader=SVGF_VERT, fragment_shader=SVGF_ATROUS_FRAG)
        self._final_prog = ctx.program(vertex_shader=SVGF_VERT, fragment_shader=SVGF_FINAL_FRAG)
        verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._vao_reproj = ctx.vertex_array(self._reproj_prog, [(self._vbo, '2f', 'in_position')], self._ibo)
        self._vao_atrous = ctx.vertex_array(self._atrous_prog, [(self._vbo, '2f', 'in_position')], self._ibo)
        self._vao_final = ctx.vertex_array(self._final_prog, [(self._vbo, '2f', 'in_position')], self._ibo)
        self._res_cache[ctx_id] = {
            '_reproj_prog': self._reproj_prog,
            '_atrous_prog': self._atrous_prog,
            '_final_prog': self._final_prog,
            '_vao_reproj': self._vao_reproj,
            '_vao_atrous': self._vao_atrous,
            '_vao_final': self._vao_final,
            '_vbo': self._vbo,
            '_ibo': self._ibo,
        }
        if len(self._res_cache) > 4:
            oldest = next(iter(self._res_cache))
            self._release_cache_objects(self._res_cache[oldest])
            del self._res_cache[oldest]

    @staticmethod
    def _release_cache_objects(entry: dict):
        for obj in entry.values():
            if obj is None:
                continue
            try:
                obj.release()
            except Exception:
                pass

    def _ensure_buffers(self, ctx: moderngl.Context, w: int, h: int):
        if self._buf_w == w and self._buf_h == h and self._history[0] is not None:
            return
        self._release_buffers()
        self._buf_w = w
        self._buf_h = h
        for i in range(2):
            htex = ctx.texture((w, h), 4, dtype='f2')
            htex.repeat_x = False
            htex.repeat_y = False
            self._history[i] = htex
            mtex = ctx.texture((w, h), 2, dtype='f2')
            mtex.repeat_x = False
            mtex.repeat_y = False
            self._moment[i] = mtex
            self._history_fbo[i] = ctx.framebuffer(color_attachments=[htex, mtex])
            self._moment_fbo[i] = ctx.framebuffer(mtex)
            atex = ctx.texture((w, h), 4, dtype='f2')
            atex.repeat_x = False
            atex.repeat_y = False
            self._atrous_buf[i] = atex
            self._atrous_fbo[i] = ctx.framebuffer(atex)
        self._history_valid = False
        self._cur_index = 0

    def _release_buffers(self):
        for i in range(2):
            for obj in (self._history[i], self._history_fbo[i],
                        self._moment[i], self._moment_fbo[i],
                        self._atrous_buf[i], self._atrous_fbo[i]):
                if obj is not None:
                    try:
                        obj.release()
                    except Exception:
                        pass
        self._history = [None, None]
        self._history_fbo = [None, None]
        self._moment = [None, None]
        self._moment_fbo = [None, None]
        self._atrous_buf = [None, None]
        self._atrous_fbo = [None, None]
        self._buf_w = 0
        self._buf_h = 0
        self._history_valid = False

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None, velocity_tex=None,
               prev_view_proj=None, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return

        self._ensure_resources(ctx)
        self._ensure_buffers(ctx, viewport_w, viewport_h)

        cur = self._cur_index
        prev = 1 - cur

        ctx.disable(moderngl.BLEND)

        current_tex = input_tex if input_tex is not None else scene_color_tex

        self._history_fbo[cur].use()
        self._history_fbo[cur].viewport = (0, 0, viewport_w, viewport_h)
        self._reproj_prog["u_current"] = 0
        current_tex.use(0)
        self._reproj_prog["u_depth"] = 1
        scene_depth_tex.use(1)
        if velocity_tex is not None and "u_velocity" in self._reproj_prog:
            self._reproj_prog["u_velocity"] = 2
            velocity_tex.use(2)
            self._reproj_prog["u_has_velocity"] = 1.0
        else:
            self._reproj_prog["u_has_velocity"] = 0.0
        self._reproj_prog["u_history"] = 4
        self._history[prev].use(4)
        self._reproj_prog["u_moment"] = 5
        self._moment[prev].use(5)
        self._reproj_prog["u_pixel"].value = (1.0 / viewport_w, 1.0 / viewport_h)
        self._reproj_prog["u_disocclusion"].value = self._disocclusion
        self._reproj_prog["u_stability"].value = self._stability
        self._reproj_prog["u_has_history"] = 1.0 if self._history_valid else 0.0
        self._vao_reproj.render()
        ctx.memory_barrier(moderngl.ALL_BARRIER_BITS)

        atrous_src = self._history[cur]
        atrous_src_fbo = self._history_fbo[cur]

        iters = max(1, min(self._iterations, 8))
        for i in range(iters):
            atrous_dst_idx = i % 2
            atrous_dst_fbo = self._atrous_fbo[atrous_dst_idx]
            atrous_dst_fbo.use()
            atrous_dst_fbo.viewport = (0, 0, viewport_w, viewport_h)
            self._atrous_prog["u_color"] = 0
            atrous_src.use(0)
            self._atrous_prog["u_depth"] = 1
            scene_depth_tex.use(1)
            self._atrous_prog["u_moment"] = 5
            self._moment[cur].use(5)
            self._atrous_prog["u_pixel"].value = (1.0 / viewport_w, 1.0 / viewport_h)
            self._atrous_prog["u_step_size"] = float(1 << i)
            self._atrous_prog["u_phi_depth"].value = self._phi_depth
            self._atrous_prog["u_phi_normal"].value = self._phi_normal
            self._atrous_prog["u_phi_luma"].value = self._phi_luma
            self._vao_atrous.render()
            atrous_src = self._atrous_buf[atrous_dst_idx]
            atrous_src_fbo = atrous_dst_fbo

        if output_fbo is not None:
            output_fbo.use()
            output_fbo.viewport = (0, 0, viewport_w, viewport_h)
        self._final_prog["u_input"] = 0
        atrous_src.use(0)
        self._vao_final.render()

        self._cur_index = prev
        self._history_valid = True
        self._frame_count += 1

    def on_disable(self):
        super().on_disable()
        self._history_valid = False

    def _release_gl(self):
        self._release_buffers()
        for obj in (self._reproj_prog, self._atrous_prog, self._final_prog,
                    self._vao_reproj, self._vao_atrous, self._vao_final,
                    self._vbo, self._ibo):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._reproj_prog = None
        self._atrous_prog = None
        self._final_prog = None
        self._vao_reproj = None
        self._vao_atrous = None
        self._vao_final = None
        self._vbo = None
        self._ibo = None

    @property
    def stability(self) -> float:
        return getattr(self, '_stability', 0.9)

    @stability.setter
    def stability(self, v: float):
        self._stability = v

    @property
    def disocclusion(self) -> float:
        return getattr(self, '_disocclusion', 0.08)

    @disocclusion.setter
    def disocclusion(self, v: float):
        self._disocclusion = v

    @property
    def phi_depth(self) -> float:
        return getattr(self, '_phi_depth', 1.0)

    @phi_depth.setter
    def phi_depth(self, v: float):
        self._phi_depth = v

    @property
    def phi_normal(self) -> float:
        return getattr(self, '_phi_normal', 128.0)

    @phi_normal.setter
    def phi_normal(self, v: float):
        self._phi_normal = v

    @property
    def phi_luma(self) -> float:
        return getattr(self, '_phi_luma', 4.0)

    @phi_luma.setter
    def phi_luma(self, v: float):
        self._phi_luma = v

    @property
    def iterations(self) -> int:
        return getattr(self, '_iterations', 5)

    @iterations.setter
    def iterations(self, v: int):
        self._iterations = v
