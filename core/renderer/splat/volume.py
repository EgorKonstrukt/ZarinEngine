# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from core.foundation.logger import Logger
from .resources import _SPLAT_GPU_GROUPS

try:
    from core._gs_volume import splat_occupancy as _volume_occupancy
    from core._gs_volume import dilate26 as _volume_dilate
    from core._gs_volume import greedy_merge_boxes as _volume_merge
except Exception:
    _volume_occupancy = None
    _volume_dilate = None
    _volume_merge = None


def _volume_available() -> bool:
    return (_volume_occupancy is not None and _volume_dilate is not None
            and _volume_merge is not None)


_GS_B_POS = 2
_GS_B_OPA = 3
_GS_B_SRAD = 4
_GS_B_KEYS = 5
_GS_B_VALS = 6
_GS_B_COUNT = 7
_GS_B_HIST = 8
_GS_B_OFFS = 9
_GS_B_KEYS2 = 10
_GS_B_VALS2 = 11
_GS_B_CMD = 12

_GS_CULL_SRC = chr(35) + """version 430 core
layout(local_size_x = 256) in;
layout(std430, binding = 2) readonly buffer GsPos { float gs_pos[]; };
layout(std430, binding = 3) readonly buffer GsOpa { float gs_opa[]; };
layout(std430, binding = 4) readonly buffer GsSrad { float gs_srad[]; };
layout(std430, binding = 5) buffer GsKeys { uint gs_keys[]; };
layout(std430, binding = 6) buffer GsVals { uint gs_vals[]; };
layout(std430, binding = 7) buffer GsCount { uint gs_count; };
uniform mat4 u_mv;
uniform float u_p00;
uniform float u_p11;
uniform float u_p20;
uniform float u_p21;
uniform float u_thr;
uniform float u_ms;
uniform int u_persp;
uniform int u_n;
uniform float u_px;
uniform float u_min_px;
shared uint shc;
uint fkey(float w) {
    uint u = floatBitsToUint(w);
    uint o = ((u & 0x80000000u) != 0u) ? (u ^ 0xFFFFFFFFu) : (u ^ 0x80000000u);
    return 0xFFFFFFFFu - o;
}
void main() {
    if (gl_LocalInvocationID.x == 0u) {
        shc = 0u;
    }
    barrier();
    uint i = gl_GlobalInvocationID.x;
    if (int(i) < u_n) {
        uint key = 0xFFFFFFFFu;
        if (gs_opa[i] > u_thr) {
            vec3 p = vec3(gs_pos[i * 3u], gs_pos[i * 3u + 1u], gs_pos[i * 3u + 2u]);
            vec4 vp = u_mv * vec4(p, 1.0);
            float ww = -vp.z;
            float rr = gs_srad[i] * u_ms;
            if (ww + rr > 0.2) {
                bool vis = true;
                if (u_persp == 1) {
                    if (ww > 0.000001) {
                        float inv = 1.0 / ww;
                        float nx = (vp.x * u_p00 + vp.z * u_p20) * inv;
                        float ny = (vp.y * u_p11 + vp.z * u_p21) * inv;
                        float mx = rr * abs(u_p00) * inv + 0.02;
                        float my = rr * abs(u_p11) * inv + 0.02;
                        if (nx < -1.0 - mx || nx > 1.0 + mx || ny < -1.0 - my || ny > 1.0 + my) {
                            vis = false;
                        }
                    } else {
                        float nx = vp.x * u_p00 + vp.z * u_p20;
                        float ny = vp.y * u_p11 + vp.z * u_p21;
                        float mx = rr * abs(u_p00) + 0.0000011;
                        float my = rr * abs(u_p11) + 0.0000011;
                        if (nx < -mx || nx > mx || ny < -my || ny > my) {
                            vis = false;
                        }
                    }
                }
                if (vis && u_min_px > 0.0) {
                    float pr;
                    if (u_persp == 1) {
                        if (ww > 0.000001) {
                            pr = rr * max(abs(u_p00), abs(u_p11)) / ww * u_px;
                        } else {
                            pr = 1e30;
                        }
                    } else {
                        pr = rr * max(abs(u_p00), abs(u_p11)) * u_px;
                    }
                    if (pr < u_min_px) {
                        vis = false;
                    }
                }
                if (vis) {
                    key = fkey(ww);
                    atomicAdd(shc, 1u);
                }
            }
        }
        gs_keys[i] = key;
        gs_vals[i] = i;
    }
    barrier();
    if (gl_LocalInvocationID.x == 0u) {
        atomicAdd(gs_count, shc);
    }
}
"""

_GS_HIST_SRC = chr(35) + """version 430 core
layout(local_size_x = 256) in;
layout(std430, binding = 5) readonly buffer GsKeys { uint gs_keys[]; };
layout(std430, binding = 8) buffer GsHist { uint gs_hist[]; };
uniform int u_n;
uniform int u_shift;
shared uint sh[256];
void main() {
    uint lid = gl_LocalInvocationID.x;
    uint wid = gl_WorkGroupID.x;
    uint G = gl_NumWorkGroups.x;
    uint S = (uint(u_n) + G - 1u) / G;
    uint C0 = wid * S;
    uint C1 = C0 + S;
    if (C1 > uint(u_n)) {
        C1 = uint(u_n);
    }
    sh[lid] = 0u;
    barrier();
    for (uint idx = C0 + lid; idx < C1; idx += 256u) {
        uint bin = (gs_keys[idx] >> uint(u_shift)) & 255u;
        atomicAdd(sh[bin], 1u);
    }
    barrier();
    gs_hist[wid * 256u + lid] = sh[lid];
}
"""

_GS_SCAN_SRC = chr(35) + """version 430 core
layout(local_size_x = 256) in;
layout(std430, binding = 8) readonly buffer GsHist { uint gs_hist[]; };
layout(std430, binding = 9) buffer GsOffs { uint gs_offs[]; };
uniform int u_groups;
shared uint tot[256];
void main() {
    uint b = gl_LocalInvocationID.x;
    uint t = 0u;
    for (int g = 0; g < u_groups; g++) {
        t += gs_hist[uint(g) * 256u + b];
    }
    tot[b] = t;
    barrier();
    if (b == 0u) {
        uint run = 0u;
        for (uint i = 0u; i < 256u; i++) {
            uint v = tot[i];
            tot[i] = run;
            run += v;
        }
    }
    barrier();
    uint pre = tot[b];
    uint run = 0u;
    for (int g = 0; g < u_groups; g++) {
        gs_offs[uint(g) * 256u + b] = pre + run;
        run += gs_hist[uint(g) * 256u + b];
    }
}
"""

_GS_SCATTER_SRC = chr(35) + """version 430 core
layout(local_size_x = 128) in;
layout(std430, binding = 5) readonly buffer GsKeysA { uint ka[]; };
layout(std430, binding = 6) readonly buffer GsValsA { uint va[]; };
layout(std430, binding = 9) readonly buffer GsOffs { uint offs[]; };
layout(std430, binding = 10) buffer GsKeysB { uint kb[]; };
layout(std430, binding = 11) buffer GsValsB { uint vb[]; };
uniform int u_n;
uniform int u_shift;
shared uint cnt[2048];
shared uint pos[2048];
void main() {
    uint lid = gl_LocalInvocationID.x;
    uint wid = gl_WorkGroupID.x;
    uint G = gl_NumWorkGroups.x;
    uint S = (uint(u_n) + G - 1u) / G;
    uint C0 = wid * S;
    uint C1 = C0 + S;
    if (C1 > uint(u_n)) {
        C1 = uint(u_n);
    }
    uint T = (S + 127u) / 128u;
    uint lo = C0 + lid * T;
    uint hi = lo + T;
    if (hi > C1) {
        hi = C1;
    }
    for (uint r = 0u; r < 16u; r++) {
        for (uint k = 0u; k < 16u; k++) {
            cnt[lid * 16u + k] = 0u;
        }
        barrier();
        for (uint e = lo; e < hi; e++) {
            uint kk = ka[e];
            uint bb = (kk >> uint(u_shift)) & 255u;
            if (bb >= r * 16u && bb < r * 16u + 16u) {
                cnt[lid * 16u + (bb - r * 16u)] += 1u;
            }
        }
        barrier();
        if (lid < 16u) {
            uint bb = r * 16u + lid;
            uint base = offs[wid * 256u + bb];
            uint run = 0u;
            for (uint t = 0u; t < 128u; t++) {
                pos[t * 16u + lid] = base + run;
                run += cnt[t * 16u + lid];
            }
        }
        barrier();
        for (uint e = lo; e < hi; e++) {
            uint kk = ka[e];
            uint bb = (kk >> uint(u_shift)) & 255u;
            if (bb >= r * 16u && bb < r * 16u + 16u) {
                uint dst = pos[lid * 16u + (bb - r * 16u)];
                pos[lid * 16u + (bb - r * 16u)] = dst + 1u;
                kb[dst] = kk;
                vb[dst] = va[e];
            }
        }
        barrier();
    }
}
"""

_GS_COPY_SRC = chr(35) + """version 430 core
layout(local_size_x = 256) in;
layout(std430, binding = 5) readonly buffer GsVals { uint gs_vals[]; };
layout(std430, binding = 6) buffer GsOrder { uint gs_order[]; };
uniform int u_n;
void main() {
    uint i = gl_GlobalInvocationID.x;
    if (int(i) >= u_n) {
        return;
    }
    gs_order[i] = gs_vals[i];
}
"""

_GS_INDIRECT_SRC = chr(35) + """version 430 core
layout(local_size_x = 1) in;
layout(std430, binding = 7) readonly buffer GsCount { uint gs_count; };
layout(std430, binding = 12) buffer GsCmd { uint gs_cmd[]; };
uniform uint u_cap;
void main() {
    uint c = gs_count;
    if (c > u_cap) {
        c = u_cap;
    }
    gs_cmd[0] = 4u;
    gs_cmd[1] = c;
    gs_cmd[2] = 0u;
    gs_cmd[3] = 0u;
    gs_cmd[4] = 0u;
}
"""


class _SplatVolumeMixin:
    def _ensure_compute(self) -> bool:
        if self._cs_ok is not None:
            return self._cs_ok
        try:
            from core.assets.compute_shader import compile_compute_shader
            jobs = (
                ("cull", _GS_CULL_SRC),
                ("hist", _GS_HIST_SRC),
                ("scan", _GS_SCAN_SRC),
                ("scatter", _GS_SCATTER_SRC),
                ("copy", _GS_COPY_SRC),
                ("indirect", _GS_INDIRECT_SRC),
            )
            for name, src in jobs:
                prog = compile_compute_shader(self._ctx, src, f"splat_{name}")
                if prog is None:
                    raise RuntimeError(f"splat compute {name}")
                self._cs_progs[name] = prog
            try:
                self._gs_hist = self._ctx.buffer(reserve=_SPLAT_GPU_GROUPS * 256 * 4)
                self._gs_offs = self._ctx.buffer(reserve=_SPLAT_GPU_GROUPS * 256 * 4)
                self._gs_counter = self._ctx.buffer(reserve=4)
                self._gs_indirect = self._ctx.buffer(reserve=20)
            except Exception:
                raise RuntimeError("splat compute buffers")
            self._cs_ok = True
        except Exception as e:
            try:
                Logger.error(f"GaussianSplatRenderer GPU sort disabled: {e}")
            except Exception:
                pass
            self._cs_ok = False
        return bool(self._cs_ok)

    def _ensure_gs_scratch(self, n: int) -> bool:
        try:
            if n <= 0:
                return False
            if self._gs_scratch_n >= n and self._gs_keys0 is not None:
                return True
            cap = max(64, int(n))
            for attr in ("_gs_keys0", "_gs_keys1", "_gs_vals0", "_gs_vals1"):
                old = getattr(self, attr)
                if old is not None:
                    try:
                        old.release()
                    except Exception:
                        pass
                setattr(self, attr, self._ctx.buffer(reserve=cap * 4))
            self._gs_scratch_n = cap
            return True
        except Exception:
            return False

    def _ensure_gpu_bufs(self, path: str, n: int) -> bool:
        try:
            if n <= 0:
                return False
            ok = True
            need = ((n * 12, "_gs_pos"), (n * 4, "_gs_opa"), (n * 4, "_gs_srad"),
                    (n * 4, "_gs_order"), (20, "_gs_cmd"))
            for size, attr in need:
                d = getattr(self, attr)
                buf = d.get(path)
                if buf is None or buf.size < size:
                    if buf is not None:
                        try:
                            buf.release()
                        except Exception:
                            pass
                    d[path] = self._ctx.buffer(reserve=max(64, int(size)))
                    if attr != "_gs_cmd":
                        self._gs_up[path] = 0
                    else:
                        try:
                            d[path].write(np.array([4, 0, 0, 0, 0], dtype=np.uint32).tobytes())
                        except Exception:
                            pass
                ok = ok and d.get(path) is not None
            return bool(ok)
        except Exception:
            return False

    def _gpu_barrier(self):
        try:
            self._ctx.memory_barrier(moderngl.SHADER_STORAGE_BARRIER_BIT)
        except Exception:
            pass
