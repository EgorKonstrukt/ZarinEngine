# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import threading
import numpy as np
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import Future
from core.foundation.logger import Logger


class SceneThreadPool:
    def __init__(self, max_workers: int = 2):
        self._max_workers = max(1, int(max_workers))
        self._executor = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="phys-scene")

    def stop(self, wait: bool = True):
        with self._lock:
            ex = self._executor
            self._executor = None
        if ex is not None:
            try:
                ex.shutdown(wait=bool(wait), cancel_futures=True)
            except Exception:
                try:
                    ex.shutdown(wait=bool(wait))
                except Exception:
                    pass

    def submit(self, fn, *args, **kwargs) -> Future | None:
        with self._lock:
            ex = self._executor
        if ex is None:
            return None
        try:
            return ex.submit(fn, *args, **kwargs)
        except Exception:
            return None

    def flush(self):
        with self._lock:
            ex = self._executor
        if ex is None:
            return
        try:
            fut = ex.submit(lambda: None)
            fut.result(timeout=5.0)
        except Exception:
            pass

    @property
    def running(self) -> bool:
        with self._lock:
            return self._executor is not None


class ThreadpoolMixin:
    def start_background_workers(self, max_workers: int = 2):
        try:
            pool = getattr(self, "_bg_pool", None)
            if pool is None:
                pool = SceneThreadPool(max_workers=max_workers)
                self._bg_pool = pool
            pool.start()
        except Exception:
            pass

    def stop_background_workers(self, wait: bool = True):
        try:
            pool = getattr(self, "_bg_pool", None)
            if pool is not None:
                pool.stop(wait=wait)
        except Exception:
            pass

    def submit_background(self, fn, *args, **kwargs):
        try:
            pool = getattr(self, "_bg_pool", None)
            if pool is None:
                return None
            return pool.submit(fn, *args, **kwargs)
        except Exception:
            return None

    def _sync_soft_mesh(self, entity_id: str, soft, local):
        import numpy as np
        try:
            local = np.ascontiguousarray(local, dtype=np.float32)
        except Exception:
            return
        try:
            soft._soft_latest_local = np.ascontiguousarray(local, dtype=np.float32)
        except Exception:
            pass
        ov = getattr(soft, "_render_mesh", None)
        if ov is None:
            self._diag_soft_once(f"sync '{entity_id}': soft._render_mesh is None (renderer override not built)")
            return
        try:
            sk_idx = getattr(soft, "_soft_skin_idx", None)
            sk_w = getattr(soft, "_soft_skin_w", None)
            sk_nsim = int(getattr(soft, "_soft_skin_nsim", -1))
            sk_nfull = int(getattr(soft, "_soft_skin_nfull", -1))
            sk_rows = int(np.asarray(sk_idx).shape[0]) if sk_idx is not None else -1
            sk_cols = int(np.asarray(sk_idx).shape[1]) if sk_idx is not None else -1
            ov_rows = int(len(np.asarray(ov.vertices).reshape(-1, 3)))
            skin_valid = (
                sk_idx is not None and sk_w is not None
                and np.asarray(sk_w).shape == np.asarray(sk_idx).shape
                and sk_rows == sk_nfull and sk_nsim == len(local)
                and ov_rows == sk_rows and sk_cols >= 1
            )
        except Exception:
            skin_valid = False
        if skin_valid:
            try:
                L = np.ascontiguousarray(local, dtype=np.float32)
                ii = np.asarray(sk_idx, dtype=np.int64)
                ww = np.ascontiguousarray(sk_w, dtype=np.float32)
                full = np.zeros((len(ii), 3), dtype=np.float32)
                for c in range(ii.shape[1]):
                    full += ww[:, c:c + 1] * L[ii[:, c]]
            except Exception:
                return
            if not np.all(np.isfinite(full)):
                return
            try:
                ov.vertices = np.ascontiguousarray(full.reshape(-1))
                if getattr(soft, "recompute_normals", True):
                    try:
                        from core.assets.importer import _compute_smooth_normals
                        faces = getattr(ov, "_soft_faces", None)
                        if faces is not None:
                            ov.normals = np.ascontiguousarray(
                                _compute_smooth_normals(full.astype(np.float32), np.asarray(faces)).reshape(-1))
                    except Exception:
                        pass
                ov.compute_aabb()
                try:
                    ov._soft_dirty = True
                    ov._soft_version = int(getattr(ov, "_soft_version", 0) or 0) + 1
                except Exception:
                    pass
                self._diag_frame(entity_id, np.asarray(full, dtype=np.float32))
            except Exception:
                pass
            return
        try:
            use_skin = getattr(soft, "_soft_use_skin", None)
        except Exception:
            use_skin = None
        if use_skin is False:
            try:
                ov_n = len(np.asarray(ov.vertices).reshape(-1, 3))
            except Exception:
                ov_n = -1
            if ov_n != len(local):
                self._diag_soft_once(f"sync '{entity_id}': count mismatch render={ov_n} physics={len(local)}, rebuilding render mesh to physics count")
            try:
                if len(local) != len(np.asarray(ov.vertices).reshape(-1, 3)):
                    sv_compact = getattr(soft, "_soft_verts", None)
                    sf_compact = getattr(soft, "_soft_faces", None)
                    if sv_compact is not None and len(sv_compact) == len(local):
                        ov.vertices = np.ascontiguousarray(sv_compact, dtype=np.float32).reshape(-1).copy()
                        ov.normals = np.zeros_like(ov.vertices)
                        n_verts = len(local)
                        try:
                            ov.uvs = np.zeros((n_verts * 2,), dtype=np.float32)
                        except Exception:
                            pass
                        try:
                            ov.sub_mesh_ranges = []
                            ov.sub_mesh_names = []
                        except Exception:
                            pass
                        if sf_compact is not None and len(sf_compact) >= 3:
                            ov.indices = np.ascontiguousarray(sf_compact, dtype=np.uint32).reshape(-1).copy()
                            ov._soft_faces = np.ascontiguousarray(sf_compact, dtype=np.int64).reshape(-1).copy()
                        ov._soft_n = len(local)
                    else:
                        sv_len = len(sv_compact) if sv_compact is not None else -1
                        self._diag_soft_once(f"sync '{entity_id}': cannot rebuild (sv_compact={sv_len} local={len(local)})")
                        return
            except Exception:
                self._diag_soft_once(f"sync '{entity_id}': rebuild exception")
                return
            try:
                ov.vertices = np.ascontiguousarray(local.reshape(-1))
                if getattr(soft, "recompute_normals", True):
                    try:
                        from core.assets.importer import _compute_smooth_normals
                        faces = getattr(ov, "_soft_faces", None)
                        if faces is not None:
                            ov.normals = np.ascontiguousarray(
                                _compute_smooth_normals(local.astype(np.float32), np.asarray(faces)).reshape(-1))
                    except Exception:
                        pass
                ov.compute_aabb()
                try:
                    ov._soft_dirty = True
                    ov._soft_version = int(getattr(ov, "_soft_version", 0) or 0) + 1
                except Exception:
                    pass
                self._diag_frame(entity_id, np.asarray(local, dtype=np.float32))
            except Exception:
                pass
            return
        try:
            soft._soft_needs_rebuild = True
        except Exception:
            pass

    def _diag_frame(self, entity_id: str, local):
        seen = getattr(self, "_diag_seen", {})
        if entity_id not in seen:
            seen[entity_id] = 0
        seen[entity_id] += 1
        self._diag_seen = seen
        if seen[entity_id] in (1, 2, 3, 4, 5) or seen[entity_id] % 15 == 0:
            try:
                ymin = float(local[:, 1].min())
                ymax = float(local[:, 1].max())
            except Exception:
                ymin = ymax = float("nan")
            Logger.info(f"[SoftBody] frame number {seen[entity_id]} '{entity_id}' local y-range: {round(ymin,3)}..{round(ymax,3)}")
