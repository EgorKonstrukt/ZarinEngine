# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

import moderngl
import numpy as np

from core.assets.matp import Material, MaterialLibrary
from core.assets.texture_import_settings import TextureImportSettings
from core.engine.eng import Engine
from core.foundation.logger import Logger
from core.foundation.progress import task_complete, task_set_detail, task_start

_TEX_MAX_PER_FRAME = 2
_TEX_MAX_PIXELS_PER_FRAME = 8 * 1024 * 1024
_TEX_MTIME_TTL = 2.0
_TEX_MISSING_TTL = 2.0

class MaterialCacheMixin:

    def load_texture(self, path: str) -> Optional[Any]:
        if not path:
            return None
        abs_path = self._resolve_tex_path(path)
        if not abs_path:
            return None
        cached = self._texture_cache.get(abs_path)
        if cached is not None:
            try:
                now = time.monotonic()
            except Exception:
                now = 0.0
            try:
                last = self._tex_mtime_checked.get(abs_path, 0.0)
            except Exception:
                last = 0.0
            if (now - last) < _TEX_MTIME_TTL:
                try:
                    return cached[1]
                except Exception:
                    pass
            try:
                self._tex_mtime_checked[abs_path] = now
            except Exception:
                pass
            try:
                import_mtime = TextureImportSettings.import_mtime(abs_path)
            except Exception:
                try:
                    return cached[1]
                except Exception:
                    return None
            try:
                if abs(import_mtime - cached[0]) < 0.001:
                    return cached[1]
            except Exception:
                try:
                    return cached[1]
                except Exception:
                    return None
            try:
                try:
                    cached[1].release()
                except Exception:
                    pass
                self._texture_cache.pop(abs_path, None)
            except Exception:
                pass
            cached = None
        else:
            try:
                now = time.monotonic()
            except Exception:
                now = 0.0
            try:
                miss_at = self._tex_missing.get(abs_path, 0.0)
                if miss_at and (now - miss_at) < _TEX_MISSING_TTL:
                    return None
            except Exception:
                pass
            try:
                exists = os.path.exists(abs_path)
            except Exception:
                exists = False
            if not exists:
                try:
                    self._tex_missing[abs_path] = now
                    if len(self._tex_missing) > 1024:
                        self._tex_missing.clear()
                        self._tex_missing[abs_path] = now
                except Exception:
                    pass
                return None
            try:
                self._tex_missing.pop(abs_path, None)
            except Exception:
                pass
        try:
            if abs_path in self._tex_inflight:
                return None
        except Exception:
            pass
        try:
            if len(self._tex_inflight) > 1024:
                self._tex_inflight.clear()
            self._tex_inflight.add(abs_path)
        except Exception:
            pass
        try:
            self.load_texture_async(abs_path, lambda tex, p=abs_path: self._tex_inflight.discard(p))
        except Exception:
            try:
                self._tex_inflight.discard(abs_path)
            except Exception:
                pass
        return None

    def _resolve_tex_path(self, path: str) -> str:
        try:
            cached = self._tex_path_cache.get(path)
            if cached is not None:
                return cached
        except Exception:
            pass
        try:
            if os.path.exists(path):
                res = os.path.abspath(path)
                try:
                    self._tex_path_cache[path] = res
                    if len(self._tex_path_cache) > 2048:
                        self._tex_path_cache.clear()
                        self._tex_path_cache[path] = res
                except Exception:
                    pass
                return res
        except Exception:
            pass
        try:
            if not os.path.isabs(path):
                candidate = os.path.join(os.getcwd(), path)
                try:
                    if os.path.exists(candidate):
                        try:
                            self._tex_path_cache[path] = candidate
                            if len(self._tex_path_cache) > 2048:
                                self._tex_path_cache.clear()
                                self._tex_path_cache[path] = candidate
                        except Exception:
                            pass
                        return candidate
                except Exception:
                    pass
        except Exception:
            pass
        try:
            eng = Engine.instance()
        except Exception:
            eng = None
        try:
            root = eng.project_root if eng and eng.project_root else os.getcwd()
        except Exception:
            root = os.getcwd()
        try:
            if len(path) > 1 and path[1] == ":":
                parts = path.replace("\\", "/").split("/")
                for i in range(len(parts)):
                    sub = "/".join(parts[i:])
                    if sub:
                        c = os.path.normpath(os.path.join(root, sub))
                        try:
                            if os.path.exists(c):
                                res = c.replace("\\", "/")
                                try:
                                    self._tex_path_cache[path] = res
                                    if len(self._tex_path_cache) > 2048:
                                        self._tex_path_cache.clear()
                                        self._tex_path_cache[path] = res
                                except Exception:
                                    pass
                                return res
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            candidate = os.path.normpath(os.path.join(root, path))
        except Exception:
            try:
                self._tex_path_cache[path] = path
            except Exception:
                pass
            return path
        try:
            if os.path.exists(candidate):
                try:
                    self._tex_path_cache[path] = candidate
                    if len(self._tex_path_cache) > 2048:
                        self._tex_path_cache.clear()
                        self._tex_path_cache[path] = candidate
                except Exception:
                    pass
                return candidate
        except Exception:
            pass
        try:
            self._tex_path_cache[path] = path
            if len(self._tex_path_cache) > 2048:
                keep = self._tex_path_cache.get(path)
                self._tex_path_cache.clear()
                if keep is not None:
                    self._tex_path_cache[path] = keep
        except Exception:
            pass
        return path

    def load_texture_async(self, path: str, callback) -> None:
        try:
            if not path:
                try:
                    callback(None)
                except Exception:
                    pass
                return
        except Exception:
            return
        try:
            abs_path = self._resolve_tex_path(path)
        except Exception:
            abs_path = path
        try:
            if not abs_path or not os.path.exists(abs_path):
                try:
                    callback(None)
                except Exception:
                    pass
                return
        except Exception:
            try:
                callback(None)
            except Exception:
                pass
            return
        try:
            cached = self._texture_cache.get(abs_path)
            if cached is not None:
                try:
                    cached_mtime, cached_tex = cached
                except Exception:
                    cached = None
                if cached is not None:
                    try:
                        import_mtime = TextureImportSettings.import_mtime(abs_path)
                    except Exception:
                        import_mtime = cached_mtime
                    try:
                        if abs(import_mtime - cached_mtime) < 0.001:
                            try:
                                callback(cached_tex)
                            except Exception:
                                pass
                            return
                    except Exception:
                        try:
                            callback(cached_tex)
                        except Exception:
                            pass
                        return
        except Exception:
            pass
        try:
            from core.ecs.pool import asset as _get_asset_pool
        except Exception:
            try:
                callback(None)
            except Exception:
                pass
            return
        try:
            file_size = os.path.getsize(abs_path)
        except OSError:
            file_size = 0
        try:
            task_start("tex_load:" + abs_path, f"Loading texture {os.path.basename(abs_path)}...",
                       total=float(file_size) if file_size else None, units="bytes")
        except Exception:
            pass

        def _task():
            try:
                from PIL import Image
                img = Image.open(abs_path).convert("RGBA")
            except (ImportError, OSError, ValueError):
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
                return
            except Exception:
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
                return
            try:
                import_settings = TextureImportSettings.for_file(abs_path)
                w, h = img.size
                longest = max(w, h)
                if longest > import_settings.max_size:
                    scale = import_settings.max_size / longest
                    img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            except Exception:
                pass
            try:
                task_set_detail("tex_load:" + abs_path, f"{img.size[0]}×{img.size[1]}")
            except Exception:
                pass
            try:
                lock = self._async_lock
                if lock is not None:
                    with lock:
                        self._pending_texture_queue.append((abs_path, callback, img))
                else:
                    self._pending_texture_queue.append((abs_path, callback, img))
            except Exception:
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
        try:
            _get_asset_pool().submit(_task)
        except Exception:
            try:
                task_complete("tex_load:" + abs_path)
            except Exception:
                pass
            try:
                callback(None)
            except Exception:
                pass

    def process_texture_pending(self, max_textures: int | None = None, max_pixels: int | None = None) -> None:
        try:
            if not self._pending_texture_queue:
                return
        except Exception:
            return
        if max_textures is None:
            max_textures = _TEX_MAX_PER_FRAME
        if max_pixels is None:
            max_pixels = _TEX_MAX_PIXELS_PER_FRAME
        try:
            lock = self._async_lock
            if lock is not None:
                with lock:
                    items = self._pending_texture_queue
                    self._pending_texture_queue = []
            else:
                items = self._pending_texture_queue
                self._pending_texture_queue = []
        except Exception:
            return
        done = 0
        pixels = 0
        idx = 0
        for abs_path, callback, img in items:
            try:
                w, h = img.size
            except Exception:
                w, h = 0, 0
            if done >= max_textures or pixels + w * h > max_pixels:
                break
            try:
                import_settings = TextureImportSettings.for_file(abs_path)
                tex = self._ctx.texture(img.size, 4, img.tobytes())
                import_settings.apply_to_texture(tex)
                if os.path.basename(abs_path) == "prototype_texture.png":
                    try:
                        tex.repeat_x = True
                        tex.repeat_y = True
                    except Exception:
                        pass
                import_mtime = TextureImportSettings.import_mtime(abs_path)
                try:
                    old = self._texture_cache.get(abs_path)
                    if old is not None:
                        try:
                            old[1].release()
                        except Exception:
                            pass
                except Exception:
                    pass
                self._texture_cache[abs_path] = (import_mtime, tex)
                try:
                    self._tex_mtime_checked[abs_path] = time.monotonic()
                except Exception:
                    pass
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(tex)
                except Exception:
                    pass
            except Exception:
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
            done += 1
            pixels += w * h
            idx += 1
        if idx < len(items):
            try:
                rest = items[idx:]
                lock = self._async_lock
                if lock is not None:
                    with lock:
                        self._pending_texture_queue = rest + self._pending_texture_queue
                else:
                    self._pending_texture_queue = rest + self._pending_texture_queue
            except Exception:
                pass

