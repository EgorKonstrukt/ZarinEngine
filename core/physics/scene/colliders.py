# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
from typing import Optional
from core.foundation.logger import Logger
from core.physics.shapep import find_shape_info, find_shapes_info, make_shape_key, make_shapes_key
from core.physics.scene.events import create_soft_body_in_solver


class CollidersMixin:
    def _find_shape(self, entity, transform=None) -> Optional[dict]:
        return find_shape_info(entity, transform)

    def _find_shapes(self, entity, transform=None) -> list[dict]:
        return find_shapes_info(entity, transform)

    def _make_shape_key(self, entity, shape_info: dict) -> tuple:
        return make_shape_key(entity, shape_info)

    def register_box_collider(self, entity_id: str, size=(1.0, 1.0, 1.0), center=(0.0, 0.0, 0.0), position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), mass=0.0, friction=0.6, restitution=0.0, is_trigger=False, is_kinematic=False, layer=0, mask=0xFFFF) -> int:
        return self._solver.create_rigid_body(entity_id=entity_id, shape_type="box", shape_params={"size": list(size), "center": list(center)}, position=position, rotation=rotation, mass=mass, friction=friction, restitution=restitution, is_trigger=is_trigger, is_kinematic=is_kinematic, collision_layer=layer, collision_mask=mask)

    def register_sphere_collider(self, entity_id: str, radius=0.5, center=(0.0, 0.0, 0.0), position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), mass=0.0, friction=0.6, restitution=0.0, is_trigger=False, is_kinematic=False, layer=0, mask=0xFFFF) -> int:
        return self._solver.create_rigid_body(entity_id=entity_id, shape_type="sphere", shape_params={"radius": float(radius), "center": list(center)}, position=position, rotation=rotation, mass=mass, friction=friction, restitution=restitution, is_trigger=is_trigger, is_kinematic=is_kinematic, collision_layer=layer, collision_mask=mask)

    def register_capsule_collider(self, entity_id: str, radius=0.5, height=2.0, center=(0.0, 0.0, 0.0), direction=1, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), mass=1.0, friction=0.6, restitution=0.0, is_trigger=False, is_kinematic=False, layer=0, mask=0xFFFF) -> int:
        return self._solver.create_rigid_body(entity_id=entity_id, shape_type="capsule", shape_params={"radius": float(radius), "height": float(height), "center": list(center), "direction": int(direction)}, position=position, rotation=rotation, mass=mass, friction=friction, restitution=restitution, is_trigger=is_trigger, is_kinematic=is_kinematic, collision_layer=layer, collision_mask=mask)

    def register_mesh_collider(self, entity_id: str, mesh_path="", collision_mode="auto", max_vertices=2000, scale=(1.0, 1.0, 1.0), center=(0.0, 0.0, 0.0), position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), mass=0.0, friction=0.6, restitution=0.0, is_trigger=False, is_kinematic=False, layer=0, mask=0xFFFF) -> int:
        return self._solver.create_rigid_body(entity_id=entity_id, shape_type="mesh", shape_params={"file": str(mesh_path), "collision_mode": str(collision_mode), "max_vertices": int(max_vertices), "scale": list(scale), "center": list(center)}, position=position, rotation=rotation, mass=mass, friction=friction, restitution=restitution, is_trigger=is_trigger, is_kinematic=is_kinematic, collision_layer=layer, collision_mask=mask)

    def register_character_collider(self, entity_id: str, position=(0.0, 0.0, 0.0), height=1.8, radius=0.4, step_height=0.4, max_slope=45.0):
        try:
            return self._solver.create_character(pos=tuple(position), height=float(height), radius=float(radius), step_height=float(step_height), max_slope=float(max_slope))
        except Exception:
            return self._solver.create_rigid_body(entity_id=entity_id, shape_type="capsule", shape_params={"radius": float(radius), "height": float(height), "center": [0.0, 0.0, 0.0], "direction": 1}, position=tuple(position), rotation=(0.0, 0.0, 0.0), mass=1.0, friction=0.6, restitution=0.0, is_trigger=False, is_kinematic=False, collision_layer=0, collision_mask=0xFFFF)

    @staticmethod
    def _soft_sig(entity, soft, tr) -> Optional[tuple]:
        try:
            from core.components.rendering.renderers.mesh_filter import MeshFilter
            mf = entity.get_component(MeshFilter)
            mesh_path = (mf.mesh_path or "") if mf else ""
            bend = soft.bend_mode.value if hasattr(soft.bend_mode, "value") else soft.bend_mode
            pin = soft.pin_mode.value if hasattr(soft.pin_mode, "value") else soft.pin_mode
            return (
                mesh_path, bool(soft.enabled),
                float(soft.mass), float(soft.compliance), str(bend), float(soft.pressure),
                float(soft.damping), int(soft.iterations), float(soft.gravity_scale),
                float(soft.vertex_radius), float(soft.max_velocity), str(pin), float(soft.pin_fraction),
                int(soft.max_vertices), bool(soft.double_sided), bool(soft.update_com),
                int(soft.layer), int(soft.mask),
                float(tr.local_scale.x), float(tr.local_scale.y), float(tr.local_scale.z),
            )
        except Exception:
            return None

    @staticmethod
    def _soft_applied_pose(tr):
        try:
            p = tr._local_pos
            q = tr._local_rot
            s = tr._local_scale
            return (float(p._x), float(p._y), float(p._z),
                    float(q._x), float(q._y), float(q._z), float(q._w),
                    float(s._x), float(s._y), float(s._z))
        except Exception:
            return None

    @staticmethod
    def _soft_pin_active(soft) -> bool:
        try:
            pm = getattr(soft, "pin_mode", None)
            v = pm.value if hasattr(pm, "value") else pm
            return str(v or "none").lower() in ("top", "bottom")
        except Exception:
            return False

    def _soft_rebuild_for_teleport(self, entity, soft, tr) -> bool:
        try:
            tr._physics_dirty = False
        except Exception:
            pass
        self._remove_entity_soft(entity.id)
        ok = self._build_entity_soft(entity, soft, tr)
        if not ok:
            return False
        try:
            self._cached_soft_sig[entity.id] = self._soft_sig(entity, soft, tr)
        except Exception:
            pass
        try:
            pose = self._soft_applied_pose(tr)
            if pose is not None:
                soft._soft_applied_pose = pose
        except Exception:
            pass
        return True

    def _soft_check_user_teleport(self, entity, soft, tr) -> bool:
        try:
            if not getattr(tr, "_physics_dirty", False):
                return False
        except Exception:
            return False
        try:
            prev = getattr(soft, "_soft_applied_pose", None)
        except Exception:
            prev = None
        if prev is None:
            return self._soft_rebuild_for_teleport(entity, soft, tr)
        cur = self._soft_applied_pose(tr)
        if cur is None:
            try:
                tr._physics_dirty = False
            except Exception:
                pass
            return False
        try:
            dp = abs(cur[0] - prev[0]) + abs(cur[1] - prev[1]) + abs(cur[2] - prev[2])
            dq = 1.0 - abs(cur[3] * prev[3] + cur[4] * prev[4] + cur[5] * prev[5] + cur[6] * prev[6])
            ds = abs(cur[7] - prev[7]) + abs(cur[8] - prev[8]) + abs(cur[9] - prev[9])
        except Exception:
            return False
        if dp > 1e-6 or dq > 1e-8 or ds > 1e-9:
            return self._soft_rebuild_for_teleport(entity, soft, tr)
        try:
            tr._physics_dirty = False
        except Exception:
            pass
        return False

    def _soft_apply_com(self, entity, soft, tr, sid=None, com=None) -> bool:
        try:
            if not bool(getattr(soft, "update_com", True)):
                return False
        except Exception:
            return False
        if self._soft_pin_active(soft):
            return False
        if com is None:
            if sid is None:
                return False
            try:
                com = self._solver.get_soft_body_com(sid)
            except Exception:
                return False
        try:
            pos, rot = com
            cx, cy, cz = float(pos[0]), float(pos[1]), float(pos[2])
            qx, qy, qz, qw = float(rot[0]), float(rot[1]), float(rot[2]), float(rot[3])
        except Exception:
            return False
        if not all(map(lambda v: v == v and abs(v) != float("inf"), (cx, cy, cz, qx, qy, qz, qw))):
            return False
        try:
            from core.maths.math3d import Vec3, Quat
            n = qx * qx + qy * qy + qz * qz + qw * qw
            if n < 1e-20:
                return False
            inv = 1.0 / (n ** 0.5)
            wq = Quat(qx * inv, qy * inv, qz * inv, qw * inv)
            parent = entity._parent if hasattr(entity, "_parent") else None
            if parent is None and hasattr(entity, "parent"):
                try:
                    parent = entity.parent
                except Exception:
                    parent = None
            if parent is not None:
                try:
                    pt = parent.transform
                except Exception:
                    pt = None
                if pt is not None:
                    try:
                        pt._update_world_matrix()
                        pwq = pt._world_matrix.decompose()[1]
                        pwc = pwq.conjugate().normalized()
                        lq = (pwc * wq).normalized()
                    except Exception:
                        return False
                    try:
                        tr.position = Vec3(cx, cy, cz)
                    except Exception:
                        return False
                    try:
                        tr._local_rot = lq
                        tr._mark_dirty()
                    except Exception:
                        pass
                else:
                    try:
                        tr.position = Vec3(cx, cy, cz)
                    except Exception:
                        return False
                    try:
                        tr._local_rot = wq
                        tr._mark_dirty()
                    except Exception:
                        pass
            else:
                try:
                    tr._local_pos = Vec3(cx, cy, cz)
                    tr._local_rot = wq
                    tr._mark_dirty()
                except Exception:
                    return False
            try:
                tr._physics_dirty = False
            except Exception:
                pass
            try:
                pose = self._soft_applied_pose(tr)
                if pose is not None:
                    soft._soft_applied_pose = pose
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _build_entity_soft(self, entity, soft, tr) -> bool:
        try:
            from core.components.rendering.renderers.mesh_filter import MeshFilter
            from core.components.physics.meshcol import load_collision_geometry
            mf = entity.get_component(MeshFilter)
            mesh_path = (mf.mesh_path or "") if mf else ""
            if not mesh_path:
                Logger.warning(f"[SoftBody] '{getattr(entity, 'name', entity.id)}' needs a MeshFilter mesh")
                return False
            Logger.info(f"[SoftBody] '{getattr(entity, 'name', entity.id)}' loading mesh '{mesh_path}'")
            verts, indices, _ = load_collision_geometry(mesh_path)
            if verts is None or indices is None or len(verts) < 3:
                Logger.warning(f"[SoftBody] '{getattr(entity, 'name', entity.id)}' could not read mesh '{mesh_path}' (verts={verts is not None}, indices={indices is not None})")
                return False
            Logger.info(f"[SoftBody] '{getattr(entity, 'name', entity.id)}' loaded {len(verts)} verts, {len(indices)} indices")
            s = tr.local_scale
            euler = tr.local_euler_angles
            bend = soft.bend_mode.value if hasattr(soft.bend_mode, "value") else str(soft.bend_mode)
            pin = soft.pin_mode.value if hasattr(soft.pin_mode, "value") else str(soft.pin_mode)
            params = {
                "mass": soft.mass, "compliance": soft.compliance, "bend_mode": bend,
                "pressure": soft.pressure, "damping": soft.damping, "iterations": soft.iterations,
                "gravity_factor": soft.gravity_scale, "friction": soft.material_friction,
                "restitution": soft.material_bounciness, "vertex_radius": soft.vertex_radius,
                "max_velocity": soft.max_velocity, "max_vertices": soft.max_vertices,
                "pin_mode": pin, "pin_fraction": soft.pin_fraction,
                "double_sided": soft.double_sided, "update_com": soft.update_com,
                "layer": soft.layer, "mask": soft.mask,
            }
            sid, n, sverts, sfaces = create_soft_body_in_solver(
                self._solver,
                vertices=verts,
                indices=indices,
                scale_xyz=(s.x, s.y, s.z),
                pos_xyz=(tr.local_position.x, tr.local_position.y, tr.local_position.z),
                euler_rad_xyz=(math.radians(euler.x), math.radians(euler.y), math.radians(euler.z)),
                params=params,
                entity_id=entity.id,
            )
        except Exception as e:
            Logger.warning(f"[SoftBody] '{getattr(entity, 'name', entity.id)}' creation exception: {e}")
            return False
        if sid is None or n <= 0:
            return False
        self._entity_to_soft[entity.id] = sid
        self._body_to_entity[sid] = entity.id
        try:
            if sverts is not None and len(sverts) >= 3:
                soft._soft_verts = np.ascontiguousarray(sverts, dtype=np.float32)
            if sfaces is not None and len(sfaces) >= 3:
                soft._soft_faces = np.ascontiguousarray(sfaces, dtype=np.int64)
        except Exception:
            pass
        try:
            Logger.info(f"SoftBody on '{getattr(entity, 'name', entity.id)}' simulating {n} vertices")
        except Exception:
            pass
        try:
            soft._soft_id = sid
        except Exception:
            pass
        return True
