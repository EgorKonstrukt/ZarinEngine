# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations


def screen_ray(camera, px: float, py: float, w: float, h: float):
    try:
        from core.maths.math3d import Vec3

        if w < 1:
            w = 1
        if h < 1:
            h = 1
        nx = (float(px) / float(w)) * 2.0 - 1.0
        ny = 1.0 - (float(py) / float(h)) * 2.0
        try:
            view = camera.get_view_matrix()
        except Exception:
            return (None, None)
        try:
            proj = camera.get_projection_matrix(float(w) / max(1.0, float(h)))
        except Exception:
            try:
                proj = camera.get_projection_matrix(float(w / max(1, h)))
            except Exception:
                return (None, None)
        try:
            vp = view * proj
            inv = vp.inverted()
        except Exception:
            return (None, None)
        import numpy as np

        def _unproject(x, y, z):
            v = np.array([x, y, z, 1.0], dtype=np.float64)
            out = v @ inv._d
            ww = out[3]
            if abs(ww) < 1e-9:
                return None
            return Vec3(float(out[0] / ww), float(out[1] / ww), float(out[2] / ww))

        near_p = _unproject(nx, ny, -1.0)
        far_p = _unproject(nx, ny, 1.0)
        if near_p is None or far_p is None:
            return (None, None)
        dx = float(far_p.x - near_p.x)
        dy = float(far_p.y - near_p.y)
        dz = float(far_p.z - near_p.z)
        ln = (dx * dx + dy * dy + dz * dz) ** 0.5
        if ln < 1e-9:
            return (None, None)
        direction = Vec3(dx / ln, dy / ln, dz / ln)
        try:
            origin = camera.position
        except Exception:
            origin = near_p
        return (origin, direction)
    except Exception:
        return (None, None)


def pick_view(views: list, origin, direction):
    best = None
    best_u = 0.0
    best_v = 0.0
    best_t = float("inf")
    if origin is None or direction is None:
        return (None, 0.0, 0.0, 0.0)
    for comp in views:
        try:
            if not bool(getattr(comp, "interactive", True)):
                continue
            ent = getattr(comp, "_entity", None)
            if ent is not None and not getattr(ent, "active", True):
                continue
            if not getattr(comp, "enabled", True):
                continue
            hit, u, v, t = comp.intersect_ray(origin, direction)
            if not hit:
                continue
            if t < best_t:
                best = comp
                best_u = float(u)
                best_v = float(v)
                best_t = float(t)
        except Exception:
            continue
    return (best, best_u, best_v, best_t)


def resolve_camera(engine, viewport):
    try:
        if viewport is not None:
            cam = getattr(viewport, "_cam", None)
            if cam is not None:
                return cam
            try:
                fn = getattr(viewport, "get_camera", None)
                if callable(fn):
                    cam = fn()
                    if cam is not None:
                        return cam
            except Exception:
                pass
    except Exception:
        pass
    try:
        if engine is not None:
            vp = getattr(engine, "viewport", None)
            if vp is not None:
                cam = getattr(vp, "_cam", None)
                if cam is not None:
                    return cam
    except Exception:
        pass
    try:
        if engine is not None and getattr(engine, "scene", None) is not None:
            from core.components.rendering.cameras.camera import Camera

            ents = engine.scene.get_entities_with_component(Camera)
            for ent in ents:
                try:
                    if not ent.active:
                        continue
                    c = ent.get_component(Camera)
                    if c is not None and c.enabled:
                        return c
                except Exception:
                    continue
    except Exception:
        pass
    return None
