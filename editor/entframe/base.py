# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.maths.math3d import Vec3


def _world_scale_factor(t) -> float:
    try:
        m = t.world_matrix._d
        sx = float(m[0, 0] * m[0, 0] + m[1, 0] * m[1, 0] + m[2, 0] * m[2, 0]) ** 0.5
        sy = float(m[0, 1] * m[0, 1] + m[1, 1] * m[1, 1] + m[2, 1] * m[2, 1]) ** 0.5
        sz = float(m[0, 2] * m[0, 2] + m[1, 2] * m[1, 2] + m[2, 2] * m[2, 2]) ** 0.5
        ms = sx
        if sy > ms:
            ms = sy
        if sz > ms:
            ms = sz
        if ms > 1e-08:
            return float(ms)
    except Exception:
        pass
    try:
        s = t.local_scale
        ms = float(s.x)
        if float(s.y) > ms:
            ms = float(s.y)
        if float(s.z) > ms:
            ms = float(s.z)
        if ms > 1e-08:
            return float(ms)
    except Exception:
        pass
    return 1.0


def _vec_len(v) -> float:
    try:
        return float(v.length())
    except Exception:
        pass
    try:
        return float((float(v[0]) * float(v[0]) + float(v[1]) * float(v[1]) + float(v[2]) * float(v[2])) ** 0.5)
    except Exception:
        pass
    try:
        return float((float(v[0]) * float(v[0]) + float(v[1]) * float(v[1])) ** 0.5)
    except Exception:
        pass
    try:
        return abs(float(v))
    except Exception:
        pass
    return 0.0


def _transform_local_point(t, lx: float, ly: float, lz: float):
    try:
        m = t.world_matrix._d
        x = float(lx * m[0, 0] + ly * m[1, 0] + lz * m[2, 0] + m[3, 0])
        y = float(lx * m[0, 1] + ly * m[1, 1] + lz * m[2, 1] + m[3, 1])
        z = float(lx * m[0, 2] + ly * m[1, 2] + lz * m[2, 2] + m[3, 2])
        return Vec3(x, y, z)
    except Exception:
        pass
    try:
        return t.position
    except Exception:
        return Vec3.zero()


def _resolve_meshes(renderer):
    if renderer is not None:
        try:
            m = getattr(renderer, "_meshes", None)
            if isinstance(m, dict):
                return m
        except Exception:
            pass
        try:
            ml = getattr(renderer, "_mesh_loader", None)
            if ml is not None:
                m = getattr(ml, "_meshes", None)
                if isinstance(m, dict):
                    return m
        except Exception:
            pass
    try:
        from core.engine.eng import Engine as _Eng
        _eng = _Eng.instance()
        _r = getattr(_eng, "_renderer", None) if _eng is not None else None
        if _r is None and _eng is not None:
            _vp = getattr(_eng, "viewport", None)
            if _vp is not None:
                _r = getattr(_vp, "_renderer", None)
        if _r is not None:
            m = getattr(_r, "_meshes", None)
            if isinstance(m, dict):
                return m
            ml = getattr(_r, "_mesh_loader", None)
            if ml is not None:
                m = getattr(ml, "_meshes", None)
                if isinstance(m, dict):
                    return m
    except Exception:
        pass
    return None


def _mesh_data_radius(md) -> float:
    try:
        r = float(getattr(md, "bounding_radius", 0.0))
        if r > 1e-08 and r < 1e12:
            return float(r)
    except Exception:
        pass
    try:
        mn = getattr(md, "aabb_min", None)
        mx = getattr(md, "aabb_max", None)
        if mn is not None and mx is not None:
            dx = float(mx[0] - mn[0])
            dy = float(mx[1] - mn[1])
            dz = float(mx[2] - mn[2])
            return float((dx * dx + dy * dy + dz * dz) ** 0.5 * 0.5)
    except Exception:
        pass
    return 0.0


def _mesh_data_local_center(md):
    try:
        mn = getattr(md, "aabb_min", None)
        mx = getattr(md, "aabb_max", None)
        if mn is not None and mx is not None:
            return float((mx[0] + mn[0]) * 0.5), float((mx[1] + mn[1]) * 0.5), float((mx[2] + mn[2]) * 0.5)
    except Exception:
        pass
    return 0.0, 0.0, 0.0


def _find_mesh_data(comp, meshes):
    try:
        md = getattr(comp, "_mesh_data", None)
        if md is not None:
            try:
                r = _mesh_data_radius(md)
            except Exception:
                r = 0.0
            if r > 1e-08:
                return md
            try:
                mn = getattr(md, "aabb_min", None)
                if mn is not None:
                    return md
            except Exception:
                pass
    except Exception:
        pass
    if meshes is None:
        return None
    try:
        name = getattr(comp, "mesh_name", "") or ""
        path = getattr(comp, "mesh_path", "") or ""
        if name and name in meshes:
            return meshes.get(name)
        if path:
            if path in meshes:
                return meshes.get(path)
            for k, v in meshes.items():
                try:
                    base = k.split("|")[0]
                    if base == path or (name and base == name):
                        return v
                except Exception:
                    continue
    except Exception:
        pass
    return None
