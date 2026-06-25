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
        self._build_buffers()

    def _build_buffers(self):
        max_verts = self._max_chars * 4
        max_indices = self._max_chars * 6
        verts = np.zeros(max_verts * 5, dtype=np.float32)
        indices = np.zeros(max_indices, dtype=np.uint32)
        for i in range(self._max_chars):
            base = i * 4
            indices[i * 6 + 0] = base + 0
            indices[i * 6 + 1] = base + 1
            indices[i * 6 + 2] = base + 2
            indices[i * 6 + 3] = base + 0
            indices[i * 6 + 4] = base + 2
            indices[i * 6 + 5] = base + 3
        self._vbo = self._ctx.buffer(verts.tobytes(), dynamic=True)
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

    def _sum_advance(self, atlas: FontAtlas, text: str) -> float:
        total = 0.0
        for c in text:
            g = atlas.get_glyph(c)
            if g:
                total += g["advance"]
        return total

    def _build_line_quads(self, atlas: FontAtlas, text: str, scale: float, pen_x: float, pen_y: float, verts: np.ndarray, base_idx: int, italic: bool = False, z_offset: float = 0.0) -> int:
        ascent = atlas.ascender
        count = 0
        skew = 0.25 if italic else 0.0
        for ch in text:
            g = atlas.get_glyph(ch)
            if g is None:
                continue
            if g["glyph_w"] <= 0 and g["glyph_h"] <= 0:
                pen_x += g["advance"] * scale
                continue
            left = pen_x + g["bearing_x"] * scale
            glyph_w = g["glyph_w"] * scale
            glyph_h = g["glyph_h"] * scale
            top = pen_y + (ascent - g["bearing_y"]) * scale
            right = left + glyph_w
            bottom = top - glyph_h
            u0, v0, u1, v1 = atlas.get_uv(ch)
            b = base_idx + count * 20
            shear = skew * (top - pen_y)
            verts[b + 0] = left
            verts[b + 1] = bottom
            verts[b + 2] = z_offset
            verts[b + 3] = u0
            verts[b + 4] = v1
            verts[b + 5] = right
            verts[b + 6] = bottom
            verts[b + 7] = z_offset
            verts[b + 8] = u1
            verts[b + 9] = v1
            verts[b + 10] = right + shear
            verts[b + 11] = top
            verts[b + 12] = z_offset
            verts[b + 13] = u1
            verts[b + 14] = v0
            verts[b + 15] = left + shear
            verts[b + 16] = top
            verts[b + 17] = z_offset
            verts[b + 18] = u0
            verts[b + 19] = v0
            pen_x += g["advance"] * scale
            count += 1
        return count

    def _build_effect_quads(self, atlas: FontAtlas, text: str, scale: float, pen_x: float, pen_y: float, verts: np.ndarray, base_idx: int, underline: bool, strikethrough: bool, z_offset: float = 0.0) -> int:
        ascent = atlas.ascender
        descender = atlas.descender
        total_w = 0.0
        for ch in text:
            g = atlas.get_glyph(ch)
            if g:
                total_w += g["advance"] * scale
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

    def _render_quads(self, verts: np.ndarray, vi: int, color: list[float], tex: Any, write_depth: bool, solid: bool):
        prog = self._prog
        if vi == 0:
            return
        self._vbo.write(verts[:vi*20].tobytes())
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
        self._vao.render(moderngl.TRIANGLES, vertices=vi * 6)

    def _render_pass(self, tr: TextRenderer, atlas: FontAtlas, tex: Any, color: list[float], view_f32: np.ndarray, proj_f32: np.ndarray, viewport_w: int, viewport_h: int, offset_x: float = 0.0, offset_y: float = 0.0, write_depth: bool = False, z_offset: float = 0.0):
        lines = tr.text.split("\n")
        inv_lh = atlas._inv_lh()
        scale = float(tr.font_size) * inv_lh * 0.01
        line_h = atlas.line_height * scale * tr.line_spacing
        line_widths = []
        total_w_raw = 0.0
        for line in lines:
            lw = self._sum_advance(atlas, line)
            line_widths.append(lw)
            if lw > total_w_raw:
                total_w_raw = lw
        total_w = total_w_raw * scale
        verts = np.zeros(self._max_chars * 20, dtype=np.float32)
        vi = 0
        pen_y = 0.0
        for line_idx, line in enumerate(lines):
            lw_world = line_widths[line_idx] * scale
            if tr.alignment == TextAlign.LEFT:
                line_off_x = 0.0
            elif tr.alignment == TextAlign.CENTER:
                line_off_x = (total_w - lw_world) * 0.5
            elif tr.alignment == TextAlign.RIGHT:
                line_off_x = total_w - lw_world
            else:
                line_off_x = 0.0
            pen_x = line_off_x
            vi += self._build_line_quads(atlas, line, scale, pen_x, pen_y, verts, vi * 20, tr.italic, z_offset)
            pen_y -= line_h
        if vi > 0:
            xs = verts[0:vi*20:5]
            ys = verts[1:vi*20:5]
            x_mid = (float(np.min(xs)) + float(np.max(xs))) * 0.5
            y_mid = (float(np.min(ys)) + float(np.max(ys))) * 0.5
            verts[0:vi*20:5] -= (x_mid + offset_x)
            verts[1:vi*20:5] -= (y_mid + offset_y)
            self._render_quads(verts, vi, color, tex, write_depth, False)
        need_effects = tr.underline or tr.strikethrough
        if need_effects:
            evi = 0
            pen_y = 0.0
            for line_idx, line in enumerate(lines):
                lw_world = line_widths[line_idx] * scale
                if tr.alignment == TextAlign.LEFT:
                    line_off_x = 0.0
                elif tr.alignment == TextAlign.CENTER:
                    line_off_x = (total_w - lw_world) * 0.5
                elif tr.alignment == TextAlign.RIGHT:
                    line_off_x = total_w - lw_world
                else:
                    line_off_x = 0.0
                pen_x = line_off_x
                evi += self._build_effect_quads(atlas, line, scale, pen_x, pen_y, verts, evi, tr.underline, tr.strikethrough, z_offset)
                pen_y -= line_h
            if evi > 0:
                xs = verts[0:evi*20:5]
                ys = verts[1:evi*20:5]
                x_mid = (float(np.min(xs)) + float(np.max(xs))) * 0.5
                y_mid = (float(np.min(ys)) + float(np.max(ys))) * 0.5
                verts[0:evi*20:5] -= (x_mid + offset_x)
                verts[1:evi*20:5] -= (y_mid + offset_y)
                self._render_quads(verts, evi, color, tex, write_depth, True)

    def render(self, scene, view_mat: Mat4, proj_mat: Mat4, viewport_w: int, viewport_h: int):
        if not self._prog or not self._vao:
            return
        prog = self._prog
        view_f32 = view_mat.to_f32()
        proj_f32 = proj_mat.to_f32()
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
            inv_lh = atlas._inv_lh()
            scale = float(tr.font_size) * inv_lh * 0.01
            self._ctx.depth_mask = True
            if tr.shadow:
                self._ctx.disable(moderngl.DEPTH_TEST)
                sx, sy = tr.shadow_offset[0], tr.shadow_offset[1]
                self._render_pass(tr, atlas, tex, list(tr.shadow_color), view_f32, proj_f32, viewport_w, viewport_h, offset_x=-sx, offset_y=-sy, write_depth=False)
                self._ctx.enable(moderngl.DEPTH_TEST)
            else:
                self._ctx.enable(moderngl.DEPTH_TEST)
            if tr.use_3d and tr.extrusion_layers > 0 and tr.extrusion_depth > 0:
                layer_step = tr.extrusion_depth / max(tr.extrusion_layers, 1)
                for layer in range(tr.extrusion_layers, -1, -1):
                    z_off = layer * layer_step
                    t_factor = 0.3 + 0.7 * (1.0 - layer / max(tr.extrusion_layers, 1))
                    if layer == 0:
                        layer_color = list(tr.color)
                    else:
                        layer_color = [
                            tr.extrusion_color[0] * t_factor,
                            tr.extrusion_color[1] * t_factor,
                            tr.extrusion_color[2] * t_factor,
                            tr.color[3],
                        ]
                    self._render_pass(tr, atlas, tex, layer_color, view_f32, proj_f32, viewport_w, viewport_h, write_depth=True, z_offset=z_off)
            elif tr.bold:
                bold_off = scale * 0.003
                self._render_pass(tr, atlas, tex, tr.color, view_f32, proj_f32, viewport_w, viewport_h, offset_x=bold_off, write_depth=True)
                self._render_pass(tr, atlas, tex, tr.color, view_f32, proj_f32, viewport_w, viewport_h, write_depth=True)
            else:
                self._render_pass(tr, atlas, tex, tr.color, view_f32, proj_f32, viewport_w, viewport_h, write_depth=True)
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
