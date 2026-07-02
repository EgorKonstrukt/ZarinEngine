# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np

_SEGMENTS_32 = 32


def generate_box(width: float = 1.0, height: float = 1.0, depth: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    hw, hh, hd = width * 0.5, height * 0.5, depth * 0.5
    positions = np.array([
        [-hw, -hh, -hd], [hw, -hh, -hd], [hw, hh, -hd], [-hw, hh, -hd],
        [-hw, -hh, hd], [hw, -hh, hd], [hw, hh, hd], [-hw, hh, hd],
    ], dtype=np.float32)
    indices = np.array([
        0,2,1, 0,3,2, 1,6,5, 1,2,6, 5,7,4, 5,6,7, 4,3,0, 4,7,3, 3,6,2, 3,7,6, 4,1,5, 4,0,1,
    ], dtype=np.uint32)
    return positions, indices


def generate_sphere(radius: float = 0.5, segments: int = _SEGMENTS_32) -> tuple[np.ndarray, np.ndarray]:
    verts = []
    idx = []
    for lat in range(segments + 1):
        theta = math.pi * lat / segments
        sin_theta = math.sin(theta)
        cos_theta = math.cos(theta)
        for lon in range(segments + 1):
            phi = 2.0 * math.pi * lon / segments
            x = sin_theta * math.cos(phi) * radius
            y = cos_theta * radius
            z = sin_theta * math.sin(phi) * radius
            verts.append([x, y, z])
    for lat in range(segments):
        for lon in range(segments):
            first = lat * (segments + 1) + lon
            second = first + segments + 1
            idx.extend([first, first + 1, second])
            idx.extend([second, first + 1, second + 1])
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.uint32)


def generate_cylinder(radius: float = 0.5, height: float = 1.0, segments: int = _SEGMENTS_32, cap: bool = True) -> tuple[np.ndarray, np.ndarray]:
    verts = []
    idx = []
    half_h = height * 0.5
    for i in range(segments):
        theta = 2.0 * math.pi * i / segments
        ct = math.cos(theta) * radius
        st = math.sin(theta) * radius
        verts.append([ct, -half_h, st])
        verts.append([ct, half_h, st])
    if cap:
        verts.append([0.0, -half_h, 0.0])
        verts.append([0.0, half_h, 0.0])
        center_bot = len(verts) - 2
        center_top = len(verts) - 1
        for i in range(segments):
            a = i * 2
            b = ((i + 1) % segments) * 2
            idx.extend([center_bot, a, b])
            idx.extend([center_top, b + 1, a + 1])
    for i in range(segments):
        a = i * 2
        b = i * 2 + 1
        na = ((i + 1) % segments) * 2
        nb = na + 1
        idx.extend([a, b, na])
        idx.extend([na, b, nb])
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.uint32)


def generate_plane(width: float = 1.0, depth: float = 1.0, w_segments: int = 1, d_segments: int = 1) -> tuple[np.ndarray, np.ndarray]:
    verts = []
    idx = []
    hw, hd = width * 0.5, depth * 0.5
    for z in range(d_segments + 1):
        for x in range(w_segments + 1):
            verts.append([-hw + width * x / w_segments, 0.0, -hd + depth * z / d_segments])
    for z in range(d_segments):
        for x in range(w_segments):
            a = z * (w_segments + 1) + x
            b = a + 1
            c = (z + 1) * (w_segments + 1) + x
            d = c + 1
            idx.extend([a, b, c])
            idx.extend([c, b, d])
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.uint32)


def generate_torus(major_radius: float = 0.5, minor_radius: float = 0.15, major_segments: int = 24, minor_segments: int = 12) -> tuple[np.ndarray, np.ndarray]:
    verts = []
    idx = []
    for i in range(major_segments + 1):
        u = 2.0 * math.pi * i / major_segments
        cu, su = math.cos(u), math.sin(u)
        for j in range(minor_segments + 1):
            v = 2.0 * math.pi * j / minor_segments
            cv, sv = math.cos(v), math.sin(v)
            x = (major_radius + minor_radius * cv) * cu
            y = minor_radius * sv
            z = (major_radius + minor_radius * cv) * su
            verts.append([x, y, z])
    for i in range(major_segments):
        for j in range(minor_segments):
            a = i * (minor_segments + 1) + j
            b = a + 1
            c = (i + 1) * (minor_segments + 1) + j
            d = c + 1
            idx.extend([a, b, c])
            idx.extend([c, b, d])
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.uint32)


def generate_cone(radius: float = 0.5, height: float = 1.0, segments: int = _SEGMENTS_32) -> tuple[np.ndarray, np.ndarray]:
    verts = []
    idx = []
    half_h = height * 0.5
    tip = [0.0, half_h, 0.0]
    verts.append(tip)
    tip_idx = 0
    for i in range(segments):
        theta = 2.0 * math.pi * i / segments
        ct = math.cos(theta) * radius
        st = math.sin(theta) * radius
        verts.append([ct, -half_h, st])
    center_bot = len(verts)
    verts.append([0.0, -half_h, 0.0])
    for i in range(segments):
        a = i + 1
        b = ((i + 1) % segments) + 1
        idx.extend([tip_idx, b, a])
        idx.extend([center_bot, a, b])
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.uint32)


def generate_stairs(width: float = 1.0, height: float = 1.0, depth: float = 1.0, steps: int = 8) -> tuple[np.ndarray, np.ndarray]:
    hw = width * 0.5
    step_h = height / steps
    step_d = depth / steps
    positions = []
    idx = []
    for i in range(steps):
        y0 = i * step_h
        y1 = (i + 1) * step_h
        z0 = i * step_d
        z1 = (i + 1) * step_d
        base = len(positions)
        positions.extend([
            [-hw, y0, z0], [hw, y0, z0], [hw, y1, z0], [-hw, y1, z0],
            [-hw, y0, z1], [hw, y0, z1], [hw, y1, z1], [-hw, y1, z1],
        ])
        idx.extend([
            base, base+2, base+1, base, base+3, base+2,
            base+1, base+6, base+5, base+1, base+2, base+6,
            base+5, base+7, base+4, base+5, base+6, base+7,
            base+4, base+3, base+0, base+4, base+7, base+3,
            base+3, base+6, base+2, base+3, base+7, base+6,
            base+4, base+1, base+5, base+4, base+0, base+1,
        ])
    return np.array(positions, dtype=np.float32), np.array(idx, dtype=np.uint32)


def generate_pipe(radius: float = 0.5, thickness: float = 0.1, height: float = 1.0, segments: int = _SEGMENTS_32) -> tuple[np.ndarray, np.ndarray]:
    inner = radius - thickness
    outer = radius
    half_h = height * 0.5
    verts = []
    idx = []
    for i in range(segments + 1):
        theta = 2.0 * math.pi * i / segments
        ct, st = math.cos(theta), math.sin(theta)
        verts.append([inner * ct, -half_h, inner * st])
        verts.append([outer * ct, -half_h, outer * st])
        verts.append([inner * ct, half_h, inner * st])
        verts.append([outer * ct, half_h, outer * st])
    for i in range(segments):
        base = i * 4
        nb = ((i + 1) % segments) * 4
        a, b, c, d = base, base + 1, base + 2, base + 3
        na, nb, nc, nd = nb, nb + 1, nb + 2, nb + 3
        idx.extend([a, c, na, na, c, nc])
        idx.extend([b, nb, d, nb, nd, d])
        idx.extend([a, b, c, c, b, d])
        idx.extend([na, nc, nb, nc, nd, nb])
    return np.array(verts, dtype=np.float32), np.array(idx, dtype=np.uint32)


_PRIMITIVE_REGISTRY = {
    "Box": generate_box,
    "Sphere": generate_sphere,
    "Cylinder": generate_cylinder,
    "Plane": generate_plane,
    "Torus": generate_torus,
    "Cone": generate_cone,
    "Pipe": generate_pipe,
    "Stairs": generate_stairs,
}


def get_primitive_names() -> list[str]:
    return list(_PRIMITIVE_REGISTRY.keys())


def create_primitive(name: str, **kwargs) -> tuple[np.ndarray, np.ndarray]:
    generator = _PRIMITIVE_REGISTRY.get(name)
    if generator is None:
        raise ValueError(f"Unknown primitive: {name}")
    return generator(**kwargs)
