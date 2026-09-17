# cython: boundscheck=False, wraparound=False, cdivision=True, nonecheck=False
# cython: language_level=3
from libc.stdint cimport uint32_t, uintptr_t
from libc.string cimport memcpy
import numpy as np
cimport numpy as np

DTYPE_F32 = np.float32
DTYPE_U32 = np.uint32
ctypedef np.float32_t F32_t
ctypedef np.uint32_t U32_t


def extract_faces(uintptr_t faces_ptr, int nf):
    cdef:
        int j, idx = 0
        uint32_t n_idx
        uintptr_t ptr_val
        uint32_t *idx_ptr
        char *face_base = <char *>faces_ptr
        int face_size = 16
        np.ndarray[U32_t, ndim=1] out = np.empty(nf * 3, dtype=np.uint32)

    with nogil:
        for j in range(nf):
            n_idx = (<uint32_t *>(face_base + j * face_size))[0]
            ptr_val = (<uintptr_t *>(face_base + j * face_size + 8))[0]
            if n_idx >= 3 and ptr_val != 0:
                idx_ptr = <uint32_t *>ptr_val
                out[idx] = idx_ptr[0]
                out[idx + 1] = idx_ptr[1]
                out[idx + 2] = idx_ptr[2]
            idx += 3
    return out


def smooth_normals(np.ndarray[F32_t, ndim=2] verts,
                   np.ndarray[U32_t, ndim=1] indices):
    cdef:
        int n_verts = verts.shape[0]
        int n_tris = indices.shape[0] // 3
        int i, i0, i1, i2
        float f0x, f0y, f0z, f1x, f1y, f1z
        float nx, ny, nz, len
        np.ndarray[F32_t, ndim=2] normals = np.zeros((n_verts, 3), dtype=np.float32)

    with nogil:
        for i in range(n_tris):
            i0 = indices[i * 3]
            i1 = indices[i * 3 + 1]
            i2 = indices[i * 3 + 2]
            f0x = verts[i1, 0] - verts[i0, 0]
            f0y = verts[i1, 1] - verts[i0, 1]
            f0z = verts[i1, 2] - verts[i0, 2]
            f1x = verts[i2, 0] - verts[i0, 0]
            f1y = verts[i2, 1] - verts[i0, 1]
            f1z = verts[i2, 2] - verts[i0, 2]
            nx = f0y * f1z - f0z * f1y
            ny = f0z * f1x - f0x * f1z
            nz = f0x * f1y - f0y * f1x
            len = (nx * nx + ny * ny + nz * nz)
            if len > 1e-20:
                len = 1.0 / (len ** 0.5)
                nx *= len
                ny *= len
                nz *= len
            normals[i0, 0] += nx
            normals[i0, 1] += ny
            normals[i0, 2] += nz
            normals[i1, 0] += nx
            normals[i1, 1] += ny
            normals[i1, 2] += nz
            normals[i2, 0] += nx
            normals[i2, 1] += ny
            normals[i2, 2] += nz

    cdef np.ndarray[F32_t, ndim=2] out = np.empty_like(normals)
    cdef float nl
    with nogil:
        for i in range(n_verts):
            nl = normals[i, 0] * normals[i, 0] + normals[i, 1] * normals[i, 1] + normals[i, 2] * normals[i, 2]
            if nl > 1e-20:
                nl = 1.0 / (nl ** 0.5)
                out[i, 0] = normals[i, 0] * nl
                out[i, 1] = normals[i, 1] * nl
                out[i, 2] = normals[i, 2] * nl
            else:
                out[i, 0] = 0.0
                out[i, 1] = 1.0
                out[i, 2] = 0.0
    return out


def apply_zup_to_yup(np.ndarray[F32_t, ndim=1] data):
    cdef:
        int n = data.shape[0] // 3
        int i
        float x, y, z
        np.ndarray[F32_t, ndim=1] out = np.empty_like(data)

    with nogil:
        for i in range(n):
            x = data[i * 3]
            y = data[i * 3 + 1]
            z = data[i * 3 + 2]
            out[i * 3] = x
            out[i * 3 + 1] = z
            out[i * 3 + 2] = -y
    return out


cdef inline bint _is_space(unsigned char c) noexcept nogil:
    return c == 32 or c == 9 or c == 13 or c == 12 or c == 11


cdef inline int _parse_float_token(const unsigned char *p, Py_ssize_t n,
                                   float *out) noexcept nogil:
    cdef Py_ssize_t i = 0
    cdef double int_part = 0.0
    cdef double frac_part = 0.0
    cdef double frac_div = 1.0
    cdef double expo = 0.0
    cdef int exp_sign = 1
    cdef int sign = 1
    cdef int digits = 0
    cdef unsigned char c
    if n <= 0:
        return -1
    if p[0] == 43:
        i = 1
    elif p[0] == 45:
        sign = -1
        i = 1
    while i < n:
        c = p[i]
        if 48 <= c <= 57:
            int_part = int_part * 10.0 + (c - 48)
            digits += 1
            i += 1
        else:
            break
    if i < n and p[i] == 46:
        i += 1
        while i < n:
            c = p[i]
            if 48 <= c <= 57:
                frac_part = frac_part * 10.0 + (c - 48)
                frac_div *= 10.0
                digits += 1
                i += 1
            else:
                break
    if digits == 0:
        if i + 2 < n and (p[i] | 32) == 105 and (p[i + 1] | 32) == 110 and (p[i + 2] | 32) == 102:
            i += 3
            if i + 5 < n and (p[i] | 32) == 105 and (p[i + 1] | 32) == 110 and (p[i + 2] | 32) == 105 and (p[i + 3] | 32) == 116 and (p[i + 4] | 32) == 121:
                i += 5
            if i != n:
                return -1
            out[0] = <float>(1e300 * 1e300) * sign
            return 0
        if i + 2 < n and (p[i] | 32) == 110 and (p[i + 1] | 32) == 97 and (p[i + 2] | 32) == 110:
            i += 3
            if i != n:
                return -1
            out[0] = <float>((1e300 * 1e300) - (1e300 * 1e300))
            return 0
        return -1
    if i < n and ((p[i] | 32) == 101):
        i += 1
        if i < n and p[i] == 43:
            i += 1
        elif i < n and p[i] == 45:
            exp_sign = -1
            i += 1
        if i >= n:
            return -1
        while i < n:
            c = p[i]
            if 48 <= c <= 57:
                expo = expo * 10.0 + (c - 48)
                i += 1
            else:
                return -1
    if i != n:
        return -1
    cdef double v = sign * (int_part + frac_part / frac_div)
    if expo != 0.0:
        if exp_sign > 0:
            while expo > 0:
                v *= 10.0
                expo -= 1.0
        else:
            while expo > 0:
                v *= 0.1
                expo -= 1.0
    out[0] = <float>v
    return 0


cdef inline int _parse_int_token(const unsigned char *p, Py_ssize_t n,
                                 long long *out) noexcept nogil:
    cdef Py_ssize_t i = 0
    cdef int sign = 1
    cdef unsigned long long acc = 0
    cdef unsigned long long acc_lim = 922337203685477580
    cdef unsigned long long pos_lim = 9223372036854775807
    cdef unsigned char c
    if n <= 0:
        return -1
    if p[0] == 43:
        i = 1
    elif p[0] == 45:
        sign = -1
        i = 1
    if i >= n:
        return -1
    while i < n:
        c = p[i]
        if 48 <= c <= 57:
            if acc >= acc_lim:
                return -2
            acc = acc * 10 + (c - 48)
            i += 1
        else:
            return -1
    if sign > 0:
        if acc > pos_lim:
            return -2
        out[0] = <long long>acc
    else:
        if acc > pos_lim + 1:
            return -2
        if acc == pos_lim + 1:
            out[0] = (<long long>-9223372036854775807) - 1
        else:
            out[0] = -<long long>acc
    return 0


def parse_obj_chunk(bytes chunk):
    cdef:
        const unsigned char *buf = chunk
        Py_ssize_t n = len(chunk)
        Py_ssize_t i = 0
        Py_ssize_t ls, le, p0, p1, q
        Py_ssize_t nv = 0
        Py_ssize_t ntt = 0
        Py_ssize_t nvn = 0
        Py_ssize_t nref = 0
        unsigned char c0, c1
        float fval
        long long ival
        int rc
        np.ndarray[F32_t, ndim=1] varr, tarr, narr
        np.ndarray[np.int64_t, ndim=1] fp, ft, fn
        Py_ssize_t vi, ti, ni, fi
        Py_ssize_t t0, t1
        Py_ssize_t slash0, slash1, slash2, c2end
        int in_tok

    with nogil:
        i = 0
        while i < n:
            while i < n and (buf[i] == 10 or _is_space(buf[i])):
                if buf[i] == 10:
                    i += 1
                    break
                i += 1
            if i >= n:
                break
            ls = i
            while i < n and buf[i] != 10:
                i += 1
            le = i
            if i < n:
                i += 1
            while ls < le and _is_space(buf[ls]):
                ls += 1
            while le > ls and _is_space(buf[le - 1]):
                le -= 1
            if ls >= le or buf[ls] == 35:
                continue
            c0 = buf[ls]
            if c0 == 118:
                if ls + 1 < le and not _is_space(buf[ls + 1]) and buf[ls + 1] != 116 and buf[ls + 1] != 110:
                    continue
                if ls + 1 < le and buf[ls + 1] == 116:
                    if ls + 2 < le and not _is_space(buf[ls + 2]):
                        continue
                    ntt += 1
                elif ls + 1 < le and buf[ls + 1] == 110:
                    if ls + 2 < le and not _is_space(buf[ls + 2]):
                        continue
                    nvn += 1
                else:
                    nv += 1
            elif c0 == 102:
                if ls + 1 < le and not _is_space(buf[ls + 1]):
                    continue
                q = ls + 1
                in_tok = 0
                while q < le:
                    if _is_space(buf[q]):
                        in_tok = 0
                    elif not in_tok:
                        in_tok = 1
                        nref += 1
                    q += 1
    varr = np.empty(nv * 3, dtype=np.float32)
    tarr = np.empty(ntt * 2, dtype=np.float32)
    narr = np.empty(nvn * 3, dtype=np.float32)
    fp = np.empty(nref, dtype=np.int64)
    ft = np.empty(nref, dtype=np.int64)
    fn = np.empty(nref, dtype=np.int64)
    cdef:
        F32_t *vp = <F32_t *>np.PyArray_DATA(varr)
        F32_t *tp = <F32_t *>np.PyArray_DATA(tarr)
        F32_t *nrp = <F32_t *>np.PyArray_DATA(narr)
        np.int64_t *fpp = <np.int64_t *>np.PyArray_DATA(fp)
        np.int64_t *ftp = <np.int64_t *>np.PyArray_DATA(ft)
        np.int64_t *fnp = <np.int64_t *>np.PyArray_DATA(fn)
    with nogil:
        vi = 0
        ti = 0
        ni = 0
        fi = 0
        i = 0
        while i < n:
            while i < n and (buf[i] == 10 or _is_space(buf[i])):
                if buf[i] == 10:
                    i += 1
                    break
                i += 1
            if i >= n:
                break
            ls = i
            while i < n and buf[i] != 10:
                i += 1
            le = i
            if i < n:
                i += 1
            while ls < le and _is_space(buf[ls]):
                ls += 1
            while le > ls and _is_space(buf[le - 1]):
                le -= 1
            if ls >= le or buf[ls] == 35:
                continue
            c0 = buf[ls]
            if c0 == 118:
                if ls + 1 < le and not _is_space(buf[ls + 1]) and buf[ls + 1] != 116 and buf[ls + 1] != 110:
                    continue
                if ls + 1 < le and buf[ls + 1] == 116:
                    if ls + 2 < le and not _is_space(buf[ls + 2]):
                        continue
                    p0 = ls + 2
                    for q in range(2):
                        while p0 < le and _is_space(buf[p0]):
                            p0 += 1
                        p1 = p0
                        while p1 < le and not _is_space(buf[p1]):
                            p1 += 1
                        if p0 >= p1:
                            with gil:
                                raise ValueError("bad vt")
                        rc = _parse_float_token(buf + p0, p1 - p0, &fval)
                        if rc != 0:
                            with gil:
                                raise ValueError("bad vt")
                        tp[ti] = fval
                        ti += 1
                        p0 = p1
                elif ls + 1 < le and buf[ls + 1] == 110:
                    if ls + 2 < le and not _is_space(buf[ls + 2]):
                        continue
                    p0 = ls + 2
                    for q in range(3):
                        while p0 < le and _is_space(buf[p0]):
                            p0 += 1
                        p1 = p0
                        while p1 < le and not _is_space(buf[p1]):
                            p1 += 1
                        if p0 >= p1:
                            with gil:
                                raise ValueError("bad vn")
                        rc = _parse_float_token(buf + p0, p1 - p0, &fval)
                        if rc != 0:
                            with gil:
                                raise ValueError("bad vn")
                        nrp[ni] = fval
                        ni += 1
                        p0 = p1
                else:
                    p0 = ls + 1
                    for q in range(3):
                        while p0 < le and _is_space(buf[p0]):
                            p0 += 1
                        p1 = p0
                        while p1 < le and not _is_space(buf[p1]):
                            p1 += 1
                        if p0 >= p1:
                            with gil:
                                raise ValueError("bad v")
                        rc = _parse_float_token(buf + p0, p1 - p0, &fval)
                        if rc != 0:
                            with gil:
                                raise ValueError("bad v")
                        vp[vi] = fval
                        vi += 1
                        p0 = p1
            elif c0 == 102:
                if ls + 1 < le and not _is_space(buf[ls + 1]):
                    continue
                p0 = ls + 1
                while p0 < le:
                    while p0 < le and _is_space(buf[p0]):
                        p0 += 1
                    if p0 >= le:
                        break
                    p1 = p0
                    while p1 < le and not _is_space(buf[p1]):
                        p1 += 1
                    t0 = p0
                    t1 = p1
                    slash0 = -1
                    slash1 = -1
                    slash2 = -1
                    q = t0
                    while q < t1:
                        if buf[q] == 47:
                            if slash0 < 0:
                                slash0 = q
                            elif slash1 < 0:
                                slash1 = q
                            else:
                                slash2 = q
                                break
                        q += 1
                    if slash0 < 0:
                        rc = _parse_int_token(buf + t0, t1 - t0, &ival)
                        if rc == -2:
                            with gil:
                                raise OverflowError("face int overflow")
                        if rc != 0:
                            with gil:
                                raise ValueError("bad f")
                        fpp[fi] = ival - 1
                        ftp[fi] = -1
                        fnp[fi] = -1
                        fi += 1
                    else:
                        rc = _parse_int_token(buf + t0, slash0 - t0, &ival)
                        if rc == -2:
                            with gil:
                                raise OverflowError("face int overflow")
                        if rc != 0:
                            with gil:
                                raise ValueError("bad f")
                        fpp[fi] = ival - 1
                        c2end = slash2 if slash2 >= 0 else t1
                        if slash1 < 0:
                            if slash0 + 1 < t1:
                                rc = _parse_int_token(buf + slash0 + 1, t1 - slash0 - 1, &ival)
                                if rc == -2:
                                    with gil:
                                        raise OverflowError("face int overflow")
                                if rc != 0:
                                    with gil:
                                        raise ValueError("bad f")
                                ftp[fi] = ival - 1
                            else:
                                ftp[fi] = -1
                            fnp[fi] = -1
                        else:
                            if slash0 + 1 < slash1:
                                rc = _parse_int_token(buf + slash0 + 1, slash1 - slash0 - 1, &ival)
                                if rc == -2:
                                    with gil:
                                        raise OverflowError("face int overflow")
                                if rc != 0:
                                    with gil:
                                        raise ValueError("bad f")
                                ftp[fi] = ival - 1
                            else:
                                ftp[fi] = -1
                            if slash1 + 1 < c2end:
                                rc = _parse_int_token(buf + slash1 + 1, c2end - slash1 - 1, &ival)
                                if rc == -2:
                                    with gil:
                                        raise OverflowError("face int overflow")
                                if rc != 0:
                                    with gil:
                                        raise ValueError("bad f")
                                fnp[fi] = ival - 1
                            else:
                                fnp[fi] = -1
                        fi += 1
                    p0 = p1
    return (np.asarray(varr[:vi]), np.asarray(tarr[:ti]), np.asarray(narr[:ni]),
            np.asarray(fp[:fi]), np.asarray(ft[:fi]), np.asarray(fn[:fi]))
