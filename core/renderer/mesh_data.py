# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import sys
import numpy as np
import moderngl
from typing import Optional, Any
from core.foundation.logger import Logger

# Shader directory relative to project root or executable.
# Shaders live in core/shaders, sorted by kind:
# materials/ (surface shaders), internal/ (engine passes), compute/,
# include/ (glsl snippets), legacy/ (old .comp/.geom).
# In a Nuitka build, __file__ may point to the source path (development)
# or inside the dist. We try both: source path first (dev), then exe path (dist).
_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHADER_CANDIDATES = [
    os.path.join(_ENGINE_ROOT, "core", "shaders"),
    os.path.join(os.path.dirname(sys.executable), "core", "shaders"),
]
_SHADER_SUBDIRS = ("", "materials", "internal", "compute", "include", "legacy")
_find_cache: dict[str, str | None] = {}


def _find_in_shaders(filename: str) -> str | None:
    if filename in _find_cache:
        return _find_cache[filename]
    for base in _SHADER_CANDIDATES:
        for sub in _SHADER_SUBDIRS:
            full = os.path.join(base, sub, filename) if sub else os.path.join(base, filename)
            if os.path.exists(full):
                _find_cache[filename] = full
                return full
    _find_cache[filename] = None
    return None


SHADER_DIR = next((p for p in _SHADER_CANDIDATES if os.path.isdir(p)), _SHADER_CANDIDATES[0])


def _resolve_shader_file(name: str) -> str:
    if os.path.isabs(name) and os.path.exists(name):
        return name
    if os.path.exists(name):
        return name
    if "/" in name or "\\" in name:
        found = _find_in_shaders(os.path.basename(name))
        if found is not None:
            return found
        for base in _SHADER_CANDIDATES:
            candidate = os.path.join(base, name)
            if os.path.exists(candidate):
                return candidate
    else:
        found = _find_in_shaders(name)
        if found is not None:
            return found
    return os.path.join(SHADER_DIR, name)


def read_shader(name: str) -> str:
    path = _resolve_shader_file(name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _to_pascal(base: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in base.split("_") if part)


def _split_shader_block(text: str) -> tuple[str, str] | None:
    start = text.find("GLSLPROGRAM")
    if start < 0:
        return None
    start += len("GLSLPROGRAM")
    end = text.find("ENDGLSL", start)
    if end < 0:
        return None
    block = text[start:end]
    marker = "// @FRAGMENT"
    idx = block.find(marker)
    if idx < 0:
        return None
    return block[:idx].strip(), block[idx + len(marker):].strip()


_SHADER_NAME_OVERRIDES = {"skybox": "SkyboxLegacy"}


def read_shader_pair(base: str) -> tuple[str, str]:
    pascal = _SHADER_NAME_OVERRIDES.get(base, _to_pascal(base))
    for candidate in (f"{pascal}.shader", f"{base}.shader"):
        path = _find_in_shaders(candidate)
        if path is not None:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            split = _split_shader_block(text)
            if split is not None:
                return split
    vert_name: str | None = None
    frag_name: str | None = None
    if base == "particle_gpu":
        vert_name, frag_name = "particle_gpu.vert", "particle.frag"
    elif base in ("underwater", "caustics"):
        vert_name, frag_name = "shadow_overlay.vert", f"{base}.frag"
    else:
        vert_name, frag_name = f"{base}.vert", f"{base}.frag"
    return read_shader(vert_name), read_shader(frag_name)


def read_compute_source(base: str) -> str:
    pascal = _to_pascal(base)
    for candidate in (f"{pascal}.compute", f"{base}.compute", f"{base}.comp"):
        full = _find_in_shaders(candidate)
        if full is not None:
            with open(full, "r", encoding="utf-8") as f:
                text = f.read()
            if candidate.endswith(".compute"):
                split_start = text.find("GLSLPROGRAM")
                if split_start >= 0:
                    split_start += len("GLSLPROGRAM")
                    split_end = text.find("ENDGLSL", split_start)
                    if split_end >= 0:
                        return text[split_start:split_end].strip()
            return text
    return read_shader(f"{base}.comp")


class MeshData:
    """GPU-ready mesh with vertex buffers, index buffers and VAO cache."""

    outline_max_triangles: int = 40000

    def __init__(self):
        self.vertices: np.ndarray = np.array([], dtype=np.float32)
        self.indices: np.ndarray = np.array([], dtype=np.uint32)
        self.normals: np.ndarray = np.array([], dtype=np.float32)
        self.uvs: np.ndarray = np.array([], dtype=np.float32)
        self.aabb_min: np.ndarray = np.array([-0.5, -0.5, -0.5], dtype=np.float32)
        self.aabb_max: np.ndarray = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        self.is_error_mesh: bool = False
        self.sub_mesh_ranges: list[tuple[int, int]] = []
        self.sub_mesh_names: list[str] = []
        self._vao: Optional[Any] = None
        self._vbo: Optional[Any] = None
        self._ibo: Optional[Any] = None
        self._outline_vao: Optional[Any] = None
        self._outline_vbo: Optional[Any] = None
        self._ctx: Optional[Any] = None
        self._vao_cache: dict[int, Any] = {}
        self._bounding_radius: Optional[float] = None
        self.has_skeleton: bool = False
        self.bone_names: list[str] = []
        self.bone_parents: list[int] = []
        self.bone_offset_matrices: list[np.ndarray] = []
        self.bone_bind_local: list[np.ndarray] = []
        self.bone_indices: np.ndarray = np.zeros((0, 4), dtype=np.int32)
        self.bone_weights: np.ndarray = np.zeros((0, 4), dtype=np.float32)
        self.blendshape_names: list[str] = []
        self.blendshape_index: dict[str, int] = {}
        self.blendshape_vert_indices: list[np.ndarray] = []
        self.blendshape_pos_deltas: list[np.ndarray] = []
        self.blendshape_nrm_deltas: list[np.ndarray] = []
        self.colors: np.ndarray = np.array([], dtype=np.float32)
        self.bone_count: int = 0
        self._bone_vbo: Optional[Any] = None
        self._color_vbo: Optional[Any] = None
        self._gpu_version: int = 0
        self._up_vbo: Optional[bytes] = None
        self._up_ibo: Optional[bytes] = None
        self._up_bone: Optional[bytes] = None
        self._up_color: Optional[bytes] = None
        self._up_outline: Optional[bytes] = None

    def compute_aabb(self):
        verts = self.vertices
        if verts.size < 3:
            self._bounding_radius = 0.0
            return
        v = verts.reshape(-1, 3)
        try:
            from core._render_utils import compute_bounding_spheres
            self.aabb_min = np.min(v, axis=0).astype(np.float32, copy=False)
            self.aabb_max = np.max(v, axis=0).astype(np.float32, copy=False)
        except ImportError:
            self.aabb_min = v.min(axis=0).astype(np.float32)
            self.aabb_max = v.max(axis=0).astype(np.float32)
        self._bounding_radius = float(np.linalg.norm(self.aabb_max - self.aabb_min) * 0.5)

    @property
    def bounding_radius(self) -> float:
        if self._bounding_radius is None:
            self.compute_aabb()
        return self._bounding_radius

    @property
    def has_blendshapes(self) -> bool:
        return len(self.blendshape_names) > 0 and len(self.blendshape_vert_indices) == len(self.blendshape_names)

    @property
    def blendshape_count(self) -> int:
        return len(self.blendshape_names)

    def compute_morph(self, weights) -> tuple[np.ndarray, np.ndarray]:
        base_v = self.vertices.reshape(-1, 3)
        n_verts = base_v.shape[0]
        v = base_v.copy()
        if self.normals.size == self.vertices.size:
            base_n = self.normals.reshape(-1, 3)
            n = base_n.copy()
        else:
            base_n = np.zeros_like(v)
            n = np.zeros_like(v)
        count = len(self.blendshape_names)
        if count == 0 or n_verts == 0:
            return np.ascontiguousarray(v.reshape(-1), dtype=np.float32), np.ascontiguousarray(n.reshape(-1), dtype=np.float32)
        active = []
        for i in range(min(count, len(weights))):
            try:
                w = float(weights[i])
            except (TypeError, ValueError):
                continue
            if w != 0.0 and np.isfinite(w):
                active.append((i, w))
        if not active:
            return np.ascontiguousarray(v.reshape(-1), dtype=np.float32), np.ascontiguousarray(n.reshape(-1), dtype=np.float32)
        touched = []
        for i, w in active:
            if i >= len(self.blendshape_vert_indices):
                continue
            idx = self.blendshape_vert_indices[i]
            if idx is None or len(idx) == 0:
                continue
            v[idx] += w * self.blendshape_pos_deltas[i].reshape(-1, 3)
            n[idx] += w * self.blendshape_nrm_deltas[i].reshape(-1, 3)
            touched.append(idx)
        if touched:
            aff = np.unique(np.concatenate(touched))
            aff = aff[(aff >= 0) & (aff < n_verts)]
            if len(aff) > 0:
                sel = n[aff]
                nl = np.linalg.norm(sel, axis=1, keepdims=True)
                good = (nl[:, 0] > 1e-12)
                sel[good] /= nl[good]
                bad = ~good
                if bool(bad.any()):
                    sel[bad] = base_n[aff[bad]]
                n[aff] = sel
        return np.ascontiguousarray(v.reshape(-1), dtype=np.float32), np.ascontiguousarray(n.reshape(-1), dtype=np.float32)

    def make_morphed_clone(self, weights, ctx=None, program=None, outline_prog=None):
        clone = MeshData()
        v2, n2 = self.compute_morph(weights)
        clone.vertices = v2
        clone.normals = n2
        clone.uvs = self.uvs
        clone.indices = self.indices
        clone.colors = self.colors
        clone.is_error_mesh = self.is_error_mesh
        clone.sub_mesh_ranges = list(self.sub_mesh_ranges)
        clone.sub_mesh_names = list(self.sub_mesh_names)
        clone.has_skeleton = self.has_skeleton
        clone.bone_names = list(self.bone_names)
        clone.bone_parents = list(self.bone_parents)
        clone.bone_offset_matrices = list(self.bone_offset_matrices)
        clone.bone_bind_local = list(self.bone_bind_local)
        clone.bone_indices = self.bone_indices
        clone.bone_weights = self.bone_weights
        clone.blendshape_names = list(self.blendshape_names)
        clone.blendshape_index = dict(self.blendshape_index)
        clone.blendshape_vert_indices = list(self.blendshape_vert_indices)
        clone.blendshape_pos_deltas = list(self.blendshape_pos_deltas)
        clone.blendshape_nrm_deltas = list(self.blendshape_nrm_deltas)
        clone.compute_aabb()
        if ctx is not None and program is not None:
            clone.build_gl(ctx, program)
            if outline_prog is not None:
                clone.build_outline_vao(ctx, outline_prog)
        return clone

    def _invalidate_vaos(self):
        for v in self._vao_cache.values():
            if v:
                try:
                    v.release()
                except Exception:
                    pass
        self._vao_cache.clear()
        self._vao = None
        if self._outline_vao is not None:
            try:
                self._outline_vao.release()
            except Exception:
                pass
            self._outline_vao = None
        if self._outline_vbo is not None:
            try:
                self._outline_vbo.release()
            except Exception:
                pass
            self._outline_vbo = None

    def _interleaved_vbo_bytes(self) -> bytes:
        verts = self.vertices
        n_verts = verts.size // 3
        data = np.empty((n_verts, 8), dtype=np.float32)
        data[:, 0:3] = verts.reshape(-1, 3)
        norms = self.normals
        if norms.size == verts.size:
            data[:, 3:6] = norms.reshape(-1, 3)
        else:
            data[:, 3:6] = 0.0
            if norms.size >= 3:
                data[:, 3:6] = np.zeros((n_verts, 3), dtype=np.float32)
        uvs = self.uvs
        if uvs.size * 3 == verts.size * 2:
            data[:, 6:8] = uvs.reshape(-1, 2)
        else:
            data[:, 6:8] = 0.0
        return data.tobytes()

    def _bone_payload_bytes(self) -> Optional[bytes]:
        if not (self.has_skeleton and self.bone_indices.size > 0):
            return None
        nb = self.bone_indices.shape[0]
        bone_data = np.empty((nb, 8), dtype=np.float32)
        bone_data[:, 0:4] = self.bone_indices.reshape(-1, 4).astype(np.float32, copy=False)
        bone_data[:, 4:8] = self.bone_weights.reshape(-1, 4)
        return bone_data.tobytes()

    def estimate_upload_bytes(self) -> int:
        n_verts = self.vertices.size // 3 if self.vertices.size else 0
        total = n_verts * 32 + n_verts * 12
        if self.indices.size > 0:
            total += int(self.indices.size) * 4
        if self.has_skeleton and self.bone_indices.size > 0:
            total += int(self.bone_indices.shape[0]) * 32
        if self.colors.size == n_verts * 4:
            total += int(self.colors.size) * 4
        return total

    def prepare_upload_bytes(self) -> None:
        if self.vertices.size == 0:
            self._up_vbo = b""
            self._up_ibo = b""
            self._up_outline = None
            self._up_bone = None
            self._up_color = None
            return
        self._up_vbo = self._interleaved_vbo_bytes()
        idx = self.indices
        self._up_ibo = idx.astype(np.uint32, copy=False).tobytes() if idx.size > 0 else b""
        self._up_bone = self._bone_payload_bytes()
        cols = self.colors
        n_verts = self.vertices.size // 3
        self._up_color = cols.astype(np.float32, copy=False).tobytes() if cols.size == n_verts * 4 else None
        self._up_outline = None

    def _consume_upload_bytes(self) -> None:
        self._up_vbo = None
        self._up_ibo = None
        self._up_bone = None
        self._up_color = None
        self._up_outline = None

    def build_gl(self, ctx: moderngl.Context, program: moderngl.Program):
        self._ctx = ctx
        verts = self.vertices
        if verts.size == 0:
            return
        n_verts = verts.size // 3
        prebuilt = self._up_vbo if self._vbo is None else None
        b = prebuilt if prebuilt is not None else self._interleaved_vbo_bytes()
        _buffers_recreated = False
        if self._vbo is None:
            self._vbo = ctx.buffer(b)
            _buffers_recreated = True
        else:
            if self._vbo.size != len(b):
                try:
                    self._vbo.release()
                except Exception:
                    pass
                self._vbo = ctx.buffer(b)
                _buffers_recreated = True
            else:
                self._vbo.write(b)
        idx = self.indices
        if idx.size > 0:
            ib = self._up_ibo if (self._ibo is None and self._up_ibo) else idx.astype(np.uint32, copy=False).tobytes()
            if self._ibo is None:
                self._ibo = ctx.buffer(ib)
                _buffers_recreated = True
            else:
                if self._ibo.size != len(ib):
                    try:
                        self._ibo.release()
                    except Exception:
                        pass
                    self._ibo = ctx.buffer(ib)
                    _buffers_recreated = True
                else:
                    self._ibo.write(ib)
        elif self._ibo is not None:
            try:
                self._ibo.release()
            except Exception:
                pass
            self._ibo = None
            _buffers_recreated = True
        if self.has_skeleton and self.bone_indices.size > 0:
            bb = self._up_bone if (self._bone_vbo is None and self._up_bone) else None
            if bb is None:
                nb = self.bone_indices.shape[0]
                bone_data = np.empty((nb, 8), dtype=np.float32)
                bone_data[:, 0:4] = self.bone_indices.reshape(-1, 4).astype(np.float32, copy=False)
                bone_data[:, 4:8] = self.bone_weights.reshape(-1, 4)
                bb = bone_data.tobytes()
            if self._bone_vbo is None:
                self._bone_vbo = ctx.buffer(bb)
            else:
                if self._bone_vbo.size != len(bb):
                    try:
                        self._bone_vbo.release()
                    except Exception:
                        pass
                    self._bone_vbo = ctx.buffer(bb)
                else:
                    self._bone_vbo.write(bb)
            self.bone_count = len(self.bone_offset_matrices)
        cols = self.colors
        if cols.size == n_verts * 4:
            cb = self._up_color if (self._color_vbo is None and self._up_color) else cols.astype(np.float32, copy=False).tobytes()
            if self._color_vbo is None:
                self._color_vbo = ctx.buffer(cb)
                _buffers_recreated = True
            else:
                if self._color_vbo.size != len(cb):
                    try:
                        self._color_vbo.release()
                    except Exception:
                        pass
                    self._color_vbo = ctx.buffer(cb)
                    _buffers_recreated = True
                else:
                    self._color_vbo.write(cb)
        if _buffers_recreated:
            self._invalidate_vaos()
            self._gpu_version += 1
        if prebuilt is not None:
            self._consume_upload_bytes()
        self._build_vao_for_program(program)
        self._vao = self._vao_cache.get(id(program))

    def _build_vao_for_program(self, program: moderngl.Program):
        if self._ctx is None or self._vbo is None:
            return
        key = id(program)
        if key in self._vao_cache:
            return
        has_pos = "in_position" in program
        has_nrm = "in_normal" in program
        has_uv = "in_uv" in program
        has_col = "in_color" in program
        has_bone_idx = "in_bone_indices" in program
        has_bone_w = "in_bone_weights" in program
        fmt_parts = []
        attrib_names = []
        if has_pos:
            fmt_parts.append("3f")
            attrib_names.append("in_position")
        else:
            fmt_parts.append("3x4")
        if has_nrm:
            fmt_parts.append("3f")
            attrib_names.append("in_normal")
        else:
            fmt_parts.append("3x4")
        if has_uv:
            fmt_parts.append("2f")
            attrib_names.append("in_uv")
        else:
            fmt_parts.append("2x4")
        buffers = [(self._vbo, " ".join(fmt_parts), *attrib_names)]
        if has_col and self._color_vbo is None and len(self.vertices) > 0:
            n = len(self.vertices) // 3
            self._color_vbo = self._ctx.buffer(np.full((n, 4), 1.0, dtype=np.float32).tobytes())
        if self._bone_vbo is not None and has_bone_idx and has_bone_w:
            buffers.append((self._bone_vbo, "4f 4f", "in_bone_indices", "in_bone_weights"))
        if self._color_vbo is not None and has_col:
            buffers.append((self._color_vbo, "4f", "in_color"))
        self._vao_cache[key] = self._ctx.vertex_array(
            program,
            buffers,
            self._ibo
        )

    def render(self, program: Optional[moderngl.Program] = None):
        if program is not None:
            self._build_vao_for_program(program)
            vao = self._vao_cache.get(id(program))
        else:
            vao = self._vao
        if vao:
            try:
                vao.render()
            except Exception as e:
                Logger.error("MeshData.render VAO render failed", e)

    def render_range(self, program: moderngl.Program, start: int, count: int):
        self._build_vao_for_program(program)
        vao = self._vao_cache.get(id(program))
        if vao:
            try:
                vao.render(vertices=count, first=start)
            except Exception as e:
                Logger.error("MeshData.render_range VAO render failed", e)

    def build_outline_vao(self, ctx: moderngl.Context, program: moderngl.Program):
        if len(self.vertices) == 0:
            return
        if self._outline_vbo is None and self._up_outline:
            raw = self._up_outline
        else:
            raw = self.vertices.astype(np.float32, copy=False).tobytes()
        if self._outline_vbo is None:
            self._outline_vbo = ctx.buffer(raw)
        else:
            try:
                if self._outline_vbo.size != len(raw):
                    try:
                        self._outline_vbo.release()
                    except Exception:
                        pass
                    self._outline_vbo = ctx.buffer(raw)
                else:
                    self._outline_vbo.write(raw)
            except Exception:
                try:
                    self._outline_vbo.release()
                except Exception:
                    pass
                self._outline_vbo = ctx.buffer(raw)
        self._create_outline_vao(program)

    def _create_outline_vao(self, program: moderngl.Program):
        if self._outline_vbo is None or self._ctx is None:
            return
        try:
            if self._outline_vao is not None:
                try:
                    self._outline_vao.release()
                except Exception:
                    pass
                self._outline_vao = None
            self._outline_vao = self._ctx.vertex_array(
                program,
                [(self._outline_vbo, "3f", "in_position")],
                self._ibo
            )
        except Exception:
            pass

    def render_outline(self):
        if not self._outline_vao:
            return
        if len(self.indices) // 3 > self.outline_max_triangles:
            return
        try:
            self._outline_vao.render()
        except Exception as e:
            Logger.error("MeshData.render_outline VAO render failed", e)

    def release(self):
        if self._vbo:
            try:
                self._vbo.release()
            except Exception:
                pass
        if self._ibo:
            try:
                self._ibo.release()
            except Exception:
                pass
        if self._bone_vbo:
            try:
                self._bone_vbo.release()
            except Exception:
                pass
            self._bone_vbo = None
        if self._color_vbo:
            try:
                self._color_vbo.release()
            except Exception:
                pass
            self._color_vbo = None
        if self._outline_vao:
            try:
                self._outline_vao.release()
            except Exception:
                pass
        if self._outline_vbo:
            try:
                self._outline_vbo.release()
            except Exception:
                pass
        for v in self._vao_cache.values():
            if v:
                try:
                    v.release()
                except Exception:
                    pass
        self._vao_cache.clear()
        self._vao = None
        self._vbo = None
        self._ibo = None
        self._outline_vao = None
        self._outline_vbo = None
        self._up_vbo = None
        self._up_ibo = None
        self._up_bone = None
        self._up_color = None
        self._up_outline = None
