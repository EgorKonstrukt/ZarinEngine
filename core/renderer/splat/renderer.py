# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import threading
import time
import numpy as np
import moderngl
from typing import Optional
from core.assets.sog import splat_exists
from core.foundation.logger import Logger
from core.foundation.progress import task_start, task_update, task_complete, notify_error
from .resources import _SPLAT_STRUCT_SIZE
from .resources import _SPLAT_UPLOAD_CHUNK_BYTES
from .resources import _SPLAT_GPU_MIN_N
from .resources import _SPLAT_MIN_PX
from .resources import _SPLAT_FAIL_RETRY_S
from .resources import _GC_IDLE_S
from .resources import _GC_MAX_PATHS
from .resources import _pack_struct
from .resources import _drop_splat_arrays
from .resources import _publish_splat_arrays
from .resources import _load_splat_file
from .resources import _splat_task_id
from .resources import _SplatResourcesMixin
from .sort import _SplatSortMixin
from .sort import _cython_available
from .volume import _SplatVolumeMixin


class GaussianSplatRenderer(_SplatResourcesMixin, _SplatSortMixin, _SplatVolumeMixin):
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
        self._sort_cache: dict[tuple[str, bytes], list] = {}
        self._scratch: dict[str, dict[str, np.ndarray]] = {}
        self._idx_key: Optional[tuple[str, bytes]] = None
        self._last_used: dict[str, float] = {}
        self._load_lock = threading.Lock()
        self._loading: set = set()
        self._completed: list = []
        self._failed: dict = {}
        self._fractions: dict = {}
        self._upload_progress: dict[str, int] = {}
        self._last_order: dict[str, np.ndarray] = {}
        self._sorts_this_frame: int = 0
        self._gpu_sorts_this_frame: int = 0
        self._cs_progs: dict[str, object] = {}
        self._cs_ok: Optional[bool] = None
        self._gs_keys0 = None
        self._gs_keys1 = None
        self._gs_vals0 = None
        self._gs_vals1 = None
        self._gs_hist = None
        self._gs_offs = None
        self._gs_counter = None
        self._gs_indirect = None
        self._gs_scratch_n: int = 0
        self._gs_pos: dict[str, object] = {}
        self._gs_opa: dict[str, object] = {}
        self._gs_srad: dict[str, object] = {}
        self._gs_order: dict[str, object] = {}
        self._gs_cmd: dict[str, object] = {}
        self._gs_up: dict[str, int] = {}
        self._gs_key: dict[tuple, bytes] = {}
        self._init_shaders()
        if _cython_available():
            self._sort_backend = "cython"
        else:
            self._sort_backend = "numpy"
        Logger.info(f"GaussianSplatRenderer sort backend: {self._sort_backend}")

    def load_data(self, path: str) -> bool:
        if path in self._gpu_data:
            return True
        now = time.monotonic()
        with self._load_lock:
            if path in self._loading:
                return False
            failed_at = self._failed.get(path)
            if failed_at is not None:
                if now - failed_at < _SPLAT_FAIL_RETRY_S:
                    return False
                del self._failed[path]
            try:
                exists = splat_exists(path) or os.path.exists(path)
            except Exception:
                exists = False
            if not exists:
                return False
            self._loading.add(path)
            self._fractions[path] = 0.0
        base = path.replace("\\", "/").split("/")[-1] or path
        task_start(_splat_task_id(path), f"Loading {base}...", fraction=0.0)
        threading.Thread(target=self._load_thread, args=(path,), daemon=True).start()
        return False

    def load_progress(self, path: str):
        if path in self._gpu_data:
            return 1.0
        with self._load_lock:
            return self._fractions.get(path)

    def _load_thread(self, path: str):
        task_id = _splat_task_id(path)

        def progress(frac, detail=None):
            f = max(0.0, min(1.0, float(frac)))
            with self._load_lock:
                if path in self._fractions:
                    self._fractions[path] = f
            task_update(task_id, fraction=f, detail=detail)

        try:
            payload = _load_splat_file(path, task_id, progress)
        except Exception as e:
            Logger.error(f"Splat load failed: {path}: {e}")
            payload = None
        with self._load_lock:
            self._loading.discard(path)
            self._fractions.pop(path, None)
            if payload is None:
                self._failed[path] = time.monotonic()
                task_complete(task_id)
                notify_error(f"Failed to load {path.replace(chr(92), '/').split('/')[-1]}")
            else:
                self._completed.append((path, payload))
                task_complete(task_id)

    def process_pending(self):
        self._sorts_this_frame = 0
        self._gpu_sorts_this_frame = 0
        with self._load_lock:
            if not self._completed:
                done = []
            else:
                done = self._completed
                self._completed = []
        now = time.monotonic()
        for path, payload in done:
            self._gpu_data[path] = payload["gpu"]
            self._pos[path] = payload["pos"]
            self._opa[path] = payload["opa"]
            self._srad[path] = payload["srad"]
            self._center[path] = payload["center"]
            self._radius[path] = payload["radius"]
            self._last_used[path] = now
            self._uploaded_path = None
            for k in [k for k in self._sort_cache if k[0] == path]:
                del self._sort_cache[k]
            self._last_order.pop(path, None)
            self._gs_up.pop(path, None)
            self._gs_key = {k: v for k, v in self._gs_key.items() if k[0] != path}
            try:
                if self._idx_key is not None and self._idx_key[0] == path:
                    self._idx_key = None
            except Exception:
                self._idx_key = None
            self._scratch.pop(path, None)
            _publish_splat_arrays(path, payload["pos"], payload["scl"], payload["opa"])
            del payload
        if done:
            self.collect_garbage()

    def _release_locked(self, path: str):
        self._gpu_data.pop(path, None)
        self._pos.pop(path, None)
        self._opa.pop(path, None)
        self._srad.pop(path, None)
        self._center.pop(path, None)
        self._radius.pop(path, None)
        self._last_used.pop(path, None)
        self._failed.pop(path, None)
        self._fractions.pop(path, None)
        self._upload_progress.pop(path, None)
        self._last_order.pop(path, None)
        self._gs_up.pop(path, None)
        self._gs_key = {k: v for k, v in self._gs_key.items() if k[0] != path}
        for attr in ("_gs_pos", "_gs_opa", "_gs_srad", "_gs_order", "_gs_cmd"):
            d = getattr(self, attr)
            buf = d.pop(path, None)
            if buf is not None:
                try:
                    buf.release()
                except Exception:
                    pass
        for k in [k for k in self._sort_cache if k[0] == path]:
            try:
                del self._sort_cache[k]
            except KeyError:
                pass
        self._scratch.pop(path, None)
        if self._uploaded_path == path:
            self._uploaded_path = None
        try:
            if self._idx_key is not None and self._idx_key[0] == path:
                self._idx_key = None
        except Exception:
            self._idx_key = None
        _drop_splat_arrays(path)

    def release_path(self, path: str):
        with self._load_lock:
            self._loading.discard(path)
            self._completed = [(p, d) for (p, d) in self._completed if p != path]
            self._release_locked(path)
        try:
            task_complete(_splat_task_id(path))
        except Exception:
            pass

    def gc_keep(self, keep):
        try:
            keep_set = set(keep) if keep is not None else set()
        except Exception:
            return
        with self._load_lock:
            for path in [p for p in list(self._gpu_data.keys()) if p not in keep_set]:
                self._release_locked(path)
            for path in [p for p in list(self._failed.keys()) if p not in keep_set]:
                self._failed.pop(path, None)

    def collect_garbage(self):
        now = time.monotonic()
        with self._load_lock:
            idle = [p for p, t in self._last_used.items() if (now - t) > _GC_IDLE_S and p in self._gpu_data]
            for path in idle:
                self._release_locked(path)
            if len(self._gpu_data) > _GC_MAX_PATHS:
                ordered = sorted(self._last_used.items(), key=lambda kv: kv[1])
                over = len(self._gpu_data) - _GC_MAX_PATHS
                for path, _ in ordered[:max(0, over)]:
                    if path in self._gpu_data:
                        self._release_locked(path)
            for path in [p for p, t in list(self._failed.items()) if (now - t) > (_SPLAT_FAIL_RETRY_S * 2.0)]:
                self._failed.pop(path, None)

    def _pack_for_gpu(self, data) -> np.ndarray:
        return _pack_struct(data.positions, data.sh_coeffs[:, :3],
                            data.sh_coeffs[:, 3:], max(0, data.sh_coeffs.shape[1] - 3),
                            data.opacity, data.scales, data.quaternions, data.num_splats)

    def prepare(self, path: str, model_matrix, view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
                opacity_threshold=0.005, sh_degree=3, cache_id=None) -> tuple:
        if not self._prog or not self._vao:
            return 0, 0, False
        if path not in self._gpu_data:
            if not self.load_data(path):
                return 0, 0, False
        gpu = self._gpu_data.get(path)
        if gpu is None or len(gpu) == 0:
            return 0, 0, False
        try:
            self._last_used[path] = time.monotonic()
        except Exception:
            pass
        n = len(gpu)
        model_f32 = np.ascontiguousarray(model_matrix.to_f32(), dtype=np.float32)
        view_f32 = np.ascontiguousarray(view_mat.to_f32(), dtype=np.float32)
        proj_f32 = np.ascontiguousarray(proj_mat.to_f32(), dtype=np.float32)
        try:
            px_scale = max(float(viewport_w), float(viewport_h)) * 0.5
        except Exception:
            px_scale = 0.0
        self._ensure_buffers(n)
        total = int(gpu.nbytes)
        if self._uploaded_path != path or self._uploaded_n != n:
            done = int(self._upload_progress.get(path, 0))
            if done <= 0:
                try:
                    self._ssbo.orphan(self._ssbo.size)
                except Exception:
                    pass
                done = 0
            if done < total:
                row = int(_SPLAT_STRUCT_SIZE)
                r0 = done // row
                r1 = min(n, r0 + max(1, _SPLAT_UPLOAD_CHUNK_BYTES // row))
                self._ssbo.write(gpu[r0:r1], offset=r0 * row)
                done = r1 * row
                if done >= total:
                    self._uploaded_path = path
                    self._uploaded_n = n
                    self._upload_progress.pop(path, None)
                else:
                    self._upload_progress[path] = done
                    return 0, n, False
            else:
                self._uploaded_path = path
                self._uploaded_n = n
                self._upload_progress.pop(path, None)
        if n >= _SPLAT_GPU_MIN_N and self._prepare_gpu(path, model_f32, view_f32, proj_f32, cam_pos,
                                                       viewport_w, viewport_h, opacity_threshold,
                                                       sh_degree, cache_id, n, px_scale):
            return 0, n, True
        key, order = self._visible_order(path, model_f32, view_f32, proj_f32, opacity_threshold, cache_id,
                                         px_scale, _SPLAT_MIN_PX)
        m = len(order)
        if m == 0:
            return 0, n
        self._ssbo.bind_to_storage_buffer(0)
        if self._idx_key is None or self._idx_key[0] != path or self._idx_key[1] != key:
            try:
                self._idx_ssbo.orphan(self._idx_ssbo.size)
            except Exception:
                pass
            self._idx_ssbo.write(order)
            self._idx_key = (path, key)
        self._idx_ssbo.bind_to_storage_buffer(1)
        self._upload_uniforms(model_f32, view_f32, proj_f32, cam_pos,
                              viewport_w, viewport_h, sh_degree, opacity_threshold)
        return m, n, False

    def draw_indirect(self, path: str):
        if not self._vao:
            return
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.depth_mask = False
        try:
            cmd = self._gs_cmd.get(path)
            if cmd is None:
                return
            self._vao.render_indirect(cmd, moderngl.TRIANGLE_STRIP, 1, 0)
        except Exception as e:
            Logger.error(f"Gaussian Splat indirect render error: {e}")
        self._ctx.enable(moderngl.CULL_FACE)
        self._ctx.depth_mask = True
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def draw_color(self, m: int):
        if not self._vao or m <= 0:
            return
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.depth_mask = False
        try:
            self._vao.render(moderngl.TRIANGLE_STRIP, vertices=4, instances=m)
        except Exception as e:
            Logger.error(f"Gaussian Splat render error: {e}")
        self._ctx.enable(moderngl.CULL_FACE)
        self._ctx.depth_mask = True
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def render(self, path: str, model_matrix, view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               opacity_threshold=0.005, sh_degree=3, cache_id=None):
        m, _, indirect = self.prepare(path, model_matrix, view_mat, proj_mat, cam_pos,
                                      viewport_w, viewport_h, opacity_threshold, sh_degree, cache_id)
        if indirect:
            self.draw_indirect(path)
        else:
            self.draw_color(m)

    def release(self):
        with self._load_lock:
            pending = list(self._loading)
            self._loading.clear()
            self._completed = []
            self._failed.clear()
            self._fractions.clear()
        for path in pending:
            try:
                task_complete(_splat_task_id(path))
            except Exception:
                pass
        if self._vao:
            self._vao.release()
        if self._ssbo:
            self._ssbo.release()
        if self._idx_ssbo:
            self._idx_ssbo.release()
        if self._prog:
            self._prog.release()
        for prog in self._cs_progs.values():
            try:
                prog.release()
            except Exception:
                pass
        self._cs_progs = {}
        self._cs_ok = None
        for attr in ("_gs_keys0", "_gs_keys1", "_gs_vals0", "_gs_vals1",
                     "_gs_hist", "_gs_offs", "_gs_counter"):
            buf = getattr(self, attr)
            if buf is not None:
                try:
                    buf.release()
                except Exception:
                    pass
                setattr(self, attr, None)
        for attr in ("_gs_pos", "_gs_opa", "_gs_srad", "_gs_order", "_gs_cmd"):
            d = getattr(self, attr)
            for buf in d.values():
                try:
                    buf.release()
                except Exception:
                    pass
            d.clear()
        self._gs_scratch_n = 0
        self._gs_pos.clear()
        self._gs_opa.clear()
        self._gs_srad.clear()
        self._gs_order.clear()
        self._gs_cmd.clear()
        self._gs_up.clear()
        self._gs_key.clear()
        self._gpu_sorts_this_frame = 0
        self._vao = None
        self._ssbo = None
        self._idx_ssbo = None
        self._prog = None
        self._gpu_data.clear()
        self._pos.clear()
        self._opa.clear()
        self._srad.clear()
        self._center.clear()
        self._radius.clear()
        self._sort_cache.clear()
        self._scratch.clear()
        self._last_used.clear()
        self._upload_progress.clear()
        self._last_order.clear()
        self._sorts_this_frame = 0
        self._idx_key = None
        self._uploaded_path = None
        self._uploaded_n = 0
