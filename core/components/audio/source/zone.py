# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from enum import Enum
from core.maths.math3d import Vec3


class AudioZoneShape(Enum):
    SPHERE = "sphere"
    BOX = "box"


def parse_audio_zone_shape(value) -> AudioZoneShape:
    try:
        if isinstance(value, AudioZoneShape):
            return value
        s = str(getattr(value, "value", value)).strip().lower()
        if "." in s:
            s = s.rsplit(".", 1)[-1]
        if s == "box":
            return AudioZoneShape.BOX
    except Exception:
        pass
    return AudioZoneShape.SPHERE


def audio_box_half_tuple(value) -> tuple[float, float, float]:
    try:
        if hasattr(value, "x"):
            return (
                max(0.0, float(value.x)) * 0.5,
                max(0.0, float(value.y)) * 0.5,
                max(0.0, float(value.z)) * 0.5,
            )
        return (
            max(0.0, float(value[0])) * 0.5,
            max(0.0, float(value[1])) * 0.5,
            max(0.0, float(value[2])) * 0.5,
        )
    except Exception:
        return (0.0, 0.0, 0.0)


def audio_box_edges(pos: Vec3, hx: float, hy: float, hz: float, color: list[float]):
    corners = [
        Vec3(pos.x - hx, pos.y - hy, pos.z - hz),
        Vec3(pos.x + hx, pos.y - hy, pos.z - hz),
        Vec3(pos.x + hx, pos.y - hy, pos.z + hz),
        Vec3(pos.x - hx, pos.y - hy, pos.z + hz),
        Vec3(pos.x - hx, pos.y + hy, pos.z - hz),
        Vec3(pos.x + hx, pos.y + hy, pos.z - hz),
        Vec3(pos.x + hx, pos.y + hy, pos.z + hz),
        Vec3(pos.x - hx, pos.y + hy, pos.z + hz),
    ]
    edges = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
    return [(corners[a], corners[b], color) for a, b in edges]


class AudioSourceZoneMixin:
    def is_box_zone(self) -> bool:
        return parse_audio_zone_shape(getattr(self, "zone_shape", "sphere")) == AudioZoneShape.BOX

    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        tr = self.transform
        if not tr:
            return []
        pos = tr.position
        if self.is_box_zone():
            lines: list[tuple[Vec3, Vec3, list[float]]] = []
            ihx, ihy, ihz = audio_box_half_tuple(self.box_inner_size)
            ohx, ohy, ohz = audio_box_half_tuple(self.box_outer_size)
            ohx = max(ohx, ihx)
            ohy = max(ohy, ihy)
            ohz = max(ohz, ihz)
            if ihx > 0.01 or ihy > 0.01 or ihz > 0.01:
                lines.extend(audio_box_edges(pos, ihx, ihy, ihz, [0.2, 1.0, 0.2, 0.5]))
            if ohx > 0.01 or ohy > 0.01 or ohz > 0.01:
                if abs(ohx - ihx) > 0.01 or abs(ohy - ihy) > 0.01 or abs(ohz - ihz) > 0.01:
                    lines.extend(audio_box_edges(pos, ohx, ohy, ohz, [1.0, 0.7, 0.1, 0.4]))
            return lines
        min_dist = self.min_distance
        max_dist = self.max_distance
        lines: list[tuple[Vec3, Vec3, list[float]]] = []
        segments = 24
        min_color = [0.2, 1.0, 0.2, 0.5]
        max_color = [1.0, 0.7, 0.1, 0.4]
        if min_dist > 0.01:
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * min_dist, math.sin(theta) * min_dist)
                    elif axis_idx == 1:
                        pt = Vec3(math.cos(theta) * min_dist, 0, math.sin(theta) * min_dist)
                    else:
                        pt = Vec3(math.cos(theta) * min_dist, math.sin(theta) * min_dist, 0)
                    pts.append(pos + pt)
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], min_color))
        if max_dist > 0.01 and max_dist > min_dist:
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * max_dist, math.sin(theta) * max_dist)
                    elif axis_idx == 1:
                        pt = Vec3(math.cos(theta) * max_dist, 0, math.sin(theta) * max_dist)
                    else:
                        pt = Vec3(math.cos(theta) * max_dist, math.sin(theta) * max_dist, 0)
                    pts.append(pos + pt)
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], max_color))
        return lines

    def gizmo(self):
        lines = self.gizmo_lines()
        if not lines:
            return []
        from core.ecs import GizmoPrimitive, GizmoStyle
        inner = GizmoPrimitive.from_lines(lines, GizmoStyle(pulsating=True, glow=True, pulse_speed=1.5, pulse_min_alpha=0.4))
        return [inner]
