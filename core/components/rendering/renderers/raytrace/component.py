# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import numpy as np
import moderngl
from typing import Optional
from core.ecs import Component
from core.components.inspector_meta import FieldType, InspectorField
_INST_STRIDE = 46
_MAX_INSTANCES = 256
_MAX_LIGHTS = 8
_MAT_STRIDE = 20
_MAX_ALBEDO_LAYERS = 32
try:
    from core._raytracing_data import prepare_raytrace_data as _cy_prepare
    _USE_CYTHON_RT = True
except ImportError:
    _USE_CYTHON_RT = False
class RaytraceComponent(Component):
    _allow_multiple = False
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Raytracing Renderer", FieldType.HEADER),
            InspectorField("enabled", "Enabled", FieldType.BOOL),
            InspectorField("_compute_shader_path", "Compute Shader", FieldType.RESOURCE_PATH, file_filter="Compute (*.compute)"),
            InspectorField("_resolution_scale", "Resolution Scale", FieldType.FLOAT, 0.1, 1.0),
            InspectorField("_max_bounces", "Max Bounces", FieldType.INT, 1, 16),
            InspectorField("_samples_per_pixel", "Samples Per Pixel", FieldType.INT, 1, 16),
            InspectorField("_accumulate", "Accumulate Frames", FieldType.BOOL),
            InspectorField("_show_overlay", "Show Overlay", FieldType.BOOL),
            InspectorField("", "Heatmap", FieldType.HEADER),
            InspectorField("_heatmap_mode", "Heatmap Mode", FieldType.INT, 0, 2),
            InspectorField("_heatmap_scale", "Heatmap Scale", FieldType.FLOAT, 1.0, 256.0),
        ]
    def __init__(self):
        super().__init__()
        self._compute_shader_path: str = "core/shaders/compute/Raytracing.compute"
        self._resolution_scale: float = 0.5
        self._max_bounces: int = 1
        self._samples_per_pixel: int = 1
        self._accumulate: bool = False
        self._show_overlay: bool = True
        self._heatmap_mode: int = 0
        self._heatmap_scale: float = 40.0
        self._program: Optional[moderngl.ComputeShader] = None
        self._output_tex: Optional[moderngl.Texture] = None
        self._output_fbo: Optional[moderngl.Framebuffer] = None
        self._emissive_tex: Optional[moderngl.Texture] = None
        self._fullscreen_quad: Optional[moderngl.VertexArray] = None
        self._fullscreen_prog: Optional[moderngl.Program] = None
        self._sky_env_tex: Optional[moderngl.Texture] = None
        self._sky_env_prog: Optional[moderngl.ComputeShader] = None
        self._albedo_array_tex: Optional[moderngl.TextureArray] = None
        self._albedo_tex_map: dict = {}
        self._albedo_array_size: tuple = (256, 256)
        self._albedo_count: int = 0
        self._bvh_buf: Optional[moderngl.Buffer] = None
        self._vert_buf: Optional[moderngl.Buffer] = None
        self._idx_buf: Optional[moderngl.Buffer] = None
        self._mat_buf: Optional[moderngl.Buffer] = None
        self._inst_buf: Optional[moderngl.Buffer] = None
        self._light_buf: Optional[moderngl.Buffer] = None
        self._ctx_id = 0
        self._bvh_np: Optional[np.ndarray] = None
        self._vert_np: Optional[np.ndarray] = None
        self._idx_np: Optional[np.ndarray] = None
        self._mat_np: Optional[np.ndarray] = None
        self._inst_np: Optional[np.ndarray] = None
        self._light_np: Optional[np.ndarray] = None
        self._fixed_bvh: Optional[np.ndarray] = None
        self._fixed_vert: Optional[np.ndarray] = None
        self._fixed_idx: Optional[np.ndarray] = None
        self._fixed_mat: Optional[np.ndarray] = None
        self._fixed_inst: Optional[np.ndarray] = None
        self._fixed_light: Optional[np.ndarray] = None
        self._accum_frame: int = 1
        self._frame: int = 0
        self._prev_view_proj: Optional[np.ndarray] = None
        self._prev_width: int = 0
        self._prev_height: int = 0
        self._rays_per_frame: int = 0
        self._mesh_geo_cache: dict[int, tuple] = {}
        self._geo_signature: Optional[tuple] = None
        self._geo_offsets: list = []
        self._geo_dirty: bool = True
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "compute_shader_path": self._compute_shader_path,
            "resolution_scale": self._resolution_scale,
            "samples_per_pixel": self._samples_per_pixel,
            "accumulate": self._accumulate,
            "show_overlay": self._show_overlay,
            "heatmap_mode": self._heatmap_mode,
            "heatmap_scale": self._heatmap_scale,
        })
        return d
    @staticmethod
    def _resolve_shader_path(path: str) -> str:
        if path and not os.path.isabs(path) and not os.path.exists(os.path.abspath(path)):
            cand = "core/shaders/compute/" + os.path.basename(path).replace("\\", "/")
            if os.path.exists(os.path.abspath(cand)):
                return cand
        return path
    @classmethod
    def deserialize(cls, data: dict):
        r = cls()
        r.enabled = data.get("enabled", True)
        r._compute_shader_path = cls._resolve_shader_path(
            data.get("compute_shader_path", "core/shaders/compute/Raytracing.compute"))
        r._resolution_scale = float(data.get("resolution_scale", 0.5))
        r._samples_per_pixel = int(data.get("samples_per_pixel", 1))
        r._accumulate = data.get("accumulate", False)
        r._show_overlay = data.get("show_overlay", True)
        r._heatmap_mode = int(data.get("heatmap_mode", 0))
        r._heatmap_scale = float(data.get("heatmap_scale", 40.0))
        return r
    def on_destroy(self):
        self._release_gl()
    def on_disable(self):
        self._release_gl()
    def _release_gl(self):
        for buf in [self._bvh_buf, self._vert_buf, self._idx_buf, self._mat_buf, self._inst_buf, self._light_buf]:
            if buf:
                buf.release()
        self._bvh_buf = self._vert_buf = self._idx_buf = self._mat_buf = self._inst_buf = self._light_buf = None
        if self._output_tex:
            self._output_tex.release()
            self._output_tex = None
        if self._output_fbo:
            self._output_fbo.release()
            self._output_fbo = None
        if self._program:
            self._program.release()
            self._program = None
        if self._fullscreen_prog:
            self._fullscreen_prog.release()
            self._fullscreen_prog = None
        if self._fullscreen_quad:
            self._fullscreen_quad.release()
            self._fullscreen_quad = None
        if self._sky_env_tex:
            self._sky_env_tex.release()
            self._sky_env_tex = None
        if self._sky_env_prog:
            self._sky_env_prog.release()
            self._sky_env_prog = None
        if self._albedo_array_tex:
            self._albedo_array_tex.release()
            self._albedo_array_tex = None
        self._albedo_tex_map.clear()
        self._albedo_count = 0
        self._mesh_geo_cache.clear()
        self._geo_signature = None
        self._geo_offsets = []
        self._geo_dirty = True
