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
from .vert import FSR2_VERT
from .easu import EASU_FRAG
from .temporal import TEMPORAL_FRAG
from .rcas import RCAS_FRAG


@ComponentRegistry.register
class FidelityFXSuperResolution2(GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "FS2"
    render_type = "screen"
    _use_velocity = True
    _is_upscaler = True

    def __init__(self):
        super().__init__()
        self._stability: float = 0.9
        self._rcas_sharpness: float = 0.2
        self._disocclusion: float = 0.15
        self._variance_gamma: float = 1.25
        self._easu_sharpness: float = 0.35
        self._ctx: Optional[moderngl.Context] = None
        self._easu_prog: Optional[moderngl.Program] = None
        self._temporal_prog: Optional[moderngl.Program] = None
        self._rcas_prog: Optional[moderngl.Program] = None
        self._vao_easu: Optional[moderngl.VertexArray] = None
        self._vao_temporal: Optional[moderngl.VertexArray] = None
        self._vao_rcas: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._easu_tex: Optional[moderngl.Texture] = None
        self._easu_fbo: Optional[moderngl.Framebuffer] = None
        self._recon: list = [None, None]
        self._recon_fbo: list = [None, None]
        self._buf_w: int = 0
        self._buf_h: int = 0
        self._cur_index: int = 0
        self._history_valid: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Fidelity Fx Super Resolution2", FieldType.HEADER),
            InspectorField("_stability", "Temporal Stability", FieldType.FLOAT, min_val=0.0, max_val=0.99, step=0.01, decimals=3),
            InspectorField("_rcas_sharpness", "RCAS Attenuation", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("_disocclusion", "Disocclusion Depth", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.005, decimals=3),
            InspectorField("_variance_gamma", "Variance Clip Gamma", FieldType.FLOAT, min_val=0.5, max_val=4.0, step=0.05, decimals=2),
            InspectorField("_easu_sharpness", "EASU Edge Sharpness", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_stability": self._stability,
            "_rcas_sharpness": self._rcas_sharpness,
            "_disocclusion": self._disocclusion,
            "_variance_gamma": self._variance_gamma,
            "_easu_sharpness": self._easu_sharpness,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> FidelityFXSuperResolution2:
        inst = super().deserialize(data)
        inst._stability = float(data.get("_stability", 0.9))
        inst._rcas_sharpness = float(data.get("_rcas_sharpness", 0.2))
        inst._disocclusion = float(data.get("_disocclusion", 0.15))
        inst._variance_gamma = float(data.get("_variance_gamma", 1.25))
        inst._easu_sharpness = float(data.get("_easu_sharpness", 0.35))
        inst._ctx = None
        inst._easu_prog = None
        inst._temporal_prog = None
        inst._rcas_prog = None
        inst._vao_easu = None
        inst._vao_temporal = None
        inst._vao_rcas = None
        inst._vbo = None
        inst._ibo = None
        inst._easu_tex = None
        inst._easu_fbo = None
        inst._recon = [None, None]
        inst._recon_fbo = [None, None]
        inst._buf_w = 0
        inst._buf_h = 0
        inst._cur_index = 0
        inst._history_valid = False
        return inst

    _res_cache: dict[int, dict] = {}

    def _ensure_resources(self, ctx: moderngl.Context):
        ctx_id = id(ctx)
        cached = self._res_cache.get(ctx_id)
        if cached is not None:
            self._ctx = ctx
            self._easu_prog = cached['_easu_prog']
            self._temporal_prog = cached['_temporal_prog']
            self._rcas_prog = cached['_rcas_prog']
            self._vao_easu = cached['_vao_easu']
            self._vao_temporal = cached['_vao_temporal']
            self._vao_rcas = cached['_vao_rcas']
            self._vbo = cached['_vbo']
            self._ibo = cached['_ibo']
            return
        self._ctx = ctx
        self._easu_prog = ctx.program(vertex_shader=FSR2_VERT, fragment_shader=EASU_FRAG)
        self._temporal_prog = ctx.program(vertex_shader=FSR2_VERT, fragment_shader=TEMPORAL_FRAG)
        self._rcas_prog = ctx.program(vertex_shader=FSR2_VERT, fragment_shader=RCAS_FRAG)
        verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._vao_easu = ctx.vertex_array(self._easu_prog, [(self._vbo, '2f', 'in_position')], self._ibo)
        self._vao_temporal = ctx.vertex_array(self._temporal_prog, [(self._vbo, '2f', 'in_position')], self._ibo)
        self._vao_rcas = ctx.vertex_array(self._rcas_prog, [(self._vbo, '2f', 'in_position')], self._ibo)
        self._res_cache[ctx_id] = {
            '_easu_prog': self._easu_prog,
            '_temporal_prog': self._temporal_prog,
            '_rcas_prog': self._rcas_prog,
            '_vao_easu': self._vao_easu,
            '_vao_temporal': self._vao_temporal,
            '_vao_rcas': self._vao_rcas,
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
        if self._buf_w == w and self._buf_h == h and self._recon[0] is not None:
            return
        self._release_buffers()
        self._buf_w = w
        self._buf_h = h
        for i in range(2):
            tex = ctx.texture((w, h), 4, dtype='f2')
            tex.repeat_x = False
            tex.repeat_y = False
            self._recon[i] = tex
            self._recon_fbo[i] = ctx.framebuffer(tex)
        self._easu_tex = ctx.texture((w, h), 4, dtype='f2')
        self._easu_tex.repeat_x = False
        self._easu_tex.repeat_y = False
        self._easu_fbo = ctx.framebuffer(self._easu_tex)
        self._history_valid = False
        self._cur_index = 0

    def _release_buffers(self):
        for obj in (self._recon[0], self._recon[1], self._recon_fbo[0], self._recon_fbo[1],
                    self._easu_tex, self._easu_fbo):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._recon = [None, None]
        self._recon_fbo = [None, None]
        self._easu_tex = None
        self._easu_fbo = None
        self._buf_w = 0
        self._buf_h = 0
        self._history_valid = False

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None, velocity_tex=None,
               prev_view_proj=None, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        render_w = int(kwargs.get('render_w') or viewport_w)
        render_h = int(kwargs.get('render_h') or viewport_h)
        self._ensure_resources(ctx)
        self._ensure_buffers(ctx, viewport_w, viewport_h)

        upscaling = (render_w != viewport_w) or (render_h != viewport_h)
        cur = self._cur_index
        prev = 1 - cur

        ctx.disable(moderngl.BLEND)

        if upscaling:
            self._easu_fbo.use()
            self._easu_fbo.viewport = (0, 0, viewport_w, viewport_h)
            self._easu_prog["u_src"] = 0
            scene_color_tex.use(0)
            self._easu_prog["u_depth"] = 1
            scene_depth_tex.use(1)
            self._easu_prog["u_src_size"].value = (float(render_w), float(render_h))
            self._easu_prog["u_src_pixel"].value = (1.0 / max(1, render_w), 1.0 / max(1, render_h))
            self._easu_prog["u_sharpness"].value = float(self._easu_sharpness)
            self._vao_easu.render()
            current_tex = self._easu_tex
        else:
            current_tex = input_tex if input_tex is not None else scene_color_tex

        self._recon_fbo[cur].use()
        self._recon_fbo[cur].viewport = (0, 0, viewport_w, viewport_h)
        self._temporal_prog["u_current"] = 0
        current_tex.use(0)
        self._temporal_prog["u_depth"] = 1
        scene_depth_tex.use(1)
        if velocity_tex is not None:
            self._temporal_prog["u_velocity"] = 2
            velocity_tex.use(2)
            self._temporal_prog["u_has_velocity"] = 1.0
        else:
            self._temporal_prog["u_has_velocity"] = 0.0
        self._temporal_prog["u_history"] = 3
        self._recon[prev].use(3)
        self._temporal_prog["u_pixel"].value = (1.0 / viewport_w, 1.0 / viewport_h)
        self._temporal_prog["u_size"].value = (float(viewport_w), float(viewport_h))
        self._temporal_prog["u_stability"].value = self._stability
        self._temporal_prog["u_disocclusion"].value = self._disocclusion
        self._temporal_prog["u_variance_gamma"].value = self._variance_gamma
        self._temporal_prog["u_has_history"] = 1 if self._history_valid else 0

        has_reproj = prev_view_proj is not None
        if has_reproj:
            try:
                cur_forward = proj_mat @ view_mat
                inv_vp = cur_forward.inverted().to_f32()
                self._temporal_prog["u_inv_view_proj"].write(inv_vp.tobytes())
                self._temporal_prog["u_prev_view_proj"].write(prev_view_proj.to_f32().tobytes())
                self._temporal_prog["u_has_reproj"] = 1
            except Exception:
                self._temporal_prog["u_has_reproj"] = 0
        else:
            self._temporal_prog["u_has_reproj"] = 0

        self._vao_temporal.render()

        if output_fbo is not None:
            output_fbo.use()
            output_fbo.viewport = (0, 0, viewport_w, viewport_h)
        ratio = max(float(viewport_w) / max(1.0, float(render_w)), float(viewport_h) / max(1.0, float(render_h)))
        taper = 1.0 / max(1.0, 1.0 + (ratio - 1.0) * 0.5)
        self._rcas_prog["u_rcas_input"] = 0
        self._recon[cur].use(0)
        self._rcas_prog["u_rcas_size"].value = (float(viewport_w), float(viewport_h))
        self._rcas_prog["u_rcas_con"].value = float(2.0 ** (-(self._rcas_sharpness * taper)))
        self._vao_rcas.render()

        self._cur_index = prev
        self._history_valid = True

    def on_disable(self):
        super().on_disable()
        self._history_valid = False

    def _release_gl(self):
        self._release_buffers()
        for obj in (self._easu_prog, self._temporal_prog, self._rcas_prog,
                    self._vao_easu, self._vao_temporal, self._vao_rcas,
                    self._vbo, self._ibo):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._easu_prog = None
        self._temporal_prog = None
        self._rcas_prog = None
        self._vao_easu = None
        self._vao_temporal = None
        self._vao_rcas = None
        self._vbo = None
        self._ibo = None

    @property
    def stability(self) -> float:
        return getattr(self, '_stability', 0.9)

    @stability.setter
    def stability(self, v: float):
        self._stability = v

    @property
    def rcas_sharpness(self) -> float:
        return getattr(self, '_rcas_sharpness', 0.2)

    @rcas_sharpness.setter
    def rcas_sharpness(self, v: float):
        self._rcas_sharpness = v

    @property
    def disocclusion(self) -> float:
        return getattr(self, '_disocclusion', 0.15)

    @disocclusion.setter
    def disocclusion(self, v: float):
        self._disocclusion = v

    @property
    def variance_gamma(self) -> float:
        return getattr(self, '_variance_gamma', 1.25)

    @variance_gamma.setter
    def variance_gamma(self, v: float):
        self._variance_gamma = v

    @property
    def easu_sharpness(self) -> float:
        return getattr(self, '_easu_sharpness', 0.35)

    @easu_sharpness.setter
    def easu_sharpness(self, v: float):
        self._easu_sharpness = v