# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from enum import Enum


class GizmoType(Enum):
    POINT = "point"
    LINE = "line"
    CIRCLE = "circle"
    SPHERE = "sphere"
    BOX = "box"
    ARC = "arc"
    CAPSULE = "capsule"
    GRID = "grid"
    CONE = "cone"
    AXIS = "axis"
    TEXT = "text"
    RING = "ring"
    ARROW = "arrow"
    CROSS = "cross"
    DASHED = "dashed"
    BEZIER = "bezier"
    TRIANGLE = "triangle"
    POLY = "poly"
    CYLINDER = "cylinder"
    ELLIPSE = "ellipse"
    RECT = "rect"
    RAY = "ray"
    BBOX = "bbox"
    FRUSTUM = "frustum"
    HELIX = "helix"
    PARABOLA = "parabola"
    SPLINE = "spline"
    ICOSPHERE = "icosphere"
    LABEL = "label"
    ICON = "icon"
    TORUS = "torus"
    PIPE = "pipe"
    STAR = "star"
    PIE = "pie"
    WEDGE = "wedge"
    SPIRAL = "spiral"
    CHORD = "chord"
    HEMISPHERE = "hemisphere"
    PYRAMID = "pyramid"


class LineStyle(Enum):
    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"
    HIDDEN = "hidden"
