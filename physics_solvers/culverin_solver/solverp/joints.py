# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
import numpy as np
from core.foundation.logger import Logger
from physics_solvers.culverin_solver.solverp.broadphase import CONSTRAINT_FIXED, CONSTRAINT_POINT, CONSTRAINT_HINGE, CONSTRAINT_SLIDER, CONSTRAINT_DISTANCE, CONSTRAINT_CONE, _JOINT_TYPE_MAP
from physics_solvers.culverin_solver.solverp.integrate import _soft_vertex_precision

class JointsMixin:

    def get_soft_body_geometry(self, soft_id: int):
        try:
            spec = self._soft_specs.get(soft_id)
            if not spec:
                return None
            return spec.get("verts"), spec.get("faces")
        except Exception:
            return None

    def remove_soft_body(self, soft_id: int):
        handle = self._soft_id_to_handle.pop(soft_id, None)
        if handle is not None:
            if handle in self._soft_handles:
                self._soft_handles.remove(handle)
            self._soft_handle_to_id.pop(handle, None)
            if self._world is not None:
                try:
                    self._world.destroy_body(handle)
                except Exception:
                    pass
        self._soft_specs.pop(soft_id, None)
        entity_id = self._soft_to_entity.pop(soft_id, None)
        if entity_id and self._entity_to_soft.get(entity_id) == soft_id:
            self._entity_to_soft.pop(entity_id, None)

    def remove_all_soft_bodies(self):
        if self._world is not None:
            for handle in list(self._soft_handles):
                try:
                    self._world.destroy_body(handle)
                except Exception:
                    pass
        self._next_soft_id = -1
        self._soft_handles.clear()
        self._soft_handle_to_id.clear()
        self._soft_id_to_handle.clear()
        self._soft_to_entity.clear()
        self._entity_to_soft.clear()
        self._soft_specs.clear()

    def get_soft_body_count(self, soft_id: int) -> int:
        try:
            return int(self._soft_specs.get(soft_id, {}).get("count", 0))
        except Exception:
            return 0

    def get_soft_body_world_vertices(self, soft_id: int):
        handle = self._resolve_soft_id(soft_id)
        if handle is None or self._world is None:
            return None
        try:
            view = self._world.get_soft_body_vertices(handle)
        except Exception:
            return None
        if view is None:
            return None
        try:
            is_double, _ = _soft_vertex_precision()
            raw = np.frombuffer(view, dtype=np.float64 if is_double else np.float32)
        except Exception:
            return None
        if raw.size < 4 or raw.size % 4 != 0:
            return None
        try:
            out = np.ascontiguousarray(raw.reshape(-1, 4)[:, :3].astype(np.float32))
        except Exception:
            return None
        try:
            want = int(self._soft_specs.get(soft_id, {}).get("count", 0))
        except Exception:
            want = 0
        if want > 0 and len(out) != want:
            return None
        return out

    def get_soft_body_com(
        self, soft_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        handle = self._resolve_soft_id(soft_id)
        if handle is None or self._world is None:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        try:
            pos = self._world.get_position(handle)
            rot = self._world.get_rotation(handle)
        except Exception:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        if pos is None or rot is None:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        return ((pos[0], pos[1], pos[2]), (rot[0], rot[1], rot[2], rot[3]))

    def apply_soft_body_force(self, soft_id: int, force: tuple[float, float, float]):
        handle = self._resolve_soft_id(soft_id)
        if handle is None or self._world is None:
            return
        try:
            self._world.apply_force(handle, float(force[0]), float(force[1]), float(force[2]))
        except Exception:
            pass

    def set_soft_body_velocity(self, soft_id: int, velocity: tuple[float, float, float]):
        handle = self._resolve_soft_id(soft_id)
        if handle is None or self._world is None:
            return
        try:
            self._world.set_linear_velocity(handle, float(velocity[0]), float(velocity[1]), float(velocity[2]))
        except Exception:
            pass

    def get_soft_body_velocity(self, soft_id: int) -> tuple[float, float, float]:
        handle = self._resolve_soft_id(soft_id)
        if handle is None or self._world is None:
            return (0.0, 0.0, 0.0)
        try:
            v = self._world.get_velocity(handle)
        except Exception:
            return (0.0, 0.0, 0.0)
        if v is None:
            return (0.0, 0.0, 0.0)
        return (v[0], v[1], v[2])

    def get_soft_body_sample(self, soft_id: int):
        try:
            sid = int(soft_id)
        except Exception:
            return None
        spec = self._soft_specs.get(sid)
        if not spec:
            return None
        verts = self.get_soft_body_world_vertices(sid)
        if verts is None or len(verts) == 0:
            return None
        try:
            v = np.asarray(verts, dtype=np.float64)
            center = v.mean(axis=0)
            bmin = v.min(axis=0)
            bmax = v.max(axis=0)
        except Exception:
            return None
        try:
            base_r = float(spec.get("radius", 0.05))
        except Exception:
            base_r = 0.05
        if not np.isfinite(base_r) or base_r <= 0.0:
            base_r = 0.05
        vel = self.get_soft_body_velocity(sid)
        try:
            pinned = spec.get("pinned", None)
            is_pinned = bool(pinned) and len(pinned) > 0
        except Exception:
            is_pinned = False
        try:
            mass = max(float(spec.get("mass", 1.0)), 1e-6)
        except Exception:
            mass = 1.0
        return {
            "center": (float(center[0]), float(center[1]), float(center[2])),
            "aabb_min": (float(bmin[0]) - base_r, float(bmin[1]) - base_r, float(bmin[2]) - base_r),
            "aabb_max": (float(bmax[0]) + base_r, float(bmax[1]) + base_r, float(bmax[2]) + base_r),
            "radius": float(base_r),
            "velocity": (float(vel[0]), float(vel[1]), float(vel[2])),
            "pinned": is_pinned,
            "mass": float(mass),
        }

    def get_soft_body_radius(self, soft_id: int) -> float:
        try:
            spec = self._soft_specs.get(int(soft_id))
            if not spec:
                return 0.0
            r = float(spec.get("radius", 0.0))
            return r if r > 0.0 else 0.0
        except Exception:
            return 0.0

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
        if self._world is None:
            return -1

        handle_a = self._id_to_handle.get(body_a_id)
        if handle_a is None:
            return -1

        handle_b = self._id_to_handle.get(body_b_id) if body_b_id >= 0 else -1
        if handle_b is None:
            return -1

        ctype = _JOINT_TYPE_MAP.get(joint_type, CONSTRAINT_FIXED)

        if handle_b < 0:
            Logger.warning("CulverinSolver: world constraints not supported")
            return -1

        params = None
        if ctype == CONSTRAINT_FIXED:
            params = None
        elif ctype == CONSTRAINT_POINT:
            params = anchor
        elif ctype in (CONSTRAINT_HINGE, CONSTRAINT_SLIDER):
            params = (anchor, axis, limit_low, limit_high)
        elif ctype == CONSTRAINT_DISTANCE:
            params = (limit_low, limit_high)
        elif ctype == CONSTRAINT_CONE:
            params = (anchor, axis, limit_high)

        motor = None
        if joint_type == "spring" and stiffness > 0:
            motor = {"type": 0, "target": stiffness}

        c_handle = self._world.create_constraint(
            ctype, handle_a, handle_b, params=params, motor=motor,
        )
        if c_handle is None or c_handle < 0:
            return -1

        joint_id = self._next_joint_id
        self._next_joint_id += 1
        self._joint_id_to_handle[joint_id] = c_handle
        self._joint_handle_to_id[c_handle] = joint_id
        self._joint_specs[joint_id] = {
            "type": ctype,
            "body_a": handle_a,
            "body_b": handle_b,
            "params": params,
            "motor": motor,
        }

        return joint_id

    def remove_joint(self, joint_id: int):
        c_handle = self._joint_id_to_handle.pop(joint_id, None)
        if c_handle is not None and self._world is not None:
            self._world.destroy_constraint(c_handle)
            self._joint_handle_to_id.pop(c_handle, None)
        self._joint_specs.pop(joint_id, None)

    def remove_all_joints(self):
        if self._world is not None:
            for c_handle in list(self._joint_handle_to_id.keys()):
                self._world.destroy_constraint(c_handle)
        self._joint_id_to_handle.clear()
        self._joint_handle_to_id.clear()
        self._joint_specs.clear()

    def change_constraint(
        self,
        constraint_id: int,
        pivot: tuple[float, float, float],
        max_force: float = 500,
    ):
        spec = self._joint_specs.get(constraint_id)
        if spec is None or self._world is None:
            return
        old_handle = self._joint_id_to_handle.get(constraint_id)
        if old_handle is None:
            return
        self._world.destroy_constraint(old_handle)
        self._joint_handle_to_id.pop(old_handle, None)

        new_params = spec["params"]
        if spec["type"] == CONSTRAINT_POINT:
            new_params = pivot
        elif spec["type"] in (CONSTRAINT_HINGE, CONSTRAINT_SLIDER):
            new_params = (pivot, spec["params"][1], spec["params"][2], spec["params"][3])

        new_handle = self._world.create_constraint(
            spec["type"],
            spec["body_a"],
            spec["body_b"],
            params=new_params,
            motor=spec["motor"],
        )
        if new_handle is not None and new_handle >= 0:
            self._joint_id_to_handle[constraint_id] = new_handle
            self._joint_handle_to_id[new_handle] = constraint_id
            spec["params"] = new_params

    def set_motor_target(self, constraint_id: int, target: float):
        if self._world is None:
            return
        c_handle = self._joint_id_to_handle.get(constraint_id)
        if c_handle is None:
            return
        try:
            self._world.set_constraint_target(c_handle, float(target))
        except Exception as e:
            Logger.debug(f"CulverinSolver.set_motor_target({constraint_id}) failed: {e}")

    def enable_constraint(self, constraint_id: int, motor: Optional[dict]) -> bool:
        if self._world is None:
            return False
        spec = self._joint_specs.get(constraint_id)
        if spec is None:
            return False
        old = self._joint_id_to_handle.get(constraint_id)
        if old is None:
            return False
        self._world.destroy_constraint(old)
        self._joint_handle_to_id.pop(old, None)
        spec["motor"] = motor
        new_handle = self._world.create_constraint(
            spec["type"], spec["body_a"], spec["body_b"],
            params=spec["params"], motor=motor,
        )
        if new_handle is None or new_handle < 0:
            return False
        self._joint_id_to_handle[constraint_id] = new_handle
        self._joint_handle_to_id[new_handle] = constraint_id
        return True

    def create_character(
        self,
        pos: tuple[float, float, float],
        height: float = 1.8,
        radius: float = 0.4,
        step_height: float = 0.4,
        max_slope: float = 45.0,
    ):
        if self._world is None:
            return None
        try:
            return self._world.create_character(
                pos,
                height=height,
                radius=radius,
                step_height=step_height,
                max_slope=max_slope,
            )
        except Exception as e:
            Logger.error(f"CulverinSolver.create_character failed: {e}")
            return None

    def move_character(self, character, velocity: tuple[float, float, float], dt: float):
        if character is None:
            return
        try:
            character.move(velocity, dt)
        except Exception as e:
            Logger.error(f"CulverinSolver.move_character failed: {e}")

    def set_character_rotation(self, character, rot: tuple[float, float, float, float]):
        if character is None:
            return
        try:
            character.set_rotation(rot)
        except Exception:
            pass

    def get_character_position(self, character):
        if character is None:
            return None
        try:
            return character.get_position()
        except Exception:
            return None

    def is_character_grounded(self, character) -> bool:
        if character is None:
            return False
        try:
            return bool(character.is_grounded())
        except Exception:
            return False

    def set_character_strength(self, character, strength: float):
        if character is None:
            return
        try:
            character.set_strength(strength)
        except Exception:
            pass

    def destroy_character(self, character):
        if character is None or self._world is None:
            return
        try:
            self._world.destroy_body(character.handle)
        except Exception:
            pass
