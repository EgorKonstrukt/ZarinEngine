# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import threading
import weakref
import numpy as np
try:
    from core import _nav_batch as _nb
    _HAS_NAV_CYTHON = True
except ImportError:
    _nb = None
    _HAS_NAV_CYTHON = False
_SHARED_GRIDS: dict = {}
_SHARED_ORDER: list = []
_COLLIDER_TYPES = ("BoxCollider", "SphereCollider", "CapsuleCollider", "MeshCollider")
_NAV_WORKER = None
_NAV_WORKER_LOCK = threading.Lock()
_COARSE_SHARED: dict = {}
_COARSE_LOCK = threading.Lock()


def _rasterize_descs_fresh(r: int, cell: float, half: float, descs) -> np.ndarray:
    fresh = np.zeros((r, r, r), dtype=np.uint8)
    try:
        for d in descs:
            try:
                if d[0] == "b":
                    o = d[1]
                    _nb.raster_box_obb(np.ascontiguousarray(fresh), cell, half,
                                       o[0][0], o[0][1], o[0][2], o[1][0], o[1][1], o[1][2],
                                       o[2][0], o[2][1], o[2][2], o[2][3])
                else:
                    c = d[1]
                    fresh[c[0]:c[3] + 1, c[1]:c[4] + 1, c[2]:c[5] + 1] = 1
            except Exception:
                pass
    except Exception:
        pass
    return fresh

def _shared_grid_for(scene, resolution: int, world_size: float):
    from .grid import NavGrid
    key = (id(scene), int(resolution), round(float(world_size), 3))
    e = _SHARED_GRIDS.get(key)
    if e is not None and e[0]() is scene:
        return e[2]
    g = NavGrid(int(resolution), float(world_size))
    _SHARED_GRIDS[key] = [weakref.ref(scene), -1, g]
    _SHARED_ORDER.append(key)
    while len(_SHARED_ORDER) > 6:
        _SHARED_GRIDS.pop(_SHARED_ORDER.pop(0), None)
    return g

def _coarse_cached(base, f: int, dil: int, ep: int, res: int):
    key = (int(ep), int(res), int(f), int(dil))
    try:
        with _COARSE_LOCK:
            hit = _COARSE_SHARED.get(key)
        if hit is not None:
            return hit
    except Exception:
        pass
    coarse = _nb.downsample_any3d(np.ascontiguousarray(base), int(f))
    if dil > 0:
        coarse = _nb.dilate3d(coarse, int(dil))
    try:
        with _COARSE_LOCK:
            _COARSE_SHARED[key] = coarse
            while len(_COARSE_SHARED) > 4:
                _COARSE_SHARED.pop(next(iter(_COARSE_SHARED)))
    except Exception:
        pass
    return coarse

def _get_nav_worker():
    from .worker import _NavSolveWorker
    global _NAV_WORKER
    w = _NAV_WORKER
    if w is None:
        with _NAV_WORKER_LOCK:
            if _NAV_WORKER is None:
                _NAV_WORKER = _NavSolveWorker()
                _NAV_WORKER.start()
            w = _NAV_WORKER
    return w

def stop_nav_worker():
    global _NAV_WORKER
    w = _NAV_WORKER
    _NAV_WORKER = None
    if w is not None:
        try:
            w.stop()
        except Exception:
            pass