# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, parts_of, first_part
from core.assets.importer.stepp.units import placement_matrix


def _placement_inverse(m: np.ndarray):
    try:
        r = np.asarray(m, dtype=np.float64).reshape(4, 4)
        out = np.eye(4, dtype=np.float64)
        rt = r[0:3, 0:3].T.copy()
        out[0:3, 0:3] = rt
        out[0:3, 3] = -rt @ r[0:3, 3]
        return out
    except (TypeError, ValueError, IndexError):
        return np.eye(4, dtype=np.float64)


def _shape_items(model: StepModel, shape_ref) -> list:
    name, args = first_part(model, shape_ref, "SHAPE_REPRESENTATION", "ADVANCED_BREP_SHAPE_REPRESENTATION",
                            "MANIFOLD_SURFACE_SHAPE_REPRESENTATION", "GEOMETRICALLY_BOUNDED_SURFACE_SHAPE_REPRESENTATION",
                            "GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION")
    if name is not None and len(args) >= 2 and isinstance(args[1], (list, tuple)):
        return list(args[1])
    name2, args2 = first_part(model, shape_ref, "SHAPE_DEFINITION_REPRESENTATION")
    if name2 is not None and len(args2) >= 2:
        return _shape_items(model, args2[1])
    return []
    return []


def _pds_for_part(model: StepModel, part_pdef_id: int):
    for ident, ent in model.entities.items():
        for pn, pa in parts_of(ent):
            if pn == "PRODUCT_DEFINITION_SHAPE" and len(pa) >= 3:
                try:
                    if isinstance(pa[2], tuple) and pa[2][0] == "ref" and int(pa[2][1]) == int(part_pdef_id):
                        return ident, pa
                except (TypeError, ValueError, IndexError):
                    continue
    return None, None


def _srep_for_pds(model: StepModel, pds_ident) -> list:
    if pds_ident is None:
        return []
    out = []
    for _ident, ent in model.entities.items():
        for pn, pa in parts_of(ent):
            if pn != "SHAPE_DEFINITION_REPRESENTATION" or len(pa) < 2:
                continue
            try:
                if isinstance(pa[0], tuple) and pa[0][0] == "ref" and int(pa[0][1]) == int(pds_ident):
                    out.append(pa[1])
            except (TypeError, ValueError, IndexError):
                continue
    return out


def _expand_mapped(model: StepModel, mapped_item_ref, outer) -> list:
    name, args = first_part(model, mapped_item_ref, "MAPPED_ITEM")
    if name is None or len(args) < 3:
        return []
    rname, rargs = first_part(model, args[1], "REPRESENTATION_MAP")
    if rname is None or len(rargs) < 3:
        return []
    try:
        m_origin = placement_matrix(model, rargs[1])
        m_target = placement_matrix(model, args[2])
        total = np.asarray(outer, dtype=np.float64).reshape(4, 4) @ m_target @ _placement_inverse(m_origin)
    except (TypeError, ValueError, IndexError):
        total = np.asarray(outer, dtype=np.float64).reshape(4, 4)
    out = []
    for item in _shape_items(model, rargs[2]):
        iname, _iargs = first_part(model, item, "MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS",
                                   "FACETED_BREP", "MAPPED_ITEM")
        if iname is None:
            continue
        if iname == "MAPPED_ITEM":
            out.extend(_expand_mapped(model, item, total))
        else:
            out.append((item, total))
    return out


def _solids_of_rep(model: StepModel, shape_ref, outer) -> list:
    out = []
    for item in _shape_items(model, shape_ref):
        iname, _iargs = first_part(model, item, "MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS",
                                   "FACETED_BREP", "MAPPED_ITEM")
        if iname is None:
            continue
        if iname == "MAPPED_ITEM":
            out.extend(_expand_mapped(model, item, outer))
        else:
            out.append((item, np.asarray(outer, dtype=np.float64).reshape(4, 4)))
    return out


def _transform_from_rep(model: StepModel, rep_ref):
    name, args = first_part(model, rep_ref, "ITEM_DEFINED_TRANSFORMATION")
    if name is not None and len(args) >= 4:
        try:
            m1 = placement_matrix(model, args[2])
            m2 = placement_matrix(model, args[3])
            return m2 @ _placement_inverse(m1)
        except (TypeError, ValueError, IndexError):
            return np.eye(4, dtype=np.float64)
    wname, wargs = first_part(model, rep_ref, "REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION")
    if wname is not None and len(wargs) >= 1:
        inner = wargs[0]
        if isinstance(inner, list):
            if not inner:
                return None
            inner = inner[0]
        return _transform_from_rep(model, inner)
    return None


def _nau_transform(model: StepModel, nau_ident: int):
    for _ident, ent in model.entities.items():
        for pn, pa in parts_of(ent):
            if pn != "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION" or len(pa) < 2:
                continue
            hit = False
            try:
                tgt = pa[1]
                if isinstance(tgt, tuple) and tgt[0] == "ref" and int(tgt[1]) == int(nau_ident):
                    hit = True
                else:
                    iname, iargs = first_part(model, tgt, "PRODUCT_DEFINITION_SHAPE")
                    if iname is not None and len(iargs) >= 3:
                        defn = iargs[2]
                        if isinstance(defn, tuple) and defn[0] == "ref" and int(defn[1]) == int(nau_ident):
                            hit = True
            except (TypeError, ValueError, IndexError):
                hit = False
            if not hit:
                continue
            mat = _transform_from_rep(model, pa[0])
            if mat is not None:
                return mat
    return None


def collect_assembly(model: StepModel):
    naus = []
    for ident, ent in model.entities.items():
        for pn, pa in parts_of(ent):
            if pn == "NEXT_ASSEMBLY_USAGE_OCCURRENCE" and len(pa) >= 5:
                naus.append((ident, pa))
    if not naus:
        reps = []
        for ident, ent in model.entities.items():
            for pn, pa in parts_of(ent):
                if pn == "SHAPE_REPRESENTATION" and len(pa) >= 2 and isinstance(pa[1], (list, tuple)):
                    reps.append((ident, pa))
        out = []
        for _ident, pa in reps:
            for item in pa[1]:
                iname, _iargs = first_part(model, item, "MAPPED_ITEM")
                if iname is not None:
                    out.extend(_expand_mapped(model, item, np.eye(4, dtype=np.float64)))
        return out if out else None
    out = []
    for ident, pa in naus:
        try:
            part_ref = pa[4]
            part_id = int(part_ref[1]) if isinstance(part_ref, tuple) and part_ref[0] == "ref" else -1
        except (TypeError, ValueError, IndexError):
            continue
        mat = _nau_transform(model, ident)
        if mat is None:
            mat = np.eye(4, dtype=np.float64)
        pds_ident, _pds = _pds_for_part(model, part_id)
        for srep in _srep_for_pds(model, pds_ident):
            out.extend(_solids_of_rep(model, srep, mat))
    if not out:
        return None
    return out
