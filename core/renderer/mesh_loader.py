# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations

import os
import threading
from typing import Optional

import numpy as np

from core.engine.engine import Engine
from core.foundation.logger import Logger
from core.foundation.progress import (
    notify_error,
    task_complete,
    task_set_detail,
    task_set_title,
    task_start,
    task_update,
)
from core.renderer.mesh_data import MeshData
from core.renderer.meshes import (
    make_cube_mesh,
    make_plane_mesh,
    make_quad_mesh,
    make_sphere_mesh,
)

_MESH_UPLOAD_BUDGET_BYTES = 6 * 1024 * 1024
_MESH_MAX_COMPLETIONS_PER_FRAME = 4
_MESH_UPLOAD_CHUNK_BYTES = 2 * 1024 * 1024


def _display_name(path: str) -> str:
    return os.path.basename(path.replace("\\", "/")) or path


def _fmt_count(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{int(n)}"


def _mesh_load_task(cache_key: str) -> str:
    return f"mesh_load:{cache_key}"

_ERROR_MESH_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "3d_models", "ERRORText.fbx"))


def _deferred_call(cb):
    try:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, cb)
    except ImportError:
        threading.Thread(target=cb, daemon=True).start()


class MeshLoader:
    def __init__(self, ctx, default_prog, outline_prog=None):
        self._ctx = ctx
        self._default_prog = default_prog
        self._outline_prog = outline_prog
        self._meshes: dict[str, MeshData] = {}
        self._pending_async_loads: int = 0
        self._pending_cache_keys: set = set()
        self._async_lock: threading.Lock = threading.Lock()
        self._pending_mesh_queue: list = []
        self._render_callback = None
        self._loaded_generation: int = 0
        self._batch_active: bool = False
        self._built_count: int = 0
        self._upload_sessions: dict = {}

    def register_primitives(self):
        self._meshes["cube"] = make_cube_mesh()
        self._meshes["sphere"] = make_sphere_mesh()
        self._meshes["plane"] = make_plane_mesh()
        self._meshes["quad"] = make_quad_mesh()
        for m in self._meshes.values():
            m.build_gl(self._ctx, self._default_prog)
            if self._outline_prog:
                m.build_outline_vao(self._ctx, self._outline_prog)

    def get_mesh(self, name: str) -> Optional[MeshData]:
        return self._meshes.get(name)

    def get_or_create(self, name: str, file_path: str = "", scale: float = 1.0,
                      center_pivot: bool = False, flip_uvs: bool = False) -> Optional[MeshData]:
        cache_key = f"{file_path or name}|s={scale}|cp={center_pivot}|fu={flip_uvs}"
        if cache_key in self._meshes:
            return self._meshes[cache_key]
        if not file_path:
            if name == "cube":
                m = make_cube_mesh()
            elif name == "sphere":
                m = make_sphere_mesh()
            elif name == "plane":
                m = make_plane_mesh()
            elif name == "quad":
                m = make_quad_mesh()
            else:
                if cache_key not in self._pending_cache_keys:
                    self._pending_cache_keys.add(cache_key)
                    with self._async_lock:
                        self._pending_async_loads += 1
                    task_start(_mesh_load_task(cache_key), f"Loading {_display_name(name)}...", fraction=None)
                    self._load_async(name, "", cache_key, scale, center_pivot, flip_uvs)
                return None
        else:
            if cache_key not in self._pending_cache_keys:
                self._pending_cache_keys.add(cache_key)
                with self._async_lock:
                    self._pending_async_loads += 1
                task_start(_mesh_load_task(cache_key), f"Loading {_display_name(file_path)}...", fraction=None)
                self._load_async(name, file_path, cache_key, scale, center_pivot, flip_uvs)
            return None
        self._apply_transforms(m, cache_key, scale, center_pivot, flip_uvs)
        self._do_render_request()
        return m

    def _prepare_mesh_cpu(self, m: MeshData, scale: float,
                          center_pivot: bool, flip_uvs: bool):
        if scale != 1.0:
            verts = m.vertices.reshape(-1, 3)
            verts = verts * scale
            m.vertices = verts.flatten()
            for i in range(len(m.blendshape_pos_deltas)):
                m.blendshape_pos_deltas[i] = np.ascontiguousarray(m.blendshape_pos_deltas[i] * scale, dtype=np.float32)
        if center_pivot:
            verts = m.vertices.reshape(-1, 3)
            center = verts.mean(axis=0)
            verts = verts - center
            m.vertices = verts.flatten()
        if flip_uvs and len(m.uvs) > 0:
            m.uvs = np.array(m.uvs, dtype=np.float32, copy=True).reshape(-1, 2)
            m.uvs[:, 1] = 1.0 - m.uvs[:, 1]
            m.uvs = np.ascontiguousarray(m.uvs.reshape(-1), dtype=np.float32)
        m.vertices = np.ascontiguousarray(m.vertices, dtype=np.float32)
        if len(m.indices) > 0:
            m.indices = np.ascontiguousarray(m.indices, dtype=np.uint32)
        m.compute_aabb()
        m.prepare_upload_bytes()

    def _apply_transforms(self, m: MeshData, cache_key: str, scale: float,
                          center_pivot: bool, flip_uvs: bool):
        self._prepare_mesh_cpu(m, scale, center_pivot, flip_uvs)
        m.build_gl(self._ctx, self._default_prog)
        if self._outline_prog:
            m.build_outline_vao(self._ctx, self._outline_prog)
        self._meshes[cache_key] = m
        from core.spatial.bvh import prebuild_mesh_bvh
        mesh_name = _display_name(cache_key.split("|")[0])
        prebuild_mesh_bvh(m.vertices, m.indices, title=f"Building BVH {mesh_name}...")
        self._record_mesh_built(cache_key)

    def _finish_mesh_ready(self, m: MeshData, cache_key: str):
        m.build_gl(self._ctx, self._default_prog)
        if self._outline_prog:
            m.build_outline_vao(self._ctx, self._outline_prog)
        self._meshes[cache_key] = m
        self._record_mesh_built(cache_key)
        self._pending_cache_keys.discard(cache_key)
        task_complete(_mesh_load_task(cache_key))
        self._loaded_generation += 1
        self._do_render_request()

    def _record_mesh_built(self, cache_key: str):
        if cache_key not in self._pending_cache_keys:
            return
        if not self._batch_active:
            total = len(self._pending_cache_keys)
            if total < 2:
                return
            self._batch_active = True
            self._built_count = 0
            task_start("mesh_batch", "Building meshes…", fraction=0.0, total=float(total))
        self._built_count += 1
        total = len(self._pending_cache_keys) or 1
        task_update(
            "mesh_batch",
            fraction=min(1.0, self._built_count / total),
            detail=f"Built {self._built_count}/{total} meshes",
        )

    def _resolve_path(self, key: str, file_path: str) -> str:
        if file_path and os.path.exists(file_path):
            return file_path
        elif file_path:
            rel = os.path.join(os.getcwd(), file_path)
            if os.path.exists(rel):
                return rel
            eng = Engine.instance()
            root = eng.project_root if eng and eng.project_root else os.getcwd()
            rel_root = os.path.join(root, file_path)
            if os.path.exists(rel_root):
                return os.path.normpath(rel_root).replace("\\", "/")
            if len(file_path) > 1 and file_path[1] == ":":
                parts = file_path.replace("\\", "/").split("/")
                for i in range(len(parts)):
                    sub = "/".join(parts[i:])
                    if sub:
                        c = os.path.normpath(os.path.join(root, sub))
                        if os.path.exists(c):
                            return c.replace("\\", "/")
            for base in ["", "assets/", "assets/models/"]:
                for ext in [".obj", ".fbx", ".stl", ".gltf", ".glb", ".usdz",
                            ".OBJ", ".FBX", ".STL", ".GLTF", ".GLB", ".USDZ"]:
                    candidate = os.path.join(base, key + ext)
                    if os.path.exists(candidate):
                        return candidate
                if file_path.endswith((".obj", ".fbx", ".stl", ".gltf", ".glb", ".usdz",
                                       ".OBJ", ".FBX", ".STL", ".GLTF", ".GLB", ".USDZ")) and os.path.exists(file_path):
                    return file_path
        else:
            for ext in [".obj", ".fbx", ".stl", ".gltf", ".glb", ".usdz",
                        ".OBJ", ".FBX", ".STL", ".GLTF", ".GLB", ".USDZ"]:
                for base in ["assets/models/", "assets/"]:
                    candidate = os.path.join(base, key + ext)
                    if os.path.exists(candidate):
                        return candidate
        return ""

    def _build_mesh_data(self, import_data):
        if import_data is None or len(import_data.vertices) == 0:
            return None
        m = MeshData()
        m.vertices = np.ascontiguousarray(import_data.vertices, dtype=np.float32)
        m.normals = np.ascontiguousarray(import_data.normals, dtype=np.float32)
        m.uvs = np.ascontiguousarray(import_data.uvs, dtype=np.float32)
        m.indices = np.ascontiguousarray(import_data.indices, dtype=np.uint32)
        m.is_error_mesh = import_data.is_error_mesh
        m.sub_mesh_ranges = list(getattr(import_data, 'sub_mesh_ranges', []))
        m.sub_mesh_names = list(getattr(import_data, 'sub_mesh_names', []))
        if getattr(import_data, 'has_skeleton', False) and len(getattr(import_data, 'bone_indices', np.zeros((0, 4), dtype=np.int32))) > 0:
            m.has_skeleton = True
            m.bone_names = list(import_data.bone_names)
            m.bone_parents = list(import_data.bone_parents)
            m.bone_offset_matrices = [np.ascontiguousarray(x, dtype=np.float32) for x in import_data.bone_offset_matrices]
            m.bone_bind_local = [np.ascontiguousarray(x, dtype=np.float32) for x in import_data.bone_bind_local]
            m.bone_indices = np.ascontiguousarray(import_data.bone_indices, dtype=np.int32)
            m.bone_weights = np.ascontiguousarray(import_data.bone_weights, dtype=np.float32)
        blend_names = list(getattr(import_data, 'blendshape_names', []) or [])
        if blend_names:
            m.blendshape_names = blend_names
            m.blendshape_index = {n: i for i, n in enumerate(blend_names)}
            m.blendshape_vert_indices = [np.ascontiguousarray(x, dtype=np.int32) for x in getattr(import_data, 'blendshape_indices', [])]
            m.blendshape_pos_deltas = [np.ascontiguousarray(x, dtype=np.float32).reshape(-1, 3) for x in getattr(import_data, 'blendshape_positions', [])]
            m.blendshape_nrm_deltas = [np.ascontiguousarray(x, dtype=np.float32).reshape(-1, 3) for x in getattr(import_data, 'blendshape_normals', [])]
        return m

    def _load_async(self, key: str, file_path: str, cache_key: str,
                    scale: float, cp: bool, fuvs: bool):
        path = self._resolve_path(key, file_path)
        if not path:
            Logger.warning(f"Mesh not found: {key}, using error fallback")
            notify_error(f"Mesh not found: {_display_name(key)}")
            path = _ERROR_MESH_PATH
        if path != _ERROR_MESH_PATH:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = None
            if size:
                task_update(_mesh_load_task(cache_key), total=float(size), units="bytes")
        from core.assets.asset_importer import load_mesh_future, load_obj_future
        lower_path = path.lower()

        def _io_done(fut):
            queued = False
            try:
                try:
                    import_data = fut.result()
                except Exception:
                    import_data = None
                is_error = (path == _ERROR_MESH_PATH)
                if not is_error and (import_data is None or len(import_data.vertices) == 0):
                    Logger.warning(f"Failed to load mesh, falling back to error mesh")
                    notify_error(f"Failed to load {_display_name(key)}")
                    from core.assets.asset_importer import load_mesh
                    import_data = load_mesh(_ERROR_MESH_PATH)
                    is_error = True
                if is_error and import_data is not None and len(import_data.vertices) > 0:
                    verts = import_data.vertices.reshape(-1, 3).astype(np.float32)
                    norms = import_data.normals.reshape(-1, 3).astype(np.float32)
                    rot = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]], dtype=np.float32)
                    verts = verts @ rot.T
                    norms = norms @ rot.T
                    s = np.array([0.25 / 9.0, 1.0 / 9.0, 1.0 / 9.0], dtype=np.float32)
                    import_data.vertices = (verts * s).ravel().astype(np.float32)
                    import_data.normals = norms.ravel().astype(np.float32)
                    import_data.is_error_mesh = True
                if import_data is not None and len(import_data.vertices) > 0:
                    task_set_detail(
                        _mesh_load_task(cache_key),
                        f"Imported {_fmt_count(len(import_data.vertices) / 3)} verts · "
                        f"{_fmt_count(len(import_data.indices) / 3)} tris",
                    )
                    m = self._build_mesh_data(import_data)
                    if m is not None:
                        self._prepare_mesh_cpu(m, scale, cp, fuvs)
                        try:
                            from core.spatial.bvh import prebuild_mesh_bvh
                            mesh_name = _display_name(cache_key.split("|")[0])
                            prebuild_mesh_bvh(m.vertices, m.indices, title=f"Building BVH {mesh_name}...")
                        except Exception:
                            pass
                        with self._async_lock:
                            self._pending_mesh_queue.append((cache_key, m))
                        self._on_async_load_complete()
                        queued = True
                        return
                with self._async_lock:
                    self._pending_cache_keys.discard(cache_key)
                self._on_async_load_complete()
            finally:
                if not queued:
                    task_complete(_mesh_load_task(cache_key))
        if lower_path.endswith(".obj"):
            fut = load_obj_future(path)
        else:
            fut = load_mesh_future(path)
        fut.add_done_callback(_io_done)

    def set_render_callback(self, callback):
        self._render_callback = callback

    def _on_async_load_complete(self):
        with self._async_lock:
            self._pending_async_loads -= 1
            if self._pending_async_loads <= 0 and self._render_callback:
                _deferred_call(self._render_callback)

    def _do_render_request(self):
        if self._render_callback:
            self._render_callback()

    def _new_upload_session(self, m: MeshData):
        streams = []
        if m._up_vbo:
            streams.append(["vbo", m._up_vbo, None, 0])
        if m._up_ibo:
            streams.append(["ibo", m._up_ibo, None, 0])
        if m._up_bone:
            streams.append(["bone", m._up_bone, None, 0])
        if m._up_color:
            streams.append(["color", m._up_color, None, 0])
        if m._up_outline:
            streams.append(["outline", m._up_outline, None, 0])
        return {"mesh": m, "streams": streams, "si": 0, "done": not streams}

    def _pump_upload_session(self, cache_key: str, budget: int) -> int:
        s = self._upload_sessions[cache_key]
        spent = 0
        streams = s["streams"]
        while budget > 0 and s["si"] < len(streams):
            st = streams[s["si"]]
            data = st[1]
            if st[2] is None:
                try:
                    st[2] = self._ctx.buffer(reserve=len(data))
                except Exception:
                    break
            off = st[3]
            if off >= len(data):
                s["si"] += 1
                continue
            n = min(len(data) - off, budget, _MESH_UPLOAD_CHUNK_BYTES)
            try:
                st[2].write(data[off:off + n], offset=off)
            except Exception:
                break
            st[3] = off + n
            spent += n
            budget -= n
            if st[3] >= len(data):
                s["si"] += 1
        if s["si"] >= len(streams):
            s["done"] = True
        return spent

    def _cancel_upload_session(self, cache_key: str):
        s = self._upload_sessions.pop(cache_key, None)
        if s is None:
            return
        for _kind, _data, buf, _off in s["streams"]:
            if buf is not None:
                try:
                    buf.release()
                except Exception:
                    pass

    def _complete_upload_session(self, cache_key: str):
        s = self._upload_sessions.pop(cache_key, None)
        if s is None:
            return
        if cache_key not in self._pending_cache_keys:
            self._cancel_upload_session(cache_key)
            return
        m = s["mesh"]
        bufs: dict = {}
        for kind, _data, buf, _off in s["streams"]:
            if buf is not None:
                bufs[kind] = buf
        if "vbo" not in bufs and m.vertices.size > 0:
            self._finish_mesh_ready(m, cache_key)
            return
        try:
            m._ctx = self._ctx
            m._invalidate_vaos()
            m._gpu_version += 1
            if "vbo" in bufs:
                m._vbo = bufs["vbo"]
            if "ibo" in bufs:
                m._ibo = bufs["ibo"]
            elif m.indices.size == 0 and m._ibo is not None:
                try:
                    m._ibo.release()
                except Exception:
                    pass
                m._ibo = None
            if "bone" in bufs:
                m._bone_vbo = bufs["bone"]
                m.bone_count = len(m.bone_offset_matrices)
            if "color" in bufs:
                m._color_vbo = bufs["color"]
            if "outline" in bufs:
                m._outline_vbo = bufs["outline"]
            m._consume_upload_bytes()
            m._build_vao_for_program(self._default_prog)
            m._vao = m._vao_cache.get(id(self._default_prog))
            if m._outline_vbo is not None and self._outline_prog:
                m._create_outline_vao(self._outline_prog)
            elif self._outline_prog is not None and m.vertices.size > 0:
                try:
                    m.build_outline_vao(self._ctx, self._outline_prog)
                except Exception:
                    pass
        except Exception:
            self._cancel_upload_session(cache_key)
            try:
                self._finish_mesh_ready(m, cache_key)
            except Exception:
                self._pending_cache_keys.discard(cache_key)
                task_complete(_mesh_load_task(cache_key))
            return
        self._meshes[cache_key] = m
        self._record_mesh_built(cache_key)
        self._pending_cache_keys.discard(cache_key)
        task_complete(_mesh_load_task(cache_key))
        self._loaded_generation += 1
        self._do_render_request()

    def cancel_prefix(self, prefix: str):
        for key in [k for k in list(self._upload_sessions.keys()) if k.startswith(prefix)]:
            self._cancel_upload_session(key)
            self._pending_cache_keys.discard(key)
            task_complete(_mesh_load_task(key))

    def process_pending(self, budget_bytes: int | None = None, max_completions: int | None = None):
        if budget_bytes is None:
            budget_bytes = _MESH_UPLOAD_BUDGET_BYTES
        if max_completions is None:
            max_completions = _MESH_MAX_COMPLETIONS_PER_FRAME
        with self._async_lock:
            queued = list(self._pending_mesh_queue) if self._pending_mesh_queue else []
            self._pending_mesh_queue.clear()
        for cache_key, m in queued:
            if cache_key not in self._pending_cache_keys:
                continue
            if cache_key in self._meshes or cache_key in self._upload_sessions:
                continue
            if m is None or m.vertices.size == 0:
                self._pending_cache_keys.discard(cache_key)
                task_complete(_mesh_load_task(cache_key))
                continue
            task_set_title(_mesh_load_task(cache_key), f"Uploading {_display_name(cache_key.split('|')[0])}...")
            self._upload_sessions[cache_key] = self._new_upload_session(m)
        if not self._upload_sessions:
            self._finish_batch_if_drained()
            return
        budget = max(0, int(budget_bytes))
        completed = 0
        for cache_key in list(self._upload_sessions.keys()):
            if completed >= max_completions:
                break
            if cache_key not in self._pending_cache_keys:
                self._cancel_upload_session(cache_key)
                continue
            if budget <= 0:
                break
            budget -= self._pump_upload_session(cache_key, budget)
            s = self._upload_sessions.get(cache_key)
            if s is not None and s["done"]:
                self._complete_upload_session(cache_key)
                completed += 1
        self._finish_batch_if_drained()

    def _finish_batch_if_drained(self):
        if not self._batch_active:
            return
        with self._async_lock:
            drained = (not self._pending_mesh_queue and not self._upload_sessions
                       and self._pending_async_loads <= 0)
        if drained:
            task_complete("mesh_batch")
            self._batch_active = False

    def bump_generation(self):
        self._loaded_generation += 1

    def clear_scene_data(self):
        if self._batch_active:
            task_complete("mesh_batch")
            self._batch_active = False
        with self._async_lock:
            pending_keys = list(self._pending_cache_keys)
            self._pending_mesh_queue.clear()
            self._pending_async_loads = 0
            self._pending_cache_keys.clear()
        for key in list(self._upload_sessions.keys()):
            self._cancel_upload_session(key)
        for key in pending_keys:
            task_complete(_mesh_load_task(key))
        self._built_count = 0
        for m in self._meshes.values():
            m.release()
        self._meshes.clear()
        self.register_primitives()
        self._loaded_generation += 1

    def release(self):
        for key in list(self._upload_sessions.keys()):
            self._cancel_upload_session(key)
        for m in self._meshes.values():
            m.release()
