# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Skinned mesh rendering."""

from __future__ import annotations
import numpy as np
import moderngl
from core.engine.engine import Engine
from core.renderer.batcher import RenderBatcher, resolve_normal_matrix


class SkinnedPassMixin:
    """Skinned mesh rendering."""


    def _ensure_skinned_bone_ssbo(self, n_bones: int):
        needed = max(64, n_bones) * 64
        if self._skinned_bone_ssbo is not None and self._skinned_bone_ssbo_capacity >= needed:
            return
        if self._skinned_bone_ssbo is not None:
            try:
                self._skinned_bone_ssbo.release()
            except Exception:
                pass
        self._skinned_bone_ssbo = self._ctx.buffer(reserve=needed)
        self._skinned_bone_ssbo_capacity = needed


    def _bind_bone_ssbo(self, flat: np.ndarray):
        n = flat.shape[0]
        self._ensure_skinned_bone_ssbo(n)
        data = flat.tobytes()
        if self._skinned_bone_ssbo.size < len(data):
            try:
                self._skinned_bone_ssbo.release()
            except Exception:
                pass
            self._skinned_bone_ssbo = self._ctx.buffer(reserve=len(data) + 64)
            self._skinned_bone_ssbo_capacity = len(data) + 64
        self._skinned_bone_ssbo.write(data)
        self._skinned_bone_ssbo.bind_to_storage_buffer(6)


    def _render_skinned_meshes(self, snap, view_f32, proj_f32, cam_pos, lights):
        eng = Engine.instance()
        scene = eng.scene if eng and hasattr(eng, 'scene') else None
        if scene is None:
            return
        last_prog = None
        skinning_set = False
        skinning_cache = self._skinning_cache
        try:
            _sk_opaque = []
            _sk_trans = []
            for _e in snap.skinned_renderables:
                try:
                    _smr = _e[3]
                    _sub = _e[6] if len(_e) > 6 else 0
                    _mat = self._materials.load_material(_smr.get_material_path(_sub if _sub >= 0 else 0) if _smr else "")
                    if self._materials.mesh_transparency(_smr, _mat):
                        _sk_trans.append(_e)
                    else:
                        _sk_opaque.append(_e)
                except Exception:
                    _sk_opaque.append(_e)
            try:
                _cx = float(cam_pos.x)
                _cy = float(cam_pos.y)
                _cz = float(cam_pos.z)
                _sk_trans.sort(key=lambda e: -(((float(e[4]._d[3, 0]) - _cx) ** 2) + ((float(e[4]._d[3, 1]) - _cy) ** 2) + ((float(e[4]._d[3, 2]) - _cz) ** 2)))
            except Exception:
                pass
            _sk_ordered = _sk_opaque + _sk_trans
            _sk_split = len(_sk_opaque)
        except Exception:
            _sk_ordered = list(snap.skinned_renderables)
            _sk_split = len(_sk_ordered)
        _sk_blend = False
        for _sk_idx, entry in enumerate(_sk_ordered):
            try:
                _want = _sk_idx >= _sk_split and _sk_split < len(_sk_ordered)
            except Exception:
                _want = False
            if _want != _sk_blend:
                _sk_blend = _want
                if _sk_blend:
                    self._scene_fbo.use()
                    self._ctx.enable(moderngl.BLEND)
                    self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                    self._ctx.depth_mask = False
                else:
                    self._ctx.depth_mask = True
                    self._ctx.disable(moderngl.BLEND)
            ent, tr, mesh, smr, wm, armature, sub_idx = entry[:7]
            if armature is None or len(armature.bone_offset_matrices) == 0:
                continue
            cache_key = ent._id
            cached = skinning_cache.get(cache_key)
            if cached is not None:
                flat, n_bones = cached
            else:
                flat, n_bones = armature.compute_skinning_buffer(scene, wm)
                if n_bones > 0:
                    skinning_cache[cache_key] = (flat, n_bones)
            if n_bones == 0:
                continue
            mat = self._materials.load_material(smr.get_material_path(sub_idx if sub_idx >= 0 else 0))
            shader_path = mat.shader_path if mat else ""
            prog = self._shaders.get_or_compile(shader_path) if shader_path else self._default_prog
            if prog is None:
                prog = self._default_prog
            if prog is not last_prog:
                self._set_scene_uniforms(prog, view_f32, proj_f32, cam_pos, lights,
                                          disable_shadows=not smr.receive_shadows)
                last_prog = prog
                skinning_set = False
            names = self._uniform_names(prog)
            if "u_model" in names:
                model_f32 = wm.to_f32()
                prog["u_model"].write(model_f32.tobytes())
            nm = resolve_normal_matrix(self._normal_cache, ent._id, wm._d)
            if "u_normal_matrix" in names:
                prog["u_normal_matrix"].write(nm.tobytes())
            if not skinning_set:
                if "u_use_skinning" in names:
                    prog["u_use_skinning"].value = 1
                skinning_set = True
            if "u_bone_count" in names:
                prog["u_bone_count"].value = int(n_bones)
            self._bind_bone_ssbo(flat)
            self._materials.apply_material(mat, prog, smr)
            if "u_use_instancing" in names:
                prog["u_use_instancing"].value = 0
            if sub_idx >= 0 and mesh.sub_mesh_ranges:
                start, count = mesh.sub_mesh_ranges[sub_idx]
                mesh.render_range(prog, start, count)
            else:
                mesh.render(prog)
        if _sk_blend:
            self._ctx.depth_mask = True
            self._ctx.disable(moderngl.BLEND)
        if last_prog is not None and "u_use_skinning" in last_prog:
            last_prog["u_use_skinning"].value = 0
