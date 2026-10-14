# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
from typing import Optional, Any
from core.assets.fontatlas import FontAtlas, request_font_atlas
from core.components.rendering.renderers.text_renderer import TextFilter
class TextAtlasMixin:
    def _tex_lock_ensure(self):
        try:
            if self._tex_lock is None:
                import threading
                self._tex_lock = threading.Lock()
            return self._tex_lock
        except Exception:
            return None
    def get_or_create_atlas(self, font_path: str, base_size: int = 128) -> Optional[FontAtlas]:
        key = (font_path, base_size)
        try:
            hit = self._font_atlases.get(key)
        except Exception:
            hit = None
        if hit is not None:
            try:
                self._font_atlases.move_to_end(key)
            except Exception:
                pass
            return hit
        if not font_path:
            return None
        atlas = request_font_atlas(font_path, base_size)
        if atlas is not None:
            try:
                self._font_atlases[key] = atlas
            except Exception:
                return atlas
            self._evict_atlases_if_needed()
        return atlas
    def _evict_atlases_if_needed(self) -> None:
        while len(self._font_atlases) > self._max_atlases:
            old_key, _old_atlas = self._font_atlases.popitem(last=False)
            tex = self._tex_cache.pop(old_key, None)
            if tex is not None:
                try:
                    tex.release()
                except Exception:
                    pass
    def _get_atlas(self, font_path: str, base_size: int = 128) -> Optional[FontAtlas]:
        return self.get_or_create_atlas(font_path, base_size)
    def _atlas_rgba_job(alpha, w: int, h: int):
        try:
            import numpy as _np
            rgba = _np.empty((h, w, 4), dtype=_np.uint8)
            rgba[:, :, 3] = alpha
            rgba[:, :, 0:3] = 255
            return rgba.tobytes(), int(w), int(h)
        except Exception:
            return None
    def _on_atlas_rgba_done(self, key, epoch: int, atlas, fut):
        try:
            res = fut.result()
        except Exception:
            res = None
        try:
            lock = self._tex_lock_ensure()
            if lock is not None:
                with lock:
                    self._tex_ready.append((key, epoch, atlas, res))
            else:
                self._tex_ready.append((key, epoch, atlas, res))
        except Exception:
            pass
    def _drain_atlas_uploads(self):
        try:
            lock = self._tex_lock_ensure()
            if lock is not None:
                with lock:
                    if not self._tex_ready:
                        return
                    batch = self._tex_ready
                    self._tex_ready = []
            else:
                if not self._tex_ready:
                    return
                batch = self._tex_ready
                self._tex_ready = []
        except Exception:
            return
        done = 0
        rest: list = []
        for entry in batch:
            try:
                key, epoch, atlas, res = entry
            except Exception:
                continue
            try:
                self._tex_pending.pop(key, None)
            except Exception:
                pass
            if epoch != self._tex_epoch:
                continue
            if res is None:
                continue
            if done >= 1:
                rest.append(entry)
                try:
                    self._tex_pending[key] = True
                except Exception:
                    pass
                continue
            try:
                data, w, h = res
            except Exception:
                continue
            try:
                tex = self._ctx.texture((w, h), 4, data)
            except Exception:
                continue
            try:
                tex.repeat_x = False
                tex.repeat_y = False
            except Exception:
                pass
            try:
                old = self._tex_cache.get(key)
                if old is not None and old is not tex:
                    try:
                        old.release()
                    except Exception:
                        pass
                self._tex_cache[key] = tex
                self._evict_tex_if_needed()
            except Exception:
                pass
            try:
                self._apply_tex_state(key, tex)
            except Exception:
                pass
            try:
                atlas.release_source_images()
            except Exception:
                pass
            done += 1
        if rest:
            try:
                lock = self._tex_lock_ensure()
                if lock is not None:
                    with lock:
                        self._tex_ready = rest + self._tex_ready
                else:
                    self._tex_ready = rest + self._tex_ready
            except Exception:
                pass
    def _evict_tex_if_needed(self):
        try:
            cache = self._tex_cache
            while len(cache) > self._max_tex_cached:
                old_key = next(iter(cache))
                tex = cache.pop(old_key, None)
                try:
                    self._tex_applied.pop(old_key, None)
                    self._tex_mipped.discard(old_key)
                    self._tex_want.pop(old_key, None)
                except Exception:
                    pass
                if tex is not None:
                    try:
                        tex.release()
                    except Exception:
                        pass
        except Exception:
            pass
    def _apply_tex_state(self, key, tex) -> None:
        try:
            want = self._tex_want.get(key)
        except Exception:
            want = None
        if want is None:
            return
        try:
            filter_mode, aniso, mip_needed = want
        except Exception:
            return
        _FILTER_MAP = {
            TextFilter.NEAREST: (moderngl.NEAREST, moderngl.NEAREST),
            TextFilter.LINEAR: (moderngl.LINEAR, moderngl.LINEAR),
            TextFilter.TRILINEAR: (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR),
        }
        try:
            applied = self._tex_applied.get(key)
        except Exception:
            applied = None
        if applied != (filter_mode, float(aniso)):
            try:
                tex.filter = _FILTER_MAP.get(filter_mode, (moderngl.LINEAR, moderngl.LINEAR))
                if aniso and float(aniso) > 0:
                    tex.anisotropy = float(aniso)
                self._tex_applied[key] = (filter_mode, float(aniso))
            except Exception:
                pass
        if mip_needed:
            try:
                if key not in self._tex_mipped:
                    tex.build_mipmaps()
                    self._tex_mipped.add(key)
            except Exception:
                pass
    def _ensure_texture(self, atlas: FontAtlas, filter_mode: TextFilter = TextFilter.LINEAR, anisotropy: float = 0.0) -> Any:
        try:
            key = (atlas.font_path, atlas.base_size)
        except Exception:
            return None
        try:
            aniso_f = float(anisotropy) if anisotropy else 0.0
        except Exception:
            aniso_f = 0.0
        try:
            mip_needed = filter_mode == TextFilter.TRILINEAR
        except Exception:
            mip_needed = False
        try:
            prev = self._tex_want.get(key)
            prev_mip = bool(prev[2]) if prev else False
        except Exception:
            prev_mip = False
        try:
            self._tex_want[key] = (filter_mode, aniso_f, prev_mip or mip_needed)
        except Exception:
            pass
        try:
            tex = self._tex_cache.get(key)
        except Exception:
            tex = None
        if tex is not None:
            try:
                self._apply_tex_state(key, tex)
            except Exception:
                pass
            return tex
        try:
            if self._tex_pending.get(key):
                return None
        except Exception:
            pass
        try:
            alpha = atlas.alpha
            w = int(atlas.texture_width)
            h = int(atlas.texture_height)
        except Exception:
            return None
        if alpha is None or w <= 0 or h <= 0:
            return None
        try:
            from core.ecs.pool import asset as _asset_pool
            pool = _asset_pool()
        except Exception:
            pool = None
        if pool is None:
            return self._ensure_texture_sync(atlas, key)
        try:
            self._tex_pending[key] = True
        except Exception:
            pass
        try:
            epoch = self._tex_epoch
            fut = pool.submit(type(self)._atlas_rgba_job, alpha, w, h)
            try:
                fut.add_done_callback(
                    lambda f, k=key, e=epoch, a=atlas:
                    self._on_atlas_rgba_done(k, e, a, f))
            except Exception:
                try:
                    self._tex_pending.pop(key, None)
                except Exception:
                    pass
                return self._ensure_texture_sync(atlas, key)
            return None
        except Exception:
            try:
                self._tex_pending.pop(key, None)
            except Exception:
                pass
            return self._ensure_texture_sync(atlas, key)
    def _ensure_texture_sync(self, atlas: FontAtlas, key) -> Any:
        try:
            alpha = atlas.alpha
            w = int(atlas.texture_width)
            h = int(atlas.texture_height)
        except Exception:
            return None
        if alpha is None or w <= 0 or h <= 0:
            return None
        res = type(self)._atlas_rgba_job(alpha, w, h)
        if res is None:
            return None
        try:
            data, w, h = res
            tex = self._ctx.texture((w, h), 4, data)
        except Exception:
            return None
        try:
            tex.repeat_x = False
            tex.repeat_y = False
        except Exception:
            pass
        try:
            old = self._tex_cache.get(key)
            if old is not None and old is not tex:
                try:
                    old.release()
                except Exception:
                    pass
            self._tex_cache[key] = tex
            self._evict_tex_if_needed()
            self._apply_tex_state(key, tex)
        except Exception:
            pass
        try:
            atlas.release_source_images()
        except Exception:
            pass
        return tex
    def release(self):
        try:
            self._tex_epoch += 1
        except Exception:
            pass
        try:
            lock = self._tex_lock_ensure()
            if lock is not None:
                with lock:
                    self._tex_ready = []
            else:
                self._tex_ready = []
        except Exception:
            pass
        try:
            self._tex_pending.clear()
        except Exception:
            pass
        for tex in self._tex_cache.values():
            try:
                tex.release()
            except Exception:
                pass
        try:
            self._tex_cache.clear()
            self._tex_applied.clear()
            self._tex_mipped.clear()
            self._tex_want.clear()
            self._part_key = None
            self._part_world = []
            self._part_screen = []
            self._rq_color = None
            self._rq_tex = None
            self._rq_solid = None
            self._rq_clip = None
            self._rq_offset = None
        except Exception:
            pass
        if self._vao:
            try:
                self._vao.release()
            except Exception:
                pass
        if self._vbo:
            try:
                self._vbo.release()
            except Exception:
                pass
        if self._ibo:
            try:
                self._ibo.release()
            except Exception:
                pass
