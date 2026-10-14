# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import threading
from typing import Optional, Any
import numpy as np
import moderngl
from core.maths.math3d import Mat4
from core.components.rendering.renderers.svg_renderer import SvgRenderer
from .parse import SvgParseMixin
from .tess import SvgTessMixin, _INST_FLOATS, _INST_INITIAL_CAPACITY, _SKIP_MAX_ITEMS
class SvgRendererGL(SvgParseMixin, SvgTessMixin):
    def __init__(self, ctx: moderngl.Context, prog: moderngl.Program):
        self._ctx = ctx
        self._prog = prog
        self._has_view = "u_view" in prog
        self._has_proj = "u_proj" in prog
        self._has_model = "u_model" in prog
        self._has_color = "u_color" in prog
        self._has_flip = "u_flip" in prog
        self._has_alpha_cutoff = "u_alpha_cutoff" in prog
        self._has_texture = "u_texture" in prog
        self._flip_arr = np.array([0.0, 0.0], dtype=np.float32)
        self._alpha_cutoff_val = 0.01
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._texture_cache: dict[tuple[str, float], tuple[str, float, Any]] = {}
        self._path_cache: dict[str, Optional[str]] = {}
        self._inst_prog: Optional[moderngl.Program] = None
        self._inst_vbo: Optional[moderngl.Buffer] = None
        self._inst_vao: Optional[moderngl.VertexArray] = None
        self._inst_capacity = 0
        self._inst_has_view = False
        self._inst_has_proj = False
        self._inst_has_texture = False
        self._inst_has_cutoff = False
        self._host_blob = np.empty((_INST_INITIAL_CAPACITY, _INST_FLOATS), dtype=np.float32)
        self._last_base = None
        self._last_key = None
        self._last_n = 0
        self._last_items = None
        self._pending_uploads: list = []
        self._pending_lock = threading.Lock()
        self._inflight: set = set()
        self._raster_epoch = 0
        self._svg_stats: dict = {"pending": 0, "inflight": 0, "last_raster_ms": 0.0, "rastered": 0}
        self._build_buffers()
        self._build_instanced()
    def _begin_frame(self, view_mat: Mat4, proj_mat: Mat4, prog, has_view: bool, has_proj: bool):
        try:
            view_f32 = view_mat.to_f32()
        except Exception:
            view_f32 = np.eye(4, dtype=np.float32).reshape(-1)
        try:
            proj_f32 = proj_mat.to_f32()
        except Exception:
            proj_f32 = np.eye(4, dtype=np.float32).reshape(-1)
        if has_view:
            try:
                prog["u_view"].write(view_f32.tobytes())
            except Exception:
                pass
        if has_proj:
            try:
                prog["u_proj"].write(proj_f32.tobytes())
            except Exception:
                pass
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._ctx.depth_mask = True
    def _end_frame(self):
        try:
            self._ctx.enable(moderngl.CULL_FACE)
        except Exception:
            pass
    def render_snapshot(self, svg_items: list, view_mat: Mat4, proj_mat: Mat4, cache_key=None):
        try:
            self._drain_uploads()
        except Exception:
            pass
        if not svg_items:
            return
        if self._inst_prog is not None and self._inst_vao is not None:
            self._render_snapshot_instanced(svg_items, view_mat, proj_mat, cache_key)
        elif self._vao is not None:
            self._render_snapshot_legacy(svg_items, view_mat, proj_mat)
    def _render_snapshot_instanced(self, svg_items: list, view_mat: Mat4, proj_mat: Mat4, cache_key=None):
        prog = self._inst_prog
        if prog is None or self._inst_vao is None:
            return
        self._begin_frame(view_mat, proj_mat, prog, self._inst_has_view, self._inst_has_proj)
        try:
            if self._inst_has_texture:
                try:
                    prog["u_texture"].value = 0
                except Exception:
                    pass
            if self._inst_has_cutoff:
                try:
                    prog["u_alpha_cutoff"].value = self._alpha_cutoff_val
                except Exception:
                    pass
            groups, tex_cache = self._group_by_texture(svg_items)
            if not groups:
                return
            if cache_key is not None and len(groups) == 1 and self._last_base is not None:
                try:
                    key0 = next(iter(groups))
                    lst0 = groups[key0]
                    if cache_key == self._last_base and key0 == self._last_key and len(lst0) == self._last_n and len(lst0) <= self._inst_capacity:
                        tex0 = tex_cache.get(key0)
                        if tex0 is not None:
                            try:
                                tex0.use(0)
                                self._inst_vao.render(moderngl.TRIANGLES, instances=len(lst0))
                                return
                            except Exception:
                                pass
                except Exception:
                    pass
            try:
                vp = view_mat._d @ proj_mat._d
                p00 = float(proj_mat._d[0, 0])
                p11 = float(proj_mat._d[1, 1])
            except Exception:
                vp = None
                p00 = 0.0
                p11 = 0.0
            drawn_total = 0
            listed_total = 0
            for key, lst in groups.items():
                tex = tex_cache.get(key)
                if tex is None:
                    continue
                listed_total += len(lst)
                drawn_total += self._render_group_instanced(lst, tex, vp, p00, p11)
            try:
                if cache_key is not None and len(groups) == 1 and listed_total == drawn_total and 0 < listed_total <= _SKIP_MAX_ITEMS:
                    self._last_base = cache_key
                    self._last_key = next(iter(groups))
                    self._last_n = listed_total
                    self._last_items = svg_items
                else:
                    self._last_base = None
                    self._last_key = None
                    self._last_n = 0
                    self._last_items = None
            except Exception:
                pass
        finally:
            self._end_frame()
    def _render_snapshot_legacy(self, svg_items: list, view_mat: Mat4, proj_mat: Mat4):
        prog = self._prog
        if prog is None or self._vao is None:
            return
        self._begin_frame(view_mat, proj_mat, prog, self._has_view, self._has_proj)
        try:
            if self._has_alpha_cutoff:
                try:
                    prog["u_alpha_cutoff"].value = self._alpha_cutoff_val
                except Exception:
                    pass
            if self._has_texture:
                try:
                    prog["u_texture"].value = 0
                except Exception:
                    pass
            groups, tex_cache = self._group_by_texture(svg_items)
            if not groups:
                return
            for key, lst in groups.items():
                tex = tex_cache.get(key)
                if tex is None:
                    continue
                try:
                    tex.use(0)
                except Exception:
                    continue
                for item in lst:
                    try:
                        model_f32 = item.world_matrix.to_f32()
                    except Exception:
                        continue
                    if self._has_model:
                        try:
                            prog["u_model"].write(model_f32.tobytes())
                        except Exception:
                            pass
                    if self._has_color:
                        try:
                            prog["u_color"].write(np.array(item.color, dtype=np.float32).tobytes())
                        except Exception:
                            pass
                    if self._has_flip:
                        try:
                            self._flip_arr[0] = 1.0 if item.flip_x else 0.0
                            self._flip_arr[1] = 1.0 if item.flip_y else 0.0
                            prog["u_flip"].write(self._flip_arr.tobytes())
                        except Exception:
                            pass
                    try:
                        self._vao.render(moderngl.TRIANGLES)
                    except Exception:
                        continue
        finally:
            self._end_frame()
    def render(self, scene, view_mat: Mat4, proj_mat: Mat4):
        try:
            self._drain_uploads()
        except Exception:
            pass
        if not self._vao:
            return
        if self._inst_prog is not None and self._inst_vao is not None:
            items = self._collect_scene_items(scene)
            if items:
                self._render_snapshot_instanced(items, view_mat, proj_mat, None)
            return
        prog = self._prog
        self._begin_frame(view_mat, proj_mat, prog, self._has_view, self._has_proj)
        try:
            if self._has_alpha_cutoff:
                try:
                    prog["u_alpha_cutoff"].value = self._alpha_cutoff_val
                except Exception:
                    pass
            entities = scene.get_entities_with_component(SvgRenderer)
            for ent in entities:
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
                tex = self._get_texture_async(abs_path, ppu)
                if tex is None:
                    continue
                if self._has_model:
                    try:
                        prog["u_model"].write(tr.world_matrix.to_f32().tobytes())
                    except Exception:
                        pass
                if self._has_color:
                    try:
                        prog["u_color"].write(np.array(sr.color, dtype=np.float32).tobytes())
                    except Exception:
                        pass
                if self._has_flip:
                    try:
                        self._flip_arr[0] = 1.0 if sr.flip_x else 0.0
                        self._flip_arr[1] = 1.0 if sr.flip_y else 0.0
                        prog["u_flip"].write(self._flip_arr.tobytes())
                    except Exception:
                        pass
                try:
                    tex.use(0)
                except Exception:
                    continue
                if self._has_texture:
                    try:
                        prog["u_texture"].value = 0
                    except Exception:
                        pass
                try:
                    self._vao.render(moderngl.TRIANGLES)
                except Exception:
                    continue
        finally:
            self._end_frame()
    def release(self):
        try:
            self._raster_epoch += 1
        except Exception:
            pass
        try:
            with self._pending_lock:
                self._pending_uploads = []
        except Exception:
            pass
        try:
            self._inflight.clear()
        except Exception:
            pass
        for entry in self._texture_cache.values():
            try:
                tex = entry[2]
            except Exception:
                tex = None
            if tex is not None:
                try:
                    tex.release()
                except Exception:
                    pass
        self._texture_cache.clear()
        self._path_cache.clear()
        if self._vao:
            try:
                self._vao.release()
            except Exception:
                pass
            self._vao = None
        if self._vbo:
            try:
                self._vbo.release()
            except Exception:
                pass
            self._vbo = None
        if self._ibo:
            try:
                self._ibo.release()
            except Exception:
                pass
            self._ibo = None
        if self._inst_vao is not None:
            try:
                self._inst_vao.release()
            except Exception:
                pass
            self._inst_vao = None
        if self._inst_vbo is not None:
            try:
                self._inst_vbo.release()
            except Exception:
                pass
            self._inst_vbo = None
        if self._inst_prog is not None:
            try:
                self._inst_prog.release()
            except Exception:
                pass
            self._inst_prog = None
        self._inst_capacity = 0
        self._last_base = None
        self._last_key = None
        self._last_n = 0
        self._last_items = None
