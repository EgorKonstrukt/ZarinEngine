# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
from core.assets.fontatlas import FontAtlas
from core.components.rendering.renderers.text_renderer import TextRenderer, TextAlign
class TextLayoutMixin:
    def _build_line_quads(self, atlas: FontAtlas, text: str, scale: float, pen_x: float, pen_y: float, verts: np.ndarray, base_idx: int, italic: bool = False, z_offset: float = 0.0, bold: bool = False) -> tuple[int, float]:
        if not text:
            return 0, 0.0
        codes = np.frombuffer(text.encode("utf-32-le"), dtype=np.uint32)
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
                seg_lines = seg.text.split("\n")
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
                            "vi_start": vi, "vi_count": c,
                            "evi_start": 0, "evi_count": 0,
                            "color": color, "bold": bold, "italic": italic,
                            "underline": ul, "strikethrough": st,
                            "width": pw,
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
                        s = seg["vi_start"] * 20
                        e = (seg["vi_start"] + seg["vi_count"]) * 20
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
                                not (self._rich_seg_info[seg_effect_i]["underline"] or self._rich_seg_info[seg_effect_i]["strikethrough"])):
                            seg_effect_i += 1
                        if seg_effect_i < len(self._rich_seg_info):
                            seg_w = self._rich_seg_info[seg_effect_i]["width"]
                            ec = self._build_effect_quads(atlas, piece_text, scale, 0.0, pen_y, verts, (vi + evi) * 20, ul, st, 0.0, seg_w)
                            self._rich_seg_info[seg_effect_i]["evi_start"] = evi
                            self._rich_seg_info[seg_effect_i]["evi_count"] = ec
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
