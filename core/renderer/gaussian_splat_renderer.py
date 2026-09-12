# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import mmap
import os
import threading
import time
import numpy as np
import moderngl
from typing import Optional
from core.assets.ply_loader import load_ply_gaussian_splat, SH_C0, _parse_header, _ply_type
from core.renderer.mesh_data import read_shader
from core.foundation.logger import Logger
from core.foundation.progress import task_start, task_update, task_complete, notify_error


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

try:
    from core._splat_sort import splat_cull_depth as _cython_cull_depth
    from core._splat_sort import compact_keep as _cython_compact
    from core._splat_sort import radix_sort_into as _cython_radix
    from core._splat_sort import remap_order as _cython_remap
except Exception:
    _cython_cull_depth = None
    _cython_compact = None
    _cython_radix = None
    _cython_remap = None


def _cython_available() -> bool:
    return (_cython_cull_depth is not None and _cython_compact is not None
            and _cython_radix is not None and _cython_remap is not None)


def _cython_available() -> bool:
    return (_cython_cull_depth is not None and _cython_compact is not None
            and _cython_radix is not None and _cython_remap is not None)


_SPLAT_LOAD_CHUNK = 262144
_SPLAT_FAIL_RETRY_S = 30.0
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


def _load_splat_file(path: str, task_id: str, progress) -> Optional[dict]:
    try:
        with open(path, "rb") as f:
            head = [f.readline().decode("ascii", errors="ignore").strip() for _ in range(4)]
    except OSError:
        return None
    is_binary = any("binary" in h for h in head)
    if is_binary:
        return _load_splat_fast(path, task_id, progress)
    return _load_splat_generic(path, progress)


class GaussianSplatRenderer:
    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._prog: Optional[moderngl.Program] = None
        self._ssbo: Optional[moderngl.Buffer] = None
        self._idx_ssbo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._uploaded_path: Optional[str] = None
        self._uploaded_n: int = 0
        self._gpu_data: dict[str, np.ndarray] = {}
        self._pos: dict[str, np.ndarray] = {}
        self._opa: dict[str, np.ndarray] = {}
        self._srad: dict[str, np.ndarray] = {}
        self._center: dict[str, np.ndarray] = {}
        self._radius: dict[str, float] = {}
        self._sort_cache: dict[tuple[str, bytes], list] = {}
        self._scratch: dict[str, dict[str, np.ndarray]] = {}
        self._idx_key: Optional[tuple[str, bytes]] = None
        self._load_lock = threading.Lock()
        self._loading: set = set()
        self._completed: list = []
        self._failed: dict = {}
        self._fractions: dict = {}
        self._init_shaders()
        if _cython_available():
            self._sort_backend = "cython"
        else:
            self._sort_backend = "numpy"
        Logger.info(f"GaussianSplatRenderer sort backend: {self._sort_backend}")

    def _init_shaders(self):
        vert_src = None
        try:
            vert_src = read_shader("gaussian_splat.vert")
            frag_src = read_shader("gaussian_splat.frag")
            self._prog = self._ctx.program(
                vertex_shader=vert_src,
                fragment_shader=frag_src,
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

    def load_data(self, path: str) -> bool:
        if path in self._gpu_data:
            return True
        now = time.monotonic()
        with self._load_lock:
            if path in self._loading:
                return False
            failed_at = self._failed.get(path)
            if failed_at is not None:
                if now - failed_at < _SPLAT_FAIL_RETRY_S:
                    return False
                del self._failed[path]
            if not os.path.isfile(path):
                return False
            self._loading.add(path)
            self._fractions[path] = 0.0
        base = path.replace("\\", "/").split("/")[-1] or path
        task_start(_splat_task_id(path), f"Loading {base}...", fraction=0.0)
        threading.Thread(target=self._load_thread, args=(path,), daemon=True).start()
        return False

    def load_progress(self, path: str):
        if path in self._gpu_data:
            return 1.0
        with self._load_lock:
            return self._fractions.get(path)

    def _load_thread(self, path: str):
        task_id = _splat_task_id(path)

        def progress(frac, detail=None):
            f = max(0.0, min(1.0, float(frac)))
            with self._load_lock:
                if path in self._fractions:
                    self._fractions[path] = f
            task_update(task_id, fraction=f, detail=detail)

        try:
            payload = _load_splat_file(path, task_id, progress)
        except Exception as e:
            Logger.error(f"Splat load failed: {path}: {e}")
            payload = None
        with self._load_lock:
            self._loading.discard(path)
            self._fractions.pop(path, None)
            if payload is None:
                self._failed[path] = time.monotonic()
                task_complete(task_id)
                notify_error(f"Failed to load {path.replace(chr(92), '/').split('/')[-1]}")
            else:
                self._completed.append((path, payload))
                task_complete(task_id)

    def process_pending(self):
        with self._load_lock:
            if not self._completed:
                return
            done = self._completed
            self._completed = []
        for path, payload in done:
            self._gpu_data[path] = payload["gpu"]
            self._pos[path] = payload["pos"]
            self._opa[path] = payload["opa"]
            self._srad[path] = payload["srad"]
            self._center[path] = payload["center"]
            self._radius[path] = payload["radius"]
            self._uploaded_path = None
            for k in [k for k in self._sort_cache if k[0] == path]:
                del self._sort_cache[k]
            self._scratch.pop(path, None)
            _publish_splat_arrays(path, payload["pos"], payload["scl"], payload["opa"])

    def _pack_for_gpu(self, data) -> np.ndarray:
        return _pack_struct(data.positions, data.sh_coeffs[:, :3],
                            data.sh_coeffs[:, 3:], max(0, data.sh_coeffs.shape[1] - 3),
                            data.opacity, data.scales, data.quaternions, data.num_splats)

    def _frame_key(self, model_f32: np.ndarray, view_f32: np.ndarray,
                   proj_f32: np.ndarray, opacity_threshold: float) -> bytes:
        proj = proj_f32.reshape(4, 4)
        zoom = np.array([proj[0, 0], proj[1, 1]], dtype=np.float32).tobytes()
        return model_f32.tobytes() + view_f32.tobytes() + np.float32(opacity_threshold).tobytes() + zoom

    def _sort_basis(self, model_f32: np.ndarray, view_f32: np.ndarray, proj_f32: np.ndarray):
        um = np.ascontiguousarray(model_f32.reshape(4, 4).T, dtype=np.float32)
        uv = np.ascontiguousarray(view_f32.reshape(4, 4).T, dtype=np.float32)
        fused = uv @ um
        mv = np.ascontiguousarray(fused.T, dtype=np.float32)
        a = mv[:3, :3]
        t = mv[3, :3]
        ms = float(np.linalg.norm(a.astype(np.float64), axis=0).max())
        if not np.isfinite(ms) or ms <= 0.0:
            return None
        up = np.ascontiguousarray(proj_f32.reshape(4, 4).T, dtype=np.float32)
        p00 = float(up[0, 0])
        p11 = float(up[1, 1])
        p20 = float(up[0, 2])
        p21 = float(up[1, 2])
        perspective = abs(float(up[3, 2]) + 1.0) < 1e-3
        return mv, a, t, ms, p00, p11, p20, p21, perspective

    def _cloud_culled(self, path: str, a: np.ndarray, t: np.ndarray, ms: float,
                      p00: float, p11: float, p20: float, p21: float, perspective: bool) -> bool:
        if not perspective:
            return False
        center = self._center.get(path)
        radius = float(self._radius.get(path, 0.0))
        if center is None or radius < 0.0:
            return False
        vc = center @ a + t
        w = float(-vc[2])
        rw = radius * ms
        if w + rw < 0.2:
            return True
        if w > 0.0:
            nx = (float(vc[0]) * p00 + float(vc[2]) * p20) / w
            ny = (float(vc[1]) * p11 + float(vc[2]) * p21) / w
            rx = rw * abs(p00) / w
            ry = rw * abs(p11) / w
            if nx < -1.0 - rx or nx > 1.0 + rx or ny < -1.0 - ry or ny > 1.0 + ry:
                return True
        return False

    def _visible_order(self, path: str, model_f32: np.ndarray, view_f32: np.ndarray,
                       proj_f32: np.ndarray, opacity_threshold: float,
                       cache_id=None) -> tuple[bytes, np.ndarray]:
        key = self._frame_key(model_f32, view_f32, proj_f32, opacity_threshold)
        slot_id = (path, key[:64], cache_id)
        slot = self._sort_cache.get(slot_id)
        if slot is not None and slot[0] == key:
            return key, slot[1]
        reuse = slot[1] if slot is not None else None
        order = self._compute_order(path, model_f32, view_f32, proj_f32, opacity_threshold, reuse)
        if slot is None and len(self._sort_cache) >= 12:
            self._sort_cache.pop(next(iter(self._sort_cache)))
        self._sort_cache[slot_id] = [key, order]
        return key, order

    def _scratch_for(self, path: str, n: int) -> dict[str, np.ndarray]:
        sc = self._scratch.get(path)
        if sc is None or len(sc["keep"]) < n:
            sc = {
                "keep": np.zeros(n, dtype=np.uint8),
                "wbuf": np.empty(n, dtype=np.float32),
                "cidx": np.empty(n, dtype=np.uint32),
                "cdep": np.empty(n, dtype=np.float32),
                "tmp": np.empty(n, dtype=np.uint32),
                "k1": np.empty(n, dtype=np.uint32),
                "k2": np.empty(n, dtype=np.uint32),
            }
            self._scratch[path] = sc
        return sc

    def _compute_order(self, path: str, model_f32: np.ndarray, view_f32: np.ndarray,
                       proj_f32: np.ndarray, opacity_threshold: float,
                       reuse: Optional[np.ndarray] = None) -> np.ndarray:
        pos = self._pos.get(path)
        opa = self._opa.get(path)
        srad = self._srad.get(path)
        if pos is None or opa is None or srad is None or len(pos) == 0:
            return _EMPTY_U32
        basis = self._sort_basis(model_f32, view_f32, proj_f32)
        if basis is None:
            return _EMPTY_U32
        mv, a, t, ms, p00, p11, p20, p21, perspective = basis
        if self._cloud_culled(path, a, t, ms, p00, p11, p20, p21, perspective):
            return _EMPTY_U32
        if _cython_available():
            n = len(pos)
            pos = np.ascontiguousarray(pos, dtype=np.float32)
            opa = np.ascontiguousarray(opa, dtype=np.float32)
            srad = np.ascontiguousarray(srad, dtype=np.float32)
            sc = self._scratch_for(path, n)
            _cython_cull_depth(pos, opa, srad, mv, np.float32(p00), np.float32(p11),
                               np.float32(p20), np.float32(p21),
                               np.float32(opacity_threshold), np.float32(ms),
                               bool(perspective), sc["keep"], sc["wbuf"])
            count = int(_cython_compact(sc["keep"], sc["wbuf"], sc["cidx"], sc["cdep"]))
            if count == 0:
                return _EMPTY_U32
            if count < 4096:
                rev = np.argsort(np.asarray(sc["cdep"][:count]))[::-1].astype(np.uint32)
                _cython_remap(np.ascontiguousarray(rev), sc["cidx"], count)
                return np.ascontiguousarray(rev)
            if reuse is not None and len(reuse) >= count:
                out = reuse[:count]
            else:
                out = np.empty(count, dtype=np.uint32)
            _cython_radix(sc["cdep"][:count], out, sc["tmp"][:count],
                          sc["k1"][:count], sc["k2"][:count])
            _cython_remap(out, sc["cidx"], count)
            return out
        else:
            v = pos @ a + t
            w = -v[:, 2]
            thr = np.float32(opacity_threshold)
            fms = np.float32(ms)
            if perspective:
                r = srad * fms
                idx = np.flatnonzero((opa > thr) & ((w + r) > np.float32(0.2)))
                if idx.size == 0:
                    return _EMPTY_U32
                if idx.size < len(pos):
                    v = v[idx]
                    w = w[idx]
                    r = r[idx]
                else:
                    idx = None
                fp00 = np.float32(p00)
                fp11 = np.float32(p11)
                fp20 = np.float32(p20)
                fp21 = np.float32(p21)
                inv = np.float32(1.0) / np.maximum(w, np.float32(1e-6))
                nx = (v[:, 0] * fp00 + v[:, 2] * fp20) * inv
                ny = (v[:, 1] * fp11 + v[:, 2] * fp21) * inv
                mx = r * np.float32(abs(p00)) * inv + np.float32(0.02)
                my = r * np.float32(abs(p11)) * inv + np.float32(0.02)
                loc = np.flatnonzero((nx >= -1.0 - mx) & (nx <= 1.0 + mx) & (ny >= -1.0 - my) & (ny <= 1.0 + my))
                if loc.size == 0:
                    return _EMPTY_U32
                w = w[loc]
                if idx is not None:
                    idx = idx[loc]
                else:
                    idx = loc
            else:
                idx = np.flatnonzero(opa > thr)
                if idx.size == 0:
                    return _EMPTY_U32
                if idx.size < len(pos):
                    w = w[idx]
                else:
                    idx = None
        rev = np.argsort(w)[::-1]
        if idx is not None:
            return np.ascontiguousarray(idx[rev], dtype=np.uint32)
        return np.ascontiguousarray(rev, dtype=np.uint32)

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

    def prepare(self, path: str, model_matrix, view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
                opacity_threshold=0.005, sh_degree=3, cache_id=None) -> tuple[int, int]:
        if not self._prog or not self._vao:
            return 0, 0
        if path not in self._gpu_data:
            if not self.load_data(path):
                return 0, 0

        gpu = self._gpu_data.get(path)
        if gpu is None or len(gpu) == 0:
            return 0, 0

        n = len(gpu)
        model_f32 = np.ascontiguousarray(model_matrix.to_f32(), dtype=np.float32)
        view_f32 = np.ascontiguousarray(view_mat.to_f32(), dtype=np.float32)
        proj_f32 = np.ascontiguousarray(proj_mat.to_f32(), dtype=np.float32)

        key, order = self._visible_order(path, model_f32, view_f32, proj_f32, opacity_threshold, cache_id)
        m = len(order)
        if m == 0:
            return 0, n
        self._ensure_buffers(n)
        if self._uploaded_path != path or self._uploaded_n != n:
            try:
                self._ssbo.orphan(self._ssbo.size)
            except Exception:
                pass
            self._ssbo.write(gpu)
            self._uploaded_path = path
            self._uploaded_n = n
        self._ssbo.bind_to_storage_buffer(0)
        if self._idx_key is None or self._idx_key[0] != path or self._idx_key[1] != key:
            try:
                self._idx_ssbo.orphan(self._idx_ssbo.size)
            except Exception:
                pass
            self._idx_ssbo.write(order)
            self._idx_key = (path, key)
        self._idx_ssbo.bind_to_storage_buffer(1)
        self._upload_uniforms(model_f32, view_f32, proj_f32, cam_pos,
                              viewport_w, viewport_h, sh_degree, opacity_threshold)
        return m, n

    def draw_color(self, m: int):
        if not self._vao or m <= 0:
            return
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.depth_mask = False

        try:
            self._vao.render(moderngl.TRIANGLE_STRIP, vertices=4, instances=m)
        except Exception as e:
            Logger.error(f"Gaussian Splat render error: {e}")

        self._ctx.enable(moderngl.CULL_FACE)
        self._ctx.depth_mask = True
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def render(self, path: str, model_matrix, view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               opacity_threshold=0.005, sh_degree=3, cache_id=None):
        m, _ = self.prepare(path, model_matrix, view_mat, proj_mat, cam_pos,
                             viewport_w, viewport_h, opacity_threshold, sh_degree, cache_id)
        self.draw_color(m)

    def release(self):
        with self._load_lock:
            pending = list(self._loading)
            self._loading.clear()
            self._completed = []
            self._failed.clear()
            self._fractions.clear()
        for path in pending:
            try:
                task_complete(_splat_task_id(path))
            except Exception:
                pass
        if self._vao:
            self._vao.release()
        if self._ssbo:
            self._ssbo.release()
        if self._idx_ssbo:
            self._idx_ssbo.release()
        if self._prog:
            self._prog.release()
        self._vao = None
        self._ssbo = None
        self._idx_ssbo = None
        self._prog = None
        self._gpu_data.clear()
        self._pos.clear()
        self._opa.clear()
        self._srad.clear()
        self._center.clear()
        self._radius.clear()
        self._sort_cache.clear()
        self._scratch.clear()
        self._idx_key = None
        self._uploaded_path = None
        self._uploaded_n = 0
