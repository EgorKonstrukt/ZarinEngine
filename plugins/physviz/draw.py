# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
_TAG = "physics_visualisation"
_BOX_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
_REF_X = np.array([1.0, 0.0, 0.0], dtype=np.float32)
_REF_Y = np.array([0.0, 1.0, 0.0], dtype=np.float32)
class PhysVizDrawMixin:
    def _entity_center(self, scene, eid):
        if not eid:
            return None
        try:
            ent = scene.get_entity(eid)
        except Exception:
            return None
        if ent is None:
            return None
        try:
            comps = getattr(ent, "_components", None)
            tr = comps.get("Transform", None) if comps else None
            if tr is None:
                return None
            p = tr.position
            return (float(p.x), float(p.y), float(p.z))
        except Exception:
            return None
    def _seg(self, sx, sy, sz, ex, ey, ez, color, off):
        try:
            self._ensure_segcap(off + 1)
            self._S[off, 0] = sx
            self._S[off, 1] = sy
            self._S[off, 2] = sz
            self._E[off, 0] = ex
            self._E[off, 1] = ey
            self._E[off, 2] = ez
            self._C[off] = color
            return off + 1
        except Exception:
            return off
    def _cross(self, x, y, z, s, color, off):
        off = self._seg(x - s, y, z, x + s, y, z, color, off)
        off = self._seg(x, y - s, z, x, y + s, z, color, off)
        off = self._seg(x, y, z - s, x, y, z + s, color, off)
        return off
    def _xform_point(self, m, x, y, z, w):
        try:
            ox = x * m[0, 0] + y * m[1, 0] + z * m[2, 0] + w * m[3, 0]
            oy = x * m[0, 1] + y * m[1, 1] + z * m[2, 1] + w * m[3, 1]
            oz = x * m[0, 2] + y * m[1, 2] + z * m[2, 2] + w * m[3, 2]
            return (float(ox), float(oy), float(oz))
        except Exception:
            return None
    def _wire_poly(self, pts, color, off):
        try:
            n = len(pts)
            if n < 2:
                return off
            for i in range(n):
                a = pts[i]
                b = pts[(i + 1) % n]
                off = self._seg(a[0], a[1], a[2], b[0], b[1], b[2], color, off)
            return off
        except Exception:
            return off
    def _wire_box_at(self, m, cx, cy, cz, sx, sy, sz, color, off):
        try:
            hx = float(sx) * 0.5
            hy = float(sy) * 0.5
            hz = float(sz) * 0.5
            local = ((cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz), (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz), (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz), (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz))
            if m is not None:
                pts = []
                for p in local:
                    q = self._xform_point(m, p[0], p[1], p[2], 1.0)
                    if q is None:
                        return off
                    pts.append(q)
            else:
                pts = list(local)
            for a, b in _BOX_EDGES:
                pa = pts[a]
                pb = pts[b]
                off = self._seg(pa[0], pa[1], pa[2], pb[0], pb[1], pb[2], color, off)
            return off
        except Exception:
            return off
    def _wire_circle_at(self, m, cx, cy, cz, ux, uy, uz, vx, vy, vz, r, color, off, segs=20):
        try:
            rr = max(1e-6, float(r))
            pts = []
            for i in range(max(3, int(segs))):
                a = 6.283185307179586 * float(i) / float(max(3, int(segs)))
                ca = math.cos(a) * rr
                sa = math.sin(a) * rr
                lx = float(cx) + ux * ca + vx * sa
                ly = float(cy) + uy * ca + vy * sa
                lz = float(cz) + uz * ca + vz * sa
                if m is not None:
                    q = self._xform_point(m, lx, ly, lz, 1.0)
                    if q is None:
                        return off
                    pts.append(q)
                else:
                    pts.append((lx, ly, lz))
            return self._wire_poly(pts, color, off)
        except Exception:
            return off
    def _wire_capsule_at(self, m, cx, cy, cz, r, h, direction, color, off):
        try:
            if direction == 0:
                ax, ay, az = 1.0, 0.0, 0.0
            elif direction == 2:
                ax, ay, az = 0.0, 0.0, 1.0
            else:
                ax, ay, az = 0.0, 1.0, 0.0
            if abs(ay) > 0.9:
                rx, ry, rz = 1.0, 0.0, 0.0
            else:
                rx, ry, rz = 0.0, 1.0, 0.0
            ux = ay * rz - az * ry
            uy = az * rx - ax * rz
            uz = ax * ry - ay * rx
            ul = math.sqrt(ux * ux + uy * uy + uz * uz)
            if ul < 1e-9:
                return off
            ux /= ul
            uy /= ul
            uz /= ul
            vx = ay * uz - az * uy
            vy = az * ux - ax * uz
            vz = ax * uy - ay * ux
            half = max(0.0, float(h) * 0.5 - float(r))
            tx = float(cx) + ax * half
            ty = float(cy) + ay * half
            tz = float(cz) + az * half
            bx = float(cx) - ax * half
            by = float(cy) - ay * half
            bz = float(cz) - az * half
            off = self._wire_circle_at(m, tx, ty, tz, ux, uy, uz, vx, vy, vz, r, color, off)
            off = self._wire_circle_at(m, bx, by, bz, ux, uy, uz, vx, vy, vz, r, color, off)
            for k in range(4):
                a = 1.5707963267948966 * float(k)
                ca = math.cos(a) * r
                sa = math.sin(a) * r
                lx = ux * ca + vx * sa
                ly = uy * ca + vy * sa
                lz = uz * ca + vz * sa
                if m is not None:
                    p0 = self._xform_point(m, tx + lx, ty + ly, tz + lz, 1.0)
                    p1 = self._xform_point(m, bx + lx, by + ly, bz + lz, 1.0)
                    if p0 is None or p1 is None:
                        return off
                    off = self._seg(p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], color, off)
                else:
                    off = self._seg(tx + lx, ty + ly, tz + lz, bx + lx, by + ly, bz + lz, color, off)
            return off
        except Exception:
            return off
    def _draw_colliders(self, comps, tr, ox, oy, oz, off):
        try:
            m = getattr(tr, "world_matrix", None)
            m = m._d if m is not None else None
        except Exception:
            m = None
        box = comps.get("BoxCollider", None)
        if box is not None and getattr(box, "enabled", True):
            try:
                ce = box.center
                sz = box.size
                color = self._trigger_color if getattr(box, "is_trigger", False) else self._collider_color
                off = self._wire_box_at(m, float(ce.x), float(ce.y), float(ce.z), float(sz.x), float(sz.y), float(sz.z), color, off)
            except Exception:
                pass
        sph = comps.get("SphereCollider", None)
        if sph is not None and getattr(sph, "enabled", True):
            try:
                ce = sph.center
                r = max(1e-6, float(sph.radius))
                color = self._trigger_color if getattr(sph, "is_trigger", False) else self._collider_color
                off = self._wire_circle_at(m, float(ce.x), float(ce.y), float(ce.z), 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, r, color, off)
                off = self._wire_circle_at(m, float(ce.x), float(ce.y), float(ce.z), 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, r, color, off)
                off = self._wire_circle_at(m, float(ce.x), float(ce.y), float(ce.z), 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, r, color, off)
            except Exception:
                pass
        cap = comps.get("CapsuleCollider", None)
        if cap is not None and getattr(cap, "enabled", True):
            try:
                ce = cap.center
                r = max(1e-6, float(cap.radius))
                h = max(0.0, float(cap.height))
                color = self._trigger_color if getattr(cap, "is_trigger", False) else self._collider_color
                off = self._wire_capsule_at(m, float(ce.x), float(ce.y), float(ce.z), r, h, int(getattr(cap, "direction", 1)), color, off)
            except Exception:
                pass
        b2 = comps.get("BoxCollider2D", None)
        if b2 is not None and getattr(b2, "enabled", True):
            try:
                ce = getattr(b2, "center", None)
                cx = float(ce.x) if ce is not None else 0.0
                cy = float(ce.y) if ce is not None else 0.0
                sz = b2.size
                color = self._trigger_color if getattr(b2, "is_trigger", False) else self._collider_color
                off = self._wire_box_at(m, cx, cy, 0.0, float(sz.x), float(sz.y), 0.001, color, off)
            except Exception:
                pass
        c2 = comps.get("CircleCollider2D", None)
        if c2 is not None and getattr(c2, "enabled", True):
            try:
                ce = getattr(c2, "center", None)
                cx = float(ce.x) if ce is not None else 0.0
                cy = float(ce.y) if ce is not None else 0.0
                r = max(1e-6, float(c2.radius))
                color = self._trigger_color if getattr(c2, "is_trigger", False) else self._collider_color
                off = self._wire_circle_at(m, cx, cy, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, r, color, off)
            except Exception:
                pass
        return off
    def _draw_joint(self, entity, scene, entities, tr, jn, ox, oy, oz, off):
        try:
            m = getattr(tr, "world_matrix", None)
            m = m._d if m is not None else None
        except Exception:
            m = None
        try:
            a = jn.anchor
            ax = float(a.x)
            ay = float(a.y)
            az = float(a.z)
        except Exception:
            ax = ay = az = 0.0
        if m is not None:
            q = self._xform_point(m, ax, ay, az, 1.0)
            if q is None:
                return off
            wx, wy, wz = q
        else:
            wx = ox + ax
            wy = oy + ay
            wz = oz + az
        try:
            d = jn.axis
            dx = float(d.x)
            dy = float(d.y)
            dz = float(d.z)
        except Exception:
            dx = dy = dz = 0.0
        dl = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dl > 1e-9 and m is not None:
            q = self._xform_point(m, dx, dy, dz, 0.0)
            if q is not None:
                dx, dy, dz = q
                dl = math.sqrt(dx * dx + dy * dy + dz * dz)
        conn = None
        try:
            cid = getattr(jn, "_connected_entity_id", "") or ""
            if cid:
                try:
                    conn = scene.get_entity(cid)
                except Exception:
                    conn = None
            if conn is None:
                nm = getattr(jn, "connected_entity_name", "") or ""
                if nm:
                    for e in entities:
                        try:
                            if getattr(e, "name", "") == nm:
                                conn = e
                                break
                        except Exception:
                            continue
        except Exception:
            conn = None
        if conn is not None:
            cp = self._entity_center(scene, getattr(conn, "id", ""))
            if cp is not None:
                off = self._seg(ox, oy, oz, cp[0], cp[1], cp[2], self._joint_color, off)
        off = self._cross(wx, wy, wz, 0.12, self._joint_color, off)
        if dl > 1e-9:
            try:
                ux = dx / dl
                uy = dy / dl
                uz = dz / dl
                off = self._seg(wx, wy, wz, wx + ux * 0.5, wy + uy * 0.5, wz + uz * 0.5, self._joint_color, off)
            except Exception:
                pass
        return off
    def _vec_batch(self, items, kind):
        try:
            n = len(items)
        except Exception:
            return 0
        if n <= 0:
            return 0
        return 0
    def _emit(self, O, F, mask, k, scale, color, off):
        try:
            idx = np.flatnonzero(mask[:k])
        except Exception:
            return off
        if idx.size == 0:
            return off
        try:
            Ok = O[idx]
            Sv = F[idx] * np.float32(scale)
            L = np.sqrt(np.einsum("ij,ij->i", Sv, Sv))
            g = L > np.float32(1e-9)
            if not bool(np.any(g)):
                return off
            Ok = np.ascontiguousarray(Ok[g])
            Sv = np.ascontiguousarray(Sv[g])
            L = np.ascontiguousarray(L[g])
            m = int(Ok.shape[0])
            self._ensure_segcap(off + m * 3)
            ends = Ok + Sv
            h = np.minimum(L * np.float32(0.22), np.float32(0.30))
            Ls = np.maximum(L, np.float32(1e-9))
            d = Sv / Ls[:, None]
            up = np.abs(d[:, 1]) > np.float32(0.9)
            ref = np.where(up[:, None], _REF_X, _REF_Y)
            p1 = np.cross(d, ref)
            n1 = np.linalg.norm(p1, axis=1)
            p1 = p1 / np.maximum(n1, np.float32(1e-6))[:, None]
            hw = (h * np.float32(0.5))[:, None]
            hh = h[:, None]
            b = ends - d * hh
            S = self._S
            E = self._E
            C = self._C
            S[off + 0::3][:m] = Ok
            E[off + 0::3][:m] = ends
            S[off + 1::3][:m] = ends
            E[off + 1::3][:m] = b + p1 * hw
            S[off + 2::3][:m] = ends
            E[off + 2::3][:m] = b - p1 * hw
            C[off:off + m * 3] = color
            return off + m * 3
        except Exception:
            return off
    def _flat_submit(self, s, e, c):
        try: import core.gizmo.api as _api; inst = _api._gizmos_instance
        except Exception: inst = None
        if inst is not None:
            try:
                with inst._lock:
                    try: inst._flat_size = 0
                    except Exception: pass
                    inst._revision += 1
                from core.gizmo.apiv import Gizmos as _G
                _G.draw_lines(s, e, c)
                return
            except Exception: pass
        self._fallback_submit(s, e, c)
    def _fallback_submit(self, s, e, c):
        try: n = int(s.shape[0])
        except Exception: return
        try:
            from core.gizmo.apiv import Gizmos as _G
        except Exception:
            return
        for i in range(n):
            try:
                _G.draw_line((float(s[i, 0]), float(s[i, 1]), float(s[i, 2])), (float(e[i, 0]), float(e[i, 1]), float(e[i, 2])), color=(float(c[i, 0]), float(c[i, 1]), float(c[i, 2]), float(c[i, 3])), thickness=1.0, tag=_TAG)
            except Exception:
                continue
    def _submit_labels(self, labels):
        try: from core.gizmo.apiv import Gizmos as _G
        except Exception: return
        for x, y, z, text, color in labels:
            try: _G.draw_label((x, y, z), text, color=color, font_size=12, tag=_TAG)
            except Exception: continue
    def _collect_contacts(self, scene, selected, playing, labels, lab_cap, off):
        if not playing or not self._show_contacts: return off
        pp = self._physics_plugin()
        if pp is not None:
            try:
                if self._hooked_pp is None: self._install_contact_hook(pp)
            except Exception: pass
        items = []
        try:
            if pp is not None and getattr(pp, "_simulation_mode", "") == "single": items = self._read_single_contacts(pp)
            else: items = self._stashed_contacts; self._stashed_contacts = []
        except Exception: items = []
        if not items: return off
        try: nl = min(3.0, max(0.05, float(self._contact_normal_length)))
        except Exception: nl = 0.6
        cur_pairs = set(); cn = 0; CO = self._XO; CF = self._XF; mn = self._xm; ms = self._xm2
        for pos, nor, imp, ea, eb, has_pos in items:
            try:
                if selected is not None and ea not in selected and eb not in selected: continue
                if ea and eb: pair = (ea, eb) if ea <= eb else (eb, ea); cur_pairs.add(pair); is_new = pair not in self._contact_pairs
                else: is_new = True
                color = self._contact_new_color if is_new else self._contact_stay_color
                if has_pos:
                    px, py, pz = pos; nx, ny, nz = nor; off = self._cross(px, py, pz, 0.09, color, off)
                    if cn < 512: CO[cn, 0] = px; CO[cn, 1] = py; CO[cn, 2] = pz; CF[cn, 0] = nx * nl; CF[cn, 1] = ny * nl; CF[cn, 2] = nz * nl; mn[cn] = is_new; ms[cn] = not is_new; cn += 1
                    if lab_cap > 0 and len(labels) < lab_cap and imp > 0.0:
                        try: labels.append((px + nx * nl, py + ny * nl, pz + nz * nl, f"{imp:.1f}", color))
                        except Exception: pass
                else:
                    ca = self._entity_center(scene, ea); cb = self._entity_center(scene, eb)
                    if ca is not None and cb is not None: off = self._seg(ca[0], ca[1], ca[2], cb[0], cb[1], cb[2], self._contact_stay_color, off)
            except Exception: continue
        try: self._contact_pairs = cur_pairs
        except Exception: pass
        if cn > 0: off = self._emit(CO, CF, mn, cn, 1.0, self._contact_new_color, off); off = self._emit(CO, CF, ms, cn, 1.0, self._contact_stay_color, off)
        return off
    def _collect_extras(self, entities, selected, scene, labels, lab_cap, off):
        show_j = self._show_joints; show_c = self._show_colliders; show_v = self._show_velocity
        if not show_j and not show_c and not show_v: return off
        cc = 0; CO = self._XO; CF = self._XF; mm = self._xm
        for entity in entities:
            try:
                if not getattr(entity, "_active", True): continue
                eid = entity.id
                if selected is not None and eid not in selected: continue
                comps = getattr(entity, "_components", None)
                if not comps: continue
                tr = comps.get("Transform", None)
                if tr is None: continue
                try: p = tr.position; ox = float(p.x); oy = float(p.y); oz = float(p.z)
                except Exception: continue
                if show_v:
                    try:
                        chc = comps.get("CharacterController", None)
                        if chc is not None and getattr(chc, "enabled", True):
                            v = chc._velocity; vx = float(v.x); vy = float(v.y); vz = float(v.z); vm = math.sqrt(vx * vx + vy * vy + vz * vz)
                            if vm > self._min_magnitude and cc < 512:
                                CO[cc, 0] = ox; CO[cc, 1] = oy; CO[cc, 2] = oz; CF[cc, 0] = vx; CF[cc, 1] = vy; CF[cc, 2] = vz; mm[cc] = True; cc += 1
                                if lab_cap > 0 and len(labels) < lab_cap: labels.append((ox, oy, oz, f"cc {vm:.2f}", self._velocity_color))
                    except Exception: pass
                if show_j:
                    try:
                        jn = comps.get("Joint", None)
                        if jn is not None and getattr(jn, "enabled", True): off = self._draw_joint(entity, scene, entities, tr, jn, ox, oy, oz, off)
                    except Exception: pass
                if show_c:
                    try: off = self._draw_colliders(comps, tr, ox, oy, oz, off)
                    except Exception: pass
            except Exception: continue
        if show_v and cc > 0: off = self._emit(CO, CF, mm, cc, self._velocity_scale, self._velocity_color, off)
        return off
