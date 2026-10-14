# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from typing import Optional, Any


class _MeshState:

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
        self._shadow_vbo: Optional[Any] = None
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
