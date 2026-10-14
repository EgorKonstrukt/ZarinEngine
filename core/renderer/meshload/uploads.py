# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations

from core.foundation.progress import task_complete, task_set_title
from core.renderer.meshd import MeshData
from core.renderer.meshload.loading import (
    _MESH_MAX_COMPLETIONS_PER_FRAME,
    _MESH_UPLOAD_BUDGET_BYTES,
    _MESH_UPLOAD_CHUNK_BYTES,
    _display_name,
    _mesh_load_task,
)


class _MeshLoaderUploads:

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
