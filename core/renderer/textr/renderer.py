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
from core.components.rendering.renderers.text_renderer import TextRenderer
from core.assets.fontatlas import FontAtlas
from core.renderer.textr.atlas import TextAtlasMixin
from core.renderer.textr.layout import TextLayoutMixin
from core.renderer.textr.draw import TextDrawMixin
_ZERO3 = np.array([0.0, 0.0, 0.0], dtype=np.float32)
class TextRendererGL(TextAtlasMixin, TextLayoutMixin, TextDrawMixin):
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
            self._draw_shadow(prog, names, tr, tex, vi, evi, ev, has_shadow)
            write_depth = False
            if has_glow or has_outline:
                try:
                    self._ctx.disable(moderngl.DEPTH_TEST)
                except Exception:
                    pass
            self._draw_glow(prog, names, tr, tex, vi, evi, ev, has_glow, write_depth)
            self._draw_outline(prog, names, tr, tex, vi, evi, ev, has_outline, write_depth)
            if has_glow or has_outline:
                if tr.font_world_space:
                    try:
                        self._ctx.enable(moderngl.DEPTH_TEST)
                    except Exception:
                        pass
            if has_3d:
                self._draw_extruded(prog, names, tr, tex, vi, evi, ev, write_depth, clip_main)
            else:
                self._draw_main(tr, tex, vi, evi, ev, write_depth, clip_main)
        try:
            self._ctx.depth_mask = True
        except Exception:
            pass
        try:
            self._ctx.enable(moderngl.CULL_FACE)
        except Exception:
            pass
