# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from bisect import bisect_right
from typing import Callable, Dict, List, Optional, Tuple
from .stats import _sort_unique, _polyfit, _polyval, _pchip_eval, _cubic_spline_eval

def _gaussian_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
    if len(x_pts) < 3:
        return None
    C = min(y_pts)
    ys_c = [max(v - C, 1e-15) for v in y_pts]
    total = sum(ys_c)
    if total < 1e-15:
        return None
    mu = sum(x * y for x, y in zip(x_pts, ys_c)) / total
    sigma2 = sum((x - mu) ** 2 * y for x, y in zip(x_pts, ys_c)) / total
    A = max(ys_c)
    return [A * math.exp(-((xi - mu) ** 2) / (2 * sigma2)) + C for xi in x_eval]


def _gaussian_formula(x_pts: List[float], y_pts: List[float]) -> str:
    C = min(y_pts)
    ys_c = [max(v - C, 1e-15) for v in y_pts]
    total = sum(ys_c)
    if total < 1e-15:
        return ""
    mu = sum(x * y for x, y in zip(x_pts, ys_c)) / total
    sigma2 = sum((x - mu) ** 2 * y for x, y in zip(x_pts, ys_c)) / total
    sigma = math.sqrt(max(sigma2, 1e-15))
    A = max(ys_c)
    return f"y = {fmt(A)}·exp(-(x-{fmt(mu)})²/(2·{fmt(sigma)}²)) + {fmt(C)}"


def _logistic_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
    if len(x_pts) < 4:
        return None
    y_min, y_max = min(y_pts), max(y_pts)
    L = y_max - y_min
    C = y_min
    if L < 1e-15:
        return None
    x0 = x_pts[len(x_pts) // 2]
    span = x_pts[-1] - x_pts[0]
    k = 4.0 / span if span > 0 else 1.0
    for _ in range(60):
        grad_k = sum(
            -2 * (y_pts[i] - C - L / (1 + math.exp(-k * (x_pts[i] - x0)))) *
            (L * (x_pts[i] - x0) * math.exp(-k * (x_pts[i] - x0)) /
             (1 + math.exp(-k * (x_pts[i] - x0))) ** 2)
            for i in range(len(x_pts))
        )
        grad_x0 = sum(
            -2 * (y_pts[i] - C - L / (1 + math.exp(-k * (x_pts[i] - x0)))) *
            (-L * k * math.exp(-k * (x_pts[i] - x0)) /
             (1 + math.exp(-k * (x_pts[i] - x0))) ** 2)
            for i in range(len(x_pts))
        )
        step = 1e-4 / (abs(grad_k) + abs(grad_x0) + 1e-15)
        k -= step * grad_k
        x0 -= step * grad_x0
    return [C + L / (1 + math.exp(-k * (xi - x0))) for xi in x_eval]


def _logistic_formula(x_pts: List[float], y_pts: List[float]) -> str:
    y_min, y_max = min(y_pts), max(y_pts)
    L = y_max - y_min
    x0 = x_pts[len(x_pts) // 2]
    span = x_pts[-1] - x_pts[0]
    k = 4.0 / span if span > 0 else 1.0
    return f"y = {fmt(L)}/(1+exp(-{fmt(k)}·(x-{fmt(x0)}))) + {fmt(y_min)}"


def _double_exp_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
    if len(x_pts) < 6:
        return None
    mid = len(x_pts) // 2
    r1 = _exp_fit(x_pts[:mid], y_pts[:mid], x_eval)
    r2 = _exp_fit(x_pts[mid:], y_pts[mid:], x_eval)
    if r1 is None or r2 is None:
        return None
    return [0.5 * (v1 + v2) for v1, v2 in zip(r1, r2)]


def _exp_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
    pairs = [(x, y) for x, y in zip(x_pts, y_pts) if y > 0]
    if len(pairs) < 2:
        return None
    xs2 = [p[0] for p in pairs]
    lys = [math.log(p[1]) for p in pairs]
    n = len(xs2)
    sx = sum(xs2)
    sy = sum(lys)
    sxx = sum(xi * xi for xi in xs2)
    sxy = sum(xi * li for xi, li in zip(xs2, lys))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return None
    b = (n * sxy - sx * sy) / denom
    a = math.exp((sy - b * sx) / n)
    return [a * math.exp(b * xi) for xi in x_eval]


def _exp_formula(x_pts: List[float], y_pts: List[float]) -> str:
    pairs = [(x, y) for x, y in zip(x_pts, y_pts) if y > 0]
    if len(pairs) < 2:
        return ""
    xs2 = [p[0] for p in pairs]
    lys = [math.log(p[1]) for p in pairs]
    n = len(xs2)
    sx = sum(xs2)
    sy = sum(lys)
    sxx = sum(xi * xi for xi in xs2)
    sxy = sum(xi * li for xi, li in zip(xs2, lys))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return ""
    b = (n * sxy - sx * sy) / denom
    a = math.exp((sy - b * sx) / n)
    sign = "+" if b >= 0 else "-"
    return f"y = {fmt(a)}·e^({sign}{fmt(abs(b))}·x)"


def _power_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
    pairs = [(x, y) for x, y in zip(x_pts, y_pts) if x > 0 and y > 0]
    if len(pairs) < 2:
        return None
    lxs = [math.log(p[0]) for p in pairs]
    lys = [math.log(p[1]) for p in pairs]
    n = len(lxs)
    sx = sum(lxs)
    sy = sum(lys)
    sxx = sum(xi * xi for xi in lxs)
    sxy = sum(xi * li for xi, li in zip(lxs, lys))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return None
    b = (n * sxy - sx * sy) / denom
    a = math.exp((sy - b * sx) / n)
    result = []
    for xi in x_eval:
        if xi > 0:
            result.append(a * (xi ** b))
        else:
            result.append(None)
    return result


def _power_formula(x_pts: List[float], y_pts: List[float]) -> str:
    pairs = [(x, y) for x, y in zip(x_pts, y_pts) if x > 0 and y > 0]
    if len(pairs) < 2:
        return ""
    lxs = [math.log(p[0]) for p in pairs]
    lys = [math.log(p[1]) for p in pairs]
    n = len(lxs)
    sx = sum(lxs)
    sy = sum(lys)
    sxx = sum(xi * xi for xi in lxs)
    sxy = sum(xi * li for xi, li in zip(lxs, lys))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return ""
    b = (n * sxy - sx * sy) / denom
    a = math.exp((sy - b * sx) / n)
    return f"y = {fmt(a)}·x^{fmt(b)}"


def _log_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
    pairs = [(x, y) for x, y in zip(x_pts, y_pts) if x > 0]
    if len(pairs) < 2:
        return None
    lxs = [math.log(p[0]) for p in pairs]
    ys2 = [p[1] for p in pairs]
    n = len(lxs)
    slx = sum(lxs)
    sy = sum(ys2)
    slxlx = sum(lx * lx for lx in lxs)
    slxy = sum(lx * yi for lx, yi in zip(lxs, ys2))
    denom = n * slxlx - slx * slx
    if abs(denom) < 1e-15:
        return None
    b = (n * slxy - slx * sy) / denom
    a = (sy - b * slx) / n
    result = []
    for xi in x_eval:
        if xi > 0:
            result.append(a + b * math.log(xi))
        else:
            result.append(None)
    return result


def _log_formula(x_pts: List[float], y_pts: List[float]) -> str:
    pairs = [(x, y) for x, y in zip(x_pts, y_pts) if x > 0]
    if len(pairs) < 2:
        return ""
    lxs = [math.log(p[0]) for p in pairs]
    ys2 = [p[1] for p in pairs]
    n = len(lxs)
    slx = sum(lxs)
    sy = sum(ys2)
    slxlx = sum(lx * lx for lx in lxs)
    slxy = sum(lx * yi for lx, yi in zip(lxs, ys2))
    denom = n * slxlx - slx * slx
    if abs(denom) < 1e-15:
        return ""
    b = (n * slxy - slx * sy) / denom
    a = (sy - b * slx) / n
    sign = "+" if b >= 0 else "-"
    return f"y = {fmt(a)} {sign} {fmt(abs(b))}·ln(x)"


def _sinusoidal_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
    n = len(x_pts)
    if n < 4:
        return None
    try:
        ys = y_pts
        y_mean = sum(ys) / n
        y_centered = [v - y_mean for v in ys]
        x_range = x_pts[-1] - x_pts[0]
        if x_range <= 0:
            return None
        T_guess = x_range / 2.0
        omega = 2 * math.pi / T_guess
        sc = sum(y_centered[i] * math.sin(omega * x_pts[i]) for i in range(n))
        cc = sum(y_centered[i] * math.cos(omega * x_pts[i]) for i in range(n))
        A = 2 * math.sqrt(sc ** 2 + cc ** 2) / n
        phi = math.atan2(sc, cc)
        return [A * math.sin(omega * xi + phi) + y_mean for xi in x_eval]
    except Exception:
        return None


def _moving_average_fit(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> List[float]:
    n = len(y_pts)
    win = max(3, n // 5)
    half = win // 2
    smoothed_x = []
    smoothed_y = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        smoothed_x.append(x_pts[i])
        smoothed_y.append(sum(y_pts[lo:hi]) / (hi - lo))
    return _pchip_eval(smoothed_x, smoothed_y, x_eval)


FitFn = Callable[[List[float], List[float], List[float]], List[float]]


class FitMode:
    def __init__(self, key: str, label: str, fn: FitFn, min_points: int = 2,
                 formula_fn: Optional[Callable[[List[float], List[float]], str]] = None):
        self.key = key
        self.label = label
        self.fn = fn
        self.min_points = min_points
        self.formula_fn = formula_fn

    def evaluate(self, x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> Optional[List[float]]:
        x_pts, y_pts = _sort_unique(x_pts, y_pts)
        if len(x_pts) < self.min_points:
            return None
        return self.fn(x_pts, y_pts, x_eval)

    def formula(self, x_pts: List[float], y_pts: List[float]) -> str:
        if self.formula_fn is None:
            return ""
        x_pts, y_pts = _sort_unique(x_pts, y_pts)
        if len(x_pts) < self.min_points:
            return ""
        try:
            return self.formula_fn(x_pts, y_pts)
        except Exception:
            return ""


def _fit_linear_origin(x_pts, y_pts, x_eval):
    denom = sum(xi * xi for xi in x_pts)
    k = sum(xi * yi for xi, yi in zip(x_pts, y_pts)) / denom if denom else 0.0
    return [k * xi for xi in x_eval]


def _formula_linear_origin(x_pts, y_pts):
    denom = sum(xi * xi for xi in x_pts)
    k = sum(xi * yi for xi, yi in zip(x_pts, y_pts)) / denom if denom else 0.0
    return f"y = {fmt(k)}·x"


def _fit_linear(x_pts, y_pts, x_eval):
    x_min = x_pts[0]
    x_range = float(x_pts[-1] - x_min) or 1.0
    xn = [(xi - x_min) / x_range for xi in x_pts]
    c = _polyfit(xn, y_pts, 1)
    return [_polyval(c, (xi - x_min) / x_range) for xi in x_eval]


def _formula_linear(x_pts, y_pts):
    x_min = x_pts[0]
    x_range = float(x_pts[-1] - x_min) or 1.0
    xn = [(xi - x_min) / x_range for xi in x_pts]
    c = _polyfit(xn, y_pts, 1)
    a_real = c[0] / x_range
    b_real = c[1] - c[0] * x_min / x_range
    sign = "+" if b_real >= 0 else "-"
    return f"y = {fmt(a_real)}·x {sign} {fmt(abs(b_real))}"


def _make_poly_fit(deg: int) -> FitFn:
    def _fit(x_pts, y_pts, x_eval):
        actual_deg = min(deg, len(x_pts) - 1)
        x_min = x_pts[0]
        x_range = float(x_pts[-1] - x_min) or 1.0
        xn = [(xi - x_min) / x_range for xi in x_pts]
        c = _polyfit(xn, y_pts, actual_deg)
        return [_polyval(c, (xi - x_min) / x_range) for xi in x_eval]
    return _fit


def _make_poly_formula(deg: int):
    def _formula(x_pts, y_pts):
        actual_deg = min(deg, len(x_pts) - 1)
        x_min = x_pts[0]
        x_range = float(x_pts[-1] - x_min) or 1.0
        xn = [(xi - x_min) / x_range for xi in x_pts]
        c = _polyfit(xn, y_pts, actual_deg)
        parts = []
        for i, coef in enumerate(c):
            power = actual_deg - i
            if abs(coef) < 1e-10:
                continue
            if power == 0:
                parts.append(fmt(coef))
            elif power == 1:
                parts.append(f"{fmt(coef)}·x")
            else:
                parts.append(f"{fmt(coef)}·x^{power}")
        return "y = " + (" + ".join(parts) if parts else "0")
    return _formula


def _fit_pchip(x_pts, y_pts, x_eval):
    return _pchip_eval(x_pts, y_pts, x_eval)


def _fit_cubic_spline(x_pts, y_pts, x_eval):
    if len(x_pts) == 2:
        return _pchip_eval(x_pts, y_pts, x_eval)
    return _cubic_spline_eval(x_pts, y_pts, x_eval)


def _fit_exp(x_pts, y_pts, x_eval):
    result = _exp_fit(x_pts, y_pts, x_eval)
    if result is None:
        return [0.0] * len(x_eval)
    return result


def _fit_power(x_pts, y_pts, x_eval):
    result = _power_fit(x_pts, y_pts, x_eval)
    if result is None:
        return [None] * len(x_eval)
    return result


def _fit_log(x_pts, y_pts, x_eval):
    result = _log_fit(x_pts, y_pts, x_eval)
    if result is None:
        return [None] * len(x_eval)
    return result


def _fit_gaussian(x_pts, y_pts, x_eval):
    r = _gaussian_fit(x_pts, y_pts, x_eval)
    return r if r is not None else [0.0] * len(x_eval)


def _fit_logistic(x_pts, y_pts, x_eval):
    r = _logistic_fit(x_pts, y_pts, x_eval)
    return r if r is not None else [0.0] * len(x_eval)


def _fit_double_exp(x_pts, y_pts, x_eval):
    r = _double_exp_fit(x_pts, y_pts, x_eval)
    return r if r is not None else [0.0] * len(x_eval)


_BUILTIN_MODES: List[FitMode] = [
    FitMode("linear_origin", "Linear (origin)",  _fit_linear_origin,     1,  _formula_linear_origin),
    FitMode("linear",        "Linear",            _fit_linear,             2,  _formula_linear),
    FitMode("poly2",         "Polynomial 2°",     _make_poly_fit(2),       2,  _make_poly_formula(2)),
    FitMode("poly3",         "Polynomial 3°",     _make_poly_fit(3),       2,  _make_poly_formula(3)),
    FitMode("poly4",         "Polynomial 4°",     _make_poly_fit(4),       2,  _make_poly_formula(4)),
    FitMode("poly5",         "Polynomial 5°",     _make_poly_fit(5),       2,  _make_poly_formula(5)),
    FitMode("pchip",         "PCHIP",             _fit_pchip,              2),
    FitMode("spline",        "Cubic Spline",      _fit_cubic_spline,       2),
    FitMode("exp",           "Exponential",       _fit_exp,                2,  _exp_formula),
    FitMode("power",         "Power",             _fit_power,              2,  _power_formula),
    FitMode("log",           "Logarithmic",       _fit_log,                2,  _log_formula),
    FitMode("sine",          "Sinusoidal",        _sinusoidal_fit,         4),
    FitMode("moving_avg",    "Moving Average",    _moving_average_fit,     3),
    FitMode("gaussian",      "Gaussian",          _fit_gaussian,           3,  _gaussian_formula),
    FitMode("logistic",      "Logistic",          _fit_logistic,           4,  _logistic_formula),
    FitMode("double_exp",    "Double Exponential",_fit_double_exp,         6),
]

_REGISTRY: Dict[str, FitMode] = {m.key: m for m in _BUILTIN_MODES}


def register_fit_mode(mode: FitMode):
    _REGISTRY[mode.key] = mode


def get_fit_modes() -> List[FitMode]:
    return list(_REGISTRY.values())


def get_fit_mode(key: str) -> Optional[FitMode]:
    return _REGISTRY.get(key)


def fmt(v: float) -> str:
    if not math.isfinite(v):
        return str(v)
    if v == 0:
        return "0"
    abs_v = abs(v)
    if abs_v >= 1e15:
        return f"{v:.6g}"
    if abs_v >= 1000:
        return f"{v:.0f}"
    if abs_v >= 100:
        return f"{v:.0f}"
    if abs_v >= 10:
        return f"{v:.1f}"
    if abs_v >= 1:
        return f"{v:.4g}"
    for digits in range(1, 10):
        s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
        if float(s) != 0.0:
            return s
    return f"{v:.4g}"
