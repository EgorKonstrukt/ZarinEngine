from __future__ import annotations
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, TYPE_CHECKING
from core.logger import Logger
from core.math3d import Vec2, Vec3

_PHYSICS_POOL = ThreadPoolExecutor(max_workers=min(4, max(2, (os.cpu_count() or 4))), thread_name_prefix="physics")

if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.physics.physics_solver import IPhysicsSolver


_SHAPE_TYPE_MAP = {
    "BoxCollider": "box",
    "SphereCollider": "sphere",
    "CapsuleCollider": "capsule",
    "MeshCollider": "mesh",
    "BoxCollider2D": "box",
    "CircleCollider2D": "cylinder",
}


_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read_import_scale(mesh_path: str):
    if not mesh_path:
        return None
    import_path = mesh_path + ".import"
    if not os.path.isabs(import_path):
        import_path = os.path.normpath(os.path.join(_PROJECT_ROOT, import_path))
    if os.path.exists(import_path):
        try:
            with open(import_path) as f:
                settings = json.load(f)
            return settings.get("scale", 1.0)
        except Exception:
            pass
    return None


_SHAPE_INFO_CACHE_KEYS = {
    "BoxCollider": ("type", "size", "center", "friction", "restitution", "is_trigger"),
    "SphereCollider": ("type", "radius", "center", "friction", "restitution", "is_trigger"),
    "CapsuleCollider": ("type", "radius", "height", "center", "direction", "friction", "restitution", "is_trigger"),
    "MeshCollider": ("type", "file", "collision_mode", "max_vertices", "scale", "friction", "restitution", "is_trigger"),
    "BoxCollider2D": ("type", "size", "center", "friction", "restitution", "is_trigger"),
    "CircleCollider2D": ("type", "radius", "height", "center", "friction", "restitution", "is_trigger"),
}


class PhysicsScene:
    """Bridges ECS entities with the physics solver."""

    def __init__(self, solver: IPhysicsSolver):
        self._solver = solver
        self._entity_to_body: dict[str, int] = {}
        self._body_to_entity: dict[int, str] = {}
        self._entity_to_joint: dict[str, int] = {}
        self._joint_to_entity: dict[int, str] = {}
        self._cached_shape: dict[str, tuple] = {}
        self._cached_shape_info: dict[str, dict] = {}
        self._prev_frame_contacts: set[frozenset[int]] = set()
        self._scene: Optional[Scene] = None
        self._2d_bodies: set[int] = set()
        self._shape_check_counter: int = 0

    @property
    def solver(self) -> IPhysicsSolver:
        return self._solver

    def initialize(self, scene: Scene):
        self._scene = scene
        Logger.info("PhysicsScene initialized.")

    def shutdown(self):
        self._solver.remove_all_joints()
        self._solver.remove_all_bodies()
        self._entity_to_body.clear()
        self._body_to_entity.clear()
        self._entity_to_joint.clear()
        self._joint_to_entity.clear()
        self._cached_shape.clear()
        self._cached_shape_info.clear()
        self._prev_frame_contacts.clear()
        self._2d_bodies.clear()
        self._scene = None

    def load_scene(self, scene: Scene):
        self._scene = scene
        self._solver.remove_all_joints()
        self._solver.remove_all_bodies()
        self._entity_to_body.clear()
        self._body_to_entity.clear()
        self._entity_to_joint.clear()
        self._joint_to_entity.clear()
        self._cached_shape.clear()
        self._cached_shape_info.clear()
        self._2d_bodies.clear()
        entities = scene.get_all_entities()
        for entity in entities:
            self._create_entity_bodies(entity)
        for entity in entities:
            self._create_entity_joints(entity)

    def _create_entity_bodies(self, entity: Entity):
        from core.components import Rigidbody, Rigidbody2D, Transform

        rb = entity.get_component(Rigidbody)
        rb2d = entity.get_component(Rigidbody2D)
        tr = entity.get_component(Transform)
        if (not rb and not rb2d) or not tr:
            return

        is_2d = rb2d is not None
        effective_rb = rb2d if is_2d else rb

        shape_info = self._find_shape(entity, tr)
        if not shape_info:
            return

        if entity.id in self._entity_to_body:
            return

        if is_2d:
            pos = (tr.local_position.x, tr.local_position.y, 0.0)
            euler = tr.local_euler_angles
            rot = (0.0, 0.0, math.radians(euler.z))
        else:
            pos = (tr.local_position.x, tr.local_position.y, tr.local_position.z)
            euler = tr.local_euler_angles
            rot = (math.radians(euler.x), math.radians(euler.y), math.radians(euler.z))

        if is_2d:
            mass = 0.0 if rb2d.is_kinematic else rb2d.mass
            is_kinematic = rb2d.is_kinematic
        else:
            mass = 0.0 if rb.is_kinematic else rb.mass
            is_kinematic = rb.is_kinematic

        body_id = self._solver.create_rigid_body(
            entity_id=entity.id,
            shape_type=shape_info["type"],
            shape_params=shape_info["params"],
            position=pos,
            rotation=rot,
            mass=mass,
            friction=shape_info.get("friction", 0.6),
            restitution=shape_info.get("restitution", 0.0),
            is_trigger=shape_info.get("is_trigger", False),
            is_kinematic=is_kinematic,
        )
        if body_id >= 0:
            self._entity_to_body[entity.id] = body_id
            self._body_to_entity[body_id] = entity.id
            effective_rb._body_id = body_id
            if is_2d:
                self._2d_bodies.add(body_id)
            key = self._make_shape_key(entity, shape_info)
            self._cached_shape[entity.id] = key
            self._cached_shape_info[entity.id] = shape_info

    def _find_shape(self, entity: Entity, transform=None) -> Optional[dict]:
        for comp in entity.get_all_components():
            cname = type(comp).__name__
            if cname in _SHAPE_TYPE_MAP:
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
        # Fallback: if entity has a MeshFilter with a mesh path, treat as MeshCollider
        from core.components import MeshFilter
        mf = entity.get_component(MeshFilter)
        if mf and mf.mesh_path:
            s = transform.local_scale if transform else Vec3.one()
            scale = _read_import_scale(mf.mesh_path)
            if scale is not None:
                params = {"file": mf.mesh_path, "collision_mode": "auto", "max_vertices": 2000, "scale": [scale * s.x, scale * s.y, scale * s.z]}
            else:
                params = {"file": mf.mesh_path, "collision_mode": "auto", "max_vertices": 2000, "scale": [s.x, s.y, s.z]}
            return {
                "type": "mesh",
                "params": params,
                "friction": 0.6,
                "restitution": 0.0,
                "is_trigger": False,
            }
        return None

    def _make_shape_key(self, entity: Entity, shape_info: dict) -> tuple:
        """Produce a comparable tuple to detect shape changes at runtime."""
        cname = None
        for comp in entity.get_all_components():
            if type(comp).__name__ in _SHAPE_TYPE_MAP:
                cname = type(comp).__name__
                break
        if cname is None:
            return ()
        keys = _SHAPE_INFO_CACHE_KEYS.get(cname, ())
        parts = [shape_info["type"]]
        for k in keys:
            if k == "type":
                continue
            val = shape_info["params"].get(k, shape_info.get(k))
            if isinstance(val, list):
                parts.append(tuple(val))
            else:
                parts.append(val)
        return tuple(parts)

    def remove_entity_bodies(self, entity_id: str):
        body_id = self._entity_to_body.pop(entity_id, None)
        if body_id is not None:
            self._solver.remove_rigid_body(body_id)
            self._body_to_entity.pop(body_id, None)
            self._2d_bodies.discard(body_id)
        joint_id = self._entity_to_joint.pop(entity_id, None)
        if joint_id is not None:
            self._solver.remove_joint(joint_id)
            self._joint_to_entity.pop(joint_id, None)

    def step(self, dt: float):
        if not self._scene:
            return
        eng = self._scene._engine
        prof = eng._profiler if eng and hasattr(eng, '_profiler') else None

        if prof: prof.start("phys_register")
        self._register_new_entities()
        if prof: prof.stop("phys_register")

        self._shape_check_counter += 1
        if self._shape_check_counter >= 60:
            self._shape_check_counter = 0
            if prof: prof.start("phys_shape_check")
            self._check_shape_changes()
            if prof: prof.stop("phys_shape_check")

        if prof: prof.start("phys_sync_to_solver")
        self._sync_ecs_to_physics()
        if prof: prof.stop("phys_sync_to_solver")

        if prof: prof.start("phys_step_sim")
        self._solver.step_simulation(dt)
        if prof: prof.stop("phys_step_sim")

        if self._2d_bodies:
            if prof: prof.start("phys_constrain_2d")
            self._constrain_2d_bodies()
            if prof: prof.stop("phys_constrain_2d")

        if prof: prof.start("phys_sync_to_ecs")
        self._sync_physics_to_ecs()
        if prof: prof.stop("phys_sync_to_ecs")

        if prof: prof.start("phys_collision_events")
        self._process_collision_events()
        if prof: prof.stop("phys_collision_events")

    def _register_new_entities(self):
        """Auto-register entities with physics components not yet tracked."""
        entities = self._scene.get_all_entities()
        if len(entities) == len(self._entity_to_body):
            return
        for entity in entities:
            if entity.id not in self._entity_to_body:
                self._create_entity_bodies(entity)

    def _constrain_2d_bodies(self):
        for body_id in list(self._2d_bodies):
            pos, rot = self._solver.get_body_transform(body_id)
            self._solver.set_body_transform(body_id, (pos[0], pos[1], 0.0), (0.0, 0.0, rot[2]))
            vel = self._solver.get_velocity(body_id)
            if vel[0] != 0.0 or vel[1] != 0.0 or vel[2] != 0.0:
                self._solver.set_velocity(body_id, (vel[0], vel[1], 0.0))
            ang_vel = self._solver.get_angular_velocity(body_id)
            if ang_vel[0] != 0.0 or ang_vel[1] != 0.0 or ang_vel[2] != 0.0:
                self._solver.set_angular_velocity(body_id, (0.0, 0.0, ang_vel[2]))

    def _process_collision_events(self):
        from core.components import ScriptComponent

        raw = self._solver.get_collision_events()
        current: set[frozenset[int]] = set()
        for ev in raw:
            ba, bb = ev["body_a"], ev["body_b"]
            if ba < 0 or bb < 0:
                continue
            current.add(frozenset([ba, bb]))

        entered = current - self._prev_frame_contacts
        exited = self._prev_frame_contacts - current
        stayed = current & self._prev_frame_contacts

        def _dispatch(body_id: int, callback: str, other_eid: str):
            eid = self._body_to_entity.get(body_id)
            if not eid:
                return
            entity = self._get_entity(eid)
            if not entity:
                return
            for sc in entity.get_components(ScriptComponent):
                inst = sc._py_instance
                if inst and hasattr(inst, callback):
                    try:
                        getattr(inst, callback)(other_eid)
                    except Exception as e:
                        Logger.error(f"Script {callback} error: {e}")

        dispatch_tasks = []
        for pair in entered:
            bodies = list(pair)
            e0 = self._body_to_entity.get(bodies[0], "")
            e1 = self._body_to_entity.get(bodies[1], "")
            if e0 and e1:
                dispatch_tasks.append((bodies[0], "on_collision_enter", e1))
                dispatch_tasks.append((bodies[1], "on_collision_enter", e0))

        for pair in exited:
            bodies = list(pair)
            e0 = self._body_to_entity.get(bodies[0], "")
            e1 = self._body_to_entity.get(bodies[1], "")
            if e0 and e1:
                dispatch_tasks.append((bodies[0], "on_collision_exit", e1))
                dispatch_tasks.append((bodies[1], "on_collision_exit", e0))

        for pair in stayed:
            bodies = list(pair)
            e0 = self._body_to_entity.get(bodies[0], "")
            e1 = self._body_to_entity.get(bodies[1], "")
            if e0 and e1:
                dispatch_tasks.append((bodies[0], "on_collision_stay", e1))
                dispatch_tasks.append((bodies[1], "on_collision_stay", e0))

        if len(dispatch_tasks) >= 4:
            futures = [_PHYSICS_POOL.submit(_dispatch, bid, cb, eid) for bid, cb, eid in dispatch_tasks]
            for f in as_completed(futures):
                try: f.result()
                except Exception as e:
                    Logger.error(f"Collision dispatch error: {e}")
        else:
            for bid, cb, eid in dispatch_tasks:
                _dispatch(bid, cb, eid)

        self._prev_frame_contacts = current

    def _check_shape_changes(self):
        for entity_id in list(self._entity_to_body.keys()):
            entity = self._get_entity(entity_id)
            if not entity:
                continue
            shape_info = self._find_shape(entity, entity.get_component_by_name("Transform"))
            if shape_info is None:
                continue
            current_key = self._make_shape_key(entity, shape_info)
            cached = self._cached_shape.get(entity_id)
            if cached is not None and current_key != cached:
                self.rebuild_entity(entity)

    def _sync_ecs_to_physics(self):
        from core.components import Rigidbody, Rigidbody2D, Transform

        items = list(self._entity_to_body.items())
        if not items:
            return
        if len(items) >= 4:
            def _batch_sync(batch):
                for entity_id, body_id in batch:
                    entity = self._get_entity(entity_id)
                    if not entity or not entity.active:
                        continue
                    rb = entity._components.get("Rigidbody")
                    rb2d = entity._components.get("Rigidbody2D")
                    tr = entity._components.get("Transform")
                    if (not rb and not rb2d) or not tr:
                        continue
                    is_2d = rb2d is not None
                    if is_2d:
                        if rb2d.is_kinematic:
                            pos = tr.local_position
                            euler = tr.local_euler_angles
                            self._solver.set_body_transform(
                                body_id,
                                (pos.x, pos.y, 0.0),
                                (0.0, 0.0, math.radians(euler.z)),
                            )
                        if rb2d._force_accum._d.any():
                            self._solver.apply_force(
                                body_id,
                                (rb2d._force_accum.x, rb2d._force_accum.y, 0.0),
                            )
                        if abs(rb2d._torque_accum) > 1e-10:
                            self._solver.apply_torque(
                                body_id,
                                (0.0, 0.0, rb2d._torque_accum),
                            )
                    else:
                        if rb.is_kinematic:
                            pos = tr.local_position
                            euler = tr.local_euler_angles
                            self._solver.set_body_transform(
                                body_id,
                                (pos.x, pos.y, pos.z),
                                (math.radians(euler.x), math.radians(euler.y), math.radians(euler.z)),
                            )
                        if rb._force_accum._d.any():
                            self._solver.apply_force(
                                body_id,
                                (rb._force_accum.x, rb._force_accum.y, rb._force_accum.z),
                            )
                        if rb._torque_accum._d.any():
                            self._solver.apply_torque(
                                body_id,
                                (rb._torque_accum.x, rb._torque_accum.y, rb._torque_accum.z),
                            )
            BATCH_SIZE = 32
            batches = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
            futures = [_PHYSICS_POOL.submit(_batch_sync, batch) for batch in batches]
            for f in as_completed(futures):
                try: f.result()
                except Exception as e:
                    Logger.error(f"Physics ECS sync error: {e}")
        else:
            for entity_id, body_id in items:
                entity = self._get_entity(entity_id)
                if not entity or not entity.active:
                    continue
                rb = entity._components.get("Rigidbody")
                rb2d = entity._components.get("Rigidbody2D")
                tr = entity._components.get("Transform")
                if (not rb and not rb2d) or not tr:
                    continue
                is_2d = rb2d is not None
                if is_2d:
                    if rb2d.is_kinematic:
                        pos = tr.local_position
                        euler = tr.local_euler_angles
                        self._solver.set_body_transform(
                            body_id,
                            (pos.x, pos.y, 0.0),
                            (0.0, 0.0, math.radians(euler.z)),
                        )
                    if rb2d._force_accum._x != 0.0 or rb2d._force_accum._y != 0.0:
                        self._solver.apply_force(
                            body_id,
                            (rb2d._force_accum.x, rb2d._force_accum.y, 0.0),
                        )
                    if abs(rb2d._torque_accum) > 1e-10:
                        self._solver.apply_torque(
                            body_id,
                            (0.0, 0.0, rb2d._torque_accum),
                        )
                else:
                    if rb.is_kinematic:
                        pos = tr.local_position
                        euler = tr.local_euler_angles
                        self._solver.set_body_transform(
                            body_id,
                            (pos.x, pos.y, pos.z),
                            (math.radians(euler.x), math.radians(euler.y), math.radians(euler.z)),
                        )
                    if rb._force_accum._d.any():
                        self._solver.apply_force(
                            body_id,
                            (rb._force_accum.x, rb._force_accum.y, rb._force_accum.z),
                        )
                    if rb._torque_accum._d.any():
                        self._solver.apply_torque(
                            body_id,
                            (rb._torque_accum.x, rb._torque_accum.y, rb._torque_accum.z),
                        )

    def _sync_physics_to_ecs(self):
        from core.components import Rigidbody, Rigidbody2D, Transform

        items = list(self._entity_to_body.items())
        if not items:
            return
        if len(items) >= 4:
            def _batch_sync(batch):
                for entity_id, body_id in batch:
                    entity = self._get_entity(entity_id)
                    if not entity or not entity.active:
                        continue
                    rb = entity._components.get("Rigidbody")
                    rb2d = entity._components.get("Rigidbody2D")
                    tr = entity._components.get("Transform")
                    if (not rb and not rb2d) or not tr:
                        continue
                    is_2d = rb2d is not None
                    if is_2d:
                        if rb2d.is_kinematic:
                            continue
                        pos, rot = self._solver.get_body_transform(body_id)
                        vel = self._solver.get_velocity(body_id)
                        ang_vel = self._solver.get_angular_velocity(body_id)
                        tr.local_position = Vec3(pos[0], pos[1], 0.0)
                        tr.local_euler_angles = Vec3(0.0, 0.0, math.degrees(rot[2]))
                        rb2d._velocity = Vec2(vel[0], vel[1])
                        rb2d._angular_velocity = ang_vel[2]
                        rb2d._force_accum = Vec2.zero()
                        rb2d._torque_accum = 0.0
                    else:
                        if rb.is_kinematic:
                            continue
                        pos, rot = self._solver.get_body_transform(body_id)
                        vel = self._solver.get_velocity(body_id)
                        ang_vel = self._solver.get_angular_velocity(body_id)
                        tr.local_position = Vec3(pos[0], pos[1], pos[2])
                        tr.local_euler_angles = Vec3(math.degrees(rot[0]), math.degrees(rot[1]), math.degrees(rot[2]))
                        rb._velocity = Vec3(vel[0], vel[1], vel[2])
                        rb._angular_velocity = Vec3(ang_vel[0], ang_vel[1], ang_vel[2])
                        rb._force_accum = Vec3.zero()
                        rb._torque_accum = Vec3.zero()
            BATCH_SIZE = 32
            batches = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
            futures = [_PHYSICS_POOL.submit(_batch_sync, batch) for batch in batches]
            for f in as_completed(futures):
                try: f.result()
                except Exception as e:
                    Logger.error(f"Physics ECS back-sync error: {e}")
        else:
            for entity_id, body_id in items:
                entity = self._get_entity(entity_id)
                if not entity or not entity.active:
                    continue
                rb = entity._components.get("Rigidbody")
                rb2d = entity._components.get("Rigidbody2D")
                tr = entity._components.get("Transform")
                if (not rb and not rb2d) or not tr:
                    continue
                is_2d = rb2d is not None
                if is_2d:
                    if rb2d.is_kinematic:
                        continue
                    pos, rot = self._solver.get_body_transform(body_id)
                    vel = self._solver.get_velocity(body_id)
                    ang_vel = self._solver.get_angular_velocity(body_id)
                    tr.local_position = Vec3(pos[0], pos[1], 0.0)
                    tr.local_euler_angles = Vec3(0.0, 0.0, math.degrees(rot[2]))
                    rb2d._velocity = Vec2(vel[0], vel[1])
                    rb2d._angular_velocity = ang_vel[2]
                    rb2d._force_accum = Vec2.zero()
                    rb2d._torque_accum = 0.0
                else:
                    if rb.is_kinematic:
                        continue
                    pos, rot = self._solver.get_body_transform(body_id)
                    vel = self._solver.get_velocity(body_id)
                    ang_vel = self._solver.get_angular_velocity(body_id)
                    tr.local_position = Vec3(pos[0], pos[1], pos[2])
                    tr.local_euler_angles = Vec3(math.degrees(rot[0]), math.degrees(rot[1]), math.degrees(rot[2]))
                    rb._velocity = Vec3(vel[0], vel[1], vel[2])
                    rb._angular_velocity = Vec3(ang_vel[0], ang_vel[1], ang_vel[2])
                    rb._force_accum = Vec3.zero()
                    rb._torque_accum = Vec3.zero()

    def _create_entity_joints(self, entity: Entity):
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

    def _find_entity_by_name(self, name: str):
        if not self._scene:
            return None
        for e in self._scene.get_all_entities():
            if e.name == name:
                return e
        return None

    def _get_entity(self, entity_id: str):
        if not self._scene:
            return None
        return self._scene.get_entity(entity_id)

    def ray_cast(self, origin: Vec3, direction: Vec3, max_distance: float = 100.0) -> Optional[dict]:
        result = self._solver.ray_cast(
            (origin.x, origin.y, origin.z),
            (direction.x, direction.y, direction.z),
            max_distance,
        )
        if result:
            body_id = result.get("body_id")
            if body_id is not None and body_id in self._body_to_entity:
                result["entity_id"] = self._body_to_entity[body_id]
        return result

    def create_drag_constraint(
        self,
        body_id: int,
        hit_world: Vec3,
        max_force: float = 500,
    ) -> Optional[int]:
        constraint_id = self._solver.create_joint(
            joint_type="point2point",
            body_a_id=body_id,
            body_b_id=-1,
            anchor=(hit_world.x, hit_world.y, hit_world.z),
        )
        if constraint_id >= 0:
            self._solver.change_constraint(constraint_id, (hit_world.x, hit_world.y, hit_world.z), max_force)
        return constraint_id if constraint_id >= 0 else None

    def update_drag_constraint(self, constraint_id: int, world_pos: Vec3):
        self._solver.change_constraint(constraint_id, (world_pos.x, world_pos.y, world_pos.z))

    def remove_drag_constraint(self, constraint_id: int):
        self._solver.remove_joint(constraint_id)

    def get_collision_events(self) -> list[dict]:
        return self._solver.get_collision_events()

    def rebuild_entity(self, entity: Entity):
        self._cached_shape.pop(entity.id, None)
        self._cached_shape_info.pop(entity.id, None)
        self.remove_entity_bodies(entity.id)
        self._create_entity_bodies(entity)
