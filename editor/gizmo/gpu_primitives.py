from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from dataclasses import dataclass

@dataclass
class GpuMesh:
    vao: moderngl.VertexArray
    vbo: moderngl.Buffer
    ibo: Optional[moderngl.Buffer]
    vertex_count: int
    instance_stride: int = 0
    instance_vbo: Optional[moderngl.Buffer] = None
    num_instances: int = 0

def make_cone_mesh(ctx: moderngl.Context, prog: moderngl.Program, segments: int = 16) -> GpuMesh:
    verts = []
    idx = []
    for i in range(segments):
        a = 2.0 * np.pi * i / segments
        nx = np.cos(a)
        nz = np.sin(a)
        verts.extend([nx, 0.0, nz, 1.0, 1.0, 1.0, 1.0])
    verts.extend([0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0])
    tip = segments
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([i, n, tip])
    base_start = segments + 1
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([base_start, base_start + n, base_start + i])
    for i in range(segments):
        a = 2.0 * np.pi * i / segments
        nx = np.cos(a)
        nz = np.sin(a)
        verts.extend([nx, 0.0, nz, 1.0, 1.0, 1.0, 1.0])
    v_data = np.array(verts, dtype=np.float32)
    i_data = np.array(idx, dtype=np.uint32)
    vbo = ctx.buffer(v_data.tobytes())
    ibo = ctx.buffer(i_data.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "3f 4f", "in_position", "in_color")], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))

def make_cylinder_mesh(ctx: moderngl.Context, prog: moderngl.Program, segments: int = 12) -> GpuMesh:
    verts = []
    idx = []
    for i in range(segments):
        a = 2.0 * np.pi * i / segments
        nx = np.cos(a)
        nz = np.sin(a)
        verts.extend([nx, 0.0, nz, 1.0, 1.0, 1.0, 1.0])
    for i in range(segments):
        a = 2.0 * np.pi * i / segments
        nx = np.cos(a)
        nz = np.sin(a)
        verts.extend([nx, 1.0, nz, 1.0, 1.0, 1.0, 1.0])
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([i, n, n + segments, i, n + segments, i + segments])
    bot_start = segments * 2
    for i in range(segments):
        a = 2.0 * np.pi * i / segments
        nx = np.cos(a)
        nz = np.sin(a)
        verts.extend([nx, 0.0, nz, 1.0, 1.0, 1.0, 1.0])
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([bot_start + i, bot_start + n, bot_start])
    top_start = segments * 3
    for i in range(segments):
        a = 2.0 * np.pi * i / segments
        nx = np.cos(a)
        nz = np.sin(a)
        verts.extend([nx, 1.0, nz, 1.0, 1.0, 1.0, 1.0])
    for i in range(segments):
        n = (i + 1) % segments
        idx.extend([top_start, top_start + n, top_start + i])
    v_data = np.array(verts, dtype=np.float32)
    i_data = np.array(idx, dtype=np.uint32)
    vbo = ctx.buffer(v_data.tobytes())
    ibo = ctx.buffer(i_data.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "3f 4f", "in_position", "in_color")], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))

def make_cube_mesh(ctx: moderngl.Context, prog: moderngl.Program) -> GpuMesh:
    verts = np.array([
        -0.5, -0.5, -0.5,  1,1,1,1,   0.5, -0.5, -0.5,  1,1,1,1,
         0.5,  0.5, -0.5,  1,1,1,1,  -0.5,  0.5, -0.5,  1,1,1,1,
        -0.5, -0.5,  0.5,  1,1,1,1,   0.5, -0.5,  0.5,  1,1,1,1,
         0.5,  0.5,  0.5,  1,1,1,1,  -0.5,  0.5,  0.5,  1,1,1,1,
    ], dtype=np.float32)
    idx = np.array([
        0,1,2,0,2,3, 4,5,6,4,6,7,
        0,1,5,0,5,4, 2,3,7,2,7,6,
        0,3,7,0,7,4, 1,2,6,1,6,5,
    ], dtype=np.uint32)
    vbo = ctx.buffer(verts.tobytes())
    ibo = ctx.buffer(idx.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "3f 4f", "in_position", "in_color")], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))

def make_quad_mesh(ctx: moderngl.Context, prog: moderngl.Program) -> GpuMesh:
    verts = np.array([
        -0.5, -0.5, 0.0, 1,1,1,1,  0.5, -0.5, 0.0, 1,1,1,1,
         0.5,  0.5, 0.0, 1,1,1,1, -0.5,  0.5, 0.0, 1,1,1,1,
    ], dtype=np.float32)
    idx = np.array([0,1,2,0,2,3], dtype=np.uint32)
    vbo = ctx.buffer(verts.tobytes())
    ibo = ctx.buffer(idx.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "3f 4f", "in_position", "in_color")], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))

def make_circle_ring_mesh(ctx: moderngl.Context, prog: moderngl.Program, segments: int = 64) -> GpuMesh:
    verts = []
    idx = []
    for i in range(segments + 1):
        a = 2.0 * np.pi * i / segments
        verts.extend([np.cos(a), 0.0, np.sin(a), 1.0, 1.0, 1.0, 1.0])
        if i < segments:
            idx.extend([i, i + 1])
    v_data = np.array(verts, dtype=np.float32)
    i_data = np.array(idx, dtype=np.uint32)
    vbo = ctx.buffer(v_data.tobytes())
    ibo = ctx.buffer(i_data.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "3f 4f", "in_position", "in_color")], ibo)
    return GpuMesh(vao=vao, vbo=vbo, ibo=ibo, vertex_count=len(idx))

def make_instance_vao(ctx: moderngl.Context, prog: moderngl.Program,
                      static_mesh: GpuMesh, max_instances: int = 256) -> GpuMesh:
    instance_size = 20 * 4
    instance_buf = ctx.buffer(reserve=instance_size * max_instances, dynamic=True)
    vao = ctx.vertex_array(
        prog,
        [
            (static_mesh.vbo, "3f 4f", "in_position", "in_color"),
            (instance_buf, "4f 4f 4f 4f 4f/i", "i_row0", "i_row1", "i_row2", "i_row3", "i_color"),
        ],
        static_mesh.ibo
    )
    static_mesh.vao = vao
    static_mesh.instance_vbo = instance_buf
    static_mesh.instance_stride = instance_size
    return static_mesh
