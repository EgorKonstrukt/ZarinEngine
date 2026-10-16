# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
_cache: dict = {}
_MAX_DIRS = 512


def list_dir(dirpath: str) -> list:
    norm = os.path.normpath(dirpath)
    try:
        key = os.stat(norm).st_mtime_ns
    except OSError:
        _cache.pop(norm, None)
        return []
    hit = _cache.get(norm)
    if hit is not None and hit[0] == key:
        return hit[1]
    rows = []
    try:
        with os.scandir(norm) as it:
            for entry in it:
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                try:
                    s = entry.stat(follow_symlinks=False)
                    rows.append((entry.name, is_dir, s.st_size, s.st_mtime_ns))
                except OSError:
                    rows.append((entry.name, is_dir, -1, 0))
    except OSError:
        return []
    rows.sort(key=lambda r: r[0].lower())
    if len(_cache) >= _MAX_DIRS:
        try:
            _cache.pop(next(iter(_cache)))
        except Exception:
            pass
    _cache[norm] = (key, rows)
    return rows


def invalidate(path: str) -> None:
    try:
        cur = os.path.normpath(os.path.abspath(path))
        for _ in range(64):
            _cache.pop(cur, None)
            nxt = os.path.normpath(os.path.dirname(cur))
            if nxt == cur:
                break
            cur = nxt
    except Exception:
        pass


def clear() -> None:
    _cache.clear()
