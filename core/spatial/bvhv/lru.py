# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future
import numpy as np
import xxhash
from core.ecs.pool import bvh as _get_bvh_pool
from core.foundation.progress import task_complete
from core.foundation.progress import task_start
from core.foundation.progress import get_progress_queue

_BVH_LOG = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "zarin_bvh_log.txt")
try:
    with open(_BVH_LOG, "w", encoding="utf-8") as _lf:
        _lf.write(f"=== BVH LOG RESET ===\n")
except OSError:
    pass

def _bvh_log(msg: str) -> None:
    try:
        with open(_BVH_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"{time.monotonic():.3f} {msg}\n")
    except OSError:
        pass

_bvh_progress_queue: object | None = None
_BVH_CACHE_VERSION = 13
_BVH_CACHE_MAX = 32

def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{int(v)}M" if v == int(v) else f"{v:.1f}M"
    if n >= 1_000:
        v = n / 1_000
        return f"{int(v)}k" if v == int(v) else f"{v:.1f}k"
    return str(n)

def _pq_put(msg):
    q = _bvh_progress_queue
    if q is not None:
        try:
            q.put_nowait(msg)
        except Exception:
            pass

def _bvh_task_update(task_id, fraction=None, detail=None, total=None, units=None):
    if _bvh_progress_queue is not None:
        kw = {}
        if fraction is not None:
            kw["fraction"] = fraction
        if detail is not None:
            kw["detail"] = detail
        if total is not None:
            kw["total"] = total
        if units is not None:
            kw["units"] = units
        _pq_put(("update", (task_id,), kw))
    else:
        from core.foundation.progress import task_update as _tu
        _tu(task_id, fraction=fraction, detail=detail, total=total, units=units)

def _report_build_progress(ctx):
    if ctx.total_tris <= 0:
        return
    frac = ctx.progress_done / ctx.total_tris
    now = time.monotonic()
    if frac - ctx.last_frac >= 0.02 or now - ctx.last_t >= 0.25:
        ctx.last_frac = frac
        ctx.last_t = now
        detail = (f"{_fmt_count(ctx.progress_done)} / {_fmt_count(ctx.total_tris)} tris" f" · {_fmt_count(ctx.n_verts)} verts")
        _bvh_task_update(ctx.task_id, frac, detail=detail)

class _BvhLru(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        while len(self) > _BVH_CACHE_MAX:
            oldest = next(iter(self))
            if oldest == key:
                break
            old = self.pop(oldest)
            try:
                from concurrent.futures import Future as _Fut
                if isinstance(old, _Fut):
                    old.cancel()
            except Exception:
                pass

_BVH_CACHE: dict = _BvhLru()
_BVH_LOCK = threading.Lock()
_BVH_CACHE_RUNTIME_VERSION: int = _BVH_CACHE_VERSION
_bvh_none_logged: set = set()
_BVH_FAILED: dict = {}
_BVH_FAIL_BACKOFF = 5.0
_BVH_ID_MEMO: dict = {}
_BVH_ID_MEMO_MAX: int = 1024
_BVH_MAKEDIRS_DONE: set = set()

class _NodeView:
    __slots__ = ('_data',)
    def __init__(self, data):
        self._data = data
    @property
    def bmin(self):
        return self._data[0:3]
    @property
    def bmax(self):
        return self._data[3:6]
    @property
    def left(self):
        return int(self._data[6])
    @property
    def right(self):
        return int(self._data[7])
    @property
    def tri_start(self):
        return int(self._data[6])
    @property
    def tri_count(self):
        return 0 if self._data[7] >= 0 else int(-self._data[7] - 1)
    @property
    def is_leaf(self):
        return self._data[7] < 0

def _bvh_cache_store(key: str, value) -> None:
    _BVH_CACHE[key] = value
    if len(_bvh_none_logged) > 512:
        _bvh_none_logged.clear()

def _bvh_cache_key(vertices: np.ndarray, indices: np.ndarray) -> str:
    h = xxhash.xxh128()
    h.update(vertices.data)
    h.update(indices.data)
    return h.hexdigest()

def _bvh_key_memoized(vertices: np.ndarray, indices: np.ndarray) -> str:
    try:
        idk = (id(vertices), id(indices))
        me = _BVH_ID_MEMO.get(idk)
        if me is not None and me[0]() is vertices and me[1]() is indices and vertices.nbytes == me[2] and indices.nbytes == me[3]:
            return me[4]
    except Exception:
        me = None
        idk = None
    key = _bvh_cache_key(vertices, indices)
    try:
        import weakref as _wr
        if idk is not None:
            if len(_BVH_ID_MEMO) >= _BVH_ID_MEMO_MAX:
                _BVH_ID_MEMO.clear()
            _BVH_ID_MEMO[idk] = (_wr.ref(vertices), _wr.ref(indices), vertices.nbytes, indices.nbytes, key)
    except Exception:
        pass
    return key

def _bvh_cache_dir() -> str | None:
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng is None:
            return None
        root = eng.project_root
        if root in _BVH_MAKEDIRS_DONE:
            return os.path.join(root, "cache", "bvh")
        d = os.path.join(root, "cache", "bvh")
        os.makedirs(d, exist_ok=True)
        _BVH_MAKEDIRS_DONE.add(root)
        return d
    except (ImportError, OSError, AttributeError, TypeError):
        return None

def _save_bvh_disk(key: str, bvh, cache_dir: str) -> None:
    prefix = f"v{_BVH_CACHE_VERSION}_{key}"
    nodes_path = os.path.join(cache_dir, prefix + "_n.npy")
    tmp_nodes = nodes_path + ".tmp"
    tris_path = os.path.join(cache_dir, prefix + "_t.npy")
    tmp_tris = tris_path + ".tmp"
    root_path = os.path.join(cache_dir, prefix + "_r.npy")
    tmp_root = root_path + ".tmp"
    try:
        np.save(tmp_nodes, bvh._nodes, allow_pickle=False)
        np.save(tmp_tris, bvh._tri_indices, allow_pickle=False)
        np.save(tmp_root, np.array(bvh._root_idx, dtype=np.int32), allow_pickle=False)
        os.replace(tmp_nodes + ".npy", nodes_path)
        os.replace(tmp_tris + ".npy", tris_path)
        os.replace(tmp_root + ".npy", root_path)
    except (OSError, ValueError):
        for p in (tmp_nodes + ".npy", tmp_tris + ".npy", tmp_root + ".npy", tmp_nodes, tmp_tris, tmp_root):
            try:
                os.remove(p)
            except OSError:
                pass

def _load_bvh_disk(key: str, cache_dir: str, vertices: np.ndarray, indices: np.ndarray):
    prefix = f"v{_BVH_CACHE_VERSION}_{key}"
    nodes_path = os.path.join(cache_dir, prefix + "_n.npy")
    tris_path = os.path.join(cache_dir, prefix + "_t.npy")
    root_path = os.path.join(cache_dir, prefix + "_r.npy")
    try:
        nodes = np.load(nodes_path, allow_pickle=False)
        tri_indices = np.load(tris_path, allow_pickle=False)
    except (OSError, ValueError):
        return None
    root_idx = len(nodes) - 1
    try:
        root_idx = int(np.load(root_path, allow_pickle=False))
    except (OSError, ValueError):
        pass
    from .bvh import BVH
    return BVH.from_cache(np.array(nodes), tri_indices, vertices, indices, root_idx)

def _build_bvh(vertices: np.ndarray, indices: np.ndarray, title: str | None = None, cache_key: str | None = None, progress_queue: object | None = None):
    global _bvh_progress_queue
    _bvh_progress_queue = progress_queue
    task_id = cache_key or str(id(vertices))
    _bvh_log(f"BUILD start key={task_id} verts={len(vertices)} idx={len(indices)}")
    if progress_queue is not None:
        _pq_put(("start", (task_id, title or "Building BVH..."), {"fraction": 0.0}))
    else:
        task_start(task_id, title or "Building BVH...", fraction=0.0)
    try:
        from .bvh import BVH
        bvh = BVH(vertices, indices, task_id=task_id)
        result = bvh._nodes.copy(), bvh._tri_indices.copy(), bvh._root_idx
        _bvh_log(f"BUILD done key={task_id} nodes={result[0].shape[0]}")
        return result
    except Exception as exc:
        _bvh_log(f"BUILD FAIL key={task_id} {type(exc).__name__}: {exc}")
        return None
    finally:
        _bvh_progress_queue = None
        try:
            if progress_queue is not None:
                progress_queue.put_nowait(("complete", (task_id,), {}))
            else:
                task_complete(task_id)
        except Exception:
            pass

def prebuild_mesh_bvh(vertices: np.ndarray, indices: np.ndarray, title: str | None = None) -> None:
    if vertices is None or len(vertices) < 3 or indices is None or len(indices) < 3:
        key = _bvh_cache_key(np.zeros(3, dtype=np.float32) if vertices is None else vertices, np.zeros(3, dtype=np.uint32) if indices is None else indices)
        with _BVH_LOCK:
            _BVH_CACHE[key] = None
        _bvh_log(f"PREBUILD skip (tiny mesh)")
        return
    key = _bvh_cache_key(vertices, indices)
    with _BVH_LOCK:
        if key in _BVH_FAILED and time.monotonic() < _BVH_FAILED[key]:
            _bvh_log(f"PREBUILD key={key} COOLDOWN")
            return
        if key in _BVH_CACHE:
            _bvh_log(f"PREBUILD key={key} ALREADY_CACHED")
            return
        cache_dir = _bvh_cache_dir()
        if cache_dir:
            cached = _load_bvh_disk(key, cache_dir, vertices, indices)
            if cached is not None:
                _BVH_CACHE[key] = cached
                _bvh_log(f"PREBUILD key={key} DISK_HIT")
                return
        n_tris = len(indices) // 3
        if n_tris <= 512:
            try:
                nodes, tris, root = _build_bvh(vertices, indices, title, key, progress_queue=None) or (None, None, None)
                if nodes is not None:
                    from .bvh import BVH
                    bvh = BVH.from_cache(nodes, tris, vertices, indices, root)
                    _BVH_CACHE[key] = bvh
                    if cache_dir:
                        _save_bvh_disk(key, bvh, cache_dir)
                    _bvh_log(f"PREBUILD key={key} SYNC_BUILT nodes={bvh.node_count()}")
                    return
            except Exception:
                pass
        try:
            pool = _get_bvh_pool()
            pq = get_progress_queue()
            _bvh_log(f"PREBUILD key={key} SUBMIT verts={len(vertices)} idx={len(indices)} pool={type(pool).__name__}")
            _BVH_CACHE[key] = pool.submit(_build_bvh, vertices, indices, title, key, progress_queue=pq)
        except Exception as exc:
            _bvh_log(f"PREBUILD key={key} SUBMIT FAIL {type(exc).__name__}: {exc}")
            try:
                import core.ecs.pool as _pm
                _pm._bvh_pool = None
                pool = _get_bvh_pool()
                pq = get_progress_queue()
                _BVH_CACHE[key] = pool.submit(_build_bvh, vertices, indices, title, key, progress_queue=pq)
            except Exception as exc2:
                _bvh_log(f"PREBUILD key={key} RETRY FAIL {type(exc2).__name__}")
                try:
                    nodes, tris, root = _build_bvh(vertices, indices, title, key, progress_queue=None) or (None, None, None)
                    if nodes is not None:
                        from .bvh import BVH
                        bvh = BVH.from_cache(nodes, tris, vertices, indices, root)
                        _BVH_CACHE[key] = bvh
                        if cache_dir:
                            _save_bvh_disk(key, bvh, cache_dir)
                        return
                except Exception:
                    pass
                _BVH_FAILED[key] = time.monotonic() + _BVH_FAIL_BACKOFF
                _BVH_CACHE[key] = None
                _bvh_log(f"PREBUILD key={key} FAILED_COOLDOWN")

def _clear_bvh_cache_locked():
    for v in list(_BVH_CACHE.values()):
        try:
            if isinstance(v, Future):
                v.cancel()
        except Exception:
            pass
    _BVH_CACHE.clear()
    _BVH_FAILED.clear()
    _bvh_none_logged.clear()
    _BVH_ID_MEMO.clear()
    try:
        import core.ecs.pool as _pool_mod
        if _pool_mod._bvh_pool is not None:
            try:
                _pool_mod._bvh_pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                try:
                    _pool_mod._bvh_pool.shutdown(wait=False)
                except Exception:
                    pass
            _pool_mod._bvh_pool = None
    except Exception:
        pass
