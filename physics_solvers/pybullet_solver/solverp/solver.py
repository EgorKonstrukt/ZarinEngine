# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from core.foundation.logger import Logger
from core.physics.physics_solver import IPhysicsSolver
from physics_solvers.pybullet_solver.solverp.bodies import _BodiesMixin
from physics_solvers.pybullet_solver.solverp.lazy import _QueryMixin, p, _pybullet_data_path

class PyBulletSolver(_BodiesMixin, _QueryMixin, IPhysicsSolver):
    def __init__(self):
        self._client: Optional[int] = None
        self._initialized = False
        self._body_count = 0
        self._debug_enabled = False
        self._all_body_ids: list[int] = []
        self._gravity: tuple[float, float, float] = (0.0, -9.81, 0.0)
        self._fixed_time_step = 1.0 / 60.0
        self._num_sub_steps = 1
        self._solver_iterations = 50
        self._erp = 0.4
        self._contact_erp = 0.4
        self._friction_erp = 0.0
        self._contact_breaking_threshold = 0.02
        self._restitution = 0.0
        self._linear_damping = 0.04
        self._angular_damping = 0.04
        self._max_contacts_per_body = 64
        self._enable_sleeping = True
        self._mesh_shape_cache: dict[tuple, int] = {}
        self._body_collision_info: dict[int, tuple[int, int]] = {}

    def initialize(self, settings: Optional[dict] = None) -> bool:
        if self._initialized:
            return True
        try:
            opts = settings or {}
            mode = p.DIRECT if opts.get("headless", True) else p.GUI
            self._client = p.connect(mode)
            if self._client < 0:
                Logger.error("PyBullet failed to connect.")
                return False
            p.setAdditionalSearchPath(_pybullet_data_path())

            gx = opts.get("gravity_x", 0.0)
            gy = opts.get("gravity_y", -9.81)
            gz = opts.get("gravity_z", 0.0)
            self._gravity = (gx, gy, gz)
            p.setGravity(gx, gy, gz, physicsClientId=self._client)
            p.setRealTimeSimulation(0, physicsClientId=self._client)

            self._fixed_time_step = max(0.001, opts.get("fixed_time_step", 1.0 / 60.0))
            self._num_sub_steps = max(1, opts.get("num_sub_steps", 1))
            self._solver_iterations = max(1, opts.get("solver_iterations", 50))
            self._erp = opts.get("erp", 0.4)
            self._contact_erp = opts.get("contact_erp", 0.4)
            self._enable_sleeping = opts.get("enable_sleeping", True)

            for param_key, opt_key, default in [
                ("numSolverIterations", "solver_iterations", 50),
                ("numSubSteps", "num_sub_steps", 1),
                ("erp", "erp", 0.4),
                ("defaultContactERP", "contact_erp", 0.4),
                ("frictionERP", "friction_erp", 0.0),
                ("contactBreakingThreshold", "contact_breaking_threshold", 0.02),
                ("fixedTimeStep", "fixed_time_step", 1.0 / 60.0),
            ]:
                v = opts.get(opt_key, default)
                try:
                    p.setPhysicsEngineParameter(**{param_key: v}, physicsClientId=self._client)
                except Exception:
                    pass

            try:
                p.setPhysicsEngineParameter(
                    enableSleeping=1 if self._enable_sleeping else 0,
                    physicsClientId=self._client,
                )
                p.setPhysicsEngineParameter(
                    enableFileCaching=0,
                    physicsClientId=self._client,
                )
            except Exception:
                pass

            self._initialized = True
            Logger.info(f"PyBulletSolver initialized (client={self._client})")
            return True
        except Exception as e:
            Logger.error(f"PyBulletSolver init failed: {e}", e)
            return False

    def shutdown(self):
        if self._client is not None:
            p.disconnect(physicsClientId=self._client)
            self._client = None
        self._initialized = False
        self._body_count = 0
        Logger.info("PyBulletSolver shutdown.")

    @property
    def body_count(self) -> int:
        return self._body_count

    @property
    def debug_draw(self):
        return self._debug_enabled

    @debug_draw.setter
    def debug_draw(self, enabled: bool):
        self._debug_enabled = enabled
        if self._client is not None:
            if enabled:
                p.configureDebugVisualizer(
                    p.COV_ENABLE_GUI, 1, physicsClientId=self._client
                )
                p.configureDebugVisualizer(
                    p.COV_ENABLE_RENDERING, 1, physicsClientId=self._client
                )
            else:
                p.configureDebugVisualizer(
                    p.COV_ENABLE_GUI, 0, physicsClientId=self._client
                )

    def _cid(self):
        if self._client is None:
            raise RuntimeError("PyBullet solver not initialized")
        return self._client

    def step_simulation(self, dt: float):
        sub_steps = max(1, self._num_sub_steps)
        internal_dt = dt / sub_steps
        p.setPhysicsEngineParameter(
            fixedTimeStep=internal_dt,
            numSubSteps=1,
            physicsClientId=self._cid(),
        )
        for _ in range(sub_steps):
            p.stepSimulation(physicsClientId=self._cid())

    def set_gravity(self, gravity: tuple[float, float, float]):
        self._gravity = gravity
        p.setGravity(*gravity, physicsClientId=self._cid())

    def create_compound_rigid_body(
        self,
        entity_id: str,
        shapes: list,
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
        cid = self._cid()
        if not shapes:
            return -1
        if len(shapes) == 1:
            first = shapes[0]
            return self.create_rigid_body(
                entity_id=entity_id,
                shape_type=first.get("type", "box"),
                shape_params=first.get("params", {}),
                position=position,
                rotation=rotation,
                mass=mass,
                friction=friction,
                restitution=restitution,
                is_trigger=is_trigger,
                is_kinematic=is_kinematic,
                collision_layer=collision_layer,
                collision_mask=collision_mask,
            )
        try:
            if any(bool(s.get("is_trigger", False)) != bool(is_trigger) for s in shapes):
                Logger.warning("MeshCollider compound: mixed trigger/solid colliders share one body, using the first")
        except Exception:
            pass
        is_static = (mass <= 0.0 or is_trigger or is_kinematic)
        try:
            from core.physics.shapep import part_volume
            vols = []
            for s in shapes:
                try:
                    vols.append(max(float(part_volume(s.get("type", "box"), s.get("params", {}))), 1e-9))
                except Exception:
                    vols.append(1.0)
        except Exception:
            vols = [1.0] * len(shapes)
        total_vol = sum(vols) or float(len(shapes))

        base_shape = self._make_shape(shapes[0].get("type", "box"), shapes[0].get("params", {}), is_static=is_static)
        if base_shape < 0:
            return -1
        link_shapes: list[int] = []
        link_masses: list[float] = []
        for s, v in zip(shapes[1:], vols[1:]):
            try:
                sid = self._make_shape(s.get("type", "box"), s.get("params", {}), is_static=is_static)
            except Exception as e:
                Logger.warning(f"Compound link failed, skipping: {e}")
                continue
            if sid < 0:
                Logger.warning("Compound link failed, skipping")
                continue
            link_shapes.append(sid)
            link_masses.append(0.0 if is_static else mass * v / total_vol)
        n_links = len(link_shapes)
        base_mass = 0.0 if (mass <= 0.0 or is_trigger or is_kinematic) else mass * vols[0] / total_vol
        try:
            body_id = p.createMultiBody(
                baseMass=base_mass,
                baseCollisionShapeIndex=base_shape,
                baseVisualShapeIndex=-1,
                basePosition=position,
                baseOrientation=p.getQuaternionFromEuler(rotation),
                linkMasses=link_masses,
                linkCollisionShapeIndices=link_shapes,
                linkVisualShapeIndices=[-1] * n_links,
                linkPositions=[[0.0, 0.0, 0.0]] * n_links,
                linkOrientations=[[0.0, 0.0, 0.0, 1.0]] * n_links,
                linkInertialFramePositions=[[0.0, 0.0, 0.0]] * n_links,
                linkInertialFrameOrientations=[[0.0, 0.0, 0.0, 1.0]] * n_links,
                linkParentIndices=[0] * n_links,
                linkJointTypes=[p.JOINT_FIXED] * n_links,
                linkJointAxis=[[0.0, 0.0, 1.0]] * n_links,
                physicsClientId=cid,
            )
        except Exception as e:
            Logger.warning(f"Compound body failed: {e}")
            return -1
        if body_id is None or body_id < 0:
            return -1
        self._body_count += 1
        self._all_body_ids.append(body_id)
        self._body_collision_info[body_id] = (collision_layer, collision_mask)
        try:
            p.changeDynamics(body_id, -1, lateralFriction=friction, restitution=restitution, activationState=1, physicsClientId=cid)
            for li in range(n_links):
                p.changeDynamics(body_id, li, lateralFriction=friction, restitution=restitution, physicsClientId=cid)
        except Exception:
            pass
        try:
            p.addUserData(body_id, "entity_id", entity_id, physicsClientId=cid)
        except Exception:
            pass
        self._apply_collision_filters(body_id)
        return body_id

    def remove_rigid_body(self, body_id: int):
        try:
            p.removeBody(body_id, physicsClientId=self._cid())
            self._body_count -= 1
            if body_id in self._all_body_ids:
                self._all_body_ids.remove(body_id)
            self._body_collision_info.pop(body_id, None)
        except Exception:
            pass

    def remove_all_bodies(self):
        cid = self._cid()
        for bid in list(self._all_body_ids):
            try:
                p.removeBody(bid, physicsClientId=cid)
            except Exception:
                pass
        self._all_body_ids.clear()
        self._body_collision_info.clear()
        self._body_count = 0
        self._mesh_shape_cache.clear()
        p.setGravity(*self._gravity, physicsClientId=cid)

    def _apply_collision_filters(self, new_body_id: int):
        cid = self._cid()
        if new_body_id not in self._body_collision_info:
            return
        new_layer, new_mask = self._body_collision_info[new_body_id]
        new_group = 1 << new_layer

        for existing_body_id, (existing_layer, existing_mask) in self._body_collision_info.items():
            if existing_body_id == new_body_id:
                continue
            existing_group = 1 << existing_layer
            should_collide = (new_group & existing_mask) != 0 and (existing_group & new_mask) != 0
            if not should_collide:
                p.setCollisionFilterPair(new_body_id, existing_body_id, -1, -1, 0, physicsClientId=cid)

    def add_plane(
        self,
        normal: tuple[float, float, float] = (0, 1, 0),
        distance: float = 0.0,
        friction: float = 0.6,
        restitution: float = 0.0,
    ) -> int:
        cid = self._cid()
        shape_id = p.createCollisionShape(
            p.GEOM_PLANE, planeNormal=normal, physicsClientId=cid
        )
        visual_id = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=[50, 0.05, 50],
            rgbaColor=[0.4, 0.4, 0.4, 1.0],
            specularColor=[0.2, 0.2, 0.2],
            physicsClientId=cid,
        )
        body_id = p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=shape_id,
            baseVisualShapeIndex=visual_id,
            basePosition=(0, -distance, 0),
            physicsClientId=cid,
        )
        p.changeDynamics(
            body_id,
            -1,
            lateralFriction=friction,
            restitution=restitution,
            physicsClientId=cid,
        )
        self._body_count += 1
        return body_id

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
        cid = self._cid()
        joint_id = -1

        if joint_type == "fixed":
            joint_id = p.createConstraint(
                body_a_id, -1,
                body_b_id, -1,
                p.JOINT_FIXED,
                (0, 0, 0),
                anchor,
                childFramePosition=(0, 0, 0),
                parentFrameOrientation=p.getQuaternionFromEuler((0, 0, 0)),
                childFrameOrientation=p.getQuaternionFromEuler((0, 0, 0)),
                physicsClientId=cid,
            )
        else:
            joint_id = p.createConstraint(
                body_a_id, -1,
                body_b_id, -1,
                p.JOINT_POINT2POINT,
                (0, 0, 0),
                anchor,
                childFramePosition=(0, 0, 0),
                parentFrameOrientation=p.getQuaternionFromEuler((0, 0, 0)),
                childFrameOrientation=p.getQuaternionFromEuler((0, 0, 0)),
                physicsClientId=cid,
            )
        if joint_id >= 0:
            kwargs = {"maxForce": 100, "physicsClientId": cid}
            if joint_type == "spring":
                kwargs["erp"] = min(1.0, stiffness * 0.01)
            try:
                p.changeConstraint(joint_id, **kwargs)
            except Exception:
                pass
        return joint_id

    def remove_joint(self, joint_id: int):
        try:
            p.removeConstraint(joint_id, physicsClientId=self._cid())
        except Exception:
            pass

    def remove_all_joints(self):
        cid = self._cid()
        for bid in list(self._all_body_ids):
            try:
                num_cons = p.getNumJoints(bid, physicsClientId=cid)
                for j in range(num_cons):
                    info = p.getJointInfo(bid, j, physicsClientId=cid)
                    p.removeConstraint(info[3], physicsClientId=cid)
            except Exception:
                pass

    def change_constraint(
        self,
        constraint_id: int,
        pivot: tuple[float, float, float],
        max_force: float = 500,
    ):
        cid = self._cid()
        try:
            p.changeConstraint(
                constraint_id,
                jointChildPivot=pivot,
                maxForce=max_force,
                physicsClientId=cid,
            )
        except Exception:
            pass

    @property
    def body_count(self) -> int:
        return self._body_count

    @property
    def debug_draw(self):
        return self._debug_enabled

    @debug_draw.setter
    def debug_draw(self, enabled: bool):
        self._debug_enabled = enabled
