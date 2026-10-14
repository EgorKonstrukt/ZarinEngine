# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.maths.math3d import Mat4
from core.components.rendering.renderers.sprite_renderer import SpriteRenderer
from core.renderer.spr.batch import SpriteBatchMixin, _INST_FLOATS, _INST_INITIAL_CAPACITY
class SpriteRendererGL(SpriteBatchMixin):
    def __init__(self, ctx: moderngl.Context, prog: moderngl.Program):
        self._ctx = ctx
        self._prog = prog
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._texture_loader = None
        self._inst_prog: Optional[moderngl.Program] = None
        self._inst_vbo: Optional[moderngl.Buffer] = None
        self._inst_vao: Optional[moderngl.VertexArray] = None
        self._inst_capacity = 0
        self._has_view = False
        self._has_proj = False
        self._has_model = False
        self._has_color = False
        self._has_flip = False
        self._has_cutoff = False
        self._has_texture = False
        self._inst_has_view = False
        self._inst_has_proj = False
        self._inst_has_texture = False
        self._inst_has_cutoff = False
        self._host_blob = np.empty((_INST_INITIAL_CAPACITY, _INST_FLOATS), dtype=np.float32)
        self._last_base = None
        self._last_tp = None
        self._last_n = 0
        self._last_items = None
        self._build_buffers()
        self._build_instanced()
    def set_texture_loader(self, loader):
        self._texture_loader = loader
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
    def render_snapshot(self, sprite_items: list, view_mat: Mat4, proj_mat: Mat4, cache_key=None):
        if not sprite_items:
            return
        if self._inst_prog is not None and self._inst_vao is not None:
            self._render_snapshot_instanced(sprite_items, view_mat, proj_mat, cache_key)
        elif self._prog is not None and self._vao is not None:
            self._render_snapshot_legacy(sprite_items, view_mat, proj_mat)
    def _render_snapshot_legacy(self, sprite_items: list, view_mat: Mat4, proj_mat: Mat4):
        prog = self._prog
        if prog is None or self._vao is None:
            return
        self._begin_frame(view_mat, proj_mat, prog, self._has_view, self._has_proj)
        try:
            has_model = self._has_model
            has_color = self._has_color
            has_flip = self._has_flip
            has_cutoff = self._has_cutoff
            has_texture = self._has_texture
            if has_cutoff:
                try:
                    prog["u_alpha_cutoff"].value = 0.01
                except Exception:
                    pass
            if has_texture:
                try:
                    prog["u_texture"].value = 0
                except Exception:
                    pass
            groups, tex_cache = self._group_by_texture(sprite_items)
            if not groups:
                return
            for tp, lst in groups.items():
                tex = tex_cache.get(tp)
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
                    if has_model:
                        try:
                            prog["u_model"].write(model_f32.tobytes())
                        except Exception:
                            pass
                    if has_color:
                        try:
                            prog["u_color"].write(np.array(item.color, dtype=np.float32).tobytes())
                        except Exception:
                            pass
                    if has_flip:
                        try:
                            prog["u_flip"].write(np.array(
                                [1.0 if item.flip_x else 0.0, 1.0 if item.flip_y else 0.0],
                                dtype=np.float32
                            ).tobytes())
                        except Exception:
                            pass
                    try:
                        self._vao.render(moderngl.TRIANGLES)
                    except Exception:
                        continue
        finally:
            self._end_frame()
    def render(self, scene, view_mat: Mat4, proj_mat: Mat4):
        if self._inst_prog is not None and self._inst_vao is not None:
            items = self._collect_scene_items(scene)
            if items:
                self._render_snapshot_instanced(items, view_mat, proj_mat)
            return
        if not self._prog or not self._vao:
            return
        prog = self._prog
        self._begin_frame(view_mat, proj_mat, prog, self._has_view, self._has_proj)
        try:
            has_model = self._has_model
            has_color = self._has_color
            has_flip = self._has_flip
            has_cutoff = self._has_cutoff
            has_texture = self._has_texture
            if has_cutoff:
                try:
                    prog["u_alpha_cutoff"].value = 0.01
                except Exception:
                    pass
            if has_texture:
                try:
                    prog["u_texture"].value = 0
                except Exception:
                    pass
            loader = self._texture_loader
            tex_cache: dict = {}
            for ent in scene.get_entities_with_component(SpriteRenderer):
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
                    tm = ent._type_map.get(SpriteRenderer)
                    sr = tm[0] if tm else None
                except Exception:
                    try:
                        sr = ent.get_component(SpriteRenderer)
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
                try:
                    tp = sr.texture_path
                except Exception:
                    continue
                if not tp:
                    continue
                tex = tex_cache.get(tp)
                if tex is None and tp not in tex_cache:
                    try:
                        tex = loader(tp) if tp and loader is not None else None
                    except Exception:
                        tex = None
                    tex_cache[tp] = tex
                if tex is None:
                    continue
                try:
                    model_f32 = tr.world_matrix.to_f32()
                except Exception:
                    continue
                if has_model:
                    try:
                        prog["u_model"].write(model_f32.tobytes())
                    except Exception:
                        pass
                if has_color:
                    try:
                        color = sr.color
                        prog["u_color"].write(np.array(color, dtype=np.float32).tobytes())
                    except Exception:
                        pass
                if has_flip:
                    try:
                        prog["u_flip"].write(np.array(
                            [1.0 if sr.flip_x else 0.0, 1.0 if sr.flip_y else 0.0],
                            dtype=np.float32
                        ).tobytes())
                    except Exception:
                        pass
                try:
                    tex.use(0)
                except Exception:
                    continue
                try:
                    self._vao.render(moderngl.TRIANGLES)
                except Exception:
                    continue
        finally:
            self._end_frame()
    def _collect_scene_items(self, scene) -> list:
        from core.renderer.render_items import _SpriteItem
        out: list = []
        try:
            append = out.append
            for ent in scene.get_entities_with_component(SpriteRenderer):
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
                    tm = ent._type_map.get(SpriteRenderer)
                    sr = tm[0] if tm else None
                except Exception:
                    try:
                        sr = ent.get_component(SpriteRenderer)
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
                try:
                    tp = sr.texture_path
                except Exception:
                    continue
                if not tp:
                    continue
                try:
                    append(_SpriteItem(
                        tr.world_matrix, sr.color, sr.flip_x, sr.flip_y, tp, tr))
                except Exception:
                    continue
        except Exception:
            pass
        return out
    def release(self):
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
        self._last_tp = None
        self._last_n = 0
        self._last_items = None
