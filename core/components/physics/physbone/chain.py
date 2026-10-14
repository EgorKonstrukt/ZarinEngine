# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import math
from core.maths.math3d import Vec3, Quat
from .types import PhysBoneMultiChild
from .mathx import _normalize_id, _normalize_id_list, _world_quat_of, _resolve_entity
from .node import _PBNode
class ChainMixin:
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
            _PB = type(self)
            ents = scene.get_entities_with_component(_PB)
            for ent in ents:
                try:
                    for comp in ent.get_components(_PB):
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
        self._nodes = []; self._pos = []; self._prev = []; self._anim = []; self._anim_quat = []
        self._initialized = False; self._prev_root_pos = None; self._prev_root_quat = None
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
    def rebuild(self): return self._rebuild_chain()
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
    def ensure_built(self):
        try:
            if self._nodes: return True
            return bool(self._rebuild_chain())
        except Exception: return False
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
