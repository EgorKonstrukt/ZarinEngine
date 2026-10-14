# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import mmap
import os
import threading
import numpy as np
from typing import Optional
from core.assets.ply_loader import load_ply_gaussian_splat, SH_C0, _parse_header, _ply_type
from core.assets.sog import load_gaussian_splat
from core.renderer.meshd import read_shader_pair
from core.renderer.shaderp import program_with_fallback
from core.foundation.logger import Logger
from core.foundation.progress import task_update

_SPLAT_DTYPE = np.dtype([
    ("pos_x", np.float32), ("pos_y", np.float32), ("pos_z", np.float32),
    ("sh_dc_0", np.float32), ("sh_dc_1", np.float32), ("sh_dc_2", np.float32),
    ("sh_rest", np.float32, (45,)),
    ("opacity", np.float32),
    ("scale_0", np.float32), ("scale_1", np.float32), ("scale_2", np.float32),
    ("quat_x", np.float32), ("quat_y", np.float32), ("quat_z", np.float32), ("quat_w", np.float32),
])

_SPLAT_STRUCT_SIZE = _SPLAT_DTYPE.itemsize
_EMPTY_U32 = np.zeros(0, dtype=np.uint32)
_SPLAT_LOAD_CHUNK = 262144
_SPLAT_FAIL_RETRY_S = 30.0
_GC_IDLE_S = 30.0
_GC_MAX_PATHS = 4
_SPLAT_UPLOAD_CHUNK_BYTES = 16 * 1024 * 1024
_SPLAT_MAX_SORTS_PER_FRAME = 2
_SPLAT_GPU_MIN_N = 131072
_SPLAT_GPU_SORTS_PER_FRAME = 4
_SPLAT_GPU_GROUPS = 128
_SPLAT_MIN_PX = 0.5
_SPLAT_GPU_ROWS = 1048576
_READY_SPLATS: dict = {}
_READY_KEYS: list = []
_READY_LOCK = threading.Lock()


def _splat_task_id(path: str) -> str:
    base = path.replace("\\", "/").split("/")[-1] or path
    return f"splat_load:{base}"


def _splat_cache_key(path: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return path


def _drop_splat_arrays(path: str):
    key = _splat_cache_key(path)
    with _READY_LOCK:
        _READY_SPLATS.pop(key, None)
        try:
            _READY_KEYS.remove(key)
        except ValueError:
            pass


def try_get_splat_arrays(path: str):
    key = _splat_cache_key(path)
    with _READY_LOCK:
        entry = _READY_SPLATS.get(key)
        if entry is None:
            return None
        try:
            _READY_KEYS.remove(key)
        except ValueError:
            pass
        _READY_KEYS.append(key)
        return entry


def _publish_splat_arrays(path: str, pos: np.ndarray, scales: np.ndarray, opacity: np.ndarray):
    key = _splat_cache_key(path)
    with _READY_LOCK:
        _READY_SPLATS[key] = (pos, scales, opacity)
        try:
            _READY_KEYS.remove(key)
        except ValueError:
            pass
        _READY_KEYS.append(key)
        while len(_READY_KEYS) > 4:
            _READY_SPLATS.pop(_READY_KEYS.pop(0), None)


def _pack_struct(pos, dc, rest, nk, opa, scl, quat, n):
    gpu = np.zeros(n, dtype=_SPLAT_DTYPE)
    gpu["pos_x"] = pos[:, 0]
    gpu["pos_y"] = pos[:, 1]
    gpu["pos_z"] = pos[:, 2]
    gpu["sh_dc_0"] = dc[:, 0]
    gpu["sh_dc_1"] = dc[:, 1]
    gpu["sh_dc_2"] = dc[:, 2]
    if nk > 0:
        gpu["sh_rest"][:, :nk] = rest[:, :nk]
    gpu["opacity"] = opa
    gpu["scale_0"] = scl[:, 0]
    gpu["scale_1"] = scl[:, 1]
    gpu["scale_2"] = scl[:, 2]
    gpu["quat_x"] = quat[:, 0]
    gpu["quat_y"] = quat[:, 1]
    gpu["quat_z"] = quat[:, 2]
    gpu["quat_w"] = quat[:, 3]
    return gpu


def _derive_splat_arrays(pos, scl):
    mn = pos.min(axis=0)
    mx = pos.max(axis=0)
    center = np.ascontiguousarray((mn + mx) * 0.5, dtype=np.float32)
    radius = float(np.linalg.norm((mx - mn).astype(np.float64) * 0.5))
    srad = np.ascontiguousarray(scl.max(axis=1) * 3.0, dtype=np.float32)
    return center, radius, srad


def _load_splat_generic(path: str, progress) -> Optional[dict]:
    progress(0.05, "parsing")
    data = load_gaussian_splat(path)
    if data is None:
        data = load_ply_gaussian_splat(path)
    if data is None or data.num_splats == 0:
        return None
    progress(0.55, "packing")
    gpu = _pack_struct(data.positions, data.sh_coeffs[:, :3],
                       data.sh_coeffs[:, 3:], max(0, data.sh_coeffs.shape[1] - 3),
                       data.opacity, data.scales, data.quaternions, data.num_splats)
    progress(0.85, "indexing")
    pos = np.ascontiguousarray(data.positions, dtype=np.float32)
    opa = np.ascontiguousarray(data.opacity.reshape(-1), dtype=np.float32)
    scl = np.ascontiguousarray(data.scales, dtype=np.float32)
    center, radius, srad = _derive_splat_arrays(pos, scl)
    progress(1.0, None)
    return {"gpu": gpu, "pos": pos, "opa": opa, "scl": scl, "srad": srad,
            "center": center, "radius": radius}


def _load_splat_fast(path: str, task_id: str, progress) -> Optional[dict]:
    try:
        total_bytes = os.path.getsize(path)
    except OSError:
        total_bytes = 0
    task_update(task_id, total=float(total_bytes) if total_bytes else None, units="bytes")
    f = open(path, "rb")
    try:
        header = []
        while True:
            line = f.readline()
            if not line:
                return None
            text = line.decode("ascii", errors="ignore").strip()
            header.append(text)
            if text == "end_header":
                break
        vertex_count, properties, fmt = _parse_header(header)
        if vertex_count <= 0:
            return None
        if fmt != "binary_little_endian":
            return _load_splat_generic(path, progress)
        names = [p[1] for p in properties]
        need = ("x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
                "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")
        if any(k not in names for k in need):
            return None
        dtypes = [_ply_type(p[0]) for p in properties]
        if any(dt != np.float32 for dt in dtypes):
            return _load_splat_generic(path, progress)
        idx = {k: i for i, k in enumerate(names)}
        rest_keys = [k for k in names if k.startswith("f_rest_")]
        nk = min(len(rest_keys), 45)
        n = vertex_count
        cols = len(properties)
        data_off = f.tell()
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            raw = np.frombuffer(mm, dtype=np.float32, count=n * cols, offset=data_off).reshape(n, cols)
            CH = _SPLAT_LOAD_CHUNK
            pos = np.empty((n, 3), dtype=np.float32)
            dc = np.empty((n, 3), dtype=np.float32)
            rest = np.zeros((n, 45), dtype=np.float32)
            opa = np.empty(n, dtype=np.float32)
            scl = np.empty((n, 3), dtype=np.float32)
            quat = np.empty((n, 4), dtype=np.float32)
            ix, iy, iz = idx["x"], idx["y"], idx["z"]
            adjacent_xyz = (iy == ix + 1 and iz == ix + 2)
            idc = [idx["f_dc_0"], idx["f_dc_1"], idx["f_dc_2"]]
            adjacent_dc = (idc[1] == idc[0] + 1 and idc[2] == idc[0] + 2)
            iop = idx["opacity"]
            isc = [idx["scale_0"], idx["scale_1"], idx["scale_2"]]
            adjacent_sc = (isc[1] == isc[0] + 1 and isc[2] == isc[0] + 2)
            iqx = [idx["rot_1"], idx["rot_2"], idx["rot_3"], idx["rot_0"]]
            rk = [names.index(k) for k in rest_keys[:nk]] if nk else []
            rest_block = (len(rk) == nk and nk > 0 and all(b - a == 1 for a, b in zip(rk, rk[1:])))
            for s in range(0, n, CH):
                e = min(s + CH, n)
                if adjacent_xyz:
                    pos[s:e] = raw[s:e, ix:ix + 3]
                else:
                    pos[s:e, 0] = raw[s:e, ix]
                    pos[s:e, 1] = raw[s:e, iy]
                    pos[s:e, 2] = raw[s:e, iz]
                if adjacent_dc:
                    dc[s:e] = raw[s:e, idc[0]:idc[0] + 3]
                else:
                    for j, c in enumerate(idc):
                        dc[s:e, j] = raw[s:e, c]
                if rest_block:
                    rest[s:e, :nk] = raw[s:e, rk[0]:rk[0] + nk]
                else:
                    for j, c in enumerate(rk):
                        rest[s:e, j] = raw[s:e, c]
                opa[s:e] = raw[s:e, iop]
                if adjacent_sc:
                    scl[s:e] = raw[s:e, isc[0]:isc[0] + 3]
                else:
                    for j, c in enumerate(isc):
                        scl[s:e, j] = raw[s:e, c]
                for j, c in enumerate(iqx):
                    quat[s:e, j] = raw[s:e, c]
                progress(0.05 + 0.45 * e / n, f"{e / 1e6:.1f}M/{n / 1e6:.1f}M splats")
            progress(0.52, "activations")
            dc *= np.float32(SH_C0)
            dc += np.float32(0.5)
            np.negative(opa, out=opa)
            np.exp(opa, out=opa)
            opa += np.float32(1.0)
            np.reciprocal(opa, out=opa)
            np.exp(scl, out=scl)
            progress(0.62, "rotations")
            qn = np.sqrt((quat * quat).sum(axis=1))
            np.maximum(qn, 1e-8, out=qn)
            quat /= qn[:, None]
            pos[:, 0] *= np.float32(-1.0)
            pos[:, 1] *= np.float32(-1.0)
            _tx = quat[:, 0].copy()
            _tz = quat[:, 2].copy()
            quat[:, 0] = -quat[:, 1]
            quat[:, 1] = _tx
            quat[:, 2] = quat[:, 3]
            quat[:, 3] = -_tz
            del _tx, _tz
            if nk == 9:
                rest[:, [0, 2, 3, 5, 6, 8]] *= np.float32(-1.0)
            elif nk == 24:
                rest[:, [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]] *= np.float32(-1.0)
            elif nk == 45:
                rest[:, [0, 2, 4, 6, 8, 10, 12, 14, 15, 17, 19, 21, 23, 25, 27, 29, 30, 32, 34, 36, 38, 40, 42, 44]] *= np.float32(-1.0)
            progress(0.68, "packing")
            gpu = np.zeros(n, dtype=_SPLAT_DTYPE)
            for s in range(0, n, CH):
                e = min(s + CH, n)
                g = gpu[s:e]
                g["pos_x"] = pos[s:e, 0]
                g["pos_y"] = pos[s:e, 1]
                g["pos_z"] = pos[s:e, 2]
                g["sh_dc_0"] = dc[s:e, 0]
                g["sh_dc_1"] = dc[s:e, 1]
                g["sh_dc_2"] = dc[s:e, 2]
                if nk > 0:
                    g["sh_rest"][:, :nk] = rest[s:e, :nk]
                g["opacity"] = opa[s:e]
                g["scale_0"] = scl[s:e, 0]
                g["scale_1"] = scl[s:e, 1]
                g["scale_2"] = scl[s:e, 2]
                g["quat_x"] = quat[s:e, 0]
                g["quat_y"] = quat[s:e, 1]
                g["quat_z"] = quat[s:e, 2]
                g["quat_w"] = quat[s:e, 3]
                progress(0.68 + 0.22 * e / n, f"{e / 1e6:.1f}M/{n / 1e6:.1f}M splats")
            progress(0.92, "indexing")
            center, radius, srad = _derive_splat_arrays(pos, scl)
            progress(1.0, None)
            return {"gpu": gpu, "pos": pos, "opa": opa, "scl": scl, "srad": srad,
                    "center": center, "radius": radius}
        finally:
            try:
                mm.close()
            except Exception:
                pass
    finally:
        try:
            f.close()
        except Exception:
            pass


def _is_sog_style(path: str) -> bool:
    try:
        lp = str(path).lower().replace("\\", "/")
    except Exception:
        return False
    try:
        if os.path.isdir(path):
            return True
    except Exception:
        pass
    if lp.endswith(".sog") or lp.endswith(".ssog") or lp.endswith(".zip"):
        return True
    if lp.endswith("/meta.json") or lp.endswith("/lod-meta.json"):
        return True
    base = lp.split("/")[-1]
    if base == "meta.json" or base == "lod-meta.json":
        return True
    return False


def _load_splat_file(path: str, task_id: str, progress) -> Optional[dict]:
    if _is_sog_style(path):
        return _load_splat_generic(path, progress)
    try:
        with open(path, "rb") as f:
            head = [f.readline().decode("ascii", errors="ignore").strip() for _ in range(4)]
    except OSError:
        return _load_splat_generic(path, progress)
    is_binary = any("binary" in h for h in head)
    if is_binary:
        return _load_splat_fast(path, task_id, progress)
    return _load_splat_generic(path, progress)


class _SplatResourcesMixin:
    def _init_shaders(self):
        vert_src = None
        try:
            vert_src, frag_src = read_shader_pair("gaussian_splat")
            self._prog = program_with_fallback(
                self._ctx,
                vertex_shader=vert_src,
                fragment_shader=frag_src,
                label="gaussian_splat"
            )
            self._vao = self._ctx.vertex_array(self._prog, [])
        except Exception as e:
            Logger.error(f"GaussianSplatRenderer shader init failed (needs OpenGL 4.3+): {e}")
            self._prog = None
            self._vao = None

    def _ensure_buffers(self, num_splats: int):
        needed = max(1, num_splats) * _SPLAT_STRUCT_SIZE
        if self._ssbo is None or self._ssbo.size < needed:
            if self._ssbo:
                self._ssbo.release()
            self._ssbo = self._ctx.buffer(reserve=needed)
            self._uploaded_path = None
        idx_needed = max(1, num_splats) * 4
        if self._idx_ssbo is None or self._idx_ssbo.size < idx_needed:
            if self._idx_ssbo:
                self._idx_ssbo.release()
            self._idx_ssbo = self._ctx.buffer(reserve=idx_needed)
            self._idx_key = None

    def _bind_gpu_draw(self, path: str, model_f32: np.ndarray, view_f32: np.ndarray,
                       proj_f32: np.ndarray, cam_pos, viewport_w, viewport_h,
                       sh_degree: int, opacity_threshold: float):
        self._ssbo.bind_to_storage_buffer(0)
        self._gs_order[path].bind_to_storage_buffer(1)
        self._upload_uniforms(model_f32, view_f32, proj_f32, cam_pos,
                              viewport_w, viewport_h, sh_degree, opacity_threshold)

    def _upload_uniforms(self, model_f32: np.ndarray, view_f32: np.ndarray,
                         proj_f32: np.ndarray, cam_pos, viewport_w, viewport_h,
                         sh_degree: int, opacity_threshold: float):
        prog = self._prog
        if prog is None:
            return
        if "u_model" in prog:
            prog["u_model"].write(model_f32.tobytes())
        if "u_view" in prog:
            prog["u_view"].write(view_f32.tobytes())
        if "u_proj" in prog:
            prog["u_proj"].write(proj_f32.tobytes())
        if "u_viewport" in prog:
            prog["u_viewport"].write(np.array([viewport_w, viewport_h], dtype=np.float32).tobytes())
        if "u_camera_pos" in prog:
            prog["u_camera_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        if "u_sh_degree" in prog:
            prog["u_sh_degree"].value = int(sh_degree)
        if "u_opacity_threshold" in prog:
            prog["u_opacity_threshold"].value = float(opacity_threshold)
