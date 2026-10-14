# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Callable, Any
from core.gizmo.apiv.types import GizmoType, LineStyle


@dataclass
class GizmoData:
    gizmo_type: GizmoType
    position: Tuple[float, float, float]
    color: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    size: float = 1.0
    duration: float = 0.0
    layer: int = 0
    world_space: bool = True
    thickness: float = 1.0
    filled: bool = False
    alpha: float = 1.0
    text: str = ""
    end_position: Optional[Tuple[float, float, float]] = None
    normal: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    angle_start: float = 0.0
    angle_end: float = 360.0
    segments: int = 32
    inner_radius: float = 0.0
    points: Optional[List[Tuple[float, float, float]]] = None
    up: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    dash_length: float = 0.3
    gap_length: float = 0.15
    font_size: int = 14
    cull_distance: float = -1.0
    on_click: Optional[Callable] = None
    unique_id: Optional[str] = None
    tag: str = ""
    _screen_pos: Optional[Tuple[int, int]] = None
    height: float = 0.0
    radius_y: float = 0.0
    arrow_size: float = 0.2
    turns: float = 3.0
    fov: float = 60.0
    near_plane: float = 0.1
    far_plane: float = 100.0
    min_point: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    max_point: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    subdivisions: int = 1
    rotation: Optional[Tuple[float, float, float, float]] = None
    transform: Optional[List[float]] = None
    billboard: bool = True
    texture_path: str = ''
    line_style: 'LineStyle' = LineStyle.SOLID
