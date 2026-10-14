# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
import numpy as np
from core.foundation.logger import Logger
from physics_solvers.culverin_solver.solverp.broadphase import SHAPE_BOX, SHAPE_SPHERE, SHAPE_CAPSULE, SHAPE_CYLINDER, MOTION_STATIC, MOTION_KINEMATIC, MOTION_DYNAMIC, euler_to_quat, _SHAPE_TYPE_MAP, _layer_category, _mask_value, _load_mesh_geometry

def _load_mesh_verts(path: str) -> Optional[np.ndarray]:
    verts, _ = _load_mesh_geometry(path)
    return verts


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
        if self._world is None:
            return -1

        body_id = self._next_body_id
        self._next_body_id += 1

        if mass <= 0.0 or is_trigger:
            motion = MOTION_STATIC
            mass_val = 0.0
        elif is_kinematic:
            motion = MOTION_KINEMATIC
            mass_val = mass
        else:
            motion = MOTION_DYNAMIC
            mass_val = mass

        rot_q = euler_to_quat(rotation[0], rotation[1], rotation[2])

        handle = -1
        com = None

        if shape_type == "mesh":
            handle, com = self._create_mesh_collider(
                position, rot_q, mass_val, motion, shape_params,
                friction, restitution, is_trigger,
                collision_layer, collision_mask, body_id,
            )
        elif shape_type == "heightfield":
            handle = self._create_heightfield_collider(
                position, rot_q, mass_val, motion, shape_params,
                friction, restitution, is_trigger,
                collision_layer, collision_mask, body_id,
            )
            com = None
        else:
            handle, com = self._create_primitive_body(
                shape_type, shape_params, position, rot_q,
                mass_val, motion, friction, restitution, is_trigger,
                _layer_category(collision_layer), _mask_value(collision_mask),
                body_id,
            )

        if handle is None or handle < 0:
            return -1

        if motion == MOTION_DYNAMIC and self._enable_sleeping:
            self._world.set_linear_velocity(handle, 0.0, -0.001, 0.0)
            self._world.set_linear_velocity(handle, 0.0, 0.0, 0.0)

        self._body_count += 1
        self._all_body_ids.append(body_id)
        self._body_handles.append(handle)
        self._handle_to_id[handle] = body_id
        self._id_to_handle[body_id] = handle
        if entity_id:
            self._entity_to_body[entity_id] = body_id
        self._body_to_entity[body_id] = entity_id
        self._body_specs[body_id] = {
            "entity_id": entity_id,
            "shape_type": shape_type,
            "mass": mass_val,
            "friction": friction,
            "restitution": restitution,
            "is_trigger": is_trigger,
            "is_kinematic": is_kinematic,
            "com": com,
        }

        return body_id

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
        if self._world is None or not shapes:
            return -1

        body_id = self._next_body_id
        self._next_body_id += 1

        if mass <= 0.0 or is_trigger:
            motion = MOTION_STATIC
            mass_val = 0.0
        elif is_kinematic:
            motion = MOTION_KINEMATIC
            mass_val = mass
        else:
            motion = MOTION_DYNAMIC
            mass_val = mass

        try:
            if any(bool(s.get("is_trigger", False)) != bool(is_trigger) for s in shapes):
                Logger.warning("CulverinSolver: mixed trigger/solid colliders share one body, using the first")
        except Exception:
            pass

        rot_q = euler_to_quat(rotation[0], rotation[1], rotation[2])
        category = _layer_category(collision_layer)
        mask = _mask_value(collision_mask)

        try:
            from core.physics.shapep import part_volume, part_center, capsule_part_quat, capsule_section_height
        except Exception:
            return -1

        parts: list = []
        total_vol = 0.0
        com_acc = [0.0, 0.0, 0.0]
        for s in shapes:
            stype = s.get("type", "box")
            params = s.get("params", {})
            if stype not in ("box", "sphere", "capsule", "cylinder"):
                continue
            spec = self._compound_part_spec(stype, params, part_center, capsule_part_quat, capsule_section_height)
            if spec is None:
                continue
            pquat, cshape, size = spec
            cen = part_center(stype, params)
            try:
                vol = max(float(part_volume(stype, params)), 1e-9)
            except Exception:
                vol = 1.0
            parts.append(((float(cen[0]), float(cen[1]), float(cen[2])), pquat, cshape, size))
            total_vol += vol
            com_acc[0] += vol * cen[0]
            com_acc[1] += vol * cen[1]
            com_acc[2] += vol * cen[2]

        if not parts:
            return -1

        if total_vol > 0.0:
            com = (com_acc[0] / total_vol, com_acc[1] / total_vol, com_acc[2] / total_vol)
        else:
            com = None
        if motion == MOTION_STATIC:
            com = None

        try:
            handle = self._world.create_compound_body(
                parts=parts,
                pos=position,
                rot=rot_q,
                motion=motion, mass=mass_val,
                user_data=body_id, is_sensor=is_trigger,
                category=category, mask=mask,
                friction=friction, restitution=restitution,
            )
        except Exception as e:
            Logger.warning(f"CulverinSolver: create_compound_body failed: {e}")
            return -1
        if handle is None or handle < 0:
            return -1

        if motion == MOTION_DYNAMIC and self._enable_sleeping:
            self._world.set_linear_velocity(handle, 0.0, -0.001, 0.0)
            self._world.set_linear_velocity(handle, 0.0, 0.0, 0.0)

        self._body_count += 1
        self._all_body_ids.append(body_id)
        self._body_handles.append(handle)
        self._handle_to_id[handle] = body_id
        self._id_to_handle[body_id] = handle
        if entity_id:
            self._entity_to_body[entity_id] = body_id
        self._body_to_entity[body_id] = entity_id
        self._body_specs[body_id] = {
            "entity_id": entity_id,
            "shape_type": "compound",
            "mass": mass_val,
            "friction": friction,
            "restitution": restitution,
            "is_trigger": is_trigger,
            "is_kinematic": is_kinematic,
            "com": com,
        }
        return body_id

    def _compound_part_spec(self, shape_type, params, part_center, capsule_part_quat, capsule_section_height):
        try:
            cen = part_center(shape_type, params)
        except Exception:
            cen = [0.0, 0.0, 0.0]
        if shape_type == "box":
            s = params.get("size", [1, 1, 1])
            try:
                half = (max(float(s[0]) * 0.5, 1e-4), max(float(s[1]) * 0.5, 1e-4), max(float(s[2]) * 0.5, 1e-4))
            except Exception:
                return None
            return (0.0, 0.0, 0.0, 1.0), SHAPE_BOX, half
        if shape_type == "sphere":
            try:
                r = max(float(params.get("radius", 0.5)), 1e-4)
            except Exception:
                return None
            return (0.0, 0.0, 0.0, 1.0), SHAPE_SPHERE, r
        if shape_type == "capsule":
            try:
                r, hsec = capsule_section_height(float(params.get("radius", 0.5)), float(params.get("height", 2.0)))
            except Exception:
                return None
            try:
                direction = int(params.get("direction", 1))
            except Exception:
                direction = 1
            return capsule_part_quat(direction), SHAPE_CAPSULE, (r, hsec * 0.5)
        if shape_type == "cylinder":
            try:
                r = max(float(params.get("radius", 0.5)), 1e-4)
                h = max(float(params.get("height", 1.0)), 1e-4)
            except Exception:
                return None
            return (0.0, 0.0, 0.0, 1.0), SHAPE_CYLINDER, (r, h * 0.5)
        return None

    def _create_primitive_body(
        self, shape_type, shape_params, position, rot_q,
        mass_val, motion, friction, restitution, is_trigger,
        category, mask, body_id,
    ):
        culv_shape = _SHAPE_TYPE_MAP.get(shape_type, SHAPE_BOX)
        try:
            from core.physics.shapep import part_center, capsule_part_quat, capsule_section_height
        except Exception:
            return -1, None
        if shape_type in ("box", "sphere", "capsule", "cylinder"):
            try:
                cen = part_center(shape_type, shape_params)
            except Exception:
                cen = [0.0, 0.0, 0.0]
            spec = self._compound_part_spec(shape_type, shape_params, part_center, capsule_part_quat, capsule_section_height)
            if spec is None:
                return -1, None
            pquat, cshape, size = spec
            if abs(cen[0]) + abs(cen[1]) + abs(cen[2]) < 1e-9 and pquat == (0.0, 0.0, 0.0, 1.0):
                try:
                    handle = self._world.create_body(
                        pos=position,
                        rot=rot_q,
                        size=size,
                        shape=cshape,
                        motion=motion,
                        mass=mass_val,
                        friction=friction,
                        restitution=restitution,
                        category=category,
                        mask=mask,
                        is_sensor=is_trigger,
                        user_data=body_id,
                    )
                    return (handle if handle is not None else -1), None
                except Exception:
                    return -1, None
            com = (float(cen[0]), float(cen[1]), float(cen[2])) if motion != MOTION_STATIC else None
            try:
                handle = self._world.create_compound_body(
                    parts=[((float(cen[0]), float(cen[1]), float(cen[2])), pquat, cshape, size)],
                    pos=position,
                    rot=rot_q,
                    motion=motion, mass=mass_val,
                    user_data=body_id, is_sensor=is_trigger,
                    category=category, mask=mask,
                    friction=friction, restitution=restitution,
                )
                return (handle if handle is not None else -1), com
            except Exception as e:
                Logger.warning(f"CulverinSolver: offset primitive failed: {e}")
                return -1, None
        try:
            size = self._shape_size(shape_type, shape_params)
            handle = self._world.create_body(
                pos=position,
                rot=rot_q,
                size=size,
                shape=culv_shape,
                motion=motion,
                mass=mass_val,
                friction=friction,
                restitution=restitution,
                category=category,
                mask=mask,
                is_sensor=is_trigger,
                user_data=body_id,
            )
            return (handle if handle is not None else -1), None
        except Exception:
            return -1, None

    def _shape_size(self, shape_type: str, shape_params: dict):
        if shape_type == "box":
            s = shape_params.get("size", [1, 1, 1])
            return (s[0] / 2.0, s[1] / 2.0, s[2] / 2.0)
        if shape_type == "sphere":
            return shape_params.get("radius", 0.5)
        if shape_type == "capsule":
            radius = shape_params.get("radius", 0.5)
            height = shape_params.get("height", 2.0)
            try:
                from core.physics.shapep import capsule_section_height
                _, hsec = capsule_section_height(float(radius), float(height))
                return (max(float(radius), 1e-4), hsec * 0.5)
            except Exception:
                return (radius, height / 2.0)
        if shape_type == "cylinder":
            radius = shape_params.get("radius", 0.5)
            height = shape_params.get("height", 1.0)
            return (radius, height / 2.0)
        if shape_type == "plane":
            n = shape_params.get("normal", [0, 1, 0])
            return (n[0], n[1], n[2], 0.0)
        return (0.5, 0.5, 0.5)

    def _create_box_approx(
        self, shaped, position, rot_q, mass_val, motion,
        friction, restitution, is_trigger, category, mask, body_id, file_path,
    ):
        try:
            mins = shaped.min(axis=0).astype(np.float64)
            maxs = shaped.max(axis=0).astype(np.float64)
        except Exception:
            return -1, None
        half = np.maximum((maxs - mins) * 0.5, 1e-4)
        off = (mins + maxs) * 0.5
        com = (float(off[0]), float(off[1]), float(off[2])) if motion != MOTION_STATIC else None
        try:
            handle = self._world.create_compound_body(
                parts=[((float(off[0]), float(off[1]), float(off[2])),
                        (0.0, 0.0, 0.0, 1.0), SHAPE_BOX,
                        (float(half[0]), float(half[1]), float(half[2])))],
                pos=position, rot=rot_q,
                motion=motion, mass=mass_val,
                user_data=body_id, is_sensor=is_trigger,
                category=category, mask=mask,
                friction=friction, restitution=restitution,
            )
            return (handle if handle is not None else -1), com
        except Exception as e:
            Logger.warning(f"CulverinSolver: box approximation failed for '{file_path}': {e}")
            return -1, None

    def _create_sphere_approx(
        self, shaped, position, rot_q, mass_val, motion,
        friction, restitution, is_trigger, category, mask, body_id, file_path,
    ):
        try:
            sc = shaped.mean(axis=0).astype(np.float64)
            radius = float(np.max(np.linalg.norm(shaped.astype(np.float64) - sc, axis=1)))
        except Exception:
            return -1, None
        radius = max(radius, 1e-4)
        com = (float(sc[0]), float(sc[1]), float(sc[2])) if motion != MOTION_STATIC else None
        try:
            handle = self._world.create_compound_body(
                parts=[((float(sc[0]), float(sc[1]), float(sc[2])),
                        (0.0, 0.0, 0.0, 1.0), SHAPE_SPHERE, radius)],
                pos=position, rot=rot_q,
                motion=motion, mass=mass_val,
                user_data=body_id, is_sensor=is_trigger,
                category=category, mask=mask,
                friction=friction, restitution=restitution,
            )
            return (handle if handle is not None else -1), com
        except Exception as e:
            Logger.warning(f"CulverinSolver: sphere approximation failed for '{file_path}': {e}")
            return -1, None

    def remove_rigid_body(self, body_id: int):
        handle = self._id_to_handle.pop(body_id, None)
        if handle is not None and self._world is not None:
            self._world.destroy_body(handle)
            self._handle_to_id.pop(handle, None)
        self._body_specs.pop(body_id, None)
        entity_id = self._body_to_entity.pop(body_id, None)
        if entity_id:
            self._entity_to_body.pop(entity_id, None)
        if body_id in self._all_body_ids:
            self._all_body_ids.remove(body_id)
        self._body_count = max(0, self._body_count - 1)

    def remove_all_bodies(self):
        if self._world is not None:
            for handle in list(self._body_handles):
                self._world.destroy_body(handle)
            for handle in list(self._soft_handles):
                try:
                    self._world.destroy_body(handle)
                except Exception:
                    pass
        self._body_handles.clear()
        self._handle_to_id.clear()
        self._id_to_handle.clear()
        self._all_body_ids.clear()
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
        self._body_count = 0
