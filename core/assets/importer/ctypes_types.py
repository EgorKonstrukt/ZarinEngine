# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import ctypes
import numpy as np
try:
    from core._mesh_import import extract_faces as _cy_extract_faces
    from core._mesh_import import smooth_normals as _cy_smooth_normals
    from core._mesh_import import apply_zup_to_yup as _cy_apply_zup
    _HAS_CYTHON = True
except ImportError:
    _HAS_CYTHON = False
try:
    from core._mesh_import import parse_obj_chunk as _cy_parse_obj_chunk
except ImportError:
    _cy_parse_obj_chunk = None
class aiVector3D(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]
class aiVector2D(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]
class aiColor4D(ctypes.Structure):
    _fields_ = [("r", ctypes.c_float), ("g", ctypes.c_float), ("b", ctypes.c_float), ("a", ctypes.c_float)]
class aiMatrix4x4(ctypes.Structure):
    _fields_ = [
        ("a1", ctypes.c_float), ("a2", ctypes.c_float), ("a3", ctypes.c_float), ("a4", ctypes.c_float),
        ("b1", ctypes.c_float), ("b2", ctypes.c_float), ("b3", ctypes.c_float), ("b4", ctypes.c_float),
        ("c1", ctypes.c_float), ("c2", ctypes.c_float), ("c3", ctypes.c_float), ("c4", ctypes.c_float),
        ("d1", ctypes.c_float), ("d2", ctypes.c_float), ("d3", ctypes.c_float), ("d4", ctypes.c_float),
    ]
class aiString(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("data", ctypes.c_char * 1024)]
_AI_NAME_SIZE = 1028
class aiFace(ctypes.Structure):
    _fields_ = [("mNumIndices", ctypes.c_uint), ("mIndices", ctypes.POINTER(ctypes.c_uint))]
class aiMesh(ctypes.Structure):
    _fields_ = [
        ("mPrimitiveTypes", ctypes.c_uint),
        ("mNumVertices", ctypes.c_uint),
        ("mNumFaces", ctypes.c_uint),
        ("mVertices", ctypes.POINTER(aiVector3D)),
        ("mNormals", ctypes.POINTER(aiVector3D)),
        ("mTangents", ctypes.POINTER(aiVector3D)),
        ("mBitangents", ctypes.POINTER(aiVector3D)),
        ("mColorss", ctypes.POINTER(aiColor4D) * 8),
        ("mTextureCoords", ctypes.POINTER(aiVector3D) * 8),
        ("mNumUVComponents", ctypes.c_uint * 8),
        ("mFaces", ctypes.POINTER(aiFace)),
        ("mNumBones", ctypes.c_uint),
        ("mBones", ctypes.c_void_p),
        ("mMaterialIndex", ctypes.c_uint),
        ("mName", aiString),
    ]
class aiNode(ctypes.Structure):
    _fields_ = [
        ("mName", aiString),
        ("mTransformation", aiMatrix4x4),
        ("mParent", ctypes.c_void_p),
        ("mNumChildren", ctypes.c_uint),
        ("mChildren", ctypes.c_void_p),
        ("mNumMeshes", ctypes.c_uint),
        ("mMeshes", ctypes.POINTER(ctypes.c_uint)),
    ]
class aiScene(ctypes.Structure):
    _fields_ = [
        ("mFlags", ctypes.c_uint),
        ("mRootNode", ctypes.c_void_p),
        ("mNumMeshes", ctypes.c_uint),
        ("mMeshes", ctypes.POINTER(ctypes.POINTER(aiMesh))),
        ("mNumMaterials", ctypes.c_uint),
        ("mMaterials", ctypes.c_void_p),
    ]
class aiVertexWeight(ctypes.Structure):
    _fields_ = [
        ("mVertexId", ctypes.c_uint),
        ("mWeight", ctypes.c_float),
    ]
class aiBone(ctypes.Structure):
    _fields_ = [
        ("mName", aiString),
        ("mNumWeights", ctypes.c_uint),
        ("mArmature", ctypes.c_void_p),
        ("mNode", ctypes.c_void_p),
        ("mWeights", ctypes.POINTER(aiVertexWeight)),
        ("mOffsetMatrix", aiMatrix4x4),
    ]
class aiAABB(ctypes.Structure):
    _fields_ = [("mMin", aiVector3D), ("mMax", aiVector3D)]
class aiAnimMesh(ctypes.Structure):
    _fields_ = [
        ("mName", aiString),
        ("mVertices", ctypes.POINTER(aiVector3D)),
        ("mNormals", ctypes.POINTER(aiVector3D)),
        ("mTangents", ctypes.POINTER(aiVector3D)),
        ("mBitangents", ctypes.POINTER(aiVector3D)),
        ("mColors", ctypes.POINTER(aiColor4D) * 8),
        ("mTextureCoords", ctypes.POINTER(aiVector3D) * 8),
        ("mNumVertices", ctypes.c_uint),
        ("mWeight", ctypes.c_float),
    ]
class aiMeshFull(ctypes.Structure):
    _fields_ = [
        ("mPrimitiveTypes", ctypes.c_uint),
        ("mNumVertices", ctypes.c_uint),
        ("mNumFaces", ctypes.c_uint),
        ("mVertices", ctypes.POINTER(aiVector3D)),
        ("mNormals", ctypes.POINTER(aiVector3D)),
        ("mTangents", ctypes.POINTER(aiVector3D)),
        ("mBitangents", ctypes.POINTER(aiVector3D)),
        ("mColors", ctypes.POINTER(aiColor4D) * 8),
        ("mTextureCoords", ctypes.POINTER(aiVector3D) * 8),
        ("mNumUVComponents", ctypes.c_uint * 8),
        ("mFaces", ctypes.POINTER(aiFace)),
        ("mNumBones", ctypes.c_uint),
        ("mBones", ctypes.c_void_p),
        ("mMaterialIndex", ctypes.c_uint),
        ("mName", aiString),
        ("mNumAnimMeshes", ctypes.c_uint),
        ("mAnimMeshes", ctypes.POINTER(ctypes.c_void_p)),
        ("mMethod", ctypes.c_int),
        ("mAABB", aiAABB),
        ("mTextureCoordsNames", ctypes.c_void_p),
    ]
_BLEND_DELTA_EPS = 1e-7
_Y_UP_ROTATION = np.array([
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
], dtype=np.float32)
def _ai_matrix_to_np(m: aiMatrix4x4) -> np.ndarray:
    return _ai_matrix_to_np_full(m)
def _ai_matrix_to_np_full(m: aiMatrix4x4) -> np.ndarray:
    return np.array([
        [m.a1, m.b1, m.c1, m.d1],
        [m.a2, m.b2, m.c2, m.d2],
        [m.a3, m.b3, m.c3, m.d3],
        [m.a4, m.b4, m.c4, m.d4],
    ], dtype=np.float32)
def _conjugate_to_y_up(mat_zup: np.ndarray) -> np.ndarray:
    r = _Y_UP_ROTATION
    return r @ mat_zup @ r.T
class MeshImportData:
    def __init__(self):
        self.name: str = ""
        self.vertices: np.ndarray = np.array([], dtype=np.float32)
        self.normals: np.ndarray = np.array([], dtype=np.float32)
        self.uvs: np.ndarray = np.array([], dtype=np.float32)
        self.indices: np.ndarray = np.array([], dtype=np.uint32)
        self.is_error_mesh: bool = False
        self.sub_mesh_ranges: list[tuple[int, int]] = []
        self.sub_mesh_names: list[str] = []
        self.has_skeleton: bool = False
        self.bone_names: list[str] = []
        self.bone_parents: list[int] = []
        self.bone_offset_matrices: list[np.ndarray] = []
        self.bone_bind_world: list[np.ndarray] = []
        self.bone_bind_local: list[np.ndarray] = []
        self.bone_indices: np.ndarray = np.zeros((0, 4), dtype=np.int32)
        self.bone_weights: np.ndarray = np.zeros((0, 4), dtype=np.float32)
        self.blendshape_names: list[str] = []
        self.blendshape_indices: list[np.ndarray] = []
        self.blendshape_positions: list[np.ndarray] = []
        self.blendshape_normals: list[np.ndarray] = []
