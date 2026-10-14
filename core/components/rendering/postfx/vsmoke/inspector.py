# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.components.inspector_meta import FieldType, InspectorField


class VolumetricSmokeInspectorMixin:
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Volumetric Smoke", FieldType.HEADER),
            InspectorField("_density", "Density", FieldType.SLIDER, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
            InspectorField("_opacity", "Opacity", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_steps", "March Steps", FieldType.INT, min_val=8, max_val=64, step=4),
            InspectorField("_light_steps", "Light Steps", FieldType.INT, min_val=2, max_val=10, step=1),
            InspectorField("", "Noise Octaves", FieldType.HEADER),
            InspectorField("_base_octaves", "Base Octaves", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("_ridge_octaves", "Ridge Octaves", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("_detail_octaves", "Detail Octaves", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("_noise_scale", "Noise Scale", FieldType.SLIDER, min_val=0.05, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_evolution", "Evolution Speed", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_seed", "Seed", FieldType.SLIDER, min_val=0.0, max_val=100.0, step=1.0, decimals=0),
            InspectorField("_wind_dir", "Wind Direction", FieldType.VEC3),
            InspectorField("_wind_speed", "Wind Speed", FieldType.SLIDER, min_val=0.0, max_val=5.0, step=0.1, decimals=1),
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("_fullness", "Fullness", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_filaments", "Filaments", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_erosion", "Erosion", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_cavity", "Cavity", FieldType.SLIDER, min_val=0.0, max_val=0.9, step=0.05, decimals=2),
            InspectorField("_edge_softness", "Edge Softness", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_fade_top", "Fade Top", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_fade_bottom", "Fade Bottom", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("", "Color", FieldType.HEADER),
            InspectorField("_color_deep", "Deep Color", FieldType.COLOR),
            InspectorField("_color_mid", "Mid Color", FieldType.COLOR),
            InspectorField("_color_core", "Core Color", FieldType.COLOR),
            InspectorField("_core_size", "Core Size", FieldType.SLIDER, min_val=0.05, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_emission", "Emission", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.1, decimals=2),
            InspectorField("_ambient", "Ambient", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("", "Light", FieldType.HEADER),
            InspectorField("_scatter", "Sun Scatter", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.1, decimals=2),
            InspectorField("_anisotropy", "Forward Scatter", FieldType.SLIDER, min_val=0.0, max_val=0.95, step=0.05, decimals=2),
            InspectorField("_self_shadow", "Self Shadow", FieldType.BOOL),
            InspectorField("_shadow_strength", "Shadow Strength", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.1, decimals=1),
            InspectorField("_absorption", "Absorption", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.1, decimals=2),
            InspectorField("_depth_fade", "Depth Fade", FieldType.SLIDER, min_val=0.0, max_val=10.0, step=0.5, decimals=1),
        ]
