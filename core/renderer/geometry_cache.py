# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Mesh, morph and soft-body caches."""

from __future__ import annotations
import os
import json
import numpy as np
from typing import Optional, Any, Callable
from core.engine.engine import Engine
from core.foundation.logger import Logger
from core.components.rendering.renderers.mesh_filter import MeshFilter
from core.components.rendering.renderers.mesh_renderer import MeshRenderer
from core.components.rendering.deform.blendshapes import BlendShapes
from core.components.mesh_editor import ProBuilderMesh
from core.maths.math3d import Mat4, Vec3
from core.renderer.mesh_data import MeshData, read_shader
from core.components.rendering.terrain import Terrain
from core.components.environment.tree import Tree
from core.components.physics.terrain_collider import TerrainCollider


class GeometryCacheMixin:
    """Mesh, morph and soft-body caches."""


    def get_or_create_mesh(self, name: str, file_path: str = "", scale: float = 1.0,
                           center_pivot: bool = False, flip_uvs: bool = False) -> Optional[MeshData]:
        if self._mesh_loader:
            return self._mesh_loader.get_or_create(name, file_path, scale, center_pivot, flip_uvs)
        return None


    def _resolve_import_meta_path(self, mesh_path: str) -> str:
        direct = mesh_path + ".import"
        if os.path.exists(direct):
            return direct
        eng = None
        try:
            from core.engine.engine import Engine
            eng = Engine.instance()
        except Exception:
            pass
        root = (eng.project_root if eng and getattr(eng, "project_root", None) else os.getcwd())
        base = os.path.basename(mesh_path)
        candidates = [os.path.join(root, mesh_path + ".import")]
        for sub in ["", "assets/", "assets/models/", "models/"]:
            candidates.append(os.path.join(root, sub, mesh_path + ".import"))
            candidates.append(os.path.join(root, sub, base + ".import"))
        for c in candidates:
            if os.path.exists(c):
                return c
        return direct


    def _sync_import_meta(self, mesh_path: str) -> tuple:
        if not mesh_path:
            return (1.0, False, True, 30.0, True, True)
        import_cache = self._resolve_import_meta_path(mesh_path)
        try:
            mtime = os.path.getmtime(import_cache) if os.path.exists(import_cache) else -1.0
        except OSError:
            mtime = -1.0
        cached_mtime = self._import_meta_mtime.get(mesh_path)
        if cached_mtime == mtime and mesh_path in self._import_meta_cache:
            return self._import_meta_cache[mesh_path]
        self._import_meta_mtime[mesh_path] = mtime
        if os.path.exists(import_cache):
            try:
                with open(import_cache) as _f:
                    _s = json.load(_f)
                meta = (
                    float(_s.get("scale", 1.0)),
                    bool(_s.get("center_pivot", False)),
                    bool(_s.get("flip_uvs", True)),
                    float(_s.get("smooth_angle", 30.0)),
                    bool(_s.get("gen_normals", True)),
                    bool(_s.get("gen_uvs", True)),
                )
            except Exception:
                meta = (1.0, False, True, 30.0, True, True)
        else:
            meta = (1.0, False, True, 30.0, True, True)
        old = self._import_meta_cache.get(mesh_path)
        self._import_meta_cache[mesh_path] = meta
        if old is not None and old != meta and self._mesh_loader is not None:
            prefix = mesh_path + "|"
            for k in [k for k in list(self._mesh_loader._meshes.keys()) if k.startswith(prefix)]:
                self._mesh_loader._meshes.pop(k, None)
            try:
                self._mesh_loader.cancel_prefix(prefix)
            except Exception:
                pass
        return meta


    def _preload_import_meta(self, scene):
        paths = set()
        for ent in scene.get_entities_with_component(MeshFilter):
            mf = ent.get_component(MeshFilter)
            if mf and mf.mesh_path:
                paths.add(mf.mesh_path)
        for mesh_path in paths:
            self._sync_import_meta(mesh_path)


    def _soft_upload_if_dirty(self, ov) -> None:
        try:
            if ov is None or not getattr(ov, "_soft_dirty", False):
                return
            if self._ctx is None or self._default_prog is None:
                return
            ov.build_gl(self._ctx, self._default_prog)
            if self._outline_prog:
                try:
                    ov.build_outline_vao(self._ctx, self._outline_prog)
                except Exception:
                    pass
            ov._soft_dirty = False
        except Exception:
            pass


    def _refresh_soft_snapshot_meshes(self, scene=None, snap=None) -> None:
        try:
            if scene is not None:
                try:
                    if not scene._component_indices.get("SoftBody"):
                        return
                except Exception:
                    pass
            if snap is None:
                snap = self._snap_cache
            if snap is None:
                return
            renderable = getattr(snap, "renderable", None)
            if not renderable:
                return
            from core.components.physics.soft_body import SoftBody
            for entry in renderable:
                try:
                    ent = entry[0]
                    if ent is None:
                        continue
                    try:
                        soft = ent.get_component(SoftBody)
                    except Exception:
                        soft = None
                    if soft is None or not getattr(soft, "enabled", True):
                        continue
                    ov = getattr(soft, "_render_mesh", None)
                    if ov is None:
                        continue
                    try:
                        needs = bool(getattr(soft, "_soft_needs_rebuild", False))
                    except Exception:
                        needs = False
                    if needs:
                        try:
                            src = getattr(ov, "_soft_src", None)
                        except Exception:
                            src = None
                        if src is not None:
                            try:
                                rebuilt = self._soft_override_mesh(ent, src)
                            except Exception:
                                rebuilt = None
                            if rebuilt is not None:
                                ov = rebuilt
                    if entry[2] is not ov:
                        entry[2] = ov
                    self._soft_upload_if_dirty(ov)
                except Exception:
                    continue
        except Exception:
            pass


    def _release_morph_cache(self, ent_id=None):
        try:
            if ent_id is None:
                for clone in self._morph_cache.values():
                    try:
                        clone.release()
                    except Exception:
                        pass
                self._morph_cache.clear()
                self._morph_sig.clear()
                return
            clone = self._morph_cache.pop(ent_id, None)
            self._morph_sig.pop(ent_id, None)
            if clone is not None:
                try:
                    clone.release()
                except Exception:
                    pass
        except Exception:
            pass


    def _morphed_mesh(self, ent, mesh):
        try:
            bs = ent.get_component(BlendShapes)
        except Exception:
            return mesh
        if bs is None or not getattr(bs, "enabled", True):
            return mesh
        if mesh is None or not getattr(mesh, "has_blendshapes", False):
            return mesh
        try:
            if len(getattr(bs, "shapes", [])) != int(getattr(mesh, "blendshape_count", 0)):
                bs.sync_with_mesh(mesh)
            else:
                want = list(getattr(mesh, "blendshape_names", []) or [])
                got = [str(s.get("name", "")) for s in bs.shapes]
                if want != got:
                    bs.sync_with_mesh(mesh)
        except Exception:
            pass
        try:
            w = bs.weights_vector(mesh)
        except Exception:
            return mesh
        if not any(v != 0.0 for v in w):
            self._release_morph_cache(getattr(ent, "id", None))
            return mesh
        try:
            sig = (id(mesh), int(getattr(mesh, "_gpu_version", 0)), tuple(float(v) for v in w))
        except Exception:
            return mesh
        eid = getattr(ent, "id", None)
        if eid is not None:
            if self._morph_sig.get(eid) == sig:
                cached = self._morph_cache.get(eid)
                if cached is not None:
                    return cached
        try:
            clone = mesh.make_morphed_clone(w, self._ctx, self._default_prog, self._outline_prog)
        except Exception:
            return mesh
        if eid is not None:
            old = self._morph_cache.get(eid)
            if old is not None and old is not clone:
                try:
                    old.release()
                except Exception:
                    pass
            self._morph_cache[eid] = clone
            self._morph_sig[eid] = sig
        return clone


    def _soft_override_mesh(self, ent, mesh):
        from core.components.physics.soft_body import SoftBody
        soft = ent.get_component(SoftBody)
        if soft is None or not getattr(soft, "enabled", True):
            return None
        try:
            n_full = int(len(mesh.vertices) // 3)
        except Exception:
            return None
        if n_full <= 0:
            return None
        sv = getattr(soft, "_soft_verts", None)
        try:
            sim_rest = np.ascontiguousarray(sv, dtype=np.float32).reshape(-1, 3) if sv is not None else None
        except Exception:
            sim_rest = None
        use_skin = sim_rest is not None and len(sim_rest) >= 3
        tr = ent.transform
        try:
            sc = tr.local_scale if tr is not None else None
            sxs, sys, szs = (float(sc.x), float(sc.y), float(sc.z)) if sc is not None else (1.0, 1.0, 1.0)
        except Exception:
            sxs, sys, szs = 1.0, 1.0, 1.0
        if use_skin and (abs(sxs) < 1e-6 or abs(sys) < 1e-6 or abs(szs) < 1e-6):
            use_skin = False
        if not use_skin and sim_rest is not None and len(sim_rest) >= 3:
            try:
                soft._soft_use_skin = False
            except Exception:
                pass
            n_c = int(len(sim_rest))
            ov = getattr(soft, "_render_mesh", None)
            if ov is None or getattr(ov, "_soft_src", None) is not mesh or getattr(ov, "_soft_n", -1) != n_c:
                try:
                    from core.foundation.logger import Logger
                    Logger.info(f"[SoftBody] override['{getattr(ent,'name',ent)}'] building ov n={n_c} (prev={getattr(ov,'_soft_n','-')})")
                except Exception:
                    pass
                from core.renderer.mesh_data import MeshData
                if ov is None:
                    ov = MeshData()
                try:
                    ov.vertices = np.ascontiguousarray(sim_rest, dtype=np.float32).copy().reshape(-1)
                    ov.normals = np.zeros_like(ov.vertices)
                    ov.uvs = np.zeros((n_c * 2,), dtype=np.float32)
                    ov.sub_mesh_ranges = []
                    ov.sub_mesh_names = []
                    sf = getattr(soft, "_soft_faces", None)
                    if sf is not None and len(sf) >= 3:
                        ov.indices = np.ascontiguousarray(sf, dtype=np.uint32).copy()
                    else:
                        ov.indices = np.ascontiguousarray(mesh.indices, dtype=np.uint32).copy()
                    try:
                        flat = np.asarray(ov.indices).reshape(-1)
                        ov._soft_faces = flat.astype(np.int64) if flat.size % 3 == 0 else None
                    except Exception:
                        ov._soft_faces = None
                    ov.compute_aabb()
                    ov.build_gl(self._ctx, self._default_prog)
                    if self._outline_prog:
                        try:
                            ov.build_outline_vao(self._ctx, self._outline_prog)
                        except Exception:
                            pass
                except Exception:
                    return None
                ov._soft_src = mesh
                ov._soft_n = n_c
                ov._soft_ctx = self._ctx
                ov._soft_prog = self._default_prog
                ov._soft_dirty = False
                try:
                    ov._soft_version = int(getattr(ov, "_soft_version", 0) or 0) + 1
                except Exception:
                    pass
                try:
                    soft._soft_needs_rebuild = False
                except Exception:
                    pass
                soft._render_mesh = ov
            else:
                self._soft_upload_if_dirty(ov)
            return ov
        skin_ok = False
        if use_skin:
            try:
                e_idx = getattr(soft, "_soft_skin_idx", None)
                e_w = getattr(soft, "_soft_skin_w", None)
                e_nsim = int(getattr(soft, "_soft_skin_nsim", -1))
                e_nfull = int(getattr(soft, "_soft_skin_nfull", -1))
                e_sc = tuple(getattr(soft, "_soft_skin_scale", ()))
                skin_ok = (
                    e_idx is not None and e_w is not None
                    and getattr(e_idx, "shape", (0, 0)) == (n_full, 4)
                    and getattr(e_w, "shape", (0, 0)) == (n_full, 4)
                    and e_nsim == len(sim_rest) and e_nfull == n_full
                    and getattr(soft, "_soft_skin_mesh", None) is mesh
                    and len(e_sc) == 3
                    and abs(e_sc[0] - sxs) < 1e-9 and abs(e_sc[1] - sys) < 1e-9 and abs(e_sc[2] - szs) < 1e-9
                )
            except Exception:
                skin_ok = False
        ov = getattr(soft, "_render_mesh", None)
        try:
            need_rebuild = bool(getattr(soft, "_soft_needs_rebuild", False))
        except Exception:
            need_rebuild = False
        if ov is None or getattr(ov, "_soft_src", None) is not mesh or getattr(ov, "_soft_n", -1) != n_full or need_rebuild or (use_skin and not skin_ok):
            try:
                from core.foundation.logger import Logger
                Logger.info(f"[SoftBody] override['{getattr(ent,'name',ent)}'] building ov n={n_full} (prev={getattr(ov,'_soft_n','-')})")
            except Exception:
                pass
            from core.renderer.mesh_data import MeshData
            if ov is None:
                ov = MeshData()
            try:
                rrest = np.ascontiguousarray(mesh.vertices, dtype=np.float32).reshape(-1, 3)
                if use_skin and not skin_ok:
                    try:
                        s0 = sim_rest / np.array([sxs, sys, szs], dtype=np.float32)
                        s0 = np.ascontiguousarray(s0, dtype=np.float32)
                        e_idx, e_w = self._soft_build_skin(rrest, s0, 4)
                        soft._soft_skin_idx = e_idx
                        soft._soft_skin_w = e_w
                        soft._soft_skin_nsim = int(len(sim_rest))
                        soft._soft_skin_nfull = int(n_full)
                        soft._soft_skin_scale = (sxs, sys, szs)
                        soft._soft_skin_mesh = mesh
                        soft._soft_use_skin = True
                        skin_ok = True
                    except Exception:
                        skin_ok = False
                        try:
                            soft._soft_use_skin = False
                        except Exception:
                            pass
                if use_skin and skin_ok:
                    try:
                        latest = np.ascontiguousarray(getattr(soft, "_soft_latest_local", None), dtype=np.float32).reshape(-1, 3)
                    except Exception:
                        latest = None
                    try:
                        src = latest if latest is not None and len(latest) == len(sim_rest) else sim_rest / np.array([sxs, sys, szs], dtype=np.float32)
                    except Exception:
                        src = sim_rest
                    ov.vertices = np.ascontiguousarray(self._soft_apply_skin(src, soft._soft_skin_idx, soft._soft_skin_w).reshape(-1))
                    ov.normals = np.zeros_like(ov.vertices)
                else:
                    ov.vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float32).copy()
                    if getattr(mesh, "normals", None) is not None and len(mesh.normals) == len(mesh.vertices):
                        ov.normals = np.ascontiguousarray(mesh.normals, dtype=np.float32).copy()
                    else:
                        ov.normals = np.zeros_like(ov.vertices)
                if getattr(mesh, "uvs", None) is not None and len(mesh.uvs) > 0:
                    try:
                        ov.uvs = np.ascontiguousarray(mesh.uvs, dtype=np.float32).copy()
                    except Exception:
                        ov.uvs = np.zeros((n_full * 2,), dtype=np.float32)
                else:
                    ov.uvs = np.zeros((n_full * 2,), dtype=np.float32)
                ov.indices = np.ascontiguousarray(mesh.indices, dtype=np.uint32).copy()
                ov.sub_mesh_ranges = list(getattr(mesh, "sub_mesh_ranges", []))
                ov.sub_mesh_names = list(getattr(mesh, "sub_mesh_names", []))
                try:
                    flat = np.asarray(ov.indices).reshape(-1)
                    ov._soft_faces = flat.astype(np.int64) if flat.size % 3 == 0 else None
                except Exception:
                    ov._soft_faces = None
                ov.compute_aabb()
                ov.build_gl(self._ctx, self._default_prog)
                if self._outline_prog:
                    try:
                        ov.build_outline_vao(self._ctx, self._outline_prog)
                    except Exception:
                        pass
            except Exception:
                return None
            ov._soft_src = mesh
            ov._soft_n = n_full
            ov._soft_ctx = self._ctx
            ov._soft_prog = self._default_prog
            ov._soft_dirty = False
            try:
                ov._soft_version = int(getattr(ov, "_soft_version", 0) or 0) + 1
            except Exception:
                pass
            try:
                soft._soft_needs_rebuild = False
            except Exception:
                pass
            soft._render_mesh = ov
        else:
            self._soft_upload_if_dirty(ov)
        return ov


    def _soft_build_skin(self, render_rest, sim_rest, k):
        import numpy as np
        R = np.ascontiguousarray(render_rest, dtype=np.float32)
        S = np.ascontiguousarray(sim_rest, dtype=np.float32)
        n_full = int(len(R))
        n_sim = int(len(S))
        kk = max(1, min(int(k), n_sim))
        idx = np.empty((n_full, kk), dtype=np.int32)
        w = np.empty((n_full, kk), dtype=np.float32)
        s2 = np.ascontiguousarray((S * S).sum(axis=1, dtype=np.float32).reshape(1, -1))
        try:
            step = max(512, min(4096, (64 * 1024 * 1024) // max(1, n_sim * 4)))
        except Exception:
            step = 1024
        for a in range(0, n_full, step):
            b = min(n_full, a + step)
            Rs = np.ascontiguousarray(R[a:b])
            r2 = np.ascontiguousarray((Rs * Rs).sum(axis=1, dtype=np.float32).reshape(-1, 1))
            d2 = r2 + s2 - 2.0 * (Rs @ S.T)
            np.maximum(d2, 0.0, out=d2)
            part = np.argpartition(d2, kth=kk - 1, axis=1)[:, :kk]
            rows = np.arange(b - a)[:, None]
            dk = d2[rows, part]
            order = np.argsort(dk, axis=1, kind="stable")
            sel = part[rows, order]
            ds = dk[rows, order].astype(np.float64)
            inv = 1.0 / (ds + 1e-8)
            inv /= inv.sum(axis=1, keepdims=True)
            idx[a:b] = sel.astype(np.int32)
            w[a:b] = inv.astype(np.float32)
        return idx, w


    def _soft_apply_skin(self, sim_pos, idx, w):
        import numpy as np
        L = np.ascontiguousarray(sim_pos, dtype=np.float32)
        ii = np.asarray(idx, dtype=np.int64)
        ww = np.ascontiguousarray(w, dtype=np.float32)
        out = np.zeros((len(ii), 3), dtype=np.float32)
        for c in range(ii.shape[1]):
            out += ww[:, c:c + 1] * L[ii[:, c]]
        return out


    def _lookup_outline_mesh(self, mf) -> Optional[MeshData]:
        if not self._mesh_loader:
            return None
        meshes = self._mesh_loader._meshes
        mesh_name = mf.mesh_name or "cube"
        mesh_path = mf.mesh_path or ""
        mesh = meshes.get(mesh_name)
        if mesh:
            return mesh
        if mesh_path:
            _meta = self._sync_import_meta(mesh_path)
            cache_key = f"{mesh_path}|s={_meta[0]}|cp={_meta[1]}|fu={_meta[2]}"
            mesh = meshes.get(cache_key)
            if mesh:
                return mesh
        return meshes.get("cube")


    @property
    def _meshes(self):
        if self._mesh_loader:
            return self._mesh_loader._meshes
        return {}


    def _sync_probuilder_meshes(self, scene):
        mesh_loader = self._mesh_loader
        if not mesh_loader:
            return
        if not hasattr(self, '_pb_scale_cache'):
            self._pb_scale_cache = {}
        for ent in scene.get_entities_with_component(ProBuilderMesh):
            if not ent.active:
                continue
            pb = ent.get_component(ProBuilderMesh)
            if not pb or not pb.enabled or pb.vertex_count == 0:
                continue
            tr = ent.transform
            if tr:
                s = tr.local_scale
                scale_key = (s.x, s.y, s.z)
                prev_scale = self._pb_scale_cache.get(ent.id)
                if prev_scale != scale_key:
                    self._pb_scale_cache[ent.id] = scale_key
                    pb.rebuild_uvs(world_scale=np.array([s.x, s.y, s.z], dtype=np.float32))
                    pb._gpu_dirty = True
            if not pb._gpu_dirty:
                continue
            mf = ent.get_component(MeshFilter)
            if not mf:
                mf = MeshFilter()
                ent.add_component(mf)
            mesh_name = f"ProBuilder_{ent.id[:6]}"
            mf.mesh_name = mesh_name
            gpu_mesh = pb.to_gpu_mesh()
            gpu_mesh.build_gl(self._ctx, self._default_prog)
            if self._outline_prog:
                gpu_mesh.build_outline_vao(self._ctx, self._outline_prog)
            mr = ent.get_component(MeshRenderer)
            if not mr:
                mr = MeshRenderer()
                ent.add_component(mr)
            cache_key = f"{mesh_name}|s=1.0|cp=False|fu=False"
            mesh_loader._meshes[cache_key] = gpu_mesh
            mesh_loader.bump_generation()
            pb._gpu_dirty = False
        active_ids = {ent.id for ent in scene.get_entities_with_component(ProBuilderMesh) if ent.active}
        stale = [k for k in self._pb_scale_cache if k not in active_ids]
        for k in stale:
            del self._pb_scale_cache[k]


    def _sync_terrain_meshes(self, scene):
        mesh_loader = self._mesh_loader
        if not mesh_loader:
            return
        for ent in scene.get_entities_with_component(Terrain):
            if not ent.active:
                continue
            terrain = ent.get_component(Terrain)
            if not terrain or not terrain.enabled:
                continue
            if terrain.auto_regenerate and (not terrain._generated or terrain._mesh_data is None):
                terrain.generate()
            if terrain._gpu_dirty and terrain._mesh_data is not None:
                mf = ent.get_component(MeshFilter)
                if not mf:
                    mf = MeshFilter()
                    ent.add_component(mf)
                mesh_name = f"Terrain_{ent.id[:6]}"
                mf.mesh_name = mesh_name
                mesh = MeshData()
                mesh.vertices = terrain._mesh_data["vertices"].astype(np.float32)
                mesh.normals = terrain._mesh_data["normals"].astype(np.float32)
                mesh.uvs = terrain._mesh_data["uvs"].astype(np.float32)
                mesh.indices = terrain._mesh_data["indices"].astype(np.uint32)
                mesh.compute_aabb()
                mesh.build_gl(self._ctx, self._default_prog)
                if self._outline_prog:
                    mesh.build_outline_vao(self._ctx, self._outline_prog)
                mr = ent.get_component(MeshRenderer)
                if not mr:
                    mr = MeshRenderer()
                    ent.add_component(mr)
                if terrain.material_path:
                    mr.materials[0]["path"] = terrain.material_path
                cache_key = f"{mesh_name}|s=1.0|cp=False|fu=False"
                mesh_loader._meshes[cache_key] = mesh
                mesh_loader.bump_generation()
                terrain._gpu_dirty = False
                tc = ent.get_component(TerrainCollider)
                if tc is not None and terrain._heightfield is not None:
                    tc.set_height_data(terrain._heightfield)
                    tc.resolution = terrain._heightfield.shape[0]
                    tc.size = Vec3(terrain.world_size, terrain.settings.get("heightScale"), terrain.world_size)


    def _sync_tree_meshes(self, scene):
        mesh_loader = self._mesh_loader
        if not mesh_loader:
            return
        for ent in scene.get_entities_with_component(Tree):
            if not ent.active:
                continue
            tree = ent.get_component(Tree)
            if not tree or not tree.enabled:
                continue
            if tree.auto_regenerate and tree.needs_regenerate():
                tree.generate()
            if tree._gpu_dirty and tree._mesh_data is not None:
                mf = ent.get_component(MeshFilter)
                if not mf:
                    mf = MeshFilter()
                    ent.add_component(mf)
                mesh_name = f"Tree_{ent.id[:6]}"
                mf.mesh_name = mesh_name
                mesh = tree._mesh_data
                mesh.build_gl(self._ctx, self._default_prog)
                if self._outline_prog:
                    mesh.build_outline_vao(self._ctx, self._outline_prog)
                mr = ent.get_component(MeshRenderer)
                if not mr:
                    mr = MeshRenderer()
                    ent.add_component(mr)
                bark_path = tree.material_path
                if not bark_path:
                    bark_path = "core/shaders/Tree.shader"
                mr.materials[0]["path"] = bark_path
                if mesh.sub_mesh_ranges:
                    leaf_path = tree.leaf_material_path
                    if not leaf_path:
                        leaf_path = bark_path
                    if len(mr.materials) < 2:
                        mr.materials.append({"path": leaf_path})
                    else:
                        mr.materials[1]["path"] = leaf_path
                for mi in mr.materials:
                    if self._materials and mi.get("path"):
                        mat = self._materials.load_material(mi["path"])
                        if mat:
                            mat.properties["double_sided"] = True
                            mat.properties["_DoubleSided"] = 1
                cache_key = f"{mesh_name}|s=1.0|cp=False|fu=False"
                mesh_loader._meshes[cache_key] = mesh
                mesh_loader.bump_generation()
                tree._gpu_dirty = False
