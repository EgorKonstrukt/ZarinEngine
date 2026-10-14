# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3

FLOAT_T = np.float32

DEF_CAP = 2048

class GpuGizmoBatch:
    __slots__ = ('start_buf', 'end_buf', 'color_buf', 'size', 'capacity')

    def __init__(self, capacity: int = DEF_CAP):
        self.capacity = capacity
        self.start_buf = np.empty((capacity, 3), dtype=FLOAT_T)
        self.end_buf = np.empty((capacity, 3), dtype=FLOAT_T)
        self.color_buf = np.empty((capacity, 4), dtype=FLOAT_T)
        self.size = 0

    def clear(self):
        self.size = 0

    def _ensure(self, n: int):
        needed = self.size + n
        if needed <= self.capacity:
            return
        new_cap = self.capacity
        while new_cap < needed:
            new_cap <<= 1
        new_s = np.empty((new_cap, 3), dtype=FLOAT_T)
        new_e = np.empty((new_cap, 3), dtype=FLOAT_T)
        new_c = np.empty((new_cap, 4), dtype=FLOAT_T)
        new_s[:self.size] = self.start_buf[:self.size]
        new_e[:self.size] = self.end_buf[:self.size]
        new_c[:self.size] = self.color_buf[:self.size]
        self.start_buf = new_s
        self.end_buf = new_e
        self.color_buf = new_c
        self.capacity = new_cap

    def append(self, start: Vec3, end: Vec3, color: list):
        self._ensure(1)
        i = self.size
        self.start_buf[i, 0] = start.x
        self.start_buf[i, 1] = start.y
        self.start_buf[i, 2] = start.z
        self.end_buf[i, 0] = end.x
        self.end_buf[i, 1] = end.y
        self.end_buf[i, 2] = end.z
        self.color_buf[i, 0] = color[0]
        self.color_buf[i, 1] = color[1]
        self.color_buf[i, 2] = color[2]
        self.color_buf[i, 3] = color[3] if len(color) > 3 else 1.0
        self.size = i + 1

    def append_quad(self, corners: list[Vec3], color: list):
        n = len(corners)
        self._ensure(n)
        for i in range(n):
            self.append(corners[i], corners[(i + 1) % n], color)

    def get_arrays(self) -> tuple:
        return (self.start_buf[:self.size], self.end_buf[:self.size], self.color_buf[:self.size])

    def get_flat_verts(self) -> Optional[np.ndarray]:
        if self.size == 0:
            return None
        n = self.size
        out = np.empty((n * 2, 7), dtype=FLOAT_T)
        out[0::2, :3] = self.start_buf[:n]
        out[1::2, :3] = self.end_buf[:n]
        out[0::2, 3:] = self.color_buf[:n]
        out[1::2, 3:] = self.color_buf[:n]
        return out
