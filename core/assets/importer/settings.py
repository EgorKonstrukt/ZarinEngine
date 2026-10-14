# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import json
import hashlib
import threading
import numpy as np
from asyncio import Future
from typing import Optional
from collections import OrderedDict as _MemOrderedDict
from core.assets.importer.ctypes_types import MeshImportData
from core.assets.importer.ctypes_types import _cy_parse_obj_chunk
from core.assets.importer.ctypes_types import _cy_smooth_normals
from core.assets.importer.ctypes_types import _HAS_CYTHON
_inflight_lock = threading.Lock()
_inflight: dict[str, Future] = {}
_mem_cache_lock = threading.Lock()
_mem_cache: dict = _MemOrderedDict()
_MEM_CACHE_MAX = 12
def _mem_cache_store(path: str, entry) -> None:
    _mem_cache[path] = entry
    _mem_cache.move_to_end(path)
    while len(_mem_cache) > _MEM_CACHE_MAX:
        _mem_cache.popitem(last=False)
def _mem_cache_touch(path: str) -> None:
    try:
        _mem_cache.move_to_end(path)
    except KeyError:
        pass
def _root_hint() -> Optional[str]:
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        return eng.project_root if eng and getattr(eng, "project_root", None) else None
    except Exception:
        return None
def _resolve_mesh_import_path(path: str) -> str:
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
def _obj_apply_gen(data: MeshImportData, has_nrm: bool, has_uv: bool, import_settings: Optional[dict], path: str):
    if len(data.vertices) == 0:
        return
    _v = data.vertices.reshape(-1, 3)
    _settings = import_settings if import_settings is not None else _read_mesh_import(path)
    if (not has_nrm or len(data.normals) == 0) and _settings.get("gen_normals", True):
        data.normals = _compute_smooth_normals(_v, data.indices).ravel()
    if (not has_uv or len(data.uvs) == 0) and _settings.get("gen_uvs", True):
        data.uvs = _generate_planar_uvs(_v).ravel()
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
        if not line or line[:1] == b"\x23":
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
def _obj_weld_slow(positions: list, texcoords: list, normals: list, face_pos: list, face_tex: list, face_nrm: list):
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
