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
from core.components.rendering.postfx.ssaop.shaders import SSAO_VERT, COMP_FRAG, _build_ao_frag, NP_RNG


@ComponentRegistry.register
class SSAO(GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "AO"
    render_type = "screen"
    _skip_rate = 0
    _intensity_prop = "_intensity"

    def __init__(self):
        super().__init__()
        self._radius: float = 1.0
        self._power: float = 2.0
        self._bias: float = 0.025
        self._kernel_size: int = 32
        self._intensity: float = 1.0
        self._bilateral_radius: float = 3.0
        self._bilateral_sigma: float = 50.0
        self._performance_scale: float = 0.5
        self._ctx: Optional[moderngl.Context] = None
        self._prog_ao: Optional[moderngl.Program] = None
        self._prog_comp: Optional[moderngl.Program] = None
        self._vao_ao: Optional[moderngl.VertexArray] = None
        self._vao_comp: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._noise_tex: Optional[moderngl.Texture] = None
        self._temp_fbo: Optional[moderngl.Framebuffer] = None
        self._fbo_size: tuple[int, int] = (0, 0)
        self._cached_kernel_size: int = self._kernel_size

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("_header_main", "Ambient Occlusion", FieldType.HEADER),
            InspectorField("_intensity", "Intensity", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=3),
            InspectorField("_radius", "Radius", FieldType.SLIDER, min_val=0.1, max_val=5.0, step=0.1, decimals=2),
            InspectorField("_power", "Power", FieldType.SLIDER, min_val=0.1, max_val=5.0, step=0.1, decimals=2),
            InspectorField("_bias", "Bias", FieldType.SLIDER, min_val=0.0, max_val=0.1, step=0.005, decimals=4),
            InspectorField("_header_quality", "Quality", FieldType.HEADER),
            InspectorField("_kernel_size", "Samples", FieldType.INT_SLIDER, min_val=4, max_val=64, step=1),
            InspectorField("_performance_scale", "Resolution Scale", FieldType.SLIDER, min_val=0.25, max_val=1.0, step=0.25, decimals=2),
            InspectorField("_bilateral_radius", "Blur Radius", FieldType.SLIDER, min_val=1.0, max_val=6.0, step=0.5, decimals=1),
            InspectorField("_bilateral_sigma", "Edge Sensitivity", FieldType.SLIDER, min_val=1.0, max_val=200.0, step=1.0, decimals=0),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_radius": self._radius,
            "_power": self._power,
            "_bias": self._bias,
            "_kernel_size": self._kernel_size,
            "_intensity": self._intensity,
            "_bilateral_radius": self._bilateral_radius,
            "_bilateral_sigma": self._bilateral_sigma,
            "_performance_scale": self._performance_scale,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> SSAO:
        inst = super().deserialize(data)
        inst._radius = float(data.get("_radius", 1.0))
        inst._power = float(data.get("_power", 2.0))
        inst._bias = float(data.get("_bias", 0.025))
        inst._kernel_size = int(data.get("_kernel_size", 32))
        inst._intensity = float(data.get("_intensity", 1.0))
        inst._bilateral_radius = float(data.get("_bilateral_radius", 3.0))
        inst._bilateral_sigma = float(data.get("_bilateral_sigma", 50.0))
        inst._performance_scale = float(data.get("_performance_scale", 0.5))
        inst._ctx = None
        inst._prog_ao = None
        inst._prog_comp = None
        inst._vao_ao = None
        inst._vao_comp = None
        inst._vbo = None
        inst._ibo = None
        inst._noise_tex = None
        inst._temp_fbo = None
        inst._fbo_size = (0, 0)
        inst._cached_kernel_size = inst._kernel_size
        return inst

    _res_cache: dict[int, dict] = {}

    def _ensure_resources(self, ctx: moderngl.Context):
        ctx_id = id(ctx)
        rebuild = False
        old_cache = self._res_cache.get(ctx_id)
        if old_cache is not None:
            self._ctx = ctx
            self._prog_ao = old_cache["_prog_ao"]
            self._prog_comp = old_cache["_prog_comp"]
            self._vao_ao = old_cache["_vao_ao"]
            self._vao_comp = old_cache["_vao_comp"]
            self._vbo = old_cache["_vbo"]
            self._ibo = old_cache["_ibo"]
            self._noise_tex = old_cache["_noise_tex"]
            rebuild = old_cache.get("_kernel_size", 0) != self._kernel_size
            if not rebuild:
                return
        self._ctx = ctx
        ao_frag = _build_ao_frag(self._kernel_size)
        self._prog_ao = ctx.program(
            vertex_shader=SSAO_VERT,
            fragment_shader=ao_frag
        )
        self._prog_comp = ctx.program(
            vertex_shader=SSAO_VERT,
            fragment_shader=COMP_FRAG
        )
        if rebuild:
            self._vbo = old_cache["_vbo"]
            self._ibo = old_cache["_ibo"]
        else:
            verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
            indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
            self._vbo = ctx.buffer(verts.tobytes())
            self._ibo = ctx.buffer(indices.tobytes())
        self._vao_ao = ctx.vertex_array(
            self._prog_ao,
            [(self._vbo, "2f", "in_position")],
            self._ibo
        )
        self._vao_comp = ctx.vertex_array(
            self._prog_comp,
            [(self._vbo, "2f", "in_position")],
            self._ibo
        )
        if not rebuild:
            noise_data = NP_RNG.uniform(-1, 1, (4, 4, 4)).astype(np.float32)
            self._noise_tex = ctx.texture((4, 4), 4, data=noise_data.tobytes(), dtype="f4")
            self._noise_tex.repeat_x = True
            self._noise_tex.repeat_y = True
            self._noise_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._cached_kernel_size = self._kernel_size
        self._res_cache[ctx_id] = {
            "_prog_ao": self._prog_ao,
            "_prog_comp": self._prog_comp,
            "_vao_ao": self._vao_ao,
            "_vao_comp": self._vao_comp,
            "_vbo": self._vbo,
            "_ibo": self._ibo,
            "_noise_tex": self._noise_tex,
            "_kernel_size": self._kernel_size,
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

    def _ensure_temp_fbo(self, ctx: moderngl.Context, w: int, h: int):
        if self._temp_fbo is None or self._fbo_size != (w, h):
            if self._temp_fbo is not None:
                self._temp_fbo.release()
            self._temp_fbo = ctx.framebuffer(
                color_attachments=[ctx.texture((w, h), 1, dtype="f4")]
            )
            self._fbo_size = (w, h)

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        if output_fbo is None:
            return
        scale = max(0.25, min(1.0, self._performance_scale))
        aw = max(1, int(viewport_w * scale))
        ah = max(1, int(viewport_h * scale))
        self._ensure_resources(ctx)
        self._ensure_temp_fbo(ctx, aw, ah)
        tex = input_tex if input_tex is not None else scene_color_tex
        self._temp_fbo.use()
        self._temp_fbo.viewport = (0, 0, aw, ah)
        self._temp_fbo.clear(1.0, 0.0, 0.0, 0.0)
        self._prog_ao["u_depth_tex"] = 0
        scene_depth_tex.use(0)
        self._prog_ao["u_noise_tex"] = 1
        self._noise_tex.use(1)
        self._prog_ao["u_proj"].write(proj_mat.to_f32().tobytes())
        self._prog_ao["u_inv_proj"].write(proj_mat.inverted().to_f32().tobytes())
        self._prog_ao["u_pixel_size"].value = (1.0 / aw, 1.0 / ah)
        self._prog_ao["u_resolution"].value = (float(aw), float(ah))
        self._prog_ao["u_radius"].value = self._radius
        self._prog_ao["u_power"].value = self._power
        self._prog_ao["u_bias"].value = self._bias
        ctx.disable(moderngl.BLEND)
        self._vao_ao.render()
        output_fbo.use()
        output_fbo.viewport = (0, 0, viewport_w, viewport_h)
        self._prog_comp["u_input_tex"] = 0
        tex.use(0)
        self._prog_comp["u_ao_tex"] = 1
        self._temp_fbo.color_attachments[0].use(1)
        self._prog_comp["u_depth_tex"] = 2
        scene_depth_tex.use(2)
        self._prog_comp["u_pixel_size"].value = (1.0 / viewport_w, 1.0 / viewport_h)
        self._prog_comp["u_bilateral_sigma"].value = self._bilateral_sigma
        self._prog_comp["u_intensity"].value = self._intensity
        self._prog_comp["u_bilateral_radius"].value = self._bilateral_radius
        self._vao_comp.render()

    def _release_gl(self):
        for obj in (self._prog_ao, self._prog_comp, self._vao_ao, self._vao_comp, self._vbo, self._ibo):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._ctx = None
        self._prog_ao = None
        self._prog_comp = None
        self._vao_ao = None
        self._vao_comp = None
        self._vbo = None
        self._ibo = None
        if self._noise_tex is not None:
            try:
                self._noise_tex.release()
            except Exception:
                pass
            self._noise_tex = None
        if self._temp_fbo is not None:
            try:
                self._temp_fbo.release()
            except Exception:
                pass
            self._temp_fbo = None
        self._fbo_size = (0, 0)
