# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, as_float


def point_of(model: StepModel, value):
    try:
        arr = np.asarray(value, dtype=np.float64).ravel()
        if arr.size >= 3 and not isinstance(value, (str, tuple, list)):
            out = np.zeros(3, dtype=np.float64)
            out[:] = arr[:3]
            return out
    except (TypeError, ValueError):
        pass
    ent = deref(model, value)
    if ent is None or not (isinstance(ent, tuple) and len(ent) == 2):
        if isinstance(ent, (list, tuple)):
            try:
                vals = [float(as_float(v)) for v in ent]
            except (TypeError, ValueError):
                return np.zeros(3, dtype=np.float64)
            out = np.zeros(3, dtype=np.float64)
            out[:min(3, len(vals))] = vals[:3]
            return out
        return np.zeros(3, dtype=np.float64)
    name, args = ent
    if name == "VERTEX_POINT" and len(args) >= 2:
        return point_of(model, args[1])
    if name != "CARTESIAN_POINT" or len(args) < 2:
        return np.zeros(3, dtype=np.float64)
    coords = args[1]
    if not isinstance(coords, (list, tuple)):
        return np.zeros(3, dtype=np.float64)
    try:
        vals = [float(as_float(v)) for v in coords]
    except (TypeError, ValueError):
        return np.zeros(3, dtype=np.float64)
    out = np.zeros(3, dtype=np.float64)
    out[:min(3, len(vals))] = vals[:3]
    return out


def direction_of(model: StepModel, value, default=None):
    ent = deref(model, value)
    vec = None
    if ent is not None and isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "DIRECTION":
        args = ent[1]
        if len(args) >= 2 and isinstance(args[1], (list, tuple)):
            try:
                vals = [float(as_float(v)) for v in args[1]]
                if len(vals) >= 3:
                    vec = np.array(vals[:3], dtype=np.float64)
            except (TypeError, ValueError):
                vec = None
    if vec is None and ent is not None and isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "VECTOR":
        args = ent[1]
        if len(args) >= 2 and args[1] is not None:
            return direction_of(model, args[1], default=default)
    if vec is None:
        vec = np.array([1.0, 0.0, 0.0] if default is None else list(default), dtype=np.float64)
    n = float(np.linalg.norm(vec))
    if n < 1e-300:
        return np.array([1.0, 0.0, 0.0], dtype=np.float64)
    return vec / n


def placement_of(model: StepModel, value):
    origin = np.zeros(3, dtype=np.float64)
    axis = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    ref = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    ent = deref(model, value)
    if ent is not None and isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "AXIS2_PLACEMENT_3D":
        args = ent[1]
        if len(args) > 1 and args[1] is not None:
            origin = point_of(model, args[1])
        if len(args) > 2 and args[2] is not None:
            axis = direction_of(model, args[2], default=[0.0, 0.0, 1.0])
        if len(args) > 3 and args[3] is not None:
            ref = direction_of(model, args[3], default=[1.0, 0.0, 0.0])
    z = axis / max(float(np.linalg.norm(axis)), 1e-300)
    x = ref - float(np.dot(ref, z)) * z
    xn = float(np.linalg.norm(x))
    if xn < 1e-12:
        x = np.array([1.0, 0.0, 0.0], dtype=np.float64) if abs(z[0]) < 0.9 else np.array([0.0, 1.0, 0.0], dtype=np.float64)
        x = x - float(np.dot(x, z)) * z
        xn = float(np.linalg.norm(x))
        if xn < 1e-12:
            x = np.array([1.0, 0.0, 0.0], dtype=np.float64)
            xn = 1.0
    x = x / xn
    y = np.cross(z, x)
    return origin, x, y, z
