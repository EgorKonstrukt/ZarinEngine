from __future__ import annotations
import os
import math
from typing import Optional, TYPE_CHECKING
from core.plugin_manager import PluginBase
from core.logger import Logger
from core.physics import PhysicsProcess
from core.math3d import Vec2, Vec3, Quat
from core.config import get_project_config

if TYPE_CHECKING:
    from core.ecs import Entity

_RAD = math.radians
_DEG = math.degrees

_SHAPE_TYPE_MAP = {
    "BoxCollider": "box",
    "SphereCollider": "sphere",
    "CapsuleCollider": "capsule",
    "MeshCollider": "mesh",
    "BoxCollider2D": "box",
    "CircleCollider2D": "cylinder",
}


def _find_shape_info(entity: "Entity", transform=None) -> Optional[dict]:
    for comp in entity.get_all_components():
        cname = type(comp).__name__
        if cname not in _SHAPE_TYPE_MAP:
            continue
        params = {}
        friction = 0.6
        restitution = 0.0
        is_trigger = False

        if cname == "BoxCollider":
            params["size"] = [comp.scaled_size.x, comp.scaled_size.y, comp.scaled_size.z]
            params["center"] = [comp.scaled_center.x, comp.scaled_center.y, comp.scaled_center.z]
            friction = comp.material_friction
            restitution = comp.material_bounciness
            is_trigger = comp.is_trigger
        elif cname == "SphereCollider":
            params["radius"] = comp.scaled_radius
            params["center"] = [comp.scaled_center.x, comp.scaled_center.y, comp.scaled_center.z]
            friction = comp.material_friction
            restitution = comp.material_bounciness
            is_trigger = comp.is_trigger
        elif cname == "CapsuleCollider":
            params["radius"] = comp.scaled_radius
            params["height"] = comp.scaled_height
            params["center"] = [comp.scaled_center.x, comp.scaled_center.y, comp.scaled_center.z]
            params["direction"] = comp.direction
            is_trigger = comp.is_trigger
        elif cname == "BoxCollider2D":
            sz = comp.scaled_size
            params["size"] = [sz.x, sz.y, 1.0]
            off = comp.scaled_offset
            params["center"] = [off.x, off.y, 0.0]
            friction = comp.material_friction
            restitution = comp.material_bounciness
            is_trigger = comp.is_trigger
        elif cname == "CircleCollider2D":
            params["radius"] = comp.scaled_radius
            params["height"] = 1.0
            off = comp.scaled_offset
            params["center"] = [off.x, off.y, 0.0]
            friction = comp.material_friction
            restitution = comp.material_bounciness
            is_trigger = comp.is_trigger
        elif cname == "MeshCollider":
            params["file"] = comp.mesh_path
            params["collision_mode"] = comp.collision_mode.value
            params["max_vertices"] = comp.max_vertices
            friction = comp.material_friction
            restitution = comp.material_bounciness
            is_trigger = comp.is_trigger

        scale = _read_import_scale(params.get("file", ""))
        s = transform.local_scale if transform else Vec3.one()
        if scale is not None:
            params["scale"] = [scale * s.x, scale * s.y, scale * s.z]
        elif cname == "MeshCollider":
            params["scale"] = [s.x, s.y, s.z]

        return {
            "type": _SHAPE_TYPE_MAP[cname],
            "params": params,
            "friction": friction,
            "restitution": restitution,
            "is_trigger": is_trigger,
        }
    return None


def _read_import_scale(mesh_path: str):
    if not mesh_path:
        return None
    import json, os
    import_path = mesh_path + ".import"
    if not os.path.isabs(import_path):
        import_path = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", import_path))
    if os.path.exists(import_path):
        try:
            with open(import_path) as f:
                return json.load(f).get("scale", 1.0)
        except Exception:
            pass
    return None


class PhysicsPlugin(PluginBase):
    NAME = "PhysicsPlugin"
    VERSION = "0.3.0"
    DESCRIPTION = "Physics system with threaded simulation."
    SYSTEM = True

    def __init__(self):
        super().__init__()
        self._enabled: bool = True
        self._scanned_entity_ids: set[str] = set()
        self._last_entity_count: int = -1
        self._physics_process: Optional[PhysicsProcess] = None
        self._prev_frame_contacts: set = set()
        self._project_root: str = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..")
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, v: bool):
        self._enabled = v

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

    def initialize(self, engine):
        super().initialize(engine)
        settings = self._get_physics_settings()
        solver_name = settings.get("solver", "pybullet")
        solver_module = ""
        solver_class = ""
        if solver_name == "physx":
            solver_module = "physics_solvers.physx_solver"
            solver_class = "PhysXSolver"
        else:
            solver_module = "physics_solvers.pybullet_solver"
            solver_class = "PyBulletSolver"

        self._physics_process = PhysicsProcess(project_root=self._project_root)
        ok = self._physics_process.start(solver_module, solver_class, settings)
        if not ok:
            Logger.error("PhysicsPlugin: process init failed.")
            self._physics_process = None
            return
        Logger.info(f"PhysicsPlugin: solver {solver_name} started in separate process.")

    def _snapshot_bodies(self, scene) -> list[dict]:
        bodies = []
        for entity in scene.get_all_entities():
            rb = entity._components.get("Rigidbody")
            rb2d = entity._components.get("Rigidbody2D")
            tr = entity._components.get("Transform")
            if (not rb and not rb2d) or not tr:
                continue
            shape_info = _find_shape_info(entity, tr)
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
        ecs_data = {}
        entities = scene._entities
        for eid, entity in entities.items():
            if not entity._active:
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
                    "is_2d": True, "is_kinematic": False,
                    "pos": (lp.x, lp.y, 0.0), "rot": (0.0, 0.0, sz),
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
                    "is_2d": False, "is_kinematic": False,
                    "pos": (lp.x, lp.y, lp.z), "quat": (q.x, q.y, q.z, q.w),
                    "vel": (r._velocity.x, r._velocity.y, r._velocity.z),
                    "ang_vel": (r._angular_velocity.x, r._angular_velocity.y, r._angular_velocity.z),
                    "force": (float(frc[0]), float(frc[1]), float(frc[2])),
                    "torque": (float(tor[0]), float(tor[1]), float(tor[2])),
                }
        return ecs_data

    def _apply_result(self, scene, result: dict):
        transforms = result.get("transforms", {})
        events = result.get("collision_events", [])
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

        if not events:
            return
        current: set = set()
        for ev in events:
            ea, eb = ev.get("entity_a", ""), ev.get("entity_b", "")
            if ea and eb:
                current.add(frozenset((ea, eb)))
        entered = current - self._prev_frame_contacts
        exited = self._prev_frame_contacts - current
        stayed = current & self._prev_frame_contacts
        for pair in entered:
            e0, e1 = tuple(pair)
            self._dispatch_collision(entities, e0, e1, "on_collision_enter")
            self._dispatch_collision(entities, e1, e0, "on_collision_enter")
        for pair in exited:
            e0, e1 = tuple(pair)
            self._dispatch_collision(entities, e0, e1, "on_collision_exit")
            self._dispatch_collision(entities, e1, e0, "on_collision_exit")
        for pair in stayed:
            e0, e1 = tuple(pair)
            self._dispatch_collision(entities, e0, e1, "on_collision_stay")
            self._dispatch_collision(entities, e1, e0, "on_collision_stay")
        self._prev_frame_contacts = current

    def _dispatch_collision(self, entities, eid: str, other_eid: str, callback: str):
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

    def _build_body_dict(self, entity, tr) -> Optional[dict]:
        rb = entity._components.get("Rigidbody")
        rb2d = entity._components.get("Rigidbody2D")
        shape_info = _find_shape_info(entity, tr)
        if not shape_info:
            return None
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
        return {
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
        }

    def on_scene_loaded(self, scene):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        self._prev_frame_contacts.clear()

    def on_scene_unloaded(self, scene):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        self._prev_frame_contacts.clear()
        if self._physics_process:
            self._physics_process.send({"type": "unload_all"})

    def on_play_start(self):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        self._prev_frame_contacts.clear()
        if self._physics_process is None or self._engine is None:
            return
        scene = self._engine.scene
        if scene is None:
            return
        bodies = self._snapshot_bodies(scene)
        if not bodies:
            return
        self._physics_process.send({"type": "load_bodies", "bodies": bodies})
        if self._physics_process.wait_for_result("load_bodies", timeout=5.0) is None:
            Logger.error("PhysicsPlugin: load_bodies timed out.")
            return
        Logger.info(f"[PhysicsPlugin] Scene loaded with {len(bodies)} bodies in physics process.")

    def on_play_stop(self):
        self._scanned_entity_ids.clear()
        self._last_entity_count = -1
        self._prev_frame_contacts.clear()
        if self._physics_process:
            self._physics_process.send({"type": "unload_all"})

    def pre_step(self, dt: float):
        if not self._enabled or self._physics_process is None:
            return
        if not self._engine or not self._engine.scene:
            return
        scene = self._engine.scene
        prof = self._engine.profiler
        prof.start("physics_scan_bodies")
        entities_dict = scene._entities
        entity_count = len(entities_dict)
        if entity_count != self._last_entity_count or not self._scanned_entity_ids:
            self._last_entity_count = entity_count
            scanned = self._scanned_entity_ids
            for eid, entity in entities_dict.items():
                if eid in scanned:
                    continue
                scanned.add(eid)
                rb = entity._components.get("Rigidbody")
                rb2d = entity._components.get("Rigidbody2D")
                tr = entity._components.get("Transform")
                if (not rb and not rb2d) or not tr:
                    continue
                body_dict = self._build_body_dict(entity, tr)
                if body_dict:
                    self._physics_process.send({"type": "add_body", "body": body_dict})
        prof.stop("physics_scan_bodies")

    def step(self, dt: float):
        if not self._enabled or self._physics_process is None:
            return
        if not self._engine or not self._engine.scene:
            return
        scene = self._engine.scene
        prof = self._engine.profiler

        prof.start("physics_collect_results")
        result = self._physics_process.poll()
        while result is not None:
            if result.get("type") == "step_result":
                self._apply_result(scene, result)
            result = self._physics_process.poll()
        prof.stop("physics_collect_results")

        prof.start("physics_build_ecs")
        ecs_data = self._snapshot_ecs(scene)
        prof.stop("physics_build_ecs")

        prof.start("physics_queue_step")
        self._physics_process.send({
            "type": "step",
            "ecs_data": ecs_data,
            "dt": dt,
            "need_collisions": True,
        })
        prof.stop("physics_queue_step")

    def shutdown(self):
        if self._physics_process:
            self._physics_process.shutdown(5000)
            self._physics_process = None
