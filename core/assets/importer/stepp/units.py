# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, as_float, parts_of


def _si_scale(name: str, prefix) -> float:
    tag = str(name or "").upper()
    mult = 1.0
    if prefix is not None:
        ptag = str(prefix).upper()
        if ptag in ("MILLI", ".MILLI."):
            mult = 0.001
        elif ptag in ("CENTI", ".CENTI."):
            mult = 0.01
        elif ptag in ("MICRO", ".MICRO."):
            mult = 1e-6
        elif ptag in ("KILO", ".KILO."):
            mult = 1000.0
    if ".METRE." in tag or tag == "METRE" or tag == "METER":
        return 1000.0 * mult
    if ".METRE" in tag or "METRE" in tag or "METER" in tag:
        return 1000.0 * mult
    return 1.0


def _unit_scale_of(model: StepModel, unit_ref) -> float:
    ent = deref(model, unit_ref)
    length_part = None
    conv_part = None
    si_part = None
    for pn, pa in parts_of(ent):
        if pn == "LENGTH_UNIT":
            length_part = pa
        elif pn == "CONVERSION_BASED_UNIT":
            conv_part = pa
        elif pn == "SI_UNIT":
            si_part = pa
    if length_part is None and conv_part is None:
        return 1.0
    if conv_part is not None and len(conv_part) >= 2:
        factor_ref = conv_part[1]
        fent = deref(model, factor_ref)
        for fn, fa in parts_of(fent):
            if fn == "LENGTH_MEASURE_WITH_UNIT" and len(fa) >= 2:
                try:
                    value = float(as_float(fa[0]))
                except (TypeError, ValueError):
                    value = 1.0
                return value * _unit_scale_of(model, fa[1])
        return 1.0
    if si_part is not None and len(si_part) >= 2:
        prefix = None
        try:
            if isinstance(si_part[0], tuple) and si_part[0][0] == "enum":
                prefix = si_part[0][1]
        except (IndexError, TypeError):
            prefix = None
        return _si_scale(si_part[1] if len(si_part) > 1 else "", prefix)
    if length_part is not None:
        return 1.0
    return 1.0


def _representation_contexts(model: StepModel):
    for _ident, ent in model.entities.items():
        for pn, pa in parts_of(ent):
            if pn == "GEOMETRIC_REPRESENTATION_CONTEXT" and len(pa) >= 3 and isinstance(pa[2], (list, tuple)):
                yield pa
    for _ident, ent in model.entities.items():
        for pn, pa in parts_of(ent):
            if pn == "GLOBAL_UNIT_ASSIGNED_CONTEXT" and isinstance(pa, (list, tuple)) and len(pa) >= 1 and isinstance(pa[0], (list, tuple)):
                yield [None, None, pa[0]]


def length_unit_scale(model: StepModel) -> float:
    try:
        for ctx in _representation_contexts(model):
            units = ctx[2]
            if not isinstance(units, (list, tuple)):
                continue
            for u in units:
                try:
                    scale = _unit_scale_of(model, u)
                except (TypeError, ValueError, IndexError, AttributeError):
                    continue
                if abs(scale - 1.0) > 1e-12:
                    return float(scale)
        return 1.0
    except (TypeError, ValueError, IndexError, AttributeError):
        return 1.0


def placement_matrix(model: StepModel, placement_ref):
    from core.assets.importer.stepp.place import placement_of
    try:
        o, x, y, z = placement_of(model, placement_ref)
        m = np.eye(4, dtype=np.float64)
        m[0:3, 0] = np.asarray(x, dtype=np.float64).ravel()[:3]
        m[0:3, 1] = np.asarray(y, dtype=np.float64).ravel()[:3]
        m[0:3, 2] = np.asarray(z, dtype=np.float64).ravel()[:3]
        m[0:3, 3] = np.asarray(o, dtype=np.float64).ravel()[:3]
        return m
    except (TypeError, ValueError, IndexError):
        return np.eye(4, dtype=np.float64)
