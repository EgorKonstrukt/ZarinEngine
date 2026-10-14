# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Any
import numpy as np
import moderngl
from core.maths.math3d import Mat4
from core.renderer.origin import relativize_chunk_f32
from .bind import pack_model_matrices_f32
from .vao import _shadow_supports_instancing, _make_shadow_instanced_vao
class InstancingMixin:
    def _supports_instancing_cached(self, prog) -> bool:
        key = id(prog)
        v = self._instancing_cache.get(key)
        if v is not None:
            return v
        v = _shadow_supports_instancing(prog)
        self._instancing_cache[key] = v
        return v
    def _remember_inst_sel(self, key, sel):
        try:
            fk = self._shadow_frame_key
            if fk is None or sel is None:
                return
            try:
                _so = self._shadow_origin
                _ok = None if _so is None else (float(_so[0]), float(_so[1]), float(_so[2]))
            except Exception:
                _ok = None
            self._shadow_inst_sel[key] = (fk, _ok, np.array(sel, dtype=np.intp, copy=True))
            if len(self._shadow_inst_sel) > 1024:
                try:
                    self._shadow_inst_sel.pop(next(iter(self._shadow_inst_sel)))
                except Exception:
                    pass
        except Exception:
            pass
    def _upload_instanced_mats(self, key: tuple, mats_slice: np.ndarray, sel=None, changed=False) -> moderngl.Buffer:
        try:
            _so = self._shadow_origin
            if _so is not None:
                mats_slice = relativize_chunk_f32(mats_slice, _so)
        except Exception:
            pass
        try:
            fk = self._shadow_frame_key
            if fk is not None and sel is not None:
                try:
                    _so2 = self._shadow_origin
                    _ok2 = None if _so2 is None else (float(_so2[0]), float(_so2[1]), float(_so2[2]))
                except Exception:
                    _ok2 = None
                rec = self._shadow_inst_sel.get(key)
                if rec is not None and len(rec) == 3 and rec[0] == fk and rec[1] == _ok2 and rec[2].shape == sel.shape and bool((rec[2] == sel).all()):
                    cached = self._shadow_inst_vbo.get(key)
                    if cached is not None:
                        return cached
        except Exception:
            pass
        data = mats_slice.tobytes()
        if changed:
            try:
                self._shadow_inst_vbo_fp[key] = data
            except Exception:
                pass
        else:
            try:
                prev = self._shadow_inst_vbo_fp.get(key)
            except Exception:
                prev = None
            if prev is not None and prev == data:
                try:
                    cached = self._shadow_inst_vbo.get(key)
                    if cached is not None and cached.size >= len(data):
                        self._remember_inst_sel(key, sel)
                        return cached
                except Exception:
                    pass
        cached = self._shadow_inst_vbo.get(key)
        if cached is not None:
            try:
                if cached.size >= len(data):
                    cached.write(data)
                    try:
                        self._shadow_inst_vbo_fp[key] = data
                    except Exception:
                        pass
                    self._remember_inst_sel(key, sel)
                    return cached
            except Exception:
                pass
            try:
                cached.release()
            except Exception:
                pass
            self._shadow_inst_vbo.pop(key, None)
            try:
                self._drop_shadow_vaos(key[0], key[1])
            except Exception:
                pass
        vbo = self._ctx.buffer(data)
        if len(self._shadow_inst_vbo) >= 2048:
            try:
                _k, _v = next(iter(self._shadow_inst_vbo.items()))
                if _k != key:
                    self._shadow_inst_vbo.pop(_k, None); self._shadow_inst_vbo_fp.pop(_k, None); self._shadow_inst_sel.pop(_k, None)
                    try:
                        self._drop_shadow_vaos(_k[0], _k[1])
                    except Exception:
                        pass
                    try:
                        _v.release()
                    except Exception:
                        pass
            except Exception:
                pass
        self._shadow_inst_vbo[key] = vbo
        try:
            self._shadow_inst_vbo_fp[key] = data
        except Exception:
            pass
        self._remember_inst_sel(key, sel)
        return vbo
    def _build_shadow_instance_vbo(self, key: tuple, model_matrices) -> moderngl.Buffer:
        if not isinstance(model_matrices, np.ndarray):
            try:
                _so = self._shadow_origin
                if _so is not None:
                    from core.renderer.origin import relativize_models
                    model_matrices = relativize_models(list(model_matrices), _so)
            except Exception:
                pass
        if isinstance(model_matrices, np.ndarray):
            return self._upload_instanced_mats(key, np.ascontiguousarray(model_matrices, dtype=np.float32))
        n = len(model_matrices)
        self._ensure_model_pack_buf(n)
        if pack_model_matrices_f32 is not None:
            try:
                pack_model_matrices_f32(model_matrices, self._model_pack_buf)
                data = self._model_pack_buf[:n * 16].tobytes()
            except Exception:
                try:
                    from core._render_utils import batch_mat4_to_f32_flat
                    data = batch_mat4_to_f32_flat(model_matrices).tobytes()
                except ImportError:
                    data = Mat4.batch_to_f32(model_matrices).tobytes()
        else:
            try:
                from core._render_utils import batch_mat4_to_f32_flat
                data = batch_mat4_to_f32_flat(model_matrices).tobytes()
            except ImportError:
                data = Mat4.batch_to_f32(model_matrices).tobytes()
        cached = self._shadow_inst_vbo.get(key)
        if cached is not None:
            try:
                if cached.size >= len(data):
                    cached.write(data)
                    return cached
            except Exception:
                pass
            try:
                cached.release()
            except Exception:
                pass
            self._shadow_inst_vbo.pop(key, None)
            try:
                self._drop_shadow_vaos(key[0], key[1])
            except Exception:
                pass
        vbo = self._ctx.buffer(data)
        self._shadow_inst_vbo[key] = vbo
        return vbo
    def _resolve_shadow_vbo(self, mesh):
        svbo = getattr(mesh, '_shadow_vbo', None)
        if svbo is not None:
            return svbo
        verts = getattr(mesh, 'vertices', None)
        if verts is None or len(verts) == 0:
            raise ValueError("empty mesh")
        data = np.ascontiguousarray(np.asarray(verts, dtype=np.float32).reshape(-1, 3)).tobytes()
        svbo = self._ctx.buffer(data)
        try:
            if getattr(mesh, '_shadow_vbo', None) is None:
                mesh._shadow_vbo = svbo
            else:
                svbo.release(); svbo = mesh._shadow_vbo
        except Exception:
            pass
        return svbo
    def _drop_shadow_vaos(self, mesh_id, prog_id):
        try:
            dead = [k for k in self._shadow_vao_cache if k[0] == mesh_id and k[1] == prog_id]
            for k in dead:
                try:
                    v = self._shadow_vao_cache.pop(k, None)
                    if v is not None:
                        v.release()
                except Exception:
                    pass
        except Exception:
            pass
    def _get_shadow_vao(self, prog: moderngl.Program, mesh, instance_vbo: moderngl.Buffer) -> moderngl.VertexArray:
        try:
            svbo = self._resolve_shadow_vbo(mesh)
            vkey = (id(mesh), id(prog), id(instance_vbo), id(svbo))
        except Exception:
            vkey = None; svbo = None
        if vkey is not None:
            cached = self._shadow_vao_cache.get(vkey)
            if cached is not None:
                return cached
        if svbo is None:
            raise ValueError("empty mesh")
        vao = _make_shadow_instanced_vao(self._ctx, prog, mesh, instance_vbo, svbo)
        if vkey is None:
            return vao
        if len(self._shadow_vao_cache) >= 2048:
            try:
                _k, _v = next(iter(self._shadow_vao_cache.items()))
                self._shadow_vao_cache.pop(_k, None)
                try:
                    _v.release()
                except Exception:
                    pass
            except Exception:
                pass
        self._shadow_vao_cache[vkey] = vao
        return vao
