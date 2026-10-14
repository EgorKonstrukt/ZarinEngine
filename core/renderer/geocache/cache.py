# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import json
import numpy as np
from typing import Optional, Any, Callable
from core.engine.eng import Engine
from core.foundation.logger import Logger
from core.components.rendering.renderers.mesh_filter import MeshFilter
from core.components.rendering.renderers.mesh_renderer import MeshRenderer
from core.components.mesh_editor import ProBuilderMesh
from core.maths.math3d import Mat4, Vec3
from core.renderer.meshd import MeshData, read_shader
from core.components.rendering.terrain import Terrain
from core.components.environment.treep import Tree
from core.components.physics.terrain_collider import TerrainCollider
class CacheMixin:
    def get_or_create_mesh(self, name: str, file_path: str = "", scale: float = 1.0,
                           center_pivot: bool = False, flip_uvs: bool = False) -> Optional[MeshData]:
        if self._mesh_loader:
            return self._mesh_loader.get_or_create(name, file_path, scale, center_pivot, flip_uvs)
        return None
    def _resolve_import_meta_path(self, mesh_path: str) -> str:
        try:
            path_cache = self._import_meta_path_cache
        except Exception:
            path_cache = None
            try:
                self._import_meta_path_cache = path_cache = {}
            except Exception:
                pass
        eng = None
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
        except Exception:
            pass
        try:
            root = (eng.project_root if eng and getattr(eng, "project_root", None) else os.getcwd())
        except Exception:
            root = os.getcwd()
        if path_cache is not None:
            hit = path_cache.get(mesh_path)
            if isinstance(hit, tuple) and len(hit) == 2 and hit[0] == root:
                return hit[1]
        direct = mesh_path + ".import"
        if os.path.exists(direct):
            if path_cache is not None:
                try:
                    path_cache[mesh_path] = (root, direct)
                except Exception:
                    pass
            return direct
        base = os.path.basename(mesh_path)
        cand = os.path.join(root, mesh_path + ".import")
        if os.path.exists(cand):
            if path_cache is not None:
                try:
                    path_cache[mesh_path] = (root, cand)
                except Exception:
                    pass
            return cand
        for sub in ["", "assets/", "assets/models/", "models/"]:
            c1 = os.path.join(root, sub, mesh_path + ".import")
            if os.path.exists(c1):
                if path_cache is not None:
                    try:
                        path_cache[mesh_path] = (root, c1)
                    except Exception:
                        pass
                return c1
            c2 = os.path.join(root, sub, base + ".import")
            if os.path.exists(c2):
                if path_cache is not None:
                    try:
                        path_cache[mesh_path] = (root, c2)
                    except Exception:
                        pass
                return c2
        if path_cache is not None:
            try:
                path_cache[mesh_path] = (root, direct)
            except Exception:
                pass
        return direct
    def _sync_import_meta(self, mesh_path: str) -> tuple:
        if not mesh_path:
            return (1.0, False, True, 30.0, True, True)
        try:
            path_cache = self._import_meta_path_cache
        except Exception:
            path_cache = {}
            try:
                self._import_meta_path_cache = path_cache
            except Exception:
                pass
        import_cache = path_cache.get(mesh_path) if isinstance(path_cache, dict) else None
        if isinstance(import_cache, tuple) and len(import_cache) == 2:
            import_cache = import_cache[1]
        if import_cache is None or not isinstance(import_cache, str):
            import_cache = self._resolve_import_meta_path(mesh_path)
            if isinstance(import_cache, tuple) and len(import_cache) == 2:
                import_cache = import_cache[1]
        try:
            mtime = os.path.getmtime(import_cache) if os.path.exists(import_cache) else -1.0
        except OSError:
            mtime = -1.0
        cached_mtime = self._import_meta_mtime.get(mesh_path)
        if cached_mtime == mtime and mesh_path in self._import_meta_cache:
            return self._import_meta_cache[mesh_path]
        self._import_meta_mtime[mesh_path] = mtime
        if mtime >= 0.0:
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
        try:
            ents = scene.get_entities_with_component(MeshFilter)
        except Exception:
            return
        for ent in ents:
            try:
                mf = ent.get_component(MeshFilter)
            except Exception:
                continue
            if mf and getattr(mf, "mesh_path", ""):
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
                    bark_path = "core/shaders/materials/Tree.shader"
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
