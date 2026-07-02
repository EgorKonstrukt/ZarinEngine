# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
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


def bevel_edges(mesh: ProBuilderMesh, edge_set: set[tuple[int, int]], amount: float = 0.1, segments: int = 1):
    if not edge_set or mesh.positions.size == 0:
        return
    pos = mesh.positions
    idx = mesh.indices.astype(np.int32)
    edge_verts = set()
    for a, b in edge_set:
        edge_verts.add(a)
        edge_verts.add(b)
    if not edge_verts:
        return
    path_verts = []
    for vi in edge_verts:
        path_verts.append(pos[vi])
    if not path_verts:
        return
    centroid = np.mean(path_verts, axis=0)
    new_positions = pos.copy()
    for vi in edge_verts:
        direction = pos[vi] - centroid
        dlen = np.linalg.norm(direction)
        if dlen > 1e-8:
            direction = direction / dlen
        new_positions[vi] = pos[vi] + direction * amount
    an_edges = set()
    for i in range(idx.shape[0]):
        for j in range(3):
            a, b = int(idx[i, j]), int(idx[i, (j + 1) % 3])
            edge = tuple(sorted((a, b)))
            if edge in edge_set:
                an_edges.add(i)
    new_idx_list = idx.tolist()
    for fi in an_edges:
        fi = int(fi)
        if fi >= len(new_idx_list):
            continue
        tri = new_idx_list[fi]
        v0, v1, v2 = tri[0], tri[1], tri[2]
        e01 = tuple(sorted((v0, v1)))
        e12 = tuple(sorted((v1, v2)))
        e20 = tuple(sorted((v2, v0)))
        matching = [e for e in [e01, e12, e20] if e in edge_set]
        if len(matching) >= 1:
            edge = matching[0]
            if edge == e01:
                mid = new_positions.shape[0]
                new_positions = np.vstack([new_positions, (new_positions[v0] + new_positions[v1]) * 0.5])
                tri2 = [v0, mid, v2]
                tri3 = [mid, v1, v2]
            elif edge == e12:
                mid = new_positions.shape[0]
                new_positions = np.vstack([new_positions, (new_positions[v1] + new_positions[v2]) * 0.5])
                tri2 = [v0, v1, mid]
                tri3 = [v0, mid, v2]
            else:
                mid = new_positions.shape[0]
                new_positions = np.vstack([new_positions, (new_positions[v2] + new_positions[v0]) * 0.5])
                tri2 = [v0, v1, mid]
                tri3 = [mid, v1, v2]
            new_idx_list[fi] = tri2
            new_idx_list.append(tri3)
    mesh.positions = new_positions.astype(np.float32)
    mesh.indices = np.array(new_idx_list, dtype=np.uint32)
    mesh.rebuild_normals()
    mesh.rebuild_uvs()
    mesh.clear_selection()
    mesh._gpu_dirty = True


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


def weld_vertices(mesh: ProBuilderMesh, threshold: float = 0.001):
    if mesh.positions.size == 0:
        return
    pos = mesh.positions
    n = pos.shape[0]
    merge_map = list(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            if np.linalg.norm(pos[i] - pos[j]) < threshold:
                merge_map[j] = i
    for i in range(n - 1, -1, -1):
        if merge_map[i] != i:
            merge_map[i] = merge_map[merge_map[i]]
    unique_indices = {}
    new_positions = []
    for i in range(n):
        target = merge_map[i]
        if target not in unique_indices:
            unique_indices[target] = len(new_positions)
            new_positions.append(pos[target].copy())
        elif i != target:
            unique_indices[i] = unique_indices[target]
    for i in range(n):
        target = merge_map[i]
        if i not in unique_indices:
            unique_indices[i] = unique_indices[target]
    new_indices = []
    idx = mesh.indices
    for i in range(idx.shape[0]):
        a = unique_indices.get(int(idx[i, 0]), int(idx[i, 0]))
        b = unique_indices.get(int(idx[i, 1]), int(idx[i, 1]))
        c = unique_indices.get(int(idx[i, 2]), int(idx[i, 2]))
        if a != b and b != c and a != c:
            new_indices.append([a, b, c])
        else:
            new_indices.append([a, b, c])
    mesh.positions = np.array(new_positions, dtype=np.float32)
    mesh.indices = np.array(new_indices, dtype=np.uint32)
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


def collapse_edges(mesh: ProBuilderMesh, edge_set: set[tuple[int, int]]):
    if not edge_set or mesh.positions.size == 0:
        return
    pos = mesh.positions
    idx = mesh.indices.astype(np.int32)
    collapse_map = {}
    for a, b in edge_set:
        mid = (pos[a] + pos[b]) * 0.5
        collapse_map[max(a, b)] = min(a, b)
        pos[min(a, b)] = mid
    new_idx = []
    for i in range(idx.shape[0]):
        v0 = collapse_map.get(int(idx[i, 0]), int(idx[i, 0]))
        v1 = collapse_map.get(int(idx[i, 1]), int(idx[i, 1]))
        v2 = collapse_map.get(int(idx[i, 2]), int(idx[i, 2]))
        if v0 != v1 and v1 != v2 and v0 != v2:
            new_idx.append([v0, v1, v2])
    mesh.positions = pos.astype(np.float32)
    mesh.indices = np.array(new_idx, dtype=np.uint32)
    mesh.rebuild_normals()
    mesh.rebuild_uvs()
    mesh.clear_selection()
    mesh._gpu_dirty = True


def bridge_edges(mesh: ProBuilderMesh, edge_a: tuple[int, int], edge_b: tuple[int, int]):
    if mesh.positions.size == 0:
        return
    new_idx = mesh.indices.tolist()
    a1, a2 = edge_a
    b1, b2 = edge_b
    new_idx.append([a1, b1, a2])
    new_idx.append([a2, b1, b2])
    mesh.indices = np.array(new_idx, dtype=np.uint32)
    mesh.rebuild_normals()
    mesh.rebuild_uvs()
    mesh.clear_selection()
    mesh._gpu_dirty = True


def smart_optimize(mesh: ProBuilderMesh):
    weld_vertices(mesh, threshold=0.001)
    if mesh.positions.size == 0:
        return
    pos = mesh.positions
    idx = mesh.indices.astype(np.int32)
    keep_face = np.ones(idx.shape[0], dtype=bool)
    for i in range(idx.shape[0]):
        v0, v1, v2 = pos[idx[i, 0]], pos[idx[i, 1]], pos[idx[i, 2]]
        area = np.linalg.norm(np.cross(v1 - v0, v2 - v0)) * 0.5
        if area < 1e-10:
            keep_face[i] = False
            continue
        for j in range(i + 1, idx.shape[0]):
            if (set(idx[i]) == set(idx[j])):
                keep_face[j] = False
    new_idx = idx[keep_face]
    mesh.indices = new_idx.astype(np.uint32)
    mesh.rebuild_normals()
    mesh._gpu_dirty = True
