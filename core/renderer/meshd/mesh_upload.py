# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from typing import Optional


class _MeshUpload:

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
