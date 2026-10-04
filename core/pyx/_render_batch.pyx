# cython: boundscheck=False, wraparound=False, cdivision=True, nonecheck=False
import numpy as np
cimport numpy as np
from libc.math cimport sqrt

DTYPE = np.float64
ctypedef np.float64_t DTYPE_t

def build_instance_matrices(list entries):
    cdef int n = len(entries)
    if n == 0:
        return np.zeros((0, 4, 4), dtype=np.float32)

    cdef np.ndarray[np.float32_t, ndim=3] out = np.empty((n, 4, 4), dtype=np.float32)
    cdef int i
    cdef object entry, wm
    cdef DTYPE_t[:, :] d
    cdef int j, k

    for i in range(n):
        entry = entries[i]
        wm = entry[4]
        d = wm._d
        for j in range(4):
            for k in range(4):
                out[i, j, k] = <np.float32_t>d[j, k]
    return out

def build_bounding_spheres_batch(list entries, np.ndarray[DTYPE_t, ndim=1] bounding_radii):
    cdef int n = len(entries)
    if n == 0:
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0, 3), dtype=np.float32), np.zeros(0, dtype=np.float32)

    cdef np.ndarray[np.float32_t, ndim=2] centers = np.empty((n, 3), dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=2] spheres = np.empty((n, 4), dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=1] radii = np.empty(n, dtype=np.float32)
    cdef int i
    cdef double sx, sy, sz, ms
    cdef object entry, wm
    cdef DTYPE_t[:, :] d

    for i in range(n):
        entry = entries[i]
        wm = entry[4]
        d = wm._d
        centers[i, 0] = <np.float32_t>d[3, 0]
        centers[i, 1] = <np.float32_t>d[3, 1]
        centers[i, 2] = <np.float32_t>d[3, 2]
        spheres[i, 0] = <np.float32_t>d[3, 0]
        spheres[i, 1] = <np.float32_t>d[3, 1]
        spheres[i, 2] = <np.float32_t>d[3, 2]
        sx = sqrt(d[0, 0] * d[0, 0] + d[1, 0] * d[1, 0] + d[2, 0] * d[2, 0])
        sy = sqrt(d[0, 1] * d[0, 1] + d[1, 1] * d[1, 1] + d[2, 1] * d[2, 1])
        sz = sqrt(d[0, 2] * d[0, 2] + d[1, 2] * d[1, 2] + d[2, 2] * d[2, 2])
        ms = sx
        if sy > ms: ms = sy
        if sz > ms: ms = sz
        radii[i] = <np.float32_t>(ms * bounding_radii[i])
        spheres[i, 3] = radii[i]

    return spheres, centers, radii

def pack_instance_vbo(np.ndarray[np.float32_t, ndim=3] matrices):
    cdef int n = matrices.shape[0]
    cdef np.ndarray[np.float32_t, ndim=2] out = np.empty((n, 16), dtype=np.float32)
    cdef int i, j, k, flat_idx
    for i in range(n):
        flat_idx = 0
        for j in range(4):
            for k in range(4):
                out[i, flat_idx] = matrices[i, k, j]
                flat_idx += 1
    return out

def pack_instance_vbo_flat(np.ndarray[np.float32_t, ndim=3] matrices):
    cdef int n = matrices.shape[0]
    cdef np.ndarray[np.float32_t, ndim=1] out = np.empty(n * 16, dtype=np.float32)
    cdef int i, j, k, idx
    idx = 0
    for i in range(n):
        for j in range(4):
            for k in range(4):
                out[idx] = matrices[i, k, j]
                idx += 1
    return out

def compute_normal_matrices_batch(np.ndarray[DTYPE_t, ndim=3] model_matrices):  
    cdef int n = model_matrices.shape[0]
    cdef np.ndarray[np.float32_t, ndim=3] out = np.empty((n, 3, 3), dtype=np.float32)
    cdef int i, r, c
    cdef DTYPE_t norm_val
    cdef DTYPE_t m00, m01, m02, m10, m11, m12, m20, m21, m22

    for i in range(n):
        m00 = model_matrices[i, 0, 0]; m01 = model_matrices[i, 0, 1]; m02 = model_matrices[i, 0, 2]
        m10 = model_matrices[i, 1, 0]; m11 = model_matrices[i, 1, 1]; m12 = model_matrices[i, 1, 2]
        m20 = model_matrices[i, 2, 0]; m21 = model_matrices[i, 2, 1]; m22 = model_matrices[i, 2, 2]

        norm_val = sqrt(m00*m00 + m10*m10 + m20*m20)
        if norm_val < 1e-10: norm_val = 1e-10
        m00 /= norm_val; m10 /= norm_val; m20 /= norm_val

        norm_val = sqrt(m01*m01 + m11*m11 + m21*m21)
        if norm_val < 1e-10: norm_val = 1e-10
        m01 /= norm_val; m11 /= norm_val; m21 /= norm_val

        norm_val = sqrt(m02*m02 + m12*m12 + m22*m22)
        if norm_val < 1e-10: norm_val = 1e-10
        m02 /= norm_val; m12 /= norm_val; m22 /= norm_val

        out[i, 0, 0] = <np.float32_t>m00
        out[i, 0, 1] = <np.float32_t>m01
        out[i, 0, 2] = <np.float32_t>m02
        out[i, 1, 0] = <np.float32_t>m10
        out[i, 1, 1] = <np.float32_t>m11
        out[i, 1, 2] = <np.float32_t>m12
        out[i, 2, 0] = <np.float32_t>m20
        out[i, 2, 1] = <np.float32_t>m21
        out[i, 2, 2] = <np.float32_t>m22

    return out


def build_collider_gizmo_batch(np.ndarray[DTYPE_t, ndim=2] params):
    cdef int n = params.shape[0]
    if n == 0:
        return np.zeros((0, 20), dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=2] out = np.empty((n, 20), dtype=np.float32)
    cdef DTYPE_t[:, :] p = params
    cdef np.float32_t[:, :] o = out
    cdef int i
    cdef double px, py, pz, qx, qy, qz, qw, sx, sy, sz, cx, cy, cz, ex, ey, ez
    cdef double nq, inv
    cdef double xx, yy, zz, xy, xz, yz, wx, wy, wz
    cdef double r00, r01, r02, r10, r11, r12, r20, r21, r22
    cdef double b00, b01, b02, b10, b11, b12, b20, b21, b22
    cdef double a00, a01, a02, a10, a11, a12, a20, a21, a22
    cdef double t0, t1, t2
    with nogil:
        for i in range(n):
            px = p[i, 0]; py = p[i, 1]; pz = p[i, 2]
            qx = p[i, 3]; qy = p[i, 4]; qz = p[i, 5]; qw = p[i, 6]
            sx = p[i, 7]; sy = p[i, 8]; sz = p[i, 9]
            cx = p[i, 10]; cy = p[i, 11]; cz = p[i, 12]
            ex = p[i, 13]; ey = p[i, 14]; ez = p[i, 15]
            nq = sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
            if nq > 1e-10:
                inv = 1.0 / nq
                qx *= inv; qy *= inv; qz *= inv; qw *= inv
            xx = qx * qx; yy = qy * qy; zz = qz * qz
            xy = qx * qy; xz = qx * qz; yz = qy * qz
            wx = qw * qx; wy = qw * qy; wz = qw * qz
            r00 = 1.0 - 2.0 * (yy + zz); r01 = 2.0 * (xy - wz); r02 = 2.0 * (xz + wy)
            r10 = 2.0 * (xy + wz); r11 = 1.0 - 2.0 * (xx + zz); r12 = 2.0 * (yz - wx)
            r20 = 2.0 * (xz - wy); r21 = 2.0 * (yz + wx); r22 = 1.0 - 2.0 * (xx + yy)
            b00 = r00 * sx; b01 = r01 * sy; b02 = r02 * sz
            b10 = r10 * sx; b11 = r11 * sy; b12 = r12 * sz
            b20 = r20 * sx; b21 = r21 * sy; b22 = r22 * sz
            a00 = b00 * ex; a01 = b01 * ey; a02 = b02 * ez
            a10 = b10 * ex; a11 = b11 * ey; a12 = b12 * ez
            a20 = b20 * ex; a21 = b21 * ey; a22 = b22 * ez
            t0 = b00 * cx + b01 * cy + b02 * cz + px
            t1 = b10 * cx + b11 * cy + b12 * cz + py
            t2 = b20 * cx + b21 * cy + b22 * cz + pz
            o[i, 0] = <np.float32_t>a00; o[i, 1] = <np.float32_t>a10; o[i, 2] = <np.float32_t>a20; o[i, 3] = 0.0
            o[i, 4] = <np.float32_t>a01; o[i, 5] = <np.float32_t>a11; o[i, 6] = <np.float32_t>a21; o[i, 7] = 0.0
            o[i, 8] = <np.float32_t>a02; o[i, 9] = <np.float32_t>a12; o[i, 10] = <np.float32_t>a22; o[i, 11] = 0.0
            o[i, 12] = <np.float32_t>t0; o[i, 13] = <np.float32_t>t1; o[i, 14] = <np.float32_t>t2; o[i, 15] = 1.0
            o[i, 16] = 0.0; o[i, 17] = 1.0; o[i, 18] = 0.0; o[i, 19] = 0.6
    return out
