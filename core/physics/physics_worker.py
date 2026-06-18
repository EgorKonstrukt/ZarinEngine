from __future__ import annotations
from queue import Queue, Empty
from typing import Optional
from PyQt6.QtCore import QThread

from core.logger import Logger


class PhysicsWorker(QThread):
    def __init__(self):
        super().__init__()
        self._cmd_queue: Queue = Queue()
        self._result_queue: Queue = Queue()
        self._running = False
        self._initialized = False
        self._solver = None
        self._physics_scene = None

    def run(self):
        self._running = True
        while self._running:
            try:
                cmd = self._cmd_queue.get(timeout=0.004)
            except Empty:
                continue
            try:
                self._process(cmd)
            except Exception as e:
                Logger.error(f"PhysicsWorker cmd error: {e}")

    def _process(self, cmd: dict):
        t = cmd["type"]

        if t == "init":
            if self._initialized:
                return
            solver_class = cmd["solver_class"]
            settings = cmd.get("settings", {})
            solver = solver_class()
            if solver.initialize(settings):
                from core.physics.physics_scene import PhysicsScene
                self._solver = solver
                self._physics_scene = PhysicsScene(solver)
                self._initialized = True

        elif t == "load_bodies":
            self._solver.remove_all_joints()
            self._solver.remove_all_bodies()
            self._physics_scene._entity_to_body.clear()
            self._physics_scene._body_to_entity.clear()
            self._physics_scene._entity_to_joint.clear()
            self._physics_scene._joint_to_entity.clear()
            self._physics_scene._cached_shape.clear()
            self._physics_scene._cached_shape_info.clear()
            self._physics_scene._prev_frame_contacts.clear()
            for body in cmd["bodies"]:
                bid = self._solver.create_rigid_body(
                    entity_id=body["entity_id"],
                    shape_type=body["shape_type"],
                    shape_params=body["shape_params"],
                    position=body["position"],
                    rotation=body["rotation"],
                    mass=body["mass"],
                    friction=body.get("friction", 0.6),
                    restitution=body.get("restitution", 0.0),
                    is_trigger=body.get("is_trigger", False),
                    is_kinematic=body.get("is_kinematic", False),
                )
                if bid >= 0:
                    self._physics_scene._entity_to_body[body["entity_id"]] = bid
                    self._physics_scene._body_to_entity[bid] = body["entity_id"]
                    self._physics_scene._cached_shape[body["entity_id"]] = ()

        elif t == "step":
            ecs_data = cmd.get("ecs_data", {})
            dt = cmd["dt"]
            ps = self._physics_scene
            solver = self._solver
            if ps is None or solver is None:
                return

            for eid, data in ecs_data.items():
                bid = ps._entity_to_body.get(eid)
                if bid is None:
                    continue
                is_kinematic = data.get("is_kinematic", False)
                if is_kinematic:
                    pos = data.get("pos", (0, 0, 0))
                    rot = data.get("rot", (0, 0, 0))
                    solver.set_body_transform(bid, pos, rot)
                else:
                    vel = data.get("vel", None)
                    if vel is not None:
                        solver.set_velocity(bid, vel)
                    ang_vel = data.get("ang_vel", None)
                    if ang_vel is not None:
                        solver.set_angular_velocity(bid, ang_vel)
                force = data.get("force", (0, 0, 0))
                if force[0] != 0.0 or force[1] != 0.0 or force[2] != 0.0:
                    solver.apply_force(bid, force)
                torque = data.get("torque", (0, 0, 0))
                if torque[0] != 0.0 or torque[1] != 0.0 or torque[2] != 0.0:
                    solver.apply_torque(bid, torque)

            solver.step_simulation(dt)

            transforms = {}
            for eid, data in ecs_data.items():
                bid = ps._entity_to_body.get(eid)
                if bid is None:
                    continue
                if data.get("is_kinematic", False):
                    continue
                if data.get("is_2d", False):
                    vel = solver.get_velocity(bid)
                    ang_vel = solver.get_angular_velocity(bid)
                    if vel[0] != 0.0 or vel[1] != 0.0 or vel[2] != 0.0:
                        solver.set_velocity(bid, (vel[0], vel[1], 0.0))
                    if ang_vel[0] != 0.0 or ang_vel[1] != 0.0 or ang_vel[2] != 0.0:
                        solver.set_angular_velocity(bid, (0.0, 0.0, ang_vel[2]))
                pos, rot = solver.get_body_transform(bid)
                vel = solver.get_velocity(bid)
                ang_vel = solver.get_angular_velocity(bid)
                transforms[eid] = {
                    "pos": pos,
                    "rot": rot,
                    "vel": vel,
                    "ang_vel": ang_vel,
                }

            events = solver.get_collision_events() if hasattr(solver, 'get_collision_events') else []

            self._result_queue.put({
                "type": "step_result",
                "transforms": transforms,
                "collision_events": events,
            })

        elif t == "remove_bodies":
            for eid in cmd["entity_ids"]:
                bid = self._physics_scene._entity_to_body.pop(eid, None)
                if bid is not None:
                    self._solver.remove_rigid_body(bid)
                    self._physics_scene._body_to_entity.pop(bid, None)

        elif t == "add_body":
            body = cmd["body"]
            bid = self._solver.create_rigid_body(
                entity_id=body["entity_id"],
                shape_type=body["shape_type"],
                shape_params=body["shape_params"],
                position=body["position"],
                rotation=body["rotation"],
                mass=body["mass"],
                friction=body.get("friction", 0.6),
                restitution=body.get("restitution", 0.0),
                is_trigger=body.get("is_trigger", False),
                is_kinematic=body.get("is_kinematic", False),
            )
            if bid >= 0:
                self._physics_scene._entity_to_body[body["entity_id"]] = bid
                self._physics_scene._body_to_entity[bid] = body["entity_id"]
                self._physics_scene._cached_shape[body["entity_id"]] = ()

        elif t == "unload_all":
            if self._solver:
                self._solver.remove_all_joints()
                self._solver.remove_all_bodies()
            if self._physics_scene:
                self._physics_scene._entity_to_body.clear()
                self._physics_scene._body_to_entity.clear()
                self._physics_scene._entity_to_joint.clear()
                self._physics_scene._joint_to_entity.clear()
                self._physics_scene._cached_shape.clear()
                self._physics_scene._cached_shape_info.clear()
                self._physics_scene._prev_frame_contacts.clear()

        elif t == "shutdown":
            if self._physics_scene:
                self._physics_scene.shutdown()
                self._physics_scene = None
            if self._solver:
                self._solver.shutdown()
                self._solver = None
            self._running = False

    def send(self, cmd: dict):
        self._cmd_queue.put(cmd)

    def poll(self) -> Optional[dict]:
        try:
            return self._result_queue.get_nowait()
        except Empty:
            return None

    def drain_results(self) -> list[dict]:
        results = []
        while True:
            r = self.poll()
            if r is None:
                break
            results.append(r)
        return results

    def shutdown(self, timeout: int = 3000):
        self.send({"type": "shutdown"})
        self.wait(timeout)
