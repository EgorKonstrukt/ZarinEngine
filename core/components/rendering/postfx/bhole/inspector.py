# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.components.inspector_meta import FieldType, InspectorField


class BlackHoleInspectorMixin:
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Black Hole", FieldType.HEADER),
            InspectorField("_schwarzschild_radius", "Schwarzschild Radius", FieldType.SLIDER, min_val=0.2, max_val=12.0, step=0.1, decimals=2),
            InspectorField("_lensing_strength", "Lensing Strength", FieldType.SLIDER, min_val=0.0, max_val=2.5, step=0.05, decimals=2),
            InspectorField("", "Accretion Disk", FieldType.HEADER),
            InspectorField("_show_disk", "Show Disk", FieldType.BOOL),
            InspectorField("_disk_inner", "Disk Inner (Rs)", FieldType.SLIDER, min_val=1.6, max_val=6.0, step=0.1, decimals=2),
            InspectorField("_disk_outer", "Disk Outer (Rs)", FieldType.SLIDER, min_val=4.0, max_val=16.0, step=0.1, decimals=2),
            InspectorField("_disk_brightness", "Disk Brightness", FieldType.SLIDER, min_val=0.0, max_val=6.0, step=0.1, decimals=2),
            InspectorField("_inner_color", "Inner Color", FieldType.COLOR),
            InspectorField("_outer_color", "Outer Color", FieldType.COLOR),
            InspectorField("_rotation_speed", "Rotation Speed", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_doppler_strength", "Doppler Beaming", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_turbulence", "Turbulence", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("", "Photon Ring", FieldType.HEADER),
            InspectorField("_photon_intensity", "Photon Intensity", FieldType.SLIDER, min_val=0.0, max_val=8.0, step=0.1, decimals=2),
            InspectorField("_photon_width", "Photon Width", FieldType.SLIDER, min_val=0.01, max_val=0.5, step=0.01, decimals=3),
            InspectorField("_fringe", "Chromatic Fringe", FieldType.SLIDER, min_val=0.0, max_val=0.1, step=0.005, decimals=3),
        ]
