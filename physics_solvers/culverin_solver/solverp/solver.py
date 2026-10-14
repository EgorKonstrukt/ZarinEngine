# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
import numpy as np
from core.foundation.logger import Logger
from core.physics.physics_solver import IPhysicsSolver
from physics_solvers.culverin_solver.solverp.broadphase import PhysicsWorld, _HAS_CULVERIN, SHAPE_PLANE, MOTION_STATIC, euler_to_quat, _layer_category, _mask_value
from physics_solvers.culverin_solver.solverp.integrate import _quat_to_euler, _rotate_vector_by_quat, _rot_vec_by_quat_xyzw, _shifted_pos
from physics_solvers.culverin_solver.solverp.bodies import BodiesMixin
from physics_solvers.culverin_solver.solverp.broadphase import BroadphaseMixin
from physics_solvers.culverin_solver.solverp.integrate import IntegrateMixin
from physics_solvers.culverin_solver.solverp.joints import JointsMixin

class CulverinSolver(BodiesMixin, BroadphaseMixin, IntegrateMixin, JointsMixin, IPhysicsSolver):

    def __init__(self):
        self._world: Optional[PhysicsWorld] = None
        self._initialized = False
        self._body_count = 0
        self._next_body_id = 1
        self._all_body_ids: list[int] = []
        self._body_handles: list[int] = []
        self._handle_to_id: dict[int, int] = {}
        self._id_to_handle: dict[int, int] = {}
        self._entity_to_body: dict[str, int] = {}
        self._body_to_entity: dict[int, str] = {}
        self._body_specs: dict[int, dict] = {}
        self._next_soft_id = -1
        self._soft_handles: list[int] = []
        self._soft_handle_to_id: dict[int, int] = {}
        self._soft_id_to_handle: dict[int, int] = {}
        self._soft_to_entity: dict[int, str] = {}
        self._entity_to_soft: dict[str, int] = {}
        self._soft_specs: dict[int, dict] = {}
        self._gravity: tuple[float, float, float] = (0.0, -9.81, 0.0)
        self._debug_enabled = False
        self._next_joint_id = 1
        self._joint_id_to_handle: dict[int, int] = {}
        self._joint_handle_to_id: dict[int, int] = {}
        self._joint_specs: dict[int, dict] = {}
        self._num_threads = 0
        self._max_physics_jobs = 8
        self._max_physics_barriers = 8
        self._enable_ccd = False
        self._enable_sleeping = True

    def initialize(self, settings: Optional[dict] = None) -> bool:
        if self._initialized:
            return True
        if not _HAS_CULVERIN or PhysicsWorld is None:
            Logger.error("CulverinSolver: culverin not installed. Run: pip install culverin")
            return False
        try:
            opts = settings or {}
            world_opts: dict = {}

            gx = opts.get("gravity_x", 0.0)
            gy = opts.get("gravity_y", -9.81)
            gz = opts.get("gravity_z", 0.0)
            self._gravity = (gx, gy, gz)
            world_opts["gravity"] = (gx, gy, gz)

            self._num_threads = opts.get("culverin_num_threads", 0)
            self._max_physics_jobs = opts.get("culverin_max_physics_jobs", 0)
            self._max_physics_barriers = opts.get("culverin_max_physics_barriers", 0)
            self._enable_ccd = opts.get("culverin_enable_ccd", False)
            self._enable_sleeping = opts.get("culverin_enable_sleeping", True)

            if self._num_threads == 0:
                self._max_physics_jobs = 0
                self._max_physics_barriers = 0

            world_opts["num_threads"] = self._num_threads
            world_opts["max_physics_jobs"] = self._max_physics_jobs
            world_opts["max_physics_barriers"] = self._max_physics_barriers
            world_opts["penetration_slop"] = opts.get("culverin_penetration_slop", 0.02)
            world_opts["max_bodies"] = opts.get("culverin_max_bodies", 65536)
            world_opts["max_pairs"] = opts.get("culverin_max_pairs", 65536)
            world_opts["max_contact_constraints"] = opts.get("culverin_max_contact_constraints", 65536)
            world_opts["temp_allocator_size"] = opts.get("culverin_temp_allocator_size", 16777216)

            self._world = PhysicsWorld(settings=world_opts)
            self._world.set_gravity(gx, gy, gz)
            self._initialized = True
            Logger.info(f"CulverinSolver initialized (threads={self._num_threads}, jobs={self._max_physics_jobs}, ccd={self._enable_ccd}, sleep={self._enable_sleeping})")
            return True
        except Exception as e:
            Logger.error(f"CulverinSolver init failed: {e}")
            return False

    def shutdown(self):
        self._world = None
        self._initialized = False
        self._body_count = 0
        self._next_body_id = 1
        self._all_body_ids.clear()
        self._body_handles.clear()
        self._handle_to_id.clear()
        self._id_to_handle.clear()
        self._entity_to_body.clear()
        self._body_to_entity.clear()
        self._body_specs.clear()
        self._next_soft_id = -1
        self._soft_handles.clear()
        self._soft_handle_to_id.clear()
        self._soft_id_to_handle.clear()
        self._soft_to_entity.clear()
        self._entity_to_soft.clear()
        self._soft_specs.clear()
        self._next_joint_id = 1
        self._joint_id_to_handle.clear()
        self._joint_handle_to_id.clear()
        self._joint_specs.clear()
        Logger.info("CulverinSolver shutdown.")

    @property
    def body_count(self) -> int:
        return self._body_count

    @property
    def debug_draw(self):
        return self._debug_enabled

    @debug_draw.setter
    def debug_draw(self, enabled: bool):
        self._debug_enabled = enabled

    def step_simulation(self, dt: float):
        if self._world is not None:
            self._world.step(dt)

    def set_gravity(self, gravity: tuple[float, float, float]):
        self._gravity = gravity
        if self._world is not None:
            self._world.set_gravity(gravity[0], gravity[1], gravity[2])

    def _body_com(self, body_id: int) -> Optional[tuple[float, float, float]]:
        try:
            spec = self._body_specs.get(body_id)
            if spec is None:
                return None
            return spec.get("com")
        except Exception:
            return None

    def _resolve_any_id(self, handle: int) -> int:
        try:
            bid = self._handle_to_id.get(handle)
            if bid is not None:
                return bid
            return self._soft_handle_to_id.get(handle, -1)
        except Exception:
            return -1

    def ray_cast(
        self,
        origin: tuple[float, float, float],
        direction: tuple[float, float, float],
        max_distance: float = 100.0,
    ) -> Optional[dict]:
        if self._world is None:
            return None
        dx, dy, dz = direction
        mag = (dx * dx + dy * dy + dz * dz) ** 0.5
        if mag < 1e-10:
            return None
        result = self._world.raycast(origin, direction, max_distance)
        if result is None:
            return None
        handle, fraction, position = result[0], result[1], result[2]
        body_id = self._resolve_any_id(handle)
        return {
            "body_id": body_id,
            "position": position,
            "normal": (0.0, 0.0, 0.0),
            "fraction": fraction,
        }

    def get_collision_events(self) -> list[dict]:
        if self._world is None:
            return []
        raw = self._world.get_contact_events()
        out = []
        for ev in raw:
            ba = self._resolve_any_id(ev[0])
            bb = self._resolve_any_id(ev[1])
            if ba == -1 or bb == -1:
                continue
            out.append({"body_a": ba, "body_b": bb})
        return out

    def add_plane(
        self,
        normal: tuple[float, float, float] = (0, 1, 0),
        distance: float = 0.0,
        friction: float = 0.6,
        restitution: float = 0.0,
    ) -> int:
        if self._world is None:
            return -1
        body_id = self._next_body_id
        self._next_body_id += 1

        handle = self._world.create_body(
            pos=(0.0, -distance, 0.0),
            rot=(0.0, 0.0, 0.0, 1.0),
            size=(normal[0], normal[1], normal[2], 0.0),
            shape=SHAPE_PLANE,
            motion=MOTION_STATIC,
            mass=0.0,
            friction=friction,
            restitution=restitution,
            user_data=body_id,
        )
        if handle is None or handle < 0:
            return -1

        self._body_count += 1
        self._all_body_ids.append(body_id)
        self._body_handles.append(handle)
        self._handle_to_id[handle] = body_id
        self._id_to_handle[body_id] = handle
        self._body_specs[body_id] = {
            "entity_id": "",
            "shape_type": "plane",
            "mass": 0.0,
            "friction": friction,
            "restitution": restitution,
            "is_trigger": False,
            "is_kinematic": False,
        }
        return body_id

    def _create_heightfield_collider(
        self, position, rot_q, mass_val, motion, shape_params,
        friction, restitution, is_trigger, collision_layer, collision_mask, body_id,
    ) -> int:
        hd = shape_params.get("height_data")
        size = shape_params.get("size", [1000.0, 60.0, 1000.0])
        resolution = int(shape_params.get("resolution", 0))
        if hd is None or resolution < 2:
            Logger.warning("CulverinSolver: terrain height field not available")
            return -1
        try:
            arr = np.asarray(hd, dtype=np.float32)
            if arr.ndim == 1:
                side = int(np.sqrt(len(arr)))
                arr = arr.reshape(side, side)
            res = arr.shape[0]
            max_verts = 8000
            step = 1
            if res * res > max_verts:
                step = max(1, int(np.ceil(res / int(np.sqrt(max_verts)))))
            sx = size[0] / max(1, res - 1)
            sz = size[2] / max(1, res - 1)
            verts = []
            indices = []
            for z in range(0, res, step):
                for x in range(0, res, step):
                    px = (x - (res - 1) * 0.5) * sx
                    pz = (z - (res - 1) * 0.5) * sz
                    verts.append(px)
                    verts.append(float(arr[z, x]))
                    verts.append(pz)
            w = (res + step - 1) // step
            for r in range(w - 1):
                for c in range(w - 1):
                    a = r * w + c
                    b = r * w + c + 1
                    d = (r + 1) * w + c
                    e = (r + 1) * w + c + 1
                    indices.append(a)
                    indices.append(d)
                    indices.append(b)
                    indices.append(b)
                    indices.append(d)
                    indices.append(e)
            buf_verts = np.array(verts, dtype=np.float32).tobytes()
            buf_indices = np.array(indices, dtype=np.uint32).tobytes()
            return self._world.create_mesh_body(
                pos=position, rot=rot_q,
                vertices=buf_verts, indices=buf_indices,
                user_data=body_id,
                category=_layer_category(collision_layer), mask=_mask_value(collision_mask),
            )
        except Exception as e:
            Logger.warning(f"CulverinSolver: heightfield body failed: {e}")
            return -1

    def set_body_transform(
        self,
        body_id: int,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float],
    ):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        rot_q = euler_to_quat(rotation[0], rotation[1], rotation[2])
        self._world.set_transform(handle, position, rot_q)

    def set_body_transform_quat(
        self,
        body_id: int,
        position: tuple[float, float, float],
        quat: tuple[float, float, float, float],
    ):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        self._world.set_transform(handle, position, quat)

    def get_body_transform(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        pos, quat = self.get_body_transform_quat(body_id)
        euler = _quat_to_euler((quat[0], quat[1], quat[2], quat[3]))
        return (pos, euler)

    def get_body_transform_quat(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        pos = self._world.get_position(handle)
        rot = self._world.get_rotation(handle)
        if pos is None or rot is None:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        quat = (rot[0], rot[1], rot[2], rot[3])
        pos = _shifted_pos((pos[0], pos[1], pos[2]), quat, self._body_com(body_id), -1.0)
        return (pos, quat)

    def apply_force(
        self, body_id: int, force: tuple[float, float, float], local: bool = False
    ):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        if local:
            rot = self._world.get_rotation(handle)
            if rot is not None:
                force = _rotate_vector_by_quat(force, rot)
        self._world.apply_force(handle, force[0], force[1], force[2])

    def apply_torque(self, body_id: int, torque: tuple[float, float, float]):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        self._world.apply_torque(handle, torque[0], torque[1], torque[2])

    def activate(self, body_id: int):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        try:
            self._world.activate(handle)
        except Exception:
            pass

    def apply_impulse(
        self, body_id: int, impulse: tuple[float, float, float], local: bool = False
    ):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        if local:
            rot = self._world.get_rotation(handle)
            if rot is not None:
                impulse = _rotate_vector_by_quat(impulse, rot)
        self._world.apply_impulse(handle, impulse[0], impulse[1], impulse[2])

    def set_velocity(self, body_id: int, velocity: tuple[float, float, float]):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        self._world.set_linear_velocity(handle, velocity[0], velocity[1], velocity[2])

    def set_velocities(
        self, body_id: int,
        linear: Optional[tuple[float, float, float]] = None,
        angular: Optional[tuple[float, float, float]] = None,
    ):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        if linear is not None:
            self._world.set_linear_velocity(handle, linear[0], linear[1], linear[2])
        if angular is not None:
            self._world.set_angular_velocity(handle, angular[0], angular[1], angular[2])

    def get_velocity(self, body_id: int) -> tuple[float, float, float]:
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return (0.0, 0.0, 0.0)
        v = self._world.get_velocity(handle)
        return v if v is not None else (0.0, 0.0, 0.0)

    def get_velocities(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        v = self._world.get_velocity(handle)
        a = self._world.get_angular_velocity(handle)
        return (
            v if v is not None else (0.0, 0.0, 0.0),
            a if a is not None else (0.0, 0.0, 0.0),
        )

    def set_angular_velocity(
        self, body_id: int, velocity: tuple[float, float, float]
    ):
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return
        self._world.set_angular_velocity(handle, velocity[0], velocity[1], velocity[2])

    def get_angular_velocity(
        self, body_id: int
    ) -> tuple[float, float, float]:
        handle = self._id_to_handle.get(body_id)
        if handle is None or self._world is None:
            return (0.0, 0.0, 0.0)
        av = self._world.get_angular_velocity(handle)
        return av if av is not None else (0.0, 0.0, 0.0)
