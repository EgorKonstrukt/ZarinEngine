# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import os
import ctypes
import numpy as np
from asyncio import Future
from typing import Optional, Callable
from core.ecs.pool import mesh_import as _get_mesh_import_pool
from core.assets.importer.ctypes_types import MeshImportData
from core.assets.importer.ctypes_types import _cy_apply_zup
from core.assets.importer.ctypes_types import _HAS_CYTHON
from core.assets.importer.assimp import _build_node_map
from core.assets.importer.assimp import _get_dll
from core.assets.importer.anim import _align_skeleton_to_mesh
from core.assets.importer.anim import _collect_meshes
from core.assets.importer.anim import _finalize_blendshapes
from core.assets.importer.anim import _finalize_skeleton
from core.assets.importer.anim import _SkeletonCtx
from core.assets.importer.settings import _OBJ_FAST_MIN_BYTES
from core.assets.importer.settings import _OBJ_FAST_THREADS
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
def _obj_parse_fast(data: bytes, jobs: int):
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
            with ThreadPoolExecutor(max_workers=len(bounds)) as ex:
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
def _obj_weld(varr: np.ndarray, tarr: np.ndarray, narr: np.ndarray, fp: np.ndarray, ft: np.ndarray, fn: np.ndarray):
    n_faces = int(fp.shape[0])
    if n_faces and (bool((fp < 0).any()) or bool((ft < -1).any()) or bool((fn < -1).any())):
        return _obj_weld_slow(varr.tolist(), tarr.tolist(), narr.tolist(), fp.tolist(), ft.tolist(), fn.tolist())
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
def _load_step_cached(path: str, import_settings: Optional[dict], sig):
    from core.assets.importer.stepp import load_step
    eng = None
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
    except Exception:
        pass
    prof = eng._profiler if eng and hasattr(eng, "_profiler") else None
    if prof:
        prof.start("load_mesh")
    try:
        settings = import_settings if import_settings is not None else _read_mesh_import(path)
        data = load_step(path, settings)
    except Exception:
        data = None
    finally:
        if prof:
            prof.stop("load_mesh")
    if data is not None and len(data.vertices) > 0:
        with _mem_cache_lock:
            _mem_cache_store(path, (sig, data))
    return data


def load_mesh(path: str, import_settings: Optional[dict] = None) -> Optional[MeshImportData]:
    _sig = _import_meta_signature(path)
    with _mem_cache_lock:
        cached = _mem_cache.get(path)
        if cached is not None and cached[0] == _sig:
            _mem_cache_touch(path)
            return cached[1]
    try:
        if os.path.splitext(path)[1].lower() in (".stp", ".step"):
            return _load_step_cached(path, import_settings, _sig)
    except (TypeError, ValueError, AttributeError):
        pass
    eng = None
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
    except Exception:
        pass
    prof = eng._profiler if eng and hasattr(eng, "_profiler") else None
    if prof:
        prof.start("load_mesh")
    dll = _get_dll()
    try:
        c_path = ctypes.c_char_p(path.encode("utf-8"))
        AI_TRIANGULATE = 0x8
        AI_GEN_NORMALS = 0x2
        _settings = import_settings if import_settings is not None else _read_mesh_import(path)
        flags = AI_TRIANGULATE
        if _settings.get("gen_normals", True):
            flags |= AI_GEN_NORMALS
        scene_ptr = dll.aiImportFile(c_path, ctypes.c_uint32(flags))
        if not scene_ptr:
            if prof:
                prof.stop("load_mesh")
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
        if prof:
            prof.stop("load_mesh")
        if data is not None and len(data.vertices) > 0:
            with _mem_cache_lock:
                _mem_cache_store(path, (_sig, data))
        return data
    except Exception:
        if prof:
            prof.stop("load_mesh")
        return None
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
                if not line or line.startswith("\x23") or line.startswith("o ") or line.startswith("s ") or line.startswith("g "):
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
            _mem_cache_touch(path)
            return cached[1]
    eng = None
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
    except Exception:
        pass
    prof = eng._profiler if eng and hasattr(eng, "_profiler") else None
    if prof:
        prof.start("load_obj")
    data = None
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if size >= _OBJ_FAST_MIN_BYTES:
        data = _obj_load_fast(path, import_settings)
    if data is None:
        data = _obj_load_slow(path, import_settings)
        if prof:
            prof.stop("load_obj")
    else:
        if prof:
            prof.stop("load_obj")
    if data is not None and len(data.vertices) > 0:
        with _mem_cache_lock:
            _mem_cache_store(path, (_sig, data))
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
