# cython: boundscheck=False, wraparound=False, cdivision=True, nonecheck=False, initializedcheck=False, overflowcheck=False
# distutils: extra_compile_args = -O3 -ffast-math -march=native -fopenmp
# distutils: extra_link_args = -fopenmp
import numpy as np
cimport numpy as np
from libc.math cimport sqrt, fabs
from libc.stdlib cimport malloc, free
from cython.parallel import prange

DTYPE = np.float64
ctypedef np.float64_t DTYPE_t

cdef int _PAR_MIN = 1024


cdef inline void _extract_frustum_planes(
    const DTYPE_t[:, :] vp,
    DTYPE_t[:, :] planes_out,
) noexcept nogil:
    cdef int i
    cdef DTYPE_t inv_norm
    for i in range(6):
        if i == 0:
            planes_out[i, 0] = vp[3, 0] + vp[0, 0]
            planes_out[i, 1] = vp[3, 1] + vp[0, 1]
            planes_out[i, 2] = vp[3, 2] + vp[0, 2]
            planes_out[i, 3] = vp[3, 3] + vp[0, 3]
        elif i == 1:
            planes_out[i, 0] = vp[3, 0] - vp[0, 0]
            planes_out[i, 1] = vp[3, 1] - vp[0, 1]
            planes_out[i, 2] = vp[3, 2] - vp[0, 2]
            planes_out[i, 3] = vp[3, 3] - vp[0, 3]
        elif i == 2:
            planes_out[i, 0] = vp[3, 0] + vp[1, 0]
            planes_out[i, 1] = vp[3, 1] + vp[1, 1]
            planes_out[i, 2] = vp[3, 2] + vp[1, 2]
            planes_out[i, 3] = vp[3, 3] + vp[1, 3]
        elif i == 3:
            planes_out[i, 0] = vp[3, 0] - vp[1, 0]
            planes_out[i, 1] = vp[3, 1] - vp[1, 1]
            planes_out[i, 2] = vp[3, 2] - vp[1, 2]
            planes_out[i, 3] = vp[3, 3] - vp[1, 3]
        elif i == 4:
            planes_out[i, 0] = vp[3, 0] + vp[2, 0]
            planes_out[i, 1] = vp[3, 1] + vp[2, 1]
            planes_out[i, 2] = vp[3, 2] + vp[2, 2]
            planes_out[i, 3] = vp[3, 3] + vp[2, 3]
        else:
            planes_out[i, 0] = vp[3, 0] - vp[2, 0]
            planes_out[i, 1] = vp[3, 1] - vp[2, 1]
            planes_out[i, 2] = vp[3, 2] - vp[2, 2]
            planes_out[i, 3] = vp[3, 3] - vp[2, 3]
        inv_norm = 1.0 / sqrt(planes_out[i,0]*planes_out[i,0]
                            + planes_out[i,1]*planes_out[i,1]
                            + planes_out[i,2]*planes_out[i,2])
        planes_out[i, 0] *= inv_norm
        planes_out[i, 1] *= inv_norm
        planes_out[i, 2] *= inv_norm
        planes_out[i, 3] *= inv_norm


cdef np.ndarray[np.intp_t, ndim=1] _cull_core(DTYPE_t[:, ::1] centers,
                                                        DTYPE_t[::1] radii,
                                                        DTYPE_t[:, ::1] planes):
    cdef int n = centers.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.intp)
    if n >= _PAR_MIN:
        return cpu_frustum_cull_parallel(np.asarray(centers), np.asarray(radii),
                                         np.asarray(planes))
    cdef np.ndarray[np.intp_t, ndim=1] visible = np.empty(n, dtype=np.intp)
    cdef int count = 0, i, j
    cdef DTYPE_t dist
    cdef bint inside
    with nogil:
        for i in range(n):
            inside = True
            for j in range(6):
                dist = (planes[j, 0] * centers[i, 0] + planes[j, 1] * centers[i, 1]
                        + planes[j, 2] * centers[i, 2] + planes[j, 3])
                if dist < -radii[i]:
                    inside = False
                    break
            if inside:
                visible[count] = i
                count += 1
    return visible[:count]


def cpu_frustum_cull(
    np.ndarray[DTYPE_t, ndim=2] centers,
    np.ndarray[DTYPE_t, ndim=1] radii,
    np.ndarray[DTYPE_t, ndim=2] view_proj,
):
    cdef int n = centers.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.intp)

    cdef np.ndarray[DTYPE_t, ndim=2] planes = np.empty((6, 4), dtype=DTYPE)
    _extract_frustum_planes(view_proj, planes)

    if n >= 2048:
        try:
            return cpu_frustum_cull_parallel(centers, radii, planes)
        except Exception:
            pass

    cdef np.ndarray[np.intp_t, ndim=1] visible = np.empty(n, dtype=np.intp)
    cdef int count = 0, i, j
    cdef DTYPE_t dist
    cdef bint inside

    for i in range(n):
        inside = True
        for j in range(6):
            dist = (planes[j,0]*centers[i,0] + planes[j,1]*centers[i,1]
                    + planes[j,2]*centers[i,2] + planes[j,3])
            if dist < -radii[i]:
                inside = False
                break
        if inside:
            visible[count] = i
            count += 1

    return visible[:count]


def cull_fast(centers, radii, view_proj):
    cdef DTYPE_t[:, ::1] c_v = centers
    cdef DTYPE_t[::1] r_v = radii
    cdef DTYPE_t[:, ::1] vp_v = view_proj
    cdef np.ndarray[DTYPE_t, ndim=2] planes = np.empty((6, 4), dtype=DTYPE)
    _extract_frustum_planes(vp_v, planes)
    cdef DTYPE_t[:, ::1] p_v = planes
    return _cull_core(c_v, r_v, p_v)


def cpu_frustum_cull_parallel(
    np.ndarray[DTYPE_t, ndim=2] centers,
    np.ndarray[DTYPE_t, ndim=1] radii,
    np.ndarray[DTYPE_t, ndim=2] planes,
):
    cdef int n = centers.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.intp)
    cdef np.ndarray[np.uint8_t, ndim=1] mask = np.empty(n, dtype=np.uint8)
    cdef DTYPE_t[:, :] cview = centers
    cdef DTYPE_t[:] rview = radii
    cdef DTYPE_t[:, :] pview = planes
    cdef unsigned char[:] mview = mask
    cdef int i, j
    cdef DTYPE_t dist
    cdef bint inside
    with nogil:
        for i in prange(n, schedule='static'):
            inside = True
            for j in range(6):
                dist = (pview[j, 0] * cview[i, 0] + pview[j, 1] * cview[i, 1]
                        + pview[j, 2] * cview[i, 2] + pview[j, 3])
                if dist < -rview[i]:
                    inside = False
                    break
            mview[i] = 1 if inside else 0
    return np.where(mask)[0].astype(np.intp, copy=False)


def extract_frustum_planes_c(np.ndarray[DTYPE_t, ndim=2] view_proj):
    cdef np.ndarray[DTYPE_t, ndim=2] planes = np.empty((6, 4), dtype=DTYPE)
    _extract_frustum_planes(view_proj, planes)
    return planes


cdef inline bint _cull_one_nogil(double* p, float* pl, double mesh_radius) noexcept nogil:
    cdef double sx, sy, sz, ms, dist
    cdef int j
    sx = sqrt(p[0] * p[0] + p[4] * p[4] + p[8] * p[8])
    sy = sqrt(p[1] * p[1] + p[5] * p[5] + p[9] * p[9])
    sz = sqrt(p[2] * p[2] + p[6] * p[6] + p[10] * p[10])
    ms = sx
    if sy > ms:
        ms = sy
    if sz > ms:
        ms = sz
    ms = ms * mesh_radius
    for j in range(6):
        dist = pl[j * 4] * p[12] + pl[j * 4 + 1] * p[13] + pl[j * 4 + 2] * p[14] + pl[j * 4 + 3]
        if dist <= -ms:
            return False
    return True


def cull_group_instances(list group, np.ndarray[np.float32_t, ndim=2] planes,
                          double mesh_radius):
    cdef int n = len(group)
    if n == 0:
        return []
    cdef list visible = []
    cdef int i, j
    cdef double sx, sy, sz, ms, dist
    cdef bint inside
    cdef object item, wm
    cdef DTYPE_t[:, :] d
    if n >= _PAR_MIN:
        try:
            return _cgi_parallel(group, planes, mesh_radius, n)
        except Exception:
            pass
    for i in range(n):
        item = group[i]
        wm = item[6]
        d = wm._d
        sx = sqrt(d[0, 0] * d[0, 0] + d[1, 0] * d[1, 0] + d[2, 0] * d[2, 0])
        sy = sqrt(d[0, 1] * d[0, 1] + d[1, 1] * d[1, 1] + d[2, 1] * d[2, 1])
        sz = sqrt(d[0, 2] * d[0, 2] + d[1, 2] * d[1, 2] + d[2, 2] * d[2, 2])
        ms = sx
        if sy > ms:
            ms = sy
        if sz > ms:
            ms = sz
        inside = True
        for j in range(6):
            dist = (planes[j, 0] * d[3, 0] + planes[j, 1] * d[3, 1]
                    + planes[j, 2] * d[3, 2] + planes[j, 3])
            if dist <= -ms * mesh_radius:
                inside = False
                break
        if inside:
            visible.append(item)
    return visible


cdef list _cgi_parallel(list group, np.ndarray[np.float32_t, ndim=2] planes,
                        double mesh_radius, int n):
    cdef float pl[24]
    cdef int j
    for j in range(6):
        pl[j * 4] = planes[j, 0]
        pl[j * 4 + 1] = planes[j, 1]
        pl[j * 4 + 2] = planes[j, 2]
        pl[j * 4 + 3] = planes[j, 3]
    cdef double** ptrs = <double**>malloc(n * sizeof(double*))
    if ptrs == NULL:
        raise MemoryError()
    cdef unsigned char* mask = <unsigned char*>malloc(n * sizeof(unsigned char))
    if mask == NULL:
        free(ptrs)
        raise MemoryError()
    cdef int i
    cdef object item, wm
    cdef DTYPE_t[:, :] d
    try:
        for i in range(n):
            item = group[i]
            wm = item[6]
            d = wm._d
            if d.strides[0] != 32 or d.strides[1] != 8:
                raise ValueError()
            ptrs[i] = &d[0, 0]
    except Exception:
        free(ptrs)
        free(mask)
        raise
    cdef int k
    with nogil:
        for k in prange(n, schedule='static'):
            mask[k] = 1 if _cull_one_nogil(ptrs[k], pl, mesh_radius) else 0
    free(ptrs)
    cdef list visible = []
    try:
        for i in range(n):
            if mask[i]:
                visible.append(group[i])
    finally:
        free(mask)
    return visible
