# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
import moderngl
from core.maths.math3d import Mat4
_INST_VERT = (chr(35) + "version 330 core\n" + "layout(location = 0) in vec3 in_position;\n" + "layout(location = 1) in vec2 in_uv;\n" + "layout(location = 2) in vec4 in_model0;\n" + "layout(location = 3) in vec4 in_model1;\n" + "layout(location = 4) in vec4 in_model2;\n" + "layout(location = 5) in vec4 in_model3;\n" + "layout(location = 6) in vec4 in_color;\n" + "layout(location = 7) in vec2 in_flip;\n" + "uniform mat4 u_view;\n" + "uniform mat4 u_proj;\n" + "out vec2 v_uv;\n" + "out vec4 v_color;\n" + "void main() {\n" + "    vec2 uv = in_uv;\n" + "    if (in_flip.x > 0.5) uv.x = 1.0 - uv.x;\n" + "    if (in_flip.y > 0.5) uv.y = 1.0 - uv.y;\n" + "    v_uv = uv;\n" + "    v_color = in_color;\n" + "    mat4 model = mat4(in_model0, in_model1, in_model2, in_model3);\n" + "    gl_Position = u_proj * u_view * model * vec4(in_position, 1.0);\n" + "}\n")
_INST_FRAG = (chr(35) + "version 330 core\n" + "in vec2 v_uv;\n" + "in vec4 v_color;\n" + "uniform sampler2D u_texture;\n" + "uniform float u_alpha_cutoff;\n" + "out vec4 frag_color;\n" + "void main() {\n" + "    vec4 tex = texture(u_texture, v_uv);\n" + "    vec4 result = tex * v_color;\n" + "    if (result.a < u_alpha_cutoff) discard;\n" + "    frag_color = result;\n" + "}\n")
_INST_FLOATS = 22
_INST_BYTES = _INST_FLOATS * 4
_INST_INITIAL_CAPACITY = 1024
_CULL_MIN_GROUP = 256
_SKIP_MAX_ITEMS = 16384
_IDENTITY_16 = np.eye(4, dtype=np.float32).reshape(-1)
class SpriteBatchMixin:
    def _build_buffers(self):
        sprite_quad = np.array([
            -0.5, -0.5, 0.0, 0.0, 0.0,
             0.5, -0.5, 0.0, 1.0, 0.0,
             0.5,  0.5, 0.0, 1.0, 1.0,
            -0.5,  0.5, 0.0, 0.0, 1.0,
        ], dtype=np.float32)
        sprite_idx = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
        self._vbo = self._ctx.buffer(sprite_quad.tobytes())
        self._ibo = self._ctx.buffer(sprite_idx.tobytes())
        self._vao = self._ctx.vertex_array(
            self._prog,
            [(self._vbo, "3f 2f", "in_position", "in_uv")],
            self._ibo
        )
        try:
            names = frozenset(self._prog)
        except Exception:
            names = frozenset()
        self._has_view = "u_view" in names
        self._has_proj = "u_proj" in names
        self._has_model = "u_model" in names
        self._has_color = "u_color" in names
        self._has_flip = "u_flip" in names
        self._has_cutoff = "u_alpha_cutoff" in names
        self._has_texture = "u_texture" in names
    def _build_instanced(self):
        try:
            prog = self._ctx.program(vertex_shader=_INST_VERT, fragment_shader=_INST_FRAG)
        except Exception:
            return
        try:
            names = frozenset(prog)
        except Exception:
            names = frozenset()
        if "in_model0" not in names or "in_color" not in names:
            try:
                prog.release()
            except Exception:
                pass
            return
        self._inst_prog = prog
        self._inst_has_view = "u_view" in names
        self._inst_has_proj = "u_proj" in names
        self._inst_has_texture = "u_texture" in names
        self._inst_has_cutoff = "u_alpha_cutoff" in names
        self._alloc_inst_storage(_INST_INITIAL_CAPACITY)
    def _alloc_inst_storage(self, capacity: int) -> bool:
        try:
            vbo = self._ctx.buffer(reserve=max(1, capacity) * _INST_BYTES, dynamic=True)
        except Exception:
            return False
        try:
            vao = self._ctx.vertex_array(
                self._inst_prog,
                [
                    (self._vbo, "3f 2f", "in_position", "in_uv"),
                    (vbo, "4f 4f 4f 4f 4f 2f /i",
                     "in_model0", "in_model1", "in_model2", "in_model3",
                     "in_color", "in_flip"),
                ],
                self._ibo,
            )
        except Exception:
            try:
                vbo.release()
            except Exception:
                pass
            return False
        try:
            if self._inst_vao is not None:
                self._inst_vao.release()
        except Exception:
            pass
        try:
            if self._inst_vbo is not None:
                self._inst_vbo.release()
        except Exception:
            pass
        self._inst_vbo = vbo
        self._inst_vao = vao
        self._inst_capacity = capacity
        self._last_base = None
        self._last_tp = None
        self._last_n = 0
        self._last_items = None
        return True
    def _ensure_inst_capacity(self, count: int) -> bool:
        if count <= self._inst_capacity and self._inst_vbo is not None and self._inst_vao is not None:
            return True
        grown = max(count, self._inst_capacity * 2 if self._inst_capacity else _INST_INITIAL_CAPACITY)
        return self._alloc_inst_storage(grown)
    def _group_by_texture(self, sprite_items: list):
        loader = self._texture_loader
        tex_cache: dict = {}
        groups: dict = {}
        for item in sprite_items:
            try:
                tp = item.texture_path
            except Exception:
                continue
            if not tp:
                continue
            tex = tex_cache.get(tp)
            if tex is None and tp not in tex_cache:
                try:
                    tex = loader(tp) if loader is not None else None
                except Exception:
                    tex = None
                tex_cache[tp] = tex
            if tex is None:
                continue
            lst = groups.get(tp)
            if lst is None:
                groups[tp] = [item]
            else:
                lst.append(item)
        return groups, tex_cache
    def _cull_mask(self, models, vp, p00: float, p11: float):
        try:
            n = models.shape[0]
            if n <= 0 or vp is None:
                return None
            if not (np.isfinite(vp).all() and np.isfinite(p00) and np.isfinite(p11)):
                return None
            if not (p00 > 0.0 and p11 > 0.0):
                return None
            c = models[:, 12:15].astype(np.float64, copy=False)
            ch = np.ones((n, 4), dtype=np.float64)
            ch[:, 0:3] = c
            clips = ch @ vp
            w = clips[:, 3]
            ok_w = w > 1e-6
            with np.errstate(divide="ignore", invalid="ignore"):
                ndc = clips[:, 0:3] / w[:, None]
            in_x0 = (ndc[:, 0] >= -1.0) & (ndc[:, 0] <= 1.0)
            in_y0 = (ndc[:, 1] >= -1.0) & (ndc[:, 1] <= 1.0)
            inside = ok_w & in_x0 & in_y0
            if bool((inside | ~ok_w).all()):
                return np.ones(n, dtype=bool)
            r0 = models[:, 0:3].astype(np.float64, copy=False)
            r1 = models[:, 4:7].astype(np.float64, copy=False)
            sx = np.sqrt((r0 * r0).sum(axis=1))
            sy = np.sqrt((r1 * r1).sum(axis=1))
            radius = 0.5 * (sx + sy) + 1e-4
            with np.errstate(divide="ignore", invalid="ignore"):
                mx = radius * (p00 / np.maximum(w, 1e-6))
                my = radius * (p11 / np.maximum(w, 1e-6))
            in_x = (ndc[:, 0] >= -1.0 - mx) & (ndc[:, 0] <= 1.0 + mx)
            in_y = (ndc[:, 1] >= -1.0 - my) & (ndc[:, 1] <= 1.0 + my)
            keep = (~ok_w) | (ok_w & in_x & in_y)
            return keep
        except Exception:
            return None
    def _ensure_host(self, count: int):
        try:
            if self._host_blob.shape[0] < count:
                grown = max(count, self._host_blob.shape[0] * 2)
                self._host_blob = np.empty((grown, _INST_FLOATS), dtype=np.float32)
        except Exception:
            try:
                self._host_blob = np.empty((max(1, count), _INST_FLOATS), dtype=np.float32)
            except Exception:
                pass
    def _build_models(self, items: list):
        n = len(items)
        try:
            return np.array([it.world_matrix._d for it in items], dtype=np.float32).reshape(n, 16)
        except Exception:
            pass
        try:
            models = np.empty((n, 16), dtype=np.float32)
            for i, it in enumerate(items):
                try:
                    models[i] = it.world_matrix._d.reshape(-1)
                except Exception:
                    try:
                        models[i] = it.world_matrix.to_f32()
                    except Exception:
                        models[i] = _IDENTITY_16
            return models
        except Exception:
            return None
    def _build_colors(self, items: list, n: int):
        try:
            colors = np.array([it.color for it in items], dtype=np.float32)
            if colors.shape == (n, 4):
                return colors
        except Exception:
            pass
        try:
            colors = np.ones((n, 4), dtype=np.float32)
            for i, it in enumerate(items):
                try:
                    c = it.color
                    colors[i, 0] = c[0]
                    colors[i, 1] = c[1]
                    colors[i, 2] = c[2]
                    colors[i, 3] = c[3] if len(c) > 3 else 1.0
                except Exception:
                    pass
            return colors
        except Exception:
            return None
    def _render_group_instanced(self, lst: list, tex, vp, p00: float, p11: float) -> int:
        n = len(lst)
        if n <= 0:
            return 0
        models = self._build_models(lst)
        if models is None:
            return 0
        if n >= _CULL_MIN_GROUP and vp is not None:
            mask = self._cull_mask(models, vp, p00, p11)
            if mask is not None:
                try:
                    vis = int(mask.sum())
                except Exception:
                    vis = n
                if vis <= 0:
                    return 0
                if vis < n:
                    try:
                        idx = np.nonzero(mask)[0]
                        models = models[idx]
                        lst = [lst[i] for i in idx]
                        n = vis
                    except Exception:
                        pass
        colors = self._build_colors(lst, n)
        if colors is None:
            return 0
        try:
            flips = np.empty((n, 2), dtype=np.float32)
            for i, it in enumerate(lst):
                try:
                    flips[i, 0] = 1.0 if it.flip_x else 0.0
                    flips[i, 1] = 1.0 if it.flip_y else 0.0
                except Exception:
                    flips[i, 0] = 0.0
                    flips[i, 1] = 0.0
        except Exception:
            return 0
        if not self._ensure_inst_capacity(n):
            return 0
        try:
            self._ensure_host(n)
            host = self._host_blob
            host[:n, 0:16] = models
            host[:n, 16:20] = colors
            host[:n, 20:22] = flips
            self._inst_vbo.write(memoryview(host[:n]))
        except Exception:
            try:
                blob = np.empty((n, _INST_FLOATS), dtype=np.float32)
                blob[:, 0:16] = models
                blob[:, 16:20] = colors
                blob[:, 20:22] = flips
                self._inst_vbo.write(blob.tobytes())
            except Exception:
                return 0
        try:
            tex.use(0)
        except Exception:
            return 0
        try:
            self._inst_vao.render(moderngl.TRIANGLES, instances=n)
        except Exception:
            return 0
        return n
    def _render_snapshot_instanced(self, sprite_items: list, view_mat: Mat4, proj_mat: Mat4, cache_key=None):
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
                    prog["u_alpha_cutoff"].value = 0.01
                except Exception:
                    pass
            groups, tex_cache = self._group_by_texture(sprite_items)
            if not groups:
                return
            if cache_key is not None and len(groups) == 1 and self._last_base is not None:
                try:
                    tp0 = next(iter(groups))
                    lst0 = groups[tp0]
                    if (cache_key == self._last_base and tp0 == self._last_tp
                            and len(lst0) == self._last_n and len(lst0) <= self._inst_capacity):
                        tex0 = tex_cache.get(tp0)
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
            for tp, lst in groups.items():
                tex = tex_cache.get(tp)
                if tex is None:
                    continue
                listed_total += len(lst)
                drawn_total += self._render_group_instanced(lst, tex, vp, p00, p11)
            try:
                if (cache_key is not None and len(groups) == 1 and listed_total == drawn_total
                        and 0 < listed_total <= _SKIP_MAX_ITEMS):
                    tp1 = next(iter(groups))
                    self._last_base = cache_key
                    self._last_tp = tp1
                    self._last_n = listed_total
                    self._last_items = sprite_items
                else:
                    self._last_base = None
                    self._last_tp = None
                    self._last_n = 0
                    self._last_items = None
            except Exception:
                pass
        finally:
            self._end_frame()
