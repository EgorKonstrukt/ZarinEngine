# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np
import moderngl
from core.maths.math3d import Mat4
from core.renderer.gpu_culling import WORLD_MATRIX_BINDING, INDEX_BINDING
from core.renderer.origin import origin_for, relativize_model_f32, relativize_models

try:
    from core._render_utils import batch_mat4_to_f32_flat as _batch_f32_flat
except Exception:
    _batch_f32_flat = None
try:
    from core._render_utils import batch_mat4_to_f32_flat_origin as _batch_f32_flat_origin
except Exception:
    _batch_f32_flat_origin = None

_INSTANCE_ATTRS = ("in_model0", "in_model1", "in_model2", "in_model3")

_INITIAL_INST_VBO_CAPACITY = 8192
_MAX_VAO_CACHE = 1024
_MAX_GROUP_VBOS = 256

_INSTANCING_CACHE: dict[int, bool] = {}


def _supports_instancing(prog: moderngl.Program) -> bool:
    pid = id(prog)
    cached = _INSTANCING_CACHE.get(pid)
    if cached is not None:
        return cached
    try:
        locs = prog._attribute_locations
        for a in _INSTANCE_ATTRS:
            if locs.get(a, -1) < 0:
                _INSTANCING_CACHE[pid] = False
                return False
        _INSTANCING_CACHE[pid] = True
        return True
    except Exception:
        _INSTANCING_CACHE[pid] = False
        return False


def _make_instanced_vao(ctx: moderngl.Context, prog: moderngl.Program,
                        mesh, instance_vbo: moderngl.Buffer) -> moderngl.VertexArray:
    vbo = getattr(mesh, '_vbo', None)
    ibo = getattr(mesh, '_ibo', None)
    if vbo is None:
        n_verts = len(mesh.vertices) // 3 if len(mesh.vertices) > 0 else 0
        if n_verts <= 0:
            raise ValueError("empty mesh")
        data = np.zeros((n_verts, 8), dtype=np.float32)
        data[:, 0:3] = mesh.vertices.reshape(-1, 3)
        if len(mesh.normals) == len(mesh.vertices):
            data[:, 3:6] = mesh.normals.reshape(-1, 3)
        if len(mesh.uvs) * 3 == len(mesh.vertices) * 2:
            data[:, 6:8] = mesh.uvs.reshape(-1, 2)
        vbo = ctx.buffer(data.tobytes())
        try:
            if getattr(mesh, '_vbo', None) is None:
                mesh._vbo = vbo
            else:
                vbo.release()
                vbo = mesh._vbo
        except Exception:
            pass
    content = [
        (vbo, '3f 3f 2f', 'in_position', 'in_normal', 'in_uv'),
    ]
    if "in_color" in prog:
        n_verts = len(mesh.vertices) // 3 if len(mesh.vertices) > 0 else vbo.size // 32
        if n_verts > 0:
            col_vbo = getattr(mesh, '_color_vbo', None)
            need = n_verts * 16
            if col_vbo is not None:
                try:
                    if col_vbo.size != need:
                        try:
                            col_vbo.release()
                        except Exception:
                            pass
                        col_vbo = None
                except Exception:
                    col_vbo = None
            if col_vbo is None:
                col_vbo = ctx.buffer(np.full((n_verts, 4), 1.0, dtype=np.float32).tobytes())
                try:
                    mesh._color_vbo = col_vbo
                except Exception:
                    pass
            content.append((col_vbo, '4f', 'in_color'))
    if _supports_instancing(prog):
        content.append((instance_vbo, '4f 4f 4f 4f /i',
                        'in_model0', 'in_model1', 'in_model2', 'in_model3'))
    if ibo is not None:
        return ctx.vertex_array(prog, content, ibo)
    return ctx.vertex_array(prog, content)


class InstanceMixin:

    def _ensure_index_buffer(self, n: int) -> moderngl.Buffer:
        needed = n * 4
        if self._index_buf is not None and self._index_buf_capacity >= needed:
            return self._index_buf
        if self._index_buf:
            try:
                self._index_buf.release()
            except Exception:
                pass
        self._index_buf = self._ctx.buffer(reserve=needed + 64)
        self._index_buf_capacity = needed + 64
        return self._index_buf

    def _write_shared_vbo(self, matrices, origin=None):
        n = len(matrices)
        if n == 0:
            return self._shared_inst_vbo
        needed_cap = n
        if needed_cap > self._inst_vbo_capacity:
            new_cap = self._inst_vbo_capacity
            while new_cap < needed_cap:
                new_cap <<= 1
            try:
                self._shared_inst_vbo.release()
            except Exception:
                pass
            self._inst_vbo_capacity = new_cap
            self._shared_inst_vbo = self._ctx.buffer(reserve=new_cap * 64)
            for vao in self._vao_cache.values():
                try:
                    vao.release()
                except Exception:
                    pass
            self._vao_cache.clear()
        return self._fill_inst_vbo(self._shared_inst_vbo, matrices, origin)

    def _get_vao(self, prog: moderngl.Program, mesh, inst_vbo=None) -> moderngl.VertexArray:
        try:
            gpu_ver = int(getattr(mesh, "_gpu_version", 0) or 0)
        except Exception:
            gpu_ver = 0
        try:
            vbo_id = id(getattr(mesh, "_vbo", None))
            ibo_id = id(getattr(mesh, "_ibo", None))
        except Exception:
            vbo_id = 0
            ibo_id = 0
        if inst_vbo is None:
            inst_vbo = self._shared_inst_vbo
        try:
            inst_id = id(inst_vbo)
        except Exception:
            inst_id = 0
        key = (id(mesh), id(prog), gpu_ver, vbo_id, ibo_id, inst_id)
        cached = self._vao_cache.get(key)
        if cached is not None:
            self._vao_cache.move_to_end(key)
            return cached
        vao = _make_instanced_vao(self._ctx, prog, mesh, inst_vbo)
        self._vao_cache[key] = vao
        if len(self._vao_cache) > _MAX_VAO_CACHE:
            _, old_vao = self._vao_cache.popitem(last=False)
            try:
                old_vao.release()
            except Exception:
                pass
        return vao

    def _drop_vaos_for_inst_vbo(self, vbo):
        try:
            vid = id(vbo)
        except Exception:
            return
        for k in list(self._vao_cache.keys()):
            try:
                if len(k) > 5 and k[5] == vid:
                    old = self._vao_cache.pop(k, None)
                    if old is not None:
                        try:
                            old.release()
                        except Exception:
                            pass
            except Exception:
                pass

    def _ensure_group_vbo(self, key, n: int):
        ent = self._group_vbos.get(key)
        if ent is not None:
            vbo, cap = ent
            if cap >= n:
                return vbo
            self._drop_vaos_for_inst_vbo(vbo)
            try:
                vbo.release()
            except Exception:
                pass
            new_cap = cap if cap else 64
            while new_cap < n:
                new_cap <<= 1
            vbo = self._ctx.buffer(reserve=new_cap * 64)
            self._group_vbos[key] = (vbo, new_cap)
            self._group_upload_state.pop(key, None)
            return vbo
        if len(self._group_vbos) >= _MAX_GROUP_VBOS:
            try:
                old_key = next(iter(self._group_vbos))
                old_vbo, _ = self._group_vbos.pop(old_key)
                self._drop_vaos_for_inst_vbo(old_vbo)
                try:
                    old_vbo.release()
                except Exception:
                    pass
                self._group_upload_state.pop(old_key, None)
            except Exception:
                pass
        cap = 64
        while cap < n:
            cap <<= 1
        vbo = self._ctx.buffer(reserve=cap * 64)
        self._group_vbos[key] = (vbo, cap)
        return vbo

    def _fill_inst_vbo(self, vbo, matrices, origin=None):
        n = len(matrices)
        if n == 0:
            return vbo
        if origin is not None:
            if _batch_f32_flat_origin is not None:
                try:
                    flat = _batch_f32_flat_origin(matrices, float(origin[0]), float(origin[1]), float(origin[2]))
                    try:
                        vbo.orphan()
                    except Exception:
                        pass
                    vbo.write(flat)
                    return vbo
                except Exception:
                    pass
            else:
                try:
                    matrices = relativize_models(matrices, origin)
                except Exception:
                    pass
                try:
                    vbo.orphan()
                except Exception:
                    pass
                vbo.write(Mat4.batch_to_f32(matrices))
                return vbo
            try:
                matrices = relativize_models(matrices, origin)
            except Exception:
                pass
        if _batch_f32_flat is not None:
            try:
                flat = _batch_f32_flat(matrices)
                try:
                    vbo.orphan()
                except Exception:
                    pass
                vbo.write(flat)
                return vbo
            except Exception:
                pass
        try:
            vbo.orphan()
        except Exception:
            pass
        vbo.write(Mat4.batch_to_f32(matrices))
        return vbo

    def _write_group_vbo(self, key, matrices, origin=None):
        n = len(matrices)
        if n == 0:
            return None
        vbo = self._ensure_group_vbo(key, n)
        return self._fill_inst_vbo(vbo, matrices, origin)

    def patch_group_vbo(self, key, patches, origin=None) -> bool:
        try:
            ent = self._group_vbos.get(key)
        except Exception:
            return False
        if ent is None:
            return False
        vbo, cap = ent
        if vbo is None:
            return False
        ok = True
        for idx, mat in patches:
            try:
                ii = int(idx)
            except Exception:
                ok = False
                continue
            if ii < 0 or ii >= cap:
                ok = False
                continue
            try:
                f32 = relativize_model_f32(mat, origin)
            except Exception:
                ok = False
                continue
            try:
                vbo.write(f32, offset=ii * 64)
            except Exception:
                try:
                    vbo.write(f32.tobytes(), offset=ii * 64)
                except Exception:
                    ok = False
        return ok

    def _write_indirect_command(self, count: int, instance_count: int,
                                first_index: int):
        if self._indirect_buf is None or self._indirect_buf_capacity < 32:
            if self._indirect_buf:
                try:
                    self._indirect_buf.release()
                except Exception:
                    pass
            self._indirect_buf = self._ctx.buffer(reserve=64)
            self._indirect_buf_capacity = 64
        cmd = np.array([count, instance_count, first_index, 0, 0],
                       dtype=np.uint32)
        self._indirect_buf.write(cmd.tobytes())

    def _try_render_gpu_driven(self, group, prog, mesh, mat,
                               view_f32, proj_f32, cam_pos, lights,
                               disable_shadows, set_scene_uniforms_fn,
                               apply_material_fn, gpu_storage,
                               set_scene=True, transparent_pass=False) -> bool:
        try:
            model_mats = [item[6] for item in group]
            n = len(model_mats)
            bounding_radii = np.full(n, mesh.bounding_radius, dtype=np.float64)
            self._gpu_version += 1
            gpu_storage.upload_world_matrices(model_mats, bounding_radii,
                                              self._gpu_version, origin_for(cam_pos))
            world_ssbo = gpu_storage.get_world_matrix_ssbo()
            if world_ssbo is None:
                return False
            indices_ssbo = gpu_storage.cull_and_get_indices(
                view_f32, proj_f32, world_ssbo, self._gpu_version)
            if indices_ssbo is None:
                return False
            visible = gpu_storage.last_visible_count
            if visible <= 0:
                self._stats_draw_calls += 1
                return True
            names = self._uniform_names(prog)
            world_ssbo.bind_to_storage_buffer(WORLD_MATRIX_BINDING)
            indices_ssbo.bind_to_storage_buffer(INDEX_BINDING)
            if "u_use_instancing" in names:
                prog["u_use_instancing"].value = 3
            if "u_use_skinning" in names:
                prog["u_use_skinning"].value = 0
            ds = bool(mat.properties.get("double_sided") or mat.properties.get("_double_sided")) if mat else False
            cull_on = bool(self._ctx.cull_face)
            two_pass = bool(ds and cull_on and transparent_pass)
            if ds and cull_on and not two_pass:
                self._ctx.disable(moderngl.CULL_FACE)
            if "u_double_sided" in names:
                try:
                    prog["u_double_sided"].value = 1 if ds else 0
                except Exception:
                    pass
            try:
                if set_scene:
                    set_scene_uniforms_fn(prog, view_f32, proj_f32, cam_pos,
                                          lights, disable_shadows=disable_shadows)
                apply_material_fn(mat, prog, group[0][3])
                ranges = mesh.sub_mesh_ranges
                sub_idx = group[0][7]
                if ranges and sub_idx >= 0 and sub_idx < len(ranges):
                    start, count = ranges[sub_idx]
                else:
                    start, count = 0, (len(mesh.indices) if hasattr(mesh, "indices") else 0)
                if count <= 0:
                    return False
                self._write_indirect_command(count, visible, start)
                vao = self._get_vao(prog, mesh)
                if two_pass:
                    try:
                        self._ctx.cull_face = "front"
                    except Exception:
                        pass
                    vao.render_indirect(self._indirect_buf, moderngl.TRIANGLES, 1, 0)
                    try:
                        self._ctx.cull_face = "back"
                    except Exception:
                        pass
                    vao.render_indirect(self._indirect_buf, moderngl.TRIANGLES, 1, 0)
                    self._stats_draw_calls += 2
                else:
                    vao.render_indirect(self._indirect_buf, moderngl.TRIANGLES, 1, 0)
                    self._stats_draw_calls += 1
                self._stats_instanced += visible
                return True
            finally:
                if two_pass:
                    try:
                        self._ctx.cull_face = "back"
                    except Exception:
                        pass
                    try:
                        self._ctx.enable(moderngl.CULL_FACE)
                    except Exception:
                        pass
                elif ds and cull_on:
                    self._ctx.enable(moderngl.CULL_FACE)
        except Exception as e:
            print(f"[batcher] gpu-driven draw failed, falling back to CPU: {e!r}")
            return False
