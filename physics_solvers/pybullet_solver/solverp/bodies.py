# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
import os
import numpy as np
from core.foundation.logger import Logger
from physics_solvers.pybullet_solver.solverp.lazy import p, _convex_hull_shape, _load_mesh_tscale, _transform_scale

class _BodiesMixin:
    def _make_shape(self, shape_type: str, shape_params: dict, is_static: bool = True) -> int:
        cid = self._cid()
        if shape_type == "box":
            size = shape_params.get("size", [1, 1, 1])
            center = shape_params.get("center", [0, 0, 0])
            half_extents = [s / 2.0 for s in size]
            return p.createCollisionShape(
                p.GEOM_BOX,
                halfExtents=half_extents,
                collisionFramePosition=center,
                physicsClientId=cid,
            )
        elif shape_type == "sphere":
            radius = shape_params.get("radius", 0.5)
            center = shape_params.get("center", [0, 0, 0])
            return p.createCollisionShape(
                p.GEOM_SPHERE,
                radius=radius,
                collisionFramePosition=center,
                physicsClientId=cid,
            )
        elif shape_type == "capsule":
            radius = shape_params.get("radius", 0.5)
            height = shape_params.get("height", 2.0)
            center = shape_params.get("center", [0, 0, 0])
            try:
                direction = int(shape_params.get("direction", 1))
            except Exception:
                direction = 1
            try:
                from core.physics.shapep import capsule_section_height, _PYBULLET_CAPSULE_EULER
                r, hsec = capsule_section_height(float(radius), float(height))
                frame_rot = p.getQuaternionFromEuler(_PYBULLET_CAPSULE_EULER.get(direction, (0.0, 0.0, 0.0)))
            except Exception:
                r, hsec, frame_rot = radius, height, (0.0, 0.0, 0.0, 1.0)
            return p.createCollisionShape(
                p.GEOM_CAPSULE,
                radius=r,
                height=hsec,
                collisionFramePosition=center,
                collisionFrameOrientation=frame_rot,
                physicsClientId=cid,
            )
        elif shape_type == "cylinder":
            radius = shape_params.get("radius", 0.5)
            height = shape_params.get("height", 1.0)
            center = shape_params.get("center", [0, 0, 0])
            return p.createCollisionShape(
                p.GEOM_CYLINDER,
                radius=radius,
                height=height,
                collisionFramePosition=center,
                physicsClientId=cid,
            )
        elif shape_type == "plane":
            return p.createCollisionShape(
                p.GEOM_PLANE,
                planeNormal=shape_params.get("normal", [0, 1, 0]),
                physicsClientId=cid,
            )
        elif shape_type == "mesh":
            file_path = shape_params.get("file", "")
            resolved = file_path
            if not os.path.isabs(resolved):
                proj_root = os.path.normpath(
                    os.path.join(os.path.dirname(__file__), "..", "..")
                )
                candidate = os.path.normpath(os.path.join(proj_root, resolved))
                if os.path.exists(candidate):
                    resolved = candidate
            if not os.path.exists(resolved):
                try:
                    from core.components.physics.meshcol import _resolve_mesh_path
                    alt = _resolve_mesh_path(file_path)
                    if alt and os.path.exists(alt):
                        resolved = alt
                except Exception:
                    pass
            if not os.path.exists(resolved):
                Logger.warning(f"MeshCollider: file not found: {file_path}")
                return -1

            raw_mode = shape_params.get("collision_mode", "auto")
            try:
                collision_mode = str(raw_mode or "auto").lower()
            except Exception:
                collision_mode = "auto"
            if collision_mode not in ("auto", "mesh", "convex_hull", "box", "sphere"):
                Logger.warning(f"MeshCollider: unknown collision_mode '{raw_mode}', using 'auto'")
                collision_mode = "auto"
            try:
                max_vertices = int(shape_params.get("max_vertices", 0) or 0)
            except Exception:
                max_vertices = 0
            scale = shape_params.get("scale", [1, 1, 1])
            try:
                sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
            except Exception:
                sx = sy = sz = 1.0
            center = shape_params.get("center", [0, 0, 0])
            try:
                cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
            except Exception:
                cx = cy = cz = 0.0
            try:
                from core.components.physics.meshcol import _import_sig_of
                meta_sig = _import_sig_of(file_path)
            except Exception:
                meta_sig = "-"
            scale_t = (sx, sy, sz)
            center_t = (cx, cy, cz)
            cache_key = (resolved, scale_t, center_t, collision_mode, max_vertices, meta_sig)
            if cache_key in self._mesh_shape_cache:
                return self._mesh_shape_cache[cache_key]

            if collision_mode == "auto":
                collision_mode = "mesh" if is_static else "convex_hull"
            elif collision_mode == "mesh" and not is_static:
                Logger.warning(f"MeshCollider: concave mesh '{file_path}' requires a static body, using convex hull")
                collision_mode = "convex_hull"

            verts, indices, import_scale = _load_mesh_tscale(resolved)
            if verts is None or len(verts) == 0:
                Logger.warning(f"MeshCollider: could not read mesh '{file_path}'")
                return -1
            tx, ty, tz = _transform_scale(scale, import_scale)
            if not all(np.isfinite((tx, ty, tz))) or min(abs(tx), abs(ty), abs(tz)) < 1e-9:
                Logger.warning(f"MeshCollider: degenerate scale for '{file_path}'")
                return -1
            sv = verts * np.array([tx, ty, tz], dtype=np.float32)

            if collision_mode == "convex_hull":
                shape_id = _convex_hull_shape(cid, sv, max_vertices, self._mesh_shape_cache, cache_key)
                if shape_id >= 0:
                    return shape_id
                Logger.warning(f"MeshCollider: convex hull failed for '{file_path}'")
                return -1

            if collision_mode == "box":
                mins = sv.min(axis=0)
                maxs = sv.max(axis=0)
                half = np.maximum((maxs - mins) * 0.5, 1e-4).tolist()
                frame = ((mins + maxs) * 0.5 + np.array([cx, cy, cz], dtype=np.float32)).tolist()
                try:
                    shape_id = p.createCollisionShape(
                        p.GEOM_BOX,
                        halfExtents=half,
                        collisionFramePosition=frame,
                        physicsClientId=cid,
                    )
                    self._mesh_shape_cache[cache_key] = shape_id
                    return shape_id
                except Exception as e:
                    Logger.warning(f"MeshCollider box approximation failed for '{file_path}': {e}")
                    return -1

            if collision_mode == "sphere":
                bc = sv.mean(axis=0)
                radius = max(float(np.max(np.linalg.norm(sv - bc, axis=1))), 1e-4)
                frame = (bc + np.array([cx, cy, cz], dtype=np.float32)).tolist()
                try:
                    shape_id = p.createCollisionShape(
                        p.GEOM_SPHERE,
                        radius=radius,
                        collisionFramePosition=frame,
                        physicsClientId=cid,
                    )
                    self._mesh_shape_cache[cache_key] = shape_id
                    return shape_id
                except Exception as e:
                    Logger.warning(f"MeshCollider sphere approximation failed for '{file_path}': {e}")
                    return -1

            frame = [cx, cy, cz]
            concave_flags = getattr(p, "GEOM_FORCE_CONCAVE_TRIMESH", 0)
            if indices is not None and len(indices) >= 3 and len(indices) % 3 == 0:
                try:
                    shape_id = p.createCollisionShape(
                        p.GEOM_MESH,
                        vertices=sv.tolist(),
                        indices=indices.reshape(-1).tolist(),
                        collisionFramePosition=frame,
                        flags=concave_flags,
                        physicsClientId=cid,
                    )
                    self._mesh_shape_cache[cache_key] = shape_id
                    return shape_id
                except Exception as e:
                    Logger.warning(f"MeshCollider: failed to build triangle mesh for '{file_path}': {e}")
                    return -1
            if indices is not None and len(indices) % 3 != 0:
                Logger.warning(f"MeshCollider: mesh '{file_path}' has non-triangulated faces, using convex hull")
                shape_id = _convex_hull_shape(cid, sv, max_vertices, self._mesh_shape_cache, cache_key)
                if shape_id < 0:
                    Logger.warning(f"MeshCollider: convex hull failed for '{file_path}'")
                return shape_id
            Logger.warning(f"MeshCollider: mesh '{file_path}' has no triangles for collision")
            return -1
        elif shape_type == "heightfield":
            size = shape_params.get("size", [1000.0, 60.0, 1000.0])
            resolution = int(shape_params.get("resolution", 0))
            height_data = shape_params.get("height_data")
            if height_data is None or resolution < 2:
                Logger.warning("TerrainCollider: no height data available for physics")
                return -1
            try:
                arr = np.asarray(height_data, dtype=np.float32)
                if arr.ndim == 2:
                    rows = arr.shape[0]
                    cols = arr.shape[1]
                    flat = arr.flatten().astype(np.float32)
                else:
                    rows = cols = int(np.sqrt(len(arr)))
                    flat = arr.astype(np.float32)
                hf_rows = rows
                hf_cols = cols
                sx = size[0] / max(1, cols - 1)
                sz = size[2] / max(1, rows - 1)
                shape_id = p.createCollisionShape(
                    p.GEOM_HEIGHTFIELD,
                    numHeightfieldRows=hf_rows,
                    numHeightfieldColumns=hf_cols,
                    heightfieldData=flat.tolist(),
                    heightfieldScaling=[sx, sz, 1.0],
                    physicsClientId=cid,
                )
                return shape_id
            except Exception as e:
                Logger.warning(f"TerrainCollider: heightfield shape failed: {e}")
                return -1
        return -1

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
        cid = self._cid()
        is_static = (mass <= 0.0 or is_trigger or is_kinematic)
        shape_id = self._make_shape(shape_type, shape_params, is_static=is_static)
        if shape_id < 0:
            return -1

        visual_id = -1
        try:
            if shape_type == "box":
                size = shape_params.get("size", [1, 1, 1])
                half = [s / 2.0 for s in size]
                center = shape_params.get("center", [0, 0, 0])
                visual_id = p.createVisualShape(
                    p.GEOM_BOX,
                    halfExtents=half,
                    visualFramePosition=center,
                    rgbaColor=[0.6, 0.6, 0.6, 1.0],
                    physicsClientId=cid,
                )
            elif shape_type == "sphere":
                radius = shape_params.get("radius", 0.5)
                center = shape_params.get("center", [0, 0, 0])
                visual_id = p.createVisualShape(
                    p.GEOM_SPHERE,
                    radius=radius,
                    visualFramePosition=center,
                    rgbaColor=[0.6, 0.6, 0.6, 1.0],
                    physicsClientId=cid,
                )
            elif shape_type == "capsule":
                radius = shape_params.get("radius", 0.5)
                height = shape_params.get("height", 2.0)
                center = shape_params.get("center", [0, 0, 0])
                visual_id = p.createVisualShape(
                    p.GEOM_CAPSULE,
                    radius=radius,
                    height=height,
                    visualFramePosition=center,
                    rgbaColor=[0.6, 0.6, 0.6, 1.0],
                    physicsClientId=cid,
                )
            elif shape_type == "cylinder":
                radius = shape_params.get("radius", 0.5)
                height = shape_params.get("height", 1.0)
                center = shape_params.get("center", [0, 0, 0])
                visual_id = p.createVisualShape(
                    p.GEOM_CYLINDER,
                    radius=radius,
                    length=height,
                    visualFramePosition=center,
                    rgbaColor=[0.6, 0.6, 0.6, 1.0],
                    physicsClientId=cid,
                )
        except Exception:
            pass

        if mass <= 0.0 or is_trigger or is_kinematic:
            mass = 0.0

        base_visual = visual_id if visual_id >= 0 else -1
        body_id = p.createMultiBody(
            baseMass=mass,
            baseCollisionShapeIndex=shape_id,
            baseVisualShapeIndex=base_visual,
            basePosition=position,
            baseOrientation=p.getQuaternionFromEuler(rotation),
            physicsClientId=cid,
        )

        if body_id >= 0:
            self._body_count += 1
            self._all_body_ids.append(body_id)
            self._body_collision_info[body_id] = (collision_layer, collision_mask)
            p.changeDynamics(
                body_id,
                -1,
                lateralFriction=friction,
                restitution=restitution,
                activationState=1,
                physicsClientId=cid,
            )
            p.addUserData(body_id, "entity_id", entity_id, physicsClientId=cid)
            self._apply_collision_filters(body_id)

        return body_id

    def set_body_transform(
        self,
        body_id: int,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float],
    ):
        cid = self._cid()
        quat = p.getQuaternionFromEuler(rotation)
        p.resetBasePositionAndOrientation(body_id, position, quat, physicsClientId=cid)

    def set_body_transform_quat(
        self,
        body_id: int,
        position: tuple[float, float, float],
        quat: tuple[float, float, float, float],
    ):
        cid = self._cid()
        p.resetBasePositionAndOrientation(body_id, position, quat, physicsClientId=cid)

    def get_body_transform(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        cid = self._cid()
        pos, quat = p.getBasePositionAndOrientation(body_id, physicsClientId=cid)
        euler = p.getEulerFromQuaternion(quat)
        return (pos[0], pos[1], pos[2]), (euler[0], euler[1], euler[2])

    def get_body_transform_quat(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        cid = self._cid()
        pos, quat = p.getBasePositionAndOrientation(body_id, physicsClientId=cid)
        return (pos[0], pos[1], pos[2]), (quat[0], quat[1], quat[2], quat[3])

    def apply_force(
        self, body_id: int, force: tuple[float, float, float], local: bool = False
    ):
        cid = self._cid()
        flags = p.LINK_FRAME if local else p.WORLD_FRAME
        p.applyExternalForce(body_id, -1, force, (0, 0, 0), flags, physicsClientId=cid)

    def apply_torque(self, body_id: int, torque: tuple[float, float, float]):
        cid = self._cid()
        p.applyExternalTorque(
            body_id, -1, torque, p.WORLD_FRAME, physicsClientId=cid
        )

    def apply_impulse(
        self, body_id: int, impulse: tuple[float, float, float], local: bool = False
    ):
        cid = self._cid()
        flags = p.LINK_FRAME if local else p.WORLD_FRAME
        p.applyExternalForce(body_id, -1, impulse, (0, 0, 0), flags, physicsClientId=cid)

    def set_velocities(
        self, body_id: int,
        linear: Optional[tuple[float, float, float]] = None,
        angular: Optional[tuple[float, float, float]] = None,
    ):
        cid = self._cid()
        kwargs = {"physicsClientId": cid}
        if linear is not None:
            kwargs["linearVelocity"] = linear
        if angular is not None:
            kwargs["angularVelocity"] = angular
        p.resetBaseVelocity(body_id, **kwargs)

    def get_velocities(
        self, body_id: int
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        cid = self._cid()
        vel, ang = p.getBaseVelocity(body_id, physicsClientId=cid)
        return (vel[0], vel[1], vel[2]), (ang[0], ang[1], ang[2])

    def set_velocity(self, body_id: int, velocity: tuple[float, float, float]):
        self.set_velocities(body_id, linear=velocity)

    def get_velocity(self, body_id: int) -> tuple[float, float, float]:
        return self.get_velocities(body_id)[0]

    def set_angular_velocity(
        self, body_id: int, velocity: tuple[float, float, float]
    ):
        self.set_velocities(body_id, angular=velocity)

    def get_angular_velocity(
        self, body_id: int
    ) -> tuple[float, float, float]:
        return self.get_velocities(body_id)[1]
