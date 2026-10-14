# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3, Quat
from core.components.inspector_meta import FieldType, InspectorField, ListElementField
from .types import PhysBoneIntegration, PhysBoneMultiChild, PhysBoneImmobileType, PhysBoneLimitType
from .mathx import _clamp, _clamp01, _sample_curve, _as_vec3, _as_curve, _normalize_id, _normalize_id_list, _GRAB_K
class ParamsMixin:
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Transforms", FieldType.HEADER),
            InspectorField("root_entity_id", "Root Transform", FieldType.GAMEOBJECT),
            InspectorField("ignore_entity_ids", "Ignore Transforms", FieldType.LIST, element_fields=[ListElementField("value", "Transform", FieldType.GAMEOBJECT)]),
            InspectorField("ignore_other_phys_bones", "Ignore Other Phys Bones", FieldType.BOOL),
            InspectorField("endpoint_position", "Endpoint Position", FieldType.VEC3),
            InspectorField("multi_child_type", "Multi Child Type", FieldType.ENUM, enum_class=PhysBoneMultiChild),
            InspectorField("", "Forces", FieldType.HEADER),
            InspectorField("integration_type", "Integration Type", FieldType.ENUM, enum_class=PhysBoneIntegration),
            InspectorField("pull", "Pull", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("pull_curve", "Pull Curve", FieldType.CURVE),
            InspectorField("spring", "Spring", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("spring_curve", "Spring Curve", FieldType.CURVE),
            InspectorField("damping", "Damping", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("damping_curve", "Damping Curve", FieldType.CURVE),
            InspectorField("gravity", "Gravity", FieldType.SLIDER, min_val=-1.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("gravity_curve", "Gravity Curve", FieldType.CURVE),
            InspectorField("gravity_falloff", "Gravity Falloff", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("gravity_falloff_curve", "Gravity Falloff Curve", FieldType.CURVE),
            InspectorField("immobile_type", "Immobile Type", FieldType.ENUM, enum_class=PhysBoneImmobileType),
            InspectorField("immobile", "Immobile", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("immobile_curve", "Immobile Curve", FieldType.CURVE),
            InspectorField("", "Limits", FieldType.HEADER),
            InspectorField("limit_type", "Limit Type", FieldType.ENUM, enum_class=PhysBoneLimitType),
            InspectorField("max_angle", "Max Angle", FieldType.SLIDER, min_val=0.0, max_val=180.0, step=0.5, decimals=2),
            InspectorField("max_angle_curve", "Max Angle Curve", FieldType.CURVE),
            InspectorField("hinge_axis", "Hinge Axis", FieldType.VEC3),
            InspectorField("", "Collision", FieldType.HEADER),
            InspectorField("radius", "Radius", FieldType.FLOAT, min_val=0.0, max_val=2.0, step=0.005, decimals=4),
            InspectorField("radius_curve", "Radius Curve", FieldType.CURVE),
            InspectorField("allow_collision", "Allow Collision", FieldType.BOOL),
            InspectorField("collider_entity_ids", "Colliders", FieldType.LIST, element_fields=[ListElementField("value", "Collider", FieldType.GAMEOBJECT)]),
            InspectorField("", "Stretch And Squish", FieldType.HEADER),
            InspectorField("stretch_motion", "Stretch Motion", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("stretch_motion_curve", "Stretch Motion Curve", FieldType.CURVE),
            InspectorField("max_stretch", "Max Stretch", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.01, decimals=3),
            InspectorField("max_stretch_curve", "Max Stretch Curve", FieldType.CURVE),
            InspectorField("max_squish", "Max Squish", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=3),
            InspectorField("max_squish_curve", "Max Squish Curve", FieldType.CURVE),
            InspectorField("", "Options", FieldType.HEADER),
            InspectorField("parameter", "Parameter", FieldType.STRING),
            InspectorField("is_animated", "Is Animated", FieldType.BOOL),
            InspectorField("reset_when_disabled", "Reset When Disabled", FieldType.BOOL),
            InspectorField("", "Debug", FieldType.HEADER),
            InspectorField("allow_grab", "Allow Grab", FieldType.BOOL),
            InspectorField("", "Gizmos", FieldType.HEADER),
            InspectorField("show_gizmo", "Show Gizmo", FieldType.BOOL),
        ]
    def __init__(self):
        super().__init__()
        self.root_entity_id: str = ""
        self.ignore_entity_ids: list = []
        self.ignore_other_phys_bones: bool = False
        self.endpoint_position: Vec3 = Vec3.zero()
        self.multi_child_type: PhysBoneMultiChild = PhysBoneMultiChild.IGNORE
        self.integration_type: PhysBoneIntegration = PhysBoneIntegration.SIMPLIFIED
        self.pull: float = 0.2
        self.pull_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.spring: float = 0.2
        self.spring_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.damping: float = 0.1
        self.damping_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.gravity: float = 0.0
        self.gravity_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.gravity_falloff: float = 0.0
        self.gravity_falloff_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.immobile_type: PhysBoneImmobileType = PhysBoneImmobileType.ALL_MOTION
        self.immobile: float = 0.0
        self.immobile_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.limit_type: PhysBoneLimitType = PhysBoneLimitType.NONE
        self.max_angle: float = 45.0
        self.max_angle_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.hinge_axis: Vec3 = Vec3(1, 0, 0)
        self.radius: float = 0.11
        self.radius_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.allow_collision: bool = True
        self.collider_entity_ids: list = []
        self.stretch_motion: float = 0.0
        self.stretch_motion_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.max_stretch: float = 0.0
        self.max_stretch_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.max_squish: float = 0.0
        self.max_squish_curve = [[0.0, 1.0], [1.0, 1.0]]
        self.parameter: str = ""
        self.is_animated: bool = False
        self.reset_when_disabled: bool = False
        self.allow_grab: bool = True
        self.show_gizmo: bool = True
        self._nodes: list = []
        self._pos: list = []
        self._prev: list = []
        self._anim: list = []
        self._anim_quat: list = []
        self._built_root_id: str = ""
        self._initialized: bool = False
        self._prev_root_pos: Vec3 | None = None
        self._prev_root_quat: Quat | None = None
        self._grab_index: int = -1
        self._grab_target: Vec3 | None = None
        self._grab_snapshot: list | None = None
        self._curve_cache: dict = {}
    def _pb_value(self, base, curve, t, lo, hi):
        try:
            b = _clamp(float(base), lo, hi)
        except Exception:
            b = lo
        try:
            m = _sample_curve(curve, t)
        except Exception:
            m = 1.0
        return _clamp(b * float(m), lo, hi)
    def _cached_curve(self, key, curve):
        try:
            cache = self._curve_cache
        except AttributeError:
            cache = self._curve_cache = {}
        try:
            ref, tx, ty = cache.get(key, (None, None, None))
            if ref is curve and tx is not None:
                return tx, ty
            pts = sorted(curve, key=lambda p: float(p[0]))
            tx = [float(p[0]) for p in pts]
            ty = [float(p[1]) for p in pts]
            if len(tx) < 2:
                cache[key] = (curve, None, None)
                return None, None
            tx = tuple(tx)
            ty = tuple(ty)
            cache[key] = (curve, tx, ty)
            if len(cache) > 64:
                cache.clear()
                cache[key] = (curve, tx, ty)
            return tx, ty
        except Exception:
            return None, None
    def _pb_fast(self, base, ckey, curve, t, lo, hi):
        try:
            b = _clamp(float(base), lo, hi)
        except Exception:
            b = lo
        try:
            tx, ty = self._cached_curve(ckey, curve)
            if tx is None:
                m = 1.0
            else:
                tt = float(t)
                if tt < 0.0:
                    tt = 0.0
                elif tt > 1.0:
                    tt = 1.0
                import bisect
                j = bisect.bisect_right(tx, tt)
                if j <= 0:
                    m = ty[0]
                elif j >= len(tx):
                    m = ty[-1]
                else:
                    t0 = tx[j - 1]
                    t1 = tx[j]
                    dt = t1 - t0
                    s = (tt - t0) / dt if abs(dt) > 1e-12 else 0.0
                    m = ty[j - 1] + (ty[j] - ty[j - 1]) * s
        except Exception:
            m = 1.0
        return _clamp(b * float(m), lo, hi)
    def _pack_arrays(self, weight, colliders):
        nodes = self._nodes
        n = len(nodes)
        anim = self._anim
        anim_q = self._anim_quat
        pos = np.zeros((n, 3), dtype=np.float64)
        prv = np.zeros((n, 3), dtype=np.float64)
        anm = np.zeros((n, 3), dtype=np.float64)
        for i in range(n):
            p = self._pos[i]
            q = self._prev[i]
            a = anim[i]
            pos[i, 0] = p.x
            pos[i, 1] = p.y
            pos[i, 2] = p.z
            prv[i, 0] = q.x
            prv[i, 1] = q.y
            prv[i, 2] = q.z
            anm[i, 0] = a.x
            anm[i, 1] = a.y
            anm[i, 2] = a.z
        pull = np.zeros(n, dtype=np.float64)
        spring = np.zeros(n, dtype=np.float64)
        grav = np.zeros(n, dtype=np.float64)
        damp = np.zeros(n, dtype=np.float64)
        radius = np.zeros(n, dtype=np.float64)
        sm = np.zeros(n, dtype=np.float64)
        mx = np.zeros(n, dtype=np.float64)
        sq = np.zeros(n, dtype=np.float64)
        maxa = np.zeros(n, dtype=np.float64)
        follow = np.zeros(n, dtype=np.float64)
        parent = np.zeros(n, dtype=np.int64)
        rest = np.zeros(n, dtype=np.float64)
        lim = np.zeros(n, dtype=np.int64)
        hinge = np.zeros((n, 3), dtype=np.float64)
        rdir = np.zeros((n, 3), dtype=np.float64)
        try:
            lt = self.limit_type
            if isinstance(lt, str):
                lt = PhysBoneLimitType(lt)
        except Exception:
            lt = PhysBoneLimitType.NONE
        li = 0
        if lt == PhysBoneLimitType.ANGLE:
            li = 1
        elif lt == PhysBoneLimitType.HINGE:
            li = 2
        w = _clamp01(weight)
        hx = self.hinge_axis if isinstance(self.hinge_axis, Vec3) else Vec3(1, 0, 0)
        if hx.length_sq() < 1e-10:
            hx = Vec3(1, 0, 0)
        for i in range(n):
            nd = nodes[i]
            t = nd.t
            pull[i] = self._pb_fast(self.pull, "pull", self.pull_curve, t, 0.0, 1.0)
            spring[i] = self._pb_fast(self.spring, "spring", self.spring_curve, t, 0.0, 1.0)
            g0 = self._pb_fast(self.gravity, "gravity", self.gravity_curve, t, -1.0, 1.0)
            try:
                fall = self._pb_fast(self.gravity_falloff, "gravity_falloff", self.gravity_falloff_curve, t, 0.0, 1.0)
            except Exception:
                fall = 0.0
            grav[i] = g0 * (1.0 - float(fall) * float(t))
            damp[i] = self._pb_fast(self.damping, "damping", self.damping_curve, t, 0.0, 1.0)
            radius[i] = self._pb_fast(self.radius, "radius", self.radius_curve, t, 0.0, 2.0)
            sm[i] = self._pb_fast(self.stretch_motion, "stretch_motion", self.stretch_motion_curve, t, 0.0, 1.0)
            mx[i] = self._pb_fast(self.max_stretch, "max_stretch", self.max_stretch_curve, t, 0.0, 2.0)
            sq[i] = self._pb_fast(self.max_squish, "max_squish", self.max_squish_curve, t, 0.0, 1.0)
            maxa[i] = self._pb_fast(self.max_angle, "max_angle", self.max_angle_curve, t, 0.0, 180.0)
            try:
                im = self._pb_fast(self.immobile, "immobile", self.immobile_curve, t, 0.0, 1.0)
            except Exception:
                im = 0.0
            f = 1.0 - (1.0 - float(im)) * float(w)
            if f < 0.0:
                f = 0.0
            if f > 1.0:
                f = 1.0
            follow[i] = f
            parent[i] = nd.parent
            rest[i] = float(nd.rest_length)
            lim[i] = li
            p = nd.parent
            if p >= 0:
                dx = anm[i, 0] - anm[p, 0]
                dy = anm[i, 1] - anm[p, 1]
                dz = anm[i, 2] - anm[p, 2]
                l = math.sqrt(dx * dx + dy * dy + dz * dz)
                if l > 1e-9:
                    rdir[i, 0] = dx / l
                    rdir[i, 1] = dy / l
                    rdir[i, 2] = dz / l
                if li == 2:
                    try:
                        pq = anim_q[p]
                        ax = pq.rotate_vec3(hx.normalized())
                        al = math.sqrt(ax.x * ax.x + ax.y * ax.y + ax.z * ax.z)
                        if al > 1e-9:
                            hinge[i, 0] = ax.x / al
                            hinge[i, 1] = ax.y / al
                            hinge[i, 2] = ax.z / al
                    except Exception:
                        pass
        m = len(colliders) if colliders else 0
        ctype = np.zeros(m, dtype=np.int64)
        ca = np.zeros((m, 3), dtype=np.float64)
        cb = np.zeros((m, 3), dtype=np.float64)
        cr = np.zeros(m, dtype=np.float64)
        cn = np.zeros((m, 3), dtype=np.float64)
        cins = np.zeros(m, dtype=np.int64)
        for k in range(m):
            try:
                col = colliders[k]
                st = col.shape_type
                if isinstance(st, str):
                    try:
                        from core.components.physics.pbcollider import PhysBoneColliderType
                        st = PhysBoneColliderType(st)
                    except Exception:
                        st = None
                try:
                    sname = st.value if st is not None else "sphere"
                except Exception:
                    sname = "sphere"
                inside = 1 if getattr(col, "is_inside", False) else 0
                cins[k] = inside
                if sname == "plane":
                    pl = col.world_plane()
                    if pl is None:
                        continue
                    p0, nn = pl
                    ctype[k] = 2
                    ca[k, 0] = p0.x
                    ca[k, 1] = p0.y
                    ca[k, 2] = p0.z
                    cn[k, 0] = nn.x
                    cn[k, 1] = nn.y
                    cn[k, 2] = nn.z
                elif sname == "capsule":
                    cap = col.world_capsule()
                    if cap is None:
                        continue
                    a, b, r = cap
                    ctype[k] = 1
                    ca[k, 0] = a.x
                    ca[k, 1] = a.y
                    ca[k, 2] = a.z
                    cb[k, 0] = b.x
                    cb[k, 1] = b.y
                    cb[k, 2] = b.z
                    cr[k] = r
                else:
                    c = col.world_center()
                    if c is None:
                        continue
                    ctype[k] = 0
                    ca[k, 0] = c.x
                    ca[k, 1] = c.y
                    ca[k, 2] = c.z
                    cr[k] = col.world_radius()
            except Exception:
                continue
        gi = -1
        gx = 0.0
        gy = 0.0
        gz = 0.0
        try:
            if self._grab_target is not None and self._grab_index > 0 and self._grab_index < n and self.allow_grab:
                gi = int(self._grab_index)
                gx = float(self._grab_target.x)
                gy = float(self._grab_target.y)
                gz = float(self._grab_target.z)
        except Exception:
            gi = -1
        return (pos, prv, anm, pull, spring, grav, damp, radius, sm, mx, sq, maxa, follow, parent, rest, lim, hinge, rdir, ctype, ca, cb, cr, cn, cins, gi, gx, gy, gz)
    def _step_cython(self, fn, dt, substeps, iters, colliders, weight):
        pack = self._pack_arrays(weight, colliders)
        pos, prv, anm, pull, spring, grav, damp, radius, sm, mx, sq, maxa, follow, parent, rest, lim, hinge, rdir, ctype, ca, cb, cr, cn, cins, gi, gx, gy, gz = pack
        fn(pos, prv, anm, pull, spring, grav, damp, radius, sm, mx, sq, maxa, follow, parent, rest, lim, hinge, rdir, ctype, ca, cb, cr, cn, cins, float(dt), int(substeps), int(iters), int(gi), float(gx), float(gy), float(gz), float(_GRAB_K))
        n = len(self._nodes)
        out = []
        new_prev = []
        for i in range(n):
            out.append(Vec3(float(pos[i, 0]), float(pos[i, 1]), float(pos[i, 2])))
            new_prev.append(Vec3(float(prv[i, 0]), float(prv[i, 1]), float(prv[i, 2])))
        self._prev = new_prev
        return out
