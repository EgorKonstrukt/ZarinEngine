# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun


from __future__ import annotations
import numpy as np
from core.foundation.logger import Logger
from physics_solvers.physx_solver.solverp.scenes import _sanitize_name, _euler_to_quat, _quat_to_euler, _rotate_vector_by_quat


class BodiesMixin:

    def create_rigid_body(
        self,
        entity_id: str,
        shape_type: str,
        shape_params: dict,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float],
        mass: float,
        friction: float = 0.6,
        restitution: float = 0.0,
        is_trigger: bool = False,
        is_kinematic: bool = False,
        collision_layer: int = 0,
        collision_mask: int = 0xFFFF,
    ) -> int:
        body_id = self._next_body_id
        self._next_body_id += 1
        prim_name = _sanitize_name(entity_id) + f"_{body_id}" if entity_id else f"body_{body_id}"
        self._body_id_to_prim[body_id] = f"/World/{prim_name}"
        spec = {
            "body_id": body_id,
            "entity_id": entity_id,
            "shape_type": shape_type,
            "shape_params": dict(shape_params),
            "position": position,
            "rotation": rotation,
            "mass": mass,
            "friction": friction,
            "restitution": restitution,
            "is_trigger": is_trigger,
            "is_kinematic": is_kinematic,
        }
        self._body_specs[body_id] = spec
        self._all_body_ids.append(body_id)
        self._body_count += 1
        if entity_id:
            self._entity_id_to_body_id[entity_id] = body_id
        self._body_id_to_entity_id[body_id] = entity_id
        self._bodies_dirty = True
        return body_id


    def remove_rigid_body(self, body_id: int):
        self._remove_joints_for_body(body_id)
        spec = self._body_specs.pop(body_id, None)
        if spec:
            eid = spec.get("entity_id", "")
            self._entity_id_to_body_id.pop(eid, None)
            self._body_id_to_entity_id.pop(body_id, None)
        self._body_id_to_prim.pop(body_id, None)
        if body_id in self._all_body_ids:
            self._all_body_ids.remove(body_id)
        self._body_count = max(0, self._body_count - 1)
        self._bodies_dirty = True


    def remove_all_bodies(self):
        self._body_specs.clear()
        self._body_id_to_prim.clear()
        self._entity_id_to_body_id.clear()
        self._body_id_to_entity_id.clear()
        self._all_body_ids.clear()
        self._body_count = 0
        self.remove_all_joints()
        self._bodies_dirty = True


    def set_body_transform(
        self,
        body_id: int,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float],
    ):
        spec = self._body_specs.get(body_id)
        if not spec:
            return
        if self._is_dynamic(body_id) and self._pose_tb is not None:
            idx = self._get_body_idx(body_id)
            if idx is not None and self._pose_buf is not None:
                qw, qx, qy, qz = _euler_to_quat(rotation)
                self._pose_buf[idx, 0] = position[0]
                self._pose_buf[idx, 1] = position[1]
                self._pose_buf[idx, 2] = position[2]
                self._pose_buf[idx, 3] = qx
                self._pose_buf[idx, 4] = qy
                self._pose_buf[idx, 5] = qz
                self._pose_buf[idx, 6] = qw
                self._pose_tb.write(self._pose_buf)
        spec["position"] = position
        spec["rotation"] = rotation


    def set_body_transform_quat(
        self,
        body_id: int,
        position: tuple[float, float, float],
        quat: tuple[float, float, float, float],
    ):
        spec = self._body_specs.get(body_id)
        if not spec:
            return
        if self._is_dynamic(body_id) and self._pose_tb is not None:
            idx = self._get_body_idx(body_id)
            if idx is not None and self._pose_buf is not None:
                qx, qy, qz, qw = quat
                self._pose_buf[idx, 0] = position[0]
                self._pose_buf[idx, 1] = position[1]
                self._pose_buf[idx, 2] = position[2]
                self._pose_buf[idx, 3] = qx
                self._pose_buf[idx, 4] = qy
                self._pose_buf[idx, 5] = qz
                self._pose_buf[idx, 6] = qw
                self._pose_tb.write(self._pose_buf)
        spec["position"] = position
        import math
        qx, qy, qz, qw = quat
        sinr_cosp = 2 * (qw * qx + qy * qz)
        cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        sinp = 2 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)
        else:
            pitch = math.asin(max(-1.0, min(1.0, sinp)))
        siny_cosp = 2 * (qw * qz + qx * qy)
        cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        spec["rotation"] = (roll, pitch, yaw)


    def get_body_transform(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        if self._is_dynamic(body_id) and self._pose_tb is not None:
            idx = self._get_body_idx(body_id)
            if idx is not None:
                try:
                    if self._pose_buf is None:
                        self._pose_buf = np.zeros(self._pose_tb.shape, dtype=np.float32)
                    self._pose_tb.read(self._pose_buf)
                    if idx < len(self._pose_buf):
                        p = self._pose_buf[idx]
                        pos = (float(p[0]), float(p[1]), float(p[2]))
                        euler = _quat_to_euler((float(p[3]), float(p[4]), float(p[5]), float(p[6])))
                        return pos, euler
                except Exception:
                    pass
        spec = self._body_specs.get(body_id)
        if spec:
            return spec["position"], spec["rotation"]
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)


    def get_body_transform_quat(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        if self._is_dynamic(body_id) and self._pose_tb is not None:
            idx = self._get_body_idx(body_id)
            if idx is not None:
                try:
                    if self._pose_buf is None:
                        self._pose_buf = np.zeros(self._pose_tb.shape, dtype=np.float32)
                    self._pose_tb.read(self._pose_buf)
                    if idx < len(self._pose_buf):
                        p = self._pose_buf[idx]
                        pos = (float(p[0]), float(p[1]), float(p[2]))
                        quat = (float(p[3]), float(p[4]), float(p[5]), float(p[6]))
                        return pos, quat
                except Exception:
                    pass
        spec = self._body_specs.get(body_id)
        if spec:
            import math
            rx, ry, rz = spec["rotation"]
            hx, hy, hz = rx * 0.5, ry * 0.5, rz * 0.5
            sx, cx = math.sin(hx), math.cos(hx)
            sy, cy = math.sin(hy), math.cos(hy)
            sz, cz = math.sin(hz), math.cos(hz)
            qx = sx * cy * cz - cx * sy * sz
            qy = cx * sy * cz + sx * cy * sz
            qz = cx * cy * sz - sx * sy * cz
            qw = cx * cy * cz + sx * sy * sz
            return spec["position"], (qx, qy, qz, qw)
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)


    def apply_force(self, body_id: int, force: tuple[float, float, float], local: bool = False):
        if not self._is_dynamic(body_id):
            return
        if local:
            spec = self._body_specs.get(body_id)
            if spec:
                euler = spec["rotation"]
                qw, qx, qy, qz = _euler_to_quat(euler)
                v = _rotate_vector_by_quat(force, (qw, qx, qy, qz))
                force = v
        if body_id not in self._pending_wrench:
            self._pending_wrench[body_id] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        w = self._pending_wrench[body_id]
        w[0] += force[0]
        w[1] += force[1]
        w[2] += force[2]


    def apply_torque(self, body_id: int, torque: tuple[float, float, float]):
        if not self._is_dynamic(body_id):
            return
        if body_id not in self._pending_wrench:
            self._pending_wrench[body_id] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        w = self._pending_wrench[body_id]
        w[3] += torque[0]
        w[4] += torque[1]
        w[5] += torque[2]


    def apply_impulse(self, body_id: int, impulse: tuple[float, float, float], local: bool = False):
        if not self._is_dynamic(body_id):
            return
        spec = self._body_specs.get(body_id)
        mass = spec.get("mass", 1.0) if spec else 1.0
        if mass <= 0:
            return
        dv = (impulse[0] / mass, impulse[1] / mass, impulse[2] / mass)
        if local:
            if spec:
                euler = spec["rotation"]
                qw, qx, qy, qz = _euler_to_quat(euler)
                dv = _rotate_vector_by_quat(dv, (qw, qx, qy, qz))
        if body_id in self._pending_vel:
            v = self._pending_vel[body_id]
            self._pending_vel[body_id] = (v[0] + dv[0], v[1] + dv[1], v[2] + dv[2])
        else:
            idx = self._get_body_idx(body_id)
            if idx is not None and self._vel_tb is not None:
                if self._vel_buf is None:
                    self._vel_buf = np.zeros(self._vel_tb.shape, dtype=np.float32)
                self._vel_tb.read(self._vel_buf)
                if idx < len(self._vel_buf):
                    cv = self._vel_buf[idx]
                    self._pending_vel[body_id] = (
                        float(cv[0]) + dv[0],
                        float(cv[1]) + dv[1],
                        float(cv[2]) + dv[2],
                    )
            else:
                self._pending_vel[body_id] = dv


    def set_velocity(self, body_id: int, velocity: tuple[float, float, float]):
        if self._is_dynamic(body_id):
            self._pending_vel[body_id] = velocity


    def get_velocity(self, body_id: int) -> tuple[float, float, float]:
        if not self._is_dynamic(body_id):
            return (0.0, 0.0, 0.0)
        idx = self._get_body_idx(body_id)
        if idx is None or self._vel_tb is None:
            return (0.0, 0.0, 0.0)
        try:
            if self._vel_buf is None:
                self._vel_buf = np.zeros(self._vel_tb.shape, dtype=np.float32)
            self._vel_tb.read(self._vel_buf)
            if idx < len(self._vel_buf):
                v = self._vel_buf[idx]
                return (float(v[0]), float(v[1]), float(v[2]))
        except Exception:
            pass
        return (0.0, 0.0, 0.0)


    def set_angular_velocity(self, body_id: int, velocity: tuple[float, float, float]):
        if self._is_dynamic(body_id):
            self._pending_ang_vel[body_id] = velocity


    def get_angular_velocity(self, body_id: int) -> tuple[float, float, float]:
        if not self._is_dynamic(body_id):
            return (0.0, 0.0, 0.0)
        idx = self._get_body_idx(body_id)
        if idx is None or self._vel_tb is None:
            return (0.0, 0.0, 0.0)
        try:
            if self._vel_buf is None:
                self._vel_buf = np.zeros(self._vel_tb.shape, dtype=np.float32)
            self._vel_tb.read(self._vel_buf)
            if idx < len(self._vel_buf):
                v = self._vel_buf[idx]
                return (float(v[3]), float(v[4]), float(v[5]))
        except Exception:
            pass
        return (0.0, 0.0, 0.0)


    def add_plane(
        self,
        normal: tuple[float, float, float] = (0, 1, 0),
        distance: float = 0.0,
        friction: float = 0.6,
        restitution: float = 0.0,
    ) -> int:
        body_id = self._next_body_id
        self._next_body_id += 1
        prim_name = f"ground_{body_id}"
        self._body_id_to_prim[body_id] = f"/World/{prim_name}"
        spec = {
            "body_id": body_id,
            "entity_id": "",
            "shape_type": "plane",
            "shape_params": {"normal": list(normal)},
            "position": (0, -distance, 0),
            "rotation": (0, 0, 0),
            "mass": 0.0,
            "friction": friction,
            "restitution": restitution,
            "is_trigger": False,
            "is_kinematic": False,
        }
        self._body_specs[body_id] = spec
        self._all_body_ids.append(body_id)
        self._body_count += 1
        self._bodies_dirty = True
        return body_id


    def _remove_joints_for_body(self, body_id: int):
        to_remove = [
            jid for jid, js in self._joint_specs.items()
            if js["body_a_id"] == body_id or js.get("body_b_id") == body_id
        ]
        for jid in to_remove:
            self._joint_specs.pop(jid, None)
            self._joint_id_to_prim.pop(jid, None)
            self._joint_count = max(0, self._joint_count - 1)


    def create_joint(
        self,
        joint_type: str,
        body_a_id: int,
        body_b_id: int,
        anchor: tuple[float, float, float],
        axis: tuple[float, float, float] = (0, 0, 1),
        limit_low: float = -3.14159,
        limit_high: float = 3.14159,
        stiffness: float = 10.0,
        damping: float = 1.0,
    ) -> int:
        if self._ov_physx is None:
            return -1
        prim_a = self._body_id_to_prim.get(body_a_id)
        if prim_a is None:
            Logger.warning(f"PhysXSolver: body_a {body_a_id} not found for joint")
            return -1
        prim_b = self._body_id_to_prim.get(body_b_id) if body_b_id >= 0 else None
        joint_id = self._next_joint_id
        self._next_joint_id += 1
        jprim = f"joint_{joint_id}"

        spec_a = self._body_specs.get(body_a_id)
        pos_a = spec_a["position"] if spec_a else (0.0, 0.0, 0.0)
        local0 = (anchor[0] - pos_a[0], anchor[1] - pos_a[1], anchor[2] - pos_a[2])

        if prim_b and body_b_id in self._body_specs:
            pos_b = self._body_specs[body_b_id]["position"]
            local1 = (anchor[0] - pos_b[0], anchor[1] - pos_b[1], anchor[2] - pos_b[2])
        else:
            local1 = anchor

        spec = {
            "joint_id": joint_id,
            "joint_type": joint_type,
            "prim_name": jprim,
            "body_a_id": body_a_id,
            "body_b_id": body_b_id if body_b_id >= 0 else None,
            "body0_path": prim_a,
            "body1_path": prim_b if prim_b else None,
            "anchor": local0,
            "local1": local1,
            "axis": axis,
            "limit_low": limit_low,
            "limit_high": limit_high,
            "stiffness": stiffness,
            "damping": damping,
            "max_force": 0.0,
        }
        self._joint_specs[joint_id] = spec
        self._joint_id_to_prim[joint_id] = f"/World/{jprim}"
        self._joint_count += 1
        self._bodies_dirty = True
        Logger.info(f"PhysXSolver: created joint {joint_id} ({joint_type}) between {body_a_id} and {body_b_id}")
        return joint_id


    def remove_joint(self, joint_id: int):
        spec = self._joint_specs.pop(joint_id, None)
        if spec:
            self._joint_id_to_prim.pop(joint_id, None)
            self._joint_count = max(0, self._joint_count - 1)
            self._bodies_dirty = True
            Logger.info(f"PhysXSolver: removed joint {joint_id}")


    def remove_all_joints(self):
        if self._joint_specs:
            self._joint_specs.clear()
            self._joint_id_to_prim.clear()
            self._joint_count = 0
            self._bodies_dirty = True
            Logger.info("PhysXSolver: removed all joints")


    def change_constraint(
        self,
        constraint_id: int,
        pivot: tuple[float, float, float],
        max_force: float = 500,
    ):
        spec = self._joint_specs.get(constraint_id)
        if spec is None:
            Logger.warning(f"PhysXSolver: constraint {constraint_id} not found")
            return
        spec["anchor"] = pivot
        spec["max_force"] = max_force
        self._bodies_dirty = True
