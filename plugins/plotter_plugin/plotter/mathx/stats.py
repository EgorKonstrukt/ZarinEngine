# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from bisect import bisect_right
from typing import Callable, Dict, List, Optional, Tuple

_CY = False
_NICE_TICKS_MAX = 64


def derivative(xs: List[float], ys: List[float]) -> Tuple[List[float], List[float]]:
    n = len(xs)
    if n < 2:
        return [], []
    dydx = []
    for i in range(n):
        if i == 0:
            dx = xs[1] - xs[0]
            dy = ys[1] - ys[0]
        elif i == n - 1:
            dx = xs[-1] - xs[-2]
            dy = ys[-1] - ys[-2]
        else:
            dx = xs[i + 1] - xs[i - 1]
            dy = ys[i + 1] - ys[i - 1]
        dydx.append(dy / dx if abs(dx) > 1e-15 else 0.0)
    return list(xs), dydx


def second_derivative(xs: List[float], ys: List[float]) -> Tuple[List[float], List[float]]:
    n = len(xs)
    if n < 3:
        return [], []
    out = []
    for i in range(1, n - 1):
        dx1 = xs[i] - xs[i - 1]
        dx2 = xs[i + 1] - xs[i]
        if abs(dx1) < 1e-15 or abs(dx2) < 1e-15:
            out.append(0.0)
        else:
            out.append(2 * ((ys[i + 1] - ys[i]) / dx2 - (ys[i] - ys[i - 1]) / dx1) / (dx1 + dx2))
    return xs[1:-1], out


def cumulative_integral(xs: List[float], ys: List[float]) -> Tuple[List[float], List[float]]:
    if len(xs) < 2:
        return list(xs), [0.0] * len(xs)
    result = [0.0]
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        result.append(result[-1] + dx * (ys[i - 1] + ys[i]) / 2.0)
    return list(xs), result


def fft_spectrum(xs: List[float], ys: List[float]) -> Tuple[List[float], List[float]]:
    n = len(ys)
    if n < 4:
        return [], []
    dt = (xs[-1] - xs[0]) / (n - 1) if n > 1 else 1.0
    if dt <= 0:
        return [], []
    re = list(ys)
    im = [0.0] * n
    for k in range(n):
        re[k] = sum(ys[j] * math.cos(2 * math.pi * k * j / n) for j in range(n))
        im[k] = -sum(ys[j] * math.sin(2 * math.pi * k * j / n) for j in range(n))
    half = n // 2 + 1
    freqs = [k / (n * dt) for k in range(half)]
    amps = [math.sqrt(re[k] ** 2 + im[k] ** 2) / n * (1 if k == 0 else 2) for k in range(half)]
    return freqs, amps


def fft_spectrum_numpy(xs: List[float], ys: List[float]) -> Tuple[List[float], List[float]]:
    try:
        import numpy as np
        n = len(ys)
        if n < 4:
            return [], []
        dt = (xs[-1] - xs[0]) / (n - 1) if n > 1 else 1.0
        if dt <= 0:
            return [], []
        fft = np.fft.rfft(ys)
        freqs = np.fft.rfftfreq(n, dt).tolist()
        amps = (np.abs(fft) / n * np.array([1] + [2] * (len(fft) - 1))).tolist()
        return freqs, amps
    except ImportError:
        return fft_spectrum(xs, ys)


def histogram(data: List[float], bins: int = 20) -> Tuple[List[float], List[float]]:
    if not data or bins < 1:
        return [], []
    lo, hi = min(data), max(data)
    if lo == hi:
        return [lo], [float(len(data))]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in data:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    centers = [lo + (i + 0.5) * width for i in range(bins)]
    return centers, [float(c) for c in counts]


def autocorrelation(ys: List[float], max_lag: Optional[int] = None) -> Tuple[List[int], List[float]]:
    n = len(ys)
    if n < 2:
        return [], []
    lim = min(max_lag or n - 1, n - 1)
    mean = sum(ys) / n
    var = sum((v - mean) ** 2 for v in ys)
    if var < 1e-15:
        return list(range(lim + 1)), [1.0] + [0.0] * lim
    lags = list(range(lim + 1))
    acf = []
    for lag in lags:
        c = sum((ys[i] - mean) * (ys[i + lag] - mean) for i in range(n - lag))
        acf.append(c / var)
    return lags, acf


def normalize(ys: List[float], method: str = "minmax") -> List[float]:
    if not ys:
        return []
    if method == "minmax":
        lo, hi = min(ys), max(ys)
        rng = hi - lo
        return [(v - lo) / rng if rng > 1e-15 else 0.0 for v in ys]
    if method == "zscore":
        n = len(ys)
        mean = sum(ys) / n
        std = math.sqrt(sum((v - mean) ** 2 for v in ys) / n)
        return [(v - mean) / std if std > 1e-15 else 0.0 for v in ys]
    if method == "maxabs":
        ma = max(abs(v) for v in ys)
        return [v / ma if ma > 1e-15 else 0.0 for v in ys]
    return list(ys)


def peak_find(xs: List[float], ys: List[float],
              min_prominence: float = 0.0) -> Tuple[List[float], List[float]]:
    n = len(ys)
    if n < 3:
        return [], []
    y_range = max(ys) - min(ys) if n else 1.0
    px, py = [], []
    for i in range(1, n - 1):
        if ys[i] > ys[i - 1] and ys[i] > ys[i + 1]:
            left_min = min(ys[:i + 1])
            right_min = min(ys[i:])
            prominence = ys[i] - max(left_min, right_min)
            if prominence >= min_prominence * y_range:
                px.append(xs[i])
                py.append(ys[i])
    return px, py


def weighted_mean(ys: List[float], weights: List[float]) -> float:
    sw = sum(weights)
    if sw < 1e-15:
        return float("nan")
    return sum(y * w for y, w in zip(ys, weights)) / sw


def moving_std(ys: List[float], window: int) -> List[float]:
    n = len(ys)
    out = []
    for i in range(n):
        lo = max(0, i - window // 2)
        hi = min(n, lo + window)
        seg = ys[lo:hi]
        m = sum(seg) / len(seg)
        out.append(math.sqrt(sum((v - m) ** 2 for v in seg) / len(seg)))
    return out


def linspace(start: float, stop: float, n: int) -> List[float]:
    if n < 2:
        return [start]
    step = (stop - start) / (n - 1)
    return [start + step * i for i in range(n)]


def _sort_unique(x: List[float], y: List[float]) -> Tuple[List[float], List[float]]:
    order = sorted(range(len(x)), key=lambda i: x[i])
    x2, y2 = [x[i] for i in order], [y[i] for i in order]
    xs: List[float] = []
    ys: List[float] = []
    for xi, yi in zip(x2, y2):
        if not xs or xi != xs[-1]:
            xs.append(xi)
            ys.append(yi)
    return xs, ys


def _gauss_solve(a: List[List[float]], b: List[float]) -> List[float]:
    n = len(b)
    a = [row[:] for row in a]
    b = b[:]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        a[col], a[pivot] = a[pivot], a[col]
        b[col], b[pivot] = b[pivot], b[col]
        if abs(a[col][col]) < 1e-15:
            continue
        f = a[col][col]
        a[col] = [v / f for v in a[col]]
        b[col] /= f
        for row in range(n):
            if row == col:
                continue
            fac = a[row][col]
            a[row] = [a[row][j] - fac * a[col][j] for j in range(n)]
            b[row] -= fac * b[col]
    return b


def _polyfit(x: List[float], y: List[float], deg: int) -> List[float]:
    d = deg + 1
    vt_v = [[0.0] * d for _ in range(d)]
    vt_y = [0.0] * d
    for xi, yi in zip(x, y):
        row = [xi ** (deg - j) for j in range(d)]
        for r in range(d):
            for c in range(d):
                vt_v[r][c] += row[r] * row[c]
            vt_y[r] += row[r] * yi
    return _gauss_solve(vt_v, vt_y)


def _polyval(coeffs: List[float], x: float) -> float:
    result = 0.0
    for c in coeffs:
        result = result * x + c
    return result


def _pchip_eval(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> List[float]:
    n = len(x_pts)
    h = [x_pts[i + 1] - x_pts[i] for i in range(n - 1)]
    s = [(y_pts[i + 1] - y_pts[i]) / h[i] for i in range(n - 1)]
    d = [0.0] * n
    d[0] = s[0]
    d[-1] = s[-1]
    for k in range(1, n - 1):
        if s[k - 1] * s[k] <= 0.0:
            d[k] = 0.0
        else:
            w1 = 2 * h[k] + h[k - 1]
            w2 = h[k] + 2 * h[k - 1]
            d[k] = (w1 + w2) / (w1 / s[k - 1] + w2 / s[k])
    result = []
    for xi in x_eval:
        idx = max(0, min(bisect_right(x_pts, xi) - 1, n - 2))
        dx = xi - x_pts[idx]
        hk = h[idx]
        t = dx / hk
        t2 = t * t
        t3 = t2 * t
        result.append(
            (2 * t3 - 3 * t2 + 1) * y_pts[idx]
            + (t3 - 2 * t2 + t) * hk * d[idx]
            + (-2 * t3 + 3 * t2) * y_pts[idx + 1]
            + (t3 - t2) * hk * d[idx + 1]
        )
    return result


def _cubic_spline_eval(x_pts: List[float], y_pts: List[float], x_eval: List[float]) -> List[float]:
    n = len(x_pts)
    h = [float(x_pts[i + 1] - x_pts[i]) for i in range(n - 1)]
    rhs = [0.0] * n
    for i in range(1, n - 1):
        rhs[i] = 3.0 * ((y_pts[i + 1] - y_pts[i]) / h[i] - (y_pts[i] - y_pts[i - 1]) / h[i - 1])
    diag = [2.0] * n
    lo = [0.0] * n
    up = [0.0] * n
    for i in range(1, n - 1):
        lo[i] = h[i - 1]
        up[i] = h[i]
    diag[0] = 1.0; up[0] = 0.0; rhs[0] = 0.0
    diag[-1] = 1.0; lo[-1] = 0.0; rhs[-1] = 0.0
    cu = [0.0] * n
    cr = [0.0] * n
    cu[0] = up[0] / diag[0] if diag[0] else 0.0
    cr[0] = rhs[0] / diag[0] if diag[0] else 0.0
    for i in range(1, n):
        den = diag[i] - lo[i] * cu[i - 1]
        cu[i] = (up[i] / den) if (i < n - 1 and den) else 0.0
        cr[i] = ((rhs[i] - lo[i] * cr[i - 1]) / den) if den else 0.0
    m = [0.0] * n
    m[-1] = cr[-1]
    for i in range(n - 2, -1, -1):
        m[i] = cr[i] - cu[i] * m[i + 1]
    a = list(y_pts[:-1])
    b_c = [(y_pts[i + 1] - y_pts[i]) / h[i] - h[i] * (2 * m[i] + m[i + 1]) / 3.0 for i in range(n - 1)]
    c_c = m[:-1]
    d_c = [(m[i + 1] - m[i]) / (3.0 * h[i]) for i in range(n - 1)]
    result = []
    for xi in x_eval:
        idx = max(0, min(bisect_right(x_pts, xi) - 1, n - 2))
        dx = xi - x_pts[idx]
        result.append(a[idx] + b_c[idx] * dx + c_c[idx] * dx ** 2 + d_c[idx] * dx ** 3)
    return result


def trapezoid_integral(xs: List[float], ys: List[float],
                       x_lo: Optional[float] = None, x_hi: Optional[float] = None) -> float:
    if len(xs) < 2:
        return 0.0
    pairs = sorted(zip(xs, ys), key=lambda p: p[0])
    if x_lo is not None:
        pairs = [(x, y) for x, y in pairs if x >= x_lo]
    if x_hi is not None:
        pairs = [(x, y) for x, y in pairs if x <= x_hi]
    if len(pairs) < 2:
        return 0.0
    total = 0.0
    for i in range(len(pairs) - 1):
        x0, y0 = pairs[i]
        x1, y1 = pairs[i + 1]
        total += (x1 - x0) * (y0 + y1) / 2.0
    return total


def rms(ys: List[float]) -> float:
    if not ys:
        return 0.0
    return math.sqrt(sum(v * v for v in ys) / len(ys))


def percentile(data: List[float], p: float) -> float:
    n = len(data)
    if n == 0:
        return float("nan")
    if n == 1:
        return data[0]
    sorted_data = sorted(data)
    pos = (p / 100.0) * (n - 1)
    lo = int(pos)
    hi = lo + 1
    if hi >= n:
        return sorted_data[-1]
    frac = pos - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


def correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(xs, ys))
    dx2 = sum((xi - mx) ** 2 for xi in xs)
    dy2 = sum((yi - my) ** 2 for yi in ys)
    denom = math.sqrt(dx2 * dy2)
    return num / denom if denom > 1e-15 else None


def r_squared(xs: List[float], ys: List[float], fit_ys: List[float]) -> Optional[float]:
    n = len(ys)
    if n < 2 or len(fit_ys) != n:
        return None
    mean_y = sum(ys) / n
    ss_res = sum((yi - fi) ** 2 for yi, fi in zip(ys, fit_ys))
    ss_tot = sum((yi - mean_y) ** 2 for yi in ys)
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else None


def nice_ticks(lo: float, hi: float, n: int = 7) -> List[float]:
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return [lo] if math.isfinite(lo) else []
    span = hi - lo
    raw = span / max(n - 1, 1)
    if raw <= 0 or not math.isfinite(raw):
        return [lo]
    try:
        mag = 10.0 ** math.floor(math.log10(raw))
    except (ValueError, OverflowError):
        return [lo]
    if not math.isfinite(mag) or mag <= 0:
        return [lo]
    step = mag
    for s in (mag, mag * 2, mag * 2.5, mag * 5, mag * 10):
        if span / s <= n + 1:
            step = s
            break
    if not math.isfinite(step) or step <= 0:
        return [lo]
    try:
        start = math.floor(lo / step) * step
    except (OverflowError, ValueError):
        return [lo]
    ticks: List[float] = []
    v = start
    while v <= hi + step * 0.001 and len(ticks) < _NICE_TICKS_MAX:
        if v >= lo - step * 0.001:
            ticks.append(round(v, 10))
        nv = round(v + step, 10)
        if nv <= v:
            break
        v = nv
    return ticks


def nice_log_ticks(lo: float, hi: float) -> List[float]:
    if lo <= 0 or hi <= 0 or lo >= hi:
        return []
    lo_e = math.floor(math.log10(lo))
    hi_e = math.ceil(math.log10(hi))
    ticks = []
    for e in range(int(lo_e), int(hi_e) + 1):
        for m in (1, 2, 5):
            v = m * 10.0 ** e
            if lo <= v <= hi:
                ticks.append(v)
    return ticks if ticks else [lo, hi]


def to_log(v: float) -> float:
    return math.log10(v) if v > 0 else float('-inf')


def decimated(xs: List[float], ys: List[float], max_pts: int) -> Tuple[List[float], List[float]]:
    n = len(xs)
    if n <= max_pts:
        return xs, ys
    step = n / max_pts
    indices = [int(i * step) for i in range(max_pts)]
    indices[-1] = n - 1
    return [xs[i] for i in indices], [ys[i] for i in indices]
