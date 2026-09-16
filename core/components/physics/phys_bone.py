# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import enum
import math
import numpy as np
from core.ecs.ecs import Component, ComponentRegistry, InstancePrimitive
from core.maths.math3d import Vec3, Quat
from core.components.inspector_meta import FieldType, InspectorField, ListElementField


class PhysBoneIntegration(enum.Enum):
    SIMPLIFIED = "simplified"
    ADVANCED = "advanced"

class PhysBoneMultiChild(enum.Enum):
    IGNORE = "ignore"
    FIRST_CHILD = "first"
    AVERAGE = "average"

class PhysBoneImmobileType(enum.Enum):
    ALL_MOTION = "all"
    WORLD_TRANSLATION = "translation"

class PhysBoneLimitType(enum.Enum):
    NONE = "none"
    ANGLE = "angle"
    HINGE = "hinge"

def _clamp(v, lo, hi):
    try:
        f = float(v)
    except Exception:
        f = float(lo)
    if f < lo:
        return lo
    if f > hi:
        return hi
    return f


def _clamp01(v):
    return _clamp(v, 0.0, 1.0)


def _sample_curve(curve, t):
    try:
        if not curve or len(curve) < 2:
            return 1.0
        tt = _clamp01(t)
        pts = sorted(curve, key=lambda p: float(p[0]))
        if tt <= float(pts[0][0]):
            return float(pts[0][1])
        if tt >= float(pts[-1][0]):
            return float(pts[-1][1])
        for i in range(len(pts) - 1):
            t0 = float(pts[i][0])
            t1 = float(pts[i + 1][0])
            if t0 <= tt <= t1:
                v0 = float(pts[i][1])
                v1 = float(pts[i + 1][1])
                denom = t1 - t0
                s = (tt - t0) / denom if abs(denom) > 1e-10 else 0.0
                return v0 + (v1 - v0) * s
        return float(pts[-1][1])
    except Exception:
        return 1.0


def _as_vec3(value, default):
    if isinstance(value, Vec3):
        return value
    try:
        return Vec3(float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        return default


def _as_curve(value):
    try:
        if not value:
            return [[0.0, 1.0], [1.0, 1.0]]
        out = []
        for p in value:
            out.append([float(p[0]), float(p[1])])
        if len(out) < 2:
            return [[0.0, 1.0], [1.0, 1.0]]
        return out
    except Exception:
        return [[0.0, 1.0], [1.0, 1.0]]


def _normalize_id(v):
    try:
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            for k in ("entity_id", "value", "id", "entity"):
                if k in v and isinstance(v[k], str):
                    return v[k]
            return ""
        return str(v)
    except Exception:
        return ""


def _normalize_id_list(v):
    try:
        if not v:
            return []
        if isinstance(v, str):
            return [v] if v else []
        out = []
        for item in v:
            nid = _normalize_id(item)
            if nid:
                out.append(nid)
        return out
    except Exception:
        return []


def _quat_from_two_vecs(a, b):
    try:
        ax, ay, az = float(a.x), float(a.y), float(a.z)
        bx, by, bz = float(b.x), float(b.y), float(b.z)
    except Exception:
        return Quat.identity()
    na = math.sqrt(ax * ax + ay * ay + az * az)
    nb = math.sqrt(bx * bx + by * by + bz * bz)
    if na < 1e-10 or nb < 1e-12:
        return Quat.identity()
    ux, uy, uz = ax / na, ay / na, az / na
    wx, wy, wz = bx / nb, by / nb, bz / nb
    c = ux * wx + uy * wy + uz * wz
    if c > 0.999999:
        return Quat.identity()
    if c < -0.999999:
        px, py, pz = -uy, ux, 0.0
        if px * px + py * py + pz * pz < 1e-8:
            px, py, pz = 0.0, -uz, uy
        n = math.sqrt(px * px + py * py + pz * pz)
        if n < 1e-10:
            return Quat(0.0, 0.0, 1.0, 0.0)
        return Quat(px / n, py / n, pz / n, 0.0)
    crx = uy * wz - uz * wy
    cry = uz * wx - ux * wz
    crz = ux * wy - uy * wx
    den = math.sqrt(2.0 * (1.0 + c))
    if den < 1e-10:
        return Quat.identity()
    return Quat(crx / den, cry / den, crz / den, den * 0.5).normalized()


def _world_quat_of(tr):
    try:
        m = tr.world_matrix._d
        trace = float(m[0, 0] + m[1, 1] + m[2, 2])
        if trace > 0.0:
            s = 0.5 / math.sqrt(trace + 1.0)
            q = ((float(m[2, 1] - m[1, 2]) * s), (float(m[0, 2] - m[2, 0]) * s), (float(m[1, 0] - m[0, 1]) * s), (0.25 / s))
        elif float(m[0, 0]) > float(m[1, 1]) and float(m[0, 0]) > float(m[2, 2]):
            s = 2.0 * math.sqrt(1.0 + float(m[0, 0]) - float(m[1, 1]) - float(m[2, 2]))
            q = (((float(m[2, 1]) - float(m[1, 2])) / s), ((float(m[0, 1]) + float(m[1, 0])) / s), ((float(m[0, 2]) + float(m[2, 0])) / s), (0.25 * s))
        elif float(m[1, 1]) > float(m[2, 2]):
            s = 2.0 * math.sqrt(1.0 + float(m[1, 1]) - float(m[0, 0]) - float(m[2, 2]))
            q = (((float(m[0, 1]) + float(m[1, 0])) / s), (0.25 * s), ((float(m[1, 2]) + float(m[2, 1])) / s), ((float(m[0, 2]) - float(m[2, 0])) / s))
        else:
            s = 2.0 * math.sqrt(1.0 + float(m[2, 2]) - float(m[0, 0]) - float(m[1, 1]))
            q = (((float(m[0, 2]) + float(m[2, 0])) / s), ((float(m[1, 2]) + float(m[2, 1])) / s), (0.25 * s), ((float(m[1, 0]) - float(m[0, 1])) / s))
        return Quat(-q[0], -q[1], -q[2], q[3]).normalized()
    except Exception:
        try:
            return tr.local_rotation.normalized()
        except Exception:
            return Quat.identity()


def _resolve_entity(scene, eid):
    try:
        if scene is None or not eid:
            return None
        return scene.get_entity(eid)
    except Exception:
        return None


_CY_CACHE = [None, False]


def _cy_step():
    if _CY_CACHE[1]:
        return _CY_CACHE[0]
    try:
        from core._physbone import step_physbone
        _CY_CACHE[0] = step_physbone
    except ImportError:
        _CY_CACHE[0] = None
    _CY_CACHE[1] = True
    return _CY_CACHE[0]


_GRAB_K = 22.0
_SPRING_K = 45.0
_PULL_RATE = 8.0
_AIR_DAMP = 0.02
_VMAX = 25.0
_MU = 0.35


class _PBNode:
    __slots__ = ("entity_id", "parent", "children", "is_virtual", "depth", "t", "rest_local_pos", "rest_local_quat", "rest_world_pos", "rest_world_quat", "rest_length", "rest_dir_local")
    def __init__(self):
        self.entity_id = ""
        self.parent = -1
        self.children = []
        self.is_virtual = False
        self.depth = 0
        self.t = 0.0
        self.rest_local_pos = Vec3.zero()
        self.rest_local_quat = Quat.identity()
        self.rest_world_pos = Vec3.zero()
        self.rest_world_quat = Quat.identity()
        self.rest_length = 0.0
        self.rest_dir_local = Vec3(0, 1, 0)


@ComponentRegistry.register
class PhysBone(Component):
    _icon = "Joint.png"
    _allow_multiple = True
    _gizmo_icon_color = (120, 220, 255)
    _gizmo_icon_label = "PB"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "armature"

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

    def _resolve_root(self):
        try:
            scene = self._entity._scene if self._entity is not None else None
            if scene is None:
                return None
            eid = _normalize_id(self.root_entity_id)
            if eid:
                ent = scene.get_entity(eid)
                if ent is not None:
                    return ent
            return self._entity
        except Exception:
            return None

    def _other_physbone_subtree_ids(self, scene):
        out = set()
        try:
            if scene is None:
                return out
            ents = scene.get_entities_with_component(PhysBone)
            for ent in ents:
                try:
                    for comp in ent.get_components(PhysBone):
                        if comp is self:
                            continue
                        r = None
                        try:
                            r = comp._resolve_root()
                        except Exception:
                            r = None
                        if r is None:
                            continue
                        stack = [r]
                        while stack:
                            cur = stack.pop()
                            try:
                                if cur.id in out:
                                    pass
                                else:
                                    out.add(cur.id)
                                for ch in cur.children:
                                    stack.append(ch)
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def _rebuild_chain(self):
        self._nodes = []
        self._pos = []
        self._prev = []
        self._anim = []
        self._anim_quat = []
        self._initialized = False
        self._prev_root_pos = None
        self._prev_root_quat = None
        try:
            root = self._resolve_root()
            if root is None:
                self._built_root_id = _normalize_id(self.root_entity_id)
                return False
            self._built_root_id = root.id
            try:
                mct = self.multi_child_type
                if isinstance(mct, str):
                    mct = PhysBoneMultiChild(mct)
            except Exception:
                mct = PhysBoneMultiChild.IGNORE
            ignore_set = set(_normalize_id_list(self.ignore_entity_ids))
            scene = self._entity._scene if self._entity is not None else None
            if self.ignore_other_phys_bones and scene is not None:
                try:
                    for oid in self._other_physbone_subtree_ids(scene):
                        ignore_set.add(oid)
                except Exception:
                    pass
            try:
                ignore_set.discard(root.id)
            except Exception:
                pass
            nodes: list = []
            rn = _PBNode()
            rn.entity_id = root.id
            rn.parent = -1
            rn.depth = 0
            try:
                tr = root.transform
                if tr is not None:
                    rn.rest_local_pos = Vec3(tr.local_position.x, tr.local_position.y, tr.local_position.z)
                    rn.rest_local_quat = Quat(tr.local_rotation.x, tr.local_rotation.y, tr.local_rotation.z, tr.local_rotation.w).normalized()
                    rn.rest_world_pos = tr.position
                    rn.rest_world_quat = _world_quat_of(tr)
            except Exception:
                pass
            nodes.append(rn)
            def children_of(ent):
                try:
                    chs = list(ent.children)
                except Exception:
                    return []
                out = []
                for ch in chs:
                    try:
                        if ch.id in ignore_set:
                            continue
                        out.append(ch)
                    except Exception:
                        continue
                return out
            def add_child(parent_idx, child_ent, depth):
                nn = _PBNode()
                nn.entity_id = child_ent.id
                nn.parent = parent_idx
                nn.depth = depth
                try:
                    tr = child_ent.transform
                    if tr is not None:
                        nn.rest_local_pos = Vec3(tr.local_position.x, tr.local_position.y, tr.local_position.z)
                        nn.rest_local_quat = Quat(tr.local_rotation.x, tr.local_rotation.y, tr.local_rotation.z, tr.local_rotation.w).normalized()
                        nn.rest_world_pos = tr.position
                        nn.rest_world_quat = _world_quat_of(tr)
                except Exception:
                    pass
                nodes.append(nn)
                return len(nodes) - 1
            def walk(idx):
                try:
                    ent = _resolve_entity(scene, nodes[idx].entity_id) if scene is not None else (root if idx == 0 else None)
                except Exception:
                    ent = None
                if ent is None:
                    return
                chs = children_of(ent)
                if not chs:
                    try:
                        ep = self.endpoint_position if isinstance(self.endpoint_position, Vec3) else Vec3.zero()
                        if ep.length_sq() > 1e-10:
                            vn = _PBNode()
                            vn.entity_id = ""
                            vn.parent = idx
                            vn.depth = nodes[idx].depth + 1
                            vn.is_virtual = True
                            try:
                                pw = nodes[idx].rest_world_pos
                                pq = nodes[idx].rest_world_quat
                                off = pq.rotate_vec3(ep)
                                vn.rest_world_pos = Vec3(pw.x + off.x, pw.y + off.y, pw.z + off.z)
                                vn.rest_world_quat = pq
                                vn.rest_length = ep.length()
                            except Exception:
                                pass
                            nodes.append(vn)
                            vix = len(nodes) - 1
                            nodes[idx].children.append(vix)
                    except Exception:
                        pass
                    return
                if mct == PhysBoneMultiChild.IGNORE:
                    if len(chs) != 1:
                        return
                    nix = add_child(idx, chs[0], nodes[idx].depth + 1)
                    nodes[idx].children.append(nix)
                    walk(nix)
                    return
                if mct == PhysBoneMultiChild.FIRST_CHILD:
                    nix = add_child(idx, chs[0], nodes[idx].depth + 1)
                    nodes[idx].children.append(nix)
                    walk(nix)
                    return
                for ch in chs:
                    nix = add_child(idx, ch, nodes[idx].depth + 1)
                    nodes[idx].children.append(nix)
                for cix in list(nodes[idx].children):
                    walk(cix)
            walk(0)
            max_depth = 0
            for nd in nodes:
                if nd.depth > max_depth:
                    max_depth = nd.depth
            for nd in nodes:
                nd.t = (float(nd.depth) / float(max_depth)) if max_depth > 0 else 0.0
            for i, nd in enumerate(nodes):
                if nd.parent < 0:
                    nd.rest_length = 0.0
                    continue
                try:
                    p = nodes[nd.parent].rest_world_pos
                    c = nd.rest_world_pos
                    dx = c.x - p.x
                    dy = c.y - p.y
                    dz = c.z - p.z
                    nd.rest_length = math.sqrt(dx * dx + dy * dy + dz * dz)
                except Exception:
                    nd.rest_length = 0.0
                try:
                    if not nd.is_virtual:
                        lp = nd.rest_local_pos
                        ll = math.sqrt(lp.x * lp.x + lp.y * lp.y + lp.z * lp.z)
                        if ll > 1e-10:
                            nd.rest_dir_local = Vec3(lp.x / ll, lp.y / ll, lp.z / ll)
                        else:
                            nd.rest_dir_local = Vec3(0, 1, 0)
                except Exception:
                    pass
            self._nodes = nodes
            self._pos = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in nodes]
            self._prev = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in nodes]
            self._anim = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in nodes]
            self._anim_quat = [Quat(nd.rest_world_quat.x, nd.rest_world_quat.y, nd.rest_world_quat.z, nd.rest_world_quat.w) for nd in nodes]
            try:
                if nodes:
                    self._prev_root_pos = Vec3(nodes[0].rest_world_pos.x, nodes[0].rest_world_pos.y, nodes[0].rest_world_pos.z)
                    self._prev_root_quat = Quat(nodes[0].rest_world_quat.x, nodes[0].rest_world_quat.y, nodes[0].rest_world_quat.z, nodes[0].rest_world_quat.w)
            except Exception:
                pass
            self._initialized = True
            return len(nodes) > 0
        except Exception:
            return False

    def _refresh_animated_rest(self):
        try:
            nodes = self._nodes
            if not nodes:
                return
            scene = self._entity._scene if self._entity is not None else None
            root = self._resolve_root()
            if root is None or scene is None:
                return
            anim_pos = [None] * len(nodes)
            anim_quat = [None] * len(nodes)
            try:
                rtr = root.transform
                rp = rtr.position if rtr is not None else nodes[0].rest_world_pos
                rq = _world_quat_of(rtr) if rtr is not None else nodes[0].rest_world_quat
            except Exception:
                rp = nodes[0].rest_world_pos
                rq = nodes[0].rest_world_quat
            anim_pos[0] = Vec3(rp.x, rp.y, rp.z)
            anim_quat[0] = Quat(rq.x, rq.y, rq.z, rq.w)
            try:
                ent0 = _resolve_entity(scene, nodes[0].entity_id)
                if ent0 is not None and ent0.transform is not None:
                    lq = ent0.transform.local_rotation
                    nodes[0].rest_local_quat = Quat(lq.x, lq.y, lq.z, lq.w).normalized()
                    nodes[0].rest_world_quat = Quat(rq.x, rq.y, rq.z, rq.w)
            except Exception:
                pass
            for i in range(1, len(nodes)):
                nd = nodes[i]
                p = nd.parent
                try:
                    if nd.is_virtual:
                        try:
                            ep = self.endpoint_position if isinstance(self.endpoint_position, Vec3) else Vec3.zero()
                            lq = anim_quat[p]
                            off = lq.rotate_vec3(ep)
                            bp = anim_pos[p]
                            anim_pos[i] = Vec3(bp.x + off.x, bp.y + off.y, bp.z + off.z)
                            anim_quat[i] = Quat(lq.x, lq.y, lq.z, lq.w)
                            nd.rest_world_pos = Vec3(anim_pos[i].x, anim_pos[i].y, anim_pos[i].z)
                            nd.rest_world_quat = Quat(lq.x, lq.y, lq.z, lq.w)
                        except Exception:
                            pass
                        continue
                    ent = _resolve_entity(scene, nd.entity_id)
                    if ent is None or ent.transform is None:
                        continue
                    lq = ent.transform.local_rotation
                    nq = Quat(lq.x, lq.y, lq.z, lq.w).normalized()
                    nd.rest_local_quat = nq
                    pq = anim_quat[p]
                    pw = anim_pos[p]
                    rd = nd.rest_dir_local
                    rl = float(nd.rest_length)
                    off = pq.rotate_vec3(Vec3(rd.x * rl, rd.y * rl, rd.z * rl))
                    anim_pos[i] = Vec3(pw.x + off.x, pw.y + off.y, pw.z + off.z)
                    nw = pq * nq
                    try:
                        nw = nw.normalized()
                    except Exception:
                        pass
                    anim_quat[i] = nw
                    nd.rest_world_pos = Vec3(anim_pos[i].x, anim_pos[i].y, anim_pos[i].z)
                    nd.rest_world_quat = Quat(nw.x, nw.y, nw.z, nw.w)
                except Exception:
                    continue
        except Exception:
            pass

    def _update_rigid_follow(self):
        try:
            nodes = self._nodes
            if not nodes:
                return
            root = self._resolve_root()
            if root is None or root.transform is None:
                return
            try:
                rtr = root.transform
                rp = rtr.position
                rq = _world_quat_of(rtr)
            except Exception:
                return
            anim_pos = [None] * len(nodes)
            anim_quat = [None] * len(nodes)
            anim_pos[0] = Vec3(rp.x, rp.y, rp.z)
            anim_quat[0] = Quat(rq.x, rq.y, rq.z, rq.w)
            nodes[0].rest_world_pos = Vec3(rp.x, rp.y, rp.z)
            nodes[0].rest_world_quat = Quat(rq.x, rq.y, rq.z, rq.w)
            for i in range(1, len(nodes)):
                nd = nodes[i]
                p = nd.parent
                try:
                    if anim_pos[p] is None or anim_quat[p] is None:
                        continue
                    if nd.is_virtual:
                        try:
                            ep = self.endpoint_position if isinstance(self.endpoint_position, Vec3) else Vec3.zero()
                            lq = anim_quat[p]
                            off = lq.rotate_vec3(ep)
                            bp = anim_pos[p]
                            anim_pos[i] = Vec3(bp.x + off.x, bp.y + off.y, bp.z + off.z)
                            anim_quat[i] = Quat(lq.x, lq.y, lq.z, lq.w)
                            nd.rest_world_pos = Vec3(anim_pos[i].x, anim_pos[i].y, anim_pos[i].z)
                            nd.rest_world_quat = Quat(lq.x, lq.y, lq.z, lq.w)
                        except Exception:
                            continue
                        continue
                    pq = anim_quat[p]
                    pw = anim_pos[p]
                    lq0 = nd.rest_local_quat
                    rd = nd.rest_dir_local
                    rl = float(nd.rest_length)
                    off = pq.rotate_vec3(Vec3(rd.x * rl, rd.y * rl, rd.z * rl))
                    anim_pos[i] = Vec3(pw.x + off.x, pw.y + off.y, pw.z + off.z)
                    nw = pq * lq0
                    try:
                        nw = nw.normalized()
                    except Exception:
                        pass
                    anim_quat[i] = nw
                    nd.rest_world_pos = Vec3(anim_pos[i].x, anim_pos[i].y, anim_pos[i].z)
                    nd.rest_world_quat = Quat(nw.x, nw.y, nw.z, nw.w)
                except Exception:
                    continue
        except Exception:
            pass

    def _animator_weight(self):
        try:
            name = (self.parameter or "").strip()
            if not name:
                return 1.0
            ent = self._entity
            if ent is None:
                return 1.0
            scene = ent._scene
            anim = ent.get_component_by_name("Animator") if ent is not None else None
            if anim is None and scene is not None:
                try:
                    root = self._resolve_root()
                    if root is not None:
                        anim = root.get_component_by_name("Animator")
                except Exception:
                    anim = None
            if anim is None:
                return 1.0
            try:
                v = anim.get_float(name)
            except Exception:
                try:
                    v = anim.get_bool(name)
                    v = 1.0 if v else 0.0
                except Exception:
                    return 1.0
            return _clamp01(float(v))
        except Exception:
            return 1.0

    def _resolve_colliders(self):
        out = []
        try:
            if not self.allow_collision:
                return out
            scene = self._entity._scene if self._entity is not None else None
            if scene is None:
                return out
            for eid in _normalize_id_list(self.collider_entity_ids):
                try:
                    ent = scene.get_entity(eid)
                    if ent is None:
                        continue
                    comp = ent.get_component_by_name("PhysBoneCollider")
                    if comp is None:
                        continue
                    out.append(comp)
                except Exception:
                    continue
        except Exception:
            pass
        return out

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
                        from core.components.physics.phys_bone_collider import PhysBoneColliderType
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

    def rebuild(self):
        return self._rebuild_chain()

    def reset_to_rest(self):
        try:
            nodes = self._nodes
            if not nodes:
                return
            scene = self._entity._scene if self._entity is not None else None
            if scene is None:
                return
            order = sorted(range(len(nodes)), key=lambda i: nodes[i].depth)
            for i in order:
                nd = nodes[i]
                if nd.is_virtual:
                    continue
                try:
                    ent = scene.get_entity(nd.entity_id)
                    if ent is None or ent.transform is None:
                        continue
                    ent.transform.local_position = Vec3(nd.rest_local_pos.x, nd.rest_local_pos.y, nd.rest_local_pos.z)
                    ent.transform.local_rotation = Quat(nd.rest_local_quat.x, nd.rest_local_quat.y, nd.rest_local_quat.z, nd.rest_local_quat.w)
                except Exception:
                    continue
            self._pos = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in nodes]
            self._prev = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in nodes]
            self._anim = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in nodes]
        except Exception:
            pass

    def chain_entities(self):
        out = []
        try:
            scene = self._entity._scene if self._entity is not None else None
            if scene is None:
                return out
            for nd in self._nodes:
                if nd.is_virtual:
                    continue
                ent = scene.get_entity(nd.entity_id)
                if ent is not None:
                    out.append(ent)
        except Exception:
            pass
        return out

    @property
    def particle_count(self):
        try:
            return len(self._nodes)
        except Exception:
            return 0

    @property
    def grab_active(self):
        try:
            return self._grab_index >= 0 and self._grab_target is not None
        except Exception:
            return False

    def chain_entity_id(self, index):
        try:
            nd = self._nodes[index]
            if nd.is_virtual:
                p = nd.parent
                while p >= 0 and self._nodes[p].is_virtual:
                    p = self._nodes[p].parent
                return self._nodes[p].entity_id if p >= 0 else ""
            return nd.entity_id
        except Exception:
            return ""

    def debug_grab_begin(self, index, world_pos):
        try:
            if not self.allow_grab:
                return False
            if not self._begin_frame():
                return False
            if index <= 0 or index >= len(self._nodes):
                return False
            snap = []
            try:
                scene = self._entity._scene if self._entity is not None else None
                if scene is not None:
                    for nd in self._nodes:
                        if nd.is_virtual:
                            continue
                        ent = scene.get_entity(nd.entity_id)
                        if ent is None or ent.transform is None:
                            continue
                        tr = ent.transform
                        snap.append((nd.entity_id, Vec3(tr.local_position.x, tr.local_position.y, tr.local_position.z), Quat(tr.local_rotation.x, tr.local_rotation.y, tr.local_rotation.z, tr.local_rotation.w)))
            except Exception:
                pass
            self._grab_snapshot = snap
            self._pos = [Vec3(p.x, p.y, p.z) for p in self._anim]
            self._prev = [Vec3(p.x, p.y, p.z) for p in self._anim]
            self._grab_index = int(index)
            self._grab_target = Vec3(world_pos.x, world_pos.y, world_pos.z)
            return True
        except Exception:
            return False

    def debug_grab_move(self, world_pos):
        try:
            if self._grab_index < 0:
                return False
            self._grab_target = Vec3(world_pos.x, world_pos.y, world_pos.z)
            return True
        except Exception:
            return False

    def debug_grab_end(self, restore):
        try:
            self._grab_index = -1
            self._grab_target = None
            if restore and self._grab_snapshot:
                try:
                    scene = self._entity._scene if self._entity is not None else None
                    if scene is not None:
                        for eid, lp, lq in self._grab_snapshot:
                            ent = scene.get_entity(eid)
                            if ent is None or ent.transform is None:
                                continue
                            ent.transform.local_position = Vec3(lp.x, lp.y, lp.z)
                            ent.transform.local_rotation = Quat(lq.x, lq.y, lq.z, lq.w)
                except Exception:
                    pass
                try:
                    if self._begin_frame():
                        self._pos = [Vec3(p.x, p.y, p.z) for p in self._anim]
                        self._prev = [Vec3(p.x, p.y, p.z) for p in self._anim]
                except Exception:
                    pass
            self._grab_snapshot = None
        except Exception:
            pass

    def preview_step(self, dt):
        try:
            self.on_update(float(dt))
        except Exception:
            pass

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

    def ensure_built(self):
        try:
            if self._nodes:
                return True
            return bool(self._rebuild_chain())
        except Exception:
            return False

    def _begin_frame(self):
        try:
            if self._entity is None:
                return False
            if not self._nodes:
                if not self._rebuild_chain():
                    return False
            else:
                try:
                    root = self._resolve_root()
                    rid = root.id if root is not None else _normalize_id(self.root_entity_id)
                    if rid != self._built_root_id:
                        if not self._rebuild_chain():
                            return False
                except Exception:
                    pass
            if not self._nodes:
                return False
            if self.is_animated:
                try:
                    self._refresh_animated_rest()
                except Exception:
                    pass
            else:
                try:
                    self._update_rigid_follow()
                except Exception:
                    pass
            try:
                nodes = self._nodes
                anim = [Vec3(nd.rest_world_pos.x, nd.rest_world_pos.y, nd.rest_world_pos.z) for nd in nodes]
                anim_q = [Quat(nd.rest_world_quat.x, nd.rest_world_quat.y, nd.rest_world_quat.z, nd.rest_world_quat.w) for nd in nodes]
                self._anim = anim
                self._anim_quat = anim_q
            except Exception:
                return False
            return True
        except Exception:
            return False

    def on_update(self, dt: float):
        try:
            if self._entity is None or not self.enabled:
                return
            if not self._begin_frame():
                return
            try:
                fdt = float(dt)
            except Exception:
                fdt = 0.016
            if fdt <= 1e-6:
                return
            if fdt > 0.033:
                fdt = 0.033
            w = self._animator_weight()
            if w <= 0.001:
                try:
                    self._pos = [Vec3(p.x, p.y, p.z) for p in self._anim]
                    self._prev = [Vec3(p.x, p.y, p.z) for p in self._anim]
                    self._apply_to_transforms(self._anim, self._anim_quat, 0.0)
                except Exception:
                    pass
                return
            try:
                adv = self.integration_type
                if isinstance(adv, str):
                    adv = PhysBoneIntegration(adv)
            except Exception:
                adv = PhysBoneIntegration.SIMPLIFIED
            if adv == PhysBoneIntegration.ADVANCED:
                iterations = 3
            else:
                iterations = 2
            try:
                substeps = int(math.ceil(fdt / (1.0 / 60.0)))
            except Exception:
                substeps = 1
            if substeps < 1:
                substeps = 1
            if substeps > 4:
                substeps = 4
            try:
                imt = self.immobile_type
                if isinstance(imt, str):
                    imt = PhysBoneImmobileType(imt)
            except Exception:
                imt = PhysBoneImmobileType.ALL_MOTION
            nodes = self._nodes
            root_delta = Vec3.zero()
            try:
                r0 = self._anim[0]
                if self._prev_root_pos is not None and imt == PhysBoneImmobileType.WORLD_TRANSLATION:
                    root_delta = Vec3(r0.x - self._prev_root_pos.x, r0.y - self._prev_root_pos.y, r0.z - self._prev_root_pos.z)
                self._prev_root_pos = Vec3(r0.x, r0.y, r0.z)
                try:
                    self._prev_root_quat = Quat(self._anim_quat[0].x, self._anim_quat[0].y, self._anim_quat[0].z, self._anim_quat[0].w)
                except Exception:
                    pass
            except Exception:
                pass
            if len(self._pos) != len(nodes) or len(self._prev) != len(nodes):
                self._pos = [Vec3(p.x, p.y, p.z) for p in self._anim]
                self._prev = [Vec3(p.x, p.y, p.z) for p in self._anim]
            if imt == PhysBoneImmobileType.WORLD_TRANSLATION:
                try:
                    if root_delta.length_sq() > 1e-12:
                        for i in range(1, len(self._pos)):
                            p = self._pos[i]
                            self._pos[i] = Vec3(p.x + root_delta.x, p.y + root_delta.y, p.z + root_delta.z)
                            q = self._prev[i]
                            self._prev[i] = Vec3(q.x + root_delta.x, q.y + root_delta.y, q.z + root_delta.z)
                except Exception:
                    pass
            sdt = fdt / float(substeps)
            try:
                colliders = self._resolve_colliders()
            except Exception:
                colliders = []
            fn = _cy_step()
            if fn is not None:
                try:
                    final = self._step_cython(fn, fdt, substeps, iterations, colliders, w)
                    try:
                        self._apply_to_transforms(final, self._anim_quat, w)
                    except Exception:
                        pass
                    try:
                        self._pos = final
                    except Exception:
                        pass
                    return
                except Exception:
                    pass
            for _ in range(substeps):
                try:
                    self._integrate(sdt)
                except Exception:
                    pass
                for _it in range(iterations):
                    try:
                        self._solve_lengths()
                    except Exception:
                        pass
                    try:
                        self._solve_limits()
                    except Exception:
                        pass
                    try:
                        if colliders:
                            self._solve_collisions(colliders)
                    except Exception:
                        pass
            try:
                final = self._blend_final(w)
            except Exception:
                return
            try:
                self._apply_to_transforms(final, self._anim_quat, w)
            except Exception:
                pass
            try:
                self._pos = final
            except Exception:
                pass
        except Exception:
            pass

    def _integrate(self, dt):
        try:
            nodes = self._nodes
            anim = self._anim
            if not nodes or not anim or len(anim) != len(nodes):
                return
            if len(self._pos) != len(nodes):
                self._pos = [Vec3(p.x, p.y, p.z) for p in anim]
            if len(self._prev) != len(nodes):
                self._prev = [Vec3(p.x, p.y, p.z) for p in anim]
            dt2 = dt * dt
            for i in range(len(nodes)):
                if i == 0:
                    try:
                        a = anim[0]
                        self._pos[0] = Vec3(a.x, a.y, a.z)
                        self._prev[0] = Vec3(a.x, a.y, a.z)
                    except Exception:
                        pass
                    continue
                try:
                    nd = nodes[i]
                    t = nd.t
                    pull_i = self._pb_value(self.pull, self.pull_curve, t, 0.0, 1.0)
                    spring_i = self._pb_value(self.spring, self.spring_curve, t, 0.0, 1.0)
                    grav_i = _clamp(float(self.gravity) * float(_sample_curve(self.gravity_curve, t)), -1.0, 1.0)
                    try:
                        fall = self._pb_value(self.gravity_falloff, self.gravity_falloff_curve, t, 0.0, 1.0)
                    except Exception:
                        fall = 0.0
                    grav_i = grav_i * (1.0 - float(fall) * float(t))
                    p = self._pos[i]
                    pr = self._prev[i]
                    a = anim[i]
                    damp_i = self._pb_value(self.damping, self.damping_curve, t, 0.0, 1.0)
                    dd = _AIR_DAMP + float(damp_i)
                    if dd < 0.0:
                        dd = 0.0
                    if dd > 0.8:
                        dd = 0.8
                    keep = 1.0 - float(dd)
                    vx = (p.x - pr.x) * keep
                    vy = (p.y - pr.y) * keep
                    vz = (p.z - pr.z) * keep
                    try:
                        vl = math.sqrt(vx * vx + vy * vy + vz * vz)
                        vmax = _VMAX * float(dt)
                        if vl > vmax and vl > 1e-12:
                            sc = vmax / vl
                            vx *= sc
                            vy *= sc
                            vz *= sc
                    except Exception:
                        pass
                    ax = (a.x - p.x) * float(spring_i) * _SPRING_K
                    ay = (a.y - p.y) * float(spring_i) * _SPRING_K - float(grav_i) * 9.81
                    az = (a.z - p.z) * float(spring_i) * _SPRING_K
                    nx = p.x + vx + ax * dt2
                    ny = p.y + vy + ay * dt2
                    nz = p.z + vz + az * dt2
                    try:
                        pf = 1.0 - math.exp(-float(pull_i) * _PULL_RATE * float(dt))
                    except Exception:
                        pf = float(pull_i)
                    if pf < 0.0:
                        pf = 0.0
                    if pf > 1.0:
                        pf = 1.0
                    if pf > 1e-6:
                        nx = nx + (a.x - nx) * pf
                        ny = ny + (a.y - ny) * pf
                        nz = nz + (a.z - nz) * pf
                    try:
                        if self._grab_target is not None and self._grab_index == i and self.allow_grab:
                            gk = 1.0 - math.exp(-_GRAB_K * float(dt))
                            nx += (self._grab_target.x - nx) * gk
                            ny += (self._grab_target.y - ny) * gk
                            nz += (self._grab_target.z - nz) * gk
                    except Exception:
                        pass
                    self._prev[i] = Vec3(p.x, p.y, p.z)
                    self._pos[i] = Vec3(nx, ny, nz)
                except Exception:
                    continue
        except Exception:
            pass

    def _solve_lengths(self):
        try:
            nodes = self._nodes
            for i in range(1, len(nodes)):
                try:
                    nd = nodes[i]
                    p = nd.parent
                    if p < 0:
                        continue
                    rest = float(nd.rest_length)
                    if rest < 1e-9:
                        continue
                    t = nd.t
                    sm = self._pb_value(self.stretch_motion, self.stretch_motion_curve, t, 0.0, 1.0)
                    mx = self._pb_value(self.max_stretch, self.max_stretch_curve, t, 0.0, 2.0)
                    sq = self._pb_value(self.max_squish, self.max_squish_curve, t, 0.0, 1.0)
                    pp = self._pos[p]
                    cp = self._pos[i]
                    dx = cp.x - pp.x
                    dy = cp.y - pp.y
                    dz = cp.z - pp.z
                    cur = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if cur < 1e-9:
                        try:
                            a = self._anim[i]
                            b = self._anim[p]
                            ddx = a.x - b.x
                            ddy = a.y - b.y
                            ddz = a.z - b.z
                            l = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz)
                            if l < 1e-9:
                                ddx, ddy, ddz = 0.0, -1.0, 0.0
                                l = 1.0
                            inv = rest / l
                            self._pos[i] = Vec3(pp.x + ddx * inv, pp.y + ddy * inv, pp.z + ddz * inv)
                        except Exception:
                            pass
                        continue
                    lo = rest * (1.0 - float(sq))
                    hi = rest * (1.0 + float(mx))
                    if lo < 0.0:
                        lo = 0.0
                    clamped = cur
                    if clamped < lo:
                        clamped = lo
                    if clamped > hi:
                        clamped = hi
                    target = rest + (clamped - rest) * float(sm)
                    corr = target - cur
                    if abs(corr) < 1e-12:
                        continue
                    ux = dx / cur
                    uy = dy / cur
                    uz = dz / cur
                    try:
                        gi = int(self._grab_index)
                    except Exception:
                        gi = -1
                    wi = 0.0
                    wp = 0.0
                    if i != gi:
                        wi = 1.0
                    if p != 0 and p != gi:
                        wp = 1.0
                    ws = wi + wp
                    if ws < 1e-10:
                        continue
                    si = corr * (wi / ws)
                    sp = corr * (wp / ws)
                    self._pos[i] = Vec3(cp.x + ux * si, cp.y + uy * si, cp.z + uz * si)
                    pp = self._pos[p]
                    self._pos[p] = Vec3(pp.x - ux * sp, pp.y - uy * sp, pp.z - uz * sp)
                except Exception:
                    continue
        except Exception:
            pass

    def _solve_limits(self):
        try:
            lt = self.limit_type
            if isinstance(lt, str):
                try:
                    lt = PhysBoneLimitType(lt)
                except Exception:
                    lt = PhysBoneLimitType.NONE
            if lt == PhysBoneLimitType.NONE:
                return
            nodes = self._nodes
            anim = self._anim
            for i in range(1, len(nodes)):
                try:
                    nd = nodes[i]
                    p = nd.parent
                    if p < 0:
                        continue
                    t = nd.t
                    ma = self._pb_value(self.max_angle, self.max_angle_curve, t, 0.0, 180.0)
                    if ma >= 179.9:
                        continue
                    if ma <= 1e-6:
                        try:
                            ap = anim[p]
                            ac = anim[i]
                            pp = self._pos[p]
                            dx = ac.x - ap.x
                            dy = ac.y - ap.y
                            dz = ac.z - ap.z
                            l = math.sqrt(dx * dx + dy * dy + dz * dz)
                            cp = self._pos[i]
                            cl = math.sqrt((cp.x - pp.x) ** 2 + (cp.y - pp.y) ** 2 + (cp.z - pp.z) ** 2)
                            if l < 1e-9 or cl < 1e-9:
                                continue
                            inv = cl / l
                            self._pos[i] = Vec3(pp.x + dx * inv, pp.y + dy * inv, pp.z + dz * inv)
                        except Exception:
                            pass
                        continue
                    pp = self._pos[p]
                    cp = self._pos[i]
                    cdx = cp.x - pp.x
                    cdy = cp.y - pp.y
                    cdz = cp.z - pp.z
                    clen = math.sqrt(cdx * cdx + cdy * cdy + cdz * cdz)
                    if clen < 1e-9:
                        continue
                    cdx /= clen
                    cdy /= clen
                    cdz /= clen
                    if lt == PhysBoneLimitType.HINGE:
                        self._solve_hinge(i, ma, (cdx, cdy, cdz), clen)
                        continue
                    gp = nodes[p].parent
                    if gp < 0:
                        try:
                            ap = anim[p]
                            ac = anim[i]
                            rdx = ac.x - ap.x
                            rdy = ac.y - ap.y
                            rdz = ac.z - ap.z
                            rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                            if rl < 1e-9:
                                continue
                            rdx /= rl
                            rdy /= rl
                            rdz /= rl
                            dot = cdx * rdx + cdy * rdy + cdz * rdz
                            if dot > 1.0:
                                dot = 1.0
                            if dot < -1.0:
                                dot = -1.0
                            ang = math.degrees(math.acos(dot))
                            if ang <= ma + 1e-6:
                                continue
                            arc = _quat_from_two_vecs(Vec3(cdx, cdy, cdz), Vec3(rdx, rdy, rdz))
                            try:
                                back = arc.conjugate().normalized()
                            except Exception:
                                back = Quat.identity()
                            excess = ang - ma
                            corr = Quat.from_axis_angle(Vec3(back.x, back.y, back.z) if (abs(back.x) + abs(back.y) + abs(back.z)) > 1e-9 else Vec3(1, 0, 0), 0.0)
                            try:
                                axis = Vec3(cdy * rdz - cdz * rdy, cdz * rdx - cdx * rdz, cdx * rdy - cdy * rdx)
                                if axis.length_sq() < 1e-12:
                                    axis = Vec3(1, 0, 0)
                                else:
                                    axis = axis.normalized()
                                corr = Quat.from_axis_angle(axis, excess)
                            except Exception:
                                continue
                            nd2 = corr.rotate_vec3(Vec3(cdx, cdy, cdz))
                            try:
                                nd2 = nd2.normalized()
                            except Exception:
                                pass
                            self._pos[i] = Vec3(pp.x + nd2.x * clen, pp.y + nd2.y * clen, pp.z + nd2.z * clen)
                        except Exception:
                            continue
                    else:
                        try:
                            gpp = self._pos[gp]
                            pdx = pp.x - gpp.x
                            pdy = pp.y - gpp.y
                            pdz = pp.z - gpp.z
                            plen = math.sqrt(pdx * pdx + pdy * pdy + pdz * pdz)
                            ap = anim[p]
                            ag = anim[gp]
                            ac = anim[i]
                            rdx = ac.x - ap.x
                            rdy = ac.y - ap.y
                            rdz = ac.z - ap.z
                            rpx = ap.x - ag.x
                            rpy = ap.y - ag.y
                            rpz = ap.z - ag.z
                            rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                            rpl = math.sqrt(rpx * rpx + rpy * rpy + rpz * rpz)
                            if plen < 1e-9 or rl < 1e-9 or rpl < 1e-9:
                                continue
                            pdx /= plen
                            pdy /= plen
                            pdz /= plen
                            rdx /= rl
                            rdy /= rl
                            rdz /= rl
                            rpx /= rpl
                            rpy /= rpl
                            rpz /= rpl
                            align = _quat_from_two_vecs(Vec3(pdx, pdy, pdz), Vec3(rpx, rpy, rpz))
                            cal = align.rotate_vec3(Vec3(cdx, cdy, cdz))
                            try:
                                cal = cal.normalized()
                            except Exception:
                                pass
                            restv = Vec3(rdx, rdy, rdz)
                            dot = cal.x * restv.x + cal.y * restv.y + cal.z * restv.z
                            if dot > 1.0:
                                dot = 1.0
                            if dot < -1.0:
                                dot = -1.0
                            ang = math.degrees(math.acos(dot))
                            if ang <= ma + 1e-6:
                                continue
                            try:
                                axis = Vec3(cal.y * restv.z - cal.z * restv.y, cal.z * restv.x - cal.x * restv.z, cal.x * restv.y - cal.y * restv.x)
                                if axis.length_sq() < 1e-12:
                                    continue
                                axis = axis.normalized()
                                corr = Quat.from_axis_angle(axis, ang - ma)
                                fixed = corr.rotate_vec3(cal)
                                try:
                                    fixed = fixed.normalized()
                                except Exception:
                                    pass
                                try:
                                    back = align.conjugate().normalized()
                                except Exception:
                                    back = Quat.identity()
                                world_fixed = back.rotate_vec3(fixed)
                                try:
                                    world_fixed = world_fixed.normalized()
                                except Exception:
                                    pass
                                self._pos[i] = Vec3(pp.x + world_fixed.x * clen, pp.y + world_fixed.y * clen, pp.z + world_fixed.z * clen)
                            except Exception:
                                continue
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass

    def _solve_hinge(self, idx, max_angle, cur_dir_t, cur_len):
        try:
            nodes = self._nodes
            anim = self._anim
            anim_q = self._anim_quat
            nd = nodes[idx]
            p = nd.parent
            pp = self._pos[p]
            cdx, cdy, cdz = cur_dir_t
            cur = Vec3(cdx, cdy, cdz)
            try:
                ap = anim[p]
                ac = anim[idx]
                rdx = ac.x - ap.x
                rdy = ac.y - ap.y
                rdz = ac.z - ap.z
                rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                if rl < 1e-9:
                    return
                rest = Vec3(rdx / rl, rdy / rl, rdz / rl)
            except Exception:
                return
            try:
                hx = self.hinge_axis if isinstance(self.hinge_axis, Vec3) else Vec3(1, 0, 0)
                if hx.length_sq() < 1e-10:
                    hx = Vec3(1, 0, 0)
                pq = anim_q[p] if p < len(anim_q) else Quat.identity()
                axis = pq.rotate_vec3(hx.normalized())
            except Exception:
                axis = Vec3(1, 0, 0)
            try:
                axis = axis.normalized()
            except Exception:
                return
            rp = rest.x * axis.x + rest.y * axis.y + rest.z * axis.z
            cp = cur.x * axis.x + cur.y * axis.y + cur.z * axis.z
            rpx = rest.x - axis.x * rp
            rpy = rest.y - axis.y * rp
            rpz = rest.z - axis.z * rp
            cpx = cur.x - axis.x * cp
            cpy = cur.y - axis.y * cp
            cpz = cur.z - axis.z * cp
            rpl = math.sqrt(rpx * rpx + rpy * rpy + rpz * rpz)
            cpl = math.sqrt(cpx * cpx + cpy * cpy + cpz * cpz)
            if rpl < 1e-8:
                try:
                    up = Vec3(0, 1, 0) if abs(axis.y) < 0.9 else Vec3(1, 0, 0)
                    tmp = Vec3(axis.y * up.z - axis.z * up.y, axis.z * up.x - axis.x * up.z, axis.x * up.y - axis.y * up.x).normalized()
                    rpx, rpy, rpz = tmp.x, tmp.y, tmp.z
                    rpl = 1.0
                except Exception:
                    return
            if cpl < 1e-8:
                cpx, cpy, cpz = rpx / rpl, rpy / rpl, rpz / rpl
                cpl = 1.0
            rpx /= rpl
            rpy /= rpl
            rpz /= rpl
            cpx /= cpl
            cpy /= cpl
            cpz /= cpl
            dot = rpx * cpx + rpy * cpy + rpz * cpz
            if dot > 1.0:
                dot = 1.0
            if dot < -1.0:
                dot = -1.0
            ang = math.degrees(math.acos(dot))
            cx = rpy * cpz - rpz * cpy
            cy = rpz * cpx - rpx * cpz
            cz = rpx * cpy - rpy * cpx
            s = cx * axis.x + cy * axis.y + cz * axis.z
            signed = ang if s >= 0.0 else -ang
            lim = float(max_angle)
            cs = signed
            if cs > lim:
                cs = lim
            if cs < -lim:
                cs = -lim
            try:
                rot = Quat.from_axis_angle(axis, cs)
                npx = rot.rotate_vec3(Vec3(rpx, rpy, rpz))
                try:
                    npx = npx.normalized()
                except Exception:
                    pass
            except Exception:
                npx = Vec3(rpx, rpy, rpz)
            rplen = math.sqrt(max(0.0, 1.0 - rp * rp))
            ndir = Vec3(axis.x * rp + npx.x * rplen, axis.y * rp + npx.y * rplen, axis.z * rp + npx.z * rplen)
            try:
                ndir = ndir.normalized()
            except Exception:
                pass
            self._pos[idx] = Vec3(pp.x + ndir.x * cur_len, pp.y + ndir.y * cur_len, pp.z + ndir.z * cur_len)
        except Exception:
            pass

    def _solve_collisions(self, colliders):
        try:
            nodes = self._nodes
            for i in range(1, len(nodes)):
                try:
                    t = nodes[i].t
                    pr = self._pb_value(self.radius, self.radius_curve, t, 0.0, 2.0)
                    if pr <= 1e-9:
                        continue
                    p = self._pos[i]
                    for col in colliders:
                        try:
                            p = col.collide(p, float(pr))
                        except Exception:
                            continue
                    try:
                        old = self._pos[i]
                        dx = p.x - old.x
                        dy = p.y - old.y
                        dz = p.z - old.z
                        if dx * dx + dy * dy + dz * dz > 1e-18:
                            pv = self._prev[i]
                            vx = (p.x - pv.x) * (1.0 - _MU)
                            vy = (p.y - pv.y) * (1.0 - _MU)
                            vz = (p.z - pv.z) * (1.0 - _MU)
                            self._prev[i] = Vec3(p.x - vx, p.y - vy, p.z - vz)
                    except Exception:
                        pass
                    self._pos[i] = p
                except Exception:
                    continue
        except Exception:
            pass

    def _blend_final(self, weight):
        try:
            nodes = self._nodes
            anim = self._anim
            out = []
            w = _clamp01(weight)
            for i in range(len(nodes)):
                try:
                    t = nodes[i].t
                    im = self._pb_value(self.immobile, self.immobile_curve, t, 0.0, 1.0)
                    follow = 1.0 - (1.0 - float(im)) * float(w)
                    if follow < 0.0:
                        follow = 0.0
                    if follow > 1.0:
                        follow = 1.0
                    s = self._pos[i]
                    a = anim[i]
                    out.append(Vec3(s.x + (a.x - s.x) * follow, s.y + (a.y - s.y) * follow, s.z + (a.z - s.z) * follow))
                except Exception:
                    try:
                        out.append(Vec3(anim[i].x, anim[i].y, anim[i].z))
                    except Exception:
                        pass
            return out
        except Exception:
            return self._pos

    def _apply_to_transforms(self, final, anim_quat, weight):
        try:
            from core.math_helpers import mat4_inv_fast
        except Exception:
            mat4_inv_fast = None
        try:
            nodes = self._nodes
            scene = self._entity._scene if self._entity is not None else None
            if scene is None or not nodes or not final or len(final) != len(nodes):
                return
            new_wq = {}
            for i in range(len(nodes)):
                nd = nodes[i]
                if nd.is_virtual:
                    continue
                try:
                    ent = scene.get_entity(nd.entity_id)
                    if ent is None or ent.transform is None:
                        continue
                    tr = ent.transform
                    if i == 0:
                        if nd.children:
                            try:
                                pp = final[0]
                                dx = 0.0
                                dy = 0.0
                                dz = 0.0
                                n = 0
                                for cix in nd.children:
                                    cp = final[cix]
                                    dx += cp.x - pp.x
                                    dy += cp.y - pp.y
                                    dz += cp.z - pp.z
                                    n += 1
                                if n > 0:
                                    dx /= n
                                    dy /= n
                                    dz /= n
                                l = math.sqrt(dx * dx + dy * dy + dz * dz)
                                if l > 1e-9:
                                    desired = Vec3(dx / l, dy / l, dz / l)
                                    ap = self._anim[0]
                                    rest_dir = None
                                    rdx = 0.0
                                    rdy = 0.0
                                    rdz = 0.0
                                    rn2 = 0
                                    for cix in nd.children:
                                        apc = self._anim[cix]
                                        rdx += apc.x - ap.x
                                        rdy += apc.y - ap.y
                                        rdz += apc.z - ap.z
                                        rn2 += 1
                                    if rn2 > 0:
                                        rdx /= rn2
                                        rdy /= rn2
                                        rdz /= rn2
                                    rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                                    if rl > 1e-9:
                                        rest_dir = Vec3(rdx / rl, rdy / rl, rdz / rl)
                                    if rest_dir is not None:
                                        arc = _quat_from_two_vecs(rest_dir, desired)
                                        base = anim_quat[0] if 0 < len(anim_quat) else _world_quat_of(tr)
                                        nq_world = arc * base
                                        try:
                                            nq_world = nq_world.normalized()
                                        except Exception:
                                            pass
                                        new_wq[i] = nq_world
                                        parent = ent.parent
                                        if parent is not None and parent.transform is not None:
                                            pwq = _world_quat_of(parent.transform)
                                            try:
                                                local = pwq.conjugate().normalized() * nq_world
                                                try:
                                                    local = local.normalized()
                                                except Exception:
                                                    pass
                                                tr.local_rotation = local
                                            except Exception:
                                                pass
                                        else:
                                            tr.local_rotation = nq_world
                            except Exception:
                                pass
                        continue
                    p = nd.parent
                    pent = scene.get_entity(nodes[p].entity_id) if p >= 0 else None
                    if pent is None or pent.transform is None:
                        continue
                    ptr = pent.transform
                    fp = final[i]
                    pp = final[p]
                    handled = False
                    try:
                        pwm = ptr.world_matrix._d
                        n0 = pwm[0, 0] * pwm[0, 0] + pwm[0, 1] * pwm[0, 1] + pwm[0, 2] * pwm[0, 2]
                        n1 = pwm[1, 0] * pwm[1, 0] + pwm[1, 1] * pwm[1, 1] + pwm[1, 2] * pwm[1, 2]
                        n2 = pwm[2, 0] * pwm[2, 0] + pwm[2, 1] * pwm[2, 1] + pwm[2, 2] * pwm[2, 2]
                        n3 = pwm[0, 0] * pwm[0, 0] + pwm[1, 0] * pwm[1, 0] + pwm[2, 0] * pwm[2, 0]
                        n4 = pwm[0, 1] * pwm[0, 1] + pwm[1, 1] * pwm[1, 1] + pwm[2, 1] * pwm[2, 1]
                        n5 = pwm[0, 2] * pwm[0, 2] + pwm[1, 2] * pwm[1, 2] + pwm[2, 2] * pwm[2, 2]
                        mxn = n0
                        mnn = n0
                        for _nv in (n1, n2, n3, n4, n5):
                            if _nv > mxn:
                                mxn = _nv
                            if _nv < mnn:
                                mnn = _nv
                        if mxn - mnn <= 1e-9 * (1.0 + mxn):
                            ssu = math.sqrt((n0 + n1 + n2 + n3 + n4 + n5) / 6.0)
                            if ssu < 1e-9:
                                ssu = 1.0
                            qp = new_wq.get(p)
                            if qp is None:
                                qp = _world_quat_of(ptr)
                            dx = (fp.x - pp.x) / ssu
                            dy = (fp.y - pp.y) / ssu
                            dz = (fp.z - pp.z) / ssu
                            qx = -qp.x
                            qy = -qp.y
                            qz = -qp.z
                            qw = qp.w
                            tx = 2.0 * (qy * dz - qz * dy)
                            ty = 2.0 * (qz * dx - qx * dz)
                            tz = 2.0 * (qx * dy - qy * dx)
                            lx = dx + qw * tx + (qy * tz - qz * ty)
                            ly = dy + qw * ty + (qz * tx - qx * tz)
                            lz = dz + qw * tz + (qx * ty - qy * tx)
                            tr.local_position = Vec3(float(lx), float(ly), float(lz))
                            handled = True
                    except Exception:
                        handled = False
                    if not handled:
                        try:
                            pwm = ptr.world_matrix._d
                        except Exception:
                            continue
                        if mat4_inv_fast is None:
                            continue
                        try:
                            inv = mat4_inv_fast(pwm)
                        except Exception:
                            continue
                        try:
                            wv = np.array([float(fp.x), float(fp.y), float(fp.z), 1.0], dtype=np.float64)
                            lv = wv @ inv
                            tr.local_position = Vec3(float(lv[0]), float(lv[1]), float(lv[2]))
                        except Exception:
                            continue
                    if nd.children:
                        try:
                            pp2 = final[i]
                            dx = 0.0
                            dy = 0.0
                            dz = 0.0
                            n = 0
                            for cix in nd.children:
                                cp = final[cix]
                                dx += cp.x - pp2.x
                                dy += cp.y - pp2.y
                                dz += cp.z - pp2.z
                                n += 1
                            if n == 0:
                                continue
                            dx /= n
                            dy /= n
                            dz /= n
                            l = math.sqrt(dx * dx + dy * dy + dz * dz)
                            if l < 1e-9:
                                continue
                            desired = Vec3(dx / l, dy / l, dz / l)
                            ap = self._anim[i]
                            rdx = 0.0
                            rdy = 0.0
                            rdz = 0.0
                            rn2 = 0
                            for cix in nd.children:
                                apc = self._anim[cix]
                                rdx += apc.x - ap.x
                                rdy += apc.y - ap.y
                                rdz += apc.z - ap.z
                                rn2 += 1
                            if rn2 == 0:
                                continue
                            rdx /= rn2
                            rdy /= rn2
                            rdz /= rn2
                            rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz)
                            if rl < 1e-9:
                                continue
                            rest_dir = Vec3(rdx / rl, rdy / rl, rdz / rl)
                            arc = _quat_from_two_vecs(rest_dir, desired)
                            base = anim_quat[i] if i < len(anim_quat) else _world_quat_of(tr)
                            nq_world = arc * base
                            try:
                                nq_world = nq_world.normalized()
                            except Exception:
                                pass
                            new_wq[i] = nq_world
                            pwq = new_wq.get(p)
                            if pwq is None:
                                pwq = _world_quat_of(ptr)
                            try:
                                local = pwq.conjugate().normalized() * nq_world
                                try:
                                    local = local.normalized()
                                except Exception:
                                    pass
                                tr.local_rotation = local
                            except Exception:
                                pass
                        except Exception:
                            pass
                    else:
                        try:
                            rq = nd.rest_local_quat
                            tr.local_rotation = Quat(rq.x, rq.y, rq.z, rq.w)
                        except Exception:
                            pass
                except Exception:
                    continue
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
    def deserialize(cls, data: dict) -> PhysBone:
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
