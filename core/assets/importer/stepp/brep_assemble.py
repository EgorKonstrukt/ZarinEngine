# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, first_part, is_true
from core.assets.importer.stepp.brep import _shell_faces, _resolve_face, _surf_id_of, _oriented_edge_parts
from core.assets.importer.stepp.brep import _sample_ring, _pick_outer, _unwrap_ring, _iter_shells
from core.assets.importer.stepp.brep import _signed_volume
from core.assets.importer.stepp.surfaces import make_surface
from core.assets.importer.stepp.triangulate import triangulate_face
from core.assets.importer.stepp.place import point_of


def _densify_ring(model: StepModel, surf, ring: list, tol: float) -> list:
    try:
        limit = max(tol * 12.0, 1e-9)
        if len(ring) >= 2048:
            return ring
        out: list[tuple] = []
        for i, (p, uv) in enumerate(ring):
            out.append((p, uv))
            q, _quv = ring[(i + 1) % len(ring)]
            try:
                seg = float(np.linalg.norm(np.asarray(q, dtype=np.float64) - np.asarray(p, dtype=np.float64)))
            except (TypeError, ValueError):
                continue
            if seg <= limit or len(out) >= 2048:
                continue
            n = min(max(int(seg / limit), 1), 64)
            try:
                p3 = np.asarray(p, dtype=np.float64)
                q3 = np.asarray(q, dtype=np.float64)
                for k in range(1, n + 1):
                    f = float(k) / float(n + 1)
                    mid3 = p3 + (q3 - p3) * f
                    uu, vv = surf.invert(mid3[None, :])
                    out.append((np.ascontiguousarray(mid3.astype(np.float64)), (float(uu[0]), float(vv[0]))))
                    if len(out) >= 2048:
                        break
            except (TypeError, ValueError, IndexError):
                continue
        return out
    except (TypeError, ValueError, IndexError, AttributeError):
        return ring


def _tessellate_shell_entries(model: StepModel, entries) -> tuple:
    parts: list[tuple[np.ndarray, np.ndarray]] = []
    skipped = 0
    faced = 0
    for faces, closed, matrix in entries:
        shell_verts: list[np.ndarray] = []
        shell_tris: list[np.ndarray] = []
        for fref in faces:
            resolved, sense = _resolve_face(model, fref)
            if resolved is None:
                skipped += 1
                continue
            bounds, surf_ref, _ = resolved
            surf_id = _surf_id_of(model, surf_ref)
            try:
                surf = make_surface(model, surf_ref)
            except (TypeError, ValueError, IndexError, OverflowError):
                surf = None
            if surf is None:
                skipped += 1
                continue
            if not isinstance(bounds, (list, tuple)):
                skipped += 1
                continue
            loops = []
            for b in bounds:
                bname, bargs = first_part(model, b, "FACE_BOUND", "FACE_OUTER_BOUND")
                if bname is None or len(bargs) < 3:
                    continue
                try:
                    borient = is_true(bargs[2])
                except (IndexError, TypeError):
                    borient = True
                loops.append((bname, bargs[1], borient))
            if not loops:
                skipped += 1
                continue
            vert_guess = []
            for _bn, lref, _bo in loops:
                lname, largs = first_part(model, lref, "EDGE_LOOP", "ORIENTED_EDGE_LOOP", "LOOP")
                if lname is None:
                    continue
                items = largs[1] if len(largs) > 1 else largs
                if not isinstance(items, (list, tuple)):
                    items = [items]
                for oe in items:
                    tgt, _f = _oriented_edge_parts(model, oe)
                    if tgt is None:
                        continue
                    tname, targs = first_part(model, tgt, "EDGE_CURVE")
                    if tname is not None:
                        ta = targs
                        if len(ta) > 1 and ta[1] is not None:
                            vert_guess.append(point_of(model, ta[1]))
                        if len(ta) > 2 and ta[2] is not None:
                            vert_guess.append(point_of(model, ta[2]))
            diag = 1.0
            if vert_guess:
                try:
                    va = np.array(vert_guess, dtype=np.float64)
                    diag = max(float(np.linalg.norm(va.max(axis=0) - va.min(axis=0))), 1e-9)
                except (TypeError, ValueError):
                    diag = 1.0
            tol = max(diag / 500.0, 1e-9)
            rings = []
            for _bn, lref, _bo in loops:
                try:
                    ring = _sample_ring(model, lref, surf, surf_id, tol)
                except (TypeError, ValueError, IndexError, OverflowError):
                    ring = None
                if ring is not None and len(ring) >= 3:
                    rings.append((_bn, ring))
            if not rings:
                skipped += 1
                continue
            outer, holes = _pick_outer(rings)
            if outer is None:
                skipped += 1
                continue
            if holes:
                try:
                    outer = _densify_ring(model, surf, outer, tol)
                except (TypeError, ValueError, IndexError, AttributeError):
                    pass
                if len(outer) < 3:
                    skipped += 1
                    continue
            outer_uv_raw = [(p[1][0], p[1][1]) for p in outer]
            holes_uv_raw = [[(p[1][0], p[1][1]) for p in h] for h in holes]
            periods = getattr(surf, "periods", (0.0, 0.0))
            outer_uv = _unwrap_ring(outer_uv_raw, periods)
            holes_uv = [_unwrap_ring(h, periods) for h in holes_uv_raw]
            verts2d, tris2d = triangulate_face(outer_uv, holes_uv, surf, tol)
            if not tris2d:
                skipped += 1
                continue
            v3 = np.array([[float(p[0]), float(p[1])] for p in verts2d], dtype=np.float64)
            try:
                p3 = surf.eval(v3[:, 0], v3[:, 1])
            except (TypeError, ValueError, IndexError):
                skipped += 1
                continue
            nv = len(verts2d)
            if len(p3) != nv:
                skipped += 1
                continue
            base = sum(len(v) for v in shell_verts)
            shell_verts.append(np.ascontiguousarray(p3, dtype=np.float64))
            arr = np.array(tris2d, dtype=np.int64) + base
            if not sense:
                arr = arr[:, ::-1].copy()
            shell_tris.append(arr)
            faced += 1
        if shell_verts:
            v = np.vstack(shell_verts)
            t = np.vstack(shell_tris)
            if closed and _signed_volume(v, t) < 0.0:
                t = t[:, ::-1].copy()
            if matrix is not None:
                try:
                    m = np.asarray(matrix, dtype=np.float64).reshape(4, 4)
                    v = np.ascontiguousarray((v @ m[0:3, 0:3].T + m[0:3, 3]).astype(np.float64))
                except (TypeError, ValueError, IndexError):
                    pass
            parts.append((v, t))
    return parts, skipped, faced


def _shells_of_solid(model: StepModel, solid_ref) -> list:
    name, args = first_part(model, solid_ref, "MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS", "FACETED_BREP")
    if name is None:
        return []
    shells = []
    if len(args) >= 2:
        shells.append((args[1], True))
    if name == "BREP_WITH_VOIDS" and len(args) >= 3 and isinstance(args[2], (list, tuple)):
        for void in args[2]:
            shells.append((void, True))
    resolved = []
    for ref, closed in shells:
        faces = _shell_faces(model, ref)
        if faces:
            resolved.append((faces, closed))
    return resolved


def collect_brep(model: StepModel):
    entries = []
    for _sid, faces, closed in _iter_shells(model):
        entries.append((faces, closed, None))
    return _tessellate_shell_entries(model, entries)


def collect_brep_instances(model: StepModel, instances) -> tuple:
    entries = []
    for solid_ref, matrix in instances:
        for faces, closed in _shells_of_solid(model, solid_ref):
            entries.append((faces, closed, matrix))
    return _tessellate_shell_entries(model, entries)
