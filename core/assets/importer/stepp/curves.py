# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import math
import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, as_float, is_true, first_part
from core.assets.importer.stepp.place import point_of, direction_of


def _curve_knots(args: list, degree: int, count: int):
    for a in args:
        if not isinstance(a, (list, tuple)) or len(a) == 0:
            continue
        if isinstance(a[0], (list, tuple)):
            continue
        if isinstance(a, tuple) and len(a) == 2 and a[0] in ("ref", "typed", "enum", "name", "omit"):
            continue
        nums: list[float] = []
        ok = True
        for v in a:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                ok = False
                break
            nums.append(float(v))
        if not ok or len(nums) < 2:
            continue
        ints = None
        try:
            ints = [int(v) for v in nums]
        except (TypeError, ValueError):
            ints = None
        if ints is not None and all(float(x) == y for x, y in zip(ints, nums)) and sum(ints) == count + degree + 1:
            knots = None
            for b in args:
                if b is a or not isinstance(b, (list, tuple)) or len(b) == 0:
                    continue
                if isinstance(b, tuple) and len(b) == 2 and b[0] in ("ref", "typed", "enum", "name", "omit"):
                    continue
                kn: list[float] = []
                okk = True
                for v in b:
                    if isinstance(v, bool) or not isinstance(v, (int, float)):
                        okk = False
                        break
                    kn.append(float(v))
                if okk and len(kn) == len(ints):
                    knots = kn
                    break
            if knots is not None:
                from core.assets.importer.stepp.nurbs import expand_knots
                full = expand_knots(ints, knots, degree, count)
                if full is not None:
                    return full
    from core.assets.importer.stepp.nurbs import uniform_knots
    return uniform_knots(count, degree)


def _curve_weights(args: list, count: int):
    for a in args:
        if not isinstance(a, (list, tuple)) or len(a) == 0:
            continue
        if isinstance(a[0], (list, tuple)):
            continue
        nums: list[float] = []
        ok = True
        for v in a:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                ok = False
                break
            nums.append(float(v))
        if ok and len(nums) == count:
            return np.array(nums, dtype=np.float64)
    return None


def _bspline_cps(model: StepModel, value, dim: int):
    ent = deref(model, value)
    if not isinstance(ent, (list, tuple)):
        return None
    pts = []
    for item in ent:
        p = point_of(model, item)
        pts.append(p[:dim])
    if not pts:
        return None
    try:
        return np.array(pts, dtype=np.float64)
    except (TypeError, ValueError):
        return None


def eval_bspline_curve(model: StepModel, args: list, ts: np.ndarray):
    try:
        if len(args) < 2:
            return None
        from core.assets.importer.stepp.nurbs import nurbs_eval_curve
        degree = int(as_float(args[1]))
        cps = _bspline_cps(model, args[2], 3)
        if cps is None:
            return None
        ku = _curve_knots(args, degree, cps.shape[0])
        w = _curve_weights(args, cps.shape[0])
        return nurbs_eval_curve(cps, ku, degree, ts, w)
    except (TypeError, ValueError, IndexError):
        return None


def _eval_circle_3d(model: StepModel, args: list, ts: np.ndarray):
    try:
        from core.assets.importer.stepp.place import placement_of
        o, x, y, _z = placement_of(model, args[1])
        r = float(as_float(args[2], 1.0))
        t = np.asarray(ts, dtype=np.float64).ravel()
        return o[None, :] + r * (np.cos(t)[:, None] * x[None, :] + np.sin(t)[:, None] * y[None, :])
    except (TypeError, ValueError, IndexError):
        return None


def _eval_ellipse_3d(model: StepModel, args: list, ts: np.ndarray):
    try:
        from core.assets.importer.stepp.place import placement_of
        o, x, y, _z = placement_of(model, args[1])
        r1 = float(as_float(args[2], 1.0))
        r2 = float(as_float(args[3], 1.0))
        t = np.asarray(ts, dtype=np.float64).ravel()
        return o[None, :] + (r1 * np.cos(t))[:, None] * x[None, :] + (r2 * np.sin(t))[:, None] * y[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _eval_line_3d(model: StepModel, args: list, ts: np.ndarray):
    try:
        p = point_of(model, args[1])
        d = direction_of(model, args[2], default=[1.0, 0.0, 0.0])
        t = np.asarray(ts, dtype=np.float64).ravel()
        return p[None, :] + t[:, None] * d[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _eval_hyperbola_3d(model: StepModel, args: list, ts: np.ndarray):
    try:
        from core.assets.importer.stepp.place import placement_of
        o, x, y, _z = placement_of(model, args[1])
        a = float(as_float(args[2], 1.0)) if len(args) > 2 else 1.0
        b = float(as_float(args[3], a)) if len(args) > 3 else abs(a)
        a = a if abs(a) > 1e-300 else 1.0
        b = b if abs(b) > 1e-300 else abs(a)
        t = np.asarray(ts, dtype=np.float64).ravel()
        return o[None, :] + (a * np.cosh(t))[:, None] * x[None, :] + (b * np.sinh(t))[:, None] * y[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _eval_parabola_3d(model: StepModel, args: list, ts: np.ndarray):
    try:
        from core.assets.importer.stepp.place import placement_of
        o, x, y, _z = placement_of(model, args[1])
        f = float(as_float(args[2], 1.0))
        f = f if abs(f) > 1e-300 else 1.0
        t = np.asarray(ts, dtype=np.float64).ravel()
        return o[None, :] + ((t * t) / (4.0 * f))[:, None] * x[None, :] + t[:, None] * y[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _wrap_circle_range(a0: float, a1: float) -> tuple:
    two_pi = 2.0 * math.pi
    span = (a1 - a0) % two_pi
    if span < 1e-9:
        span = two_pi
    return a0, a0 + span


def _trim_params_3d(model: StepModel, geom_name: str, geom_args: list, trim1, trim2, master: str):
    if master == "PARAMETER":
        try:
            return float(as_float(trim1)), float(as_float(trim2))
        except (TypeError, ValueError):
            return None
    p1 = point_of(model, trim1)
    p2 = point_of(model, trim2)
    if geom_name == "LINE":
        try:
            p0 = point_of(model, geom_args[1])
            d = direction_of(model, geom_args[2], default=[1.0, 0.0, 0.0])
            return float(np.dot(p1 - p0, d)), float(np.dot(p2 - p0, d))
        except (TypeError, ValueError, IndexError):
            return None
    if geom_name in ("CIRCLE", "ELLIPSE"):
        try:
            from core.assets.importer.stepp.place import placement_of
            o, x, y, _z = placement_of(model, geom_args[1])
            r1 = float(as_float(geom_args[2], 1.0)) if len(geom_args) > 2 else 1.0
            r2 = float(as_float(geom_args[3], r1)) if len(geom_args) > 3 else abs(r1)
            r1 = r1 if abs(r1) > 1e-300 else 1.0
            r2 = r2 if abs(r2) > 1e-300 else abs(r1)
            a1 = float(np.arctan2(float(np.dot(p1 - o, y)) / r2, float(np.dot(p1 - o, x)) / r1))
            a2 = float(np.arctan2(float(np.dot(p2 - o, y)) / r2, float(np.dot(p2 - o, x)) / r1))
            if abs(a2 - a1) < 1e-9 and float(np.linalg.norm(np.asarray(p1).ravel() - np.asarray(p2).ravel())) < 1e-9:
                return a1, a1 + 2.0 * math.pi
            return _wrap_circle_range(a1, a2)
        except (TypeError, ValueError, IndexError):
            return None
    if geom_name == "HYPERBOLA":
        try:
            from core.assets.importer.stepp.place import placement_of
            o, x, y, _z = placement_of(model, geom_args[1])
            a = float(as_float(geom_args[2], 1.0)) if len(geom_args) > 2 else 1.0
            b = float(as_float(geom_args[3], a)) if len(geom_args) > 3 else abs(a)
            a = a if abs(a) > 1e-300 else 1.0
            b = b if abs(b) > 1e-300 else abs(a)
            e1 = np.asarray(p1, dtype=np.float64).ravel() - o
            e2 = np.asarray(p2, dtype=np.float64).ravel() - o
            t1 = float(np.arcsinh(np.dot(e1, y) / b))
            t2 = float(np.arcsinh(np.dot(e2, y) / b))
            return t1, t2
        except (TypeError, ValueError, IndexError):
            return None
    if geom_name == "PARABOLA":
        try:
            from core.assets.importer.stepp.place import placement_of
            o, _x, y, _z = placement_of(model, geom_args[1])
            d1 = np.asarray(p1, dtype=np.float64).ravel() - o
            d2 = np.asarray(p2, dtype=np.float64).ravel() - o
            return float(np.dot(d1, y)), float(np.dot(d2, y))
        except (TypeError, ValueError, IndexError):
            return None
    if geom_name in ("B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE",
                      "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE", "BEZIER_CURVE"):
        try:
            from core.assets.importer.stepp.nurbs import nurbs_eval_curve
            degree = int(as_float(geom_args[1])) if len(geom_args) > 1 else 3
            cps = _bspline_cps(model, geom_args[2], 3) if len(geom_args) > 2 else None
            if cps is None:
                return None
            ku = _curve_knots(geom_args, degree, cps.shape[0])
            w = _curve_weights(geom_args, cps.shape[0])
            ts = np.linspace(float(ku[degree]), float(ku[len(ku) - degree - 1]), 65)
            pts = nurbs_eval_curve(cps, ku, degree, ts, w)
            if pts is None:
                return None
            d1 = np.sum((pts - p1[None, :]) ** 2, axis=1)
            d2 = np.sum((pts - p2[None, :]) ** 2, axis=1)
            return float(ts[int(np.argmin(d1))]), float(ts[int(np.argmin(d2))])
        except (TypeError, ValueError, IndexError):
            return None
    return None


def _sample_geom_3d(model: StepModel, geom, t0: float, t1: float, tol: float):
    name, args = first_part(model, geom, "LINE", "CIRCLE", "ELLIPSE", "HYPERBOLA", "PARABOLA",
                            "B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE",
                            "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE", "BEZIER_CURVE", "POLYLINE")
    if name is None:
        return None
    span = abs(float(t1) - float(t0))
    if name == "LINE":
        pts = _eval_line_3d(model, args, np.array([t0, t1]))
        return pts
    if name == "CIRCLE":
        length = span * float(as_float(args[2], 1.0)) if len(args) > 2 else span
        n = int(np.clip(np.ceil(length / max(tol, 1e-12)) + 1, 3, 257))
        pts = _eval_circle_3d(model, args, np.linspace(t0, t1, n))
        return pts
    if name == "ELLIPSE":
        r = max(float(as_float(args[2], 1.0)) if len(args) > 2 else 1.0, float(as_float(args[3], 1.0)) if len(args) > 3 else 1.0)
        n = int(np.clip(np.ceil(span * r / max(tol, 1e-12)) + 1, 3, 257))
        return _eval_ellipse_3d(model, args, np.linspace(t0, t1, n))
    if name in ("HYPERBOLA", "PARABOLA"):
        n = 65
        if name == "HYPERBOLA":
            pts = _eval_hyperbola_3d(model, args, np.linspace(t0, t1, n))
        else:
            pts = _eval_parabola_3d(model, args, np.linspace(t0, t1, n))
        if pts is None:
            return None
        seg = np.linalg.norm(pts[1:] - pts[:-1], axis=1)
        length = float(seg.sum())
        n2 = int(np.clip(np.ceil(length / max(tol, 1e-12)) + 1, 4, 513))
        if n2 == n:
            return pts
        if name == "HYPERBOLA":
            return _eval_hyperbola_3d(model, args, np.linspace(t0, t1, n2))
        return _eval_parabola_3d(model, args, np.linspace(t0, t1, n2))
    if name in ("B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE",
                "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE", "BEZIER_CURVE"):
        n = 65
        ts = np.linspace(t0, t1, n)
        pts = eval_bspline_curve(model, args, ts)
        if pts is None:
            return None
        seg = np.linalg.norm(pts[1:] - pts[:-1], axis=1)
        length = float(seg.sum())
        n2 = int(np.clip(np.ceil(length / max(tol, 1e-12)) + 1, 4, 513))
        if n2 == n:
            return pts
        return eval_bspline_curve(model, args, np.linspace(t0, t1, n2))
    if name == "POLYLINE" and len(args) >= 2:
        cps = _bspline_cps(model, args[1], 3)
        return cps
    return None


def resolve_trimmed_3d(model: StepModel, value):
    name, args = first_part(model, value, "TRIMMED_CURVE", "SURFACE_CURVE", "SEAM_CURVE")
    if name is None:
        ent = deref(model, value)
        if ent is None or not (isinstance(ent, tuple) and len(ent) == 2):
            return None, None, None
        return ent, None, None
    if name in ("SURFACE_CURVE", "SEAM_CURVE") and len(args) >= 2:
        iname, iargs = first_part(model, args[1], "TRIMMED_CURVE", "LINE", "CIRCLE", "ELLIPSE",
                                  "HYPERBOLA", "PARABOLA", "B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS",
                                  "RATIONAL_B_SPLINE_CURVE", "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE",
                                  "BEZIER_CURVE", "POLYLINE")
        if iname is None:
            return None, None, None
        if iname == "TRIMMED_CURVE":
            return resolve_trimmed_3d(model, args[1])
        return (iname, iargs), None, None
    if name != "TRIMMED_CURVE" or len(args) < 4:
        return ent, None, None
    bname, bargs = first_part(model, args[1], "LINE", "CIRCLE", "ELLIPSE", "HYPERBOLA", "PARABOLA",
                              "B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE",
                              "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE", "BEZIER_CURVE", "POLYLINE")
    if bname is None:
        return ent, None, None
    basis = (bname, bargs)
    sense = True
    master = "UNSPECIFIED"
    trim1 = args[2] if len(args) > 2 else None
    trim2 = args[3] if len(args) > 3 else None
    for extra in args[4:]:
        if isinstance(extra, tuple) and len(extra) == 2 and extra[0] == "enum":
            tag = str(extra[1]).upper()
            if tag in ("PARAMETER", "CARTESIAN", "UNSPECIFIED"):
                master = tag
            elif tag in ("T", "TRUE", "F", "FALSE"):
                sense = tag in ("T", "TRUE")
    if master == "PARAMETER" and trim1 is not None and trim2 is not None:
        try:
            t0, t1 = float(as_float(trim1)), float(as_float(trim2))
        except (TypeError, ValueError):
            t0 = t1 = None
        if t0 is not None:
            if not sense:
                t0, t1 = t1, t0
            return basis, t0, t1
    if trim1 is not None and trim2 is not None:
        trims = _trim_params_3d(model, bname, basis[1], trim1, trim2, master)
        if trims is not None:
            t0, t1 = trims
            if not sense:
                t0, t1 = t1, t0
            return basis, t0, t1
    if bname in ("CIRCLE", "ELLIPSE"):
        return basis, 0.0, 2.0 * np.pi
    if bname == "LINE":
        return basis, 0.0, 1.0
    return ent, None, None


def sample_edge_3d(model: StepModel, edge_curve_ref, tol: float):
    name, args = first_part(model, edge_curve_ref, "EDGE_CURVE", "VERTEX_POINT")
    if name is None:
        v = point_of(model, edge_curve_ref)
        return np.array([v, v + 1e-9], dtype=np.float64)
    if name == "VERTEX_POINT":
        v = point_of(model, edge_curve_ref)
        return np.array([v, v + 1e-9], dtype=np.float64)
    if len(args) < 4:
        v = point_of(model, edge_curve_ref)
        return np.array([v, v + 1e-9], dtype=np.float64)
    v_start = point_of(model, args[1]) if len(args) > 1 and args[1] is not None else None
    v_end = point_of(model, args[2]) if len(args) > 2 and args[2] is not None else None
    geom = args[3] if len(args) > 3 else None
    try:
        edge_sense = is_true(args[4]) if len(args) > 4 else True
    except (IndexError, TypeError):
        edge_sense = True
    basis, t0, t1 = resolve_trimmed_3d(model, geom)
    if basis is None:
        return None
    if t0 is None and v_start is not None and v_end is not None:
        rng = _direct_range_3d(model, basis, v_start, v_end)
        if rng is not None:
            t0, t1 = rng
    if t0 is None:
        bname = basis[0] if isinstance(basis, tuple) else ""
        if bname in ("CIRCLE", "ELLIPSE"):
            t0, t1 = 0.0, 2.0 * np.pi
        else:
            return None
    pts = _sample_geom_3d(model, basis, float(t0), float(t1), tol)
    if pts is None or len(pts) < 2:
        return None
    if not edge_sense:
        pts = pts[::-1].copy()
    if v_start is not None:
        pts = np.ascontiguousarray(pts)
        pts[0] = v_start
    if v_end is not None:
        pts[-1] = v_end
    return np.ascontiguousarray(pts, dtype=np.float64)


def _direct_range_3d(model: StepModel, basis, v_start, v_end):
    if basis is None or not (isinstance(basis, tuple) and len(basis) == 2):
        return None
    bname, bargs = basis
    if bname == "LINE":
        try:
            p0 = point_of(model, bargs[1]) if len(bargs) > 1 else np.zeros(3)
            d = direction_of(model, bargs[2], default=[1.0, 0.0, 0.0]) if len(bargs) > 2 else np.array([1.0, 0.0, 0.0])
            return float(np.dot(v_start - p0, d)), float(np.dot(v_end - p0, d))
        except (TypeError, ValueError, IndexError):
            return None
    if bname in ("CIRCLE", "ELLIPSE", "HYPERBOLA", "PARABOLA"):
        trims = _trim_params_3d(model, bname, bargs, v_start, v_end, "CARTESIAN")
        if trims is not None:
            return trims
        if bname in ("CIRCLE", "ELLIPSE"):
            a0 = 0.0
            try:
                from core.assets.importer.stepp.place import placement_of
                o, x, y, _z = placement_of(model, bargs[1])
                a0 = float(np.arctan2(float(np.dot(v_start - o, y)), float(np.dot(v_start - o, x))))
            except (TypeError, ValueError, IndexError):
                a0 = 0.0
            return a0, a0 + 2.0 * np.pi
        return None
    if bname in ("B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE",
                  "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE", "BEZIER_CURVE"):
        return _trim_params_3d(model, bname, bargs, v_start, v_end, "CARTESIAN")
    return None
