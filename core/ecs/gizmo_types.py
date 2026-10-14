# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class GizmoStyle:
    glow: bool = False
    dashed: bool = False
    pulsating: bool = False
    color_cycling: bool = False
    xray: bool = False
    line_width: float = 1.0
    dash_length: float = 0.3
    gap_length: float = 0.15
    glow_layers: int = 3
    glow_intensity: float = 0.4
    pulse_speed: float = 2.0
    pulse_min_alpha: float = 0.2
    cycle_speed: float = 1.0
    cull_distance: float = 0.0
    DEFAULT: Optional[GizmoStyle] = None


GizmoStyle.DEFAULT = GizmoStyle()


@dataclass
class GizmoPrimitive:
    starts: np.ndarray
    ends: np.ndarray
    colors: np.ndarray
    style: GizmoStyle = field(default_factory=lambda: GizmoStyle.DEFAULT)
    @classmethod
    def from_lines(cls, lines: list, style: GizmoStyle = None) -> GizmoPrimitive:
        n = len(lines)
        starts = np.zeros((n, 3), dtype=np.float32)
        ends = np.zeros((n, 3), dtype=np.float32)
        colors = np.zeros((n, 4), dtype=np.float32)
        for i, (s, e, c) in enumerate(lines):
            starts[i, 0] = s.x; starts[i, 1] = s.y; starts[i, 2] = s.z
            ends[i, 0] = e.x; ends[i, 1] = e.y; ends[i, 2] = e.z
            colors[i, 0] = c[0]; colors[i, 1] = c[1]; colors[i, 2] = c[2]
            colors[i, 3] = c[3] if len(c) > 3 else 1.0
        return cls(starts, ends, colors, style or GizmoStyle.DEFAULT)


@dataclass
class InstancePrimitive:
    shape_type: str
    transform_flat: np.ndarray
    color: list
