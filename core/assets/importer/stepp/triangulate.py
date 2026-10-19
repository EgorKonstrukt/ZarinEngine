# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def signed_area(ring) -> float:
    s = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s * 0.5


def _point_in_triangle(px, py, ax, ay, bx, by, cx, cy) -> bool:
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    neg = (d1 < 0.0) or (d2 < 0.0) or (d3 < 0.0)
    pos = (d1 > 0.0) or (d2 > 0.0) or (d3 > 0.0)
    return not (neg and pos)


def _seg_intersect(ax, ay, bx, by, cx, cy, dx, dy) -> bool:
    d = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
    if abs(d) < 1e-300:
        return False
    t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / d
    u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / d
    eps = 1e-9
    return eps < t < 1.0 - eps and eps < u < 1.0 - eps


def _clean_ring(ring: list) -> list:
    if len(ring) < 3:
        return list(ring)
    tol2 = 1e-18
    out = []
    for p in ring:
        if not out:
            out.append(p)
            continue
        dx = p[0] - out[-1][0]
        dy = p[1] - out[-1][1]
        if dx * dx + dy * dy > tol2:
            out.append(p)
    if len(out) >= 2:
        dx = out[0][0] - out[-1][0]
        dy = out[0][1] - out[-1][1]
        if dx * dx + dy * dy <= tol2:
            out.pop()
    return out


def _ear_clip(ring: list) -> list:
    pts = _clean_ring(ring)
    return _ear_clip_core(pts)


def _ear_clip_core(pts: list) -> list:
    n = len(pts)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    if signed_area(pts) < 0.0:
        pts = pts[::-1]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    import math as _math
    cells = max(1, int(_math.ceil(_math.sqrt(float(n)))))
    cwx = (maxx - minx) / cells + 1e-300
    cwy = (maxy - miny) / cells + 1e-300
    buckets: dict[tuple[int, int], list] = {}
    for ii, (px, py) in enumerate(zip(xs, ys)):
        key = (int((px - minx) / cwx), int((py - miny) / cwy))
        buckets.setdefault(key, []).append(ii)

    def _blocked(ax, ay, bx, by, cx, cy, skip) -> bool:
        lox = ax
        if bx < lox:
            lox = bx
        if cx < lox:
            lox = cx
        hix = ax
        if bx > hix:
            hix = bx
        if cx > hix:
            hix = cx
        loy = ay
        if by < loy:
            loy = by
        if cy < loy:
            loy = cy
        hiy = ay
        if by > hiy:
            hiy = by
        if cy > hiy:
            hiy = cy
        kx0 = int((lox - minx) / cwx)
        kx1 = int((hix - minx) / cwx)
        ky0 = int((loy - miny) / cwy)
        ky1 = int((hiy - miny) / cwy)
        for kx in range(kx0, kx1 + 1):
            for ky in range(ky0, ky1 + 1):
                for j in buckets.get((kx, ky), ()):
                    if j == skip[0] or j == skip[1] or j == skip[2]:
                        continue
                    px = xs[j]
                    if px == ax and ys[j] == ay:
                        continue
                    if px == bx and ys[j] == by:
                        continue
                    if px == cx and ys[j] == cy:
                        continue
                    if px < lox or px > hix:
                        continue
                    py = ys[j]
                    if py < loy or py > hiy:
                        continue
                    if _point_in_triangle(px, py, ax, ay, bx, by, cx, cy):
                        return True
        return False

    idx = list(range(len(pts)))
    tris: list[tuple[int, int, int]] = []
    guard = n * n + 8
    while len(idx) > 3 and guard > 0:
        guard -= 1
        found = -1
        m = len(idx)
        for k in range(m):
            i0 = idx[(k - 1) % m]
            i1 = idx[k]
            i2 = idx[(k + 1) % m]
            ax, ay = pts[i0]
            bx, by = pts[i1]
            cx, cy = pts[i2]
            if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= 1e-12:
                continue
            if not _blocked(ax, ay, bx, by, cx, cy, (i0, i1, i2)):
                found = k
                break
        if found < 0:
            break
        i0 = idx[(found - 1) % len(idx)]
        i1 = idx[found]
        i2 = idx[(found + 1) % len(idx)]
        tris.append((i0, i1, i2))
        del idx[found]
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
        return tris
    if not tris:
        for k in range(1, len(pts) - 1):
            tris.append((0, k, k + 1))
    return tris
    if not tris:
        for k in range(1, len(pts) - 1):
            tris.append((0, k, k + 1))
    return tris


def _seg_blocked(ax, ay, bx, by, blockers) -> bool:
    for k, (cx, cy, dx, dy) in enumerate(blockers):
        if _seg_intersect(ax, ay, bx, by, cx, cy, dx, dy):
            return True
    return False


def _bridge_holes(outer: list, holes: list) -> list:
    pts = [(p, ("o", i)) for i, p in enumerate(outer)]

    def _blockers_for(hole, hx):
        segs = []
        n = len(pts)
        for i in range(n):
            q0 = pts[i][0]
            q1 = pts[(i + 1) % n][0]
            segs.append((q0[0], q0[1], q1[0], q1[1]))
        for other in holes:
            if other is hole or len(other) < 3:
                continue
            m2 = len(other)
            for i in range(m2):
                q0 = other[i]
                q1 = other[(i + 1) % m2]
                segs.append((q0[0], q0[1], q1[0], q1[1]))
        m = len(hole)
        for i in range(m):
            if i == hx or (i + 1) % m == hx:
                continue
            q0 = hole[i]
            q1 = hole[(i + 1) % m]
            segs.append((q0[0], q0[1], q1[0], q1[1]))
        return segs

    for hnum, hole in enumerate(holes):
        if len(hole) < 3:
            continue
        hx = max(range(len(hole)), key=lambda i: hole[i][0])
        hx_p = hole[hx]
        blockers = _blockers_for(hole, hx)
        best = -1
        best_d2 = 0.0
        for i in range(len(pts)):
            p, src = pts[i]
            if src[0] != "o":
                continue
            if p[1] > hx_p[1]:
                continue
            nxt = pts[(i + 1) % len(pts)][0]
            dx = p[0] - hx_p[0]
            dy = p[1] - hx_p[1]
            d2 = dx * dx + dy * dy
            if best >= 0 and d2 >= best_d2:
                continue
            if _seg_blocked(hx_p[0], hx_p[1], p[0], p[1], blockers):
                continue
            if _seg_blocked(hx_p[0], hx_p[1], nxt[0], nxt[1], blockers):
                continue
            best = i
            best_d2 = d2
        if best < 0:
            for i in range(len(pts)):
                p, src = pts[i]
                if src[0] != "o":
                    continue
                nxt = pts[(i + 1) % len(pts)][0]
                dx = p[0] - hx_p[0]
                dy = p[1] - hx_p[1]
                d2 = dx * dx + dy * dy
                if best >= 0 and d2 >= best_d2:
                    continue
                if _seg_blocked(hx_p[0], hx_p[1], p[0], p[1], blockers):
                    continue
                if _seg_blocked(hx_p[0], hx_p[1], nxt[0], nxt[1], blockers):
                    continue
                best = i
                best_d2 = d2
        if best < 0:
            continue
        merged = pts[:best + 1]
        for k in range(len(hole) + 1):
            merged.append((hole[(hx + k) % len(hole)], ("h", hnum, (hx + k) % len(hole))))
        merged.extend(pts[best + 1:])
        pts = merged
    return pts


def _clip_half(poly: list, axis: int, bound: float, keep_le: bool) -> list:
    if len(poly) < 3:
        return list(poly)
    out: list = []
    n = len(poly)
    for i in range(n):
        cur = poly[i]
        prev = poly[(i - 1) % n]
        cv = cur[axis] - bound
        pv = prev[axis] - bound
        cin = cv <= 1e-12 if keep_le else cv >= -1e-12
        pin = pv <= 1e-12 if keep_le else pv >= -1e-12
        if cin:
            if not pin:
                t = pv / (pv - cv) if abs(pv - cv) > 1e-300 else 0.0
                t = min(1.0, max(0.0, t))
                out.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
            out.append(cur)
        elif pin:
            t = pv / (pv - cv) if abs(pv - cv) > 1e-300 else 0.0
            t = min(1.0, max(0.0, t))
            out.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
    return out


def _surf_metric(surf, u: float, v: float):
    try:
        q = surf.eval([u], [v])[0]
        e = 1e-3
        qu = (surf.eval([u + e], [v])[0] - q) / e
        qv = (surf.eval([u], [v + e])[0] - q) / e
        return float((qu[0] * qu[0] + qu[1] * qu[1] + qu[2] * qu[2]) ** 0.5), float((qv[0] * qv[0] + qv[1] * qv[1] + qv[2] * qv[2]) ** 0.5)
    except (TypeError, ValueError, IndexError):
        return 1.0, 1.0


def _split_face(outer: list, surf, tol: float, depth: int) -> list:
    if depth <= 0 or len(outer) < 3:
        return [outer]
    us = [p[0] for p in outer]
    vs = [p[1] for p in outer]
    u0, u1 = min(us), max(us)
    v0, v1 = min(vs), max(vs)
    try:
        su, sv = _surf_metric(surf, (u0 + u1) * 0.5, (v0 + v1) * 0.5)
    except (TypeError, ValueError):
        su, sv = 1.0, 1.0
    if su < 1e-300:
        su = 1.0
    if sv < 1e-300:
        sv = 1.0
    limit = max(12.0 * tol, 1e-9)
    eu = (u1 - u0) * su
    ev = (v1 - v0) * sv
    if max(eu, ev) <= limit:
        return [outer]
    if eu >= ev:
        lo = _clip_half(outer, 0, (u0 + u1) * 0.5, True)
        hi = _clip_half(outer, 0, (u0 + u1) * 0.5, False)
    else:
        lo = _clip_half(outer, 1, (v0 + v1) * 0.5, True)
        hi = _clip_half(outer, 1, (v0 + v1) * 0.5, False)
    if len(lo) < 3 or len(hi) < 3:
        return [outer]
    out = []
    out.extend(_split_face(lo, surf, tol, depth - 1))
    out.extend(_split_face(hi, surf, tol, depth - 1))
    return out


def triangulate_face(outer: list, holes: list, surf=None, tol: float = 0.0) -> tuple:
    if holes or surf is None or tol <= 0.0:
        return triangulate_with_holes(outer, holes)
    try:
        if bool(getattr(surf, "is_planar", False)):
            return triangulate_with_holes(outer, holes)
    except (TypeError, ValueError):
        pass
    outer_c = _clean_ring([(float(p[0]), float(p[1])) for p in outer])
    if len(outer_c) < 3 or abs(signed_area(outer_c)) < 1e-12:
        return [], []
    if signed_area(outer_c) < 0.0:
        outer_c = outer_c[::-1]
    pieces = _split_face(outer_c, surf, tol, 8)
    if len(pieces) <= 1:
        return triangulate_with_holes(outer, holes)
    verts: list = []
    tris: list = []
    for piece in pieces:
        pv, pt = triangulate_with_holes(piece, [])
        if not pt:
            continue
        base = len(verts)
        verts.extend(pv)
        for a, b, c in pt:
            tris.append((a + base, b + base, c + base))
    return verts, tris


def triangulate_with_holes(outer: list, holes: list) -> tuple:
    outer_c = _clean_ring([(float(p[0]), float(p[1])) for p in outer])
    if len(outer_c) < 3:
        return [], []
    holes_c = []
    for h in holes or []:
        hc = _clean_ring([(float(p[0]), float(p[1])) for p in h])
        if len(hc) >= 3 and abs(signed_area(hc)) > 1e-12:
            holes_c.append(hc)
    if abs(signed_area(outer_c)) < 1e-12:
        return [], []
    if signed_area(outer_c) < 0.0:
        outer_c = outer_c[::-1]
    fixed = []
    for hc in holes_c:
        if signed_area(hc) > 0.0:
            hc = hc[::-1]
        fixed.append(hc)
    verts = list(outer_c)
    for hc in fixed:
        verts.extend(hc)
    if not fixed:
        return verts, _ear_clip_core(verts)
    bridged = _bridge_holes(outer_c, fixed)
    bpts = [p for p, _s in bridged]
    raw = _ear_clip_core(bpts)
    no = len(outer_c)
    offs = [0]
    for hc in fixed:
        offs.append(offs[-1] + len(hc))
    tris: list[tuple[int, int, int]] = []
    for a, b, c in raw:
        sa = bridged[a][1]
        sb = bridged[b][1]
        sc = bridged[c][1]
        if sa[0] == "o":
            ia = sa[1]
        else:
            ia = no + offs[sa[1]] + sa[2]
        if sb[0] == "o":
            ib = sb[1]
        else:
            ib = no + offs[sb[1]] + sb[2]
        if sc[0] == "o":
            ic = sc[1]
        else:
            ic = no + offs[sc[1]] + sc[2]
        if len({ia, ib, ic}) == 3:
            tris.append((ia, ib, ic))
    return verts, tris
