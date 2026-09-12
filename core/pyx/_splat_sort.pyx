# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

# cython: boundscheck=False, wraparound=False, cdivision=True, nonecheck=False, initializedcheck=False, overflowcheck=False
# distutils: extra_compile_args = -O3 -ffast-math -march=native -fopenmp
# distutils: extra_link_args = -fopenmp
import numpy as np
cimport numpy as cnp
from cython.parallel import prange


def splat_cull_depth(cnp.float32_t[:, :] pos,
                     cnp.float32_t[:] opa,
                     cnp.float32_t[:] srad,
                     cnp.float32_t[:, :] mv,
                     float p00,
                     float p11,
                     float p20,
                     float p21,
                     float thr,
                     float ms,
                     bint persp,
                     cnp.uint8_t[:] keep,
                     cnp.float32_t[:] wout):
    cdef Py_ssize_t n = pos.shape[0]
    cdef Py_ssize_t i
    cdef float m00 = mv[0, 0]
    cdef float m10 = mv[1, 0]
    cdef float m20 = mv[2, 0]
    cdef float m01 = mv[0, 1]
    cdef float m11 = mv[1, 1]
    cdef float m21 = mv[2, 1]
    cdef float m02 = mv[0, 2]
    cdef float m12 = mv[1, 2]
    cdef float m22 = mv[2, 2]
    cdef float t0 = mv[3, 0]
    cdef float t1 = mv[3, 1]
    cdef float t2 = mv[3, 2]
    cdef float ap00 = p00 if p00 >= 0.0 else -p00
    cdef float ap11 = p11 if p11 >= 0.0 else -p11
    cdef float fms = ms
    cdef float fthr = thr
    cdef float x, y, z, vx, vy, vz, ww, rr, inv, nx, ny, mx, my
    with nogil:
        for i in prange(n, schedule='static'):
            if opa[i] <= fthr:
                keep[i] = 0
                continue
            x = pos[i, 0]
            y = pos[i, 1]
            z = pos[i, 2]
            vx = x * m00 + y * m10 + z * m20 + t0
            vy = x * m01 + y * m11 + z * m21 + t1
            vz = x * m02 + y * m12 + z * m22 + t2
            ww = -vz
            rr = srad[i] * fms
            if ww + rr <= 0.2:
                keep[i] = 0
                continue
            if persp:
                if ww > 0.000001:
                    inv = 1.0 / ww
                    nx = (vx * p00 + vz * p20) * inv
                    ny = (vy * p11 + vz * p21) * inv
                    mx = rr * ap00 * inv + 0.02
                    my = rr * ap11 * inv + 0.02
                    if nx < -1.0 - mx or nx > 1.0 + mx or ny < -1.0 - my or ny > 1.0 + my:
                        keep[i] = 0
                        continue
                else:
                    nx = vx * p00 + vz * p20
                    ny = vy * p11 + vz * p21
                    mx = rr * ap00 + 0.0000011
                    my = rr * ap11 + 0.0000011
                    if nx < -mx or nx > mx or ny < -my or ny > my:
                        keep[i] = 0
                        continue
            keep[i] = 1
            wout[i] = ww


from libc.string cimport memcpy


cdef inline cnp.uint32_t _far_key(float w) noexcept nogil:
    cdef cnp.uint32_t u = 0
    cdef cnp.uint32_t HI = <cnp.uint32_t>1 << 31
    cdef cnp.uint32_t ALL = ~<cnp.uint32_t>0
    cdef cnp.uint32_t o
    memcpy(&u, &w, 4)
    if (u & HI) != 0:
        o = u ^ ALL
    else:
        o = u ^ HI
    return ALL - o


def compact_keep(cnp.uint8_t[:] keep,
                 cnp.float32_t[:] wbuf,
                 cnp.uint32_t[:] cidx,
                 cnp.float32_t[:] cdep):
    cdef Py_ssize_t n = keep.shape[0]
    cdef Py_ssize_t i
    cdef Py_ssize_t count = 0
    for i in range(n):
        if keep[i]:
            cidx[count] = <cnp.uint32_t>i
            cdep[count] = wbuf[i]
            count += 1
    return count


def remap_order(cnp.uint32_t[:] order,
                cnp.uint32_t[:] cidx,
                Py_ssize_t count):
    cdef Py_ssize_t i
    for i in range(count):
        order[i] = cidx[order[i]]


def radix_sort_into(cnp.float32_t[:] depths,
                    cnp.uint32_t[:] order,
                    cnp.uint32_t[:] tmp,
                    cnp.uint32_t[:] k1,
                    cnp.uint32_t[:] k2):
    cdef Py_ssize_t n = depths.shape[0]
    if n == 0:
        return
    cdef int chunks = 8
    if n < 4096:
        chunks = 1
    cdef Py_ssize_t cs = (n + chunks - 1) // chunks
    cdef Py_ssize_t i
    cdef int c
    cdef int b
    cdef int shift
    cdef Py_ssize_t lo
    cdef Py_ssize_t hi
    cdef cnp.uint32_t[:] src_o
    cdef cnp.uint32_t[:] dst_o
    cdef cnp.uint32_t[:] src_k
    cdef cnp.uint32_t[:] dst_k
    cdef cnp.uint32_t hist[8][256]
    cdef cnp.uint32_t starts[8][256]
    cdef cnp.uint32_t nxt[8][256]
    cdef cnp.uint32_t d
    with nogil:
        for i in prange(n, schedule='static'):
            order[i] = <cnp.uint32_t>i
            k1[i] = _far_key(depths[i])
    for shift in range(0, 32, 8):
        if (shift // 8) % 2 == 0:
            src_o = order
            dst_o = tmp
            src_k = k1
            dst_k = k2
        else:
            src_o = tmp
            dst_o = order
            src_k = k2
            dst_k = k1
        with nogil:
            for c in range(chunks):
                for b in range(256):
                    hist[c][b] = 0
            for c in prange(chunks, schedule='static'):
                lo = c * cs
                hi = lo + cs
                if hi > n:
                    hi = n
                for i in range(lo, hi):
                    hist[c][(src_k[i] >> shift) & 255] += 1
            d = 0
            for b in range(256):
                for c in range(chunks):
                    starts[c][b] = d
                    d = d + hist[c][b]
            for c in prange(chunks, schedule='static'):
                for b in range(256):
                    nxt[c][b] = starts[c][b]
                lo = c * cs
                hi = lo + cs
                if hi > n:
                    hi = n
                for i in range(lo, hi):
                    b = (src_k[i] >> shift) & 255
                    d = nxt[c][b]
                    nxt[c][b] = d + 1
                    dst_k[d] = src_k[i]
                    dst_o[d] = src_o[i]


def radix_sort_order(cnp.float32_t[:] depths):
    cdef Py_ssize_t n = depths.shape[0]
    cdef cnp.ndarray[cnp.uint32_t, ndim=1] order = np.empty(n, dtype=np.uint32)
    cdef cnp.ndarray[cnp.uint32_t, ndim=1] tmp = np.empty(n, dtype=np.uint32)
    cdef cnp.ndarray[cnp.uint32_t, ndim=1] keys = np.empty(n, dtype=np.uint32)
    cdef cnp.ndarray[cnp.uint32_t, ndim=1] keys2 = np.empty(n, dtype=np.uint32)
    radix_sort_into(depths, order, tmp, keys, keys2)
    return order
