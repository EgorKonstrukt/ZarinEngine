# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from concurrent.futures.thread import ThreadPoolExecutor
import os
from typing import Optional
from PySide6.QtCore import QThread, Signal

def _find_engine_root() -> Optional[str]:
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(cur) == "editor":
            return os.path.dirname(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None

class _PopulateWorker(QThread):
    batch_ready = Signal(object)

    def __init__(self, project_root: str, extensions: tuple, filter_text: str):
        super().__init__()
        self._project_root = project_root
        self._extensions = extensions
        self._filter_text = filter_text
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        _skip_dirs = {"build", "build_output", ".git", ".idea", "__pycache__",
                       "node_modules", ".venv", "venv", "tools", ".pytest_cache",
                       "physics_solvers", "thirdparty", "lib"}
        search_root = self._project_root
        assets_dir = os.path.join(self._project_root, "assets")
        if os.path.isdir(assets_dir):
            search_root = assets_dir
        engine_root = _find_engine_root()
        extra_dirs: list[str] = []
        for sub in ("core/shaders",):
            for base in (self._project_root, engine_root):
                if not base:
                    continue
                d = os.path.normpath(os.path.join(base, sub))
                if os.path.isdir(d) and not d.startswith(os.path.normpath(search_root)):
                    if d not in extra_dirs:
                        extra_dirs.append(d)
        search_dirs = [search_root] + extra_dirs
        batch: list = []
        seen_paths: set[str] = set()
        pending: list[tuple[str, str]] = []
        for search_dir in search_dirs:
            for root, dirs, files in os.walk(search_dir):
                if self._cancelled:
                    return
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _skip_dirs]
                for f in files:
                    if self._cancelled:
                        return
                    if f.startswith("."):
                        continue
                    if f.endswith(".import"):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    if self._extensions and ext not in self._extensions:
                        continue
                    if self._filter_text and self._filter_text.lower() not in f.lower():
                        continue
                    full_path = os.path.normpath(os.path.join(root, f))
                    if full_path in seen_paths:
                        continue
                    seen_paths.add(full_path)
                    pending.append((full_path, f))
                    if len(pending) >= 200:
                        self._flush_pending(pending, batch)
                        if len(batch) >= 100:
                            self.batch_ready.emit(batch)
                            batch = []
                        pending = []
                        if self._cancelled:
                            return
        if pending:
            self._flush_pending(pending, batch)
        if batch:
            self.batch_ready.emit(batch)

    def _flush_pending(self, pending: list[tuple[str, str]], batch: list):
        def stat_one(item: tuple[str, str]):
            full_path, f = item
            try:
                sz = os.path.getsize(full_path)
            except OSError:
                sz = 0
            try:
                rel = os.path.relpath(full_path, self._project_root)
            except Exception:
                rel = full_path
            return (full_path, f, rel, sz)
        if len(pending) > 16:
            with ThreadPoolExecutor(max_workers=8) as ex:
                for r in ex.map(stat_one, pending):
                    batch.append(r)
        else:
            for item in pending:
                batch.append(stat_one(item))
