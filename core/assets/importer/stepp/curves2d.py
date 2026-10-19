# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import math
import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, as_float, first_part
from core.assets.importer.stepp.place import point_of
from core.assets.importer.stepp.curves import _bspline_cps
from core.assets.importer.stepp.curves import _curve_knots
from core.assets.importer.stepp.curves import _curve_weights


def _direction_2d(model: StepModel, value):
    ent = deref(model, value)
    if ent is not None and isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "VECTOR":
        args = ent[1]
        if len(args) >= 2 and args[1] is not None:
            return _direction_2d(model, args[1])
        return np.array([1.0, 0.0], dtype=np.float64)
    if ent is not None and isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "DIRECTION":
        args = ent[1]
        if len(args) >= 2 and isinstance(args[1], (list, tuple)):
            try:
                vals = [float(as_float(v)) for v in args[1]]
                if len(vals) >= 2:
                    v = np.array(vals[:2], dtype=np.float64)
                    n = float(np.linalg.norm(v))
                    if n > 1e-300:
                        return v / n
            except (TypeError, ValueError):
                pass
    return np.array([1.0, 0.0], dtype=np.float64)


def placement_2d_of(model: StepModel, value):
    origin = np.zeros(2, dtype=np.float64)
    ref = np.array([1.0, 0.0], dtype=np.float64)
    ent = deref(model, value)
    if ent is not None and isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "AXIS2_PLACEMENT_2D":
        args = ent[1]
        if len(args) > 1 and args[1] is not None:
            p = point_of(model, args[1])
            origin = np.array([float(p[0]), float(p[1])], dtype=np.float64)
        if len(args) > 2 and args[2] is not None:
            ref = _direction_2d(model, args[2])
    n = float(np.linalg.norm(ref))
    if n < 1e-300:
        ref = np.array([1.0, 0.0], dtype=np.float64)
        n = 1.0
    x = ref / n
    y = np.array([-x[1], x[0]], dtype=np.float64)
    return origin, x, y


def eval_bspline_2d(model: StepModel, args: list, ts: np.ndarray):
    try:
        if len(args) < 2:
            return None
        from core.assets.importer.stepp.nurbs import nurbs_eval_curve
        degree = int(as_float(args[1]))
        cps = _bspline_cps(model, args[2], 2)
        if cps is None:
            return None
        ku = _curve_knots(args, degree, cps.shape[0])
        w = _curve_weights(args, cps.shape[0])
        return nurbs_eval_curve(cps, ku, degree, ts, w)
    except (TypeError, ValueError, IndexError):
        return None


def _eval_circle_2d(model: StepModel, args: list, ts: np.ndarray):
    try:
        o, x, y = placement_2d_of(model, args[1])
        r = float(as_float(args[2], 1.0))
        t = np.asarray(ts, dtype=np.float64).ravel()
        return o[None, :] + r * (np.cos(t)[:, None] * x[None, :] + np.sin(t)[:, None] * y[None, :])
    except (TypeError, ValueError, IndexError):
        return None


def _eval_ellipse_2d(model: StepModel, args: list, ts: np.ndarray):
    try:
        o, x, y = placement_2d_of(model, args[1])
        r1 = float(as_float(args[2], 1.0))
        r2 = float(as_float(args[3], 1.0))
        t = np.asarray(ts, dtype=np.float64).ravel()
        return o[None, :] + (r1 * np.cos(t))[:, None] * x[None, :] + (r2 * np.sin(t))[:, None] * y[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _eval_hyperbola_2d(model: StepModel, args: list, ts: np.ndarray):
    try:
        o, x, y = placement_2d_of(model, args[1])
        a = float(as_float(args[2], 1.0)) if len(args) > 2 else 1.0
        b = float(as_float(args[3], a)) if len(args) > 3 else abs(a)
        a = a if abs(a) > 1e-300 else 1.0
        b = b if abs(b) > 1e-300 else abs(a)
        t = np.asarray(ts, dtype=np.float64).ravel()
        ch = np.cosh(t)
        sh = np.sinh(t)
        return o[None, :] + (a * ch)[:, None] * x[None, :] + (b * sh)[:, None] * y[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _eval_parabola_2d(model: StepModel, args: list, ts: np.ndarray):
    try:
        o, x, y = placement_2d_of(model, args[1])
        f = float(as_float(args[2], 1.0))
        f = f if abs(f) > 1e-300 else 1.0
        t = np.asarray(ts, dtype=np.float64).ravel()
        return o[None, :] + ((t * t) / (4.0 * f))[:, None] * x[None, :] + t[:, None] * y[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _hyperbola_range_2d(model: StepModel, args: list, p1, p2):
    try:
        o, x, y = placement_2d_of(model, args[1])
        r = float(as_float(args[2], 1.0))
        d1 = (np.asarray(p1, dtype=np.float64).ravel()[:2] - o) / max(abs(r), 1e-300)
        d2 = (np.asarray(p2, dtype=np.float64).ravel()[:2] - o) / max(abs(r), 1e-300)
        t1 = float(np.arcsinh(max(d1[1], -1e300)))
        t2 = float(np.arcsinh(max(d2[1], -1e300)))
        return t1, t2
    except (TypeError, ValueError, IndexError):
        return None


def _parabola_range_2d(model: StepModel, args: list, p1, p2):
    try:
        o, x, y = placement_2d_of(model, args[1])
        d1 = np.asarray(p1, dtype=np.float64).ravel()[:2] - o
        d2 = np.asarray(p2, dtype=np.float64).ravel()[:2] - o
        return float(np.dot(d1, y)), float(np.dot(d2, y))
    except (TypeError, ValueError, IndexError):
        return None


def _eval_line_2d(model: StepModel, args: list, ts: np.ndarray):
    try:
        p3 = point_of(model, args[1])
        d = _direction_2d(model, args[2])
        p = np.array([float(p3[0]), float(p3[1])], dtype=np.float64)
        t = np.asarray(ts, dtype=np.float64).ravel()
        return p[None, :] + t[:, None] * d[None, :]
    except (TypeError, ValueError, IndexError):
        return None


def _trim_params_2d(model: StepModel, geom_name: str, geom_args: list, trim1, trim2):
    p1 = point_of(model, trim1)
    p2 = point_of(model, trim2)
    q1 = np.array([float(p1[0]), float(p1[1])], dtype=np.float64)
    q2 = np.array([float(p2[0]), float(p2[1])], dtype=np.float64)
    if geom_name == "LINE":
        try:
            p0 = point_of(model, geom_args[1])
            d = _direction_2d(model, geom_args[2])
            o = np.array([float(p0[0]), float(p0[1])], dtype=np.float64)
            return float(np.dot(q1 - o, d)), float(np.dot(q2 - o, d))
        except (TypeError, ValueError, IndexError):
            return None
    if geom_name in ("CIRCLE", "ELLIPSE"):
        try:
            o, x, y = placement_2d_of(model, geom_args[1])
            r1 = float(as_float(geom_args[2], 1.0)) if len(geom_args) > 2 else 1.0
            r2 = float(as_float(geom_args[3], r1)) if len(geom_args) > 3 else abs(r1)
            r1 = r1 if abs(r1) > 1e-300 else 1.0
            r2 = r2 if abs(r2) > 1e-300 else abs(r1)
            a1 = float(np.arctan2(float(np.dot(q1 - o, y)) / r2, float(np.dot(q1 - o, x)) / r1))
            a2 = float(np.arctan2(float(np.dot(q2 - o, y)) / r2, float(np.dot(q2 - o, x)) / r1))
            if float(np.linalg.norm(q1 - q2)) < 1e-9:
                return a1, a1 + 2.0 * math.pi
            span = (a2 - a1) % (2.0 * math.pi)
            if span < 1e-9:
                span = 2.0 * math.pi
            return a1, a1 + span
        except (TypeError, ValueError, IndexError):
            return None
    if geom_name == "HYPERBOLA":
        try:
            o, x, y = placement_2d_of(model, geom_args[1])
            a = float(as_float(geom_args[2], 1.0)) if len(geom_args) > 2 else 1.0
            b = float(as_float(geom_args[3], a)) if len(geom_args) > 3 else abs(a)
            a = a if abs(a) > 1e-300 else 1.0
            b = b if abs(b) > 1e-300 else abs(a)
            d1 = q1 - o
            d2 = q2 - o
            return float(np.arcsinh(float(np.dot(d1, y)) / b)), float(np.arcsinh(float(np.dot(d2, y)) / b))
        except (TypeError, ValueError, IndexError):
            return None
    if geom_name in ("HYPERBOLA", "PARABOLA"):
        try:
            o, x, y = placement_2d_of(model, geom_args[1])
            if geom_name == "HYPERBOLA":
                r = float(as_float(geom_args[2], 1.0)) if len(geom_args) > 2 else 1.0
                r = r if abs(r) > 1e-300 else 1.0
                d1 = (q1 - o) / r
                d2 = (q2 - o) / r
                return float(np.arcsinh(d1[1])), float(np.arcsinh(d2[1]))
            d1 = q1 - o
            d2 = q2 - o
            return float(np.dot(d1, y)), float(np.dot(d2, y))
        except (TypeError, ValueError, IndexError):
            return None
    return None


def _resolve_trimmed_2d(model: StepModel, value):
    ent = deref(model, value)
    if ent is None or not (isinstance(ent, tuple) and len(ent) == 2):
        return None, None, None, False
    name, args = ent
    if name in ("DEFINITIONAL_REPRESENTATION", "REPRESENTATION"):
        items = args[1] if len(args) > 1 else None
        if isinstance(items, (list, tuple)) and len(items) > 0:
            return _resolve_trimmed_2d(model, items[0])
        return None, None, None, False
    if name != "TRIMMED_CURVE" or len(args) < 4:
        return ent, None, None, False
    if len(args) < 4:
        return ent, None, None, False
    basis = deref(model, args[1])
    if basis is None or not (isinstance(basis, tuple) and len(basis) == 2):
        return ent, None, None, False
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
    t0 = t1 = None
    exact = False
    if master == "PARAMETER" and trim1 is not None and trim2 is not None:
        try:
            t0, t1 = float(as_float(trim1)), float(as_float(trim2))
            exact = True
        except (TypeError, ValueError):
            t0 = t1 = None
    if t0 is None and master == "CARTESIAN" and trim1 is not None and trim2 is not None:
        got = _trim_params_2d(model, basis[0] if isinstance(basis, tuple) else "", basis[1] if isinstance(basis, tuple) else [], trim1, trim2)
        if got is not None:
            t0, t1 = got
            exact = True
    if t0 is None:
        return ent, None, None, False
    if not sense:
        t0, t1 = t1, t0
    return basis, t0, t1, exact


def sample_curve_2d(model: StepModel, value, t0: float, t1: float, tol: float):
    name, args = first_part(model, value, "LINE", "CIRCLE", "ELLIPSE", "HYPERBOLA", "PARABOLA",
                            "B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE",
                            "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE", "BEZIER_CURVE", "POLYLINE")
    if name is None:
        return None
    span = abs(float(t1) - float(t0))
    if name == "LINE":
        return _eval_line_2d(model, args, np.array([t0, t1]))
    if name in ("CIRCLE", "ELLIPSE"):
        r = 1.0
        try:
            if name == "CIRCLE" and len(args) > 2:
                r = float(as_float(args[2], 1.0))
            elif len(args) > 3:
                r = max(float(as_float(args[2], 1.0)), float(as_float(args[3], 1.0)))
        except (TypeError, ValueError, IndexError):
            r = 1.0
        n = int(np.clip(np.ceil(span * r / max(tol, 1e-12)) + 1, 3, 257))
        if name == "CIRCLE":
            return _eval_circle_2d(model, args, np.linspace(t0, t1, n))
        return _eval_ellipse_2d(model, args, np.linspace(t0, t1, n))
    if name in ("HYPERBOLA", "PARABOLA"):
        n = 65
        if name == "HYPERBOLA":
            pts = _eval_hyperbola_2d(model, args, np.linspace(t0, t1, n))
        else:
            pts = _eval_parabola_2d(model, args, np.linspace(t0, t1, n))
        if pts is None:
            return None
        seg = np.linalg.norm(pts[1:] - pts[:-1], axis=1)
        length = float(seg.sum())
        n2 = int(np.clip(np.ceil(length / max(tol, 1e-12)) + 1, 4, 513))
        if n2 == n:
            return pts
        if name == "HYPERBOLA":
            return _eval_hyperbola_2d(model, args, np.linspace(t0, t1, n2))
        return _eval_parabola_2d(model, args, np.linspace(t0, t1, n2))
    if name in ("B_SPLINE_CURVE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE",
                "QUASI_UNIFORM_CURVE", "UNIFORM_CURVE", "BEZIER_CURVE"):
        n = 65
        pts = eval_bspline_2d(model, args, np.linspace(t0, t1, n))
        if pts is None:
            return None
        seg = np.linalg.norm(pts[1:] - pts[:-1], axis=1)
        length = float(seg.sum())
        n2 = int(np.clip(np.ceil(length / max(tol, 1e-12)) + 1, 4, 513))
        if n2 == n:
            return pts
        return eval_bspline_2d(model, args, np.linspace(t0, t1, n2))
    if name == "POLYLINE" and len(args) >= 2:
        return _bspline_cps(model, args[1], 2)
    return None


def sample_pcurve(model: StepModel, pcurve_ref, tol: float):
    name, args = first_part(model, pcurve_ref, "PCURVE")
    if name is None or len(args) < 3:
        return None, None
    basis_id = None
    try:
        b = args[1]
        if isinstance(b, tuple) and len(b) == 2 and b[0] == "ref":
            basis_id = int(b[1])
    except (TypeError, ValueError, IndexError):
        basis_id = None
    basis, t0, t1, exact = _resolve_trimmed_2d(model, args[2])
    if basis is None:
        return None, None
    if t0 is None or not exact:
        return None, None
    pts = sample_curve_2d(model, basis, float(t0), float(t1), tol)
    if pts is None:
        return None, None
    return np.ascontiguousarray(pts, dtype=np.float64), basis_id
