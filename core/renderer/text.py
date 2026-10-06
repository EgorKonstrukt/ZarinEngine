# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional, Any
from collections import OrderedDict
from core.maths.math3d import Mat4
from core.components.rendering.renderers.text_renderer import TextRenderer, TextAlign, TextFilter

from core.assets.font_atlas import FontAtlas, request_font_atlas


_ZERO3 = np.array([0.0, 0.0, 0.0], dtype=np.float32)


class TextRendererGL:
    def __init__(self, ctx: moderngl.Context, prog: moderngl.Program):
        self._ctx = ctx
        self._prog = prog
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._max_chars: int = 4096
        self._font_atlases: "OrderedDict[tuple[str, int], FontAtlas]" = OrderedDict()
        self._tex_cache: dict[tuple[str, int], Any] = {}
        self._tex_applied: dict = {}
        self._tex_mipped: set = set()
        self._tex_want: dict = {}
        self._max_atlases: int = 4
        self._max_tex_cached: int = 64
        self._verts: Optional[np.ndarray] = None
        self._geom_cache: dict[int, tuple] = {}
        self._rich_seg_info: list[dict] = []
        self._part_key = None
        self._part_world: list = []
        self._part_screen: list = []
        self._rq_color = None
        self._rq_tex = None
        self._rq_solid = None
        self._rq_clip = None
        self._rq_offset = None
        self._tex_pending: dict = {}
        self._tex_ready: list = []
        self._tex_lock = None
        self._tex_epoch = 0
        self._cull_vp = None
        self._cull_p00 = 0.0
        self._cull_p11 = 0.0
        self._build_buffers()

    def _tex_lock_ensure(self):
        try:
            if self._tex_lock is None:
                import threading
                self._tex_lock = threading.Lock()
            return self._tex_lock
        except Exception:
            return None

    def _quad_indices(self, count: int) -> np.ndarray:
        qv = np.arange(count, dtype=np.uint32)
        base = qv * np.uint32(4)
        new_indices = np.empty(count * 6, dtype=np.uint32)
        new_indices[0::6] = base
        new_indices[1::6] = base + 1
        new_indices[2::6] = base + 2
        new_indices[3::6] = base
        new_indices[4::6] = base + 2
        new_indices[5::6] = base + 3
        return new_indices

    def _ensure_capacity(self, needed_chars: int):
        if needed_chars <= self._max_chars:
            return
        new_max = 1
        while new_max < needed_chars:
            new_max <<= 1
        new_verts = np.zeros(new_max * 20, dtype=np.float32)
        old_len = self._max_chars * 20
        try:
            new_verts[:old_len] = self._verts[:old_len]
        except Exception:
            pass
        self._verts = new_verts
        new_indices = self._quad_indices(new_max)
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
        if self._vao:
            try:
                self._vao.release()
            except Exception:
                pass
        self._vbo = self._ctx.buffer(self._verts.tobytes(), dynamic=True)
        self._ibo = self._ctx.buffer(new_indices.tobytes())
        self._vao = self._ctx.vertex_array(
            self._prog,
            [(self._vbo, "3f 2f", "in_position", "in_uv")],
            self._ibo
        )
        self._max_chars = new_max

    def _build_buffers(self):
        max_verts = self._max_chars * 4
        self._verts = np.zeros(max_verts * 5, dtype=np.float32)
        indices = self._quad_indices(self._max_chars)
        self._vbo = self._ctx.buffer(self._verts.tobytes(), dynamic=True)
        self._ibo = self._ctx.buffer(indices.tobytes())
        self._vao = self._ctx.vertex_array(
            self._prog,
            [(self._vbo, "3f 2f", "in_position", "in_uv")],
            self._ibo
        )

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
            fut = pool.submit(TextRendererGL._atlas_rgba_job, alpha, w, h)
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
        res = TextRendererGL._atlas_rgba_job(alpha, w, h)
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

    def _build_line_quads(self, atlas: FontAtlas, text: str, scale: float, pen_x: float, pen_y: float, verts: np.ndarray, base_idx: int, italic: bool = False, z_offset: float = 0.0, bold: bool = False) -> tuple[int, float]:
        if not text:
            return 0, 0.0
        codes = np.frombuffer(text.encode('utf-32-le'), dtype=np.uint32)
        oob = codes >= atlas.max_cp
        if np.any(oob):
            codes = codes.copy()
            codes[oob] = 0
        advances = atlas._gp_advance[codes] * scale
        bw = atlas._gp_bearing_x[codes] * scale
        bh = atlas._gp_bearing_y[codes] * scale
        gw = atlas._gp_glyph_w[codes] * scale
        gh = atlas._gp_glyph_h[codes] * scale
        valid = (gw > 0) & (gh > 0) & ~oob
        vi = np.where(valid)[0]
        n = len(vi)
        total_adv = float(np.sum(advances))
        if n == 0:
            return 0, total_adv
        max_floats = len(verts)
        space_left = max_floats - base_idx
        max_n = space_left // 20
        if max_n <= 0:
            return 0, total_adv
        if n > max_n:
            n = max_n
            vi = vi[:n]
        cum = np.cumsum(advances) - advances
        ascent = atlas.ascender
        top_base = pen_y + ascent * scale
        l = pen_x + cum + bw
        r = l + gw
        t = top_base - bh
        b = t - gh
        skew = 0.25 if italic else 0.0
        sh = skew * (t - pen_y)
        uv_arr = atlas._gp_uv_bold if bold else atlas._gp_uv
        u0 = uv_arr[codes, 0]
        v0 = uv_arr[codes, 1]
        u1 = uv_arr[codes, 2]
        v1 = uv_arr[codes, 3]
        idx = vi
        e = base_idx + n * 20
        verts[base_idx + 0:e:20] = l[idx]
        verts[base_idx + 1:e:20] = b[idx]
        verts[base_idx + 2:e:20] = z_offset
        verts[base_idx + 3:e:20] = u0[idx]
        verts[base_idx + 4:e:20] = v1[idx]
        verts[base_idx + 5:e:20] = r[idx]
        verts[base_idx + 6:e:20] = b[idx]
        verts[base_idx + 7:e:20] = z_offset
        verts[base_idx + 8:e:20] = u1[idx]
        verts[base_idx + 9:e:20] = v1[idx]
        verts[base_idx + 10:e:20] = r[idx] + sh[idx]
        verts[base_idx + 11:e:20] = t[idx]
        verts[base_idx + 12:e:20] = z_offset
        verts[base_idx + 13:e:20] = u1[idx]
        verts[base_idx + 14:e:20] = v0[idx]
        verts[base_idx + 15:e:20] = l[idx] + sh[idx]
        verts[base_idx + 16:e:20] = t[idx]
        verts[base_idx + 17:e:20] = z_offset
        verts[base_idx + 18:e:20] = u0[idx]
        verts[base_idx + 19:e:20] = v0[idx]
        return n, total_adv

    def _build_effect_quads(self, atlas: FontAtlas, text: str, scale: float, pen_x: float, pen_y: float, verts: np.ndarray, base_idx: int, underline: bool, strikethrough: bool, z_offset: float = 0.0, total_w: float = 0.0) -> int:
        ascent = atlas.ascender
        descender = atlas.descender
        if total_w <= 0:
            return 0
        count = 0
        if underline:
            line_y = pen_y - descender * scale * 0.5
            thickness = scale * 4.0
            b = base_idx + count * 20
            verts[b + 0] = pen_x
            verts[b + 1] = line_y - thickness
            verts[b + 2] = z_offset
            verts[b + 3] = 0.0
            verts[b + 4] = 0.0
            verts[b + 5] = pen_x + total_w
            verts[b + 6] = line_y - thickness
            verts[b + 7] = z_offset
            verts[b + 8] = 0.0
            verts[b + 9] = 0.0
            verts[b + 10] = pen_x + total_w
            verts[b + 11] = line_y + thickness
            verts[b + 12] = z_offset
            verts[b + 13] = 0.0
            verts[b + 14] = 0.0
            verts[b + 15] = pen_x
            verts[b + 16] = line_y + thickness
            verts[b + 17] = z_offset
            verts[b + 18] = 0.0
            verts[b + 19] = 0.0
            count += 1
        if strikethrough:
            line_y = pen_y + ascent * scale * 0.35
            thickness = scale * 3.0
            b = base_idx + count * 20
            verts[b + 0] = pen_x
            verts[b + 1] = line_y - thickness
            verts[b + 2] = z_offset
            verts[b + 3] = 0.0
            verts[b + 4] = 0.0
            verts[b + 5] = pen_x + total_w
            verts[b + 6] = line_y - thickness
            verts[b + 7] = z_offset
            verts[b + 8] = 0.0
            verts[b + 9] = 0.0
            verts[b + 10] = pen_x + total_w
            verts[b + 11] = line_y + thickness
            verts[b + 12] = z_offset
            verts[b + 13] = 0.0
            verts[b + 14] = 0.0
            verts[b + 15] = pen_x
            verts[b + 16] = line_y + thickness
            verts[b + 17] = z_offset
            verts[b + 18] = 0.0
            verts[b + 19] = 0.0
            count += 1
        return count

    def _render_quads(self, vi: int, color, tex: Any, write_depth: bool, solid: bool, start_v: int = 0, clip_alpha: float = 0.01):
        prog = self._prog
        if vi == 0:
            return
        if tex is None:
            return
        names = getattr(self, "_prog_names", None)
        if names is None or getattr(self, "_prog_id", None) is not id(prog):
            names = frozenset(prog)
            self._prog_names = names
            self._prog_id = id(prog)
        try:
            if len(color) > 3:
                ckey = (float(color[0]), float(color[1]), float(color[2]), float(color[3]))
            else:
                ckey = (float(color[0]), float(color[1]), float(color[2]), 1.0)
        except Exception:
            ckey = None
        if "u_color" in names:
            if ckey is not None and ckey == self._rq_color:
                pass
            else:
                try:
                    prog["u_color"].write(np.array(ckey if ckey is not None else color, dtype=np.float32).tobytes())
                except Exception:
                    try:
                        prog["u_color"].write(np.array(color, dtype=np.float32).tobytes())
                    except Exception:
                        pass
                self._rq_color = ckey
        try:
            skey = 1.0 if solid else 0.0
        except Exception:
            skey = 0.0
        if "u_solid" in names and skey != self._rq_solid:
            try:
                prog["u_solid"].value = skey
            except Exception:
                pass
            self._rq_solid = skey
        try:
            akey = float(clip_alpha)
        except Exception:
            akey = 0.01
        if "u_clip_alpha" in names and akey != self._rq_clip:
            try:
                prog["u_clip_alpha"].value = akey
            except Exception:
                pass
            self._rq_clip = akey
        try:
            tid = id(tex)
        except Exception:
            tid = None
        if tid != self._rq_tex:
            try:
                tex.use(0)
            except Exception:
                return
            if "u_texture" in names:
                try:
                    prog["u_texture"].value = 0
                except Exception:
                    pass
            self._rq_tex = tid
        try:
            self._vao.render(moderngl.TRIANGLES, vertices=vi * 6, first=start_v * 6)
        except Exception:
            pass

    def _geom_hash(self, tr: TextRenderer, atlas: FontAtlas) -> int:
        props = (
            tr.text, tr.font_path, tr.font_size, tuple(tr.color),
            tr.font_world_space, tr.billboard, tr.alignment, tr.line_spacing,
            tr.italic, tr.underline, tr.strikethrough,
            tr.shadow, tuple(tr.shadow_offset), tuple(tr.shadow_color),
            tr.use_3d, tr.extrusion_depth, tr.extrusion_layers,
            tuple(tr.extrusion_color), tr.atlas_resolution, tr.bold,
            tr.use_rich_text, atlas.font_path, atlas.base_size,
        )
        return hash(props)

    def _local_bounds(self, verts: np.ndarray, total: int):
        try:
            if total <= 0:
                return (0.0, 0.0, 0.0)
            n = total * 20
            xs = verts[0:n:5]
            ys = verts[1:n:5]
            mnx = float(np.min(xs))
            mxx = float(np.max(xs))
            mny = float(np.min(ys))
            mxy = float(np.max(ys))
            cx = (mnx + mxx) * 0.5
            cy = (mny + mxy) * 0.5
            dx = (mxx - mnx) * 0.5
            dy = (mxy - mny) * 0.5
            return (cx, cy, float(np.sqrt(dx * dx + dy * dy)))
        except Exception:
            return (0.0, 0.0, 0.0)

    def _text_visible(self, wm_d, cx: float, cy: float, r: float, pad: float) -> bool:
        try:
            vp = self._cull_vp
            if vp is None:
                return True
            p00 = self._cull_p00
            p11 = self._cull_p11
            r0x = float(wm_d[0][0])
            r0y = float(wm_d[0][1])
            r0z = float(wm_d[0][2])
            r1x = float(wm_d[1][0])
            r1y = float(wm_d[1][1])
            r1z = float(wm_d[1][2])
            r2x = float(wm_d[2][0])
            r2y = float(wm_d[2][1])
            r2z = float(wm_d[2][2])
            tx = float(wm_d[3][0])
            ty = float(wm_d[3][1])
            tz = float(wm_d[3][2])
            s0 = (r0x * r0x + r0y * r0y + r0z * r0z) ** 0.5
            s1 = (r1x * r1x + r1y * r1y + r1z * r1z) ** 0.5
            s2 = (r2x * r2x + r2y * r2y + r2z * r2z) ** 0.5
            s = s0
            if s1 > s:
                s = s1
            if s2 > s:
                s = s2
            if not s > 0.0:
                s = 1.0
            wx = cx * r0x + cy * r1x + tx
            wy = cx * r0y + cy * r1y + ty
            wz = cx * r0z + cy * r1z + tz
            c0 = wx * vp[0][0] + wy * vp[1][0] + wz * vp[2][0] + vp[3][0]
            c1 = wx * vp[0][1] + wy * vp[1][1] + wz * vp[2][1] + vp[3][1]
            c2 = wx * vp[0][2] + wy * vp[1][2] + wz * vp[2][2] + vp[3][2]
            c3 = wx * vp[0][3] + wy * vp[1][3] + wz * vp[2][3] + vp[3][3]
            if not c3 > 1e-6:
                return True
            wr = r * s + pad * s
            mx = wr * p00 / c3
            my = wr * p11 / c3
            nx = c0 / c3
            ny = c1 / c3
            return (-1.0 - mx <= nx <= 1.0 + mx) and (-1.0 - my <= ny <= 1.0 + my)
        except Exception:
            return True

    def _build_text_verts(self, tr: TextRenderer, atlas: FontAtlas):
        self._rich_seg_info.clear()
        inv_lh = atlas._inv_lh()
        scale = float(tr.font_size) * inv_lh * 0.01
        line_h = atlas.line_height * scale * tr.line_spacing
        verts = self._verts
        vi = 0
        evi = 0
        if tr.use_rich_text and tr._rich_segments:
            line_pieces: list[list[tuple[str, list[float], bool, bool, bool, bool]]] = [[]]
            for seg in tr._rich_segments:
                seg_lines = seg.text.split('\n')
                for i, piece in enumerate(seg_lines):
                    if i > 0:
                        line_pieces.append([])
                    if piece:
                        if not line_pieces:
                            line_pieces.append([])
                        line_pieces[-1].append((piece, seg.color, seg.bold, seg.italic, seg.underline, seg.strikethrough))
            if not line_pieces or not line_pieces[0]:
                return 0, 0, scale
            line_advs = []
            pen_y = 0.0
            vi = 0
            for pieces in line_pieces:
                pen_x = 0.0
                for piece_text, color, bold, italic, ul, st in pieces:
                    c, pw = self._build_line_quads(atlas, piece_text, scale, pen_x, pen_y, verts, vi * 20, italic, 0.0, bold)
                    if c > 0:
                        self._rich_seg_info.append({
                            'vi_start': vi, 'vi_count': c,
                            'evi_start': 0, 'evi_count': 0,
                            'color': color, 'bold': bold, 'italic': italic,
                            'underline': ul, 'strikethrough': st,
                            'width': pw,
                        })
                        vi += c
                        pen_x += pw
                line_advs.append(pen_x)
                pen_y -= line_h
            max_w = max(line_advs) if line_advs else 0.0
            seg_i = 0
            for line_idx, pieces in enumerate(line_pieces):
                if tr.alignment == TextAlign.LEFT:
                    off_x = 0.0
                elif tr.alignment == TextAlign.CENTER:
                    off_x = (max_w - line_advs[line_idx]) * 0.5
                elif tr.alignment == TextAlign.RIGHT:
                    off_x = max_w - line_advs[line_idx]
                else:
                    off_x = 0.0
                if off_x != 0.0:
                    for _ in pieces:
                        seg = self._rich_seg_info[seg_i]
                        s = seg['vi_start'] * 20
                        e = (seg['vi_start'] + seg['vi_count']) * 20
                        verts[s:e:5] -= off_x
                        seg_i += 1
                else:
                    seg_i += len(pieces)
            if vi > 0:
                xs = verts[0:vi * 20:5]
                ys = verts[1:vi * 20:5]
                x_mid = (float(np.min(xs)) + float(np.max(xs))) * 0.5
                y_mid = (float(np.min(ys)) + float(np.max(ys))) * 0.5
                verts[0:vi * 20:5] -= x_mid
                verts[1:vi * 20:5] -= y_mid
            pen_y = 0.0
            seg_effect_i = 0
            for line_idx, pieces in enumerate(line_pieces):
                for piece_text, color, bold, italic, ul, st in pieces:
                    if ul or st:
                        while (seg_effect_i < len(self._rich_seg_info) and
                               not (self._rich_seg_info[seg_effect_i]['underline'] or self._rich_seg_info[seg_effect_i]['strikethrough'])):
                            seg_effect_i += 1
                        if seg_effect_i < len(self._rich_seg_info):
                            seg_w = self._rich_seg_info[seg_effect_i]['width']
                            ec = self._build_effect_quads(atlas, piece_text, scale, 0.0, pen_y, verts, (vi + evi) * 20, ul, st, 0.0, seg_w)
                            self._rich_seg_info[seg_effect_i]['evi_start'] = evi
                            self._rich_seg_info[seg_effect_i]['evi_count'] = ec
                            seg_effect_i += 1
                            evi += ec
                pen_y -= line_h
            if evi > 0:
                es = vi * 20
                ee = (vi + evi) * 20
                xs = verts[es:ee:5]
                ys = verts[es + 1:ee:5]
                x_mid = (float(np.min(xs)) + float(np.max(xs))) * 0.5
                y_mid = (float(np.min(ys)) + float(np.max(ys))) * 0.5
                verts[es:ee:5] -= x_mid
                verts[es + 1:ee:5] -= y_mid
            return vi, evi, scale, self._local_bounds(verts, vi + evi)
        lines = tr.text.split("\n")
        line_start_idxs = [0]
        line_advs = []
        pen_y = 0.0
        for line in lines:
            c, adv = self._build_line_quads(atlas, line, scale, 0.0, pen_y, verts, vi * 20, tr.italic, 0.0, tr.bold)
            vi += c
            line_start_idxs.append(vi)
            line_advs.append(adv)
            pen_y -= line_h
        max_w = max(line_advs) if line_advs else 0.0
        for i in range(len(lines)):
            if tr.alignment == TextAlign.LEFT:
                off_x = 0.0
            elif tr.alignment == TextAlign.CENTER:
                off_x = (max_w - line_advs[i]) * 0.5
            elif tr.alignment == TextAlign.RIGHT:
                off_x = max_w - line_advs[i]
            else:
                off_x = 0.0
            if off_x != 0.0:
                s = line_start_idxs[i] * 20
                e = line_start_idxs[i + 1] * 20
                verts[s:e:5] -= off_x
        if vi > 0:
            xs = verts[0:vi * 20:5]
            ys = verts[1:vi * 20:5]
            x_mid = (float(np.min(xs)) + float(np.max(xs))) * 0.5
            y_mid = (float(np.min(ys)) + float(np.max(ys))) * 0.5
            verts[0:vi * 20:5] -= x_mid
            verts[1:vi * 20:5] -= y_mid
        need_effects = tr.underline or tr.strikethrough
        if need_effects:
            pen_y = 0.0
            e_start_idxs = [0]
            for i, line in enumerate(lines):
                evi += self._build_effect_quads(atlas, line, scale, 0.0, pen_y, verts, (vi + evi) * 20, tr.underline, tr.strikethrough, 0.0, line_advs[i])
                e_start_idxs.append(evi)
                pen_y -= line_h
            for i in range(len(lines)):
                if tr.alignment == TextAlign.LEFT:
                    off_x = 0.0
                elif tr.alignment == TextAlign.CENTER:
                    off_x = (max_w - line_advs[i]) * 0.5
                elif tr.alignment == TextAlign.RIGHT:
                    off_x = max_w - line_advs[i]
                else:
                    off_x = 0.0
                if off_x != 0.0:
                    s = vi * 20 + e_start_idxs[i] * 20
                    e = vi * 20 + e_start_idxs[i + 1] * 20
                    verts[s:e:5] -= off_x
            if evi > 0:
                es = vi * 20
                ee = (vi + evi) * 20
                xs = verts[es:ee:5]
                ys = verts[es + 1:ee:5]
                x_mid = (float(np.min(xs)) + float(np.max(xs))) * 0.5
                y_mid = (float(np.min(ys)) + float(np.max(ys))) * 0.5
                verts[es:ee:5] -= x_mid
                verts[es + 1:ee:5] -= y_mid
        return vi, evi, scale, self._local_bounds(verts, vi + evi)

    _OUTLINE_DIRS = [
        (1.0, 0.0), (0.9239, 0.3827), (0.7071, 0.7071), (0.3827, 0.9239),
        (0.0, 1.0), (-0.3827, 0.9239), (-0.7071, 0.7071), (-0.9239, 0.3827),
        (-1.0, 0.0), (-0.9239, -0.3827), (-0.7071, -0.7071), (-0.3827, -0.9239),
        (0.0, -1.0), (0.3827, -0.9239), (0.7071, -0.7071), (0.9239, -0.3827),
    ]

    _GLOW_RINGS = [
        (1.0, 0.5),
        (1.5, 0.3),
        (2.5, 0.15),
    ]

    def _write_offset(self, prog, names, x: float, y: float, z: float):
        try:
            key = (float(x), float(y), float(z))
        except Exception:
            return
        if key == self._rq_offset:
            return
        if "u_offset" in names:
            try:
                prog["u_offset"].write(np.array(key, dtype=np.float32).tobytes())
            except Exception:
                pass
        self._rq_offset = key

    def render(self, scene, view_mat: Mat4, proj_mat: Mat4, viewport_w: int, viewport_h: int, world_space_only: bool | None = None):
        if not self._prog or not self._vao:
            return
        try:
            self._drain_atlas_uploads()
        except Exception:
            pass
        try:
            if scene is None or not scene._component_indices.get("TextRenderer"):
                return
        except Exception:
            pass
        prog = self._prog
        try:
            view_f32 = view_mat.to_f32()
        except Exception:
            view_f32 = None
        try:
            proj_f32 = proj_mat.to_f32()
        except Exception:
            proj_f32 = None
        names = getattr(self, "_prog_names", None)
        if names is None or getattr(self, "_prog_id", None) is not id(prog):
            names = frozenset(prog)
            self._prog_names = names
            self._prog_id = id(prog)
        self._rq_color = None
        self._rq_tex = None
        self._rq_solid = None
        self._rq_clip = None
        self._rq_offset = None
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        try:
            self._ctx.depth_mask = False
        except Exception:
            pass
        if "u_view" in names and view_f32 is not None:
            try:
                prog["u_view"].write(view_f32.tobytes())
            except Exception:
                pass
        if "u_proj" in names and proj_f32 is not None:
            try:
                prog["u_proj"].write(proj_f32.tobytes())
            except Exception:
                pass
        if "u_viewport_size" in names:
            try:
                prog["u_viewport_size"].write(np.array([float(viewport_w), float(viewport_h)], dtype=np.float32).tobytes())
            except Exception:
                pass
        try:
            self._cull_vp = view_mat._d @ proj_mat._d
            self._cull_p00 = float(proj_mat._d[0, 0])
            self._cull_p11 = float(proj_mat._d[1, 1])
        except Exception:
            self._cull_vp = None
            self._cull_p00 = 0.0
            self._cull_p11 = 0.0
        try:
            skey = (id(scene), scene._render_version)
        except Exception:
            skey = None
        if skey is None or skey != self._part_key:
            _pw: list = []
            _ps: list = []
            try:
                for _e in scene.get_entities_with_component(TextRenderer):
                    try:
                        _tm = _e._type_map.get(TextRenderer)
                        _t0 = _tm[0] if _tm else None
                    except Exception:
                        _t0 = None
                    if _t0 is None:
                        continue
                    try:
                        _ws = bool(_t0.font_world_space)
                    except Exception:
                        _ws = True
                    if _ws:
                        _pw.append(_e)
                    else:
                        _ps.append(_e)
            except Exception:
                pass
            self._part_world = _pw
            self._part_screen = _ps
            self._part_key = skey
            try:
                _alive = set()
                for _e in _pw:
                    try:
                        _alive.add(_e.id)
                    except Exception:
                        pass
                for _e in _ps:
                    try:
                        _alive.add(_e.id)
                    except Exception:
                        pass
                for _eid in [k for k in self._geom_cache if k not in _alive]:
                    try:
                        del self._geom_cache[_eid]
                    except Exception:
                        pass
            except Exception:
                pass
        if world_space_only is None:
            _ents = self._part_world + self._part_screen
        elif world_space_only:
            _ents = self._part_world
        else:
            _ents = self._part_screen
        for ent in _ents:
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
                _tml = ent._type_map.get(TextRenderer)
                tr = _tml[0] if _tml else None
            except Exception:
                try:
                    tr = ent.get_component(TextRenderer)
                except Exception:
                    continue
            if tr is None:
                continue
            try:
                if not tr.enabled or not tr.text:
                    continue
            except Exception:
                continue
            if world_space_only is not None:
                try:
                    _is_ws = bool(tr.font_world_space)
                except Exception:
                    _is_ws = True
                if world_space_only and not _is_ws:
                    continue
                if not world_space_only and _is_ws:
                    continue
            try:
                t = ent._transform
                if t is None:
                    t = ent.transform
                if t is None:
                    continue
            except Exception:
                continue
            try:
                wm = t.world_matrix
            except Exception:
                continue
            try:
                atlas = self._get_atlas(tr.font_path, tr.atlas_resolution)
            except Exception:
                atlas = None
            if atlas is None:
                continue
            try:
                tex = self._ensure_texture(atlas, tr.filter_mode, tr.anisotropy)
            except Exception:
                tex = None
            if tex is None:
                continue
            try:
                self._ensure_capacity(len(tr.text))
            except Exception:
                pass
            try:
                model_f32 = wm.to_f32()
            except Exception:
                continue
            if "u_model" in names:
                try:
                    prog["u_model"].write(model_f32.tobytes())
                except Exception:
                    pass
            if "u_billboard" in names:
                try:
                    prog["u_billboard"].value = 1.0 if tr.billboard else 0.0
                except Exception:
                    pass
            if "u_screen_space" in names:
                try:
                    prog["u_screen_space"].value = 0.0 if tr.font_world_space else 1.0
                except Exception:
                    pass
            try:
                gh = self._geom_hash(tr, atlas)
            except Exception:
                continue
            try:
                eid = ent.id
            except Exception:
                eid = -1
            try:
                cached = self._geom_cache.get(eid)
            except Exception:
                cached = None
            if cached is not None and len(cached) >= 7 and cached[4] == gh:
                vi, evi, scale, vdata = cached[0], cached[1], cached[2], cached[3]
                try:
                    self._verts[:len(vdata)] = vdata
                except Exception:
                    continue
                try:
                    self._rich_seg_info = list(cached[5])
                except Exception:
                    self._rich_seg_info = []
                try:
                    bx, by, br = cached[6]
                except Exception:
                    bx, by, br = (0.0, 0.0, 0.0)
            else:
                try:
                    vi, evi, scale, bounds = self._build_text_verts(tr, atlas)
                except Exception:
                    continue
                try:
                    bx, by, br = bounds
                except Exception:
                    bx, by, br = (0.0, 0.0, 0.0)
                try:
                    self._geom_cache[eid] = (vi, evi, scale, self._verts[:(vi + evi) * 20].copy(), gh, self._rich_seg_info.copy(), (bx, by, br))
                except Exception:
                    pass
            if vi == 0 and evi == 0:
                continue
            try:
                _is_ws2 = bool(tr.font_world_space)
            except Exception:
                _is_ws2 = True
            if _is_ws2:
                try:
                    pad = 0.0
                    if tr.glow:
                        pad += float(tr.glow_size) * 2.5
                    if tr.outline:
                        pad += float(tr.outline_width)
                    if tr.shadow:
                        try:
                            sox = float(tr.shadow_offset[0])
                            soy = float(tr.shadow_offset[1])
                            pad += (sox * sox + soy * soy) ** 0.5
                        except Exception:
                            pass
                    if tr.use_3d:
                        pad += float(tr.extrusion_depth)
                    wm_d = wm._d
                except Exception:
                    wm_d = None
                    pad = 0.0
                if wm_d is not None:
                    try:
                        if not self._text_visible(wm_d, float(bx), float(by), float(br), float(pad)):
                            continue
                    except Exception:
                        pass
            try:
                total_verts = (vi + evi) * 4
                self._vbo.write(memoryview(self._verts[:total_verts * 5]))
            except Exception:
                try:
                    self._vbo.write(self._verts[:total_verts * 5].tobytes())
                except Exception:
                    continue
            ev = vi
            try:
                is_3d = tr.use_3d and tr.extrusion_layers > 0 and tr.extrusion_depth > 0
            except Exception:
                is_3d = False
            try:
                _sc = tr.shadow_color
                has_shadow = bool(tr.shadow) and float(_sc[3]) > 0
            except Exception:
                has_shadow = False
            try:
                _oc = tr.outline_color
                has_outline = bool(tr.outline) and not is_3d and float(_oc[3]) > 0
            except Exception:
                has_outline = False
            try:
                _gc0 = tr.glow_color
                has_glow = bool(tr.glow) and not is_3d and float(_gc0[3]) > 0
            except Exception:
                has_glow = False
            has_3d = is_3d
            clip_main = 0.05 if (has_outline or has_glow) else 0.01
            if tr.font_world_space:
                try:
                    self._ctx.enable(moderngl.DEPTH_TEST)
                except Exception:
                    pass
            else:
                try:
                    self._ctx.disable(moderngl.DEPTH_TEST)
                except Exception:
                    pass
            if has_shadow:
                try:
                    self._ctx.disable(moderngl.DEPTH_TEST)
                except Exception:
                    pass
                try:
                    sx, sy = tr.shadow_offset[0], tr.shadow_offset[1]
                except Exception:
                    sx, sy = 0.0, 0.0
                self._write_offset(prog, names, -float(sx), -float(sy), 0.0)
                if vi > 0:
                    self._render_quads(vi, tr.shadow_color, tex, False, False, 0)
                if evi > 0:
                    self._render_quads(evi, tr.shadow_color, tex, False, True, ev)
                self._write_offset(prog, names, 0.0, 0.0, 0.0)
                if tr.font_world_space:
                    try:
                        self._ctx.enable(moderngl.DEPTH_TEST)
                    except Exception:
                        pass
            write_depth = False
            if has_glow or has_outline:
                try:
                    self._ctx.disable(moderngl.DEPTH_TEST)
                except Exception:
                    pass
            if has_glow:
                gc = list(tr.glow_color)
                try:
                    base_intensity = float(gc[3]) * float(tr.glow_intensity)
                except Exception:
                    base_intensity = 0.0
                try:
                    glow_size = float(tr.glow_size)
                except Exception:
                    glow_size = 0.0
                for radius, alpha_scale in self._GLOW_RINGS:
                    r = glow_size * radius
                    a = base_intensity * alpha_scale
                    if a < 0.005:
                        continue
                    gc[3] = a
                    for dx, dy in self._OUTLINE_DIRS:
                        self._write_offset(prog, names, float(dx * r), float(dy * r), 0.0)
                        if vi > 0:
                            self._render_quads(vi, gc, tex, write_depth, False, 0)
                        if evi > 0:
                            self._render_quads(evi, gc, tex, write_depth, False, ev)
                    self._write_offset(prog, names, 0.0, 0.0, 0.0)
            if has_outline:
                oc = tr.outline_color
                try:
                    ow = float(tr.outline_width)
                except Exception:
                    ow = 0.0
                for dx, dy in self._OUTLINE_DIRS:
                    self._write_offset(prog, names, float(dx * ow), float(dy * ow), 0.0)
                    if vi > 0:
                        self._render_quads(vi, oc, tex, write_depth, False, 0)
                    if evi > 0:
                        self._render_quads(evi, oc, tex, write_depth, False, ev)
                self._write_offset(prog, names, 0.0, 0.0, 0.0)
            if has_glow or has_outline:
                if tr.font_world_space:
                    try:
                        self._ctx.enable(moderngl.DEPTH_TEST)
                    except Exception:
                        pass
            if has_3d:
                try:
                    layer_step = float(tr.extrusion_depth) / max(int(tr.extrusion_layers), 1)
                except Exception:
                    layer_step = 0.0
                for layer in range(int(tr.extrusion_layers), 0, -1):
                    z_off = layer * layer_step
                    try:
                        t_factor = 0.3 + 0.7 * (1.0 - layer / max(int(tr.extrusion_layers), 1))
                    except Exception:
                        t_factor = 1.0
                    try:
                        ecolor = [
                            tr.extrusion_color[0] * t_factor,
                            tr.extrusion_color[1] * t_factor,
                            tr.extrusion_color[2] * t_factor,
                            tr.color[3],
                        ]
                    except Exception:
                        continue
                    self._write_offset(prog, names, 0.0, 0.0, -float(z_off))
                    if vi > 0:
                        self._render_quads(vi, ecolor, tex, write_depth, False, 0)
                    if evi > 0:
                        self._render_quads(evi, ecolor, tex, write_depth, True, ev)
                self._write_offset(prog, names, 0.0, 0.0, 0.0)
                if vi > 0:
                    self._render_quads(vi, tr.color, tex, write_depth, False, 0, clip_main)
                if evi > 0:
                    self._render_quads(evi, tr.color, tex, write_depth, True, ev)
            elif self._rich_seg_info:
                for seg in self._rich_seg_info:
                    try:
                        seg_color = seg['color']
                        seg_vc = int(seg['vi_count'])
                    except Exception:
                        continue
                    if seg_vc > 0:
                        try:
                            seg_vs = int(seg['vi_start'])
                        except Exception:
                            seg_vs = 0
                        self._render_quads(seg_vc, seg_color, tex, write_depth, False, seg_vs, clip_main)
                    try:
                        seg_fx = bool(seg['underline'] or seg['strikethrough'])
                    except Exception:
                        seg_fx = False
                    if seg_fx:
                        try:
                            seg_ec = int(seg['evi_count'])
                            seg_es = int(seg['evi_start'])
                        except Exception:
                            seg_ec = 0
                            seg_es = 0
                        self._render_quads(seg_ec, seg_color, tex, write_depth, True, ev + seg_es)
            else:
                if vi > 0:
                    self._render_quads(vi, tr.color, tex, write_depth, False, 0, clip_main)
                if evi > 0:
                    self._render_quads(evi, tr.color, tex, write_depth, True, ev)
        try:
            self._ctx.depth_mask = True
        except Exception:
            pass
        try:
            self._ctx.enable(moderngl.CULL_FACE)
        except Exception:
            pass

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
