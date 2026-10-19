# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, as_float
from core.assets.importer.stepp.place import point_of


def expand_knots(mults, knots, degree: int, count: int):
    try:
        mults = [int(m) for m in mults]
        knots = [float(as_float(k)) for k in knots]
    except (TypeError, ValueError):
        return None
    if len(mults) != len(knots) or sum(mults) != count + degree + 1:
        return None
    full: list[float] = []
    for m, k in zip(mults, knots):
        full.extend([k] * m)
    return np.array(full, dtype=np.float64)


def uniform_knots(count: int, degree: int):
    inner = count - degree - 1
    if inner <= 0:
        return np.array([0.0] * (degree + 1) + [1.0] * (degree + 1), dtype=np.float64)
    seq = [0.0] * (degree + 1)
    seq.extend([float(i) / float(inner) for i in range(1, inner)])
    seq.extend([1.0] * (degree + 1))
    return np.array(seq, dtype=np.float64)


def _basis_spans(us: np.ndarray, degree: int, knots: np.ndarray):
    n = len(knots) - degree - 2
    spans = np.searchsorted(knots, us, side="right") - 1
    spans = np.clip(spans, degree, n)
    return spans


def nurbs_basis(us: np.ndarray, degree: int, knots: np.ndarray):
    us = np.asarray(us, dtype=np.float64).ravel()
    npts = us.shape[0]
    spans = _basis_spans(us, degree, knots)
    left = np.zeros((npts, degree + 1), dtype=np.float64)
    right = np.zeros((npts, degree + 1), dtype=np.float64)
    temp = np.zeros((npts, degree + 1), dtype=np.float64)
    ndu = np.zeros((npts, degree + 1, degree + 1), dtype=np.float64)
    ndu[:, 0, 0] = 1.0
    for j in range(1, degree + 1):
        left[:, j] = us - knots[spans - j + 1 - 1 + 1]
        right[:, j] = knots[spans + j] - us
        saved = np.zeros(npts, dtype=np.float64)
        for r in range(j):
            ndu_r = ndu[:, r, j - 1]
            denom = right[:, r + 1] + left[:, j - r]
            temp[:, r] = np.where(np.abs(denom) > 1e-300, ndu_r / np.where(np.abs(denom) > 1e-300, denom, 1.0), 0.0)
            ndu[:, r, j] = saved + right[:, r + 1] * temp[:, r]
            saved = left[:, j - r] * temp[:, r]
        ndu[:, j, j] = saved
    out = np.zeros((npts, degree + 1), dtype=np.float64)
    for j in range(degree + 1):
        out[:, j] = ndu[:, j, degree]
    return spans, out


def nurbs_eval_points(cps: np.ndarray, ku: np.ndarray, kv: np.ndarray, du: int, dv: int, us: np.ndarray, vs: np.ndarray, weights=None):
    us = np.asarray(us, dtype=np.float64).ravel()
    vs = np.asarray(vs, dtype=np.float64).ravel()
    spu, bu = nurbs_basis(us, du, ku)
    spv, bv = nurbs_basis(vs, dv, kv)
    nu = cps.shape[0]
    nv = cps.shape[1]
    iu = np.clip(spu - du, 0, nu - 1)
    iv = np.clip(spv - dv, 0, nv - 1)
    uu = np.arange(du + 1)[None, :] + iu[:, None]
    vv = np.arange(dv + 1)[None, :] + iv[:, None]
    uu = np.clip(uu, 0, nu - 1)
    vv = np.clip(vv, 0, nv - 1)
    patch = cps[uu[:, :, None], vv[:, None, :], :]
    if weights is not None:
        w = weights[uu[:, :, None], vv[:, None, :]]
        patch = patch * w[..., None]
        wb = np.einsum("pi,pij,pj->p", bu, w, bv)
        num = np.einsum("pi,pijc,pj->pc", bu, patch, bv)
        out = num / np.maximum(wb[..., None], 1e-300)
        return out.reshape(-1, 3)
    num = np.einsum("pi,pijc,pj->pc", bu, patch, bv)
    return num.reshape(-1, 3)


def nurbs_eval_curve(cps: np.ndarray, ku: np.ndarray, degree: int, ts: np.ndarray, weights=None):
    ts = np.asarray(ts, dtype=np.float64).ravel()
    spans, bu = nurbs_basis(ts, degree, ku)
    n = cps.shape[0]
    idx = np.clip(spans - degree, 0, n - 1)
    ii = np.arange(degree + 1)[None, :] + idx[:, None]
    ii = np.clip(ii, 0, n - 1)
    patch = cps[ii, :]
    if weights is not None:
        w = weights[ii]
        wb = np.einsum("pi,pi->p", bu, w)
        num = np.einsum("pi,pic->pc", bu, patch * w[..., None])
        return num / np.maximum(wb[:, None], 1e-300)
    return np.einsum("pi,pic->pc", bu, patch)


class NurbsSurface:
    __slots__ = ("cps", "ku", "kv", "du", "dv", "weights", "periods", "domain")

    def __init__(self, cps, ku, kv, du, dv, weights=None):
        self.cps = np.ascontiguousarray(cps, dtype=np.float64)
        self.ku = np.ascontiguousarray(ku, dtype=np.float64)
        self.kv = np.ascontiguousarray(kv, dtype=np.float64)
        self.du = int(du)
        self.dv = int(dv)
        self.weights = None if weights is None else np.ascontiguousarray(weights, dtype=np.float64)
        self.periods = (0.0, 0.0)
        self.domain = (float(ku[du]), float(ku[len(ku) - du - 1]), float(kv[dv]), float(kv[len(kv) - dv - 1]))

    def eval(self, u, v):
        return nurbs_eval_points(self.cps, self.ku, self.kv, self.du, self.dv, u, v, self.weights)

    def invert(self, pts):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
        n = pts.shape[0]
        u0, u1, v0, v1 = self.domain
        su = float(np.linalg.norm(self.cps[-1, 0] - self.cps[0, 0])) + 1e-12
        best_u = np.full(n, (u0 + u1) * 0.5)
        best_v = np.full(n, (v0 + v1) * 0.5)
        best_d = np.full(n, np.inf)
        for gu in np.linspace(u0, u1, 5):
            for gv in np.linspace(v0, v1, 5):
                q = self.eval(np.array([gu]), np.array([gv]))[0]
                d = np.sum((pts - q[None, :]) ** 2, axis=1)
                better = d < best_d
                best_d = np.where(better, d, best_d)
                best_u = np.where(better, gu, best_u)
                best_v = np.where(better, gv, best_v)
        u = best_u.copy()
        v = best_v.copy()
        for _ in range(4):
            q = self.eval(u, v)
            r = pts - q
            e = 1e-4 * su
            qu = (self.eval(u + e, v) - q) / e
            qv = (self.eval(u, v + e) - q) / e
            a11 = np.einsum("ij,ij->i", qu, qu) + 1e-18
            a12 = np.einsum("ij,ij->i", qu, qv)
            a22 = np.einsum("ij,ij->i", qv, qv) + 1e-18
            b1 = np.einsum("ij,ij->i", qu, r)
            b2 = np.einsum("ij,ij->i", qv, r)
            det = a11 * a22 - a12 * a12
            det = np.where(np.abs(det) < 1e-24, 1e-24, det)
            du_ = (b1 * a22 - b2 * a12) / det
            dv_ = (b2 * a11 - b1 * a12) / det
            step = np.minimum(1.0, 0.25 * su / (np.abs(du_) + np.abs(dv_) + 1e-18))
            u = u + du_ * step
            v = v + dv_ * step
        return u, v


def _control_grid(model: StepModel, value):
    ent = deref(model, value)
    if not isinstance(ent, (list, tuple)):
        return None
    grid = []
    for row in ent:
        if not isinstance(row, (list, tuple)):
            return None
        pts = []
        for item in row:
            pts.append(point_of(model, item))
        grid.append(pts)
    if not grid:
        return None
    try:
        return np.array(grid, dtype=np.float64)
    except (TypeError, ValueError):
        return None


def _flat_floats(value):
    if not isinstance(value, (list, tuple)):
        return None
    out = []
    for v in value:
        if isinstance(v, bool):
            return None
        if not isinstance(v, (int, float)):
            return None
        out.append(float(v))
    return out


def make_nurbs_surface(model: StepModel, args: list):
    try:
        if len(args) < 4:
            return None
        du = int(as_float(args[1]))
        dv = int(as_float(args[2]))
        cps = _control_grid(model, args[3])
        if cps is None or cps.ndim != 3 or cps.shape[2] != 3:
            return None
        nu, nv = cps.shape[0], cps.shape[1]
        weights = None
        ku = None
        kv = None
        for a in args[4:]:
            if isinstance(a, tuple) and len(a) == 2 and a[0] in ("ref", "typed", "enum", "name", "omit"):
                continue
            if a is None:
                continue
            if not isinstance(a, (list, tuple)):
                continue
            if len(a) == 0:
                continue
            first = a[0]
            if isinstance(first, (list, tuple)):
                grid = []
                ok = True
                for row in a:
                    if not isinstance(row, (list, tuple)):
                        ok = False
                        break
                    try:
                        grid.append([float(as_float(v)) for v in row])
                    except (TypeError, ValueError):
                        ok = False
                        break
                if ok and len(grid) == nu and all(len(r) == nv for r in grid):
                    weights = np.array(grid, dtype=np.float64)
                continue
            nums = _flat_floats(a)
            if nums is None or len(nums) < 2:
                continue
            ints = None
            try:
                ints = [int(v) for v in nums]
            except (TypeError, ValueError):
                ints = None
            if ints is not None and all(float(x) == y for x, y in zip(ints, nums)) and sum(ints) == nu + du + 1 and ku is None:
                ku = (ints, None)
                continue
            if ints is not None and all(float(x) == y for x, y in zip(ints, nums)) and sum(ints) == nv + dv + 1 and kv is None:
                kv = (ints, None)
                continue
            if ku is not None and isinstance(ku, tuple) and ku[1] is None and len(nums) == len(ku[0]):
                ku = expand_knots(ku[0], nums, du, nu)
                continue
            if kv is not None and isinstance(kv, tuple) and kv[1] is None and len(nums) == len(kv[0]):
                kv = expand_knots(kv[0], nums, dv, nv)
                continue
        if ku is None or isinstance(ku, tuple):
            ku = uniform_knots(nu, du)
        if kv is None or isinstance(kv, tuple):
            kv = uniform_knots(nv, dv)
        ku = np.ascontiguousarray(ku, dtype=np.float64)
        kv = np.ascontiguousarray(kv, dtype=np.float64)
        if len(ku) != nu + du + 1:
            ku = uniform_knots(nu, du)
        if len(kv) != nv + dv + 1:
            kv = uniform_knots(nv, dv)
        return NurbsSurface(cps, ku, kv, du, dv, weights)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
