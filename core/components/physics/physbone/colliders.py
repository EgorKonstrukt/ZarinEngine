# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.maths.math3d import Vec3, Quat
from .mathx import _clamp01, _normalize_id_list, _world_quat_of
class CollidersMixin:
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
