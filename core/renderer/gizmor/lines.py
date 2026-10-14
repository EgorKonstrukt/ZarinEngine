# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.maths.math3d import Vec3, Mat4
from core.renderer.origin import origin_for, relativize_positions, shifted_vp
from core.renderer.shaderp import program_with_fallback

_STRIP_T = np.array([0.0, 1.0, 1.0, 0.0, 1.0, 0.0], dtype=np.float32)
_STRIP_S = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0], dtype=np.float32)
_RL_DIFF_THRESHOLD = 50000

RAWLINES_VERT = """
#version 330 core
in vec4 i_start;
in vec4 i_end;
in vec4 i_color;
in vec2 a_strip;
uniform mat4 u_mvp;
uniform float u_thickness_ndc_x;
uniform float u_thickness_ndc_y;
uniform bool u_dash_enabled;
uniform float u_dash_length;
uniform float u_gap_length;
uniform float u_dash_time;
out vec4 v_color;
out float v_t;
out float v_line_len;
void main() {
    float a_t = a_strip.x;
    float a_side = a_strip.y;
    vec4 clip_start = u_mvp * vec4(i_start.xyz, 1.0);
    vec4 clip_end   = u_mvp * vec4(i_end.xyz, 1.0);
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
    v_t = a_t;
    v_line_len = length(i_end.xyz - i_start.xyz);
}
"""

RAWLINES_FRAG = """
#version 330 core
in vec4 v_color;
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
    fragColor = v_color;
}
"""

class GizmoLinesMixin:
    def render_lines(self, lines, vp_mat: Mat4, fw: int = 1920, fh: int = 1080, thickness_multiplier: float = 1.0, cam_pos=None):
        if not self._fatline_prog or not lines:
            return
        desired_pixels = max(1.0, float(self._line_width) * 1.5 * thickness_multiplier)
        _origin = origin_for(cam_pos) if cam_pos is not None else None
        if isinstance(lines, tuple) and len(lines) == 3 and all(isinstance(a, np.ndarray) for a in lines):
            starts_np, ends_np, colors_np = lines
            self._render_lines_np(starts_np, ends_np, colors_np, vp_mat, fw, fh, desired_pixels, None, cam_pos)
            return
        color_groups: dict = {}
        for start, end, color in lines:
            if isinstance(start, Vec3):
                key = (float(color[0]), float(color[1]), float(color[2]))
                color_groups.setdefault(key, []).append((start, end))
            else:
                key = (float(color[0]), float(color[1]), float(color[2]))
                color_groups.setdefault(key, []).append((start, end))
        try:
            old_cull = bool(self._ctx.cull_face)
        except:
            old_cull = True
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.DEPTH_TEST)
        prog = self._fatline_prog
        names = self._names(prog)
        vp_f32 = shifted_vp(vp_mat, _origin).to_f32()
        if "u_mvp" in names:
            prog["u_mvp"].write(vp_f32.tobytes())
        ndc_x = desired_pixels / max(1.0, float(fw))
        ndc_y = desired_pixels / max(1.0, float(fh))
        if "u_thickness_ndc_x" in names:
            prog["u_thickness_ndc_x"] = float(ndc_x)
        if "u_thickness_ndc_y" in names:
            prog["u_thickness_ndc_y"] = float(ndc_y)
        strip_t = _STRIP_T
        strip_s = _STRIP_S
        try:
            _ox = float(_origin[0]) if _origin is not None else 0.0
            _oy = float(_origin[1]) if _origin is not None else 0.0
            _oz = float(_origin[2]) if _origin is not None else 0.0
        except Exception:
            _ox = 0.0; _oy = 0.0; _oz = 0.0
        try:
            for color_key, segs in color_groups.items():
                alpha_val = float(color_key[3]) if len(color_key) > 3 else 1.0
                if alpha_val <= 0.001:
                    continue
                n_segs = len(segs)
                n_verts = n_segs * 6
                pts = np.empty((n_segs, 6), dtype=np.float32)
                for i, (s, e) in enumerate(segs):
                    pts[i, 0] = s.x - _ox; pts[i, 1] = s.y - _oy; pts[i, 2] = s.z - _oz
                    pts[i, 3] = e.x - _ox; pts[i, 4] = e.y - _oy; pts[i, 5] = e.z - _oz
                starts_arr = np.repeat(pts[:, :3], 6, axis=0)
                ends_arr = np.repeat(pts[:, 3:], 6, axis=0)
                ts_arr = np.tile(_STRIP_T, n_segs)
                side_arr = np.tile(_STRIP_S, n_segs)
                self._ensure_fatline_capacity(n_verts)
                self._fatline_vbo_start.write(memoryview(starts_arr))
                self._fatline_vbo_end.write(memoryview(ends_arr))
                self._fatline_vbo_t.write(memoryview(ts_arr))
                self._fatline_vbo_side.write(memoryview(side_arr))
                color_arr = np.zeros((n_verts, 4), dtype=np.float32)
                color_arr[:, 0] = color_key[0]
                color_arr[:, 1] = color_key[1]
                color_arr[:, 2] = color_key[2]
                color_arr[:, 3] = alpha_val
                self._fatline_vbo_color.write(memoryview(color_arr))
                self._stat_upload_bytes += n_verts * 48
                self._stat_upload_full += 1
                self._fatline_vao.render(moderngl.TRIANGLES, vertices=n_verts)
        finally:
            if old_cull:
                self._ctx.enable(moderngl.CULL_FACE)
            else:
                self._ctx.disable(moderngl.CULL_FACE)
            self._ctx.enable(moderngl.DEPTH_TEST)

    def _render_lines_np(self, starts: np.ndarray, ends: np.ndarray, colors: np.ndarray, vp_mat: Mat4, fw: int, fh: int, desired_pixels: float, dash_opts: Optional[dict] = None, cam_pos=None):
        n_segs = starts.shape[0]
        if n_segs == 0:
            return
        self._stat_lines += n_segs
        self._stat_draws += 1
        n_verts = n_segs * 6
        try:
            old_cull = bool(self._ctx.cull_face)
        except:
            old_cull = True
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.DEPTH_TEST)
        prog = self._fatline_prog
        names = self._names(prog)
        _origin = origin_for(cam_pos) if cam_pos is not None else None
        vp_f32 = shifted_vp(vp_mat, _origin).to_f32()
        if "u_mvp" in names:
            prog["u_mvp"].write(vp_f32.tobytes())
        ndc_x = desired_pixels / max(1.0, float(fw))
        ndc_y = desired_pixels / max(1.0, float(fh))
        if "u_thickness_ndc_x" in names:
            prog["u_thickness_ndc_x"] = float(ndc_x)
        if "u_thickness_ndc_y" in names:
            prog["u_thickness_ndc_y"] = float(ndc_y)
        if dash_opts and "u_dash_enabled" in names:
            prog["u_dash_enabled"] = True
            prog["u_dash_length"] = float(dash_opts.get('dash_length', 0.3))
            prog["u_gap_length"] = float(dash_opts.get('gap_length', 0.15))
            prog["u_dash_time"] = float(dash_opts.get('time', 0.0))
        elif "u_dash_enabled" in names:
            prog["u_dash_enabled"] = False
        self._ensure_fatline_capacity(n_verts)
        _rs = relativize_positions(starts, _origin)
        _re = relativize_positions(ends, _origin)
        sv = self._fs_starts[:n_verts].reshape(-1, 6, 3)
        sv[:] = _rs[:, None, :]
        ev = self._fs_ends[:n_verts].reshape(-1, 6, 3)
        ev[:] = _re[:, None, :]
        tv = self._fs_t[:n_verts].reshape(-1, 6)
        tv[:] = _STRIP_T[None, :]
        sidev = self._fs_side[:n_verts].reshape(-1, 6)
        sidev[:] = _STRIP_S[None, :]
        cv = self._fs_colors[:n_verts].reshape(-1, 6, 4)
        if colors.shape[1] == 3:
            cv[:, :, :3] = colors[:, None, :]
            cv[:, :, 3] = 1.0
        elif colors.shape[1] >= 4:
            cv[:] = colors[:, None, :4]
        else:
            cv[:] = 0.5
        self._fatline_vbo_start.write(memoryview(self._fs_starts[:n_verts]))
        self._fatline_vbo_end.write(memoryview(self._fs_ends[:n_verts]))
        self._fatline_vbo_t.write(memoryview(self._fs_t[:n_verts]))
        self._fatline_vbo_side.write(memoryview(self._fs_side[:n_verts]))
        self._fatline_vbo_color.write(memoryview(self._fs_colors[:n_verts]))
        self._stat_upload_bytes += n_verts * 48
        self._stat_upload_full += 1
        self._fatline_vao.render(moderngl.TRIANGLES, vertices=n_verts)
        if old_cull:
            self._ctx.enable(moderngl.CULL_FACE)
        else:
            self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.DEPTH_TEST)

    def _ensure_rawline_prog(self):
        if self._raw_line_prog is not None:
            return
        try:
            self._raw_line_prog = program_with_fallback(
                self._ctx,
                vertex_shader=RAWLINES_VERT,
                fragment_shader=RAWLINES_FRAG,
                label="gizmo_rawline"
            )
        except Exception:
            self._raw_line_prog = None

    def _build_rawline_buffers(self, capacity: int = 262144):
        cap = max(capacity, 262144)
        for buf_name in ('_raw_line_vao', '_raw_line_static_vbo',
                         '_raw_line_start_vbo', '_raw_line_end_vbo', '_raw_line_color_vbo'):
            b = getattr(self, buf_name, None)
            if b is not None:
                try:
                    b.release()
                except Exception:
                    pass
        static = np.empty((6, 2), dtype=np.float32)
        static[:, 0] = _STRIP_T
        static[:, 1] = _STRIP_S
        self._raw_line_static_vbo = self._ctx.buffer(static.tobytes())
        self._raw_line_start_vbo = self._ctx.buffer(reserve=cap * 12, dynamic=True)
        self._raw_line_end_vbo = self._ctx.buffer(reserve=cap * 12, dynamic=True)
        self._raw_line_color_vbo = self._ctx.buffer(reserve=cap * 16, dynamic=True)
        self._raw_line_vao = self._ctx.vertex_array(
            self._raw_line_prog,
            [
                (self._raw_line_static_vbo, "2f", "a_strip"),
                (self._raw_line_start_vbo, "3f /i", "i_start"),
                (self._raw_line_end_vbo, "3f /i", "i_end"),
                (self._raw_line_color_vbo, "4f /i", "i_color"),
            ]
        )
        self._fs_starts = np.empty((cap, 3), dtype=np.float32)
        self._fs_ends = np.empty((cap, 3), dtype=np.float32)
        self._fs_colors4 = np.empty((cap, 4), dtype=np.float32)
        self._rl_shadow_starts = np.zeros(cap, dtype=np.uint32)
        self._rl_shadow_ends = np.zeros(cap, dtype=np.uint32)
        self._rl_shadow_colors = np.zeros(cap, dtype=np.uint32)
        self._rl_shadow_n = 0
        self._rl_shadow_scalar[:] = 0
        self._raw_line_capacity = cap

    def _ensure_rawline_capacity(self, n: int):
        if n <= self._raw_line_capacity:
            return False
        new_cap = self._raw_line_capacity or 262144
        while new_cap < n:
            new_cap <<= 1
        self._build_rawline_buffers(new_cap)
        return True

    def render_raw_lines(self, starts: np.ndarray, ends: np.ndarray, colors: np.ndarray, vp_mat: Mat4, fw: int, fh: int, desired_pixels: float, dash_opts: Optional[dict] = None, dirty: bool = True, cam_pos=None):
        n = starts.shape[0]
        if n == 0:
            return
        self._ensure_rawline_prog()
        if self._raw_line_prog is None:
            self._render_lines_np(starts, ends, colors, vp_mat, fw, fh, desired_pixels, dash_opts, cam_pos)
            return
        grew = self._ensure_rawline_capacity(n)
        if grew:
            dirty = True
        self._stat_lines += n
        self._stat_draws += 1
        _origin = origin_for(cam_pos) if cam_pos is not None else None
        _rs = relativize_positions(starts, _origin)
        _re = relativize_positions(ends, _origin)
        if _origin is not None:
            dirty = True
        if dirty:
            if (_rs.flags.c_contiguous and _re.flags.c_contiguous and colors.ndim == 2
                    and colors.shape[1] >= 4 and colors.flags.c_contiguous):
                s_arr = np.ascontiguousarray(_rs, dtype=np.float32)
                e_arr = np.ascontiguousarray(_re, dtype=np.float32)
                c_arr = colors[:, :4]
            else:
                fs = self._fs_starts[:n]
                fs[:] = _rs
                self._fs_ends[:n] = _re
                fc = self._fs_colors4[:n]
                if colors.shape[1] >= 4:
                    fc[:] = colors[:, :4]
                elif colors.shape[1] == 3:
                    fc[:, :3] = colors
                    fc[:, 3] = 1.0
                else:
                    fc[:] = 0.5
                s_arr = self._fs_starts[:n]
                e_arr = self._fs_ends[:n]
                c_arr = self._fs_colors4[:n]
            if n >= _RL_DIFF_THRESHOLD:
                self._rl_upload_diff(s_arr, e_arr, c_arr)
            else:
                self._raw_line_start_vbo.write(memoryview(s_arr))
                self._raw_line_end_vbo.write(memoryview(e_arr))
                self._raw_line_color_vbo.write(memoryview(c_arr))
                self._stat_upload_bytes += n * (12 + 12 + 16)
                self._stat_upload_full += 1
                self._rl_refresh_shadow(s_arr, e_arr, c_arr)
        self._draw_rawlines(n, vp_mat, fw, fh, desired_pixels, dash_opts, cam_pos)

    def _rl_refresh_shadow(self, s_arr: np.ndarray, e_arr: np.ndarray, c_arr: np.ndarray):
        n = s_arr.shape[0]
        vs = s_arr.view(np.uint32)
        ve = e_arr.view(np.uint32)
        vc = c_arr.view(np.uint32)
        self._rl_shadow_starts[:n] = np.bitwise_xor(np.bitwise_xor(vs[:, 0], vs[:, 1]), vs[:, 2])
        self._rl_shadow_ends[:n] = np.bitwise_xor(np.bitwise_xor(ve[:, 0], ve[:, 1]), ve[:, 2])
        self._rl_shadow_colors[:n] = np.bitwise_xor(np.bitwise_xor(np.bitwise_xor(vc[:, 0], vc[:, 1]), vc[:, 2]), vc[:, 3])
        self._rl_shadow_n = n
        self._rl_shadow_scalar[0] = np.bitwise_xor.reduce(vs.ravel())
        self._rl_shadow_scalar[1] = np.bitwise_xor.reduce(ve.ravel())
        self._rl_shadow_scalar[2] = np.bitwise_xor.reduce(vc.ravel())

    def _rl_upload_ranges(self, vbo, data: np.ndarray, mask: np.ndarray, stride: int):
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return
        bounds = np.flatnonzero(np.diff(idx) > 1)
        rs = np.concatenate(([idx[0]], idx[bounds + 1]))
        re = np.concatenate((idx[bounds] + 1, [idx[-1] + 1]))
        if idx.size > 0:
            self._stat_upload_partial += 1
        for r0, r1 in zip(rs.tolist(), re.tolist()):
            vbo.write(memoryview(data[r0:r1]), offset=r0 * stride)
            self._stat_upload_bytes += (r1 - r0) * stride

    def _rl_upload_diff(self, s_arr: np.ndarray, e_arr: np.ndarray, c_arr: np.ndarray) -> bool:
        n = s_arr.shape[0]
        vs = s_arr.view(np.uint32)
        ve = e_arr.view(np.uint32)
        vc = c_arr.view(np.uint32)
        scalars = np.empty(3, dtype=np.uint32)
        scalars[0] = np.bitwise_xor.reduce(vs.ravel())
        scalars[1] = np.bitwise_xor.reduce(ve.ravel())
        scalars[2] = np.bitwise_xor.reduce(vc.ravel())
        if n == self._rl_shadow_n and (scalars == self._rl_shadow_scalar).all():
            return False
        grew = n != self._rl_shadow_n
        for arr, shadow_name, stride, s_idx, vbo in (
                (vs, '_rl_shadow_starts', 12, 0, self._raw_line_start_vbo),
                (ve, '_rl_shadow_ends', 12, 1, self._raw_line_end_vbo),
                (vc, '_rl_shadow_colors', 16, 2, self._raw_line_color_vbo)):
            shadow = getattr(self, shadow_name)
            if not (grew or scalars[s_idx] != self._rl_shadow_scalar[s_idx]):
                continue
            m = arr.shape[0]
            cs = np.bitwise_xor(np.bitwise_xor(arr[:, 0], arr[:, 1]), arr[:, 2])
            if arr.shape[1] > 3:
                cs = np.bitwise_xor(cs, arr[:, 3])
            mask = cs != shadow[:m]
            shadow[:m] = cs
            self._rl_upload_ranges(vbo, arr.view(np.float32), mask, stride)
        self._rl_shadow_n = n
        self._rl_shadow_scalar[:] = scalars
        return True

    def _draw_rawlines(self, n: int, vp_mat: Mat4, fw: int, fh: int, desired_pixels: float, dash_opts: Optional[dict], cam_pos=None):
        try:
            old_cull = bool(self._ctx.cull_face)
        except Exception:
            old_cull = True
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.DEPTH_TEST)
        prog = self._raw_line_prog
        names = self._names(prog)
        vp_f32 = shifted_vp(vp_mat, origin_for(cam_pos) if cam_pos is not None else None).to_f32()
        if "u_mvp" in names:
            prog["u_mvp"].write(vp_f32.tobytes())
        ndc_x = desired_pixels / max(1.0, float(fw))
        ndc_y = desired_pixels / max(1.0, float(fh))
        if "u_thickness_ndc_x" in names:
            prog["u_thickness_ndc_x"] = float(ndc_x)
        if "u_thickness_ndc_y" in names:
            prog["u_thickness_ndc_y"] = float(ndc_y)
        if dash_opts and "u_dash_enabled" in names:
            prog["u_dash_enabled"] = True
            prog["u_dash_length"] = float(dash_opts.get('dash_length', 0.3))
            prog["u_gap_length"] = float(dash_opts.get('gap_length', 0.15))
            prog["u_dash_time"] = float(dash_opts.get('time', 0.0))
        elif "u_dash_enabled" in names:
            prog["u_dash_enabled"] = False
        self._raw_line_vao.render(moderngl.TRIANGLES, vertices=6, instances=n)
        if old_cull:
            self._ctx.enable(moderngl.CULL_FACE)
        else:
            self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.DEPTH_TEST)

    def render_wireframe_box(self, center: Vec3, size: Vec3, color: list[float], vp_mat: Mat4, cam_pos=None):
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
        self.render_lines(lines, vp_mat, cam_pos=cam_pos)
