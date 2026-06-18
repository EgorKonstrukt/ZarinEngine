from __future__ import annotations
import math
from typing import TYPE_CHECKING
from core.math3d import Vec3

if TYPE_CHECKING:
    from core.ecs import Entity


def get_audio_source_gizmo_lines(
    entity: Entity,
) -> list[tuple[Vec3, Vec3, list[float]]]:
    tr = entity.get_component_by_name("Transform")
    if not tr:
        return []
    audio = entity.get_component_by_name("AudioSource")
    if not audio:
        return []

    pos = tr.position
    min_dist = audio.min_distance
    max_dist = audio.max_distance

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
