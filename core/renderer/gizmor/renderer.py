# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.renderer.gpu_primitives import GpuMesh
from core.renderer.gizmor.lines import GizmoLinesMixin
from core.renderer.gizmor.icons import GizmoIconsMixin

FATLINE_VERT = """
#version 330 core
uniform mat4 u_mvp;
in vec3 a_start;
in vec3 a_end;
in float a_t;
in float a_side;
in vec4 a_color;
out vec3 v_color;
out float v_alpha;
out float v_t;
out float v_line_len;
uniform float u_thickness_ndc_x;
uniform float u_thickness_ndc_y;
void main() {
    vec4 clip_start = u_mvp * vec4(a_start, 1.0);
    vec4 clip_end   = u_mvp * vec4(a_end,   1.0);
    vec4 clipPos = mix(clip_start, clip_end, a_t);
    vec2 dxy = clip_end.xy - clip_start.xy;
    float len = length(dxy);
    vec2 perp;
    if (len > 1e-6) {
        vec2 dir = dxy / len;
        perp = vec2(-dir.y, dir.x);
    } else {
        perp = vec2(1.0, 0.0);
    }
    float thickness = max(u_thickness_ndc_x, u_thickness_ndc_y);
    float aspect = u_thickness_ndc_y / max(u_thickness_ndc_x, 1e-6);
    vec2 adj_perp = normalize(vec2(perp.x * aspect, perp.y));
    clipPos.xy += adj_perp * a_side * thickness * clipPos.w;
    gl_Position = clipPos;
    v_color = a_color.rgb;
    v_alpha = a_color.a;
    v_t = a_t;
    v_line_len = length(a_end - a_start);
}
"""

FATLINE_FRAG = """
#version 330 core
in vec3 v_color;
in float v_alpha;
in float v_t;
in float v_line_len;
uniform bool u_dash_enabled;
uniform float u_dash_length;
uniform float u_gap_length;
uniform float u_dash_time;
out vec4 fragColor;
void main() {
    if (u_dash_enabled) {
        float total = u_dash_length + u_gap_length;
        float offset = u_dash_time * 1.2;
        float pos = v_t * v_line_len + offset;
        float mod_pos = mod(pos, total);
        if (mod_pos > u_dash_length) {
            discard;
        }
    }
    fragColor = vec4(v_color, v_alpha);
}
"""

class GizmoRenderer(GizmoLinesMixin, GizmoIconsMixin):
    def __init__(self, ctx: moderngl.Context, gizmo_prog: moderngl.Program, fatline_prog: moderngl.Program, solid_prog: moderngl.Program):
        self._ctx = ctx
        self._gizmo_prog = gizmo_prog
        self._fatline_prog = fatline_prog
        self._solid_prog = solid_prog
        self._line_width: float = 2.0
        self._fatline_vbo_start: Optional[moderngl.Buffer] = None
        self._fatline_vbo_end: Optional[moderngl.Buffer] = None
        self._fatline_vbo_t: Optional[moderngl.Buffer] = None
        self._fatline_vbo_side: Optional[moderngl.Buffer] = None
        self._fatline_vbo_color: Optional[moderngl.Buffer] = None
        self._fatline_vao: Optional[moderngl.VertexArray] = None
        self._fatline_capacity: int = 0
        self._fs_starts = np.empty((0, 3), dtype=np.float32)
        self._fs_ends = np.empty((0, 3), dtype=np.float32)
        self._fs_t = np.empty((0,), dtype=np.float32)
        self._fs_side = np.empty((0,), dtype=np.float32)
        self._fs_colors = np.empty((0, 4), dtype=np.float32)
        self._solid_vbo: Optional[moderngl.Buffer] = None
        self._solid_ibo: Optional[moderngl.Buffer] = None
        self._solid_vao: Optional[moderngl.VertexArray] = None
        self._solid_vbo_cap: int = 0
        self._solid_ibo_cap: int = 0
        self._instanced_prog: Optional[moderngl.Program] = None
        self._cone_mesh: Optional[GpuMesh] = None
        self._cylinder_mesh: Optional[GpuMesh] = None
        self._cube_mesh: Optional[GpuMesh] = None
        self._quad_mesh: Optional[GpuMesh] = None
        self._circle_mesh: Optional[GpuMesh] = None
        self._instanced_initialized: bool = False
        self._inst_line_prog: Optional[moderngl.Program] = None
        self._box_inst_mesh: Optional[GpuMesh] = None
        self._sphere_inst_mesh: Optional[GpuMesh] = None
        self._inst_line_initialized: bool = False
        self._raw_line_prog: Optional[moderngl.Program] = None
        self._raw_line_static_vbo: Optional[moderngl.Buffer] = None
        self._raw_line_start_vbo: Optional[moderngl.Buffer] = None
        self._raw_line_end_vbo: Optional[moderngl.Buffer] = None
        self._raw_line_color_vbo: Optional[moderngl.Buffer] = None
        self._raw_line_vao: Optional[moderngl.VertexArray] = None
        self._raw_line_capacity: int = 0
        self._fs_starts: np.ndarray = np.empty((0, 3), dtype=np.float32)
        self._fs_ends: np.ndarray = np.empty((0, 3), dtype=np.float32)
        self._fs_colors4: np.ndarray = np.empty((0, 4), dtype=np.float32)
        self._rl_shadow_scalar: np.ndarray = np.zeros(3, dtype=np.uint32)
        self._rl_shadow_starts: np.ndarray = np.zeros(0, dtype=np.uint32)
        self._rl_shadow_ends: np.ndarray = np.zeros(0, dtype=np.uint32)
        self._rl_shadow_colors: np.ndarray = np.zeros(0, dtype=np.uint32)
        self._rl_shadow_n: int = 0
        self._build_fatline_buffers()
        self._build_solid_buffers()
        self._stat_lines: int = 0
        self._stat_instances: int = 0
        self._stat_mesh_verts: int = 0
        self._stat_draws: int = 0
        self._stat_upload_bytes: int = 0
        self._stat_upload_full: int = 0
        self._stat_upload_partial: int = 0
        self._prog_names: dict = {}

    def _names(self, prog):
        pid = id(prog)
        n = self._prog_names.get(pid)
        if n is None:
            n = frozenset(prog)
            if len(self._prog_names) > 32:
                self._prog_names.clear()
            self._prog_names[pid] = n
        return n

    def _build_fatline_buffers(self, capacity: int = 32768):
        cap = max(capacity, 32768)
        dummy3 = np.zeros(cap * 3, dtype=np.float32)
        dummy1 = np.zeros(cap, dtype=np.float32)
        dummy4 = np.zeros(cap * 4, dtype=np.float32)
        for buf_name in ('_fatline_vbo_start', '_fatline_vbo_end', '_fatline_vbo_t', '_fatline_vbo_side', '_fatline_vbo_color'):
            b = getattr(self, buf_name, None)
            if b is not None:
                try: b.release()
                except: pass
        if self._fatline_vao is not None:
            try: self._fatline_vao.release()
            except: pass
        self._fatline_vbo_start = self._ctx.buffer(dummy3.tobytes(), dynamic=True)
        self._fatline_vbo_end = self._ctx.buffer(dummy3.tobytes(), dynamic=True)
        self._fatline_vbo_t = self._ctx.buffer(dummy1.tobytes(), dynamic=True)
        self._fatline_vbo_side = self._ctx.buffer(dummy1.tobytes(), dynamic=True)
        self._fatline_vbo_color = self._ctx.buffer(dummy4.tobytes(), dynamic=True)
        self._fatline_vao = self._ctx.vertex_array(
            self._fatline_prog,
            [
                (self._fatline_vbo_start, "3f", "a_start"),
                (self._fatline_vbo_end, "3f", "a_end"),
                (self._fatline_vbo_t, "1f", "a_t"),
                (self._fatline_vbo_side, "1f", "a_side"),
                (self._fatline_vbo_color, "4f", "a_color"),
            ]
        )
        self._fs_starts = np.empty((cap, 3), dtype=np.float32)
        self._fs_ends = np.empty((cap, 3), dtype=np.float32)
        self._fs_t = np.empty((cap,), dtype=np.float32)
        self._fs_side = np.empty((cap,), dtype=np.float32)
        self._fs_colors = np.empty((cap, 4), dtype=np.float32)
        self._fatline_capacity = cap

    def _ensure_fatline_capacity(self, n_verts: int):
        if n_verts <= self._fatline_capacity:
            return
        new_cap = int(n_verts * 1.5 + 4096)
        self._build_fatline_buffers(new_cap)

    def _build_solid_buffers(self, vcap: int = 4096, icap: int = 8192):
        vcap = max(vcap, 4096)
        icap = max(icap, 8192)
        for buf_name in ('_solid_vbo', '_solid_ibo'):
            b = getattr(self, buf_name, None)
            if b is not None:
                try: b.release()
                except: pass
        if self._solid_vao is not None:
            try: self._solid_vao.release()
            except: pass
        self._solid_vbo = self._ctx.buffer(np.zeros(vcap * 7, dtype=np.float32).tobytes(), dynamic=True)
        self._solid_ibo = self._ctx.buffer(np.zeros(icap, dtype=np.uint32).tobytes(), dynamic=True)
        self._solid_vao = self._ctx.vertex_array(
            self._solid_prog,
            [(self._solid_vbo, "3f 4f", "in_position", "in_color")],
            self._solid_ibo
        )
        self._solid_vbo_cap = vcap
        self._solid_ibo_cap = icap

    def release(self):
        for buf_name in ('_fatline_vbo_start', '_fatline_vbo_end', '_fatline_vbo_t', '_fatline_vbo_side', '_fatline_vbo_color',
                         '_solid_vbo', '_solid_ibo'):
            b = getattr(self, buf_name, None)
            if b is not None:
                try: b.release()
                except: pass
        for vao_name in ('_fatline_vao', '_solid_vao'):
            v = getattr(self, vao_name, None)
            if v is not None:
                try: v.release()
                except: pass
        for mesh_name in ('_cone_mesh', '_cylinder_mesh', '_cube_mesh', '_quad_mesh', '_circle_mesh'):
            m = getattr(self, mesh_name, None)
            if m is not None:
                if m.vao:
                    try: m.vao.release()
                    except: pass
                if m.vbo:
                    try: m.vbo.release()
                    except: pass
                if m.ibo:
                    try: m.ibo.release()
                    except: pass
                if m.instance_vbo:
                    try: m.instance_vbo.release()
                    except: pass
        if self._instanced_prog:
            try: self._instanced_prog.release()
            except: pass
        for mesh_name in ('_box_inst_mesh', '_sphere_inst_mesh', '_rect_inst_mesh', '_circle_inst_mesh', '_capsule_inst_mesh'):
            m = getattr(self, mesh_name, None)
            if m is not None:
                if m.vao:
                    try: m.vao.release()
                    except: pass
                if m.vbo:
                    try: m.vbo.release()
                    except: pass
                if m.instance_vbo:
                    try: m.instance_vbo.release()
                    except: pass
        if self._inst_line_prog:
            try: self._inst_line_prog.release()
            except: pass
