# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import time
import numpy as np
import moderngl
from typing import Optional
from collections import OrderedDict
from core.renderer.gpu_culling import WORLD_MATRIX_BINDING, INDEX_BINDING
from core.renderer.origin import origin_for, relativize_model_f32
from core.renderer.batch.groups import GroupsMixin, _frustum_cull_instances
from core.renderer.batch.instance import InstanceMixin, _supports_instancing, _INITIAL_INST_VBO_CAPACITY


def resolve_normal_matrix(cache: dict, ent_id: int, model_d) -> np.ndarray:
    try:
        key = model_d[:3, :3].tobytes()
    except Exception:
        key = None
    if key is not None:
        cached = cache.get(ent_id)
        if cached is not None:
            old_key, nm = cached
            if old_key == key:
                return nm
    from core.math_helpers import mat4_normal_matrix
    try:
        nm = mat4_normal_matrix(model_d)
    except Exception:
        nm = np.eye(3, dtype=np.float32).T
    if len(cache) >= 4096:
        try:
            cache.pop(next(iter(cache)))
        except Exception:
            cache.clear()
    cache[ent_id] = (key, nm)
    return nm


class RenderBatcher(GroupsMixin, InstanceMixin):

    def __init__(self, ctx: moderngl.Context, default_prog: moderngl.Program,
                 gpu_driven_min_instances: int = 4):
        self._ctx = ctx
        self._default_prog = self._ensure_instancing_prog(default_prog)
        self._vao_cache: OrderedDict[tuple[int, int], moderngl.VertexArray] = OrderedDict()
        self._prog_member_cache: dict[int, frozenset] = {}
        self._inst_vbo_capacity: int = _INITIAL_INST_VBO_CAPACITY
        self._shared_inst_vbo = ctx.buffer(reserve=_INITIAL_INST_VBO_CAPACITY * 64)
        self._index_buf: Optional[moderngl.Buffer] = None
        self._index_buf_capacity: int = 0
        self._indirect_buf: Optional[moderngl.Buffer] = None
        self._indirect_buf_capacity: int = 0
        self._gpu_driven_min_instances: int = gpu_driven_min_instances
        self._gpu_version: int = 0
        self._stats_batches: int = 0
        self._stats_draw_calls: int = 0
        self._stats_instanced: int = 0
        self._total_instances: int = 0
        self._frustum_planes_cache = None
        self._frustum_cache_key = None
        self._groups_cache_key = None
        self._groups_cache_val = None
        self._groups_topology = None
        self._group_vbos: dict = {}
        self._group_upload_state: dict = {}
        self._last_view_f32 = None
        self._last_proj_f32 = None
        self._last_cam_pos = None
        self._last_lights_key = None
        self._uniform_cache: dict[int, bytes] = {}

    @staticmethod
    def _ensure_instancing_prog(prog: moderngl.Program) -> moderngl.Program:
        if _supports_instancing(prog):
            return prog
        try:
            from core.renderer.meshd import read_shader_pair
            from core.renderer.shaderp import program_with_fallback
            vert, frag = read_shader_pair("default")
            new_prog = program_with_fallback(prog.ctx, vert, frag, label="default")
            if new_prog is not None and _supports_instancing(new_prog):
                return new_prog
        except Exception:
            pass
        return prog

    def reset_stats(self):
        self._stats_batches = 0
        self._stats_draw_calls = 0
        self._stats_instanced = 0

    def _uniform_names(self, prog: moderngl.Program) -> frozenset:
        key = id(prog)
        cached = self._prog_member_cache.get(key)
        if cached is not None:
            return cached
        names = frozenset(prog)
        self._prog_member_cache[key] = names
        return names

    def _render_instanced(self, group, prog, mesh, mat,
                          view_f32, proj_f32, cam_pos, lights,
                          disable_shadows, set_scene_uniforms_fn,
                          apply_material_fn,
                          selected_entities, outline_queue,
                          gpu_storage=None, set_scene=True, skip_upload=False,
                          group_key=None, group_patches=None, group_skip=False,
                          transparent_pass=False):
        names = self._uniform_names(prog)
        if not skip_upload and (gpu_storage is not None and gpu_storage.is_gpu_driven()
                and len(group) >= self._gpu_driven_min_instances
                and self._try_render_gpu_driven(
                    group, prog, mesh, mat, view_f32, proj_f32, cam_pos,
                    lights, disable_shadows, set_scene_uniforms_fn,
                    apply_material_fn, gpu_storage, set_scene=set_scene,
                    transparent_pass=transparent_pass)):
            return
        if gpu_storage is not None and gpu_storage.is_gpu_driven():
            frustum_planes = self._get_frustum_planes(view_f32, proj_f32)
            group = _frustum_cull_instances(group, frustum_planes,
                                            mesh.bounding_radius)
            if len(group) == 0:
                self._stats_draw_calls += 1
                return
        world_ssbo = gpu_storage.get_world_matrix_ssbo() if gpu_storage else None
        if world_ssbo is not None:
            if skip_upload:
                idx_buf = self._ensure_index_buffer(len(group))
                idx_buf.write(np.arange(len(group), dtype=np.uint32).tobytes())
                world_ssbo.bind_to_storage_buffer(WORLD_MATRIX_BINDING)
                idx_buf.bind_to_storage_buffer(INDEX_BINDING)
                if "u_use_instancing" in names:
                    prog["u_use_instancing"].value = 2
            else:
                model_mats = [item[6] for item in group]
                bounding_radii = np.full(len(model_mats), mesh.bounding_radius,
                                         dtype=np.float64)
                gpu_storage.upload_world_matrices(model_mats, bounding_radii,
                                                  self._gpu_version, origin_for(cam_pos))
                indices = np.arange(len(model_mats), dtype=np.uint32)
                idx_buf = self._ensure_index_buffer(len(indices))
                idx_buf.write(indices.tobytes())
                world_ssbo.bind_to_storage_buffer(WORLD_MATRIX_BINDING)
                idx_buf.bind_to_storage_buffer(INDEX_BINDING)
                if "u_use_instancing" in names:
                    prog["u_use_instancing"].value = 2
            inst_vbo = self._shared_inst_vbo
        elif group_key is not None:
            _org = origin_for(cam_pos)
            try:
                if _org is None:
                    _org_key = None
                else:
                    _org_key = (float(_org[0]), float(_org[1]), float(_org[2]))
            except Exception:
                _org_key = None
            _ng = len(group)
            _vbo = None
            try:
                _st = self._group_upload_state.get(group_key)
            except Exception:
                _st = None
            try:
                _fkey = (_ng, _org_key, id(group[0][6]), id(group[-1][6]))
            except Exception:
                _fkey = (_ng, _org_key, 0, 0)
            if group_patches:
                _vbo = self._ensure_group_vbo(group_key, _ng)
                if self.patch_group_vbo(group_key, group_patches, _org):
                    try:
                        self._group_upload_state[group_key] = _fkey
                    except Exception:
                        pass
                else:
                    _vbo = self._write_group_vbo(group_key, [item[6] for item in group], _org)
                    try:
                        self._group_upload_state[group_key] = _fkey
                    except Exception:
                        pass
            elif group_skip and _st is not None and _st == _fkey:
                try:
                    _vbo = self._group_vbos[group_key][0]
                except Exception:
                    _vbo = None
                if _vbo is None:
                    _vbo = self._write_group_vbo(group_key, [item[6] for item in group], _org)
                    try:
                        self._group_upload_state[group_key] = _fkey
                    except Exception:
                        pass
            else:
                _vbo = self._write_group_vbo(group_key, [item[6] for item in group], _org)
                try:
                    self._group_upload_state[group_key] = _fkey
                except Exception:
                    pass
            if _vbo is None:
                _org2 = origin_for(cam_pos)
                self._write_shared_vbo([item[6] for item in group], _org2)
                _vbo = self._shared_inst_vbo
            inst_vbo = _vbo
            if "u_use_instancing" in names:
                prog["u_use_instancing"].value = 1
        else:
            if not skip_upload:
                _org = origin_for(cam_pos)
                model_mats = [item[6] for item in group]
                self._write_shared_vbo(model_mats, _org)
            if "u_use_instancing" in names:
                prog["u_use_instancing"].value = 1
            inst_vbo = self._shared_inst_vbo
        if "u_use_skinning" in names:
            prog["u_use_skinning"].value = 0
        vao = self._get_vao(prog, mesh, inst_vbo)
        if set_scene:
            set_scene_uniforms_fn(prog, view_f32, proj_f32, cam_pos, lights,
                                  disable_shadows=disable_shadows)
        if mesh.is_error_mesh:
            apply_material_fn(None, prog)
            r = 0.1 + 0.9 * abs(np.sin(time.perf_counter() * 3.0))
            if "u_albedo_color" in names:
                prog["u_albedo_color"].write(np.array([r, 0.0, 0.0, 0.8], dtype=np.float32).tobytes())
        else:
            apply_material_fn(mat, prog, group[0][3])
        sub_idx = group[0][7]
        ranges = mesh.sub_mesh_ranges
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
        def _draw_inst():
            if ranges and sub_idx >= 0 and sub_idx < len(ranges):
                start, count = ranges[sub_idx]
                vao.render(instances=len(group), vertices=count, first=start)
            else:
                vao.render(instances=len(group))
        try:
            if two_pass:
                try:
                    self._ctx.cull_face = "front"
                except Exception:
                    pass
                _draw_inst()
                try:
                    self._ctx.cull_face = "back"
                except Exception:
                    pass
                _draw_inst()
                self._stats_draw_calls += 1
            else:
                _draw_inst()
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
        self._stats_draw_calls += 1
        self._stats_instanced += len(group)
        if selected_entities:
            for item in group:
                ent, tr, _, _, _, _, wm, _ = item
                if ent in selected_entities:
                    outline_queue.append((mesh, wm))

    def _render_single(self, item, prog, mesh, mat,
                        view_f32, proj_f32, cam_pos, lights,
                        disable_shadows, set_scene_uniforms_fn,
                        apply_material_fn, normal_cache,
                        selected_entities, outline_queue, set_scene=True,
                        transparent_pass=False):
        self._stats_draw_calls += 1
        ent, tr, _, mr, _, _, wm, sub_idx = item
        names = self._uniform_names(prog)
        if "u_use_instancing" in names:
            prog["u_use_instancing"].value = 0
        if "u_use_skinning" in names:
            prog["u_use_skinning"].value = 0
        if set_scene:
            set_scene_uniforms_fn(prog, view_f32, proj_f32, cam_pos, lights,
                                  disable_shadows=disable_shadows)
        model = wm
        model_f32 = relativize_model_f32(model, origin_for(cam_pos))
        if "u_model" in names:
            prog["u_model"].write(model_f32)
        if "u_normal_matrix" in names:
            nm = resolve_normal_matrix(normal_cache, ent._id, model._d)
            prog["u_normal_matrix"].write(nm.tobytes())
        if mesh.is_error_mesh:
            apply_material_fn(None, prog)
            r = 0.1 + 0.9 * abs(np.sin(time.perf_counter() * 3.0))
            if "u_albedo_color" in names:
                prog["u_albedo_color"].write(np.array([r, 0.0, 0.0, 0.8], dtype=np.float32).tobytes())
        else:
            apply_material_fn(mat, prog, mr)
        ranges = mesh.sub_mesh_ranges
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
        def _draw_single():
            if ranges and sub_idx >= 0 and sub_idx < len(ranges):
                start, count = ranges[sub_idx]
                mesh.render_range(prog, start, count)
            else:
                mesh.render(prog)
        try:
            if two_pass:
                try:
                    self._ctx.cull_face = "front"
                except Exception:
                    pass
                _draw_single()
                try:
                    self._ctx.cull_face = "back"
                except Exception:
                    pass
                _draw_single()
                self._stats_draw_calls += 1
            else:
                _draw_single()
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
        if selected_entities and ent in selected_entities:
            outline_queue.append((mesh, wm))

    @property
    def draw_calls(self) -> int:
        return self._stats_draw_calls

    @property
    def batches(self) -> int:
        return self._stats_batches

    @property
    def instanced(self) -> int:
        return self._stats_instanced

    def release(self):
        for vao in self._vao_cache.values():
            try:
                vao.release()
            except Exception:
                pass
        self._vao_cache.clear()
        self._prog_member_cache.clear()
        try:
            for vbo, _ in self._group_vbos.values():
                try:
                    vbo.release()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._group_vbos.clear()
            self._group_upload_state.clear()
        except Exception:
            pass
        if self._shared_inst_vbo:
            try:
                self._shared_inst_vbo.release()
            except Exception:
                pass
            self._shared_inst_vbo = None
        if self._index_buf:
            try:
                self._index_buf.release()
            except Exception:
                pass
            self._index_buf = None
        if self._indirect_buf:
            try:
                self._indirect_buf.release()
            except Exception:
                pass
            self._indirect_buf = None
