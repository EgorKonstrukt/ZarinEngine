from __future__ import annotations
import math
from enum import Enum
from typing import Optional
from core.math3d import Vec3


class FillMode(Enum):
    WIREFRAME = "wireframe"
    SOLID = "solid"
    FILLED_WIREFRAME = "filled_wireframe"


class GizmoDrawer:

    @staticmethod
    def line(
        start: Vec3, end: Vec3, color: list[float],
    ) -> list[tuple[Vec3, Vec3, list[float]]]:
        return [(start, end, color)]

    @staticmethod
    def rect(
        center: Vec3, size: tuple[float, float], color: list[float],
        fill: FillMode = FillMode.WIREFRAME, rotation: float = 0.0,
    ) -> tuple[list, list]:
        hx, hy = size[0] * 0.5, size[1] * 0.5
        cos_a, sin_a = math.cos(rotation), math.sin(rotation)
        local = [Vec3(-hx, -hy, 0.0), Vec3(hx, -hy, 0.0), Vec3(hx, hy, 0.0), Vec3(-hx, hy, 0.0)]
        corners = []
        for p in local:
            rx = p.x * cos_a - p.y * sin_a
            ry = p.x * sin_a + p.y * cos_a
            corners.append(Vec3(center.x + rx, center.y + ry, center.z))
        return GizmoDrawer._quad(corners, color, fill)

    @staticmethod
    def circle(
        center: Vec3, radius: float, color: list[float],
        fill: FillMode = FillMode.WIREFRAME, segments: int = 32,
    ) -> tuple[list, list]:
        pts = []
        for i in range(segments + 1):
            theta = 2.0 * math.pi * i / segments
            pts.append(Vec3(center.x + math.cos(theta) * radius, center.y + math.sin(theta) * radius, center.z))
        lines = []
        for i in range(segments):
            lines.append((pts[i], pts[i + 1], color))
        meshes = []
        if fill != FillMode.WIREFRAME:
            verts = [center]
            cols = [color]
            idx = [0]
            for i in range(segments + 1):
                verts.append(pts[i])
                cols.append(color)
                if i < segments:
                    idx.append(i + 1)
                    idx.append(0)
                    idx.append(i + 2 if i + 2 <= segments else 1)
            meshes.append((verts, idx, cols))
        if fill == FillMode.FILLED_WIREFRAME:
            return lines, meshes
        if fill == FillMode.SOLID:
            return [], meshes
        return lines, []

    @staticmethod
    def box(
        center: Vec3, size: tuple[float, float, float], color: list[float],
        fill: FillMode = FillMode.WIREFRAME,
    ) -> tuple[list, list]:
        hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        c = center
        corners = [
            Vec3(c.x - hx, c.y - hy, c.z - hz), Vec3(c.x + hx, c.y - hy, c.z - hz),
            Vec3(c.x + hx, c.y + hy, c.z - hz), Vec3(c.x - hx, c.y + hy, c.z - hz),
            Vec3(c.x - hx, c.y - hy, c.z + hz), Vec3(c.x + hx, c.y - hy, c.z + hz),
            Vec3(c.x + hx, c.y + hy, c.z + hz), Vec3(c.x - hx, c.y + hy, c.z + hz),
        ]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        lines = [(corners[a], corners[b], color) for a, b in edges]
        meshes = []
        if fill != FillMode.WIREFRAME:
            faces = [
                (0, 1, 2, 3), (4, 5, 6, 7),
                (0, 1, 5, 4), (2, 3, 7, 6),
                (0, 3, 7, 4), (1, 2, 6, 5),
            ]
            verts = []
            cols = []
            idx = []
            for f in faces:
                i0 = len(verts)
                verts.append(corners[f[0]])
                verts.append(corners[f[1]])
                verts.append(corners[f[2]])
                verts.append(corners[f[3]])
                cols.extend([color] * 4)
                idx.extend([i0, i0 + 1, i0 + 2, i0, i0 + 2, i0 + 3])
            meshes.append((verts, idx, cols))
        if fill == FillMode.FILLED_WIREFRAME:
            return lines, meshes
        if fill == FillMode.SOLID:
            return [], meshes
        return lines, []

    @staticmethod
    def sphere(
        center: Vec3, radius: float, color: list[float],
        fill: FillMode = FillMode.WIREFRAME, segments: int = 16,
    ) -> tuple[list, list]:
        lines = []
        meshes = []
        rings = [
            (0, 1, 2),
            (0, 2, 1),
            (2, 1, 0),
        ]
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
                pts.append(Vec3(center.x + pt.x, center.y + pt.y, center.z + pt.z))
            for i in range(segments):
                lines.append((pts[i], pts[i + 1], color))
        if fill != FillMode.WIREFRAME:
            verts = []
            cols = []
            idx = []
            for lat in range(segments):
                theta1 = math.pi * lat / segments
                theta2 = math.pi * (lat + 1) / segments
                for lon in range(segments):
                    phi1 = 2.0 * math.pi * lon / segments
                    phi2 = 2.0 * math.pi * (lon + 1) / segments
                    p0 = Vec3(
                        center.x + radius * math.sin(theta1) * math.cos(phi1),
                        center.y + radius * math.cos(theta1),
                        center.z + radius * math.sin(theta1) * math.sin(phi1),
                    )
                    p1 = Vec3(
                        center.x + radius * math.sin(theta1) * math.cos(phi2),
                        center.y + radius * math.cos(theta1),
                        center.z + radius * math.sin(theta1) * math.sin(phi2),
                    )
                    p2 = Vec3(
                        center.x + radius * math.sin(theta2) * math.cos(phi2),
                        center.y + radius * math.cos(theta2),
                        center.z + radius * math.sin(theta2) * math.sin(phi2),
                    )
                    p3 = Vec3(
                        center.x + radius * math.sin(theta2) * math.cos(phi1),
                        center.y + radius * math.cos(theta2),
                        center.z + radius * math.sin(theta2) * math.sin(phi1),
                    )
                    i0 = len(verts)
                    verts.extend([p0, p1, p2, p3])
                    cols.extend([color] * 4)
                    idx.extend([i0, i0 + 1, i0 + 2, i0, i0 + 2, i0 + 3])
            meshes.append((verts, idx, cols))
        if fill == FillMode.FILLED_WIREFRAME:
            return lines, meshes
        if fill == FillMode.SOLID:
            return [], meshes
        return lines, []

    @staticmethod
    def arc(
        center: Vec3, radius: float, start_angle: float, end_angle: float,
        color: list[float], fill: FillMode = FillMode.WIREFRAME, segments: int = 24,
    ) -> tuple[list, list]:
        if end_angle < start_angle:
            end_angle += 2.0 * math.pi
        pts = []
        n = max(2, segments)
        for i in range(n + 1):
            t = start_angle + (end_angle - start_angle) * i / n
            pts.append(Vec3(center.x + math.cos(t) * radius, center.y + math.sin(t) * radius, center.z))
        lines = [(pts[i], pts[i + 1], color) for i in range(n)]
        meshes = []
        if fill != FillMode.WIREFRAME:
            verts = [center]
            cols = [color]
            idx = [0]
            for i in range(n + 1):
                verts.append(pts[i])
                cols.append(color)
                if i < n:
                    idx.append(i + 1)
                    idx.append(0)
                    idx.append(i + 2 if i + 2 <= n + 1 else 1)
            meshes.append((verts, idx, cols))
        if fill == FillMode.FILLED_WIREFRAME:
            return lines, meshes
        if fill == FillMode.SOLID:
            return [], meshes
        return lines, []

    @staticmethod
    def _quad(
        corners: list[Vec3], color: list[float], fill: FillMode,
    ) -> tuple[list, list]:
        edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
        lines = [(corners[a], corners[b], color) for a, b in edges]
        meshes = []
        if fill != FillMode.WIREFRAME:
            verts = [corners[0], corners[1], corners[2], corners[3]]
            cols = [color] * 4
            idx = [0, 1, 2, 0, 2, 3]
            meshes.append((verts, idx, cols))
        if fill == FillMode.FILLED_WIREFRAME:
            return lines, meshes
        if fill == FillMode.SOLID:
            return [], meshes
        return lines, []
