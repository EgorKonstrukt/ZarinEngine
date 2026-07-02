# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from dataclasses import dataclass, field

VERT_FORMAT = "3f 4f"
VERT_ATTRS = ("in_position", "in_color")
INST_FORMAT = "4f 4f 4f 4f 4f/i"
INST_ATTRS = ("i_row0", "i_row1", "i_row2", "i_row3", "i_color")
INST_STRIDE = 20 * 4

@dataclass
class GpuMesh:
    vao: moderngl.VertexArray
    vbo: moderngl.Buffer
    ibo: Optional[moderngl.Buffer] = None
    vertex_count: int = 0
    instance_stride: int = 0
    instance_vbo: Optional[moderngl.Buffer] = None
    num_instances: int = 0


def _build_ring_verts(segments: int, y: float, r: float = 1.0) -> list[float]:
    verts = []
    for i in range(segments + 1):
        a = 2.0 * np.pi * i / segments
        verts.extend([np.cos(a) * r, y, np.sin(a) * r, 1.0, 1.0, 1.0, 1.0])
    return verts


def make_cone_mesh(ctx: moderngl.Context, prog: moderngl.Program, segments: int = 16) -> GpuMesh:
    ring = _build_ring_verts(segments, 0.0)
    verts = ring + [0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    idx = []
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([i, n, segments])
    base_start = segments + 1
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([base_start, base_start + n, base_start + i])
    base_ring = _build_ring_verts(segments, 0.0)
    verts.extend(base_ring)
    v_data = np.array(verts, dtype=np.float32)
    i_data = np.array(idx, dtype=np.uint32)
    vbo = ctx.buffer(v_data.tobytes())
    ibo = ctx.buffer(i_data.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, VERT_FORMAT, *VERT_ATTRS)], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))


def make_cylinder_mesh(ctx: moderngl.Context, prog: moderngl.Program, segments: int = 12) -> GpuMesh:
    bot_ring = _build_ring_verts(segments, 0.0)
    top_ring = _build_ring_verts(segments, 1.0)
    verts = bot_ring + top_ring
    idx = []
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([i, n, n + segments, i, n + segments, i + segments])
    bot_start = segments * 2
    cap_ring = _build_ring_verts(segments, 0.0)
    verts.extend(cap_ring)
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([bot_start + i, bot_start + n, bot_start])
    top_start = segments * 3
    cap_ring2 = _build_ring_verts(segments, 1.0)
    verts.extend(cap_ring2)
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([top_start, top_start + n, top_start + i])
    v_data = np.array(verts, dtype=np.float32)
    i_data = np.array(idx, dtype=np.uint32)
    vbo = ctx.buffer(v_data.tobytes())
    ibo = ctx.buffer(i_data.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, VERT_FORMAT, *VERT_ATTRS)], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))


def make_cube_mesh(ctx: moderngl.Context, prog: moderngl.Program) -> GpuMesh:
    verts = np.array([
        -0.5, -0.5, -0.5, 1,1,1,1,  0.5, -0.5, -0.5, 1,1,1,1,
         0.5,  0.5, -0.5, 1,1,1,1, -0.5,  0.5, -0.5, 1,1,1,1,
        -0.5, -0.5,  0.5, 1,1,1,1,  0.5, -0.5,  0.5, 1,1,1,1,
         0.5,  0.5,  0.5, 1,1,1,1, -0.5,  0.5,  0.5, 1,1,1,1,
    ], dtype=np.float32)
    idx = np.array([
        0,1,2,0,2,3, 4,5,6,4,6,7,
        0,1,5,0,5,4, 2,3,7,2,7,6,
        0,3,7,0,7,4, 1,2,6,1,6,5,
    ], dtype=np.uint32)
    vbo = ctx.buffer(verts.tobytes())
    ibo = ctx.buffer(idx.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, VERT_FORMAT, *VERT_ATTRS)], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))


def make_quad_mesh(ctx: moderngl.Context, prog: moderngl.Program) -> GpuMesh:
    verts = np.array([
        -0.5, -0.5, 0.0, 1,1,1,1,  0.5, -0.5, 0.0, 1,1,1,1,
         0.5,  0.5, 0.0, 1,1,1,1, -0.5,  0.5, 0.0, 1,1,1,1,
    ], dtype=np.float32)
    idx = np.array([0,1,2,0,2,3], dtype=np.uint32)
    vbo = ctx.buffer(verts.tobytes())
    ibo = ctx.buffer(idx.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, VERT_FORMAT, *VERT_ATTRS)], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))


def make_circle_ring_mesh(ctx: moderngl.Context, prog: moderngl.Program, segments: int = 64) -> GpuMesh:
    ring = _build_ring_verts(segments, 0.0)
    idx = []
    for i in range(segments):
        idx.extend([i, i + 1])
    v_data = np.array(ring, dtype=np.float32)
    i_data = np.array(idx, dtype=np.uint32)
    vbo = ctx.buffer(v_data.tobytes())
    ibo = ctx.buffer(i_data.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, VERT_FORMAT, *VERT_ATTRS)], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))


def make_instance_vao(ctx: moderngl.Context, prog: moderngl.Program,
                      static_mesh: GpuMesh, max_instances: int = 256) -> GpuMesh:
    instance_buf = ctx.buffer(reserve=INST_STRIDE * max_instances, dynamic=True)
    vao = ctx.vertex_array(
        prog,
        [
            (static_mesh.vbo, VERT_FORMAT, *VERT_ATTRS),
            (instance_buf, INST_FORMAT, *INST_ATTRS),
        ],
        static_mesh.ibo
    )
    static_mesh.vao = vao
    static_mesh.instance_vbo = instance_buf
    static_mesh.instance_stride = INST_STRIDE
    return static_mesh


def make_line_vao(ctx: moderngl.Context, prog: moderngl.Program) -> GpuMesh:
    vbo = ctx.buffer(reserve=0, dynamic=True)
    vao = ctx.vertex_array(prog, [(vbo, VERT_FORMAT, *VERT_ATTRS)])
    return GpuMesh(vao=vao, vbo=vbo, vertex_count=0)


_INST_LINE_STRIDE_T = np.array([0.0, 1.0, 1.0, 0.0, 1.0, 0.0], dtype=np.float32)
_INST_LINE_STRIDE_S = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0], dtype=np.float32)

INST_LINE_ATTRS = ("a_unit_start", "a_unit_end", "a_t", "a_side")
INST_LINE_FORMAT = "3f 3f 1f 1f"
INST_LINE_STRIDE = 8 * 4  # 8 floats per vertex

INST_INST_FORMAT = "4f 4f 4f 4f 4f /i"
INST_INST_ATTRS = ("i_row0", "i_row1", "i_row2", "i_row3", "i_color")
INST_INST_STRIDE = 20 * 4


def _build_unit_line_verts(starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    n_segs = starts.shape[0]
    n_verts = n_segs * 6
    verts = np.empty((n_verts, 8), dtype=np.float32)
    verts[:, :3] = np.repeat(starts, 6, axis=0)
    verts[:, 3:6] = np.repeat(ends, 6, axis=0)
    verts[:, 6] = np.tile(_INST_LINE_STRIDE_T, n_segs)
    verts[:, 7] = np.tile(_INST_LINE_STRIDE_S, n_segs)
    return verts


_BOX_CORNERS = np.array([
    [-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
    [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],
], dtype=np.float32)

_BOX_EDGES = np.array([
    (0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)
], dtype=np.int32)


def make_unit_box_line_verts() -> np.ndarray:
    starts = _BOX_CORNERS[_BOX_EDGES[:, 0]]
    ends = _BOX_CORNERS[_BOX_EDGES[:, 1]]
    return _build_unit_line_verts(starts, ends)


def make_unit_sphere_line_verts(segments: int = 24) -> np.ndarray:
    theta = np.linspace(0, 2 * np.pi, segments + 1, dtype=np.float32)
    ct = np.cos(theta); st = np.sin(theta)
    all_starts = np.empty((segments * 3, 3), dtype=np.float32)
    all_ends = np.empty((segments * 3, 3), dtype=np.float32)

    base = np.zeros((segments, 3), dtype=np.float32)
    base[:, 1] = ct[:-1]; base[:, 2] = st[:-1]
    all_starts[:segments] = base
    base[:, 1] = ct[1:]; base[:, 2] = st[1:]
    all_ends[:segments] = base

    base = np.zeros((segments, 3), dtype=np.float32)
    base[:, 0] = ct[:-1]; base[:, 2] = st[:-1]
    all_starts[segments:2*segments] = base
    base[:, 0] = ct[1:]; base[:, 2] = st[1:]
    all_ends[segments:2*segments] = base

    base = np.zeros((segments, 3), dtype=np.float32)
    base[:, 0] = ct[:-1]; base[:, 1] = st[:-1]
    all_starts[2*segments:3*segments] = base
    base[:, 0] = ct[1:]; base[:, 1] = st[1:]
    all_ends[2*segments:3*segments] = base

    return _build_unit_line_verts(all_starts, all_ends)


def make_unit_rect_line_verts() -> np.ndarray:
    starts = np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]], dtype=np.float32)
    ends   = np.array([[1,-1,0],[1,1,0],[-1,1,0],[-1,-1,0]], dtype=np.float32)
    return _build_unit_line_verts(starts, ends)


def make_unit_circle_line_verts(segments: int = 24) -> np.ndarray:
    theta = np.linspace(0, 2*np.pi, segments+1, dtype=np.float32)
    pts = np.zeros((segments+1, 3), dtype=np.float32)
    pts[:, 0] = np.cos(theta); pts[:, 1] = np.sin(theta)
    starts = pts[:-1]; ends = pts[1:]
    return _build_unit_line_verts(starts, ends)


def make_unit_capsule_line_verts(segments: int = 24) -> np.ndarray:
    r = 1.0; half_h = 1.0
    theta = np.linspace(0, 2*np.pi, segments+1, dtype=np.float32)
    ct = np.cos(theta); st = np.sin(theta)
    total_segs = segments * 4 + 8
    all_starts = np.empty((total_segs, 3), dtype=np.float32)
    all_ends = np.empty((total_segs, 3), dtype=np.float32)
    idx = 0
    for ring_axis in (0, 2):
        if ring_axis == 0:
            u = np.array([0,1,0], dtype=np.float32); v = np.array([0,0,1], dtype=np.float32)
        else:
            u = np.array([1,0,0], dtype=np.float32); v = np.array([0,1,0], dtype=np.float32)
        for y_pos in (-half_h, half_h):
            pts = u * ct[:,None] + v * st[:,None]
            pts[:, 1] += y_pos
            n = segments
            all_starts[idx:idx+n] = pts[:-1]; all_ends[idx:idx+n] = pts[1:]; idx += n
    theta8 = np.linspace(0, 2*np.pi, 9, dtype=np.float32)[:-1]
    ct8 = np.cos(theta8); st8 = np.sin(theta8)
    for i in range(8):
        all_starts[idx+i] = [ct8[i], half_h, st8[i]]
        all_ends[idx+i]   = [ct8[i], -half_h, st8[i]]
    return _build_unit_line_verts(all_starts, all_ends)


def make_instance_line_vao(ctx: moderngl.Context, prog: moderngl.Program,
                            unit_verts: np.ndarray, max_instances: int = 512) -> GpuMesh:
    static_vbo = ctx.buffer(unit_verts.tobytes())
    instance_vbo = ctx.buffer(reserve=INST_INST_STRIDE * max_instances, dynamic=True)
    vao = ctx.vertex_array(
        prog,
        [
            (static_vbo, INST_LINE_FORMAT, *INST_LINE_ATTRS),
            (instance_vbo, INST_INST_FORMAT, *INST_INST_ATTRS),
        ]
    )
    return GpuMesh(
        vao=vao,
        vbo=static_vbo,
        instance_vbo=instance_vbo,
        vertex_count=unit_verts.shape[0],
        instance_stride=INST_INST_STRIDE,
        num_instances=0,
    )
