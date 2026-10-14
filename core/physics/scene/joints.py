# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional
from core.foundation.logger import Logger


class JointsMixin:
    def _create_entity_joints(self, entity):
        from core.components import Joint
        joint = entity.get_component(Joint)
        if not joint or not joint.enabled:
            return
        body_a_id = self._entity_to_body.get(entity.id)
        if body_a_id is None:
            return
        connected = self._find_entity_by_name(joint.connected_entity_name)
        if connected is None:
            Logger.warning(f"Joint: connected entity '{joint.connected_entity_name}' not found")
            return
        body_b_id = self._entity_to_body.get(connected.id)
        if body_b_id is None:
            Logger.warning(f"Joint: connected entity '{joint.connected_entity_name}' has no body")
            return
        joint_id = self._solver.create_joint(
            joint_type=joint.joint_type,
            body_a_id=body_a_id,
            body_b_id=body_b_id,
            anchor=(joint.anchor.x, joint.anchor.y, joint.anchor.z),
            axis=(joint.axis.x, joint.axis.y, joint.axis.z),
            limit_low=joint.limit_low,
            limit_high=joint.limit_high,
            stiffness=joint.stiffness,
            damping=joint.damping,
        )
        if joint_id >= 0:
            self._entity_to_joint[entity.id] = joint_id
            self._joint_to_entity[joint_id] = entity.id

    def create_drag_constraint(self, body_id: int, hit_world, max_force: float = 500) -> Optional[int]:
        try:
            if int(body_id) < 0:
                return None
        except Exception:
            return None
        constraint_id = self._solver.create_joint(
            joint_type="point2point",
            body_a_id=body_id,
            body_b_id=-1,
            anchor=(hit_world.x, hit_world.y, hit_world.z),
        )
        if constraint_id >= 0:
            self._solver.change_constraint(constraint_id, (hit_world.x, hit_world.y, hit_world.z), max_force)
        return constraint_id if constraint_id >= 0 else None

    def update_drag_constraint(self, constraint_id: int, world_pos):
        self._solver.change_constraint(constraint_id, (world_pos.x, world_pos.y, world_pos.z))

    def remove_drag_constraint(self, constraint_id: int):
        self._solver.remove_joint(constraint_id)

    def create_fixed_constraint(self, body_a_id: int, body_b_id: int, anchor=(0.0, 0.0, 0.0)) -> Optional[int]:
        try:
            jid = self._solver.create_joint(joint_type="fixed", body_a_id=int(body_a_id), body_b_id=int(body_b_id), anchor=tuple(anchor))
        except Exception:
            return None
        return jid if jid >= 0 else None

    def create_hinge_constraint(self, body_a_id: int, body_b_id: int, anchor=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), limit_low=-3.14159, limit_high=3.14159) -> Optional[int]:
        try:
            jid = self._solver.create_joint(joint_type="hinge", body_a_id=int(body_a_id), body_b_id=int(body_b_id), anchor=tuple(anchor), axis=tuple(axis), limit_low=float(limit_low), limit_high=float(limit_high))
        except Exception:
            return None
        return jid if jid >= 0 else None

    def remove_joint_constraint(self, joint_id: int):
        try:
            self._solver.remove_joint(int(joint_id))
        except Exception:
            pass
        self._joint_to_entity.pop(int(joint_id), None)
        for eid, jid in list(self._entity_to_joint.items()):
            if int(jid) == int(joint_id):
                self._entity_to_joint.pop(eid, None)
                break
