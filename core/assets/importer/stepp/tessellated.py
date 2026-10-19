# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, entity_of, as_float, first_part, parts_of


_FACE_SET_TYPES = frozenset({
    "TRIANGULATED_FACE_SET",
    "COMPLEX_TRIANGULATED_FACE_SET",
    "TRIANGULATED_SURFACE_SET",
    "TESSELLATED_FACE_SET",
    "TRIANGULATED_FACE",
})


def _point_coords(model: StepModel, value):
    ent = deref(model, value)
    if ent is None:
        return None
    if isinstance(ent, (list, tuple)) and not (isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "ref"):
        try:
            nums = [float(as_float(v)) for v in ent]
        except (TypeError, ValueError):
            return None
        if len(nums) >= 3 and all(isinstance(v, (int, float)) for v in ent[:3]):
            return (float(nums[0]), float(nums[1]), float(nums[2]))
        return None
    if isinstance(ent, tuple) and len(ent) == 2 and ent[0] in ("CARTESIAN_POINT",):
        return None
    return None


def _cartesian_coords(model: StepModel, value):
    name, args = first_part(model, value, "CARTESIAN_POINT")
    if name is None or len(args) < 2:
        nums = None
        ent = deref(model, value)
        if isinstance(ent, (list, tuple)):
            nums = ent
        if nums is None:
            return None
        try:
            vals = [float(as_float(v)) for v in nums]
        except (TypeError, ValueError):
            return None
        if len(vals) < 3:
            return None
        return (float(vals[0]), float(vals[1]), float(vals[2]))
    coords = args[1]
    if not isinstance(coords, (list, tuple)):
        return None
    try:
        vals = [float(as_float(v)) for v in coords]
    except (TypeError, ValueError):
        return None
    if len(vals) < 3:
        return None
    return (float(vals[0]), float(vals[1]), float(vals[2]))


def _coordinates_matrix(model: StepModel, value):
    name, args = first_part(model, value, "COORDINATES_LIST")
    if name is None or len(args) < 3:
        return None
    raw = args[2]
    if not isinstance(raw, (list, tuple)):
        return None
    pts: list[tuple[float, float, float]] = []
    for item in raw:
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "ref":
            c = _cartesian_coords(model, item)
        else:
            c = _point_coords(model, item)
        if c is None:
            return None
        pts.append(c)
    if not pts:
        return None
    return np.array(pts, dtype=np.float64)


def _pnindex_matrix(value):
    if not isinstance(value, (list, tuple)):
        return None
    rows: list[tuple[int, int, int]] = []
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            return None
        try:
            rows.append((int(row[0]) - 1, int(row[1]) - 1, int(row[2]) - 1))
        except (TypeError, ValueError):
            return None
    if not rows:
        return None
    arr = np.array(rows, dtype=np.int64)
    if arr.min() < 0:
        return None
    return arr


def _extract_face_set(model: StepModel, ident: int):
    name, args = first_part(model, ("ref", ident), "TRIANGULATED_FACE", "TRIANGULATED_FACE_SET",
                            "COMPLEX_TRIANGULATED_FACE_SET", "TRIANGULATED_SURFACE_SET", "TESSELLATED_FACE_SET")
    if name is None:
        return None
    if name == "TRIANGULATED_FACE" or name == "TRIANGULATED_FACE_SET":
        if len(args) < 5:
            return None
        mat = _coordinates_matrix(model, args[1])
        idx = _pnindex_matrix(args[4])
        if mat is None or idx is None:
            return None
        if idx.max() >= len(mat):
            return None
        return mat, idx
    if name in ("COMPLEX_TRIANGULATED_FACE_SET", "TRIANGULATED_SURFACE_SET", "TESSELLATED_FACE_SET"):
        if len(args) < 2:
            return None
        members = args[1]
        if not isinstance(members, (list, tuple)):
            return None
        mats: list[np.ndarray] = []
        idxs: list[np.ndarray] = []
        for m in members:
            sub = deref(model, m)
            if sub is None or not (isinstance(sub, tuple) and len(sub) == 2):
                continue
            _sn, _sa = sub
            if _sn not in ("TRIANGULATED_FACE", "TRIANGULATED_FACE_SET") or len(_sa) < 5:
                continue
            mat = _coordinates_matrix(model, _sa[1])
            idx = _pnindex_matrix(_sa[4])
            if mat is None or idx is None or idx.max() >= len(mat):
                continue
            off = sum(len(x) for x in mats)
            mats.append(mat)
            idxs.append(idx + off)
        if not mats:
            return None
        return np.vstack(mats), np.vstack(idxs)
    return None


def collect_tessellated(model: StepModel):
    parts: list[tuple[np.ndarray, np.ndarray]] = []
    for ident, ent in model.entities.items():
        hit = False
        for pn, _pa in parts_of(ent):
            if pn in _FACE_SET_TYPES:
                hit = True
                break
        if not hit:
            continue
        try:
            got = _extract_face_set(model, ident)
        except (TypeError, ValueError, IndexError, OverflowError):
            got = None
        if got is None:
            continue
        mat, idx = got
        if len(mat) and len(idx):
            parts.append((np.ascontiguousarray(mat, dtype=np.float64), np.ascontiguousarray(idx, dtype=np.int64)))
    return parts
