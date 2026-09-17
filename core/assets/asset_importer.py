# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import sys
import os
import json
import hashlib
import ctypes
import threading
from asyncio import Future
import numpy as np
from typing import Optional, Callable
from core.ecs.pool import asset as _get_asset_pool
from core.ecs.pool import mesh_import as _get_mesh_import_pool

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

_inflight_lock = threading.Lock()
_inflight: dict[str, Future] = {}
_mem_cache_lock = threading.Lock()
_mem_cache: dict[str, MeshImportData] = {}

if sys.platform == "win32":
    _ASSIMP_LIB_NAME = "assimp-vc143-mt.dll"
else:
    _ASSIMP_LIB_NAME = "libassimp.so.6.0.5"


def _find_project_root():
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(cur) == "core":
            return os.path.dirname(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_PROJECT_ROOT = _find_project_root()
_DLL_PATH = os.path.join(_PROJECT_ROOT, _ASSIMP_LIB_NAME)


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


class _SkeletonCtx:
    __slots__ = (
        "bone_names", "bone_index", "bone_offsets_zup", "influences",
        "mesh_node_world_zup", "has_skeleton", "root_bone_name",
        "ref_world_zup", "ref_world_inv_zup",
        "blend_names", "blend_index", "blend_idx_chunks",
        "blend_pos_chunks", "blend_nrm_chunks", "want_blend",
    )

    def __init__(self):
        self.bone_names: list[str] = []
        self.bone_index: dict[str, int] = {}
        self.bone_offsets_zup: list[np.ndarray] = []
        self.influences: dict[int, list[tuple[int, float]]] = {}
        self.mesh_node_world_zup: Optional[np.ndarray] = None
        self.has_skeleton: bool = False
        self.root_bone_name: str = ""
        self.ref_world_zup: Optional[np.ndarray] = None
        self.ref_world_inv_zup: Optional[np.ndarray] = None
        self.blend_names: list[str] = []
        self.blend_index: dict[str, int] = {}
        self.blend_idx_chunks: list[list[np.ndarray]] = []
        self.blend_pos_chunks: list[list[np.ndarray]] = []
        self.blend_nrm_chunks: list[list[np.ndarray]] = []
        self.want_blend: bool = True


_dll = None


def _get_dll():
    global _dll
    if _dll is not None:
        return _dll

    candidates = [_DLL_PATH, _ASSIMP_LIB_NAME]

    if sys.platform == "win32":
        ctypes.windll.kernel32.SetErrorMode(0x8007)

    for p in candidates:
        try:
            d = ctypes.CDLL(p)
            if hasattr(d, 'aiImportFile'):
                d.aiImportFile.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
                d.aiImportFile.restype = ctypes.POINTER(aiScene)
                d.aiReleaseImport.argtypes = [ctypes.POINTER(aiScene)]
                if hasattr(d, 'aiGetMaterialString'):
                    d.aiGetMaterialString.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                                      ctypes.c_uint, ctypes.c_uint,
                                                      ctypes.POINTER(aiString)]
                    d.aiGetMaterialString.restype = ctypes.c_uint
                _dll = d
                return d
        except Exception:
            pass

    raise RuntimeError("Assimp library not found")


def _read_material_name(scene, mat_idx):
    try:
        if not scene.mMaterials or mat_idx >= scene.mNumMaterials or mat_idx < 0:
            return ""
        dll = _get_dll()
        if not hasattr(dll, 'aiGetMaterialString'):
            return ""
        mats = ctypes.cast(scene.mMaterials, ctypes.POINTER(ctypes.c_void_p))
        s = aiString()
        dll.aiGetMaterialString(ctypes.c_void_p(mats[mat_idx]), b"?mat.name", 0, 0, ctypes.byref(s))
        return s.data.decode("utf-8", "ignore")[:s.length]
    except Exception:
        return ""


def _build_node_map(node_ptr, parent_name, node_map):
    if not node_ptr:
        return
    node = ctypes.cast(node_ptr, ctypes.POINTER(aiNode)).contents
    node_name = _read_name(node.mName)
    try:
        local = _ai_matrix_to_np_full(node.mTransformation)
    except Exception:
        local = np.eye(4, dtype=np.float32)
    node_map[node_name] = (local, parent_name)
    children_ptr = ctypes.cast(node.mChildren, ctypes.POINTER(ctypes.c_void_p * node.mNumChildren))
    for i in range(node.mNumChildren):
        child_addr = children_ptr.contents[i]
        if child_addr:
            _build_node_map(child_addr, node_name, node_map)


def _node_world_zup(node_map, name):
    chain = []
    cur = name
    seen = set()
    while cur is not None and cur in node_map and cur not in seen:
        seen.add(cur)
        local, parent = node_map[cur]
        chain.append(local)
        cur = parent
    m = np.eye(4, dtype=np.float32)
    for part in chain:
        m = m @ part
    return m


def _collect_meshes(node_ptr, scene, mesh_parts, skeleton_ctx, node_map, vert_offset_ref):
    if not node_ptr:
        return
    node = ctypes.cast(node_ptr, ctypes.POINTER(aiNode)).contents
    node_name = _read_name(node.mName)
    node_world_zup = _node_world_zup(node_map, node_name)
    for i in range(node.mNumMeshes):
        mesh_idx = node.mMeshes[i]
        mesh_ptr = scene.mMeshes[mesh_idx]
        if not mesh_ptr:
            continue
        mesh = mesh_ptr.contents
        nv = mesh.mNumVertices
        nf = mesh.mNumFaces
        name = _read_material_name(scene, mesh.mMaterialIndex)
        if not name:
            name = node_name
        if not name:
            try:
                name = _read_name(mesh.mName)
            except Exception:
                name = ""
        if nv == 0 or not mesh.mVertices:
            mesh_parts.append((np.zeros(nv * 3, dtype=np.float32),
                               np.full(nv * 3, 1.0, dtype=np.float32),
                               np.zeros(nv * 2, dtype=np.float32),
                               np.array([], dtype=np.uint32), nv, name))
            vert_offset_ref[0] += nv
            continue
        verts_ptr = ctypes.cast(mesh.mVertices, ctypes.POINTER(aiVector3D * nv)).contents
        verts = np.frombuffer(verts_ptr, dtype=np.float32).copy()
        if mesh.mNormals:
            norms_ptr = ctypes.cast(mesh.mNormals, ctypes.POINTER(aiVector3D * nv)).contents
            norms = np.frombuffer(norms_ptr, dtype=np.float32).copy()
        else:
            norms = np.tile(np.array([0.0, 1.0, 0.0], dtype=np.float32), nv)
        tc = mesh.mTextureCoords[0]
        if tc and mesh.mNumUVComponents[0] >= 2:
            uvs_ptr = ctypes.cast(tc, ctypes.POINTER(aiVector3D * nv)).contents
            uvs_raw = np.frombuffer(uvs_ptr, dtype=np.float32)
            uvs = uvs_raw.reshape(-1, 3)[:, :2].copy().flatten()
        else:
            uvs = np.zeros(nv * 2, dtype=np.float32)
        base_lv = verts.reshape(-1, 3).copy()
        base_ln = norms.reshape(-1, 3).copy()
        if skeleton_ctx.ref_world_zup is None:
            skeleton_ctx.ref_world_zup = node_world_zup.copy()
            try:
                skeleton_ctx.ref_world_inv_zup = np.linalg.inv(node_world_zup)
            except Exception:
                skeleton_ctx.ref_world_inv_zup = np.linalg.pinv(node_world_zup)
        rel_zup = node_world_zup @ skeleton_ctx.ref_world_inv_zup
        if not np.allclose(rel_zup, np.eye(4, dtype=np.float32)):
            v3 = verts.reshape(-1, 3)
            v4 = np.concatenate([v3, np.ones((v3.shape[0], 1), dtype=np.float32)], axis=1)
            verts = (v4 @ rel_zup)[:, :3].astype(np.float32).ravel()
            n3 = norms.reshape(-1, 3) @ rel_zup[:3, :3]
            n_len = np.linalg.norm(n3, axis=1, keepdims=True)
            n_len[n_len == 0] = 1.0
            norms = (n3 / n_len).astype(np.float32).ravel()
        if mesh.mFaces and nf > 0:
            faces_ptr = ctypes.addressof(mesh.mFaces.contents) if mesh.mNumFaces > 0 else 0
            if _HAS_CYTHON and faces_ptr:
                indices = _cy_extract_faces(faces_ptr, nf)
            else:
                faces_arr = ctypes.cast(mesh.mFaces, ctypes.POINTER(aiFace * nf)).contents
                all_idxs = np.empty(nf * 3, dtype=np.uint32)
                idx = 0
                for j in range(nf):
                    face = faces_arr[j]
                    n_idx = face.mNumIndices
                    if n_idx > 0 and face.mIndices:
                        ptr = ctypes.cast(face.mIndices, ctypes.POINTER(ctypes.c_uint * n_idx)).contents
                        for k in range(min(3, n_idx)):
                            all_idxs[idx] = ptr[k]
                            idx += 1
                    else:
                        idx += 3
                indices = all_idxs[:idx]
        else:
            indices = np.array([], dtype=np.uint32)
        vert_offset = vert_offset_ref[0]
        _read_bones(mesh, vert_offset, skeleton_ctx, node_map, node_world_zup)
        if getattr(skeleton_ctx, "want_blend", True):
            try:
                rel33 = rel_zup[:3, :3].astype(np.float32)
            except Exception:
                rel33 = np.eye(3, dtype=np.float32)
            _read_anim_meshes(mesh_ptr, nv, base_lv, base_ln, vert_offset, rel33, skeleton_ctx)
        mesh_parts.append((verts, norms, uvs, indices, nv, name))
        vert_offset_ref[0] += nv
    children_ptr = ctypes.cast(node.mChildren, ctypes.POINTER(ctypes.c_void_p * node.mNumChildren))
    for i in range(node.mNumChildren):
        child_addr = children_ptr.contents[i]
        if child_addr:
            _collect_meshes(child_addr, scene, mesh_parts, skeleton_ctx, node_map, vert_offset_ref)


def _read_name(field) -> str:
    try:
        buf = ctypes.string_at(ctypes.addressof(field), ctypes.sizeof(field))
    except Exception:
        return ""
    n = int.from_bytes(buf[0:4], "little")
    if n <= 0 or n > 1024:
        n = 0
    data = buf[4:4 + n] if n else b""
    return data.split(b"\x00")[0].decode("utf-8", "ignore")


def _decode_assimp_name(field) -> str:
    return _read_name(field)


def _read_bones(mesh, vert_offset, skeleton_ctx, node_map, mesh_node_world_zup):
    if mesh.mNumBones == 0 or not mesh.mBones:
        return
    if skeleton_ctx.mesh_node_world_zup is None:
        skeleton_ctx.mesh_node_world_zup = mesh_node_world_zup
    if skeleton_ctx.ref_world_zup is None:
        skeleton_ctx.ref_world_zup = mesh_node_world_zup.copy()
        try:
            skeleton_ctx.ref_world_inv_zup = np.linalg.inv(mesh_node_world_zup)
        except Exception:
            skeleton_ctx.ref_world_inv_zup = np.linalg.pinv(mesh_node_world_zup)
    try:
        inv_w = np.linalg.inv(mesh_node_world_zup)
    except Exception:
        inv_w = np.linalg.pinv(mesh_node_world_zup)
    ref_w = skeleton_ctx.ref_world_zup
    bones_ptr = ctypes.cast(mesh.mBones, ctypes.POINTER(ctypes.POINTER(aiBone)))
    for b in range(mesh.mNumBones):
        bone = bones_ptr[b].contents
        bname = _decode_assimp_name(bone.mName)
        if not bname:
            continue
        if bname not in skeleton_ctx.bone_index:
            gidx = len(skeleton_ctx.bone_names)
            skeleton_ctx.bone_index[bname] = gidx
            skeleton_ctx.bone_names.append(bname)
            off = _ai_matrix_to_np_full(bone.mOffsetMatrix)
            off = (ref_w @ inv_w @ off).astype(np.float32)
            skeleton_ctx.bone_offsets_zup.append(off)
            skeleton_ctx.has_skeleton = True
        gidx = skeleton_ctx.bone_index[bname]
        w_ptr = ctypes.cast(bone.mWeights, ctypes.POINTER(aiVertexWeight))
        for w in range(bone.mNumWeights):
            vw = w_ptr[w]
            gid = vert_offset + vw.mVertexId
            lst = skeleton_ctx.influences.get(gid)
            if lst is None:
                lst = []
                skeleton_ctx.influences[gid] = lst
            lst.append((gidx, float(vw.mWeight)))


def _read_anim_meshes(mesh_ptr, nv: int, base_verts: np.ndarray, base_norms: np.ndarray,
                      vert_offset: int, rel_3x3: np.ndarray, skeleton_ctx) -> None:
    try:
        full = ctypes.cast(mesh_ptr, ctypes.POINTER(aiMeshFull)).contents
        n_anim = int(full.mNumAnimMeshes)
    except Exception:
        return
    if n_anim <= 0 or n_anim > 10000 or not full.mAnimMeshes:
        return
    try:
        arr = ctypes.cast(full.mAnimMeshes, ctypes.POINTER(ctypes.c_void_p * n_anim)).contents
    except Exception:
        return
    for a in range(n_anim):
        addr = arr[a]
        if not addr:
            continue
        try:
            am = ctypes.cast(addr, ctypes.POINTER(aiAnimMesh)).contents
            anv = int(am.mNumVertices)
            if anv != nv or not am.mVertices:
                continue
            aname = _decode_assimp_name(am.mName)
            if not aname:
                aname = f"blend_{a}"
            av_ptr = ctypes.cast(am.mVertices, ctypes.POINTER(aiVector3D * anv)).contents
            av = np.frombuffer(av_ptr, dtype=np.float32).reshape(-1, 3)
            dp = (av - base_verts) @ rel_3x3
            if am.mNormals:
                an_ptr = ctypes.cast(am.mNormals, ctypes.POINTER(aiVector3D * anv)).contents
                anm = np.frombuffer(an_ptr, dtype=np.float32).reshape(-1, 3)
                dn = (anm - base_norms) @ rel_3x3
            else:
                dn = np.zeros_like(dp)
            mag = np.abs(dp).max(axis=1) + np.abs(dn).max(axis=1)
            mask = mag > _BLEND_DELTA_EPS
            if not bool(mask.any()):
                idx = skeleton_ctx.blend_index.get(aname)
                if idx is None:
                    idx = len(skeleton_ctx.blend_names)
                    skeleton_ctx.blend_index[aname] = idx
                    skeleton_ctx.blend_names.append(aname)
                    skeleton_ctx.blend_idx_chunks.append([])
                    skeleton_ctx.blend_pos_chunks.append([])
                    skeleton_ctx.blend_nrm_chunks.append([])
                continue
            local_ids = np.nonzero(mask)[0].astype(np.int32)
            gids = (local_ids.astype(np.int64) + vert_offset).astype(np.int32)
            pos = dp[mask].astype(np.float32)
            nrm = dn[mask].astype(np.float32)
            idx = skeleton_ctx.blend_index.get(aname)
            if idx is None:
                idx = len(skeleton_ctx.blend_names)
                skeleton_ctx.blend_index[aname] = idx
                skeleton_ctx.blend_names.append(aname)
                skeleton_ctx.blend_idx_chunks.append([])
                skeleton_ctx.blend_pos_chunks.append([])
                skeleton_ctx.blend_nrm_chunks.append([])
            skeleton_ctx.blend_idx_chunks[idx].append(gids)
            skeleton_ctx.blend_pos_chunks[idx].append(pos)
            skeleton_ctx.blend_nrm_chunks[idx].append(nrm)
        except Exception:
            continue


def _bone_parent_name(node_map, name, bone_set):
    if name not in node_map:
        return None
    cur = node_map[name][1]
    seen = set()
    while cur is not None and cur in node_map and cur not in seen:
        seen.add(cur)
        if cur in bone_set:
            return cur
        cur = node_map[cur][1]
    return None


def _finalize_skeleton(skeleton_ctx, node_map, total_verts):
    if not skeleton_ctx.has_skeleton or len(skeleton_ctx.bone_names) == 0:
        return None
    n = len(skeleton_ctx.bone_names)
    r4 = _Y_UP_ROTATION
    offset_yup = [r4 @ off @ r4.T for off in skeleton_ctx.bone_offsets_zup]
    bind_world = []
    for i in range(n):
        try:
            bw = np.linalg.inv(offset_yup[i])
        except Exception:
            bw = np.linalg.pinv(offset_yup[i])
        bind_world.append(bw)
    bone_set = set(skeleton_ctx.bone_names)
    parents = []
    for name in skeleton_ctx.bone_names:
        pn = -1
        cur = node_map.get(name, (None, None))[1] if name in node_map else None
        while cur:
            if cur in bone_set:
                pn = skeleton_ctx.bone_index[cur]
                break
            cur = node_map.get(cur, (None, None))[1] if cur in node_map else None
        parents.append(pn)
    bind_local = []
    for idx in range(n):
        p = parents[idx]
        if p < 0:
            bind_local.append(bind_world[idx])
        else:
            try:
                bind_local.append(bind_world[idx] @ np.linalg.inv(bind_world[p]))
            except Exception:
                bind_local.append(bind_world[idx] @ np.linalg.pinv(bind_world[p]))
    bone_indices = np.zeros((total_verts, 4), dtype=np.int32)
    bone_weights = np.zeros((total_verts, 4), dtype=np.float32)
    for gid, infl in skeleton_ctx.influences.items():
        if gid < 0 or gid >= total_verts:
            continue
        infl.sort(key=lambda x: -x[1])
        top = infl[:4]
        wsum = sum(w for _, w in top)
        if wsum <= 0:
            continue
        for k in range(min(4, len(top))):
            bi, w = top[k]
            bone_indices[gid, k] = bi
            bone_weights[gid, k] = w / wsum
    return {
        "has_skeleton": True,
        "bone_names": skeleton_ctx.bone_names,
        "bone_parents": parents,
        "bone_offset_matrices": offset_yup,
        "bone_bind_world": bind_world,
        "bone_bind_local": bind_local,
        "bone_indices": bone_indices,
        "bone_weights": bone_weights,
    }


def _finalize_blendshapes(skeleton_ctx, total_verts):
    if len(skeleton_ctx.blend_names) == 0:
        return None
    c3 = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0],
    ], dtype=np.float32)
    names: list[str] = []
    all_idx: list[np.ndarray] = []
    all_pos: list[np.ndarray] = []
    all_nrm: list[np.ndarray] = []
    for s in range(len(skeleton_ctx.blend_names)):
        chunks_i = skeleton_ctx.blend_idx_chunks[s]
        chunks_p = skeleton_ctx.blend_pos_chunks[s]
        chunks_n = skeleton_ctx.blend_nrm_chunks[s]
        if not chunks_i:
            names.append(skeleton_ctx.blend_names[s])
            all_idx.append(np.zeros((0,), dtype=np.int32))
            all_pos.append(np.zeros((0, 3), dtype=np.float32))
            all_nrm.append(np.zeros((0, 3), dtype=np.float32))
            continue
        try:
            gi = np.concatenate(chunks_i).astype(np.int32)
            gp = np.concatenate(chunks_p).astype(np.float32)
            gn = np.concatenate(chunks_n).astype(np.float32)
        except Exception:
            continue
        valid = (gi >= 0) & (gi < total_verts)
        if not bool(valid.any()):
            continue
        gi = gi[valid]
        gp = gp[valid] @ c3
        gn = gn[valid] @ c3
        order = np.argsort(gi, kind="stable")
        names.append(skeleton_ctx.blend_names[s])
        all_idx.append(np.ascontiguousarray(gi[order], dtype=np.int32))
        all_pos.append(np.ascontiguousarray(gp[order], dtype=np.float32))
        all_nrm.append(np.ascontiguousarray(gn[order], dtype=np.float32))
    if not names:
        return None
    return {
        "blendshape_names": names,
        "blendshape_indices": all_idx,
        "blendshape_positions": all_pos,
        "blendshape_normals": all_nrm,
    }


def _align_skeleton_to_mesh(skel, verts_yp):
    bw = skel.get("bone_bind_world")
    bl = skel.get("bone_bind_local")
    parents = skel.get("bone_parents")
    if not bw or not bl or verts_yp.size == 0:
        return
    joints = np.array([m[3, :3] for m in bw], dtype=np.float32)
    bone_c = joints.mean(axis=0)
    mesh_c = verts_yp.reshape(-1, 3).mean(axis=0).astype(np.float32)
    g = (mesh_c - bone_c).astype(np.float32)
    if np.max(np.abs(g)) <= 1e-4:
        return
    T = np.eye(4, dtype=np.float32)
    T[3, :3] = g
    n = len(bw)
    new_bl = [m.copy() for m in bl]
    for i in range(n):
        if parents[i] < 0:
            new_bl[i] = new_bl[i] @ T
    new_bw = [m @ T for m in bw]
    skel["bone_bind_local"] = new_bl
    skel["bone_bind_world"] = new_bw
    skel["bone_offset_matrices"] = [np.linalg.inv(m) for m in new_bw]


def _root_hint() -> Optional[str]:
    try:
        from core.engine.engine import Engine
        eng = Engine.instance()
        return eng.project_root if eng and getattr(eng, "project_root", None) else None
    except Exception:
        return None


def _resolve_mesh_import_path(path: str) -> str:
    """Resolve ``<mesh>.import`` for absolute and project-relative mesh paths.

    The inspector stores import settings next to the source mesh (absolute
    ``<mesh>.import``), while scenes keep ``mesh_path`` relative to the
    project root. Relative paths must resolve against that root, not the
    process CWD, otherwise saved parameters are silently ignored.
    """
    direct = path + ".import"
    if os.path.exists(direct):
        return direct
    root = _root_hint() or os.getcwd()
    base = os.path.basename(path)
    candidates = [os.path.join(root, path + ".import")]
    for sub in ["", "assets/", "assets/models/", "models/"]:
        candidates.append(os.path.join(root, sub, path + ".import"))
        candidates.append(os.path.join(root, sub, base + ".import"))
    for c in candidates:
        if os.path.exists(c):
            return os.path.normpath(c)
    return direct


def _import_meta_signature(path: str):
    """(size, content hash) of the resolved `<mesh>.import`, or None when absent.

    Content hashing (instead of mtime) keeps the cache valid when the file is
    copied to another machine with timestamps preserved.
    """
    import_path = _resolve_mesh_import_path(path)
    try:
        if os.path.exists(import_path):
            with open(import_path, "rb") as f:
                raw = f.read()
            return (len(raw), hashlib.sha1(raw).hexdigest()[:16])
    except OSError:
        pass
    return None


_settings_cache_lock = threading.Lock()
_settings_cache: dict = {}


def _read_mesh_import(path: str) -> dict:
    import_path = _resolve_mesh_import_path(path)
    settings = {
        "scale": 1.0,
        "center_pivot": False,
        "flip_uvs": True,
        "smooth_angle": 30.0,
        "gen_normals": True,
        "gen_uvs": True,
        "blendshapes": True,
    }
    try:
        st = os.stat(import_path)
        stat_sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        return settings
    with _settings_cache_lock:
        cached = _settings_cache.get(import_path)
        if cached is not None and cached[0] == stat_sig:
            out = dict(cached[1])
            if isinstance(out.get("materials"), list):
                out["materials"] = list(out["materials"])
            return out
    if os.path.exists(import_path):
        try:
            with open(import_path) as _f:
                _data = json.load(_f)
            for _k in settings:
                if _k in _data:
                    settings[_k] = _data[_k]
            if isinstance(_data.get("materials"), list):
                settings["materials"] = [m for m in _data["materials"] if isinstance(m, str)]
        except Exception:
            pass
    with _settings_cache_lock:
        _settings_cache[import_path] = (stat_sig, dict(settings))
        if len(_settings_cache) > 4096:
            _settings_cache.clear()
            _settings_cache[import_path] = (stat_sig, dict(settings))
    return settings


def _compute_smooth_normals(verts: np.ndarray, indices: np.ndarray) -> np.ndarray:
    if _HAS_CYTHON and len(indices) > 0:
        return _cy_smooth_normals(verts.astype(np.float32), indices.astype(np.uint32))
    n = len(verts)
    normals = np.zeros((n, 3), dtype=np.float32)
    if len(indices) == 0:
        return normals
    tri = verts[indices].reshape(-1, 3, 3)
    f0 = tri[:, 1] - tri[:, 0]
    f1 = tri[:, 2] - tri[:, 0]
    face_n = np.cross(f0, f1)
    lens = np.linalg.norm(face_n, axis=1, keepdims=True)
    lens[lens == 0] = 1.0
    face_n = face_n / lens
    expanded = np.repeat(face_n, 3, axis=0)
    np.add.at(normals, indices, expanded)
    nl = np.linalg.norm(normals, axis=1, keepdims=True)
    nl[nl == 0] = 1.0
    return (normals / nl).astype(np.float32)


def _generate_planar_uvs(verts: np.ndarray) -> np.ndarray:
    if len(verts) == 0:
        return np.zeros((0, 2), dtype=np.float32)
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    span = (maxs - mins)
    span[span == 0] = 1.0
    uvs = (verts - mins) / span
    uvs = uvs[:, :2]
    uvs[:, 1] = 1.0 - uvs[:, 1]
    return uvs.astype(np.float32)


_OBJ_FAST_MIN_BYTES = 2 << 20
_OBJ_FAST_THREADS = min(8, max(4, (os.cpu_count() or 4) // 2))


def _obj_chunk_bounds(data: bytes, nchunks: int) -> list:
    n = len(data)
    bounds = []
    start = 0
    for i in range(1, nchunks):
        cut = (n * i) // nchunks
        nl = data.find(b"\n", cut)
        cut = n if nl < 0 else nl + 1
        bounds.append((start, cut))
        start = cut
        if start >= n:
            break
    bounds.append((start, n))
    return [(s, e) for s, e in bounds if e > s]


def _obj_parse_chunk(chunk: bytes):
    if _cy_parse_obj_chunk is not None:
        try:
            return _cy_parse_obj_chunk(chunk)
        except (ValueError, OverflowError, MemoryError):
            return None
    vbuf = bytearray()
    tbuf = bytearray()
    nbuf = bytearray()
    nv = ntt = nvn = 0
    fp: list = []
    ft: list = []
    fn: list = []
    for line in chunk.split(b"\n"):
        line = line.strip()
        if not line or line[:1] == b"#":
            continue
        c0 = line[:1]
        if c0 == b"v":
            c1 = line[1:2]
            if c1 and c1.isspace():
                vbuf += line[1:]
                vbuf += b" "
                nv += 1
            elif c1 == b"t":
                if line[2:3] and not line[2:3].isspace():
                    continue
                rest = line[2:].strip()
                if not rest:
                    return None
                tbuf += rest
                tbuf += b" "
                ntt += 1
            elif c1 == b"n":
                if line[2:3] and not line[2:3].isspace():
                    continue
                rest = line[2:].strip()
                if not rest:
                    return None
                nbuf += rest
                nbuf += b" "
                nvn += 1
            elif not c1:
                return None
            continue
        if c0 == b"f":
            if line == b"f":
                continue
            if not line[1:2].isspace():
                continue
            toks = line[1:].split()
            if not toks:
                continue
            if len(toks) == 3 and b"//" not in line:
                cells = [t.split(b"/") for t in toks]
                if all(len(c) == 3 and c[0] and c[1] and c[2] for c in cells):
                    for c in cells:
                        fp.append(int(c[0]) - 1)
                        ft.append(int(c[1]) - 1)
                        fn.append(int(c[2]) - 1)
                    continue
            for tok in toks:
                v = tok.split(b"/")
                fp.append(int(v[0]) - 1)
                if len(v) > 1 and v[1]:
                    ft.append(int(v[1]) - 1)
                else:
                    ft.append(-1)
                if len(v) > 2 and v[2]:
                    fn.append(int(v[2]) - 1)
                else:
                    fn.append(-1)
            continue
        continue
    try:
        varr = np.fromstring(bytes(vbuf), dtype=np.float32, sep=" ") if nv else np.zeros(0, dtype=np.float32)
        tarr = np.fromstring(bytes(tbuf), dtype=np.float32, sep=" ") if ntt else np.zeros(0, dtype=np.float32)
        narr = np.fromstring(bytes(nbuf), dtype=np.float32, sep=" ") if nvn else np.zeros(0, dtype=np.float32)
    except (ValueError, TypeError):
        return None
    if varr.size != nv * 3 or tarr.size != ntt * 2 or narr.size != nvn * 3:
        return None
    try:
        return (varr, tarr, narr, np.array(fp, dtype=np.int64),
                np.array(ft, dtype=np.int64), np.array(fn, dtype=np.int64))
    except (ValueError, TypeError, OverflowError):
        return None


def _obj_parse_fast(data: bytes, jobs: int):
    import concurrent.futures as _cf
    if b"\r" in data:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    bounds = _obj_chunk_bounds(data, max(1, jobs))
    if len(bounds) < 2:
        bounds = [(0, len(data))]
    results = []
    if len(bounds) == 1:
        try:
            r = _obj_parse_chunk(data)
        except (ValueError, TypeError, OverflowError, MemoryError):
            return None
        if r is None:
            return None
        results.append(r)
    else:
        try:
            with _cf.ThreadPoolExecutor(max_workers=len(bounds)) as ex:
                futs = [ex.submit(_obj_parse_chunk, data[s:e]) for s, e in bounds]
                for f in futs:
                    r = f.result()
                    if r is None:
                        return None
                    results.append(r)
        except (ValueError, TypeError, OverflowError, MemoryError):
            return None
    varr = np.concatenate([r[0] for r in results]) if results else np.zeros(0, dtype=np.float32)
    tarr = np.concatenate([r[1] for r in results]) if results else np.zeros(0, dtype=np.float32)
    narr = np.concatenate([r[2] for r in results]) if results else np.zeros(0, dtype=np.float32)
    fp = np.concatenate([r[3] for r in results]) if results else np.zeros(0, dtype=np.int64)
    ft = np.concatenate([r[4] for r in results]) if results else np.zeros(0, dtype=np.int64)
    fn = np.concatenate([r[5] for r in results]) if results else np.zeros(0, dtype=np.int64)
    return varr, tarr, narr, fp, ft, fn


def _obj_weld_slow(positions: list, texcoords: list, normals: list,
                   face_pos: list, face_tex: list, face_nrm: list):
    has_uv = len(face_tex) == len(face_pos) and len(texcoords) > 0
    has_nrm = len(face_nrm) == len(face_pos) and len(normals) > 0
    pos_arr = np.array(positions, dtype=np.float32)
    n_faces = len(face_pos)
    verts = np.empty(n_faces * 3, dtype=np.float32)
    norms_out = np.empty(n_faces * 3, dtype=np.float32)
    uvs_out = np.empty(n_faces * 2, dtype=np.float32)
    idx = np.empty(n_faces, dtype=np.uint32)
    seen: dict = {}
    out_idx = 0
    normals_arr = np.array(normals, dtype=np.float32)
    texcoords_arr = np.array(texcoords, dtype=np.float32)
    for i in range(n_faces):
        pi = face_pos[i]
        ni = face_nrm[i] if has_nrm else 0
        ti = face_tex[i] if has_uv else 0
        key = (int(pi), int(ni), int(ti))
        if key not in seen:
            seen[key] = out_idx
            pi3 = int(pi) * 3
            verts[out_idx * 3:out_idx * 3 + 3] = pos_arr[pi3:pi3 + 3]
            if has_nrm:
                ni3 = int(ni) * 3
                norms_out[out_idx * 3:out_idx * 3 + 3] = normals_arr[ni3:ni3 + 3]
            else:
                norms_out[out_idx * 3:out_idx * 3 + 3] = [0.0, 0.0, 0.0]
            if has_uv:
                ti2 = int(ti) * 2
                uvs_out[out_idx * 2:out_idx * 2 + 2] = texcoords_arr[ti2:ti2 + 2]
            else:
                uvs_out[out_idx * 2:out_idx * 2 + 2] = [0.0, 0.0]
            out_idx += 1
        idx[i] = seen[key]
    return verts, norms_out, uvs_out, idx, has_uv, has_nrm


def _obj_weld(varr: np.ndarray, tarr: np.ndarray, narr: np.ndarray,
              fp: np.ndarray, ft: np.ndarray, fn: np.ndarray):
    n_faces = int(fp.shape[0])
    if n_faces and (bool((fp < 0).any()) or bool((ft < -1).any()) or bool((fn < -1).any())):
        return _obj_weld_slow(varr.tolist(), tarr.tolist(), narr.tolist(),
                              fp.tolist(), ft.tolist(), fn.tolist())
    has_uv = bool(np.all(ft != -1)) and tarr.size > 0
    has_nrm = bool(np.all(fn != -1)) and narr.size > 0
    pos_arr = np.ascontiguousarray(varr, dtype=np.float32)
    if has_uv:
        ti_col = ft
    else:
        ti_col = np.zeros(n_faces, dtype=np.int64)
    if has_nrm:
        ni_col = fn
    else:
        ni_col = np.zeros(n_faces, dtype=np.int64)
    keys = np.empty((n_faces, 3), dtype=np.int64)
    keys[:, 0] = fp
    keys[:, 1] = ni_col
    keys[:, 2] = ti_col
    _, first, inv = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")
    remap = np.empty(first.shape[0], dtype=np.int64)
    remap[order] = np.arange(first.shape[0])
    idx = remap[inv].astype(np.uint32)
    pick = first[order]
    pos3 = pos_arr.reshape(-1, 3)
    verts = np.ascontiguousarray(pos3[fp[pick]].reshape(-1).astype(np.float32))
    if has_nrm:
        nrm3 = np.ascontiguousarray(narr, dtype=np.float32).reshape(-1, 3)
        norms_out = np.ascontiguousarray(nrm3[ni_col[pick]].reshape(-1).astype(np.float32))
    else:
        norms_out = np.zeros(verts.shape[0], dtype=np.float32)
    if has_uv:
        tex2 = np.ascontiguousarray(tarr, dtype=np.float32).reshape(-1, 2)
        uvs_out = np.ascontiguousarray(tex2[ti_col[pick]].reshape(-1).astype(np.float32))
    else:
        uvs_out = np.zeros((verts.shape[0] // 3) * 2, dtype=np.float32)
    return verts, norms_out, uvs_out, idx, has_uv, has_nrm


def load_mesh(path: str, import_settings: Optional[dict] = None) -> Optional[MeshImportData]:
    _sig = _import_meta_signature(path)
    with _mem_cache_lock:
        cached = _mem_cache.get(path)
        if cached is not None and cached[0] == _sig:
            return cached[1]

    eng = None
    try:
        from core.engine.engine import Engine
        eng = Engine.instance()
    except Exception:
        pass
    prof = eng._profiler if eng and hasattr(eng, '_profiler') else None
    if prof: prof.start("load_mesh")

    dll = _get_dll()
    try:
        c_path = ctypes.c_char_p(path.encode('utf-8'))
        AI_TRIANGULATE = 0x8
        AI_GEN_NORMALS = 0x2
        _settings = import_settings if import_settings is not None else _read_mesh_import(path)
        flags = AI_TRIANGULATE
        if _settings.get("gen_normals", True):
            flags |= AI_GEN_NORMALS
        scene_ptr = dll.aiImportFile(c_path, ctypes.c_uint32(flags))
        if not scene_ptr:
            if prof: prof.stop("load_mesh")
            return None
        scene = scene_ptr.contents
        mesh_parts = []
        skeleton_ctx = _SkeletonCtx()
        try:
            skeleton_ctx.want_blend = bool(_settings.get("blendshapes", True))
        except Exception:
            skeleton_ctx.want_blend = True
        node_map: dict = {}
        if scene.mRootNode:
            _build_node_map(scene.mRootNode, None, node_map)
            _collect_meshes(scene.mRootNode, scene, mesh_parts, skeleton_ctx, node_map, [0])
        dll.aiReleaseImport(scene_ptr)
        data = MeshImportData()
        data.name = os.path.splitext(os.path.basename(path))[0]
        if mesh_parts:
            vert_offset = 0
            all_verts = []
            all_norms = []
            all_uvs = []
            all_idxs = []
            ranges = []
            names = []
            idx_offset = 0
            for verts, norms, uvs, idxs, nv, name in mesh_parts:
                all_verts.append(verts)
                all_norms.append(norms)
                all_uvs.append(uvs)
                if len(idxs) > 0:
                    offset_idxs = idxs + vert_offset
                    ranges.append((idx_offset, len(offset_idxs)))
                    names.append(name)
                    idx_offset += len(offset_idxs)
                    all_idxs.append(offset_idxs)
                vert_offset += nv
            verts_out = np.concatenate(all_verts)
            norms_out = np.concatenate(all_norms)

            if _HAS_CYTHON:
                verts_out = _cy_apply_zup(verts_out)
                norms_out = _cy_apply_zup(norms_out)
            else:
                z_up_to_y_up = np.array([
                    [1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [0.0, -1.0, 0.0]
                ], dtype=np.float32)
                verts_out = (verts_out.reshape(-1, 3) @ z_up_to_y_up.T).ravel()
                norms_out = (norms_out.reshape(-1, 3) @ z_up_to_y_up.T).ravel()

            data.vertices = verts_out
            data.normals = norms_out
            data.uvs = np.concatenate(all_uvs)
            if all_idxs:
                data.indices = np.concatenate(all_idxs)
                data.sub_mesh_ranges = ranges
                data.sub_mesh_names = names
            total_verts = len(data.vertices) // 3
            blend = _finalize_blendshapes(skeleton_ctx, total_verts)
            if blend is not None:
                data.blendshape_names = blend["blendshape_names"]
                data.blendshape_indices = blend["blendshape_indices"]
                data.blendshape_positions = blend["blendshape_positions"]
                data.blendshape_normals = blend["blendshape_normals"]
            skel = _finalize_skeleton(skeleton_ctx, node_map, total_verts)
            if skel is not None:
                _align_skeleton_to_mesh(skel, verts_out)
                data.has_skeleton = True
                data.bone_names = skel["bone_names"]
                data.bone_parents = skel["bone_parents"]
                data.bone_offset_matrices = skel["bone_offset_matrices"]
                data.bone_bind_world = skel["bone_bind_world"]
                data.bone_bind_local = skel["bone_bind_local"]
                data.bone_indices = skel["bone_indices"]
                data.bone_weights = skel["bone_weights"]
        if prof: prof.stop("load_mesh")
        if data is not None and len(data.vertices) > 0:
            with _mem_cache_lock:
                _mem_cache[path] = (_sig, data)
        return data
    except Exception:
        if prof: prof.stop("load_mesh")
        return None


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


def _obj_apply_gen(data: MeshImportData, has_nrm: bool, has_uv: bool,
                   import_settings: Optional[dict], path: str):
    if len(data.vertices) == 0:
        return
    _v = data.vertices.reshape(-1, 3)
    _settings = import_settings if import_settings is not None else _read_mesh_import(path)
    if (not has_nrm or len(data.normals) == 0) and _settings.get("gen_normals", True):
        data.normals = _compute_smooth_normals(_v, data.indices).ravel()
    if (not has_uv or len(data.uvs) == 0) and _settings.get("gen_uvs", True):
        data.uvs = _generate_planar_uvs(_v).ravel()


def _obj_load_fast(path: str, import_settings: Optional[dict]) -> Optional[MeshImportData]:
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError:
        return None
    try:
        parsed = _obj_parse_fast(blob, _OBJ_FAST_THREADS)
    except (MemoryError, OSError):
        return None
    if parsed is None:
        return None
    varr, tarr, narr, fp, ft, fn = parsed
    if fp.shape[0] == 0:
        return None
    try:
        welded = _obj_weld(varr, tarr, narr, fp, ft, fn)
    except (ValueError, TypeError, IndexError, MemoryError, OverflowError):
        return None
    if welded is None:
        return None
    verts, norms_out, uvs_out, idx, has_uv, has_nrm = welded
    if verts.shape[0] == 0:
        return None
    data = MeshImportData()
    data.name = os.path.splitext(os.path.basename(path))[0]
    data.vertices = np.ascontiguousarray(verts, dtype=np.float32)
    data.normals = np.ascontiguousarray(norms_out, dtype=np.float32)
    data.uvs = np.ascontiguousarray(uvs_out, dtype=np.float32)
    data.indices = np.ascontiguousarray(idx, dtype=np.uint32)
    try:
        _obj_apply_gen(data, has_uv, has_nrm, import_settings, path)
    except Exception:
        return None
    return data


def _obj_load_slow(path: str, import_settings: Optional[dict]) -> Optional[MeshImportData]:
    positions, texcoords, normals = [], [], []
    face_pos, face_tex, face_nrm = [], [], []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("o ") or line.startswith(
                        "s ") or line.startswith("g "):
                    continue
                if line.startswith("usemtl ") or line.startswith("mtllib "):
                    continue
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == "v":
                    positions.extend([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == "vt":
                    texcoords.extend([float(parts[1]), float(parts[2])])
                elif parts[0] == "vn":
                    normals.extend([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == "f":
                    for token in parts[1:]:
                        v = token.split("/")
                        vi = int(v[0]) - 1
                        face_pos.append(vi)
                        if len(v) > 1 and v[1]:
                            face_tex.append(int(v[1]) - 1)
                        if len(v) > 2 and v[2]:
                            face_nrm.append(int(v[2]) - 1)
    except Exception:
        return None
    if not face_pos:
        return None
    has_uv = len(face_tex) == len(face_pos) and len(texcoords) > 0
    has_nrm = len(face_nrm) == len(face_pos) and len(normals) > 0
    pos_arr = np.array(positions, dtype=np.float32)
    n_faces = len(face_pos)
    verts = np.empty(n_faces * 3, dtype=np.float32)
    norms_out = np.empty(n_faces * 3, dtype=np.float32)
    uvs_out = np.empty(n_faces * 2, dtype=np.float32)
    idx = np.empty(n_faces, dtype=np.uint32)
    seen: dict[tuple, int] = {}
    out_idx = 0
    normals_arr = np.array(normals, dtype=np.float32)
    texcoords_arr = np.array(texcoords, dtype=np.float32)
    for i in range(n_faces):
        pi = face_pos[i]
        ni = face_nrm[i] if has_nrm else 0
        ti = face_tex[i] if has_uv else 0
        key = (pi, ni, ti)
        if key not in seen:
            seen[key] = out_idx
            pi3 = pi * 3
            verts[out_idx * 3:out_idx * 3 + 3] = pos_arr[pi3:pi3 + 3]
            if has_nrm:
                ni3 = ni * 3
                norms_out[out_idx * 3:out_idx * 3 + 3] = normals_arr[ni3:ni3 + 3]
            else:
                norms_out[out_idx * 3:out_idx * 3 + 3] = [0.0, 0.0, 0.0]
            if has_uv:
                ti2 = ti * 2
                uvs_out[out_idx * 2:out_idx * 2 + 2] = texcoords_arr[ti2:ti2 + 2]
            else:
                uvs_out[out_idx * 2:out_idx * 2 + 2] = [0.0, 0.0]
            out_idx += 1
        idx[i] = seen[key]
    data = MeshImportData()
    data.name = os.path.splitext(os.path.basename(path))[0]
    if out_idx > 0:
        data.vertices = verts[:out_idx * 3].copy()
        data.normals = norms_out[:out_idx * 3].copy()
        data.uvs = uvs_out[:out_idx * 2].copy()
    data.indices = idx
    if out_idx > 0:
        try:
            _obj_apply_gen(data, has_nrm, has_uv, import_settings, path)
        except Exception:
            return None
    return data


def load_obj(path: str, import_settings: Optional[dict] = None) -> Optional[MeshImportData]:
    _sig = _import_meta_signature(path)
    with _mem_cache_lock:
        cached = _mem_cache.get(path)
        if cached is not None and cached[0] == _sig:
            return cached[1]

    eng = None
    try:
        from core.engine.engine import Engine
        eng = Engine.instance()
    except Exception:
        pass
    prof = eng._profiler if eng and hasattr(eng, '_profiler') else None
    if prof: prof.start("load_obj")

    data = None
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if size >= _OBJ_FAST_MIN_BYTES:
        data = _obj_load_fast(path, import_settings)
    if data is None:
        data = _obj_load_slow(path, import_settings)
        if prof: prof.stop("load_obj")
    else:
        if prof: prof.stop("load_obj")
    if data is not None and len(data.vertices) > 0:
        with _mem_cache_lock:
            _mem_cache[path] = (_sig, data)
    return data


def load_mesh_async(path: str, callback: Callable[[Optional[MeshImportData]], None]) -> None:
    _settings = _read_mesh_import(path)
    fut = _get_mesh_import_pool().submit(load_mesh, path, _settings)

    def _done(f):
        try:
            callback(f.result())
        except Exception:
            callback(None)

    fut.add_done_callback(_done)


def load_obj_async(path: str, callback: Callable[[Optional[MeshImportData]], None]) -> None:
    _settings = _read_mesh_import(path)
    fut = _get_mesh_import_pool().submit(load_obj, path, _settings)

    def _done(f):
        try:
            callback(f.result())
        except Exception:
            callback(None)

    fut.add_done_callback(_done)


def load_gif_frames(path: str) -> list[np.ndarray]:
    from PIL import Image
    gif = Image.open(path)
    frames = []
    try:
        while True:
            frame = gif.copy().convert("RGBA")
            frames.append(np.array(frame, dtype=np.uint8))
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass
    if not frames:
        raise ValueError(f"No frames found in GIF: {path}")
    return frames


def gif_frames_to_flipbook(frames: list[np.ndarray], cols: int = None, rows: int = None) -> tuple[np.ndarray, int, int]:
    n = len(frames)
    if cols is None and rows is None:
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
    elif cols is None:
        cols = int(np.ceil(n / rows))
    elif rows is None:
        rows = int(np.ceil(n / cols))
    total = cols * rows
    fh, fw = frames[0].shape[:2]
    sheet = np.zeros((fh * rows, fw * cols, 4), dtype=np.uint8)
    for i in range(total):
        cx = (i % cols) * fw
        cy = (i // cols) * fh
        src = frames[i] if i < n else frames[-1]
        sheet[cy:cy + fh, cx:cx + fw] = src
    return sheet, cols, rows


def import_gif_to_flipbook(gif_path: str, output_path: str = None, cols: int = None, rows: int = None) -> tuple[
    int, int, int]:
    frames = load_gif_frames(gif_path)
    sheet, cols_out, rows_out = gif_frames_to_flipbook(frames, cols, rows)
    if output_path is None:
        base = os.path.splitext(gif_path)[0]
        output_path = base + "_flipbook.png"
    from PIL import Image
    Image.fromarray(sheet).save(output_path)
    return cols_out, rows_out, len(frames)


def import_gif_to_flipbook_async(gif_path: str, callback: Callable[[Optional[tuple[int, int, int]]], None] = None,
                                 output_path: str = None, cols: int = None, rows: int = None) -> Future:
    fut = _get_asset_pool().submit(import_gif_to_flipbook, gif_path, output_path, cols, rows)

    def _done(f):
        try:
            result = f.result()
            if callback:
                callback(result)
        except Exception:
            if callback:
                callback(None)

    fut.add_done_callback(_done)
    return fut


def load_mesh_future(path: str) -> Future:
    with _inflight_lock:
        existing = _inflight.get(path)
        if existing is not None and not existing.done():
            return existing
    _settings = _read_mesh_import(path)
    fut = _get_mesh_import_pool().submit(load_mesh, path, _settings)
    with _inflight_lock:
        _inflight[path] = fut

    def _cleanup(f):
        with _inflight_lock:
            if _inflight.get(path) is f:
                del _inflight[path]

    fut.add_done_callback(_cleanup)
    return fut


def load_obj_future(path: str) -> Future:
    with _inflight_lock:
        existing = _inflight.get(path)
        if existing is not None and not existing.done():
            return existing
    _settings = _read_mesh_import(path)
    fut = _get_mesh_import_pool().submit(load_obj, path, _settings)
    with _inflight_lock:
        _inflight[path] = fut

    def _cleanup(f):
        with _inflight_lock:
            if _inflight.get(path) is f:
                del _inflight[path]

    fut.add_done_callback(_cleanup)
    return fut