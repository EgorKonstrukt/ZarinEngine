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
from libc.math cimport floorf


def splat_occupancy(cnp.float32_t[:, :] pos,
                    cnp.float32_t[:, :] scales,
                    cnp.float32_t[:] opa,
                    float thr,
                    float voxel,
                    float cover,
                    float ox, float oy, float oz,
                    Py_ssize_t nx, Py_ssize_t ny, Py_ssize_t nz,
                    cnp.uint8_t[:] out):
    cdef Py_ssize_t n = pos.shape[0]
    cdef Py_ssize_t i
    cdef float inv = 1.0 / voxel
    cdef float x, y, z, o, s0, s1, s2, smax, h
    cdef Py_ssize_t ix, iy, iz
    cdef Py_ssize_t x0, x1, y0, y1, z0, z1, xx, yy, zz
    cdef Py_ssize_t hi
    with nogil:
        for i in prange(n, schedule='static'):
            o = opa[i]
            if not (o >= thr):
                continue
            x = pos[i, 0]
            y = pos[i, 1]
            z = pos[i, 2]
            if x != x or y != y or z != z:
                continue
            if x > 3.402823e38 or x < -3.402823e38:
                continue
            if y > 3.402823e38 or y < -3.402823e38:
                continue
            if z > 3.402823e38 or z < -3.402823e38:
                continue
            s0 = scales[i, 0]
            s1 = scales[i, 1]
            s2 = scales[i, 2]
            smax = s0
            if s1 > smax:
                smax = s1
            if s2 > smax:
                smax = s2
            if smax != smax:
                continue
            h = cover * smax * inv - 0.5
            if h <= 0.0:
                hi = 0
            elif h >= 8.0:
                hi = 8
            else:
                hi = <Py_ssize_t>(h + 1.0)
            ix = <Py_ssize_t>floorf((x - ox) * inv)
            iy = <Py_ssize_t>floorf((y - oy) * inv)
            iz = <Py_ssize_t>floorf((z - oz) * inv)
            x0 = ix - hi
            x1 = ix + hi
            y0 = iy - hi
            y1 = iy + hi
            z0 = iz - hi
            z1 = iz + hi
            if x0 < 0:
                x0 = 0
            if y0 < 0:
                y0 = 0
            if z0 < 0:
                z0 = 0
            if x1 >= nx:
                x1 = nx - 1
            if y1 >= ny:
                y1 = ny - 1
            if z1 >= nz:
                z1 = nz - 1
            if x0 > x1 or y0 > y1 or z0 > z1:
                continue
            for zz in range(z0, z1 + 1):
                for yy in range(y0, y1 + 1):
                    for xx in range(x0, x1 + 1):
                        out[(zz * ny + yy) * nx + xx] = 1


def dilate26(cnp.uint8_t[:] src,
             cnp.uint8_t[:] dst,
             Py_ssize_t nx, Py_ssize_t ny, Py_ssize_t nz):
    cdef Py_ssize_t x, y, z, xx, yy, zz, i
    cdef Py_ssize_t v
    with nogil:
        for z in prange(nz, schedule='static'):
            for y in range(ny):
                for x in range(nx):
                    i = (z * ny + y) * nx + x
                    if src[i]:
                        dst[i] = 1
                        continue
                    v = 0
                    for zz in range(z - 1, z + 2):
                        if zz < 0 or zz >= nz:
                            continue
                        for yy in range(y - 1, y + 2):
                            if yy < 0 or yy >= ny:
                                continue
                            for xx in range(x - 1, x + 2):
                                if xx < 0 or xx >= nx:
                                    continue
                                if src[(zz * ny + yy) * nx + xx]:
                                    v = 1
                                    break
                            if v:
                                break
                        if v:
                            break
                    dst[i] = v


def greedy_merge_boxes(cnp.uint8_t[:] occ,
                       Py_ssize_t nx, Py_ssize_t ny, Py_ssize_t nz,
                       cnp.uint8_t[:] mask,
                       cnp.float32_t[:, :] out,
                       Py_ssize_t cap):
    cdef Py_ssize_t x, y, z, xx, yy, zz
    cdef Py_ssize_t x1, y1, z1
    cdef Py_ssize_t i, j
    cdef Py_ssize_t count = 0
    cdef int ok
    for i in range(nx * ny * nz):
        mask[i] = 0
    for z in range(nz):
        for y in range(ny):
            for x in range(nx):
                i = (z * ny + y) * nx + x
                if occ[i] == 0 or mask[i]:
                    continue
                x1 = x
                while x1 + 1 < nx:
                    j = (z * ny + y) * nx + x1 + 1
                    if occ[j] == 0 or mask[j]:
                        break
                    x1 += 1
                y1 = y
                while y1 + 1 < ny:
                    ok = 1
                    for xx in range(x, x1 + 1):
                        j = ((y1 + 1) * nx + xx) + z * ny * nx
                        if occ[j] == 0 or mask[j]:
                            ok = 0
                            break
                    if not ok:
                        break
                    y1 += 1
                z1 = z
                while z1 + 1 < nz:
                    ok = 1
                    for yy in range(y, y1 + 1):
                        for xx in range(x, x1 + 1):
                            j = ((z1 + 1) * ny + yy) * nx + xx
                            if occ[j] == 0 or mask[j]:
                                ok = 0
                                break
                        if not ok:
                            break
                    if not ok:
                        break
                    z1 += 1
                for zz in range(z, z1 + 1):
                    for yy in range(y, y1 + 1):
                        for xx in range(x, x1 + 1):
                            mask[(zz * ny + yy) * nx + xx] = 1
                if count >= cap:
                    return -1
                out[count, 0] = <float>x
                out[count, 1] = <float>y
                out[count, 2] = <float>z
                out[count, 3] = <float>x1
                out[count, 4] = <float>y1
                out[count, 5] = <float>z1
                count += 1
    return count
