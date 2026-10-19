# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from core.foundation.logger import Logger
from core.physics.scene.bodies import BodiesMixin
from core.physics.scene.colliders import CollidersMixin
from core.physics.scene.joints import JointsMixin
from core.physics.scene.events import EventsMixin
from core.physics.scene.threadpool import ThreadpoolMixin

if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.physics.physics_solver import IPhysicsSolver


_INV_FAST = None
_INV_TRIED = False


def _ensure_inv_fast():
    global _INV_FAST, _INV_TRIED
    if _INV_TRIED:
        return _INV_FAST
    _INV_TRIED = True
    try:
        from core.math_helpers import mat4_inv_fast as _f
        _INV_FAST = _f
    except Exception:
        _INV_FAST = None
    return _INV_FAST


class PhysicsScene(BodiesMixin, CollidersMixin, JointsMixin, EventsMixin, ThreadpoolMixin):
    _ZERO_VEC3 = None
    _ZERO_VEC2 = None

    def __init__(self, solver: IPhysicsSolver):
        self._solver = solver
        self._entity_to_body: dict[str, int] = {}
        self._body_to_entity: dict[int, str] = {}
        self._entity_to_extra_bodies: dict[str, list[int]] = {}
        self._entity_to_soft: dict[str, int] = {}
        self._cached_soft_sig: dict[str, tuple] = {}
        self._entity_body_cache: dict[str, tuple] = {}
        self._entity_to_joint: dict[str, int] = {}
        self._joint_to_entity: dict[int, str] = {}
        self._cached_shape: dict[str, tuple] = {}
        self._cached_shape_info: dict[str, list] = {}
        self._prev_frame_contacts: set[frozenset[int]] = set()
        self._scene: Optional[Scene] = None
        self._2d_bodies: set[int] = set()
        self._shape_check_counter: int = 0
        self._body_items: list[tuple[str, int]] = []
        self._body_items_dirty: bool = False
        self._sync_items: list[tuple] | None = None
        self._reg_count: int = -1
        self._reg_rv = None
        self._has_collision_scripts: bool = False
        self._collision_scripts_checked: bool = False
        self._collision_listener_sig: tuple = None

    @property
    def solver(self) -> IPhysicsSolver:
        return self._solver

    def initialize(self, scene: Scene):
        self._scene = scene
        Logger.info("PhysicsScene initialized.")

    def shutdown(self):
        self._solver.remove_all_joints()
        self._solver.remove_all_bodies()
        try:
            self._solver.remove_all_soft_bodies()
        except Exception:
            pass
        self._entity_to_body.clear()
        self._body_to_entity.clear()
        self._entity_to_extra_bodies.clear()
        self._entity_to_soft.clear()
        self._cached_soft_sig.clear()
        self._entity_body_cache.clear()
        self._entity_to_joint.clear()
        self._joint_to_entity.clear()
        self._cached_shape.clear()
        self._cached_shape_info.clear()
        self._sync_items = None
        self._body_items = []
        self._body_items_dirty = False
        self._reg_count = -1
        self._reg_rv = None
        self._prev_frame_contacts.clear()
        self._2d_bodies.clear()
        self._has_collision_scripts = False
        self._collision_scripts_checked = False
        self._scene = None

    def load_scene(self, scene: Scene):
        self._scene = scene
        self._solver.remove_all_joints()
        self._solver.remove_all_bodies()
        try:
            self._solver.remove_all_soft_bodies()
        except Exception:
            pass
        self._entity_to_body.clear()
        self._body_to_entity.clear()
        self._entity_to_extra_bodies.clear()
        self._entity_to_soft.clear()
        self._cached_soft_sig.clear()
        self._entity_body_cache.clear()
        self._entity_to_joint.clear()
        self._joint_to_entity.clear()
        self._cached_shape.clear()
        self._cached_shape_info.clear()
        self._sync_items = None
        self._body_items = []
        self._body_items_dirty = False
        self._reg_count = -1
        self._reg_rv = None
        self._2d_bodies.clear()
        self._has_collision_scripts = False
        self._collision_scripts_checked = False
        entities = scene.get_all_entities()
        for entity in entities:
            self._create_entity_bodies(entity)
        for entity in entities:
            self._create_entity_soft(entity)
        for entity in entities:
            self._create_entity_joints(entity)

    def step(self, dt: float):
        if not self._scene:
            return
        eng = self._scene._engine
        if eng is None:
            return
        if self._entity_to_soft and not getattr(self, "_soft_step_logged", False):
            Logger.info(f"[PhysicsScene] step with {len(self._entity_to_soft)} soft bodies, dt={dt:.4f}")
            self._soft_step_logged = True
        prof = eng._profiler if hasattr(eng, "_profiler") else None
        if prof:
            prof.start("phys_register")
        self._register_new_entities()
        if prof:
            prof.stop("phys_register")
        self._shape_check_counter += 1
        if self._shape_check_counter >= 60:
            self._shape_check_counter = 0
            if prof:
                prof.start("phys_shape_check")
            self._check_shape_changes()
            if prof:
                prof.stop("phys_shape_check")
        if prof:
            prof.start("phys_sync_to_solver")
        self._sync_ecs_to_physics()
        if prof:
            prof.stop("phys_sync_to_solver")
        if self._entity_to_soft and len(self._entity_to_soft) >= 2:
            if prof:
                prof.start("phys_soft_separate")
            try:
                self._separate_soft_bodies(dt)
            except Exception:
                pass
            if prof:
                prof.stop("phys_soft_separate")
        if prof:
            prof.start("phys_step_sim")
        self._solver.step_simulation(dt)
        if prof:
            prof.stop("phys_step_sim")
        if self._2d_bodies:
            if prof:
                prof.start("phys_constrain_2d")
            self._constrain_2d_bodies()
            if prof:
                prof.stop("phys_constrain_2d")
        if prof:
            prof.start("phys_sync_to_ecs")
        self._sync_physics_to_ecs()
        if prof:
            prof.stop("phys_sync_to_ecs")
        if self._entity_to_soft:
            if prof:
                prof.start("phys_sync_soft")
            self._sync_soft_bodies()
            if prof:
                prof.stop("phys_sync_soft")
        if prof:
            prof.start("phys_collision_events")
        self._process_collision_events()
        if prof:
            prof.stop("phys_collision_events")

    def _register_new_entities(self):
        if not self._scene:
            return
        all_ents = self._scene.get_all_entities()
        try:
            rv = self._scene._render_version
        except Exception:
            rv = None
        if len(all_ents) == self._reg_count and rv == self._reg_rv:
            return
        self._reg_count = len(all_ents)
        self._reg_rv = rv
        need_reset = False
        for entity in all_ents:
            if entity.id not in self._entity_to_body:
                before = len(self._entity_to_body)
                self._create_entity_bodies(entity)
                if len(self._entity_to_body) != before:
                    need_reset = True
            if entity.id not in self._entity_to_soft:
                before = len(self._entity_to_soft)
                self._create_entity_soft(entity)
                if len(self._entity_to_soft) != before:
                    need_reset = True
        if need_reset:
            self._has_collision_scripts = False
            self._collision_scripts_checked = False

    def _constrain_2d_bodies(self):
        for body_id in list(self._2d_bodies):
            pos, rot = self._solver.get_body_transform(body_id)
            clamped = False
            if pos[2] != 0.0:
                clamped = True
            if rot[0] != 0.0 or rot[1] != 0.0:
                clamped = True
            if clamped:
                self._solver.set_body_transform(body_id, (pos[0], pos[1], 0.0), (0.0, 0.0, rot[2]))
            vel = self._solver.get_velocity(body_id)
            if vel[2] != 0.0:
                self._solver.set_velocity(body_id, (vel[0], vel[1], 0.0))
            ang_vel = self._solver.get_angular_velocity(body_id)
            if ang_vel[0] != 0.0 or ang_vel[1] != 0.0:
                self._solver.set_angular_velocity(body_id, (0.0, 0.0, ang_vel[2]))

    def _mark_body_items_dirty(self):
        self._body_items_dirty = True

    def _get_sync_items(self):
        if self._body_items_dirty or self._sync_items is None:
            self._body_items = list(self._entity_to_body.items())
            self._body_items_dirty = False
            cache = self._entity_body_cache
            items = []
            for eid, bid in self._body_items:
                c = cache.get(eid)
                if c is not None:
                    items.append((eid, bid, c[0], c[1], c[2], c[3]))
            self._sync_items = items
        return self._sync_items

    def _get_body_items(self):
        if self._body_items_dirty or not self._body_items:
            self._body_items = list(self._entity_to_body.items())
            self._body_items_dirty = False
        return self._body_items

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

    def ray_cast(self, origin, direction, max_distance: float = 100.0) -> Optional[dict]:
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

    @staticmethod
    def _entity_frame_inv(tr):
        import numpy as np
        try:
            wm = tr.world_matrix
            m = np.asarray(wm._d, dtype=np.float64)
            if m.shape != (4, 4):
                raise ValueError("bad world matrix shape")
            f = _ensure_inv_fast()
            if f is not None:
                return f(np.ascontiguousarray(m, dtype=np.float64))
            return np.linalg.inv(m)
        except Exception:
            pass
        try:
            p = tr.local_position
            q = tr.local_rotation
            x, y, z, w = q.x, q.y, q.z, q.w
            n = x * x + y * y + z * z + w * w
            if n > 1e-20:
                inv = 1.0 / (n ** 0.5)
                x *= inv
                y *= inv
                z *= inv
                w *= inv
            R = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)],
                [2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)],
                [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)],
            ], dtype=np.float64)
            F = np.eye(4, dtype=np.float64)
            F[:3, :3] = R.T
            F[3, :3] = [p.x, p.y, p.z]
            try:
                g = _ensure_inv_fast()
                if g is not None:
                    return g(np.ascontiguousarray(F, dtype=np.float64))
                return np.linalg.inv(F)
            except Exception:
                return None
        except Exception:
            return None

    def _sync_soft_bodies(self):
        if not self._entity_to_soft or not self._scene:
            return
        import numpy as np
        if not getattr(self, "_soft_sync_logged", False):
            Logger.info(f"[PhysicsScene] _sync_soft_bodies called, {len(self._entity_to_soft)} entities")
            self._soft_sync_logged = True
        for entity_id, sid in list(self._entity_to_soft.items()):
            entity = self._get_entity(entity_id)
            if entity is None or not entity._active:
                self._diag_soft_once("sync: entity missing/inactive")
                continue
            soft = self._soft_component(entity)
            if soft is None:
                self._remove_entity_soft(entity_id)
                continue
            tr = entity.transform
            if tr is None:
                self._diag_soft_once(f"sync '{entity_id}': no transform")
                continue
            try:
                if self._soft_check_user_teleport(entity, soft, tr):
                    sid = self._entity_to_soft.get(entity_id, sid)
            except Exception:
                pass
            try:
                world = self._solver.get_soft_body_world_vertices(sid)
            except Exception:
                self._diag_soft_once(f"sync '{entity_id}': get_soft_body_world_vertices raised")
                continue
            if world is None or len(world) == 0:
                self._diag_soft_once(f"sync '{entity_id}': no world verts (world={world is not None})")
                continue
            try:
                self._soft_apply_com(entity, soft, tr, sid)
            except Exception:
                pass
            invW = self._entity_frame_inv(tr)
            if invW is None:
                self._diag_soft_once(f"sync '{entity_id}': _entity_frame_inv returned None")
                continue
            try:
                w4 = np.ones((len(world), 4), dtype=np.float64)
                w4[:, :3] = np.asarray(world, dtype=np.float64)
                local = (w4 @ invW)[:, :3].astype(np.float32)
            except Exception:
                continue
            if not np.all(np.isfinite(local)):
                self._diag_soft_once(f"sync '{entity_id}': local has NaN/inf")
                continue
            self._sync_soft_mesh(entity_id, soft, local)
