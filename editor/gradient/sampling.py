# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def _default_gradient():
    return [(0.0, [0.0, 0.0, 0.0, 1.0]), (1.0, [1.0, 1.0, 1.0, 1.0])]


def _sample_gradient(stops, t):
    if not stops:
        return [0, 0, 0, 1]
    t = max(0.0, min(1.0, t))
    stops = sorted(stops, key=lambda s: s[0])
    if t <= stops[0][0]:
        return list(stops[0][1])
    if t >= stops[-1][0]:
        return list(stops[-1][1])
    for i in range(len(stops) - 1):
        t1, c1 = stops[i]
        t2, c2 = stops[i + 1]
        if t1 <= t <= t2:
            if t2 - t1 < 1e-10:
                return list(c1)
            f = (t - t1) / (t2 - t1)
            return [c1[j] + (c2[j] - c1[j]) * f for j in range(4)]
    return list(stops[-1][1])
