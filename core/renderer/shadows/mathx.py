# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
MAX_POINT_SHADOWS = 4
MAX_SPOT_SHADOWS = 4
_POINT_FACE_DIRS = (
    (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
)
_POINT_FACE_UPS = (
    (0.0, -1.0, 0.0), (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
    (0.0, -1.0, 0.0), (0.0, -1.0, 0.0),
)
def _tr_pos_xyz(tr):
    d = tr.world_matrix._d
    return float(d[3, 0]), float(d[3, 1]), float(d[3, 2])
def _tr_fwd_xyz(tr):
    d = tr.world_matrix._d
    fx = -float(d[2, 0])
    fy = -float(d[2, 1])
    fz = -float(d[2, 2])
    inv = 1.0 / max(1e-12, math.sqrt(fx * fx + fy * fy + fz * fz))
    return fx * inv, fy * inv, fz * inv
def _tr_up_xyz(tr):
    d = tr.world_matrix._d
    ux = float(d[1, 0])
    uy = float(d[1, 1])
    uz = float(d[1, 2])
    inv = 1.0 / max(1e-12, math.sqrt(ux * ux + uy * uy + uz * uz))
    return ux * inv, uy * inv, uz * inv
