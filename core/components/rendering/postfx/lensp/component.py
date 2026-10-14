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
from core.components.rendering.postfx.lensp.shaders import FLARE_VERT, EXTRACT_FRAG, DOWNSAMPLE_FRAG, FLARE_FRAG


@ComponentRegistry.register
class LensFlares(GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "✦"
    render_type = "additive"
    _intensity_prop = "_intensity"

    def __init__(self):
        super().__init__()
        self._intensity: float = 1.0
        self._scale: float = 1.0
        self._glow: float = 1.0
        self._threshold: float = 1.0
        self._soft_threshold: float = 0.5
        self._ghost_intensity: float = 1.0
        self._anamorphic: float = 0.6
        self._chromatic: float = 0.8
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._extract_prog: Optional[moderngl.Program] = None
        self._extract_vao: Optional[moderngl.VertexArray] = None
        self._ds_prog: Optional[moderngl.Program] = None
        self._ds_vao: Optional[moderngl.VertexArray] = None
        self._bright_tex: Optional[moderngl.Texture] = None
        self._bright_fbo: Optional[moderngl.Framebuffer] = None
        self._glow_tex: Optional[moderngl.Texture] = None
        self._glow_fbo: Optional[moderngl.Framebuffer] = None
        self._chain_size: tuple[int, int] = (0, 0)

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Lens Flares", FieldType.HEADER),
            InspectorField("_intensity", "Intensity", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
            InspectorField("_scale", "Scale", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
            InspectorField("_glow", "Glow", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
            InspectorField("_threshold", "Bright Threshold", FieldType.FLOAT, min_val=0.0, max_val=2.0, step=0.05, decimals=3),
            InspectorField("_soft_threshold", "Soft Knee", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_ghost_intensity", "Ghost Intensity", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
            InspectorField("_anamorphic", "Anamorphic Streak", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
            InspectorField("_chromatic", "Chromatic", FieldType.FLOAT, min_val=0.0, max_val=3.0, step=0.05, decimals=2),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_intensity": self._intensity,
            "_scale": self._scale,
            "_glow": self._glow,
            "_threshold": self._threshold,
            "_soft_threshold": self._soft_threshold,
            "_ghost_intensity": self._ghost_intensity,
            "_anamorphic": self._anamorphic,
            "_chromatic": self._chromatic,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> LensFlares:
        inst = super().deserialize(data)
        inst._intensity = float(data.get("_intensity", 1.0))
        inst._scale = float(data.get("_scale", 1.0))
        inst._glow = float(data.get("_glow", 1.0))
        inst._threshold = float(data.get("_threshold", 1.0))
        inst._soft_threshold = float(data.get("_soft_threshold", 0.5))
        inst._ghost_intensity = float(data.get("_ghost_intensity", 1.0))
        inst._anamorphic = float(data.get("_anamorphic", 0.6))
        inst._chromatic = float(data.get("_chromatic", 0.8))
        inst._prog = None
        inst._vao = None
        inst._vbo = None
        inst._ibo = None
        inst._extract_prog = None
        inst._extract_vao = None
        inst._ds_prog = None
        inst._ds_vao = None
        inst._bright_tex = None
        inst._bright_fbo = None
        inst._glow_tex = None
        inst._glow_fbo = None
        inst._chain_size = (0, 0)
        return inst

    _res_prog_cache: dict[int, dict] = {}

    def _ensure_resources(self, ctx: moderngl.Context):
        ctx_id = id(ctx)
        cached = self._res_prog_cache.get(ctx_id)
        if cached is not None:
            self._ctx = ctx
            self._prog = cached["_prog"]
            self._vao = cached["_vao"]
            self._vbo = cached["_vbo"]
            self._ibo = cached["_ibo"]
            self._extract_prog = cached["_extract_prog"]
            self._extract_vao = cached["_extract_vao"]
            self._ds_prog = cached["_ds_prog"]
            self._ds_vao = cached["_ds_vao"]
            return
        self._ctx = ctx
        verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._prog = ctx.program(vertex_shader=FLARE_VERT, fragment_shader=FLARE_FRAG)
        self._extract_prog = ctx.program(vertex_shader=FLARE_VERT, fragment_shader=EXTRACT_FRAG)
        self._ds_prog = ctx.program(vertex_shader=FLARE_VERT, fragment_shader=DOWNSAMPLE_FRAG)
        self._vao = ctx.vertex_array(self._prog, [(self._vbo, "2f", "in_position")], self._ibo)
        self._extract_vao = ctx.vertex_array(self._extract_prog, [(self._vbo, "2f", "in_position")], self._ibo)
        self._ds_vao = ctx.vertex_array(self._ds_prog, [(self._vbo, "2f", "in_position")], self._ibo)
        self._res_prog_cache[ctx_id] = {
            "_prog": self._prog,
            "_vao": self._vao,
            "_vbo": self._vbo,
            "_ibo": self._ibo,
            "_extract_prog": self._extract_prog,
            "_extract_vao": self._extract_vao,
            "_ds_prog": self._ds_prog,
            "_ds_vao": self._ds_vao,
        }
        if len(self._res_prog_cache) > 4:
            oldest = next(iter(self._res_prog_cache))
            self._release_cache_objects({oldest: self._res_prog_cache[oldest]})
            del self._res_prog_cache[oldest]

    def _ensure_chain(self, ctx: moderngl.Context, rw: int, rh: int):
        if self._bright_tex is not None and self._chain_size == (rw, rh):
            return
        self._release_chain()
        gw = max(rw // 2, 16)
        gh = max(rh // 2, 16)
        self._bright_tex = ctx.texture((rw, rh), 4, dtype="f4")
        self._bright_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._bright_fbo = ctx.framebuffer(self._bright_tex)
        self._glow_tex = ctx.texture((gw, gh), 4, dtype="f4")
        self._glow_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._glow_fbo = ctx.framebuffer(self._glow_tex)
        self._chain_size = (rw, rh)

    def _release_chain(self):
        for obj in (self._bright_fbo, self._bright_tex, self._glow_fbo, self._glow_tex):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._bright_tex = None
        self._bright_fbo = None
        self._glow_tex = None
        self._glow_fbo = None
        self._chain_size = (0, 0)

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        if self.should_skip():
            return
        self._ensure_resources(ctx)
        rw = max(64, int(viewport_w / 4))
        rh = max(36, int(viewport_h / 4))
        self._ensure_chain(ctx, rw, rh)
        prev_fbo = ctx.fbo
        ctx.disable(moderngl.BLEND)
        self._bright_fbo.use()
        self._bright_fbo.viewport = (0, 0, rw, rh)
        self._extract_prog["u_scene_color"] = 0
        self._extract_prog["u_threshold"].value = float(self._threshold)
        self._extract_prog["u_soft_threshold"].value = float(self._soft_threshold)
        scene_color_tex.use(0)
        self._extract_vao.render()
        self._glow_fbo.use()
        self._glow_fbo.viewport = (0, 0, rw // 2, rh // 2)
        self._ds_prog["u_src"] = 0
        self._ds_prog["u_texel"].value = (1.0 / rw, 1.0 / rh)
        self._bright_tex.use(0)
        self._ds_vao.render()
        if prev_fbo is not None:
            w, h = prev_fbo.size
        else:
            w, h = viewport_w, viewport_h
        prev_fbo.use()
        prev_fbo.viewport = (0, 0, w, h)
        ctx.viewport = (0, 0, w, h)
        prog = self._prog
        prog["u_bright_tex"] = 0
        prog["u_glow_tex"] = 1
        prog["u_texel"].value = (1.0 / rw, 1.0 / rh)
        prog["u_intensity"].value = float(self._intensity)
        prog["u_scale"].value = float(self._scale)
        prog["u_glow"].value = float(self._glow)
        prog["u_ghost_intensity"].value = float(self._ghost_intensity)
        prog["u_anamorphic"].value = float(self._anamorphic)
        prog["u_chromatic"].value = float(self._chromatic)
        self._bright_tex.use(0)
        self._glow_tex.use(1)
        ctx.blend_func = moderngl.ONE, moderngl.ONE
        ctx.enable(moderngl.BLEND)
        self._vao.render()
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def _release_gl(self):
        self._release_chain()
        for obj in (self._prog, self._vao, self._vbo, self._ibo,
                    self._extract_prog, self._extract_vao,
                    self._ds_prog, self._ds_vao):
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
        self._extract_prog = None
        self._extract_vao = None
        self._ds_prog = None
        self._ds_vao = None

    @property
    def intensity(self) -> float:
        return getattr(self, "_intensity", 1.0)

    @intensity.setter
    def intensity(self, v: float):
        self._intensity = v

    @property
    def threshold(self) -> float:
        return getattr(self, "_threshold", 1.0)

    @threshold.setter
    def threshold(self, v: float):
        self._threshold = v
