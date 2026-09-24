# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Voxelized object rendering."""

from __future__ import annotations
import os
import numpy as np
import moderngl
from core.foundation.logger import Logger


class VoxelPassMixin:
    """Voxelized object rendering."""


    _VOX_MAX_DIM = 128


    _VOX_MAX_INSTANCES = 2200000


    _VOXEL_INST_VERT = """#version 330 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_uv;
layout(location = 3) in vec4 i_cell;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform float u_vox_size;
uniform vec3 u_vox_scale;

out vec3 v_world_pos;
out vec3 v_normal;
out vec2 v_uv;
out vec3 v_view_pos;
out vec3 v_local_pos;

    void main() {
        vec3 s = max(vec3(0.01), u_vox_scale);
        vec3 h = u_vox_size * 0.9 * s;
    vec3 center = i_cell.xyz;
    vec3 local = center + vec3(in_position.x * h.x, in_position.y * h.y, in_position.z * h.z);
    vec4 world = u_model * vec4(local, 1.0);
    v_world_pos = world.xyz;
    v_local_pos = local;
    v_normal = in_normal;
    v_uv = in_uv;
    vec4 view_pos = u_view * world;
    v_view_pos = view_pos.xyz;
    gl_Position = u_proj * view_pos;
    if (i_cell.w < 0.0) {
        gl_Position = vec4(0.0, 0.0, 0.0, 0.0);
    }
}
"""


    _VOXEL_INST_FRAG = """#version 330 core
in vec3 v_world_pos;
in vec3 v_normal;
in vec2 v_uv;
in vec3 v_view_pos;
in vec3 v_local_pos;

uniform vec3 u_camera_pos;
uniform vec3 u_vox_color;
uniform float u_vox_amount;
uniform float u_vox_emission;
uniform float u_vox_rim;

out vec4 frag_color;

    void main() {
        vec3 N = normalize(v_normal);
        vec3 V = normalize(u_camera_pos - v_world_pos);
        vec3 L1 = normalize(vec3(0.5, 0.9, 0.4));
        vec3 L2 = normalize(vec3(-0.4, -0.3, -0.7));
        float ndl = max(dot(N, L1), 0.0) * 0.8 + max(dot(N, L2), 0.0) * 0.2;
        float fres = pow(1.0 - max(dot(N, V), 0.0), max(0.1, u_vox_rim));
        float edge = smoothstep(0.0, 0.06, v_uv.x) * smoothstep(0.0, 0.06, v_uv.y)
                   * smoothstep(0.0, 0.06, 1.0 - v_uv.x) * smoothstep(0.0, 0.06, 1.0 - v_uv.y);
        vec3 base = u_vox_color * (0.22 + 0.78 * ndl) * mix(0.82, 1.0, edge);
        float glow = u_vox_amount * (u_vox_emission + fres * u_vox_emission * 1.5);
        vec3 col = base + u_vox_color * glow;
        frag_color = vec4(col, 1.0);
    }
"""


    def _build_voxel_cube(self):
        s = 0.5
        faces = [
            ((0.0, 0.0, 1.0), [(-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)]),
            ((0.0, 0.0, -1.0), [(s, -s, -s), (-s, -s, -s), (-s, s, -s), (s, s, -s)]),
            ((1.0, 0.0, 0.0), [(s, -s, s), (s, -s, -s), (s, s, -s), (s, s, s)]),
            ((-1.0, 0.0, 0.0), [(-s, -s, -s), (-s, -s, s), (-s, s, s), (-s, s, -s)]),
            ((0.0, 1.0, 0.0), [(-s, s, s), (s, s, s), (s, s, -s), (-s, s, -s)]),
            ((0.0, -1.0, 0.0), [(-s, -s, -s), (s, -s, -s), (s, -s, s), (-s, -s, s)]),
        ]
        uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        data = []
        idx = []
        base = 0
        for nrm, corners in faces:
            for i, c in enumerate(corners):
                data.append([c[0], c[1], c[2], nrm[0], nrm[1], nrm[2], uvs[i][0], uvs[i][1]])
            idx.extend([base, base + 1, base + 2, base, base + 2, base + 3])
            base += 4
        return np.array(data, dtype=np.float32), np.array(idx, dtype=np.uint32)


    def _init_voxel_instancing(self):
        try:
            self._vox_prog = self._ctx.program(
                vertex_shader=self._VOXEL_INST_VERT,
                fragment_shader=self._VOXEL_INST_FRAG,
            )
            cube_data, cube_idx = self._build_voxel_cube()
            self._vox_cube_vbo = self._ctx.buffer(cube_data.tobytes())
            self._vox_cube_ibo = self._ctx.buffer(cube_idx.astype(np.uint32).tobytes())
            self._vox_inst_vbo = self._ctx.buffer(reserve=1024 * 16)
            self._vox_inst_cap = 1024
            self._vox_vao = self._ctx.vertex_array(
                self._vox_prog,
                [
                    (self._vox_cube_vbo, "3f 3f 2f", "in_position", "in_normal", "in_uv"),
                    (self._vox_inst_vbo, "4f /i", "i_cell"),
                ],
                self._vox_cube_ibo,
            )
            self._vox_compute = None
            comp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shaders", "legacy", "voxelize.comp")
            if os.path.exists(comp_path):
                try:
                    with open(comp_path) as f:
                        src = f.read()
                    self._vox_compute = self._ctx.compute_shader(src)
                except Exception as e:
                    Logger.error(f"Voxel compute shader failed: {e}", e)
                    self._vox_compute = None
        except Exception as e:
            Logger.error(f"Voxel instancing init failed: {e}", e)
            self._vox_prog = None
            self._vox_vao = None
            self._vox_compute = None


    def _vox_ensure_res(self, fx, nverts, nidx, total):
        res = getattr(fx, "_vox_res", None)
        need_inst = min(total, self._VOX_MAX_INSTANCES)
        if res is None or res["nverts"] != nverts or res["nidx"] != nidx \
                or res["grid_cap"] < total or res["inst_cap"] < need_inst:
            if res is not None:
                for k in ("pos", "idx", "grid", "inst", "vao"):
                    obj = res.get(k)
                    if obj is not None:
                        try:
                            obj.release()
                        except Exception:
                            pass
            pos = self._ctx.buffer(reserve=max(1, nverts) * 16)
            idxf = self._ctx.buffer(reserve=max(1, nidx) * 4)
            grid_cap = max(total, res["grid_cap"] if res else 0)
            inst_cap = max(need_inst, res["inst_cap"] if res else 0)
            grid = self._ctx.buffer(reserve=max(1, grid_cap) * 4)
            inst = self._ctx.buffer(reserve=max(1, inst_cap) * 16)
            vao = self._ctx.vertex_array(
                self._vox_prog,
                [
                    (self._vox_cube_vbo, "3f 3f 2f", "in_position", "in_normal", "in_uv"),
                    (inst, "4f /i", "i_cell"),
                ],
                self._vox_cube_ibo,
            )
            res = {
                "pos": pos, "idx": idxf, "grid": grid, "inst": inst,
                "vao": vao, "nverts": nverts, "nidx": nidx,
                "grid_cap": grid_cap, "inst_cap": inst_cap,
                "pos_key": None, "idx_key": None,
            }
            fx._vox_res = res
        return res


    def _render_voxel_instances(self, entry, fx, view_f32, proj_f32, cam_pos):
        mesh = entry[2]
        wm = entry[4]
        verts = getattr(mesh, "vertices", None)
        idx = getattr(mesh, "indices", None)
        if verts is None or len(verts) < 9 or self._vox_prog is None:
            return
        size = float(fx.voxel_size)
        if size <= 0.0:
            return
        world_grid = bool(fx.world_grid)
        model = np.asarray(wm._d, dtype=np.float32).T
        ctx = self._ctx
        prev_cull = ctx.cull_face
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        ctx.cull_face = 'back'
        ctx.disable(moderngl.BLEND)
        try:
            if self._vox_compute is not None:
                self._render_voxel_gpu(entry, fx, verts, idx, model, size, world_grid, view_f32, proj_f32, cam_pos)
            else:
                self._render_voxel_cpu(entry, fx, verts, idx, model, size, world_grid, view_f32, proj_f32, cam_pos)
        finally:
            ctx.enable(moderngl.DEPTH_TEST)
            if prev_cull:
                ctx.cull_face = prev_cull
            else:
                ctx.disable(moderngl.CULL_FACE)
            ctx.disable(moderngl.BLEND)


    def _set_vox_uniforms(self, prog, fx, wm, world_grid, size, view_f32, proj_f32, cam_pos):
        model = np.asarray(wm.to_f32(), dtype=np.float32).reshape(4, 4)
        prog["u_view"].write(view_f32.tobytes())
        prog["u_proj"].write(proj_f32.tobytes())
        prog["u_camera_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        if world_grid:
            prog["u_model"].write(np.eye(4, dtype=np.float32).tobytes())
        else:
            prog["u_model"].write(model.tobytes())
        prog["u_vox_size"].value = size
        sc = fx.scale
        if hasattr(sc, "x"):
            sc = np.array([sc.x, sc.y, sc.z], dtype=np.float32)
        else:
            sc = np.asarray(sc, dtype=np.float32)
            if sc.shape[0] < 3:
                sc = np.full(3, float(sc[0]) if sc.shape[0] else 1.0, dtype=np.float32)
        prog["u_vox_scale"].write(sc[:3].tobytes())
        col = np.array(fx.color, dtype=np.float32)
        if col.shape[0] < 3:
            col = np.array([0.4, 1.0, 0.6], dtype=np.float32)
        prog["u_vox_color"].write(col[:3].tobytes())
        prog["u_vox_amount"].value = float(fx.amount)
        prog["u_vox_emission"].value = float(fx.emission)
        prog["u_vox_rim"].value = float(fx.rim)


    def _render_voxel_cpu(self, entry, fx, verts, idx, model, size, world_grid, view_f32, proj_f32, cam_pos):
        wm = entry[4]
        grid_min = None
        if world_grid:
            V = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
            ones = np.ones((V.shape[0], 1), dtype=np.float32)
            S = (model @ np.concatenate([V, ones], axis=1).T).T[:, :3]
            grid_min = np.floor(S.min(axis=0) / size) * size
        cells = fx.get_voxel_instances(verts, idx, model, size, world_grid, float(fx.jitter), grid_min)
        n = cells.shape[0]
        if n == 0 or self._vox_vao is None:
            return
        if n > self._vox_inst_cap:
            self._vox_inst_vbo.orphan(n * 16)
            self._vox_inst_cap = n
        self._vox_inst_vbo.write(cells[:n].tobytes())
        self._set_vox_uniforms(self._vox_prog, fx, wm, world_grid, size, view_f32, proj_f32, cam_pos)
        self._vox_vao.render(moderngl.TRIANGLES, instances=n)


    def _render_voxel_gpu(self, entry, fx, verts, idx, model, size, world_grid, view_f32, proj_f32, cam_pos):
        wm = entry[4]
        V = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
        nverts = V.shape[0]
        if idx is not None and len(idx) >= 3:
            nt = (len(idx) // 3) * 3
            I = np.asarray(idx[:nt], dtype=np.uint32)
        else:
            I = np.arange(nverts, dtype=np.uint32)
        ntris = I.shape[0] // 3
        if ntris == 0:
            return

        if world_grid:
            m = model
            ones = np.ones((nverts, 1), dtype=np.float32)
            S = (m @ np.concatenate([V, ones], axis=1).T).T[:, :3]
            smin = np.floor(S.min(axis=0) / size) * size
            smax = np.floor(S.max(axis=0) / size) * size + size
        else:
            S = V
            smin = S.min(axis=0)
            smax = S.max(axis=0)
        extent = np.maximum(smax - smin, 1e-4)
        cell = float(size)
        dims = np.ceil(extent / cell).astype(np.int64)
        over = np.maximum(dims - self._VOX_MAX_DIM, 0)
        if np.any(over > 0):
            factor = float(np.max(dims)) / self._VOX_MAX_DIM
            cell = cell * factor
            dims = np.ceil(extent / cell).astype(np.int64)
        dims = np.clip(dims, 1, self._VOX_MAX_DIM).astype(np.int32)
        total = int(dims[0]) * int(dims[1]) * int(dims[2])
        if total <= 0:
            return

        res = self._vox_ensure_res(fx, nverts, I.shape[0], total)

        pkey = (id(verts), nverts)
        if res["pos_key"] != pkey:
            P = np.zeros((nverts, 4), dtype=np.float32)
            P[:, :3] = V
            res["pos"].write(P.tobytes())
            res["pos_key"] = pkey
        ikey = (id(idx) if idx is not None else -1, I.shape[0])
        if res["idx_key"] != ikey:
            res["idx"].write(I.tobytes())
            res["idx_key"] = ikey

        res["grid"].clear()

        cs = self._vox_compute
        cs["u_pass"].value = 0
        cs["u_num_tris"].value = ntris
        cs["u_total_cells"].value = total
        cs["u_grid_min"].write(smin.astype(np.float32).tobytes())
        cs["u_cell_size"].value = cell
        cs["u_grid_dims"].write(dims.astype(np.int32).tobytes())
        cs["u_jitter"].value = 0.0
        cs["u_world_grid"].value = 1 if world_grid else 0
        cs["u_model"].write(wm.to_f32().tobytes())
        res["pos"].bind_to_storage_buffer(0)
        res["idx"].bind_to_storage_buffer(1)
        res["grid"].bind_to_storage_buffer(2)
        res["inst"].bind_to_storage_buffer(3)
        cs.run((ntris + 63) // 64, 1, 1)
        self._ctx.memory_barrier(moderngl.SHADER_STORAGE_BARRIER_BIT)

        cs["u_pass"].value = 1
        cs["u_jitter"].value = float(fx.jitter)
        cs.run((total + 63) // 64, 1, 1)
        try:
            bar = moderngl.SHADER_STORAGE_BARRIER_BIT | moderngl.VERTEX_ATTRIB_ARRAY_BARRIER_BIT
        except AttributeError:
            bar = moderngl.SHADER_STORAGE_BARRIER_BIT
        self._ctx.memory_barrier(bar)

        if total > res["inst_cap"]:
            return
        self._set_vox_uniforms(self._vox_prog, fx, wm, world_grid, cell, view_f32, proj_f32, cam_pos)
        res["vao"].render(moderngl.TRIANGLES, instances=total)
