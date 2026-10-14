# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np


class _Voice:
    __slots__ = ("active", "sample", "wave", "loop_start", "loop_end", "loop_mode",
                 "pos", "vol", "pan", "freq", "base_period", "arp_base",
                 "porta_target", "porta_speed", "vib_pos", "vib_depth", "vib_speed",
                 "vol_up", "vol_down", "offset", "delay_tick", "cut_tick",
                 "retrig_every", "retrig_count", "finetune", "last_volslide",
                 "pitch_mode", "base_freq")

    def __init__(self):
        self.active = False
        self.sample = None
        self.wave = np.zeros(1, dtype=np.float32)
        self.loop_start = 0
        self.loop_end = 0
        self.loop_mode = 0
        self.pos = 0.0
        self.vol = 0.0
        self.pan = 128
        self.freq = 110.0
        self.base_period = 0
        self.arp_base = 0
        self.porta_target = 0
        self.porta_speed = 0
        self.vib_pos = 0
        self.vib_depth = 0
        self.vib_speed = 0
        self.vol_up = 0
        self.vol_down = 0
        self.offset = 0
        self.delay_tick = -1
        self.cut_tick = -1
        self.retrig_every = 0
        self.retrig_count = 0
        self.finetune = 0
        self.last_volslide = 0
        self.pitch_mode = "mod"
        self.base_freq = 0.0
