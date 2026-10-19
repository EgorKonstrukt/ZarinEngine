# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os

import numpy as np


STEP_EXTS = frozenset({".stp", ".step"})


def is_step_file(path: str) -> bool:
    try:
        return os.path.splitext(path or "")[1].lower() in STEP_EXTS
    except Exception:
        return False


def load_step(path: str, import_settings=None):
    from core.assets.importer.stepp.parser import parse_step_file
    from core.assets.importer.stepp.tessellated import collect_tessellated
    from core.assets.importer.stepp.brep_assemble import collect_brep
    from core.assets.importer.stepp.brep_assemble import collect_brep_instances
    from core.assets.importer.stepp.assembly import collect_assembly
    from core.assets.importer.stepp.units import length_unit_scale
    from core.assets.importer.ctypes_types import MeshImportData
    from core.assets.importer.settings import _read_mesh_import
    from core.assets.importer.settings import _compute_smooth_normals
    from core.assets.importer.settings import _generate_planar_uvs
    try:
        model = parse_step_file(path)
    except (OSError, MemoryError, ValueError):
        return None
    if model is None:
        return None
    try:
        tess_parts = collect_tessellated(model)
    except (TypeError, ValueError, IndexError, OverflowError, MemoryError):
        tess_parts = []
    try:
        brep_parts, _skipped, _faced = collect_brep(model)
    except (TypeError, ValueError, IndexError, OverflowError, MemoryError):
        brep_parts = []
    try:
        instances = collect_assembly(model)
    except (TypeError, ValueError, IndexError, AttributeError):
        instances = None
    if instances:
        try:
            inst_parts, _isk, _ifa = collect_brep_instances(model, instances)
            if inst_parts:
                brep_parts = inst_parts
        except (TypeError, ValueError, IndexError, OverflowError, MemoryError):
            pass
    try:
        unit_scale = float(length_unit_scale(model))
    except (TypeError, ValueError, IndexError, AttributeError):
        unit_scale = 1.0
    if not unit_scale or unit_scale <= 0.0:
        unit_scale = 1.0
    blobs: list[tuple[np.ndarray, np.ndarray, str]] = []
    for i, (v, t) in enumerate(tess_parts):
        blobs.append((v, t, "tess_" + str(i)))
    for i, (v, t) in enumerate(brep_parts):
        blobs.append((v, t, "shell_" + str(i)))
    blobs = [(v, t, n) for v, t, n in blobs if len(v) and len(t)]
    if not blobs:
        return None
    verts = np.vstack([np.asarray(v, dtype=np.float64).reshape(-1, 3) for v, _t, _n in blobs])
    idx_list: list[np.ndarray] = []
    ranges: list[tuple[int, int]] = []
    names: list[str] = []
    v_off = 0
    i_off = 0
    for v, t, n in blobs:
        nv = np.asarray(v, dtype=np.float64).reshape(-1, 3).shape[0]
        ti = np.asarray(t, dtype=np.int64).reshape(-1, 3) + v_off
        idx_list.append(ti)
        ranges.append((i_off, len(ti) * 3))
        names.append(n)
        v_off += nv
        i_off += len(ti) * 3
    idx = np.vstack(idx_list).reshape(-1, 3)
    uniq, inv = np.unique(verts, axis=0, return_inverse=True)
    idx = inv[idx].astype(np.uint32)
    verts = np.ascontiguousarray(uniq, dtype=np.float32)
    settings = import_settings if import_settings is not None else _read_mesh_import(path)
    try:
        scale = float(settings.get("scale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    total_scale = scale * unit_scale
    if total_scale and total_scale != 1.0:
        verts = (verts * total_scale).astype(np.float32)
    rot = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]], dtype=np.float32)
    verts = np.ascontiguousarray((verts.reshape(-1, 3) @ rot.T).astype(np.float32))
    data = MeshImportData()
    try:
        data.name = os.path.splitext(os.path.basename(path))[0]
    except Exception:
        data.name = "step"
    data.vertices = verts.ravel()
    data.indices = np.ascontiguousarray(idx.ravel())
    data.sub_mesh_ranges = ranges
    data.sub_mesh_names = names
    if settings.get("gen_normals", True):
        try:
            data.normals = np.ascontiguousarray(_compute_smooth_normals(verts.reshape(-1, 3), data.indices).ravel())
        except (TypeError, ValueError, IndexError):
            data.normals = np.zeros_like(verts).ravel()
    else:
        data.normals = np.zeros_like(verts).ravel()
    if settings.get("gen_uvs", True):
        try:
            data.uvs = np.ascontiguousarray(_generate_planar_uvs(verts.reshape(-1, 3)).ravel())
        except (TypeError, ValueError, IndexError):
            data.uvs = np.zeros((len(verts), 2), dtype=np.float32).ravel()
    else:
        data.uvs = np.zeros((len(verts), 2), dtype=np.float32).ravel()
    if len(data.vertices) == 0 or len(data.indices) == 0:
        return None
    return data
