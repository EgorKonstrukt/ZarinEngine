# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from core.maths.math3d import Vec3, Mat4
from core.renderer.origin import origin_for, relativize_chunk_f32, shifted_vp
from core.renderer.prec import apply_precision
from core.renderer.shaderp import program_with_fallback
from core.renderer.gpu_primitives import GpuMesh, make_cone_mesh, make_cylinder_mesh, make_cube_mesh, make_quad_mesh, make_circle_ring_mesh, make_instance_vao, make_unit_box_line_verts, make_unit_sphere_line_verts, make_unit_rect_line_verts, make_unit_circle_line_verts, make_unit_capsule_line_verts, make_instance_line_vao, VERT_FORMAT, VERT_ATTRS, INST_FORMAT, INST_ATTRS, INST_LINE_FORMAT, INST_LINE_ATTRS, INST_INST_FORMAT, INST_INST_ATTRS

INSTANCED_VERT = """
#version 330 core
in vec3 in_position;
in vec4 in_color;
in vec4 i_row0;
in vec4 i_row1;
in vec4 i_row2;
in vec4 i_row3;
in vec4 i_color;
uniform mat4 u_mvp;
out vec4 v_color;
void main() {
    mat4 i_model = mat4(i_row0, i_row1, i_row2, i_row3);
    v_color = i_color * in_color;
    gl_Position = u_mvp * i_model * vec4(in_position, 1.0);
}
"""

INSTANCED_FRAG = """
#version 330 core
in vec4 v_color;
out vec4 fragColor;
void main() {
    fragColor = v_color;
}
"""

class GizmoIconsMixin:
    def _ensure_instanced_prog(self):
        if self._instanced_prog is not None:
            return
        try:
            self._instanced_prog = self._ctx.program(
                vertex_shader=apply_precision(INSTANCED_VERT),
                fragment_shader=apply_precision(INSTANCED_FRAG)
            )
        except Exception:
            self._instanced_prog = None

    def initialize_instanced_meshes(self):
        if self._instanced_initialized:
            return
        self._ensure_instanced_prog()
        if self._instanced_prog is None:
            return
        ctx = self._ctx
        prog = self._instanced_prog
        self._cone_mesh = make_instance_vao(ctx, prog, make_cone_mesh(ctx, prog))
        self._cylinder_mesh = make_instance_vao(ctx, prog, make_cylinder_mesh(ctx, prog))
        self._cube_mesh = make_instance_vao(ctx, prog, make_cube_mesh(ctx, prog))
        self._quad_mesh = make_instance_vao(ctx, prog, make_quad_mesh(ctx, prog))
        self._circle_mesh = make_instance_vao(ctx, prog, make_circle_ring_mesh(ctx, prog))
        self._instanced_initialized = True

    def _ensure_inst_solid_capacity(self, mesh: GpuMesh, needed: int):
        try:
            cur = mesh.instance_vbo.size // mesh.instance_stride
        except Exception:
            cur = 0
        if needed <= cur:
            return
        new_cap = cur * 2 if cur > 0 else needed
        if new_cap < needed:
            new_cap = needed
        new_buf = self._ctx.buffer(reserve=new_cap * mesh.instance_stride, dynamic=True)
        new_vao = self._ctx.vertex_array(
            self._instanced_prog,
            [
                (mesh.vbo, VERT_FORMAT, *VERT_ATTRS),
                (new_buf, INST_FORMAT, *INST_ATTRS),
            ],
            mesh.ibo
        )
        try:
            mesh.vao.release()
        except Exception:
            pass
        try:
            mesh.instance_vbo.release()
        except Exception:
            pass
        mesh.vao = new_vao
        mesh.instance_vbo = new_buf

    def _ensure_inst_line_capacity(self, mesh: GpuMesh, needed: int):
        try:
            cur = mesh.instance_vbo.size // mesh.instance_stride
        except Exception:
            cur = 0
        if needed <= cur:
            return
        new_cap = cur * 2 if cur > 0 else needed
        if new_cap < needed:
            new_cap = needed
        new_buf = self._ctx.buffer(reserve=new_cap * mesh.instance_stride, dynamic=True)
        new_vao = self._ctx.vertex_array(
            self._inst_line_prog,
            [
                (mesh.vbo, INST_LINE_FORMAT, *INST_LINE_ATTRS),
                (new_buf, INST_INST_FORMAT, *INST_INST_ATTRS),
            ]
        )
        try:
            mesh.vao.release()
        except Exception:
            pass
        try:
            mesh.instance_vbo.release()
        except Exception:
            pass
        mesh.vao = new_vao
        mesh.instance_vbo = new_buf

    def render_instanced(self, mesh: GpuMesh, instance_data: np.ndarray, vp_mat: Mat4, num_instances: int, cam_pos=None):
        if not self._instanced_initialized or mesh.instance_vbo is None:
            return
        self._stat_instances += num_instances
        self._stat_draws += 1
        prog = self._instanced_prog
        _origin = origin_for(cam_pos) if cam_pos is not None else None
        vp_f32 = shifted_vp(vp_mat, _origin).to_f32()
        if "u_mvp" in self._names(prog):
            prog["u_mvp"].write(vp_f32.tobytes())
        data_size = num_instances * mesh.instance_stride
        if data_size > 0:
            self._ensure_inst_solid_capacity(mesh, num_instances)
            _idata = relativize_chunk_f32(instance_data, _origin)
            if _idata.flags.c_contiguous:
                mesh.instance_vbo.write(memoryview(_idata)[:data_size])
            else:
                mesh.instance_vbo.write(_idata[:data_size].tobytes())
            self._stat_upload_bytes += data_size
            self._stat_upload_full += 1
        try:
            old_cull = bool(self._ctx.cull_face)
        except:
            old_cull = True
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.DEPTH_TEST)
        mesh.vao.render(moderngl.TRIANGLES, instances=num_instances)
        if old_cull:
            self._ctx.enable(moderngl.CULL_FACE)
        else:
            self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.DEPTH_TEST)

    def initialize_instanced_lines(self):
        if self._inst_line_initialized:
            return
        self._ensure_inst_line_prog()
        if self._inst_line_prog is None:
            return
        ctx = self._ctx
        prog = self._inst_line_prog
        self._box_inst_mesh = make_instance_line_vao(ctx, prog, make_unit_box_line_verts())
        self._sphere_inst_mesh = make_instance_line_vao(ctx, prog, make_unit_sphere_line_verts())
        self._rect_inst_mesh = make_instance_line_vao(ctx, prog, make_unit_rect_line_verts())
        self._circle_inst_mesh = make_instance_line_vao(ctx, prog, make_unit_circle_line_verts())
        self._capsule_inst_mesh = make_instance_line_vao(ctx, prog, make_unit_capsule_line_verts())
        self._inst_line_initialized = True

    def _ensure_inst_line_prog(self):
        if self._inst_line_prog is not None:
            return
        try:
            self._inst_line_prog = program_with_fallback(self._ctx,
                vertex_shader="""
#version 330 core
layout(location = 0) in vec3 a_unit_start;
layout(location = 1) in vec3 a_unit_end;
layout(location = 2) in float a_t;
layout(location = 3) in float a_side;
in vec4 i_row0;
in vec4 i_row1;
in vec4 i_row2;
in vec4 i_row3;
in vec4 i_color;
uniform mat4 u_mvp;
uniform float u_thickness_ndc_x;
uniform float u_thickness_ndc_y;
out vec4 v_color;
out float v_world_z;
void main() {
    mat4 model = mat4(i_row0, i_row1, i_row2, i_row3);
    vec4 ws_start = model * vec4(a_unit_start, 1.0);
    vec4 ws_end   = model * vec4(a_unit_end, 1.0);
    vec4 clip_start = u_mvp * ws_start;
    vec4 clip_end   = u_mvp * ws_end;
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
    clipPos.xy += perp * a_side * vec2(u_thickness_ndc_x, u_thickness_ndc_y) * clipPos.w;
    gl_Position = clipPos;
    v_color = i_color;
    v_world_z = (ws_start.z + ws_end.z) * 0.5;
}
""",
                fragment_shader="""
#version 330 core
in vec4 v_color;
in float v_world_z;
uniform vec3 u_camera_pos;
out vec4 fragColor;
void main() {
    float dist = abs(v_world_z - u_camera_pos.z);
    float fade = 1.0 - smoothstep(20.0, 80.0, dist);
    fragColor = vec4(v_color.rgb * fade, v_color.a * fade);
}
""",
                label="gizmo_inst_line"
            )
        except Exception:
            self._inst_line_prog = None

    def render_instanced_lines(self, shape_type: str, instance_data: np.ndarray, num_instances: int, vp_mat: Mat4, fw: int, fh: int, thickness_multiplier: float = 1.0, cam_pos: Vec3 = Vec3(0, 0, 0)):
        if not self._inst_line_initialized or self._inst_line_prog is None:
            self.initialize_instanced_lines()
            if self._inst_line_prog is None:
                return
        mesh = None
        if shape_type == 'box':
            mesh = self._box_inst_mesh
        elif shape_type == 'sphere':
            mesh = self._sphere_inst_mesh
        elif shape_type == 'rect':
            mesh = self._rect_inst_mesh
        elif shape_type == 'circle':
            mesh = self._circle_inst_mesh
        elif shape_type == 'capsule':
            mesh = self._capsule_inst_mesh
        if mesh is None or mesh.instance_vbo is None or num_instances == 0:
            return
        self._stat_instances += num_instances
        self._stat_draws += 1
        prog = self._inst_line_prog
        names = self._names(prog)
        _origin = origin_for(cam_pos) if cam_pos is not None else None
        try:
            _ox = float(_origin[0]) if _origin is not None else 0.0
            _oy = float(_origin[1]) if _origin is not None else 0.0
            _oz = float(_origin[2]) if _origin is not None else 0.0
        except Exception:
            _ox = 0.0; _oy = 0.0; _oz = 0.0
        vp_f32 = shifted_vp(vp_mat, _origin).to_f32()
        if "u_mvp" in names:
            prog["u_mvp"].write(vp_f32.tobytes())
        desired_pixels = max(1.0, float(self._line_width) * 1.5 * thickness_multiplier)
        ndc_x = desired_pixels / max(1.0, float(fw))
        ndc_y = desired_pixels / max(1.0, float(fh))
        if "u_thickness_ndc_x" in names:
            prog["u_thickness_ndc_x"] = float(ndc_x)
        if "u_thickness_ndc_y" in names:
            prog["u_thickness_ndc_y"] = float(ndc_y)
        if "u_camera_pos" in names:
            prog["u_camera_pos"].write(np.array([cam_pos.x - _ox, cam_pos.y - _oy, cam_pos.z - _oz], dtype=np.float32).tobytes())
        data_size = num_instances * mesh.instance_stride
        if data_size > 0:
            self._ensure_inst_line_capacity(mesh, num_instances)
            _idata = relativize_chunk_f32(instance_data, _origin)
            if _idata.flags.c_contiguous:
                mesh.instance_vbo.write(memoryview(_idata)[:data_size])
            else:
                mesh.instance_vbo.write(_idata[:data_size].tobytes())
            self._stat_upload_bytes += data_size
            self._stat_upload_full += 1
        try:
            old_cull = bool(self._ctx.cull_face)
        except:
            old_cull = True
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.DEPTH_TEST)
        mesh.vao.render(moderngl.TRIANGLES, vertices=mesh.vertex_count, instances=num_instances)
        if old_cull:
            self._ctx.enable(moderngl.CULL_FACE)
        else:
            self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.DEPTH_TEST)

    def render_meshes(self, meshes: list[tuple], vp_mat: Mat4, cam_pos=None):
        if not self._solid_prog or not meshes:
            return
        for verts, indices, colors in meshes:
            if not verts or not indices or len(indices) < 3:
                continue
            self._stat_mesh_verts += len(verts)
            self._stat_draws += 1
            n = len(verts)
            v_data = np.empty((n, 7), dtype=np.float32)
            for i in range(n):
                v = verts[i]
                v_data[i, 0] = v.x; v_data[i, 1] = v.y; v_data[i, 2] = v.z
                c = colors[i] if i < len(colors) else [1, 1, 1, 1]
                v_data[i, 3] = c[0]; v_data[i, 4] = c[1]; v_data[i, 5] = c[2]
                v_data[i, 6] = c[3] if len(c) > 3 else 1.0
            idx_arr = np.array(indices, dtype=np.uint32)
            n_idx = len(idx_arr)
            if n > self._solid_vbo_cap or n_idx > self._solid_ibo_cap:
                self._build_solid_buffers(n, n_idx)
            self._solid_vbo.write(v_data.tobytes())
            self._solid_ibo.write(idx_arr.tobytes())
            self._stat_upload_bytes += len(v_data) * 28 + len(idx_arr) * 4
            self._stat_upload_full += 1
            self._solid_vao.render(moderngl.TRIANGLES, vertices=n_idx)
        self._ctx.disable(moderngl.BLEND)
        try:
            self._ctx.enable(moderngl.CULL_FACE)
        except:
            pass

    def render_mesh_np(self, v_data: np.ndarray, idx_arr: np.ndarray, vp_mat: Mat4, cam_pos=None):
        prog = self._solid_prog
        if not prog:
            return
        self._stat_mesh_verts += v_data.shape[0]
        self._stat_draws += 1
        _origin = origin_for(cam_pos) if cam_pos is not None else None
        vp_f32 = shifted_vp(vp_mat, _origin).to_f32()
        if "u_mvp" in self._names(prog):
            prog["u_mvp"].write(vp_f32.tobytes())
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        n_idx = len(idx_arr)
        n = v_data.shape[0]
        if n > self._solid_vbo_cap or n_idx > self._solid_ibo_cap:
            self._build_solid_buffers(n, n_idx)
        try:
            _vd = np.ascontiguousarray(v_data, dtype=np.float32)
        except Exception:
            _vd = v_data
        if _origin is not None:
            try:
                _w = np.ascontiguousarray(v_data, dtype=np.float64).copy()
                _w[:, 0] -= float(_origin[0])
                _w[:, 1] -= float(_origin[1])
                _w[:, 2] -= float(_origin[2])
                _vd = np.ascontiguousarray(_w.astype(np.float32))
            except Exception:
                pass
        self._solid_vbo.write(_vd.tobytes())
        self._solid_ibo.write(idx_arr.tobytes())
        self._stat_upload_bytes += len(v_data) * 28 + len(idx_arr) * 4
        self._stat_upload_full += 1
        self._solid_vao.render(moderngl.TRIANGLES, vertices=n_idx)
        self._ctx.disable(moderngl.BLEND)
        try:
            self._ctx.enable(moderngl.CULL_FACE)
        except:
            pass
