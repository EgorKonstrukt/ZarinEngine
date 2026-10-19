# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
import moderngl
from typing import Optional
from .resources import _EMPTY_U32
from .resources import _SPLAT_MAX_SORTS_PER_FRAME
from .resources import _SPLAT_GPU_MIN_N
from .resources import _SPLAT_GPU_SORTS_PER_FRAME
from .resources import _SPLAT_GPU_GROUPS
from .resources import _SPLAT_GPU_ROWS
from .resources import _SPLAT_MIN_PX
from .volume import _GS_B_POS
from .volume import _GS_B_OPA
from .volume import _GS_B_SRAD
from .volume import _GS_B_KEYS
from .volume import _GS_B_VALS
from .volume import _GS_B_COUNT
from .volume import _GS_B_HIST
from .volume import _GS_B_OFFS
from .volume import _GS_B_KEYS2
from .volume import _GS_B_VALS2
from .volume import _GS_B_CMD

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


class _SplatSortMixin:
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
        c0 = math.sqrt(float(a[0, 0] * a[0, 0] + a[1, 0] * a[1, 0] + a[2, 0] * a[2, 0]))
        c1 = math.sqrt(float(a[0, 1] * a[0, 1] + a[1, 1] * a[1, 1] + a[2, 1] * a[2, 1]))
        c2 = math.sqrt(float(a[0, 2] * a[0, 2] + a[1, 2] * a[1, 2] + a[2, 2] * a[2, 2]))
        ms = c0
        if c1 > ms:
            ms = c1
        if c2 > ms:
            ms = c2
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
                       cache_id=None, px_scale: float = 0.0, min_px: float = 0.0) -> tuple[bytes, np.ndarray]:
        key = self._frame_key(model_f32, view_f32, proj_f32, opacity_threshold)
        try:
            key = key + np.float32(px_scale).tobytes() + np.float32(min_px).tobytes()
        except Exception:
            pass
        slot_id = (path, key[:64], cache_id)
        slot = self._sort_cache.get(slot_id)
        if slot is not None and slot[0] == key:
            if slot[1] is not None and len(slot[1]) > 0:
                self._last_order[path] = slot[1]
            return key, slot[1]
        if self._sorts_this_frame >= _SPLAT_MAX_SORTS_PER_FRAME:
            prev = self._last_order.get(path)
            if prev is not None and len(prev) > 0:
                return key, prev
            return key, _EMPTY_U32
        self._sorts_this_frame += 1
        reuse = slot[1] if slot is not None else None
        order = self._compute_order(path, model_f32, view_f32, proj_f32, opacity_threshold, reuse,
                                    px_scale, min_px)
        if slot is None and len(self._sort_cache) >= 12:
            self._sort_cache.pop(next(iter(self._sort_cache)))
        self._sort_cache[slot_id] = [key, order]
        if len(order) > 0:
            self._last_order[path] = order
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
                       reuse: Optional[np.ndarray] = None,
                       px_scale: float = 0.0, min_px: float = 0.0) -> np.ndarray:
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
                               bool(perspective), np.float32(px_scale), np.float32(min_px),
                               sc["keep"], sc["wbuf"])
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
                if min_px > 0.0 and px_scale > 0.0:
                    fpx = np.float32(px_scale)
                    fmp = np.float32(min_px)
                    ap0 = np.float32(abs(float(fp00)))
                    ap1 = np.float32(abs(float(fp11)))
                    pmax = ap0 if ap0 >= ap1 else ap1
                    wl = w[loc]
                    rl = r[loc]
                    big = wl > np.float32(1e-6)
                    pr = np.empty_like(wl)
                    bv = wl[big]
                    pr[big] = rl[big] * pmax / bv * fpx
                    pr[~big] = np.float32(1e30)
                    keepm = pr >= fmp
                    if not bool(keepm.all()):
                        loc = loc[keepm]
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
                if min_px > 0.0 and px_scale > 0.0:
                    fpx = np.float32(px_scale)
                    fmp = np.float32(min_px)
                    ap0 = np.float32(abs(float(p00)))
                    ap1 = np.float32(abs(float(p11)))
                    pmax = ap0 if ap0 >= ap1 else ap1
                    rr = (srad * fms)[idx] if idx is not None else (srad * fms)
                    keepm = (rr * pmax * fpx) >= fmp
                    if not bool(keepm.all()):
                        w = w[keepm]
                        if w.size == 0:
                            return _EMPTY_U32
                        idx = idx[keepm] if idx is not None else np.flatnonzero(keepm)
        rev = np.argsort(w)[::-1]
        if idx is not None:
            return np.ascontiguousarray(idx[rev], dtype=np.uint32)
        return np.ascontiguousarray(rev, dtype=np.uint32)

    def _prepare_gpu(self, path: str, model_f32: np.ndarray, view_f32: np.ndarray,
                     proj_f32: np.ndarray, cam_pos, viewport_w, viewport_h,
                     opacity_threshold: float, sh_degree: int, cache_id, n: int,
                     px_scale: float = 0.0) -> bool:
        try:
            if not self._ensure_compute():
                return None
            if n < _SPLAT_GPU_MIN_N or not self._ensure_gs_scratch(n):
                return None
            if not self._ensure_gpu_bufs(path, n):
                return None
            done = int(self._gs_up.get(path, 0))
            if done < n:
                pos = self._pos.get(path)
                opa = self._opa.get(path)
                srad = self._srad.get(path)
                if pos is None or opa is None or srad is None:
                    return None
                r1 = min(n, done + _SPLAT_GPU_ROWS)
                try:
                    self._gs_pos[path].write(np.ascontiguousarray(pos[done:r1]).tobytes(), offset=done * 12)
                    self._gs_opa[path].write(np.ascontiguousarray(opa[done:r1]).tobytes(), offset=done * 4)
                    self._gs_srad[path].write(np.ascontiguousarray(srad[done:r1]).tobytes(), offset=done * 4)
                except Exception:
                    return None
                self._gs_up[path] = r1
                if r1 < n:
                    return None
            key = self._frame_key(model_f32, view_f32, proj_f32, opacity_threshold)
            gk = (path, cache_id)
            if self._gs_key.get(gk) == key:
                self._bind_gpu_draw(path, model_f32, view_f32, proj_f32, cam_pos,
                                    viewport_w, viewport_h, sh_degree, opacity_threshold)
                return key, True
            if self._gpu_sorts_this_frame >= _SPLAT_GPU_SORTS_PER_FRAME:
                return None
            self._gpu_sorts_this_frame += 1
            basis = self._sort_basis(model_f32, view_f32, proj_f32)
            if basis is None:
                return None
            mv, _a, _t, ms, p00, p11, p20, p21, perspective = basis
            groups = _SPLAT_GPU_GROUPS
            progs = self._cs_progs
            try:
                self._gs_counter.write(np.zeros(1, dtype=np.uint32).tobytes())
            except Exception:
                return None
            try:
                self._gs_pos[path].bind_to_storage_buffer(_GS_B_POS)
                self._gs_opa[path].bind_to_storage_buffer(_GS_B_OPA)
                self._gs_srad[path].bind_to_storage_buffer(_GS_B_SRAD)
                self._gs_keys0.bind_to_storage_buffer(_GS_B_KEYS)
                self._gs_vals0.bind_to_storage_buffer(_GS_B_VALS)
                self._gs_counter.bind_to_storage_buffer(_GS_B_COUNT)
            except Exception:
                return None
            try:
                cu = progs["cull"]
                cu["u_mv"].write(np.ascontiguousarray(mv, dtype=np.float32).tobytes())
                cu["u_p00"].value = float(p00)
                cu["u_p11"].value = float(p11)
                cu["u_p20"].value = float(p20)
                cu["u_p21"].value = float(p21)
                cu["u_thr"].value = float(opacity_threshold)
                cu["u_ms"].value = float(ms)
                cu["u_persp"].value = 1 if perspective else 0
                cu["u_n"].value = int(n)
                try:
                    _px = float(px_scale)
                except Exception:
                    _px = 0.0
                cu["u_px"].value = _px
                try:
                    _mpx = float(_SPLAT_MIN_PX) if _px > 0.0 else 0.0
                except Exception:
                    _mpx = 0.0
                cu["u_min_px"].value = _mpx
                cu.run((n + 255) // 256, 1, 1)
            except Exception:
                return None
            self._gpu_barrier()
            kb = [self._gs_keys0, self._gs_keys1]
            vb = [self._gs_vals0, self._gs_vals1]
            try:
                hi = progs["hist"]
                sc = progs["scan"]
                st = progs["scatter"]
                for pi, shift in enumerate((0, 8, 16, 24)):
                    rk = kb[pi % 2]
                    rv = vb[pi % 2]
                    wk = kb[1 - pi % 2]
                    wv = vb[1 - pi % 2]
                    rk.bind_to_storage_buffer(_GS_B_KEYS)
                    self._gs_hist.bind_to_storage_buffer(_GS_B_HIST)
                    self._gs_offs.bind_to_storage_buffer(_GS_B_OFFS)
                    hi["u_n"].value = int(n)
                    hi["u_shift"].value = int(shift)
                    hi.run(groups, 1, 1)
                    self._gpu_barrier()
                    sc["u_groups"].value = int(groups)
                    sc.run(1, 1, 1)
                    self._gpu_barrier()
                    rk.bind_to_storage_buffer(_GS_B_KEYS)
                    rv.bind_to_storage_buffer(_GS_B_VALS)
                    wk.bind_to_storage_buffer(_GS_B_KEYS2)
                    wv.bind_to_storage_buffer(_GS_B_VALS2)
                    self._gs_offs.bind_to_storage_buffer(_GS_B_OFFS)
                    st["u_n"].value = int(n)
                    st["u_shift"].value = int(shift)
                    st.run(groups, 1, 1)
                    self._gpu_barrier()
                cp = progs["copy"]
                self._gs_vals0.bind_to_storage_buffer(_GS_B_KEYS)
                self._gs_order[path].bind_to_storage_buffer(_GS_B_VALS)
                cp["u_n"].value = int(n)
                cp.run((n + 255) // 256, 1, 1)
                self._gpu_barrier()
            except Exception:
                return None
            try:
                ind = progs["indirect"]
                self._gs_counter.bind_to_storage_buffer(_GS_B_COUNT)
                self._gs_cmd[path].bind_to_storage_buffer(_GS_B_CMD)
                ind["u_cap"].value = int(n)
                ind.run(1, 1, 1)
            except Exception:
                return None
            try:
                self._ctx.memory_barrier(moderngl.SHADER_STORAGE_BARRIER_BIT | moderngl.COMMAND_BARRIER_BIT)
            except Exception:
                pass
            self._gs_key[gk] = key
            self._bind_gpu_draw(path, model_f32, view_f32, proj_f32, cam_pos,
                                viewport_w, viewport_h, sh_degree, opacity_threshold)
            return key, False
        except Exception:
            return None
