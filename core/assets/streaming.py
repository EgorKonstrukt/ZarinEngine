# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

_PREFETCH_CHUNK = 4 << 20


def _read_all(path: str, chunk: int = _PREFETCH_CHUNK) -> int:
    total = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            total += len(b)
    return total


def prefetch_files(paths: list, workers: int = 8,
                   progress: Optional[Callable[[int, int], None]] = None) -> tuple:
    paths = [p for p in paths if os.path.isfile(p)]
    total_bytes = 0
    done_files = 0
    lock = threading.Lock()
    t0 = time.perf_counter()

    def _one(p: str) -> int:
        nonlocal total_bytes, done_files
        n = _read_all(p)
        with lock:
            total_bytes += n
            done_files += 1
            if progress is not None:
                try:
                    progress(done_files, len(paths))
                except Exception:
                    pass
        return n

    if not paths:
        return 0, 0.0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(_one, paths))
    return total_bytes, time.perf_counter() - t0


def load_many(paths: list, loader: Callable[[str], object],
              workers: int = 8, prefetch: bool = True,
              progress: Optional[Callable[[int, int], None]] = None) -> dict:
    paths = list(paths)
    if prefetch and len(paths) > 1:
        prefetch_files(paths, workers=workers)
    results: dict = {}
    lock = threading.Lock()
    done = 0

    def _one(p: str):
        nonlocal done
        try:
            data = loader(p)
        except Exception:
            data = None
        with lock:
            results[p] = data
            done += 1
            if progress is not None:
                try:
                    progress(done, len(paths))
                except Exception:
                    pass

    if not paths:
        return results
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(_one, paths))
    return results


def disk_ceiling_mbps(path: str, chunk: int = _PREFETCH_CHUNK) -> float:
    n = os.path.getsize(path)
    t0 = time.perf_counter()
    _read_all(path, chunk)
    dt = time.perf_counter() - t0
    return n / dt / 1e6 if dt > 0 else 0.0
