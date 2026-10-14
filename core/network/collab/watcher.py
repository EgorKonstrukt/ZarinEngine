# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import threading
from typing import Callable
class _AssetWatcher(threading.Thread):
    def __init__(self, assets_dir: str, interval: float, on_change: Callable, on_delete: Callable):
        super().__init__(daemon=True)
        self._assets_dir = assets_dir
        self._interval = max(0.5, float(interval))
        self._on_change = on_change
        self._on_delete = on_delete
        self._stop_event = threading.Event()
        self._snapshots: dict[str, float] = {}
        self._lock = threading.Lock()
        self._refresh()
    def _refresh(self):
        with self._lock:
            self._snapshots.clear()
            if not os.path.isdir(self._assets_dir):
                return
            for root, dirs, files in os.walk(self._assets_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, self._assets_dir)
                    try:
                        self._snapshots[rel] = os.path.getmtime(full)
                    except Exception:
                        pass
    def stop(self):
        self._stop_event.set()
    def run(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                return
            if not os.path.isdir(self._assets_dir):
                continue
            current: dict[str, float] = {}
            for root, dirs, files in os.walk(self._assets_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, self._assets_dir)
                    try:
                        current[rel] = os.path.getmtime(full)
                    except Exception:
                        pass
            with self._lock:
                old = dict(self._snapshots)
            for rel, mtime in current.items():
                o = old.get(rel)
                if o is None:
                    try:
                        self._on_change(rel)
                    except Exception:
                        pass
                elif abs(mtime - o) > 0.1:
                    try:
                        self._on_change(rel)
                    except Exception:
                        pass
            for rel in list(old.keys()):
                if rel not in current:
                    try:
                        self._on_delete(rel)
                    except Exception:
                        pass
            with self._lock:
                self._snapshots = current
