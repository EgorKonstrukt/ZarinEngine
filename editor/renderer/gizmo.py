from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.math3d import Vec3, Mat4


class GizmoRenderer:
    """Renders gizmo lines, solid meshes and wireframe overlays."""

    def __init__(self, ctx: moderngl.Context, gizmo_prog: moderngl.Program,
                 fatline_prog: moderngl.Program, solid_prog: moderngl.Program):
        self._ctx = ctx
        self._gizmo_prog = gizmo_prog
        self._fatline_prog = fatline_prog
        self._solid_prog = solid_prog
        self._line_vbo_data: Optional[moderngl.Buffer] = None
        self._line_vao: Optional[moderngl.VertexArray] = None
        self._fatline_vbo_start: Optional[moderngl.Buffer] = None
        self._fatline_vbo_end: Optional[moderngl.Buffer] = None
        self._fatline_vbo_t: Optional[moderngl.Buffer] = None
        self._fatline_vbo_side: Optional[moderngl.Buffer] = None
        self._fatline_vao_persistent: Optional[moderngl.VertexArray] = None
        self._fatline_vbo_capacity: int = 0
        self._solid_vbo: Optional[moderngl.Buffer] = None
        self._solid_ibo: Optional[moderngl.Buffer] = None
        self._solid_vao_persistent: Optional[moderngl.VertexArray] = None
        self._solid_vbo_capacity: int = 0
        self._solid_ibo_capacity: int = 0
        self._line_width: float = 1.0
        self._build_buffers()

    def _build_buffers(self):
        dummy = np.zeros((6,), dtype=np.float32)
        self._line_vbo_data = self._ctx.buffer(dummy.tobytes(), dynamic=True)
        self._line_vao = self._ctx.vertex_array(
            self._gizmo_prog,
            [(self._line_vbo_data, "3f", "in_position")]
        )
        self._ensure_fatline_buffers(2048)
        self._ensure_solid_buffers(512, 1024)

    def _ensure_fatline_buffers(self, n_verts: int):
        if self._fatline_vbo_capacity >= n_verts and self._fatline_vao_persistent is not None:
            return
        cap = max(n_verts, 2048)
        dummy3 = np.zeros(cap * 3, dtype=np.float32)
        dummy1 = np.zeros(cap, dtype=np.float32)
        for attr in ('_fatline_vbo_start', '_fatline_vbo_end', '_fatline_vbo_t', '_fatline_vbo_side'):
            buf = getattr(self, attr)
            if buf is not None:
                try:
                    buf.release()
                except Exception:
                    pass
        if self._fatline_vao_persistent is not None:
            try:
                self._fatline_vao_persistent.release()
            except Exception:
                pass
        self._fatline_vbo_start = self._ctx.buffer(dummy3.tobytes(), dynamic=True)
        self._fatline_vbo_end = self._ctx.buffer(dummy3.tobytes(), dynamic=True)
        self._fatline_vbo_t = self._ctx.buffer(dummy1.tobytes(), dynamic=True)
        self._fatline_vbo_side = self._ctx.buffer(dummy1.tobytes(), dynamic=True)
        self._fatline_vao_persistent = self._ctx.vertex_array(
            self._fatline_prog,
            [
                (self._fatline_vbo_start, "3f", "a_start"),
                (self._fatline_vbo_end, "3f", "a_end"),
                (self._fatline_vbo_t, "1f", "a_t"),
                (self._fatline_vbo_side, "1f", "a_side"),
            ]
        )
        self._fatline_vbo_capacity = cap

    def _ensure_solid_buffers(self, n_verts: int, n_idx: int):
        if (self._solid_vbo_capacity >= n_verts and
                self._solid_ibo_capacity >= n_idx and
                self._solid_vao_persistent is not None):
            return
        vcap = max(n_verts, 512)
        icap = max(n_idx, 1024)
        for attr in ('_solid_vbo', '_solid_ibo'):
            buf = getattr(self, attr)
            if buf is not None:
                try:
                    buf.release()
                except Exception:
                    pass
        if self._solid_vao_persistent is not None:
            try:
                self._solid_vao_persistent.release()
            except Exception:
                pass
        self._solid_vbo = self._ctx.buffer(np.zeros(vcap * 7, dtype=np.float32).tobytes(), dynamic=True)
        self._solid_ibo = self._ctx.buffer(np.zeros(icap, dtype=np.uint32).tobytes(), dynamic=True)
        self._solid_vao_persistent = self._ctx.vertex_array(
            self._solid_prog,
            [(self._solid_vbo, "3f 4f", "in_position", "in_color")],
            self._solid_ibo
        )
        self._solid_vbo_capacity = vcap
        self._solid_ibo_capacity = icap

    def render_lines(self, lines: list[tuple], vp_mat: Mat4,
                     fw: int = 1920, fh: int = 1080, thickness_multiplier: float = 1.0):
        if not self._fatline_prog or not lines:
            return
        desired_pixels = max(1.0, float(self._line_width) * 1.5 * thickness_multiplier)
        color_groups: dict[tuple, list] = {}
        for start, end, color in lines:
            c = (float(color[0]), float(color[1]), float(color[2]))
            color_groups.setdefault(c, []).append((start, end))
        try:
            old_cull_face = bool(self._ctx.cull_face)
        except Exception:
            old_cull_face = True
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.DEPTH_TEST)
        prog = self._fatline_prog
        vp_f32 = vp_mat.to_f32()
        if "u_mvp" in prog:
            prog["u_mvp"].write(vp_f32.tobytes())
        fw_s, fh_s = max(1.0, float(fw)), max(1.0, float(fh))
        ndc_x, ndc_y = desired_pixels / fw_s, desired_pixels / fh_s
        if "u_thickness_ndc_x" in prog:
            prog["u_thickness_ndc_x"] = float(ndc_x)
        if "u_thickness_ndc_y" in prog:
            prog["u_thickness_ndc_y"] = float(ndc_y)
        strip_t = np.array([0.0, 1.0, 1.0, 0.0, 1.0, 0.0], dtype=np.float32)
        strip_s = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0], dtype=np.float32)
        try:
            for color, segs in color_groups.items():
                alpha_val = float(color[3]) if len(color) > 3 else 1.0
                if alpha_val <= 0.001:
                    continue
                n_segs = len(segs)
                n_verts = n_segs * 6
                pts = np.empty((n_segs, 6), dtype=np.float32)
                for i, (s, e) in enumerate(segs):
                    pts[i, 0] = s.x; pts[i, 1] = s.y; pts[i, 2] = s.z
                    pts[i, 3] = e.x; pts[i, 4] = e.y; pts[i, 5] = e.z
                starts_arr = np.repeat(pts[:, :3], 6, axis=0)
                ends_arr = np.repeat(pts[:, 3:], 6, axis=0)
                ts_arr = np.tile(strip_t, n_segs)
                side_arr = np.tile(strip_s, n_segs)
                self._ensure_fatline_buffers(n_verts)
                if n_verts > self._fatline_vbo_capacity:
                    self._fatline_vbo_start.orphan(n_verts * 12)
                    self._fatline_vbo_end.orphan(n_verts * 12)
                    self._fatline_vbo_t.orphan(n_verts * 4)
                    self._fatline_vbo_side.orphan(n_verts * 4)
                    self._fatline_vbo_capacity = n_verts
                self._fatline_vbo_start.write(starts_arr.tobytes())
                self._fatline_vbo_end.write(ends_arr.tobytes())
                self._fatline_vbo_t.write(ts_arr.tobytes())
                self._fatline_vbo_side.write(side_arr.tobytes())
                if "u_line_color" in prog:
                    prog["u_line_color"] = color[:3]
                if "u_alpha" in prog:
                    prog["u_alpha"] = alpha_val
                self._fatline_vao_persistent.render(moderngl.TRIANGLES, vertices=n_verts)
        finally:
            if old_cull_face:
                self._ctx.enable(moderngl.CULL_FACE)
            else:
                self._ctx.disable(moderngl.CULL_FACE)
            self._ctx.enable(moderngl.DEPTH_TEST)

    def render_meshes(self, meshes: list[tuple], vp_mat: Mat4):
        if not self._solid_prog or not meshes:
            return
        prog = self._solid_prog
        vp_f32 = vp_mat.to_f32()
        if "u_mvp" in prog:
            prog["u_mvp"].write(vp_f32.tobytes())
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        for verts, indices, colors in meshes:
            if not verts or not indices or len(indices) < 3:
                continue
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
            self._ensure_solid_buffers(n, n_idx)
            if n > self._solid_vbo_capacity:
                self._solid_vbo.orphan(n * 28)
                self._solid_vbo_capacity = n
            if n_idx > self._solid_ibo_capacity:
                self._solid_ibo.orphan(n_idx * 4)
                self._solid_ibo_capacity = n_idx
            self._solid_vbo.write(v_data.tobytes())
            self._solid_ibo.write(idx_arr.tobytes())
            self._solid_vao_persistent.render(moderngl.TRIANGLES, vertices=n_idx)
        self._ctx.disable(moderngl.BLEND)
        try:
            self._ctx.enable(moderngl.CULL_FACE)
        except Exception:
            pass

    def render_wireframe_box(self, center: Vec3, size: Vec3, color: list[float], vp_mat: Mat4):
        h = Vec3(size.x * 0.5, size.y * 0.5, size.z * 0.5)
        corners = [
            Vec3(center.x - h.x, center.y - h.y, center.z - h.z),
            Vec3(center.x + h.x, center.y - h.y, center.z - h.z),
            Vec3(center.x + h.x, center.y + h.y, center.z - h.z),
            Vec3(center.x - h.x, center.y + h.y, center.z - h.z),
            Vec3(center.x - h.x, center.y - h.y, center.z + h.z),
            Vec3(center.x + h.x, center.y - h.y, center.z + h.z),
            Vec3(center.x + h.x, center.y + h.y, center.z + h.z),
            Vec3(center.x - h.x, center.y + h.y, center.z + h.z),
        ]
        edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        lines = [(corners[a], corners[b], color) for a, b in edges]
        self.render_lines(lines, vp_mat)

    def release(self):
        if self._line_vao:
            self._line_vao.release()
        if self._line_vbo_data:
            self._line_vbo_data.release()
        for attr in ('_fatline_vbo_start', '_fatline_vbo_end', '_fatline_vbo_t',
                     '_fatline_vbo_side', '_fatline_vao_persistent',
                     '_solid_vbo', '_solid_ibo', '_solid_vao_persistent'):
            buf = getattr(self, attr, None)
            if buf:
                try:
                    buf.release()
                except Exception:
                    pass
