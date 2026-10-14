# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import ctypes
import numpy as np
from typing import Optional
from core.assets.importer.ctypes_types import aiAnimMesh
from core.assets.importer.ctypes_types import aiBone
from core.assets.importer.ctypes_types import aiFace
from core.assets.importer.ctypes_types import aiMesh
from core.assets.importer.ctypes_types import aiMeshFull
from core.assets.importer.ctypes_types import aiNode
from core.assets.importer.ctypes_types import aiVector3D
from core.assets.importer.ctypes_types import aiVertexWeight
from core.assets.importer.ctypes_types import _ai_matrix_to_np_full
from core.assets.importer.ctypes_types import _BLEND_DELTA_EPS
from core.assets.importer.ctypes_types import _cy_extract_faces
from core.assets.importer.ctypes_types import _HAS_CYTHON
from core.assets.importer.ctypes_types import _Y_UP_ROTATION
from core.assets.importer.assimp import _build_node_map
from core.assets.importer.assimp import _decode_assimp_name
from core.assets.importer.assimp import _node_world_zup
from core.assets.importer.assimp import _read_name
from core.assets.importer.material import _read_material_name
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
def _read_anim_meshes(mesh_ptr, nv: int, base_verts: np.ndarray, base_norms: np.ndarray, vert_offset: int, rel_3x3: np.ndarray, skeleton_ctx) -> None:
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
