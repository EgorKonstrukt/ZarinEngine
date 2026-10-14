# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.maths.math3d import Mat4, Vec3


def _fallback_game_view(scene, aspect):
    try:
        import math
        try:
            ents = scene._entities.values()
        except Exception:
            return None
        sx = sy = sz = 0.0
        n = 0
        pts = []
        for e in ents:
            try:
                if not e.active:
                    continue
                tr = e.transform
                if tr is None:
                    continue
                p = tr.position
                x = float(p.x)
                y = float(p.y)
                z = float(p.z)
                sx += x
                sy += y
                sz += z
                n += 1
                pts.append((x, y, z))
            except Exception:
                continue
        if n <= 0:
            return None
        cx = sx / n
        cy = sy / n
        cz = sz / n
        radius = 2.0
        try:
            for x, y, z in pts:
                dx = x - cx
                dy = y - cy
                dz = z - cz
                d = math.sqrt(dx * dx + dy * dy + dz * dz)
                if d > radius:
                    radius = d
            radius = max(1.0, radius + 1.0)
        except Exception:
            radius = 5.0
        fov = 60.0
        try:
            dist = radius / max(0.05, math.tan(math.radians(fov) * 0.5)) * 1.3
        except Exception:
            dist = radius * 2.5
        dist = max(dist, 0.5)
        il = 1.0 / math.sqrt(0.62 * 0.62 + 0.5 * 0.5 + 0.72 * 0.72)
        dx = 0.62 * il
        dy = 0.5 * il
        dz = 0.72 * il
        pos = Vec3(cx + dx * dist, cy + dy * dist, cz + dz * dist)
        center = Vec3(cx, cy, cz)
        view = Mat4.look_at(pos, center, Vec3(0.0, 1.0, 0.0))
        near = max(0.01, dist * 0.01)
        far = max(1000.0, dist + radius * 20.0)
        try:
            a = max(0.1, float(aspect))
        except Exception:
            a = 16.0 / 9.0
        proj = Mat4.perspective(fov, a, near, far)
        return view, proj, pos, near, far
    except Exception:
        return None
