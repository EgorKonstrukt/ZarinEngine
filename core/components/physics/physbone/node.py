# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.maths.math3d import Vec3, Quat
class _PBNode:
    __slots__ = ("entity_id", "parent", "children", "is_virtual", "depth", "t", "rest_local_pos", "rest_local_quat", "rest_world_pos", "rest_world_quat", "rest_length", "rest_dir_local")
    def __init__(self):
        self.entity_id = ""
        self.parent = -1
        self.children = []
        self.is_virtual = False
        self.depth = 0
        self.t = 0.0
        self.rest_local_pos = Vec3.zero()
        self.rest_local_quat = Quat.identity()
        self.rest_world_pos = Vec3.zero()
        self.rest_world_quat = Quat.identity()
        self.rest_length = 0.0
        self.rest_dir_local = Vec3(0, 1, 0)
