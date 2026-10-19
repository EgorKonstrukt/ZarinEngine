# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from core.assets.importer.stepp.parser import StepModel, deref, as_float, is_true, first_part
from core.assets.importer.stepp.place import placement_of


class PlaneSurface:
    __slots__ = ("origin", "x", "y", "z", "periods", "is_planar")

    def __init__(self, origin, x, y, z):
        self.origin = origin
        self.x = x
        self.y = y
        self.z = z
        self.periods = (0.0, 0.0)
        self.is_planar = True

    def eval(self, u, v):
        u = np.asarray(u, dtype=np.float64).ravel()
        v = np.asarray(v, dtype=np.float64).ravel()
        return self.origin[None, :] + u[:, None] * self.x[None, :] + v[:, None] * self.y[None, :]

    def invert(self, pts):
        d = np.asarray(pts, dtype=np.float64).reshape(-1, 3) - self.origin[None, :]
        return d @ self.x, d @ self.y


class CylSurface:
    __slots__ = ("origin", "x", "y", "z", "r", "periods")

    def __init__(self, origin, x, y, z, r):
        self.origin = origin
        self.x = x
        self.y = y
        self.z = z
        self.r = max(float(r), 1e-12)
        self.periods = (2.0 * np.pi, 0.0)

    def eval(self, u, v):
        u = np.asarray(u, dtype=np.float64).ravel()
        v = np.asarray(v, dtype=np.float64).ravel()
        cu = np.cos(u)
        su = np.sin(u)
        return self.origin[None, :] + self.r * (cu[:, None] * self.x[None, :] + su[:, None] * self.y[None, :]) + v[:, None] * self.z[None, :]

    def invert(self, pts):
        d = np.asarray(pts, dtype=np.float64).reshape(-1, 3) - self.origin[None, :]
        return np.arctan2(d @ self.y, d @ self.x), d @ self.z


class ConeSurface:
    __slots__ = ("origin", "x", "y", "z", "r", "semi", "periods")

    def __init__(self, origin, x, y, z, r, semi):
        self.origin = origin
        self.x = x
        self.y = y
        self.z = z
        self.r = float(r)
        self.semi = float(semi)
        self.periods = (2.0 * np.pi, 0.0)

    def eval(self, u, v):
        u = np.asarray(u, dtype=np.float64).ravel()
        v = np.asarray(v, dtype=np.float64).ravel()
        rr = self.r + v * float(np.tan(self.semi))
        cu = np.cos(u)
        su = np.sin(u)
        return self.origin[None, :] + rr[:, None] * (cu[:, None] * self.x[None, :] + su[:, None] * self.y[None, :]) + v[:, None] * self.z[None, :]

    def invert(self, pts):
        d = np.asarray(pts, dtype=np.float64).reshape(-1, 3) - self.origin[None, :]
        return np.arctan2(d @ self.y, d @ self.x), d @ self.z


class SphereSurface:
    __slots__ = ("origin", "x", "y", "z", "r", "periods")

    def __init__(self, origin, x, y, z, r):
        self.origin = origin
        self.x = x
        self.y = y
        self.z = z
        self.r = max(float(r), 1e-12)
        self.periods = (2.0 * np.pi, 0.0)

    def eval(self, u, v):
        u = np.asarray(u, dtype=np.float64).ravel()
        v = np.asarray(v, dtype=np.float64).ravel()
        cu = np.cos(u)
        su = np.sin(u)
        cv = np.cos(v)
        sv = np.sin(v)
        return self.origin[None, :] + self.r * (cv[:, None] * (cu[:, None] * self.x[None, :] + su[:, None] * self.y[None, :]) + sv[:, None] * self.z[None, :])

    def invert(self, pts):
        d = np.asarray(pts, dtype=np.float64).reshape(-1, 3) - self.origin[None, :]
        n = np.linalg.norm(d, axis=1)
        n = np.maximum(n, 1e-300)
        dn = d / n[:, None]
        return np.arctan2(dn @ self.y, dn @ self.x), np.arcsin(np.clip(dn @ self.z, -1.0, 1.0))


class TorusSurface:
    __slots__ = ("origin", "x", "y", "z", "major", "minor", "periods")

    def __init__(self, origin, x, y, z, major, minor):
        self.origin = origin
        self.x = x
        self.y = y
        self.z = z
        self.major = max(float(major), 1e-12)
        self.minor = max(float(minor), 1e-12)
        self.periods = (2.0 * np.pi, 2.0 * np.pi)

    def eval(self, u, v):
        u = np.asarray(u, dtype=np.float64).ravel()
        v = np.asarray(v, dtype=np.float64).ravel()
        cu = np.cos(u)
        su = np.sin(u)
        cv = np.cos(v)
        sv = np.sin(v)
        rr = self.major + self.minor * cv
        return self.origin[None, :] + rr[:, None] * (cu[:, None] * self.x[None, :] + su[:, None] * self.y[None, :]) + (self.minor * sv)[:, None] * self.z[None, :]

    def invert(self, pts):
        d = np.asarray(pts, dtype=np.float64).reshape(-1, 3) - self.origin[None, :]
        u = np.arctan2(d @ self.y, d @ self.x)
        radial = np.sqrt((d @ self.x) ** 2 + (d @ self.y) ** 2) - self.major
        return u, np.arctan2(d @ self.z, radial)


class TrimmedSurface:
    __slots__ = ("basis", "u0", "u1", "v0", "v1", "usense", "vsense", "periods", "domain", "is_planar")

    def __init__(self, basis, u0, u1, v0, v1, usense=True, vsense=True):
        self.basis = basis
        self.is_planar = bool(getattr(basis, "is_planar", False))
        self.u0 = min(float(u0), float(u1))
        self.u1 = max(float(u0), float(u1))
        self.v0 = min(float(v0), float(v1))
        self.v1 = max(float(v0), float(v1))
        self.usense = bool(usense)
        self.vsense = bool(vsense)
        self.periods = getattr(basis, "periods", (0.0, 0.0))
        self.domain = (self.u0, self.u1, self.v0, self.v1)

    def eval(self, u, v):
        return self.basis.eval(u, v)

    def invert(self, pts):
        return self.basis.invert(pts)


class OffsetSurface:
    __slots__ = ("basis", "offset", "periods", "domain")

    def __init__(self, basis, offset):
        self.basis = basis
        self.offset = float(offset)
        self.periods = getattr(basis, "periods", (0.0, 0.0))
        self.domain = getattr(basis, "domain", None)

    def eval(self, u, v):
        q = self.basis.eval(u, v)
        e = 1e-4
        u = np.asarray(u, dtype=np.float64).ravel()
        v = np.asarray(v, dtype=np.float64).ravel()
        qu = (self.basis.eval(u + e, v) - q) / e
        qv = (self.basis.eval(u, v + e) - q) / e
        n = np.cross(qu, qv)
        l = np.linalg.norm(n, axis=1, keepdims=True)
        n = n / np.maximum(l, 1e-300)
        return q + self.offset * n

    def invert(self, pts):
        return self.basis.invert(pts)


def make_surface(model: StepModel, value):
    name, args = first_part(model, value, "PLANE", "CYLINDRICAL_SURFACE", "CONICAL_SURFACE",
                            "SPHERICAL_SURFACE", "TOROIDAL_SURFACE", "B_SPLINE_SURFACE",
                            "B_SPLINE_SURFACE_WITH_KNOTS", "RATIONAL_B_SPLINE_SURFACE",
                            "QUASI_UNIFORM_SURFACE", "UNIFORM_SURFACE", "BEZIER_SURFACE",
                            "RECTANGULAR_TRIMMED_SURFACE", "OFFSET_SURFACE")
    if name is None:
        return None
    try:
        if name == "PLANE" and len(args) >= 2:
            o, x, y, z = placement_of(model, args[1])
            return PlaneSurface(o, x, y, z)
        if name == "CYLINDRICAL_SURFACE" and len(args) >= 3:
            o, x, y, z = placement_of(model, args[1])
            return CylSurface(o, x, y, z, as_float(args[2], 1.0))
        if name == "CONICAL_SURFACE" and len(args) >= 4:
            o, x, y, z = placement_of(model, args[1])
            return ConeSurface(o, x, y, z, as_float(args[2], 0.0), as_float(args[3], 0.0))
        if name == "SPHERICAL_SURFACE" and len(args) >= 3:
            o, x, y, z = placement_of(model, args[1])
            return SphereSurface(o, x, y, z, as_float(args[2], 1.0))
        if name == "TOROIDAL_SURFACE" and len(args) >= 4:
            o, x, y, z = placement_of(model, args[1])
            return TorusSurface(o, x, y, z, as_float(args[2], 1.0), as_float(args[3], 1.0))
        if name in ("B_SPLINE_SURFACE", "B_SPLINE_SURFACE_WITH_KNOTS", "RATIONAL_B_SPLINE_SURFACE",
                    "QUASI_UNIFORM_SURFACE", "UNIFORM_SURFACE", "BEZIER_SURFACE"):
            from core.assets.importer.stepp.nurbs import make_nurbs_surface
            return make_nurbs_surface(model, args)
        if name == "RECTANGULAR_TRIMMED_SURFACE" and len(args) >= 8:
            basis = make_surface(model, args[1])
            if basis is None:
                return None
            return TrimmedSurface(basis, as_float(args[2]), as_float(args[3]), as_float(args[4]), as_float(args[5]), is_true(args[6]) if len(args) > 6 else True, is_true(args[7]) if len(args) > 7 else True)
        if name == "OFFSET_SURFACE" and len(args) >= 4:
            basis = make_surface(model, args[1])
            if basis is None:
                return None
            return OffsetSurface(basis, as_float(args[2]))
    except (TypeError, ValueError, IndexError):
        return None
    return None
