# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import os
import numpy as np
import moderngl
from core.maths.math3d import Mat4, Vec3
from core.components.rendering.renderers.mesh_filter import MeshFilter
from core.components.rendering.renderers.mesh_renderer import MeshRenderer
from core.components.lighting.lightp import Light, LightType
from core.components.rendering.renderers.raytrace.component import _INST_STRIDE, _MAX_INSTANCES, _MAX_LIGHTS, _MAT_STRIDE, _MAX_ALBEDO_LAYERS
class RaytraceDenoiseMixin:
    def _build_mesh_geo(self, mesh, bvh) -> tuple:
        verts3 = mesh.vertices.reshape(-1, 3)
        idxs = mesh.indices.reshape(-1, 3)
        nv = verts3.shape[0]
        nt = idxs.shape[0]
        vert8 = np.zeros((nv, 8), dtype=np.float32)
        vert8[:, :3] = verts3
        norms = getattr(mesh, "normals", None)
        if norms is not None and norms.shape[0] == nv * 3:
            vert8[:, 3:6] = norms.reshape(-1, 3)
        else:
            f0 = verts3[0::3]
            f1 = verts3[1::3]
            f2 = verts3[2::3]
            e1 = f1 - f0
            e2 = f2 - f0
            face_norms = np.cross(e1, e2)
            fn_len = np.linalg.norm(face_norms, axis=1, keepdims=True)
            fn_len[fn_len == 0] = 1
            vert8[:, 3:6] = np.repeat(face_norms / fn_len, 3, axis=0)
        uvs = getattr(mesh, "uvs", None)
        if uvs is not None and len(uvs) >= nv * 2:
            vert8[:, 6:8] = uvs.reshape(-1, 2)[:nv]
        if bvh.tri_indices is not None and len(bvh.tri_indices) == nt:
            idx_local = idxs[bvh.tri_indices].astype(np.uint32, copy=False)
        else:
            idx_local = idxs.astype(np.uint32, copy=False)
        bvh_flat = np.asarray(bvh.flatten_for_gpu(), dtype=np.float32)
        nn = bvh_flat.shape[0]
        internal_mask = bvh_flat[:, 7] >= 0
        root = bvh.nodes[int(getattr(bvh, "_root_idx", len(bvh.nodes) - 1))]
        lbmin = np.asarray(root.bmin, dtype=np.float32)
        lbmax = np.asarray(root.bmax, dtype=np.float32)
        return vert8, idx_local, bvh_flat, internal_mask, nn, nt, nv, bvh, lbmin, lbmax
    def _rebuild_geometry_buffers(self, geo_entries: list) -> None:
        total_v = sum(g[6] for g in geo_entries)
        total_t = sum(g[5] for g in geo_entries)
        total_n = sum(g[4] for g in geo_entries)
        vert_np = np.empty((total_v, 8), dtype=np.float32)
        idx_np = np.empty((total_t, 3), dtype=np.uint32)
        bvh_np = np.empty((total_n, 8), dtype=np.float32)
        offsets = []
        vo, io, bo = 0, 0, 0
        for vert8, idx_local, bvh_flat, internal_mask, nn, nt, nv, _bvh, _lbmin, _lbmax in geo_entries:
            vert_np[vo:vo + nv] = vert8
            idx_np[io:io + nt] = idx_local + vo
            if bo > 0 and nn > 0 and internal_mask.any():
                blk = bvh_flat.copy()
                blk[internal_mask, 6] += bo
                blk[internal_mask, 7] += bo
            else:
                blk = bvh_flat
            bvh_np[bo:bo + nn] = blk
            offsets.append((vo, io, bo, nn, nt, int(getattr(_bvh, "_root_idx", nn - 1)) + bo))
            vo += nv
            io += nt
            bo += nn
        self._vert_np = vert_np
        self._idx_np = idx_np.reshape(-1)
        self._bvh_np = bvh_np.reshape(-1)
        self._geo_offsets = offsets
        self._geo_dirty = True
    def _collect_and_upload(self, ctx: moderngl.Context, scene, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3, renderer):
        from core.spatial.bvhv import get_mesh_bvh
        instances = []
        material_map = {}
        mf_list = scene.get_entities_with_component(MeshFilter)
        for ent in mf_list:
            if len(instances) >= _MAX_INSTANCES:
                break
            mr = ent.get_component(MeshRenderer)
            tr = ent.transform
            if not tr or not mr or not mr.enabled:
                continue
            mf = ent.get_component(MeshFilter)
            mesh_name = mf.mesh_name
            mesh_path = mf.mesh_path or ""
            scale, cp, fuvs = 1.0, False, False
            if mesh_path:
                meta = renderer._import_meta_cache.get(mesh_path) if hasattr(renderer, "_import_meta_cache") else None
                if meta is None:
                    meta = (1.0, False, False, 30.0, True, True)
                scale, cp, fuvs = meta[0], meta[1], meta[2]
            if not mesh_name:
                mesh_name = "cube" if not mesh_path else os.path.splitext(os.path.basename(mesh_path))[0]
            mesh = renderer.get_or_create_mesh(mesh_name, mesh_path, scale, cp, fuvs)
            if not mesh or mesh.vertices is None or len(mesh.vertices) < 3:
                continue
            bvh = get_mesh_bvh(mesh.vertices, mesh.indices)
            if not bvh or not bvh.nodes:
                try:
                    from core.spatial.bvhv import get_mesh_bvh_sync
                    bvh = get_mesh_bvh_sync(mesh.vertices, mesh.indices, timeout=0.5)
                except Exception:
                    bvh = None
            if not bvh or not bvh.nodes:
                continue
            mat_path = mr.get_material_path(0)
            if mat_path and mat_path not in material_map:
                material_map[mat_path] = len(material_map)
            instances.append((Mat4(tr.world_matrix._d), mat_path, mesh, bvh))
        if not instances:
            return False
        n_inst = len(instances)
        geo_entries = []
        sig_parts = []
        cache = self._mesh_geo_cache
        for _wm, _mat_path, mesh, bvh in instances:
            key = id(mesh)
            geo = cache.get(key)
            if geo is None or geo[7] is not bvh:
                geo = self._build_mesh_geo(mesh, bvh)
                cache[key] = geo
            geo_entries.append(geo)
            sig_parts.append(key)
        signature = tuple(sig_parts)
        if signature != self._geo_signature:
            self._rebuild_geometry_buffers(geo_entries)
            self._geo_signature = signature
            if len(cache) > max(64, n_inst * 4):
                active = set(sig_parts)
                for stale_key in [k for k in cache if k not in active]:
                    del cache[stale_key]
        offsets = self._geo_offsets
        n_mats = max(len(material_map), 1)
        mat_np = np.zeros((n_mats, _MAT_STRIDE), dtype=np.float32)
        mat_np[:, :3] = 0.8
        mat_np[:, 3] = 0.0
        mat_np[:, 4] = 0.5
        mat_np[:, 10] = 1.0
        mat_np[:, 11] = 1.0
        mat_np[:, 13] = 1.5
        mat_np[:, 9] = -1.0
        mmgr = getattr(renderer, "_materials", None)
        if mmgr:
            for mat_path, mi in material_map.items():
                mat = mmgr.load_material(mat_path)
                if mat:
                    props = mat.properties
                    bc = props.get("_BaseColor", None)
                    if bc is None:
                        bc = props.get("albedo_color", (0.8, 0.8, 0.8, 1.0))
                    mat_np[mi, 0] = float(bc[0])
                    mat_np[mi, 1] = float(bc[1])
                    mat_np[mi, 2] = float(bc[2])
                    mat_np[mi, 3] = float(props.get("_Metallic", 0.0))
                    mat_np[mi, 4] = float(props.get("_Smoothness", 0.5))
                    ec = props.get("_EmissionColor")
                    if ec is None:
                        ec = props.get("emission_color", (0, 0, 0, 0))
                    if ec is None:
                        ec = (0, 0, 0, 0)
                    mat_np[mi, 5] = float(ec[0])
                    mat_np[mi, 6] = float(ec[1])
                    mat_np[mi, 7] = float(ec[2])
                    mat_np[mi, 8] = float(props.get("_EmissionIntensity", 0.0))
                    mat_np[mi, 10] = float(props.get("_OcclusionStrength", 1.0))
                    mat_np[mi, 11] = float(bc[3]) if bc is not None and len(bc) > 3 else 1.0
                    mat_np[mi, 12] = float(props.get("_Transmission", 0.0))
                    mat_np[mi, 13] = float(props.get("_IOR", 1.5))
                    albedo_tex_path = props.get("_BaseMap")
                    if not albedo_tex_path:
                        albedo_tex_path = props.get("albedo_texture", "")
                    if albedo_tex_path and isinstance(albedo_tex_path, str):
                        layer = self._get_or_load_albedo_layer(albedo_tex_path, mmgr)
                        if layer >= 0:
                            mat_np[mi, 9] = float(layer)
        self._mat_np = mat_np
        wm_list = np.array([wm._d for wm, _, _, _ in instances])
        inv_wm_list = np.linalg.inv(wm_list)
        inst_np = np.empty((n_inst, _INST_STRIDE), dtype=np.float32)
        wm_f32 = np.array([Mat4(w).to_f32() for w in wm_list])
        inv_w_f32 = np.array([Mat4(w).to_f32() for w in inv_wm_list])
        inst_np[:, :16] = wm_f32.reshape(n_inst, 16)
        inst_np[:, 16:32] = inv_w_f32.reshape(n_inst, 16)
        _bvh_roots = np.array([float(offsets[i][5]) for i in range(n_inst)])
        _vert_offs = np.array([float(offsets[i][0]) for i in range(n_inst)])
        _idx_offs = np.array([float(offsets[i][1]) for i in range(n_inst)])
        _mat_idxs = np.array([float(material_map.get(instances[i][1], 0)) for i in range(n_inst)])
        _tri_counts = np.array([float(offsets[i][4]) for i in range(n_inst)])
        _node_counts = np.array([float(offsets[i][3]) for i in range(n_inst)])
        inst_np[:, 32] = _bvh_roots
        inst_np[:, 33] = _vert_offs
        inst_np[:, 34] = _idx_offs
        inst_np[:, 35] = _mat_idxs
        inst_np[:, 36] = _tri_counts
        inst_np[:, 37] = _node_counts
        lbmins = np.array([geo_entries[i][8] for i in range(n_inst)])
        lbmaxs = np.array([geo_entries[i][9] for i in range(n_inst)])
        centers = (lbmins + lbmaxs) * 0.5
        extents = (lbmaxs - lbmins) * 0.5
        r3 = wm_list[:, :3, :3]
        wcenters = np.einsum("ij,ikj->ik", centers, r3) + wm_list[:, 3, :3]
        wextents = np.einsum("ij,ikj->ik", extents, np.abs(r3))
        inst_np[:, 38:41] = wcenters - wextents
        inst_np[:, 41:44] = wcenters + wextents
        self._inst_np = inst_np
        lights_list = []
        lights_ents = scene.get_entities_with_component(Light)
        for ent in lights_ents:
            if len(lights_list) >= _MAX_LIGHTS:
                break
            if not ent.active:
                continue
            l = ent.get_component(Light)
            t = ent.transform
            if not l or not l.enabled or not t:
                continue
            lt = 0
            if l.light_type == LightType.DIRECTIONAL:
                lt = 0
            elif l.light_type == LightType.POINT:
                lt = 1
            elif l.light_type == LightType.SPOT:
                lt = 2
            fwd = t.forward
            c = l.color
            spot_cos = math.cos(math.radians(l.spot_angle))
            inner_cos = math.cos(math.radians(l.spot_inner_angle))
            _, eff_int = Light.shader_radiance(l, t)
            lights_list.append([
                float(lt), t.position.x, t.position.y, t.position.z,
                fwd.x, fwd.y, fwd.z,
                c[0], c[1], c[2],
                eff_int, l.range, spot_cos, inner_cos,
            ])
        n_lights = min(len(lights_list), _MAX_LIGHTS)
        light_np = np.zeros((max(n_lights, 1), 14), dtype=np.float32)
        if n_lights > 0:
            light_np[:n_lights] = np.array(lights_list[:n_lights], dtype=np.float32)
        self._light_np = light_np
        if self._geo_dirty:
            self._upload_or_realloc(ctx, "_bvh_buf", self._bvh_np)
            self._upload_or_realloc(ctx, "_vert_buf", self._vert_np)
            self._upload_or_realloc(ctx, "_idx_buf", self._idx_np)
            self._geo_dirty = False
        self._upload_or_realloc(ctx, "_mat_buf", self._mat_np)
        self._upload_or_realloc(ctx, "_inst_buf", self._inst_np)
        self._upload_or_realloc(ctx, "_light_buf", self._light_np)
        return True
    def _get_or_load_albedo_layer(self, tex_path: str, mmgr) -> int:
        if tex_path in self._albedo_tex_map:
            return self._albedo_tex_map[tex_path]
        if self._albedo_count >= _MAX_ALBEDO_LAYERS:
            return -1
        abs_path = mmgr._resolve_tex_path(tex_path) if mmgr else tex_path
        if not abs_path or not os.path.exists(abs_path):
            self._albedo_tex_map[tex_path] = -1
            return -1
        try:
            from PIL import Image
            img = Image.open(abs_path).convert("RGBA")
        except Exception:
            self._albedo_tex_map[tex_path] = -1
            return -1
        w, h = img.size
        aw, ah = self._albedo_array_size
        if w > aw or h > ah:
            scale = min(aw / w, ah / h)
            w = max(1, int(w * scale))
            h = max(1, int(h * scale))
            img = img.resize((w, h), Image.LANCZOS)
        data = img.tobytes()
        x_off = (aw - w) // 2
        y_off = (ah - h) // 2
        try:
            layer = self._albedo_count
            self._albedo_array_tex.write(data, viewport=(x_off, y_off, layer, w, h, 1))
            self._albedo_count += 1
            self._albedo_tex_map[tex_path] = layer
            return layer
        except Exception:
            return -1
