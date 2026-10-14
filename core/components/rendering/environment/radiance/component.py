# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional
import moderngl
import numpy as np
from core.components.inspector_meta import FieldType, InspectorField
from core.ecs import Component, ComponentRegistry
from core.components.rendering.renderers.raytrace import RaytracingRenderer
from core.components.rendering.environment.radiance.resources import RadianceResourcesMixin
from core.components.rendering.environment.radiance.dispatch import RadianceDispatchMixin
from core.components.rendering.environment.radiance.blit import RadianceBlitMixin
@ComponentRegistry.register
class RadianceCascadesGI(RadianceResourcesMixin, RadianceDispatchMixin, RadianceBlitMixin, Component):
    _allow_multiple = False
    NUM_CASCADES = 5
    CASCADE_DIRS = (12, 12, 16, 32, 64)
    CASCADE_STRIDES = (2, 4, 8, 16, 32)
    MODE_TRACE = 0
    MODE_RECONSTRUCT = 1
    MODE_DEBUG_TEST = 2
    MODE_BLUR_H = 3
    MODE_BLUR_V = 4
    MODE_TEMPORAL = 5
    MODE_DEBUG_ATLAS = 6
    MODE_NORMALS = 8
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Radiance Cascades Gi", FieldType.HEADER),
            InspectorField("enabled", "Enabled", FieldType.BOOL),
            InspectorField("_compute_shader_path", "Compute Shader", FieldType.RESOURCE_PATH, file_filter="Compute (*.compute)"),
            InspectorField("_resolution_scale", "Resolution Scale", FieldType.FLOAT, 0.25, 1.0),
            InspectorField("_intensity", "GI Intensity", FieldType.FLOAT, 0.0, 5.0),
            InspectorField("_base_range", "Range", FieldType.FLOAT, 0.1, 8.0),
            InspectorField("_temporal_factor", "Temporal Blend", FieldType.FLOAT, 0.0, 0.99),
            InspectorField("_sky_intensity", "Sky Intensity", FieldType.FLOAT, 0.0, 4.0),
            InspectorField("_show_overlay", "Show Overlay", FieldType.BOOL),
            InspectorField("_debug_mode", "Debug Mode", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self._compute_shader_path: str = "core/shaders/compute/RadianceCascades.compute"
        self._resolution_scale: float = 0.5
        self._intensity: float = 1.0
        self._base_range: float = 2.0
        self._temporal_factor: float = 0.85
        self._sky_intensity: float = 1.0
        self._show_overlay: bool = False
        self._debug_mode: bool = False
        self._program: Optional[moderngl.ComputeShader] = None
        self._cas_tex: list = [None] * self.NUM_CASCADES
        self._gi_output_tex: Optional[moderngl.Texture] = None
        self._gi_temp_tex: Optional[moderngl.Texture] = None
        self._history_tex: Optional[moderngl.Texture] = None
        self._normal_tex: Optional[moderngl.Texture] = None
        self._gi_output_fbo: Optional[moderngl.Framebuffer] = None
        self._gi_temp_fbo: Optional[moderngl.Framebuffer] = None
        self._history_fbo: Optional[moderngl.Framebuffer] = None
        self._fullscreen_quad: Optional[moderngl.VertexArray] = None
        self._fullscreen_prog: Optional[moderngl.Program] = None
        self._rt: RaytracingRenderer = RaytracingRenderer()
        self._ctx_id = 0
        self._prev_width: int = 0
        self._prev_height: int = 0
        self._frame: int = 0
        self._prev_view_proj: Optional[np.ndarray] = None
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "compute_shader_path": self._compute_shader_path,
            "resolution_scale": self._resolution_scale,
            "intensity": self._intensity,
            "base_range": self._base_range,
            "temporal_factor": self._temporal_factor,
            "sky_intensity": self._sky_intensity,
            "show_overlay": self._show_overlay,
            "debug_mode": self._debug_mode,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> RadianceCascadesGI:
        r = cls()
        r.enabled = data.get("enabled", True)
        r._compute_shader_path = cls._resolve_shader_path(data.get("compute_shader_path", "core/shaders/compute/RadianceCascades.compute"))
        r._resolution_scale = float(data.get("resolution_scale", 0.5))
        r._intensity = float(data.get("intensity", 1.0))
        r._base_range = float(data.get("base_range", 2.0))
        r._temporal_factor = float(data.get("temporal_factor", 0.85))
        r._sky_intensity = float(data.get("sky_intensity", 1.0))
        r._show_overlay = data.get("show_overlay", False)
        r._debug_mode = data.get("debug_mode", False)
        return r
    def on_destroy(self):
        self._release_gl()
    def on_disable(self):
        self._release_gl()
