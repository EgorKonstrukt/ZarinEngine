# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from enum import Enum

class GizmoMode(Enum):
    NONE = "none"
    TRANSLATE = "translate"
    ROTATE = "rotate"
    SCALE = "scale"
    MULTI = "multi"

class GizmoSpace(Enum):
    WORLD = "world"
    LOCAL = "local"

class GizmoAlignment(Enum):
    WORLD = "world"
    LOCAL = "local"
    VIEW = "view"
    CUSTOM = "custom"

class GizmoAxis(Enum):
    NONE = 0
    X = 1
    Y = 2
    Z = 3
    XY = 4
    XZ = 5
    YZ = 6
    ALL = 7

AXIS_COLORS = {
    GizmoAxis.X: [0.900, 0.050, 0.050, 1.0],
    GizmoAxis.Y: [0.388, 0.900, 0.050, 1.0],
    GizmoAxis.Z: [0.050, 0.388, 0.921, 1.0],
    GizmoAxis.XY: [0.050, 0.388, 0.921, 0.4],
    GizmoAxis.XZ: [0.388, 0.792, 0.050, 0.4],
    GizmoAxis.YZ: [0.900, 0.050, 0.050, 0.4],
    GizmoAxis.ALL: [1.0, 1.0, 1.0, 1.0],
}
AXIS_HIGHLIGHT = [1.0, 0.835, 0.0, 1.0]
