# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, is_true, first_part, parts_of
from core.assets.importer.stepp.curves import sample_edge_3d
from core.assets.importer.stepp.curves2d import sample_pcurve
from core.assets.importer.stepp.triangulate import signed_area
from core.assets.importer.stepp.place import point_of


def _shell_faces(model: StepModel, shell_ref) -> list:
    name, args = first_part(model, shell_ref, "ORIENTED_CLOSED_SHELL", "CLOSED_SHELL",
                            "OPEN_SHELL", "CONNECTED_FACE_SET")
    if name is None:
        return []
    if name == "ORIENTED_CLOSED_SHELL" and len(args) >= 3 and args[2] is not None:
        return _shell_faces(model, args[2])
    faces = args[1] if len(args) > 1 else None
    if isinstance(faces, (list, tuple)):
        return list(faces)
    return []


def _iter_shells(model: StepModel):
    shells: list[tuple] = []
    seen: set[int] = set()

    def _solids():
        for ident, ent in model.entities.items():
            for name, args in parts_of(ent):
                if name in ("MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS", "FACETED_BREP",
                            "SHELL_BASED_SURFACE_MODEL", "MANIFOLD_SURFACE_SHAPE_REPRESENTATION"):
                    yield ident, name, args

    for ident, name, args in _solids():
        if name == "MANIFOLD_SOLID_BREP" and len(args) >= 2:
            shells.append((ident, args[1], True))
        elif name == "BREP_WITH_VOIDS" and len(args) >= 3:
            shells.append((ident, args[1], True))
            voids = args[2]
            if isinstance(voids, (list, tuple)):
                for v in voids:
                    shells.append((ident, v, True))
        elif name == "FACETED_BREP" and len(args) >= 2:
            shells.append((ident, args[1], True))
        elif name == "SHELL_BASED_SURFACE_MODEL" and len(args) >= 2:
            subs = args[1]
            if isinstance(subs, (list, tuple)):
                for s in subs:
                    shells.append((ident, s, False))
    out = []
    for _ident, ref, closed in shells:
        ent = deref(model, ref)
        sid = ref[1] if isinstance(ref, tuple) and len(ref) == 2 and ref[0] == "ref" else -1
        if sid in seen:
            continue
        seen.add(sid)
        faces = _shell_faces(model, ref)
        if faces:
            out.append((sid, faces, closed))
    standalone = []
    for ident, ent in model.entities.items():
        for name, args in parts_of(ent):
            if name in ("CLOSED_SHELL", "OPEN_SHELL") and ident not in seen and len(args) >= 2:
                faces = args[1]
                if isinstance(faces, (list, tuple)) and faces:
                    standalone.append((ident, list(faces), name == "CLOSED_SHELL"))
                    seen.add(ident)
    out.extend(standalone)
    return out


def _resolve_face(model: StepModel, face_ref):
    name, args = first_part(model, face_ref, "ORIENTED_FACE", "ADVANCED_FACE", "FACE_SURFACE", "FACE")
    if name is None:
        return None, True
    if name == "ORIENTED_FACE" and len(args) >= 3:
        inner, sense = _resolve_face(model, args[2])
        if inner is None:
            return None, True
        try:
            flip = not is_true(args[1] if len(args) > 1 else None)
        except (IndexError, TypeError):
            flip = False
        return inner, (not sense) if flip else sense
    if name in ("ADVANCED_FACE", "FACE_SURFACE", "FACE") and len(args) >= 4:
        try:
            sense = is_true(args[3])
        except (IndexError, TypeError):
            sense = True
        return (args[1], args[2], face_ref), sense
    return None, True


def _surf_id_of(model: StepModel, surf_ref) -> int:
    try:
        if isinstance(surf_ref, tuple) and len(surf_ref) == 2 and surf_ref[0] == "ref":
            return int(surf_ref[1])
    except (TypeError, ValueError):
        pass
    return -1


def _edge_pcurve_for(model: StepModel, edge_curve_ref, surf_id: int):
    name, args = first_part(model, edge_curve_ref, "EDGE_CURVE")
    if name is None or len(args) < 4:
        return None
    gname, gargs = first_part(model, args[3], "PCURVE", "SURFACE_CURVE", "SEAM_CURVE")
    if gname is None:
        return None
    if gname == "PCURVE":
        return args[3]
    if len(gargs) < 3:
        return None
    assoc = gargs[2]
    if not isinstance(assoc, (list, tuple)):
        return None
    for pc in assoc:
        pname, pargs = first_part(model, pc, "PCURVE")
        if pname is None:
            continue
        if len(pargs) >= 2 and _surf_id_of(model, pargs[1]) == surf_id:
            return pc
    return None


def _oriented_edge_parts(model: StepModel, oe_ref):
    name, args = first_part(model, oe_ref, "ORIENTED_EDGE", "EDGE_CURVE", "VERTEX_POINT")
    if name is None:
        return None, True
    if name == "ORIENTED_EDGE" and len(args) >= 2:
        elem = None
        for a in args[1:]:
            if isinstance(a, tuple) and len(a) == 2 and a[0] == "ref":
                elem = a
                break
        fwd = True
        for a in args[1:]:
            if isinstance(a, tuple) and len(a) == 2 and a[0] == "enum":
                tag = str(a[1]).upper()
                if tag in ("T", "TRUE", "F", "FALSE"):
                    fwd = tag in ("T", "TRUE")
        inner = elem
        iname, _iargs = first_part(model, inner, "ORIENTED_EDGE")
        if iname is not None:
            sub, sub_fwd = _oriented_edge_parts(model, inner)
            return sub, (fwd and sub_fwd) or ((not fwd) and (not sub_fwd))
        return inner, fwd
    if name == "EDGE_CURVE":
        return oe_ref, True
    if name == "VERTEX_POINT":
        return oe_ref, True
    return None, True


def _sample_ring(model: StepModel, loop_ref, surf, surf_id: int, tol: float):
    name, args = first_part(model, loop_ref, "VERTEX_LOOP", "EDGE_LOOP", "ORIENTED_EDGE_LOOP", "LOOP")
    if name is None:
        return None
    if name == "VERTEX_LOOP" and len(args) >= 2:
        p = point_of(model, args[1])
        u, v = surf.invert(p[None, :])
        return [(np.array([float(p[0]), float(p[1]), float(p[2])]), (float(u[0]), float(v[0])))]
    if name not in ("EDGE_LOOP", "ORIENTED_EDGE_LOOP", "LOOP") or len(args) < 2:
        return None
    edges = args[1]
    if not isinstance(edges, (list, tuple)) or not edges:
        return None
    pieces: list[tuple[list, list, bool]] = []
    for oe in edges:
        target, fwd = _oriented_edge_parts(model, oe)
        if target is None:
            return None
        tname, _targs = first_part(model, target, "VERTEX_POINT")
        if tname is not None:
            p = point_of(model, target)
            u, v = surf.invert(p[None, :])
            pieces.append(([(float(p[0]), float(p[1]), float(p[2]))], [(float(u[0]), float(v[0]))], False))
            continue
        pc = _edge_pcurve_for(model, target, surf_id)
        pts3 = None
        uvs = None
        if pc is not None:
            try:
                pud, _bid = sample_pcurve(model, pc, tol)
                if pud is not None and len(pud) >= 2:
                    uvs = [(float(p[0]), float(p[1])) for p in pud]
                    pts3 = surf.eval(np.array([p[0] for p in uvs]), np.array([p[1] for p in uvs]))
            except (TypeError, ValueError, IndexError):
                pts3 = None
        if pts3 is None:
            try:
                pts3 = sample_edge_3d(model, target, tol)
            except (TypeError, ValueError, IndexError):
                pts3 = None
            if pts3 is None or len(pts3) < 2:
                return None
            try:
                uu, vv = surf.invert(pts3)
                uvs = [(float(a), float(b)) for a, b in zip(uu, vv)]
            except (TypeError, ValueError, IndexError):
                return None
        if not fwd:
            pts3 = pts3[::-1].copy()
            uvs = uvs[::-1]
        p3 = [(float(q[0]), float(q[1]), float(q[2])) for q in pts3]
        closed = bool(np.allclose(np.array(p3[0]), np.array(p3[-1]), atol=max(tol * 10.0, 1e-9)))
        pieces.append((p3, list(uvs), closed))
    order = _pick_closed_directions(pieces, surf)
    ring: list[tuple] = []
    for k, rev in enumerate(order):
        p3, uvs, _closed = pieces[k]
        if rev:
            p3 = p3[::-1]
            uvs = uvs[::-1]
        start = 0
        if ring:
            start = 1
        for j in range(start, len(p3) - 1):
            ring.append((np.array([float(p3[j][0]), float(p3[j][1]), float(p3[j][2])]), uvs[j]))
        ring.append((np.array([float(p3[-1][0]), float(p3[-1][1]), float(p3[-1][2])]), uvs[-1]))
    if len(ring) < 3:
        return None
    try:
        if float(np.linalg.norm(ring[0][0] - ring[-1][0])) <= max(tol * 0.01, 1e-9):
            ring.pop()
    except (TypeError, ValueError, IndexError):
        pass
    return ring


def _pieces_drift(pieces, order, periods) -> float:
    seq: list[tuple[float, float]] = []
    for k, rev in enumerate(order):
        _p3, uvs, _closed = pieces[k]
        seq.extend(uvs[::-1] if rev else uvs)
    if len(seq) < 2:
        return 0.0
    w = _unwrap_ring([(float(p[0]), float(p[1])) for p in seq], periods)
    if len(w) < 2:
        return 0.0
    du = w[-1][0] - w[0][0]
    dv = w[-1][1] - w[0][1]
    pu, pv = periods
    score = 0.0
    if pu:
        score += abs(du / pu)
    else:
        score += min(abs(du), 1.0) * 8.0
    if pv:
        score += abs(dv / pv)
    else:
        score += min(abs(dv), 1.0) * 8.0
    return score


def _pick_closed_directions(pieces, surf) -> list:
    closed_idx = [i for i, (_p3, uvs, closed) in enumerate(pieces) if closed and len(uvs) >= 2]
    order = [False] * len(pieces)
    if not closed_idx:
        return order
    try:
        periods = getattr(surf, "periods", (0.0, 0.0))
    except (TypeError, ValueError):
        periods = (0.0, 0.0)
    if len(closed_idx) > 8:
        closed_idx = closed_idx[:8]
    best = list(order)
    best_score = _pieces_drift(pieces, best, periods) + 0.0
    n = len(closed_idx)
    for mask in range(1, 1 << n):
        cand = list(order)
        flips = 0
        for j in range(n):
            if mask & (1 << j):
                cand[closed_idx[j]] = True
                flips += 1
        score = _pieces_drift(pieces, cand, periods) + flips * 1e-6
        if score < best_score - 1e-9:
            best_score = score
            best = cand
    return best


def _unwrap_ring(uvs: list, periods) -> list:
    pu, pv = periods
    out = [uvs[0]]
    for p in uvs[1:]:
        u, v = p
        pu0, pv0 = out[-1]
        if pu:
            du = u - pu0
            u = u - pu * round(du / pu)
        if pv:
            dv = v - pv0
            v = v - pv * round(dv / pv)
        out.append((u, v))
    return out


def _signed_volume(verts: np.ndarray, tris: np.ndarray) -> float:
    try:
        t = verts[tris]
        return float(np.sum(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2]))) / 6.0)
    except (TypeError, ValueError, IndexError):
        return 0.0


def _point_in_ring(px: float, py: float, ring) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > py) != (yj > py):
            try:
                xint = (xj - xi) * (py - yi) / (yj - yi) + xi
            except ZeroDivisionError:
                xint = xi
            if px < xint:
                inside = not inside
        j = i
    return inside


def _pick_outer(rings) -> tuple:
    if not rings:
        return None, []
    explicit = [r for b, r in rings if b == "FACE_OUTER_BOUND"]
    rest = [r for b, r in rings if b != "FACE_OUTER_BOUND"]
    if len(explicit) == 1 and rest:
        return explicit[0], rest
    cands = [r for _b, r in rings]
    scored = []
    for i, ri in enumerate(cands):
        try:
            area = abs(signed_area([(p[1][0], p[1][1]) for p in ri]))
        except (TypeError, ValueError, IndexError):
            area = 0.0
        scored.append((area, i))
    scored.sort()
    for _area, i in reversed(scored):
        try:
            uv_i = [(p[1][0], p[1][1]) for p in cands[i]]
        except (TypeError, ValueError, IndexError):
            continue
        ok = True
        for j, rj in enumerate(cands):
            if i == j:
                continue
            try:
                px, py = rj[0][1][0], rj[0][1][1]
                if not _point_in_ring(px, py, uv_i):
                    ok = False
                    break
            except (TypeError, ValueError, IndexError):
                ok = False
                break
        if ok:
            return cands[i], [cands[j] for j in range(len(cands)) if j != i]
    outer = cands[scored[-1][1]]
    holes = [cands[j] for _a, j in scored[:-1]]
    return outer, holes
