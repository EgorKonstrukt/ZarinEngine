from __future__ import annotations
import math
from typing import TYPE_CHECKING
from core.math3d import Vec3
from core.components.rendering.particle_system import ShapeType

if TYPE_CHECKING:
    from core.ecs import Entity


def get_particle_emitter_lines(
    entity: Entity,
    color: list[float] | None = None,
) -> list[tuple[Vec3, Vec3, list[float]]]:
    if color is None:
        color = [0.8, 0.3, 0.8, 0.6]

    tr = entity.get_component_by_name("Transform")
    if not tr:
        return []

    ps = entity.get_component_by_name("ParticleSystem")
    if not ps:
        return []

    world_pos, world_rot, _ = tr.world_matrix.decompose()
    R = world_rot.to_matrix4()._d[:3, :3]
    lines: list[tuple[Vec3, Vec3, list[float]]] = []

    def local_to_world(v: Vec3) -> Vec3:
        return world_pos + Vec3(
            v.x * R[0, 0] + v.y * R[0, 1] + v.z * R[0, 2],
            v.x * R[1, 0] + v.y * R[1, 1] + v.z * R[1, 2],
            v.x * R[2, 0] + v.y * R[2, 1] + v.z * R[2, 2],
        )

    shape = ps.shape_type
    radius = ps.shape_radius
    arc_rad = math.radians(ps.shape_arc)
    segments = 24

    if shape == ShapeType.CONE:
        angle_rad = math.radians(ps.shape_angle)
        half_len = ps.shape_length * 0.5
        base_r = radius
        apex = local_to_world(Vec3(0, -half_len, 0))
        pts = []
        for i in range(segments + 1):
            theta = 2.0 * math.pi * i / segments
            pt = local_to_world(Vec3(math.cos(theta) * base_r, half_len, math.sin(theta) * base_r))
            pts.append(pt)
        for i in range(segments):
            lines.append((pts[i], pts[i + 1], color))
        lines.append((apex, pts[0], color))
        lines.append((apex, pts[segments // 4], color))
        lines.append((apex, pts[segments // 2], color))
        lines.append((apex, pts[3 * segments // 4], color))
        inner_r = base_r * (1.0 - math.tan(angle_rad)) if math.tan(angle_rad) < 1.0 else 0.0
        if inner_r > 0.01:
            inner_pts = []
            for i in range(segments + 1):
                theta = 2.0 * math.pi * i / segments
                pt = local_to_world(Vec3(math.cos(theta) * inner_r, -half_len, math.sin(theta) * inner_r))
                inner_pts.append(pt)
            for i in range(segments):
                lines.append((inner_pts[i], inner_pts[i + 1], color))

    elif shape == ShapeType.SPHERE:
        for axis_idx in range(3):
            pts = []
            for i in range(segments + 1):
                theta = 2.0 * math.pi * i / segments
                if axis_idx == 0:
                    pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                elif axis_idx == 1:
                    pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                else:
                    pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                pts.append(local_to_world(pt))
            for i in range(segments):
                lines.append((pts[i], pts[i + 1], color))
        if arc_rad < math.pi * 2.0 - 0.01:
            arc_pts = []
            for i in range(segments + 1):
                theta = arc_rad * i / segments
                pt = Vec3(math.sin(theta) * radius, 0, math.cos(theta) * radius)
                arc_pts.append(local_to_world(pt))
            for i in range(segments):
                lines.append((arc_pts[i], arc_pts[i + 1], [0.8, 0.8, 0.2, 0.6]))

    elif shape == ShapeType.HEMISPHERE:
        ring_pts = []
        for i in range(segments + 1):
            theta = 2.0 * math.pi * i / segments
            pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
            ring_pts.append(local_to_world(pt))
        for i in range(segments):
            lines.append((ring_pts[i], ring_pts[i + 1], color))
        for axis_idx in [0, 2]:
            pts = []
            for i in range(segments // 2 + 1):
                theta = math.pi * i / segments
                if axis_idx == 0:
                    pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                else:
                    pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                if pt.y < 0:
                    continue
                pts.append(local_to_world(pt))
            for i in range(len(pts) - 1):
                lines.append((pts[i], pts[i + 1], color))
        if arc_rad < math.pi * 2.0 - 0.01:
            arc_pts = []
            for i in range(segments + 1):
                theta = arc_rad * i / segments
                pt = Vec3(math.sin(theta) * radius, 0, math.cos(theta) * radius)
                arc_pts.append(local_to_world(pt))
            for i in range(segments):
                lines.append((arc_pts[i], arc_pts[i + 1], [0.8, 0.8, 0.2, 0.6]))

    elif shape == ShapeType.BOX:
        bx = ps.shape_box or [1, 1, 1]
        hx, hy, hz = bx[0] * 0.5, bx[1] * 0.5, bx[2] * 0.5
        corners_local = [
            Vec3(-hx, -hy, -hz), Vec3(hx, -hy, -hz),
            Vec3(hx, hy, -hz), Vec3(-hx, hy, -hz),
            Vec3(-hx, -hy, hz), Vec3(hx, -hy, hz),
            Vec3(hx, hy, hz), Vec3(-hx, hy, hz),
        ]
        corners = [local_to_world(v) for v in corners_local]
        edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        for a, b in edges:
            lines.append((corners[a], corners[b], color))

    else:
        pts = []
        for i in range(segments + 1):
            theta = arc_rad * i / segments
            pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
            pts.append(local_to_world(pt))
        for i in range(segments):
            lines.append((pts[i], pts[i + 1], color))
        lines.append((world_pos, local_to_world(Vec3(0, 0, 0)), color))

    return lines
