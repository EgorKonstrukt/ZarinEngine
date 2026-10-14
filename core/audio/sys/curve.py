# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
class AudioRolloffCurve:
    @staticmethod
    def evaluate_normalized(t: float, curve_data: list[list[float]]) -> float:
        if not curve_data:
            return 1.0
        try:
            tt = max(0.0, min(1.0, float(t)))
        except Exception:
            return 1.0
        keys = sorted(curve_data, key=lambda k: k[0])
        if tt <= keys[0][0]:
            return keys[0][1]
        if tt >= keys[-1][0]:
            return keys[-1][1]
        for i in range(len(keys) - 1):
            t0, v0 = keys[i]
            t1, v1 = keys[i + 1]
            if t0 <= tt <= t1:
                dt = t1 - t0
                if dt == 0:
                    return v0
                return v0 + (v1 - v0) * (tt - t0) / dt
        return 1.0
    @staticmethod
    def evaluate(distance: float, min_dist: float, max_dist: float,
                 curve_data: list[list[float]]) -> float:
        if not curve_data or min_dist >= max_dist or max_dist <= 0:
            return 1.0
        if distance <= min_dist:
            return 1.0
        if distance >= max_dist:
            return 0.0
        t = (distance - min_dist) / (max_dist - min_dist)
        return AudioRolloffCurve.evaluate_normalized(t, curve_data)
def _normalize_audio_zone_shape(value) -> str:
    try:
        s = str(getattr(value, "value", value)).strip().lower()
        if "." in s:
            s = s.rsplit(".", 1)[-1]
        if s == "box":
            return "box"
    except Exception:
        pass
    return "sphere"
def _normalize_audio_box_halves(value, default: float) -> tuple[float, float, float]:
    try:
        if value is None:
            raise ValueError()
        if hasattr(value, "x"):
            vals = (float(value.x), float(value.y), float(value.z))
        else:
            vals = (float(value[0]), float(value[1]), float(value[2]))
        out = []
        for v in vals:
            if v != v or v == float("inf") or v == float("-inf"):
                raise ValueError()
            out.append(max(0.0, v) * 0.5)
        return (out[0], out[1], out[2])
    except Exception:
        pass
    try:
        d = max(0.0, float(default)) * 0.5
    except Exception:
        d = 0.0
    return (d, d, d)
def _box_zone_t(listener: tuple[float, float, float], center: tuple[float, float, float],
                inner_half: tuple[float, float, float], outer_half: tuple[float, float, float]) -> float:
    try:
        ix, iy, iz = (max(0.0, float(inner_half[0])), max(0.0, float(inner_half[1])), max(0.0, float(inner_half[2])))
        ox, oy, oz = (max(float(outer_half[0]), ix), max(float(outer_half[1]), iy), max(float(outer_half[2]), iz))
        dx = abs(float(listener[0]) - float(center[0]))
        dy = abs(float(listener[1]) - float(center[1]))
        dz = abs(float(listener[2]) - float(center[2]))
        q_in = max(dx - ix, dy - iy, dz - iz)
        q_out = max(dx - ox, dy - oy, dz - oz)
        if q_out >= 0.0:
            return 1.0
        if q_in <= 0.0:
            return 0.0
        span = q_in - q_out
        if span <= 1e-09:
            return 1.0
        t = q_in / span
        if t < 0.0:
            return 0.0
        if t > 1.0:
            return 1.0
        return t
    except Exception:
        return 1.0
