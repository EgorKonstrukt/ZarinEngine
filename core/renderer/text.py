from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional, Any
from core.math3d import Mat4
from core.components.rendering.text_renderer import TextRenderer, TextAlign
from core.components.transform import Transform
from core.font_atlas import FontAtlas


class TextRendererGL:
    def __init__(self, ctx: moderngl.Context, prog: moderngl.Program):
        self._ctx = ctx
        self._prog = prog
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._max_chars: int = 4096
        self._font_atlases: dict[tuple[str, int], FontAtlas] = {}
        self._tex_cache: dict[tuple[str, int], Any] = {}
        self._verts: Optional[np.ndarray] = None
        self._geom_cache: dict[int, tuple[int, int, float, np.ndarray, int]] = {}
        self._build_buffers()

    def _build_buffers(self):
        max_verts = self._max_chars * 4
        max_indices = self._max_chars * 6
        self._verts = np.zeros(max_verts * 5, dtype=np.float32)
        indices = np.zeros(max_indices, dtype=np.uint32)
        for i in range(self._max_chars):
            base = i * 4
            indices[i * 6 + 0] = base + 0
            indices[i * 6 + 1] = base + 1
            indices[i * 6 + 2] = base + 2
            indices[i * 6 + 3] = base + 0
            indices[i * 6 + 4] = base + 2
            indices[i * 6 + 5] = base + 3
        self._vbo = self._ctx.buffer(self._verts.tobytes(), dynamic=True)
        self._ibo = self._ctx.buffer(indices.tobytes())
        self._vao = self._ctx.vertex_array(
            self._prog,
            [(self._vbo, "3f 2f", "in_position", "in_uv")],
            self._ibo
        )

    def get_or_create_atlas(self, font_path: str, base_size: int = 128) -> Optional[FontAtlas]:
        key = (font_path, base_size)
        if key in self._font_atlases:
            return self._font_atlases[key]
        if not font_path:
            return None
        try:
            atlas = FontAtlas(font_path, base_size)
            self._font_atlases[key] = atlas
            return atlas
        except Exception:
            return None

    def _get_atlas(self, font_path: str, base_size: int = 128) -> Optional[FontAtlas]:
        return self.get_or_create_atlas(font_path, base_size)

    def _ensure_texture(self, atlas: FontAtlas) -> Any:
        key = (atlas.font_path, atlas.base_size)
        if key in self._tex_cache:
            return self._tex_cache[key]
        tex = self._ctx.texture((atlas.texture_width, atlas.texture_height), 4, atlas.texture.tobytes())
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex.repeat_x = False
        tex.repeat_y = False
        tex.build_mipmaps()
        self._tex_cache[key] = tex
        return tex

    def _build_line_quads(self, atlas: FontAtlas, text: str, scale: float, pen_x: float, pen_y: float, verts: np.ndarray, base_idx: int, italic: bool = False, z_offset: float = 0.0) -> tuple[int, float]:
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
        cum = np.cumsum(advances) - advances
        ascent = atlas.ascender
        top_base = pen_y + ascent * scale
        l = pen_x + cum + bw
        r = l + gw
        t = top_base - bh
        b = t - gh
        skew = 0.25 if italic else 0.0
        sh = skew * (t - pen_y)
        u0 = atlas._gp_uv[codes, 0]
        v0 = atlas._gp_uv[codes, 1]
        u1 = atlas._gp_uv[codes, 2]
        v1 = atlas._gp_uv[codes, 3]
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
            line_y = pen_y - descender * scale * 0.3
            thickness = scale * 0.08
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
            thickness = scale * 0.06
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

    def _render_quads(self, vi: int, color: list[float], tex: Any, write_depth: bool, solid: bool, start_v: int = 0):
        prog = self._prog
        if vi == 0:
            return
        if "u_color" in prog:
            prog["u_color"].write(np.array(color, dtype=np.float32).tobytes())
        if "u_solid" in prog:
            prog["u_solid"].value = 1.0 if solid else 0.0
        tex.use(0)
        if "u_texture" in prog:
            prog["u_texture"].value = 0
        if write_depth:
            self._ctx.depth_mask = True
        else:
            self._ctx.depth_mask = False
        self._vao.render(moderngl.TRIANGLES, vertices=vi * 6, first=start_v * 4)

    def _geom_hash(self, tr: TextRenderer, atlas: FontAtlas) -> int:
        props = (
            tr.text, tr.font_path, tr.font_size, tuple(tr.color),
            tr.font_world_space, tr.billboard, tr.alignment, tr.line_spacing,
            tr.italic, tr.underline, tr.strikethrough,
            tr.shadow, tuple(tr.shadow_offset), tuple(tuple(tr.shadow_color)),
            tr.use_3d, tr.extrusion_depth, tr.extrusion_layers,
            tuple(tuple(tr.extrusion_color)), tr.atlas_resolution, tr.bold,
            atlas.font_path, atlas.base_size,
        )
        return hash(props)

    def _build_text_verts(self, tr: TextRenderer, atlas: FontAtlas) -> tuple[int, int, float]:
        lines = tr.text.split("\n")
        inv_lh = atlas._inv_lh()
        scale = float(tr.font_size) * inv_lh * 0.01
        line_h = atlas.line_height * scale * tr.line_spacing
        self._verts[:] = 0.0
        verts = self._verts
        vi = 0
        line_starts = [0]
        line_advs = []
        pen_y = 0.0
        for line in lines:
            c, adv = self._build_line_quads(atlas, line, scale, 0.0, pen_y, verts, vi * 20, tr.italic, 0.0)
            vi += c
            line_starts.append(vi)
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
                s = line_starts[i] * 20
                e = line_starts[i + 1] * 20
                verts[s:e:5] -= off_x
        if vi > 0:
            xs = verts[0:vi * 20:5]
            ys = verts[1:vi * 20:5]
            x_mid = (float(np.min(xs)) + float(np.max(xs))) * 0.5
            y_mid = (float(np.min(ys)) + float(np.max(ys))) * 0.5
            verts[0:vi * 20:5] -= x_mid
            verts[1:vi * 20:5] -= y_mid
        need_effects = tr.underline or tr.strikethrough
        evi = 0
        if need_effects:
            pen_y = 0.0
            e_starts = [0]
            for i, line in enumerate(lines):
                evi += self._build_effect_quads(atlas, line, scale, 0.0, pen_y, verts, (vi + evi) * 20, tr.underline, tr.strikethrough, 0.0, line_advs[i])
                e_starts.append(evi)
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
                    s = vi * 20 + e_starts[i] * 20
                    e = vi * 20 + e_starts[i + 1] * 20
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
        return vi, evi, scale

    def render(self, scene, view_mat: Mat4, proj_mat: Mat4, viewport_w: int, viewport_h: int):
        if not self._prog or not self._vao:
            return
        prog = self._prog
        view_f32 = view_mat.to_f32()
        proj_f32 = proj_mat.to_f32()
        zero3 = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        if "u_view" in prog:
            prog["u_view"].write(view_f32.tobytes())
        if "u_proj" in prog:
            prog["u_proj"].write(proj_f32.tobytes())
        if "u_viewport_size" in prog:
            prog["u_viewport_size"].write(np.array([float(viewport_w), float(viewport_h)], dtype=np.float32).tobytes())
        for ent in scene.get_entities_with_component(TextRenderer):
            if not ent.active:
                continue
            tr = ent.get_component(TextRenderer)
            if not tr or not tr.enabled or not tr.text:
                continue
            t = ent.get_component(Transform)
            if not t:
                continue
            atlas = self._get_atlas(tr.font_path, tr.atlas_resolution)
            if atlas is None:
                continue
            tex = self._ensure_texture(atlas)
            model_f32 = t.world_matrix.to_f32()
            if "u_model" in prog:
                prog["u_model"].write(model_f32.tobytes())
            if "u_billboard" in prog:
                prog["u_billboard"].value = 1.0 if tr.billboard else 0.0
            if "u_screen_space" in prog:
                prog["u_screen_space"].value = 0.0 if tr.font_world_space else 1.0
            gh = self._geom_hash(tr, atlas)
            cached = self._geom_cache.get(ent.id)
            if cached is not None and cached[4] == gh:
                vi, evi, scale, vdata = cached[0], cached[1], cached[2], cached[3]
                self._verts[:len(vdata)] = vdata
            else:
                vi, evi, scale = self._build_text_verts(tr, atlas)
                self._geom_cache[ent.id] = (vi, evi, scale, self._verts[:(vi+evi)*20].copy(), gh)
            if vi == 0 and evi == 0:
                continue
            total_verts = (vi + evi) * 4
            self._vbo.write(self._verts[:total_verts * 5].tobytes())
            ev = vi * 4
            has_shadow = tr.shadow and list(tr.shadow_color)[3] > 0
            has_3d = tr.use_3d and tr.extrusion_layers > 0 and tr.extrusion_depth > 0
            has_bold = tr.bold and not has_3d
            if has_shadow:
                self._ctx.disable(moderngl.DEPTH_TEST)
                sx, sy = tr.shadow_offset[0], tr.shadow_offset[1]
                if "u_offset" in prog:
                    prog["u_offset"].write(np.array([-sx, -sy, 0.0], dtype=np.float32).tobytes())
                if vi > 0:
                    self._render_quads(vi, list(tr.shadow_color), tex, False, False, 0)
                if evi > 0:
                    self._render_quads(evi, list(tr.shadow_color), tex, False, True, ev)
                if "u_offset" in prog:
                    prog["u_offset"].write(zero3.tobytes())
                self._ctx.enable(moderngl.DEPTH_TEST)
            else:
                self._ctx.enable(moderngl.DEPTH_TEST)
            if has_3d:
                layer_step = tr.extrusion_depth / max(tr.extrusion_layers, 1)
                if "u_offset" in prog:
                    for layer in range(tr.extrusion_layers, 0, -1):
                        z_off = layer * layer_step
                        t_factor = 0.3 + 0.7 * (1.0 - layer / max(tr.extrusion_layers, 1))
                        ecolor = [
                            tr.extrusion_color[0] * t_factor,
                            tr.extrusion_color[1] * t_factor,
                            tr.extrusion_color[2] * t_factor,
                            tr.color[3],
                        ]
                        prog["u_offset"].write(np.array([0.0, 0.0, z_off], dtype=np.float32).tobytes())
                        if vi > 0:
                            self._render_quads(vi, ecolor, tex, True, False, 0)
                        if evi > 0:
                            self._render_quads(evi, ecolor, tex, True, True, ev)
                    prog["u_offset"].write(zero3.tobytes())
                if vi > 0:
                    self._render_quads(vi, list(tr.color), tex, True, False, 0)
                if evi > 0:
                    self._render_quads(evi, list(tr.color), tex, True, True, ev)
            elif has_bold:
                bold_off = scale * 0.003
                if "u_offset" in prog:
                    prog["u_offset"].write(np.array([bold_off, 0.0, 0.0], dtype=np.float32).tobytes())
                if vi > 0:
                    self._render_quads(vi, list(tr.color), tex, True, False, 0)
                if "u_offset" in prog:
                    prog["u_offset"].write(np.array([-bold_off, 0.0, 0.0], dtype=np.float32).tobytes())
                if vi > 0:
                    self._render_quads(vi, list(tr.color), tex, True, False, 0)
                if "u_offset" in prog:
                    prog["u_offset"].write(zero3.tobytes())
                if evi > 0:
                    self._render_quads(evi, list(tr.color), tex, True, True, ev)
            else:
                if vi > 0:
                    self._render_quads(vi, list(tr.color), tex, True, False, 0)
                if evi > 0:
                    self._render_quads(evi, list(tr.color), tex, True, True, ev)
        self._ctx.depth_mask = True
        self._ctx.enable(moderngl.CULL_FACE)

    def release(self):
        for tex in self._tex_cache.values():
            try:
                tex.release()
            except Exception:
                pass
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._ibo:
            self._ibo.release()
