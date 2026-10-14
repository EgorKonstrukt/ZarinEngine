# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.assets.importer.ctypes_types import aiAABB
from core.assets.importer.ctypes_types import aiAnimMesh
from core.assets.importer.ctypes_types import aiBone
from core.assets.importer.ctypes_types import aiColor4D
from core.assets.importer.ctypes_types import aiFace
from core.assets.importer.ctypes_types import aiMatrix4x4
from core.assets.importer.ctypes_types import aiMesh
from core.assets.importer.ctypes_types import aiMeshFull
from core.assets.importer.ctypes_types import aiNode
from core.assets.importer.ctypes_types import aiScene
from core.assets.importer.ctypes_types import aiString
from core.assets.importer.ctypes_types import aiVector2D
from core.assets.importer.ctypes_types import aiVector3D
from core.assets.importer.ctypes_types import aiVertexWeight
from core.assets.importer.ctypes_types import MeshImportData
from core.assets.importer.ctypes_types import _AI_NAME_SIZE
from core.assets.importer.ctypes_types import _BLEND_DELTA_EPS
from core.assets.importer.ctypes_types import _HAS_CYTHON
from core.assets.importer.ctypes_types import _Y_UP_ROTATION
from core.assets.importer.ctypes_types import _ai_matrix_to_np
from core.assets.importer.ctypes_types import _ai_matrix_to_np_full
from core.assets.importer.ctypes_types import _conjugate_to_y_up
from core.assets.importer.ctypes_types import _cy_apply_zup
from core.assets.importer.ctypes_types import _cy_extract_faces
from core.assets.importer.ctypes_types import _cy_parse_obj_chunk
from core.assets.importer.ctypes_types import _cy_smooth_normals
from core.assets.importer.assimp import _ASSIMP_LIB_NAME
from core.assets.importer.assimp import _DLL_PATH
from core.assets.importer.assimp import _PROJECT_ROOT
from core.assets.importer.assimp import _build_node_map
from core.assets.importer.assimp import _decode_assimp_name
from core.assets.importer.assimp import _dll
from core.assets.importer.assimp import _find_project_root
from core.assets.importer.assimp import _get_dll
from core.assets.importer.assimp import _node_world_zup
from core.assets.importer.assimp import _read_name
from core.assets.importer.settings import _MemOrderedDict
from core.assets.importer.settings import _MEM_CACHE_MAX
from core.assets.importer.settings import _OBJ_FAST_MIN_BYTES
from core.assets.importer.settings import _OBJ_FAST_THREADS
from core.assets.importer.settings import _compute_smooth_normals
from core.assets.importer.settings import _generate_planar_uvs
from core.assets.importer.settings import _import_meta_signature
from core.assets.importer.settings import _inflight
from core.assets.importer.settings import _inflight_lock
from core.assets.importer.settings import _mem_cache
from core.assets.importer.settings import _mem_cache_lock
from core.assets.importer.settings import _mem_cache_store
from core.assets.importer.settings import _mem_cache_touch
from core.assets.importer.settings import _obj_apply_gen
from core.assets.importer.settings import _obj_chunk_bounds
from core.assets.importer.settings import _obj_parse_chunk
from core.assets.importer.settings import _obj_weld_slow
from core.assets.importer.settings import _read_mesh_import
from core.assets.importer.settings import _resolve_mesh_import_path
from core.assets.importer.settings import _root_hint
from core.assets.importer.settings import _settings_cache
from core.assets.importer.settings import _settings_cache_lock
from core.assets.importer.material import _read_material_name
from core.assets.importer.material import _get_asset_pool
from core.assets.importer.material import gif_frames_to_flipbook
from core.assets.importer.material import import_gif_to_flipbook
from core.assets.importer.material import import_gif_to_flipbook_async
from core.assets.importer.material import load_gif_frames
from core.assets.importer.anim import _align_skeleton_to_mesh
from core.assets.importer.anim import _bone_parent_name
from core.assets.importer.anim import _collect_meshes
from core.assets.importer.anim import _finalize_blendshapes
from core.assets.importer.anim import _finalize_skeleton
from core.assets.importer.anim import _read_anim_meshes
from core.assets.importer.anim import _read_bones
from core.assets.importer.anim import _SkeletonCtx
from core.assets.importer.mesh import _obj_load_fast
from core.assets.importer.mesh import _get_mesh_import_pool
from core.assets.importer.mesh import _obj_load_slow
from core.assets.importer.mesh import _obj_parse_fast
from core.assets.importer.mesh import _obj_weld
from core.assets.importer.mesh import load_mesh
from core.assets.importer.mesh import load_mesh_async
from core.assets.importer.mesh import load_mesh_future
from core.assets.importer.mesh import load_obj
from core.assets.importer.mesh import load_obj_async
from core.assets.importer.mesh import load_obj_future
__all__ = [
    "aiAABB",
    "aiAnimMesh",
    "aiBone",
    "aiColor4D",
    "aiFace",
    "aiMatrix4x4",
    "aiMesh",
    "aiMeshFull",
    "aiNode",
    "aiScene",
    "aiString",
    "aiVector2D",
    "aiVector3D",
    "aiVertexWeight",
    "MeshImportData",
    "_AI_NAME_SIZE",
    "_BLEND_DELTA_EPS",
    "_HAS_CYTHON",
    "_Y_UP_ROTATION",
    "_ai_matrix_to_np",
    "_ai_matrix_to_np_full",
    "_conjugate_to_y_up",
    "_cy_apply_zup",
    "_cy_extract_faces",
    "_cy_parse_obj_chunk",
    "_cy_smooth_normals",
    "_ASSIMP_LIB_NAME",
    "_DLL_PATH",
    "_PROJECT_ROOT",
    "_build_node_map",
    "_decode_assimp_name",
    "_dll",
    "_find_project_root",
    "_get_dll",
    "_node_world_zup",
    "_read_name",
    "_MEM_CACHE_MAX",
    "_MemOrderedDict",
    "_get_asset_pool",
    "_get_mesh_import_pool",
    "_OBJ_FAST_MIN_BYTES",
    "_OBJ_FAST_THREADS",
    "_compute_smooth_normals",
    "_generate_planar_uvs",
    "_import_meta_signature",
    "_inflight",
    "_inflight_lock",
    "_mem_cache",
    "_mem_cache_lock",
    "_mem_cache_store",
    "_mem_cache_touch",
    "_obj_apply_gen",
    "_obj_chunk_bounds",
    "_obj_parse_chunk",
    "_obj_weld_slow",
    "_read_mesh_import",
    "_resolve_mesh_import_path",
    "_root_hint",
    "_settings_cache",
    "_settings_cache_lock",
    "_read_material_name",
    "gif_frames_to_flipbook",
    "import_gif_to_flipbook",
    "import_gif_to_flipbook_async",
    "load_gif_frames",
    "_align_skeleton_to_mesh",
    "_bone_parent_name",
    "_collect_meshes",
    "_finalize_blendshapes",
    "_finalize_skeleton",
    "_read_anim_meshes",
    "_read_bones",
    "_SkeletonCtx",
    "_obj_load_fast",
    "_obj_load_slow",
    "_obj_parse_fast",
    "_obj_weld",
    "load_mesh",
    "load_mesh_async",
    "load_mesh_future",
    "load_obj",
    "load_obj_async",
    "load_obj_future",
]
