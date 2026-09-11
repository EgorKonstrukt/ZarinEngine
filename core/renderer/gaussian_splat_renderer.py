# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.assets.ply_loader import load_ply_gaussian_splat
from core.renderer.mesh_data import read_shader


_SPLAT_DTYPE = np.dtype([
    ("pos_x", np.float32), ("pos_y", np.float32), ("pos_z", np.float32),
    ("sh_dc_0", np.float32), ("sh_dc_1", np.float32), ("sh_dc_2", np.float32),
    ("sh_rest", np.float32, (45,)),
    ("opacity", np.float32),
    ("scale_0", np.float32), ("scale_1", np.float32), ("scale_2", np.float32),
    ("quat_x", np.float32), ("quat_y", np.float32), ("quat_z", np.float32), ("quat_w", np.float32),
])

_SPLAT_STRUCT_SIZE = _SPLAT_DTYPE.itemsize

_EMPTY_U32 = np.zeros(0, dtype=np.uint32)

try:
    from core._splat_sort import splat_cull_depth as _cython_cull_depth
except Exception:
    _cython_cull_depth = None


class GaussianSplatRenderer:
    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._prog: Optional[moderngl.Program] = None
        self._ssbo: Optional[moderngl.Buffer] = None
        self._idx_ssbo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._uploaded_path: Optional[str] = None
        self._uploaded_n: int = 0
        self._gpu_data: dict[str, np.ndarray] = {}
        self._pos: dict[str, np.ndarray] = {}
        self._opa: dict[str, np.ndarray] = {}
        self._srad: dict[str, np.ndarray] = {}
        self._center: dict[str, np.ndarray] = {}
        self._radius: dict[str, float] = {}
        self._sort_cache: dict[str, tuple[bytes, np.ndarray]] = {}
        self._order_tick: dict[str, int] = {}
        self._idx_key: Optional[tuple[str, bytes]] = None
        self._cs_key = None
        self._cs_bitonic = None
        self._cs_key_u: tuple = (None, None, None, None)
        self._cs_bit_u: tuple = (None, None, None)
        self._key_ssbo = None
        self._gpu_state: Optional[tuple[str, bytes, int]] = None
        self._init_shaders()
        self._init_compute()

    def _init_shaders(self):
        try:
            vert_src = read_shader("gaussian_splat.vert")
            frag_src = read_shader("gaussian_splat.frag")
            self._prog = self._ctx.program(
                vertex_shader=vert_src,
                fragment_shader=frag_src,
            )
            self._vao = self._ctx.vertex_array(self._prog, [])
        except Exception:
            self._prog = None
            self._vao = None

    def _resolve_compute_uniform(self, prog, name):
        try:
            return prog[name]
        except Exception:
            return None

    def _init_compute(self):
        try:
            key_src = read_shader("gaussian_sort_key.comp")
            bit_src = read_shader("gaussian_sort_bitonic.comp")
            self._cs_key = self._ctx.compute_shader(key_src)
            self._cs_bitonic = self._ctx.compute_shader(bit_src)
            self._cs_key_u = (
                self._resolve_compute_uniform(self._cs_key, "u_mv"),
                self._resolve_compute_uniform(self._cs_key, "u_n"),
                self._resolve_compute_uniform(self._cs_key, "u_np"),
                self._resolve_compute_uniform(self._cs_key, "u_opacity_thr"),
            )
            self._cs_bit_u = (
                self._resolve_compute_uniform(self._cs_bitonic, "u_n"),
                self._resolve_compute_uniform(self._cs_bitonic, "u_span"),
                self._resolve_compute_uniform(self._cs_bitonic, "u_dir"),
            )
        except Exception:
            self._cs_key = None
            self._cs_bitonic = None
            self._cs_key_u = (None, None, None, None)
            self._cs_bit_u = (None, None, None)

    def _compute_ready(self) -> bool:
        return self._cs_key is not None and self._cs_bitonic is not None

    def _ensure_buffers(self, num_splats: int):
        needed = max(1, num_splats) * _SPLAT_STRUCT_SIZE
        if self._ssbo is None or self._ssbo.size < needed:
            if self._ssbo:
                self._ssbo.release()
            self._ssbo = self._ctx.buffer(reserve=needed)
            self._uploaded_path = None

        idx_needed = max(1, num_splats) * 4
        if self._idx_ssbo is None or self._idx_ssbo.size < idx_needed:
            if self._idx_ssbo:
                self._idx_ssbo.release()
            self._idx_ssbo = self._ctx.buffer(reserve=idx_needed)
            self._idx_key = None
            self._gpu_state = None

    def _ensure_sort_buffers(self, padded: int):
        need = max(1, padded) * 4
        if self._key_ssbo is None or self._key_ssbo.size < need:
            if self._key_ssbo:
                self._key_ssbo.release()
            self._key_ssbo = self._ctx.buffer(reserve=need)
            self._gpu_state = None
        if self._idx_ssbo is None or self._idx_ssbo.size < need:
            if self._idx_ssbo:
                self._idx_ssbo.release()
            self._idx_ssbo = self._ctx.buffer(reserve=need)
            self._idx_key = None
            self._gpu_state = None

    def load_data(self, path: str) -> bool:
        if path in self._gpu_data:
            return True
        data = load_ply_gaussian_splat(path)
        if data is None or data.num_splats == 0:
            return False
        gpu = self._pack_for_gpu(data)
        self._gpu_data[path] = gpu
        self._pos[path] = np.ascontiguousarray(data.positions, dtype=np.float32)
        self._opa[path] = np.ascontiguousarray(data.opacity.reshape(-1), dtype=np.float32)
        self._srad[path] = np.ascontiguousarray(data.scales.max(axis=1) * 3.0, dtype=np.float32)
        mn = data.positions.min(axis=0)
        mx = data.positions.max(axis=0)
        self._center[path] = np.ascontiguousarray((mn + mx) * 0.5, dtype=np.float32)
        self._radius[path] = float(np.linalg.norm((mx - mn).astype(np.float64) * 0.5))
        self._uploaded_path = None
        self._sort_cache.pop(path, None)
        self._order_tick.pop(path, None)
        return True

    def _pack_for_gpu(self, data) -> np.ndarray:
        n = data.num_splats
        num_rest = max(0, min(data.sh_coeffs.shape[1] - 3, 45))

        gpu = np.zeros(n, dtype=_SPLAT_DTYPE)
        gpu["pos_x"] = data.positions[:, 0]
        gpu["pos_y"] = data.positions[:, 1]
        gpu["pos_z"] = data.positions[:, 2]
        gpu["sh_dc_0"] = data.sh_coeffs[:, 0]
        gpu["sh_dc_1"] = data.sh_coeffs[:, 1]
        gpu["sh_dc_2"] = data.sh_coeffs[:, 2]
        if num_rest > 0:
            gpu["sh_rest"][:, :num_rest] = data.sh_coeffs[:, 3:3 + num_rest]
        gpu["opacity"] = data.opacity
        gpu["scale_0"] = data.scales[:, 0]
        gpu["scale_1"] = data.scales[:, 1]
        gpu["scale_2"] = data.scales[:, 2]
        gpu["quat_x"] = data.quaternions[:, 0]
        gpu["quat_y"] = data.quaternions[:, 1]
        gpu["quat_z"] = data.quaternions[:, 2]
        gpu["quat_w"] = data.quaternions[:, 3]
        return gpu

    def _frame_key(self, model_f32: np.ndarray, view_f32: np.ndarray,
                   proj_f32: np.ndarray, opacity_threshold: float) -> bytes:
        proj = proj_f32.reshape(4, 4)
        zoom = np.array([proj[0, 0], proj[1, 1]], dtype=np.float32).tobytes()
        return model_f32.tobytes() + view_f32.tobytes() + np.float32(opacity_threshold).tobytes() + zoom

    def _sort_basis(self, model_f32: np.ndarray, view_f32: np.ndarray, proj_f32: np.ndarray):
        mv = np.ascontiguousarray(model_f32.reshape(4, 4) @ view_f32.reshape(4, 4), dtype=np.float32)
        a = mv[:3, :3]
        t = mv[3, :3]
        ms = float(np.linalg.norm(a.astype(np.float64), axis=0).max())
        if not np.isfinite(ms) or ms <= 0.0:
            return None
        proj = proj_f32.reshape(4, 4)
        p00 = float(proj[0, 0])
        p11 = float(proj[1, 1])
        perspective = abs(float(proj[2, 3]) + 1.0) < 1e-3
        return mv, a, t, ms, p00, p11, perspective

    def _cloud_culled(self, path: str, a: np.ndarray, t: np.ndarray, ms: float,
                      p00: float, p11: float, perspective: bool) -> bool:
        if not perspective:
            return False
        center = self._center.get(path)
        radius = float(self._radius.get(path, 0.0))
        if center is None or radius < 0.0:
            return False
        vc = center @ a + t
        w = float(-vc[2])
        rw = radius * ms
        if w + rw < 0.05:
            return True
        if w > 0.0:
            nx = float(vc[0]) * p00 / w
            ny = float(vc[1]) * p11 / w
            rx = rw * abs(p00) / w
            ry = rw * abs(p11) / w
            if nx < -1.0 - rx or nx > 1.0 + rx or ny < -1.0 - ry or ny > 1.0 + ry:
                return True
        return False

    def _visible_order(self, path: str, model_f32: np.ndarray, view_f32: np.ndarray,
                       proj_f32: np.ndarray, opacity_threshold: float) -> tuple[bytes, np.ndarray]:
        key = self._frame_key(model_f32, view_f32, proj_f32, opacity_threshold)
        cached = self._sort_cache.get(path)
        if cached is not None and cached[0] == key:
            return key, cached[1]
        tick = self._order_tick.get(path, 0) + 1
        self._order_tick[path] = tick
        if cached is not None and (tick & 1):
            return cached
        order = self._compute_order(path, model_f32, view_f32, proj_f32, opacity_threshold)
        self._sort_cache[path] = (key, order)
        return key, order

    def _compute_order(self, path: str, model_f32: np.ndarray, view_f32: np.ndarray,
                       proj_f32: np.ndarray, opacity_threshold: float) -> np.ndarray:
        pos = self._pos.get(path)
        opa = self._opa.get(path)
        srad = self._srad.get(path)
        if pos is None or opa is None or srad is None or len(pos) == 0:
            return _EMPTY_U32
        basis = self._sort_basis(model_f32, view_f32, proj_f32)
        if basis is None:
            return _EMPTY_U32
        mv, a, t, ms, p00, p11, perspective = basis
        if self._cloud_culled(path, a, t, ms, p00, p11, perspective):
            return _EMPTY_U32
        if _cython_cull_depth is not None:
            n = len(pos)
            keep = np.zeros(n, dtype=np.uint8)
            wbuf = np.empty(n, dtype=np.float32)
            _cython_cull_depth(pos, opa, srad, mv, np.float32(p00), np.float32(p11),
                               np.float32(opacity_threshold), np.float32(ms),
                               bool(perspective), keep, wbuf)
            idx = np.flatnonzero(keep)
            if idx.size == 0:
                return _EMPTY_U32
            if idx.size < n:
                w = wbuf[idx]
            else:
                idx = None
                w = wbuf
        else:
            v = pos @ a + t
            w = -v[:, 2]
            thr = np.float32(opacity_threshold)
            fms = np.float32(ms)
            if perspective:
                r = srad * fms
                idx = np.flatnonzero((opa > thr) & ((w + r) > np.float32(0.05)))
                if idx.size == 0:
                    return _EMPTY_U32
                if idx.size < len(pos):
                    v = v[idx]
                    w = w[idx]
                    r = r[idx]
                else:
                    idx = None
                fp00 = np.float32(p00)
                fp11 = np.float32(p11)
                inv = np.float32(1.0) / np.maximum(w, np.float32(1e-6))
                nx = v[:, 0] * fp00 * inv
                ny = v[:, 1] * fp11 * inv
                mx = r * np.float32(abs(p00)) * inv + np.float32(0.02)
                my = r * np.float32(abs(p11)) * inv + np.float32(0.02)
                loc = np.flatnonzero((nx >= -1.0 - mx) & (nx <= 1.0 + mx) & (ny >= -1.0 - my) & (ny <= 1.0 + my))
                if loc.size == 0:
                    return _EMPTY_U32
                w = w[loc]
                if idx is not None:
                    idx = idx[loc]
                else:
                    idx = loc
            else:
                idx = np.flatnonzero(opa > thr)
                if idx.size == 0:
                    return _EMPTY_U32
                if idx.size < len(pos):
                    w = w[idx]
                else:
                    idx = None
        rev = np.argsort(w)[::-1]
        if idx is not None:
            return np.ascontiguousarray(idx[rev], dtype=np.uint32)
        return np.ascontiguousarray(rev, dtype=np.uint32)

    def _gpu_sort(self, padded: int, n: int, mv_bytes: bytes, opacity_threshold: float):
        groups = (padded + 255) // 256
        self._ssbo.bind_to_storage_buffer(0)
        self._key_ssbo.bind_to_storage_buffer(2)
        self._idx_ssbo.bind_to_storage_buffer(4)
        mv_u, n_u, np_u, thr_u = self._cs_key_u
        if mv_u is not None:
            mv_u.write(mv_bytes)
        if n_u is not None:
            n_u.value = int(n)
        if np_u is not None:
            np_u.value = int(padded)
        if thr_u is not None:
            thr_u.value = float(opacity_threshold)
        self._cs_key.run(groups)
        barrier = self._ctx.memory_barrier
        sb = moderngl.SHADER_STORAGE_BARRIER_BIT
        barrier(sb)
        bn_u, span_u, dir_u = self._cs_bit_u
        size = 2
        while size <= padded:
            span = size // 2
            while span >= 1:
                if bn_u is not None:
                    bn_u.value = int(padded)
                if span_u is not None:
                    span_u.value = int(span)
                if dir_u is not None:
                    dir_u.value = int(size)
                self._cs_bitonic.run(groups)
                barrier(sb)
                span //= 2
            size *= 2

    def render(self, path: str, model_matrix, view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               opacity_threshold=0.005, sh_degree=3, max_screen_size=32.0):
        if not self._prog or not self._vao:
            return
        if path not in self._gpu_data:
            if not self.load_data(path):
                return

        gpu = self._gpu_data.get(path)
        if gpu is None or len(gpu) == 0:
            return

        n = len(gpu)
        model_f32 = np.ascontiguousarray(model_matrix.to_f32(), dtype=np.float32)
        view_f32 = np.ascontiguousarray(view_mat.to_f32(), dtype=np.float32)
        proj_f32 = np.ascontiguousarray(proj_mat.to_f32(), dtype=np.float32)

        use_gpu = self._compute_ready()
        order = None
        padded = 0
        if use_gpu:
            basis = self._sort_basis(model_f32, view_f32, proj_f32)
            if basis is None:
                return
            mv, a, t, ms, p00, p11, perspective = basis
            if self._cloud_culled(path, a, t, ms, p00, p11, perspective):
                return
            key = self._frame_key(model_f32, view_f32, proj_f32, opacity_threshold)
            padded = 1 << (n - 1).bit_length()
            state = (path, key, padded)
            self._ensure_buffers(n)
            if self._uploaded_path != path or self._uploaded_n != n:
                self._ssbo.write(gpu.tobytes())
                self._uploaded_path = path
                self._uploaded_n = n
            self._ensure_sort_buffers(padded)
            if self._gpu_state != state:
                self._gpu_sort(padded, n, mv.tobytes(), opacity_threshold)
                self._gpu_state = state
            instances = padded
        else:
            key, order = self._visible_order(path, model_f32, view_f32, proj_f32, opacity_threshold)
            m = len(order)
            if m == 0:
                return
            self._ensure_buffers(n)
            if self._uploaded_path != path or self._uploaded_n != n:
                self._ssbo.write(gpu.tobytes())
                self._uploaded_path = path
                self._uploaded_n = n
            self._ssbo.bind_to_storage_buffer(0)
            if self._idx_key is None or self._idx_key[0] != path or self._idx_key[1] != key:
                self._idx_ssbo.write(order.tobytes())
                self._idx_key = (path, key)
            self._idx_ssbo.bind_to_storage_buffer(1)
            instances = m

        prog = self._prog
        if use_gpu:
            self._idx_ssbo.bind_to_storage_buffer(1)
        if "u_model" in prog:
            prog["u_model"].write(model_f32.tobytes())
        if "u_view" in prog:
            prog["u_view"].write(view_f32.tobytes())
        if "u_proj" in prog:
            prog["u_proj"].write(proj_f32.tobytes())
        if "u_viewport" in prog:
            prog["u_viewport"].write(np.array([viewport_w, viewport_h], dtype=np.float32).tobytes())
        if "u_camera_pos" in prog:
            prog["u_camera_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        if "u_sh_degree" in prog:
            prog["u_sh_degree"].value = int(sh_degree)
        if "u_opacity_threshold" in prog:
            prog["u_opacity_threshold"].value = float(opacity_threshold)
        if "u_max_screen_size" in prog:
            prog["u_max_screen_size"].value = float(max_screen_size)

        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.depth_mask = False

        try:
            self._vao.render(moderngl.TRIANGLE_STRIP, vertices=4, instances=instances)
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"Gaussian Splat render error: {e}")

        self._ctx.enable(moderngl.CULL_FACE)
        self._ctx.depth_mask = True
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def release(self):
        if self._vao:
            self._vao.release()
        if self._ssbo:
            self._ssbo.release()
        if self._idx_ssbo:
            self._idx_ssbo.release()
        if self._key_ssbo:
            self._key_ssbo.release()
        if self._prog:
            self._prog.release()
        if self._cs_key is not None:
            try:
                self._cs_key.release()
            except Exception:
                pass
        if self._cs_bitonic is not None:
            try:
                self._cs_bitonic.release()
            except Exception:
                pass
        self._vao = None
        self._ssbo = None
        self._idx_ssbo = None
        self._key_ssbo = None
        self._prog = None
        self._cs_key = None
        self._cs_bitonic = None
        self._cs_key_u = (None, None, None, None)
        self._cs_bit_u = (None, None, None)
        self._gpu_state = None
        self._gpu_data.clear()
        self._pos.clear()
        self._opa.clear()
        self._srad.clear()
        self._center.clear()
        self._radius.clear()
        self._sort_cache.clear()
        self._order_tick.clear()
        self._idx_key = None
        self._uploaded_path = None
        self._uploaded_n = 0
