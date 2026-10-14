# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.maths.math3d import Vec3, Quat
class GrabMixin:
    @property
    def grab_active(self):
        try:
            return self._grab_index >= 0 and self._grab_target is not None
        except Exception:
            return False
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
