# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import threading
import time
_NAV_STATS: dict = {}
_NAV_STATS_LOCK = threading.Lock()


def _stat(key: str, dt_ms: float):
    try:
        with _NAV_STATS_LOCK:
            e = _NAV_STATS.get(key)
            if e is None:
                e = _NAV_STATS[key] = [0, 0.0, 0.0]
            e[0] += 1
            e[1] += dt_ms
            if dt_ms > e[2]:
                e[2] = dt_ms
    except Exception:
        pass

def _timed(key: str):
    def deco(fn):
        try:
            import functools

            @functools.wraps(fn)
            def wrap(*a, **k):
                t0 = time.perf_counter()
                try:
                    return fn(*a, **k)
                finally:
                    try:
                        _stat(key, (time.perf_counter() - t0) * 1000.0)
                    except Exception:
                        pass
            return wrap
        except Exception:
            return fn
    return deco

def nav_stats(reset: bool = False) -> dict:
    try:
        out = {k: {"n": v[0], "total_ms": round(v[1], 1),
                   "avg_ms": round(v[1] / v[0], 3) if v[0] else 0.0,
                   "max_ms": round(v[2], 2)} for k, v in _NAV_STATS.items()}
    except Exception:
        out = {}
    if reset:
        try:
            with _NAV_STATS_LOCK:
                _NAV_STATS.clear()
        except Exception:
            pass
    return out