# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
from core.foundation.logger import Logger
from core.physics.shapep import find_shapes_info, make_shapes_key, partition_compound_shapes


class BodiesMixin:
    def _soft_component(self, entity):
        try:
            from core.components.physics.soft_body import SoftBody
            comp = entity.get_component(SoftBody)
            if comp is not None and getattr(comp, "enabled", True):
                return comp
        except Exception:
            pass
        return None

    def _diag_soft_once(self, msg: str):
        if not getattr(self, "_soft_diag", False):
            self._soft_diag = True
            Logger.warning(f"[SoftBody] {msg}")

    def _create_entity_bodies(self, entity):
        from core.components import Rigidbody, Rigidbody2D
        if self._soft_component(entity) is not None:
            return
        rb = entity.get_component(Rigidbody)
        rb2d = entity.get_component(Rigidbody2D)
        tr = entity.transform
        if (not rb and not rb2d) or not tr:
            return
        is_2d = rb2d is not None
        effective_rb = rb2d if is_2d else rb
        shapes = find_shapes_info(entity, tr)
        if not shapes:
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
        if is_2d or len(shapes) == 1:
            shape_info = shapes[0]
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
                collision_layer=shape_info.get("layer", 0),
                collision_mask=shape_info.get("mask", 0xFFFF),
            )
            extra_shapes: list[dict] = []
        else:
            dynamic = (mass > 0.0) and (not is_kinematic) and (not shapes[0].get("is_trigger", False))
            prims, extra_shapes = partition_compound_shapes(shapes, dynamic)
            if len(prims) == 1 and not extra_shapes:
                shape_info = prims[0]
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
                    collision_layer=shape_info.get("layer", 0),
                    collision_mask=shape_info.get("mask", 0xFFFF),
                )
            else:
                first = shapes[0]
                if not prims:
                    shape_info = first
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
                        collision_layer=shape_info.get("layer", 0),
                        collision_mask=shape_info.get("mask", 0xFFFF),
                    )
                    extra_shapes = [s for s in shapes if s is not first]
                else:
                    anchor = prims[0]
                    body_id = self._solver.create_compound_rigid_body(
                        entity_id=entity.id,
                        shapes=prims,
                        position=pos,
                        rotation=rot,
                        mass=mass,
                        friction=anchor.get("friction", 0.6),
                        restitution=anchor.get("restitution", 0.0),
                        is_trigger=anchor.get("is_trigger", False),
                        is_kinematic=is_kinematic,
                        collision_layer=anchor.get("layer", 0),
                        collision_mask=anchor.get("mask", 0xFFFF),
                    )
        if body_id >= 0:
            self._entity_to_body[entity.id] = body_id
            self._body_to_entity[body_id] = entity.id
            self._entity_body_cache[entity.id] = (entity, effective_rb, tr, is_2d)
            effective_rb._body_id = body_id
            self._mark_body_items_dirty()
            if is_2d:
                self._2d_bodies.add(body_id)
            key = make_shapes_key(shapes)
            self._cached_shape[entity.id] = key
            self._cached_shape_info[entity.id] = shapes
            if extra_shapes:
                body_static = (mass <= 0.0) or is_kinematic or shapes[0].get("is_trigger", False)
                for extra in extra_shapes:
                    self._create_extra_body(entity, extra, pos, rot, mass, is_kinematic, body_static)

    def _create_extra_body(self, entity, shape_info: dict, pos, rot, mass: float, is_kinematic: bool, body_static: bool):
        extra_static = body_static or shape_info["type"] == "heightfield"
        try:
            extra_id = self._solver.create_rigid_body(
                entity_id=entity.id,
                shape_type=shape_info["type"],
                shape_params=shape_info["params"],
                position=pos,
                rotation=rot,
                mass=0.0 if extra_static else (0.0 if is_kinematic else mass),
                friction=shape_info.get("friction", 0.6),
                restitution=shape_info.get("restitution", 0.0),
                is_trigger=shape_info.get("is_trigger", False),
                is_kinematic=True if extra_static else is_kinematic,
                collision_layer=shape_info.get("layer", 0),
                collision_mask=shape_info.get("mask", 0xFFFF),
            )
        except Exception:
            return
        if extra_id is not None and extra_id >= 0:
            self._body_to_entity[extra_id] = entity.id
            self._entity_to_extra_bodies.setdefault(entity.id, []).append(extra_id)

    def _sync_extra_bodies(self):
        if not self._entity_to_extra_bodies:
            return
        try:
            from core.math_helpers import quat_to_euler_rad
        except ImportError:
            return
        for entity_id, extras in self._entity_to_extra_bodies.items():
            cached = self._entity_body_cache.get(entity_id)
            if not cached:
                continue
            entity, rb, tr, is_2d = cached
            if not entity._active:
                continue
            if not getattr(tr, "_physics_dirty", False):
                continue
            p = tr._local_pos
            if is_2d:
                bpos = (p._x, p._y, 0.0)
                brot = (0.0, 0.0, quat_to_euler_rad(tr._local_rot._x, tr._local_rot._y, tr._local_rot._z, tr._local_rot._w)[2])
            else:
                e = quat_to_euler_rad(tr._local_rot._x, tr._local_rot._y, tr._local_rot._z, tr._local_rot._w)
                bpos = (p._x, p._y, p._z)
                brot = e
            for extra_id in extras:
                try:
                    self._solver.set_body_transform(extra_id, bpos, brot)
                except Exception:
                    pass

    def _create_entity_soft(self, entity):
        if entity.id in self._entity_to_soft:
            return
        soft = self._soft_component(entity)
        if soft is None:
            return
        tr = entity.transform
        if tr is None:
            Logger.warning(f"[SoftBody] '{getattr(entity, 'name', entity.id)}' has no transform, skipping")
            return
        sig = self._soft_sig(entity, soft, tr)
        if sig is None:
            Logger.warning(f"[SoftBody] '{getattr(entity, 'name', entity.id)}' signature is None, skipping")
            return
        if not self._build_entity_soft(entity, soft, tr):
            return
        self._cached_soft_sig[entity.id] = sig
        try:
            pose = self._soft_applied_pose(tr)
            if pose is not None:
                soft._soft_applied_pose = pose
        except Exception:
            pass
        try:
            from core.components import Rigidbody
            if entity.get_component(Rigidbody) is not None:
                Logger.warning(f"SoftBody owns '{getattr(entity, 'name', entity.id)}', rigid body skipped")
        except Exception:
            pass

    def _remove_entity_soft(self, entity_id: str):
        sid = self._entity_to_soft.pop(entity_id, None)
        if sid is not None:
            try:
                self._solver.remove_soft_body(sid)
            except Exception:
                pass
            self._body_to_entity.pop(sid, None)
        self._cached_soft_sig.pop(entity_id, None)
        try:
            entity = self._get_entity(entity_id)
            soft = self._soft_component(entity) if entity is not None else None
            if soft is not None:
                for attr in ("_soft_skin_idx", "_soft_skin_w", "_soft_skin_nsim",
                             "_soft_skin_nfull", "_soft_skin_scale", "_soft_skin_mesh",
                             "_soft_use_skin", "_soft_needs_rebuild"):
                    try:
                        if hasattr(soft, attr):
                            delattr(soft, attr)
                    except Exception:
                        pass
        except Exception:
            pass

    def _check_soft_changes(self):
        for entity_id in list(self._entity_to_soft.keys()):
            entity = self._get_entity(entity_id)
            if entity is None:
                self._remove_entity_soft(entity_id)
                continue
            soft = self._soft_component(entity)
            if soft is None:
                self._remove_entity_soft(entity_id)
                continue
            tr = entity.transform
            if tr is None:
                continue
            sig = self._soft_sig(entity, soft, tr)
            if sig is not None and sig != self._cached_soft_sig.get(entity_id):
                self._remove_entity_soft(entity_id)
                self._create_entity_soft(entity)

    def remove_entity_bodies(self, entity_id: str):
        self._remove_entity_soft(entity_id)
        body_id = self._entity_to_body.pop(entity_id, None)
        if body_id is not None:
            self._solver.remove_rigid_body(body_id)
            self._body_to_entity.pop(body_id, None)
            self._2d_bodies.discard(body_id)
        for extra_id in self._entity_to_extra_bodies.pop(entity_id, []):
            try:
                self._solver.remove_rigid_body(extra_id)
            except Exception:
                pass
            self._body_to_entity.pop(extra_id, None)
            self._2d_bodies.discard(extra_id)
        self._entity_body_cache.pop(entity_id, None)
        self._mark_body_items_dirty()
        joint_id = self._entity_to_joint.pop(entity_id, None)
        if joint_id is not None:
            self._solver.remove_joint(joint_id)
            self._joint_to_entity.pop(joint_id, None)

    def rebuild_entity(self, entity):
        self._cached_shape.pop(entity.id, None)
        self._cached_shape_info.pop(entity.id, None)
        self.remove_entity_bodies(entity.id)
        self._create_entity_bodies(entity)

    def _check_shape_changes(self):
        for entity_id in list(self._entity_to_body.keys()):
            entity = self._get_entity(entity_id)
            if not entity:
                continue
            shapes = self._find_shapes(entity, entity.transform)
            if not shapes:
                continue
            current_key = make_shapes_key(shapes)
            cached = self._cached_shape.get(entity_id)
            if cached is not None and current_key != cached:
                self.rebuild_entity(entity)
        self._check_soft_changes()

    def _sync_ecs_to_physics(self):
        try:
            from core._physics_sync import batch_sync_ecs_to_physics
            self._sync_extra_bodies()
            items = self._get_sync_items()
            if items:
                batch_sync_ecs_to_physics(items, self._solver)
            from core.math_helpers import quat_to_euler_rad
            for entity_id, body_id, entity, rb, tr, is_2d in items:
                if not entity._active:
                    continue
                if not getattr(tr, "_physics_dirty", False):
                    continue
                p = tr._local_pos
                q = tr._local_rot
                if is_2d:
                    self._solver.set_body_transform(body_id, (p._x, p._y, 0.0), (0.0, 0.0, quat_to_euler_rad(q._x, q._y, q._z, q._w)[2]))
                else:
                    e = quat_to_euler_rad(q._x, q._y, q._z, q._w)
                    self._solver.set_body_transform(body_id, (p._x, p._y, p._z), e)
                try:
                    self._solver.activate(body_id)
                except Exception:
                    pass
                tr._physics_dirty = False
        except ImportError:
            from core.math_helpers import quat_to_euler_rad
            self._sync_extra_bodies()
            cache = self._entity_body_cache
            for entity_id, body_id in self._entity_to_body.items():
                cached = cache.get(entity_id)
                if not cached:
                    continue
                entity, rb, tr, is_2d = cached
                if not entity._active:
                    continue
                if getattr(tr, "_physics_dirty", False):
                    p = tr._local_pos
                    if is_2d:
                        self._solver.set_body_transform(body_id, (p._x, p._y, 0.0), (0.0, 0.0, quat_to_euler_rad(tr._local_rot._x, tr._local_rot._y, tr._local_rot._z, tr._local_rot._w)[2]))
                    else:
                        e = quat_to_euler_rad(tr._local_rot._x, tr._local_rot._y, tr._local_rot._z, tr._local_rot._w)
                        self._solver.set_body_transform(body_id, (p._x, p._y, p._z), e)
                    try:
                        self._solver.activate(body_id)
                    except Exception:
                        pass
                    tr._physics_dirty = False
                fa = rb._force_accum
                if is_2d:
                    if fa._x != 0.0 or fa._y != 0.0:
                        self._solver.apply_force(body_id, (fa._x, fa._y, 0.0))
                    if abs(rb._torque_accum) > 1e-10:
                        self._solver.apply_torque(body_id, (0.0, 0.0, rb._torque_accum))
                else:
                    if fa._x * fa._x + fa._y * fa._y + fa._z * fa._z > 1e-10:
                        self._solver.apply_force(body_id, (fa._x, fa._y, fa._z))
                    ta = rb._torque_accum
                    if ta._x * ta._x + ta._y * ta._y + ta._z * ta._z > 1e-10:
                        self._solver.apply_torque(body_id, (ta._x, ta._y, ta._z))

    def _sync_physics_to_ecs(self):
        try:
            from core._physics_sync import batch_sync_physics_to_ecs
            items = self._get_sync_items()
            if items:
                batch_sync_physics_to_ecs(items, self._solver)
        except ImportError:
            from core.math_helpers import quat_from_euler_rad
            cache = self._entity_body_cache
            try:
                _scn = self._scene
            except Exception:
                _scn = None
            for entity_id, body_id in self._entity_to_body.items():
                cached = cache.get(entity_id)
                if not cached:
                    continue
                entity, rb, tr, is_2d = cached
                if not entity._active or rb.is_kinematic or getattr(tr, "_physics_dirty", False):
                    continue
                pos, rot = self._solver.get_body_transform(body_id)
                vel = self._solver.get_velocity(body_id)
                ang_vel = self._solver.get_angular_velocity(body_id)
                tr._local_pos._x = pos[0]
                tr._local_pos._y = pos[1]
                tr._local_pos._z = 0.0 if is_2d else pos[2]
                if is_2d:
                    q = quat_from_euler_rad(0.0, 0.0, rot[2])
                else:
                    q = quat_from_euler_rad(rot[0], rot[1], rot[2])
                tr._local_rot._x = q[0]
                tr._local_rot._y = q[1]
                tr._local_rot._z = q[2]
                tr._local_rot._w = q[3]
                tr._dirty = True
                if _scn is not None:
                    try:
                        _scn._dirty_roots.add(tr)
                        _scn._transform_version_pending = True
                    except Exception:
                        pass
                rb._velocity._x = vel[0]
                rb._velocity._y = vel[1]
                if not is_2d:
                    rb._velocity._z = vel[2]
                    rb._angular_velocity._x = ang_vel[0]
                    rb._angular_velocity._y = ang_vel[1]
                    rb._angular_velocity._z = ang_vel[2]
                else:
                    rb._angular_velocity = ang_vel[2]
                rb._force_accum._x = 0.0
                rb._force_accum._y = 0.0
                if not is_2d:
                    rb._force_accum._z = 0.0
                    rb._torque_accum._x = 0.0
                    rb._torque_accum._y = 0.0
                    rb._torque_accum._z = 0.0
                else:
                    rb._torque_accum = 0.0
