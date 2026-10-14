# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.renderer.meshd.shader_paths import _ENGINE_ROOT, _SHADER_CANDIDATES, _SHADER_SUBDIRS, _find_cache, _find_in_shaders, SHADER_DIR, _resolve_shader_file
from core.renderer.meshd.shader_source import read_shader, _to_pascal, _split_shader_block, _SHADER_NAME_OVERRIDES, read_shader_pair, read_compute_source
from core.renderer.meshd.mesh_state import _MeshState
from core.renderer.meshd.mesh_upload import _MeshUpload
from core.renderer.meshd.mesh_gl import _MeshGl
from core.renderer.meshd.mesh_outline import _MeshOutline


class MeshData(_MeshState, _MeshUpload, _MeshGl, _MeshOutline):

    def make_morphed_clone(self, weights, ctx=None, program=None, outline_prog=None):
        clone = MeshData()
        v2, n2 = self.compute_morph(weights)
        clone.vertices = v2
        clone.normals = n2
        clone.uvs = self.uvs
        clone.indices = self.indices
        clone.colors = self.colors
        clone.is_error_mesh = self.is_error_mesh
        clone.sub_mesh_ranges = list(self.sub_mesh_ranges)
        clone.sub_mesh_names = list(self.sub_mesh_names)
        clone.has_skeleton = self.has_skeleton
        clone.bone_names = list(self.bone_names)
        clone.bone_parents = list(self.bone_parents)
        clone.bone_offset_matrices = list(self.bone_offset_matrices)
        clone.bone_bind_local = list(self.bone_bind_local)
        clone.bone_indices = self.bone_indices
        clone.bone_weights = self.bone_weights
        clone.blendshape_names = list(self.blendshape_names)
        clone.blendshape_index = dict(self.blendshape_index)
        clone.blendshape_vert_indices = list(self.blendshape_vert_indices)
        clone.blendshape_pos_deltas = list(self.blendshape_pos_deltas)
        clone.blendshape_nrm_deltas = list(self.blendshape_nrm_deltas)
        clone.compute_aabb()
        if ctx is not None and program is not None:
            clone.build_gl(ctx, program)
            if outline_prog is not None:
                clone.build_outline_vao(ctx, outline_prog)
        return clone


__all__ = ["_ENGINE_ROOT", "_SHADER_CANDIDATES", "_SHADER_SUBDIRS", "_find_cache", "_find_in_shaders", "SHADER_DIR", "_resolve_shader_file", "read_shader", "_to_pascal", "_split_shader_block", "_SHADER_NAME_OVERRIDES", "read_shader_pair", "read_compute_source", "MeshData"]
