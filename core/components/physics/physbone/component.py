# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import math
import numpy as np
from core.ecs import Component, ComponentRegistry, InstancePrimitive
from core.maths.math3d import Vec3, Quat
from .types import PhysBoneIntegration, PhysBoneMultiChild, PhysBoneImmobileType, PhysBoneLimitType
from .mathx import _normalize_id, _normalize_id_list, _as_vec3, _as_curve, _world_quat_of
from .chain import ChainMixin
from .colliders import CollidersMixin
from .params import ParamsMixin
from .dynamics import DynamicsMixin
from .grab import GrabMixin
@ComponentRegistry.register
class PhysBone(ChainMixin, CollidersMixin, ParamsMixin, DynamicsMixin, GrabMixin, Component):
    _icon = "Joint.png"
    _allow_multiple = True
    _gizmo_icon_color = (120, 220, 255)
    _gizmo_icon_label = "PB"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "armature"
    def on_start(self):
        try:
            self._rebuild_chain()
        except Exception:
            pass
    def on_enable(self):
        try:
            cur = _normalize_id(self.root_entity_id)
            root = self._resolve_root()
            rid = root.id if root is not None else cur
            if not self._nodes or self._built_root_id != rid:
                self._rebuild_chain()
            else:
                self._pos = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in self._nodes]
                self._prev = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in self._nodes]
        except Exception:
            pass
    def on_disable(self):
        try:
            if self.reset_when_disabled:
                self.reset_to_rest()
        except Exception:
            pass
    def on_destroy(self):
        try:
            if self.reset_when_disabled:
                self.reset_to_rest()
        except Exception:
            pass
    def gizmo_instances(self):
        try:
            if not self.show_gizmo:
                return None
            nodes = self._nodes
            if not nodes:
                return None
            pts = self._pos if len(self._pos) == len(nodes) else [nd.rest_world_pos for nd in nodes]
            out = []
            for i, nd in enumerate(nodes):
                try:
                    p = pts[i]
                    pr = self._pb_fast(self.radius, "radius", self.radius_curve, nd.t, 0.0, 2.0)
                    rl = float(nd.rest_length)
                    r = pr
                    if rl > 1e-9 and rl * 0.18 > r:
                        r = rl * 0.18
                    if r < 0.012:
                        r = 0.012
                    if nd.is_virtual:
                        r = max(pr * 0.7, 0.01)
                        col = [1.0, 0.45, 1.0, 0.95]
                    elif i == 0:
                        col = [0.35, 1.0, 0.5, 1.0]
                    elif self._grab_index == i and self._grab_target is not None:
                        col = [1.0, 0.25, 0.25, 1.0]
                    else:
                        col = [1.0, 0.85, 0.3, 1.0]
                    m = np.eye(4, dtype=np.float32)
                    m[0, 0] = r
                    m[1, 1] = r
                    m[2, 2] = r
                    m[0, 3] = float(p.x)
                    m[1, 3] = float(p.y)
                    m[2, 3] = float(p.z)
                    out.append(InstancePrimitive("sphere", m.ravel("F"), col))
                except Exception:
                    continue
            try:
                if self._grab_target is not None and self._grab_index >= 0:
                    g = self._grab_target
                    m = np.eye(4, dtype=np.float32)
                    m[0, 0] = 0.02
                    m[1, 1] = 0.02
                    m[2, 2] = 0.02
                    m[0, 3] = float(g.x)
                    m[1, 3] = float(g.y)
                    m[2, 3] = float(g.z)
                    out.append(InstancePrimitive("sphere", m.ravel("F"), [1.0, 0.2, 0.2, 1.0]))
            except Exception:
                pass
            return out or None
        except Exception:
            return None
    def _gizmo_rest_dir(self, i, pts):
        try:
            nodes = self._nodes
            p = nodes[i].parent
            anim = self._anim if len(self._anim) == len(nodes) else None
            if anim is not None:
                ap = anim[p]
                ac = anim[i]
                dx = ac.x - ap.x
                dy = ac.y - ap.y
                dz = ac.z - ap.z
            else:
                ap = nodes[p].rest_world_pos
                ac = nodes[i].rest_world_pos
                dx = ac.x - ap.x
                dy = ac.y - ap.y
                dz = ac.z - ap.z
            l = math.sqrt(dx * dx + dy * dy + dz * dz)
            if l < 1e-9:
                return None
            return Vec3(dx / l, dy / l, dz / l)
        except Exception:
            return None
    def _gizmo_hinge_axis(self, i):
        try:
            nodes = self._nodes
            p = nodes[i].parent
            hx = self.hinge_axis if isinstance(self.hinge_axis, Vec3) else Vec3(1, 0, 0)
            if hx.length_sq() < 1e-10:
                hx = Vec3(1, 0, 0)
            anim_q = self._anim_quat if len(self._anim_quat) == len(nodes) else None
            if anim_q is not None:
                axis = anim_q[p].rotate_vec3(hx.normalized())
            else:
                axis = nodes[p].rest_world_quat.rotate_vec3(hx.normalized())
            return axis.normalized()
        except Exception:
            return Vec3(1, 0, 0)
    def gizmo_lines(self):
        try:
            if not self.show_gizmo:
                return []
            nodes = self._nodes
            if not nodes:
                root = self._resolve_root()
                if root is None or root.transform is None:
                    return []
                return []
            pts = self._pos if len(self._pos) == len(nodes) else [nd.rest_world_pos for nd in nodes]
            lines = []
            col = [0.9, 0.95, 1.0, 1.0]
            lim_col = [1.0, 0.6, 0.2, 0.9]
            grab_col = [1.0, 0.25, 0.25, 1.0]
            for i, nd in enumerate(nodes):
                p = nd.parent
                if p < 0:
                    continue
                try:
                    lines.append((pts[p], pts[i], col))
                except Exception:
                    continue
            try:
                lt = self.limit_type
                if isinstance(lt, str):
                    lt = PhysBoneLimitType(lt)
                if lt != PhysBoneLimitType.NONE:
                    for i in range(1, len(nodes)):
                        try:
                            t = nodes[i].t
                            ma = self._pb_fast(self.max_angle, "max_angle", self.max_angle_curve, t, 0.0, 180.0)
                            if ma <= 1e-6 or ma >= 179.9:
                                continue
                            pp = pts[nodes[i].parent]
                            cp = pts[i]
                            dx = cp.x - pp.x
                            dy = cp.y - pp.y
                            dz = cp.z - pp.z
                            l = math.sqrt(dx * dx + dy * dy + dz * dz)
                            if l < 1e-9:
                                continue
                            if lt == PhysBoneLimitType.HINGE:
                                axis = self._gizmo_hinge_axis(i)
                                rest = self._gizmo_rest_dir(i, pts)
                                if rest is None:
                                    continue
                                rp = rest.x * axis.x + rest.y * axis.y + rest.z * axis.z
                                rpx = rest.x - axis.x * rp
                                rpy = rest.y - axis.y * rp
                                rpz = rest.z - axis.z * rp
                                rpl = math.sqrt(rpx * rpx + rpy * rpy + rpz * rpz)
                                if rpl < 1e-6:
                                    continue
                                rpx /= rpl
                                rpy /= rpl
                                rpz /= rpl
                                wx = axis.y * rpz - axis.z * rpy
                                wy = axis.z * rpx - axis.x * rpz
                                wz = axis.x * rpy - axis.y * rpx
                                rplen = math.sqrt(max(0.0, 1.0 - rp * rp))
                                segs = 10
                                prev = None
                                for sgi in range(segs + 1):
                                    a = math.radians(-ma + 2.0 * ma * sgi / segs)
                                    ca = math.cos(a)
                                    sa = math.sin(a)
                                    dxn = axis.x * rp + (rpx * ca + wx * sa) * rplen
                                    dyn = axis.y * rp + (rpy * ca + wy * sa) * rplen
                                    dzn = axis.z * rp + (rpz * ca + wz * sa) * rplen
                                    pt = Vec3(pp.x + dxn * l, pp.y + dyn * l, pp.z + dzn * l)
                                    if prev is not None:
                                        lines.append((prev, pt, lim_col))
                                    prev = pt
                                try:
                                    ax0 = Vec3(pp.x - axis.x * l * 0.35, pp.y - axis.y * l * 0.35, pp.z - axis.z * l * 0.35)
                                    ax1 = Vec3(pp.x + axis.x * l * 0.35, pp.y + axis.y * l * 0.35, pp.z + axis.z * l * 0.35)
                                    lines.append((ax0, ax1, [0.4, 0.7, 1.0, 1.0]))
                                except Exception:
                                    pass
                                continue
                            r = l * math.sin(math.radians(min(ma, 89.0)))
                            if r < 1e-6:
                                continue
                            d = Vec3(dx / l, dy / l, dz / l)
                            up = Vec3(0, 1, 0) if abs(d.y) < 0.9 else Vec3(1, 0, 0)
                            u = Vec3(d.y * up.z - d.z * up.y, d.z * up.x - d.x * up.z, d.x * up.y - d.y * up.x).normalized()
                            v = Vec3(d.y * u.z - d.z * u.y, d.z * u.x - d.x * u.z, d.x * u.y - d.y * u.x).normalized()
                            rim = []
                            segs = 12
                            for sgi in range(segs):
                                ang = 2.0 * math.pi * sgi / segs
                                pt = Vec3(cp.x + (u.x * math.cos(ang) + v.x * math.sin(ang)) * r, cp.y + (u.y * math.cos(ang) + v.y * math.sin(ang)) * r, cp.z + (u.z * math.cos(ang) + v.z * math.sin(ang)) * r)
                                rim.append(pt)
                            for sgi in range(segs):
                                lines.append((rim[sgi], rim[(sgi + 1) % segs], lim_col))
                            for sgi in range(0, segs, 2):
                                lines.append((pp, rim[sgi], lim_col))
                        except Exception:
                            continue
            except Exception:
                pass
            try:
                if self._grab_target is not None and self._grab_index > 0 and self._grab_index < len(pts):
                    lines.append((pts[self._grab_index], self._grab_target, grab_col))
            except Exception:
                pass
            return lines
        except Exception:
            return []
    def serialize(self) -> dict:
        d = super().serialize()
        try:
            mct = self.multi_child_type.value if isinstance(self.multi_child_type, PhysBoneMultiChild) else str(self.multi_child_type)
        except Exception:
            mct = "ignore"
        try:
            it = self.integration_type.value if isinstance(self.integration_type, PhysBoneIntegration) else str(self.integration_type)
        except Exception:
            it = "simplified"
        try:
            imt = self.immobile_type.value if isinstance(self.immobile_type, PhysBoneImmobileType) else str(self.immobile_type)
        except Exception:
            imt = "all"
        try:
            lmt = self.limit_type.value if isinstance(self.limit_type, PhysBoneLimitType) else str(self.limit_type)
        except Exception:
            lmt = "none"
        d.update({
            "root_entity_id": _normalize_id(self.root_entity_id),
            "ignore_entity_ids": _normalize_id_list(self.ignore_entity_ids),
            "ignore_other_phys_bones": bool(self.ignore_other_phys_bones),
            "endpoint_position": self.endpoint_position.to_list() if isinstance(self.endpoint_position, Vec3) else [0, 0, 0],
            "multi_child_type": mct,
            "integration_type": it,
            "pull": float(self.pull),
            "pull_curve": _as_curve(self.pull_curve),
            "spring": float(self.spring),
            "spring_curve": _as_curve(self.spring_curve),
            "damping": float(self.damping),
            "damping_curve": _as_curve(self.damping_curve),
            "gravity": float(self.gravity),
            "gravity_curve": _as_curve(self.gravity_curve),
            "gravity_falloff": float(self.gravity_falloff),
            "gravity_falloff_curve": _as_curve(self.gravity_falloff_curve),
            "immobile_type": imt,
            "immobile": float(self.immobile),
            "immobile_curve": _as_curve(self.immobile_curve),
            "limit_type": lmt,
            "max_angle": float(self.max_angle),
            "max_angle_curve": _as_curve(self.max_angle_curve),
            "hinge_axis": self.hinge_axis.to_list() if isinstance(self.hinge_axis, Vec3) else [1, 0, 0],
            "radius": float(self.radius),
            "radius_curve": _as_curve(self.radius_curve),
            "allow_collision": bool(self.allow_collision),
            "collider_entity_ids": _normalize_id_list(self.collider_entity_ids),
            "stretch_motion": float(self.stretch_motion),
            "stretch_motion_curve": _as_curve(self.stretch_motion_curve),
            "max_stretch": float(self.max_stretch),
            "max_stretch_curve": _as_curve(self.max_stretch_curve),
            "max_squish": float(self.max_squish),
            "max_squish_curve": _as_curve(self.max_squish_curve),
            "parameter": str(self.parameter or ""),
            "is_animated": bool(self.is_animated),
            "reset_when_disabled": bool(self.reset_when_disabled),
            "allow_grab": bool(self.allow_grab),
            "show_gizmo": bool(self.show_gizmo),
        })
        return d
    @classmethod
    def deserialize(cls, data: dict):
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.root_entity_id = _normalize_id(data.get("root_entity_id", ""))
        inst.ignore_entity_ids = _normalize_id_list(data.get("ignore_entity_ids", []))
        inst.ignore_other_phys_bones = bool(data.get("ignore_other_phys_bones", False))
        inst.endpoint_position = _as_vec3(data.get("endpoint_position", [0, 0, 0]), Vec3.zero())
        try:
            inst.multi_child_type = PhysBoneMultiChild(data.get("multi_child_type", "ignore"))
        except Exception:
            inst.multi_child_type = PhysBoneMultiChild.IGNORE
        try:
            inst.integration_type = PhysBoneIntegration(data.get("integration_type", "simplified"))
        except Exception:
            inst.integration_type = PhysBoneIntegration.SIMPLIFIED
        inst.pull = float(data.get("pull", 0.2))
        inst.pull_curve = _as_curve(data.get("pull_curve", [[0, 1], [1, 1]]))
        inst.spring = float(data.get("spring", 0.2))
        inst.spring_curve = _as_curve(data.get("spring_curve", [[0, 1], [1, 1]]))
        inst.damping = float(data.get("damping", 0.1))
        inst.damping_curve = _as_curve(data.get("damping_curve", [[0, 1], [1, 1]]))
        inst.gravity = float(data.get("gravity", 0.0))
        inst.gravity_curve = _as_curve(data.get("gravity_curve", [[0, 1], [1, 1]]))
        inst.gravity_falloff = float(data.get("gravity_falloff", 0.0))
        inst.gravity_falloff_curve = _as_curve(data.get("gravity_falloff_curve", [[0, 1], [1, 1]]))
        try:
            inst.immobile_type = PhysBoneImmobileType(data.get("immobile_type", "all"))
        except Exception:
            inst.immobile_type = PhysBoneImmobileType.ALL_MOTION
        inst.immobile = float(data.get("immobile", 0.0))
        inst.immobile_curve = _as_curve(data.get("immobile_curve", [[0, 1], [1, 1]]))
        try:
            inst.limit_type = PhysBoneLimitType(data.get("limit_type", "none"))
        except Exception:
            inst.limit_type = PhysBoneLimitType.NONE
        inst.max_angle = float(data.get("max_angle", 45.0))
        inst.max_angle_curve = _as_curve(data.get("max_angle_curve", [[0, 1], [1, 1]]))
        inst.hinge_axis = _as_vec3(data.get("hinge_axis", [1, 0, 0]), Vec3(1, 0, 0))
        inst.radius = float(data.get("radius", 0.11))
        inst.radius_curve = _as_curve(data.get("radius_curve", [[0, 1], [1, 1]]))
        inst.allow_collision = bool(data.get("allow_collision", True))
        inst.collider_entity_ids = _normalize_id_list(data.get("collider_entity_ids", []))
        inst.stretch_motion = float(data.get("stretch_motion", 0.0))
        inst.stretch_motion_curve = _as_curve(data.get("stretch_motion_curve", [[0, 1], [1, 1]]))
        inst.max_stretch = float(data.get("max_stretch", 0.0))
        inst.max_stretch_curve = _as_curve(data.get("max_stretch_curve", [[0, 1], [1, 1]]))
        inst.max_squish = float(data.get("max_squish", 0.0))
        inst.max_squish_curve = _as_curve(data.get("max_squish_curve", [[0, 1], [1, 1]]))
        inst.parameter = str(data.get("parameter", "") or "")
        inst.is_animated = bool(data.get("is_animated", False))
        inst.reset_when_disabled = bool(data.get("reset_when_disabled", False))
        inst.allow_grab = bool(data.get("allow_grab", True))
        inst.show_gizmo = bool(data.get("show_gizmo", True))
        return inst
