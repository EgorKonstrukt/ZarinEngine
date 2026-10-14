# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import time
from typing import Optional, Any
from core.assets.texture_import_settings import TextureImportSettings
from core.components.rendering.renderers.svg_renderer import SvgRenderer
_SVG_MAX_UPLOADS_PER_FRAME = 2
_SVG_MAX_PIXELS_PER_FRAME = 4 * 1024 * 1024
_SVG_CACHE_MAX_ENTRIES = 256
def _rasterize_svg_job(abs_path: str, pixels_per_unit: float, max_size: int):
    try:
        from PyQt6.QtGui import QImage, QPainter
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QRectF
    except Exception:
        return None
    try:
        t0 = time.perf_counter()
        renderer = QSvgRenderer(abs_path)
        if not renderer.isValid():
            return None
        ds = renderer.defaultSize()
        if ds.isValid() and ds.width() > 0 and ds.height() > 0:
            longest = max(ds.width(), ds.height())
            tex_size = max(int(pixels_per_unit), 16)
            w = max(1, int(ds.width() * tex_size / longest))
            h = max(1, int(ds.height() * tex_size / longest))
        else:
            w = h = max(int(pixels_per_unit), 16)
        if max_size > 0 and max(w, h) > max_size:
            scale = max_size / max(w, h)
            w = max(1, int(w * scale))
            h = max(1, int(h * scale))
        img = QImage(w, h, QImage.Format.Format_RGBA8888)
        img.fill(0)
        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(p, QRectF(0.0, 0.0, float(w), float(h)))
        finally:
            try:
                p.end()
            except Exception:
                pass
        data = bytes(img.constBits().asstring(w * h * 4))
        ms = (time.perf_counter() - t0) * 1000.0
        return (data, w, h, ms)
    except Exception:
        return None
class SvgParseMixin:
    def _resolve_path(self, path: str) -> Optional[str]:
        if not path:
            return None
        cached = self._path_cache.get(path)
        if cached is not None:
            return cached
        abs_path: Optional[str] = None
        if os.path.exists(path):
            abs_path = os.path.abspath(path)
        elif not os.path.isabs(path):
            candidate = os.path.join(os.getcwd(), path)
            if os.path.exists(candidate):
                abs_path = candidate
            else:
                from core.engine.eng import Engine
                eng = Engine.instance()
                root = eng.project_root if eng and eng.project_root else os.getcwd()
                candidate = os.path.normpath(os.path.join(root, path))
                if os.path.exists(candidate):
                    abs_path = candidate
        self._path_cache[path] = abs_path
        return abs_path
    def _evict_if_needed(self):
        try:
            cache = self._texture_cache
            if len(cache) <= _SVG_CACHE_MAX_ENTRIES:
                return
            for key in list(cache.keys()):
                if len(cache) <= _SVG_CACHE_MAX_ENTRIES:
                    break
                entry = cache.pop(key, None)
                if entry is not None and len(entry) >= 3 and entry[2] is not None:
                    try:
                        entry[2].release()
                    except Exception:
                        pass
        except Exception:
            pass
    def _upload_raster(self, abs_path: str, pixels_per_unit: float, mtime: float, import_mtime: float, res) -> Optional[Any]:
        key = (abs_path, pixels_per_unit)
        if res is None:
            try:
                self._texture_cache[key] = (mtime, pixels_per_unit, None, import_mtime)
            except Exception:
                pass
            return None
        try:
            data, w, h, _ms = res
        except Exception:
            return None
        try:
            import_settings = TextureImportSettings.for_file(abs_path)
        except Exception:
            import_settings = None
        try:
            tex = self._ctx.texture((w, h), 4, data)
        except Exception:
            return None
        try:
            if import_settings is not None:
                import_settings.apply_to_texture(tex)
        except Exception:
            pass
        try:
            old = self._texture_cache.get(key)
            if old is not None and len(old) >= 3 and old[2] is not None and old[2] is not tex:
                try:
                    old[2].release()
                except Exception:
                    pass
            self._texture_cache[key] = (mtime, pixels_per_unit, tex, import_mtime)
            self._evict_if_needed()
        except Exception:
            pass
        return tex
    def _on_raster_done(self, key, epoch: int, mtime: float, import_mtime: float, fut):
        try:
            res = fut.result()
        except Exception:
            res = None
        try:
            ms = float(res[3]) if res is not None else 0.0
        except Exception:
            ms = 0.0
        try:
            self._svg_stats["last_raster_ms"] = ms
            self._svg_stats["rastered"] = int(self._svg_stats.get("rastered", 0)) + 1
        except Exception:
            pass
        try:
            with self._pending_lock:
                self._pending_uploads.append((key, epoch, mtime, import_mtime, res))
                try:
                    self._svg_stats["pending"] = len(self._pending_uploads)
                except Exception:
                    pass
        except Exception:
            pass
    def _drain_uploads(self):
        try:
            with self._pending_lock:
                if not self._pending_uploads:
                    try:
                        self._svg_stats["pending"] = 0
                        self._svg_stats["inflight"] = len(self._inflight)
                    except Exception:
                        pass
                    return
                batch = self._pending_uploads
                self._pending_uploads = []
        except Exception:
            return
        uploads = 0
        pixels = 0
        rest: list = []
        try:
            self._svg_stats["pending"] = 0
        except Exception:
            pass
        for entry in batch:
            try:
                key, epoch, mtime, import_mtime, res = entry
            except Exception:
                continue
            try:
                self._inflight.discard(key)
            except Exception:
                pass
            if epoch != self._raster_epoch:
                continue
            if res is not None:
                try:
                    _data, w, h, _ms = res
                    if uploads >= _SVG_MAX_UPLOADS_PER_FRAME or pixels + w * h > _SVG_MAX_PIXELS_PER_FRAME:
                        rest.append(entry)
                        try:
                            self._inflight.add(key)
                        except Exception:
                            pass
                        continue
                except Exception:
                    pass
            else:
                w = h = 0
            try:
                cur_mtime = os.path.getmtime(key[0])
            except OSError:
                cur_mtime = 0.0
            except Exception:
                cur_mtime = mtime
            if abs(cur_mtime - mtime) > 0.001:
                continue
            self._upload_raster(key[0], key[1], mtime, import_mtime, res)
            uploads += 1
            try:
                pixels += w * h
            except Exception:
                pass
        if rest:
            try:
                with self._pending_lock:
                    self._pending_uploads = rest + self._pending_uploads
            except Exception:
                pass
        try:
            self._svg_stats["inflight"] = len(self._inflight)
        except Exception:
            pass
    def _request_raster(self, abs_path: str, pixels_per_unit: float, max_size: int, mtime: float, import_mtime: float) -> bool:
        key = (abs_path, pixels_per_unit)
        try:
            if key in self._inflight:
                return False
        except Exception:
            pass
        try:
            from core.ecs.pool import asset as _asset_pool
            pool = _asset_pool()
        except Exception:
            pool = None
        if pool is None:
            return False
        try:
            self._inflight.add(key)
        except Exception:
            pass
        try:
            epoch = self._raster_epoch
            fut = pool.submit(_rasterize_svg_job, abs_path, pixels_per_unit, max_size)
            try:
                fut.add_done_callback(lambda f, k=key, e=epoch, m=mtime, im=import_mtime: self._on_raster_done(k, e, m, im, f))
            except Exception:
                try:
                    self._inflight.discard(key)
                except Exception:
                    pass
                return False
            try:
                self._svg_stats["inflight"] = len(self._inflight)
            except Exception:
                pass
            return True
        except Exception:
            try:
                self._inflight.discard(key)
            except Exception:
                pass
            return False
    def _get_texture_async(self, abs_path: str, pixels_per_unit: float) -> Optional[Any]:
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            mtime = 0.0
        except Exception:
            mtime = 0.0
        try:
            import_mtime = TextureImportSettings.import_mtime(abs_path)
        except Exception:
            import_mtime = 0.0
        key = (abs_path, pixels_per_unit)
        try:
            cached = self._texture_cache.get(key)
        except Exception:
            cached = None
        if cached is not None and len(cached) >= 4 and cached[0] == mtime and cached[3] == import_mtime:
            return cached[2]
        try:
            max_size = TextureImportSettings.for_file(abs_path).max_size
        except Exception:
            max_size = 2048
        try:
            max_size = int(max_size)
        except Exception:
            max_size = 2048
        if self._request_raster(abs_path, pixels_per_unit, max_size, mtime, import_mtime):
            return None
        return self._get_texture(abs_path, pixels_per_unit)
    def _get_texture(self, abs_path: str, pixels_per_unit: float) -> Optional[Any]:
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            mtime = 0.0
        except Exception:
            mtime = 0.0
        try:
            import_mtime = TextureImportSettings.import_mtime(abs_path)
        except Exception:
            import_mtime = 0.0
        key = (abs_path, pixels_per_unit)
        try:
            cached = self._texture_cache.get(key)
        except Exception:
            cached = None
        if cached is not None and len(cached) >= 4 and cached[0] == mtime and cached[3] == import_mtime:
            return cached[2]
        try:
            max_size = int(TextureImportSettings.for_file(abs_path).max_size)
        except Exception:
            max_size = 2048
        res = _rasterize_svg_job(abs_path, pixels_per_unit, max_size)
        return self._upload_raster(abs_path, pixels_per_unit, mtime, import_mtime, res)
    def svg_stats(self) -> dict:
        try:
            return dict(self._svg_stats)
        except Exception:
            return {}
    def resolve_path(self, path: str) -> Optional[str]:
        return self._resolve_path(path)
    def _collect_scene_items(self, scene) -> list:
        from core.renderer.render_items import _SvgItem
        out: list = []
        try:
            append = out.append
            for ent in scene.get_entities_with_component(SvgRenderer):
                try:
                    if not ent._active:
                        continue
                except Exception:
                    try:
                        if not ent.active:
                            continue
                    except Exception:
                        continue
                try:
                    tm = ent._type_map.get(SvgRenderer)
                    sr = tm[0] if tm else None
                except Exception:
                    try:
                        sr = ent.get_component(SvgRenderer)
                    except Exception:
                        continue
                if sr is None:
                    continue
                try:
                    if not sr.enabled:
                        continue
                except Exception:
                    continue
                try:
                    tr = ent._transform
                    if tr is None:
                        tr = ent.transform
                    if tr is None:
                        continue
                except Exception:
                    continue
                abs_path = self._resolve_path(sr.svg_path)
                if not abs_path:
                    continue
                try:
                    ppu = float(sr.pixels_per_unit)
                except Exception:
                    continue
                try:
                    append(_SvgItem(tr.world_matrix, sr.color, sr.flip_x, sr.flip_y, abs_path, ppu, tr))
                except Exception:
                    continue
        except Exception:
            pass
        return out
