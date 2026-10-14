# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from core.components.mesh_editor.probuilder_mesh import ProBuilderMesh


def extrude_faces(mesh: ProBuilderMesh, face_indices: set[int], distance: float = 0.25):
    if not face_indices or mesh.indices.size == 0:
        return
    pos = mesh.positions
    idx = mesh.indices.astype(np.int32)
    face_set = set(face_indices)
    border_edges = _get_face_border_edges(mesh, face_indices)
    face_verts = set()
    for fi in face_indices:
        if fi < idx.shape[0]:
            face_verts.update([int(idx[fi, 0]), int(idx[fi, 1]), int(idx[fi, 2])])
    normals = np.zeros((pos.shape[0], 3), dtype=np.float32)
    for fi in range(idx.shape[0]):
        v0, v1, v2 = pos[idx[fi, 0]], pos[idx[fi, 1]], pos[idx[fi, 2]]
        n = np.cross(v1 - v0, v2 - v0)
        nlen = np.linalg.norm(n)
        if nlen > 1e-8:
            n = n / nlen
        for j in range(3):
            normals[idx[fi, j]] += n
    for i in range(normals.shape[0]):
        nlen = np.linalg.norm(normals[i])
        if nlen > 1e-8:
            normals[i] = normals[i] / nlen
    avg_normal = np.mean([normals[list(face_verts)]], axis=1)[0] if face_verts else np.array([0, 1, 0])
    nlen = np.linalg.norm(avg_normal)
    if nlen > 1e-8:
        avg_normal = avg_normal / nlen
    else:
        avg_normal = np.array([0, 1, 0])
    offset = avg_normal * distance
    vert_map = {}
    new_positions = pos.copy()
    old_face_count = idx.shape[0]
    for fi in face_indices:
        fi = int(fi)
        if fi >= old_face_count:
            continue
        new_verts = []
        for j in range(3):
            vi = int(idx[fi, j])
            if vi not in vert_map:
                nv = new_positions.shape[0]
                new_positions = np.vstack([new_positions, pos[vi] + offset])
                vert_map[vi] = nv
            new_verts.append(vert_map[vi])
        idx[fi, 0] = new_verts[0]
        idx[fi, 1] = new_verts[1]
        idx[fi, 2] = new_verts[2]
    for fi in face_indices:
        fi = int(fi)
        if fi >= old_face_count:
            continue
        for j in range(3):
            a = int(idx[fi, j])
            b = int(idx[fi, (j + 1) % 3])
            edge = tuple(sorted((a, b)))
            if edge in border_edges:
                source_vi = None
                for sv, nv in vert_map.items():
                    if nv == a:
                        source_vi = sv
                        break
                source_vj = None
                for sv, nv in vert_map.items():
                    if nv == b:
                        source_vj = sv
                        break
                if source_vi is not None and source_vj is not None:
                    new_faces = np.array([[source_vi, source_vj, a],
                                          [source_vj, b, a]], dtype=np.int32)
                    idx = np.vstack([idx, new_faces])
    mesh.positions = new_positions.astype(np.float32)
    mesh.indices = idx.astype(np.uint32)
    mesh.rebuild_normals()
    mesh.rebuild_uvs()
    mesh.clear_selection()
    mesh._gpu_dirty = True


def _get_face_border_edges(mesh: ProBuilderMesh, face_indices: set[int]) -> set[tuple[int, int]]:
    idx = mesh.indices.astype(np.int32)
    edge_count = {}
    for fi in range(idx.shape[0]):
        if fi in face_indices:
            continue
        for j in range(3):
            a, b = int(idx[fi, j]), int(idx[fi, (j + 1) % 3])
            edge = tuple(sorted((a, b)))
            edge_count[edge] = edge_count.get(edge, 0) + 1
    border = set()
    for fi in face_indices:
        fi = int(fi)
        if fi >= idx.shape[0]:
            continue
        for j in range(3):
            a, b = int(idx[fi, j]), int(idx[fi, (j + 1) % 3])
            edge = tuple(sorted((a, b)))
            if edge not in edge_count:
                border.add(edge)
    return border


def subdivide_faces(mesh: ProBuilderMesh, face_indices: set[int]):
    if not face_indices or mesh.indices.size == 0:
        return
    pos = mesh.positions
    idx = mesh.indices.astype(np.int32)
    new_positions = pos.copy().tolist()
    new_idx = []
    for fi in range(idx.shape[0]):
        if fi not in face_indices:
            new_idx.append([int(idx[fi, 0]), int(idx[fi, 1]), int(idx[fi, 2])])
            continue
        v0, v1, v2 = int(idx[fi, 0]), int(idx[fi, 1]), int(idx[fi, 2])
        p0, p1, p2 = pos[v0], pos[v1], pos[v2]
        m01 = len(new_positions)
        new_positions.append((p0 + p1) * 0.5)
        m12 = len(new_positions)
        new_positions.append((p1 + p2) * 0.5)
        m20 = len(new_positions)
        new_positions.append((p2 + p0) * 0.5)
        new_idx.append([v0, m01, m20])
        new_idx.append([m01, v1, m12])
        new_idx.append([m01, m12, m20])
        new_idx.append([m20, m12, v2])
    mesh.positions = np.array(new_positions, dtype=np.float32)
    mesh.indices = np.array(new_idx, dtype=np.uint32)
    mesh.rebuild_normals()
    mesh.rebuild_uvs()
    mesh.clear_selection()
    mesh._gpu_dirty = True


def flip_normals(mesh: ProBuilderMesh, face_indices: set[int] | None = None):
    if mesh.indices.size == 0:
        return
    idx = mesh.indices
    if face_indices:
        for fi in face_indices:
            if fi < idx.shape[0]:
                idx[fi, 0], idx[fi, 2] = idx[fi, 2], idx[fi, 0]
    else:
        for i in range(idx.shape[0]):
            idx[i, 0], idx[i, 2] = idx[i, 2], idx[i, 0]
    mesh.indices = idx.astype(np.uint32)
    mesh.rebuild_normals()
    mesh.clear_selection()
    mesh._gpu_dirty = True
