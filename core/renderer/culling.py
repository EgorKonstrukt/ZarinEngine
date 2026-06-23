from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional

_CULL_COMPUTE_SRC = """
#version 460 core
layout(local_size_x = 256, local_size_y = 1, local_size_z = 1) in;

layout(std430, binding = 0) readonly buffer BoundingSpheres {
    vec4 spheres[];
};

layout(std430, binding = 1) buffer VisibleIndices {
    uint indices[];
};

layout(std430, binding = 2) buffer VisibleCount {
    uint count;
};

uniform vec4 u_planes[6];
uniform uint u_num_objects;

void main() {
    uint id = gl_GlobalInvocationID.x;
    if (id >= u_num_objects) return;

    vec4 sphere = spheres[id];
    for (int i = 0; i < 6; i++) {
        float d = dot(u_planes[i].xyz, sphere.xyz) + u_planes[i].w;
        if (d < -sphere.w) return;
    }

    uint idx = atomicAdd(count, 1u);
    indices[idx] = id;
}
"""


def extract_frustum_planes(view_proj: np.ndarray) -> np.ndarray:
    vp = view_proj.astype(np.float32)
    planes = np.zeros((6, 4), dtype=np.float32)
    planes[0] = vp[3] + vp[0]
    planes[1] = vp[3] - vp[0]
    planes[2] = vp[3] + vp[1]
    planes[3] = vp[3] - vp[1]
    planes[4] = vp[3] + vp[2]
    planes[5] = vp[3] - vp[2]
    for i in range(6):
        n = np.linalg.norm(planes[i, :3])
        if n > 1e-10:
            planes[i] /= n
    return planes


class GpuFrustumCuller:
    def __init__(self, ctx: moderngl.Context, max_objects: int = 16384):
        self._ctx = ctx
        self._max_objects = max_objects

        self._prog = ctx.compute_shader(_CULL_COMPUTE_SRC)

        self._sphere_buf = ctx.buffer(reserve=max_objects * 16)
        self._index_buf = ctx.buffer(reserve=max_objects * 4)
        self._count_buf = ctx.buffer(reserve=4)

        self._sphere_buf.bind_to_storage_buffer(0)
        self._index_buf.bind_to_storage_buffer(1)
        self._count_buf.bind_to_storage_buffer(2)

        self._zero = np.zeros(1, dtype=np.uint32)
        self._visible_indices: Optional[np.ndarray] = None

    def cull(self, centers: np.ndarray, radii: np.ndarray,
             view_proj: np.ndarray) -> np.ndarray:
        n = len(centers)
        if n == 0:
            return np.zeros(0, dtype=np.uint32)

        spheres = np.zeros((n, 4), dtype=np.float32)
        spheres[:, :3] = centers.astype(np.float32).reshape(-1, 3)
        spheres[:, 3] = radii.astype(np.float32)
        data = spheres.tobytes()

        if len(data) > self._sphere_buf.size:
            self._sphere_buf.orphan(len(data))
        self._sphere_buf.write(data)

        self._count_buf.write(self._zero.tobytes())

        planes = extract_frustum_planes(view_proj)
        self._prog['u_planes'].write(planes.tobytes())
        self._prog['u_num_objects'] = n

        groups = (n + 255) // 256
        self._prog.run(group_x=groups)

        count_bytes = self._count_buf.read(4)
        vis_count = int(np.frombuffer(count_bytes, dtype=np.uint32)[0])

        if vis_count == 0:
            return np.zeros(0, dtype=np.uint32)

        indices_bytes = self._index_buf.read(vis_count * 4)
        return np.frombuffer(indices_bytes, dtype=np.uint32).copy()

    def release(self):
        self._prog.release()
        self._sphere_buf.release()
        self._index_buf.release()
        self._count_buf.release()
