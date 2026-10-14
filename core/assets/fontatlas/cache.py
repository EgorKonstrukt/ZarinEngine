# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import threading
import queue as _queue
from collections import OrderedDict
from core.assets.fontatlas.atlas import FontAtlas
from core.assets.fontatlas.atlas import get_default_font_path
_font_atlas_max_cached = 3
_font_atlas_cache: "OrderedDict" = OrderedDict()
_font_atlas_pending: set = set()
_font_atlas_lock = threading.Lock()
_font_atlas_queue: "_queue.Queue" = _queue.Queue()
_font_atlas_thread = None
def _font_atlas_worker() -> None:
    while True:
        item = _font_atlas_queue.get()
        if item is None:
            _font_atlas_queue.task_done()
            break
        key, font_path, base_size = item
        try:
            atlas = FontAtlas(font_path, base_size)
        except Exception:
            atlas = None
        with _font_atlas_lock:
            _font_atlas_pending.discard(key)
            _font_atlas_cache[key] = atlas
            _font_atlas_cache.move_to_end(key)
            while len(_font_atlas_cache) > _font_atlas_max_cached:
                _font_atlas_cache.popitem(last=False)
        _font_atlas_queue.task_done()
def _ensure_font_atlas_thread() -> None:
    global _font_atlas_thread
    if _font_atlas_thread is None:
        _font_atlas_thread = threading.Thread(target=_font_atlas_worker, daemon=True, name="font-atlas")
        _font_atlas_thread.start()
def request_font_atlas(font_path: str, base_size: int = 128):
    if not font_path or not os.path.exists(font_path):
        resolved = get_default_font_path()
        if not resolved:
            return None
        font_path = resolved
    key = (font_path, base_size)
    with _font_atlas_lock:
        if key in _font_atlas_cache:
            _font_atlas_cache.move_to_end(key)
            return _font_atlas_cache[key]
        if key in _font_atlas_pending:
            return None
        _font_atlas_pending.add(key)
    _ensure_font_atlas_thread()
    _font_atlas_queue.put((key, font_path, base_size))
    return None
def drop_font_atlas(font_path: str, base_size: int = 128) -> None:
    key = (font_path, base_size)
    with _font_atlas_lock:
        _font_atlas_cache.pop(key, None)
def get_cached_font_atlas(font_path: str, base_size: int = 128):
    if not font_path:
        return None
    with _font_atlas_lock:
        a = _font_atlas_cache.get((font_path, base_size))
        if a is not None:
            _font_atlas_cache.move_to_end((font_path, base_size))
        return a
def shutdown_font_atlas_loader() -> None:
    with _font_atlas_lock:
        if _font_atlas_thread is None:
            return
    _font_atlas_queue.put(None)
    _font_atlas_thread.join(timeout=2.0)
