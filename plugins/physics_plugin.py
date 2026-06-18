from __future__ import annotations
import math
from typing import Optional, TYPE_CHECKING
from core.plugin_manager import PluginBase
from core.logger import Logger
from core.physics import PhysicsScene
from core.physics.physics_worker import PhysicsWorker
from core.math3d import Vec2, Vec3, Quat
from core.config import get_project_config

if TYPE_CHECKING:
    from core.physics.physics_solver import IPhysicsSolver

_RAD = math.radians
_DEG = math.degrees


class PhysicsPlugin(PluginBase):
    NAME = "PhysicsPlugin"
    VERSION = "0.2.0"
    DESCRIPTION = "Physics system with background-thread simulation."
    SYSTEM = True

    def __init__(self):
        super().__init__()
        self._solver: Optional[IPhysicsSolver] = None
        self._physics_scene: Optional[PhysicsScene] = None
        self._worker: Optional[PhysicsWorker] = None
        self._enabled: bool = True
        self._solver_class = None
        self._scanned_entity_ids: set[str] = set()
        self._last_entity_count: int = -1

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, v: bool):
        self._enabled = v

    @property
    def physics_scene(self) -> Optional[PhysicsScene]:
        return self._physics_scene

    @property
    def solver(self) -> Optional[IPhysicsSolver]:
        return self._solver

    def _get_physics_settings(self) -> dict:
        project_path = getattr(self._engine, "_project_path", ".") if self._engine else "."
        cfg = get_project_config(project_path)
        out = {}
        prefix = "physics."
        for k in (
            "solver",
            "physx_device",
            "gravity_x", "gravity_y", "gravity_z",
            "fixed_time_step", "num_sub_steps", "solver_iterations",
            "erp", "contact_erp", "friction_erp",
            "contact_breaking_threshold", "restitution",
            "linear_damping", "angular_damping", "max_contacts_per_body",
        ):
            v = cfg.get(prefix + k)
            if v is not None:
                out[k] = v
        return out

    def set_solver(self, solver: IPhysicsSolver):
        old = self._solver
        if old is not None:
            old.shutdown()
        self._solver = solver
        if solver is not None:
            solver.initialize(self._get_physics_settings())
        if self._physics_scene is not None:
            self._physics_scene._solver = solver
        Logger.info(f"PhysicsPlugin: solver set to {type(solver).__name__}")

    def initialize(self, engine):
        super().initialize(engine)
        self._load_solver_from_settings()
        self._worker = PhysicsWorker()
        self._worker.start()
        if self._solver_class:
            self._worker.send({"type": "init", "solver_class": self._solver_class, "settings": self._get_physics_settings()})
        Logger.info("[PhysicsPlugin] Physics system initialized.")

    def _load_solver_from_settings(self):
        settings = self._get_physics_settings()
        solver_name = settings.get("solver", "pybullet")
        try:
            if solver_name == "physx":
                from physics_solvers.physx_solver import PhysXSolver
                solver_cls = PhysXSolver
            else:
                from physics_solvers.pybullet_solver import PyBulletSolver
                solver_cls = PyBulletSolver
            self._solver_class = solver_cls
            solver = solver_cls()
            if solver.initialize(settings):
                self._solver = solver
                self._physics_scene = PhysicsScene(solver)
                Logger.info(f"PhysicsPlugin: solver {solver_name} loaded ({type(solver).__name__}).")
            else:
                Logger.error(f"PhysicsPlugin: failed to init solver '{solver_name}'.")
        except ImportError as e:
            Logger.warning(f"PhysicsPlugin: solver '{solver_name}' not available ({e}). "
                           f"Falling back to pybullet.")
            try:
                from physics_solvers.pybullet_solver import PyBulletSolver
                self._solver_class = PyBulletSolver
                solver = PyBulletSolver()
                if solver.initialize(settings):
                    self._solver = solver
                    self._physics_scene = PhysicsScene(solver)
                    Logger.info("PhysicsPlugin: fallback PyBulletSolver loaded.")
            except ImportError:
                Logger.error("PhysicsPlugin: no physics solver available.")

    def _snapshot_bodies(self, scene) -> list[dict]:
        ps = self._physics_scene
        if not ps:
            return []
        bodies = []
        for entity in scene.get_all_entities():
            rb = entity._components.get("Rigidbody")
            rb2d = entity._components.get("Rigidbody2D")
            tr = entity._components.get("Transform")
            if (not rb and not rb2d) or not tr:
                continue
            shape_info = ps._find_shape(entity, tr)
            if not shape_info:
                continue
            is_2d = rb2d is not None
            lp = tr._local_pos
            q = tr._local_rot
            if is_2d:
                pos = (lp.x, lp.y, 0.0)
                sz = 2.0 * math.asin(max(-1.0, min(1.0, q.z)))
                rot = (0.0, 0.0, sz)
                mass = 0.0 if rb2d.is_kinematic else rb2d.mass
                is_kinematic = rb2d.is_kinematic
            else:
                pos = (lp.x, lp.y, lp.z)
                euler = tr.local_euler_angles
                rot = (_RAD(euler.x), _RAD(euler.y), _RAD(euler.z))
                mass = 0.0 if rb.is_kinematic else rb.mass
                is_kinematic = rb.is_kinematic
            bodies.append({
                "entity_id": entity.id,
                "is_2d": is_2d,
                "shape_type": shape_info["type"],
                "shape_params": shape_info["params"],
                "position": pos,
                "rotation": rot,
                "mass": mass,
                "friction": shape_info.get("friction", 0.6),
                "restitution": shape_info.get("restitution", 0.0),
                "is_trigger": shape_info.get("is_trigger", False),
                "is_kinematic": is_kinematic,
            })
        return bodies

    def _snapshot_ecs(self, scene) -> dict:
        ps = self._physics_scene
        if not ps or not hasattr(ps, '_entity_to_body'):
            return {}
        ecs_data = {}
        entities = scene._entities
        for eid in ps._entity_to_body:
            entity = entities.get(eid)
            if not entity or not entity._active:
                continue
            rb = entity._components.get("Rigidbody")
            rb2d = entity._components.get("Rigidbody2D")
            tr = entity._components.get("Transform")
            if not tr:
                continue
            lp = tr._local_pos
            if rb2d is not None:
                r = rb2d
                if r.is_kinematic:
                    continue
                frc = r._force_accum._d
                q = tr._local_rot
                sz = 2.0 * math.asin(max(-1.0, min(1.0, q.z)))
                ecs_data[eid] = {
                    "is_2d": True,
                    "is_kinematic": False,
                    "pos": (lp.x, lp.y, 0.0),
                    "rot": (0.0, 0.0, sz),
                    "vel": (r._velocity.x, r._velocity.y, 0.0),
                    "ang_vel": (0.0, 0.0, r._angular_velocity),
                    "force": (float(frc[0]), float(frc[1]), 0.0),
                    "torque": (0.0, 0.0, r._torque_accum),
                }
            elif rb is not None:
                r = rb
                if r.is_kinematic:
                    continue
                frc = r._force_accum._d
                tor = r._torque_accum._d
                q = tr._local_rot
                ecs_data[eid] = {
                    "is_2d": False,
                    "is_kinematic": False,
                    "pos": (lp.x, lp.y, lp.z),
                    "quat": (q.x, q.y, q.z, q.w),
                    "vel": (r._velocity.x, r._velocity.y, r._velocity.z),
                    "ang_vel": (r._angular_velocity.x, r._angular_velocity.y, r._angular_velocity.z),
                    "force": (float(frc[0]), float(frc[1]), float(frc[2])),
                    "torque": (float(tor[0]), float(tor[1]), float(tor[2])),
                }
        return ecs_data

    def _apply_worker_results(self, scene, transforms: dict, events: list):
        entities = scene._entities
        for eid, data in transforms.items():
            entity = entities.get(eid)
            if not entity:
                continue
            rb = entity._components.get("Rigidbody")
            rb2d = entity._components.get("Rigidbody2D")
            tr = entity._components.get("Transform")
            if not tr:
                continue
            if rb2d is not None:
                if rb2d.is_kinematic:
                    continue
                pos = data["pos"]
                rot = data["rot"]
                tr._local_pos = Vec3(pos[0], pos[1], 0.0)
                half_z = rot[2] * 0.5
                tr._local_rot = Quat(0.0, 0.0, math.sin(half_z), math.cos(half_z))
                tr._mark_dirty()
                vel = data["vel"]
                rb2d._velocity = Vec2(vel[0], vel[1])
                rb2d._angular_velocity = data["ang_vel"][2]
                rb2d._force_accum = Vec2.zero()
                rb2d._torque_accum = 0.0
            elif rb is not None:
                if rb.is_kinematic:
                    continue
                pos = data["pos"]
                tr._local_pos = Vec3(pos[0], pos[1], pos[2])
                if "quat" in data:
                    q = data["quat"]
                    tr._local_rot = Quat(q[0], q[1], q[2], q[3])
                else:
                    rot = data["rot"]
                    tr.local_euler_angles = Vec3(_DEG(rot[0]), _DEG(rot[1]), _DEG(rot[2]))
                tr._mark_dirty()
                vel = data["vel"]
                av = data["ang_vel"]
                rb._velocity = Vec3(vel[0], vel[1], vel[2])
                rb._angular_velocity = Vec3(av[0], av[1], av[2])
                rb._force_accum = Vec3.zero()
                rb._torque_accum = Vec3.zero()

        def _dispatch(body_id: int, callback: str, other_eid: str):
            ps = self._physics_scene
            if not ps or not hasattr(ps, '_body_to_entity'):
                return
            eid = ps._body_to_entity.get(body_id)
            if not eid:
                return
            entity = entities.get(eid)
            if not entity:
                return
            from core.components import ScriptComponent
            for sc in entity.get_components(ScriptComponent):
                inst = sc._py_instance
                if inst and hasattr(inst, callback):
                    try:
                        getattr(inst, callback)(other_eid)
                    except Exception as e:
                        Logger.error(f"Script {callback} error: {e}")

        ps = self._physics_scene
        prev = ps._prev_frame_contacts if (ps and hasattr(ps, '_prev_frame_contacts')) else set()
        current: set = set()
        pe = ps._body_to_entity if (ps and hasattr(ps, '_body_to_entity')) else {}
        for ev in events:
            ba, bb = ev.get("body_a", -1), ev.get("body_b", -1)
            if ba >= 0 and bb >= 0:
                current.add(frozenset((ba, bb)))
        entered = current - prev
        exited = prev - current
        stayed = current & prev
        for pair in entered:
            bl = tuple(pair)
            e0, e1 = pe.get(bl[0], ""), pe.get(bl[1], "")
            if e0 and e1:
                _dispatch(bl[0], "on_collision_enter", e1)
                _dispatch(bl[1], "on_collision_enter", e0)
        for pair in exited:
            bl = tuple(pair)
            e0, e1 = pe.get(bl[0], ""), pe.get(bl[1], "")
            if e0 and e1:
                _dispatch(bl[0], "on_collision_exit", e1)
                _dispatch(bl[1], "on_collision_exit", e0)
        for pair in stayed:
            bl = tuple(pair)
            e0, e1 = pe.get(bl[0], ""), pe.get(bl[1], "")
            if e0 and e1:
                _dispatch(bl[0], "on_collision_stay", e1)
                _dispatch(bl[1], "on_collision_stay", e0)
        if ps and hasattr(ps, '_prev_frame_contacts'):
            ps._prev_frame_contacts = current

    def on_scene_loaded(self, scene):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        if self._solver is None:
            return
        if self._physics_scene is None:
            self._physics_scene = PhysicsScene(self._solver)
        self._physics_scene.initialize(scene)
        self._physics_scene.load_scene(scene)
        if self._worker and self._worker.isRunning() and self._worker._initialized:
            bodies = self._snapshot_bodies(scene)
            self._worker.send({"type": "load_bodies", "bodies": bodies})

    def on_scene_unloaded(self, scene):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        if self._worker and self._worker.isRunning():
            self._worker.send({"type": "unload_all"})
        if self._physics_scene:
            self._physics_scene.shutdown()

    def on_play_start(self):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        if self._solver is None or self._engine is None:
            return
        scene = self._engine.scene
        if scene is None:
            return
        if self._physics_scene is None:
            self._physics_scene = PhysicsScene(self._solver)
            self._physics_scene.initialize(scene)
        self._physics_scene.load_scene(scene)
        if self._worker and self._worker.isRunning() and self._worker._initialized:
            bodies = self._snapshot_bodies(scene)
            self._worker.send({"type": "load_bodies", "bodies": bodies})
        Logger.info("[PhysicsPlugin] Scene re-scanned for physics on play start.")

    def on_play_stop(self):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        if self._worker and self._worker.isRunning():
            self._worker.send({"type": "unload_all"})
        if self._physics_scene:
            self._physics_scene.shutdown()
        Logger.info("[PhysicsPlugin] Physics bodies cleaned up on play stop.")

    def _register_new_bodies(self, scene):
        ps = self._physics_scene
        if not ps:
            return
        entities_dict = scene._entities
        entity_count = len(entities_dict)
        if entity_count == self._last_entity_count and self._scanned_entity_ids:
            return
        self._last_entity_count = entity_count
        scanned = self._scanned_entity_ids
        tracked = ps._entity_to_body
        worker = self._worker
        worker_running = worker and worker.isRunning()
        for eid, entity in entities_dict.items():
            if eid in scanned:
                continue
            scanned.add(eid)
            if eid in tracked:
                continue
            rb = entity._components.get("Rigidbody")
            rb2d = entity._components.get("Rigidbody2D")
            tr = entity._components.get("Transform")
            if (not rb and not rb2d) or not tr:
                continue
            shape_info = ps._find_shape(entity, tr)
            if not shape_info:
                continue
            is_2d = rb2d is not None
            effective_rb = rb2d if is_2d else rb
            lp = tr._local_pos
            body_data = {
                "entity_id": eid,
                "shape_type": shape_info["type"],
                "shape_params": shape_info["params"],
                "friction": shape_info.get("friction", 0.6),
                "restitution": shape_info.get("restitution", 0.0),
                "is_trigger": shape_info.get("is_trigger", False),
            }
            if is_2d:
                q = tr._local_rot
                sz = 2.0 * math.asin(max(-1.0, min(1.0, q.z)))
                body_data["position"] = (lp.x, lp.y, 0.0)
                body_data["rotation"] = (0.0, 0.0, sz)
                body_data["mass"] = 0.0 if rb2d.is_kinematic else rb2d.mass
                body_data["is_kinematic"] = rb2d.is_kinematic
            else:
                euler = tr.local_euler_angles
                body_data["position"] = (lp.x, lp.y, lp.z)
                body_data["rotation"] = (_RAD(euler.x), _RAD(euler.y), _RAD(euler.z))
                body_data["mass"] = 0.0 if rb.is_kinematic else rb.mass
                body_data["is_kinematic"] = rb.is_kinematic
            if worker_running:
                self._worker.send({"type": "add_body", "body": body_data})
                tracked[eid] = -1
                ps._cached_shape[eid] = ps._make_shape_key(entity, shape_info)
                if is_2d:
                    ps._2d_bodies.add(-1)
                effective_rb._body_id = -1
            else:
                ps._create_entity_bodies(entity)

    def pre_step(self, dt: float):
        if not self._enabled or not self._physics_scene:
            return
        if not self._engine or not self._engine.scene:
            return
        scene = self._engine.scene
        prof = self._engine.profiler
        prof.start("physics_scan_bodies")
        self._register_new_bodies(scene)
        prof.stop("physics_scan_bodies")
        if self._worker and self._worker.isRunning():
            prof.start("physics_drain_results")
            for r in self._worker.drain_results():
                if r.get("type") == "step_result":
                    self._apply_worker_results(scene, r.get("transforms", {}), r.get("collision_events", []))
            prof.stop("physics_drain_results")

    def step(self, dt: float):
        if not self._enabled or not self._physics_scene:
            return
        if not self._engine or not self._engine.scene:
            return
        scene = self._engine.scene
        prof = self._engine.profiler
        if self._worker and self._worker.isRunning():
            prof.start("physics_snapshot")
            ecs_data = self._snapshot_ecs(scene)
            prof.stop("physics_snapshot")
            prof.start("physics_worker_send")
            self._worker.send({"type": "step", "dt": dt, "ecs_data": ecs_data})
            prof.stop("physics_worker_send")
        else:
            prof.start("physics_scene_step")
            self._physics_scene.step(dt)
            prof.stop("physics_scene_step")

    def shutdown(self):
        if self._worker:
            self._worker.shutdown()
            self._worker = None
        if self._solver:
            self._solver.shutdown()
            self._solver = None
        self._physics_scene = None
        Logger.info("[PhysicsPlugin] Physics shutdown.")