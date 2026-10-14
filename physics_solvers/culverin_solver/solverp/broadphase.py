# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import os
from typing import Optional
import numpy as np
from core.foundation.logger import Logger

try:
    import culverin
    from culverin import (
        PhysicsWorld,
        SoftBodySharedSettings,
        SHAPE_BOX,
        SHAPE_SPHERE,
        SHAPE_CAPSULE,
        SHAPE_CYLINDER,
        SHAPE_PLANE,
        SHAPE_MESH,
        SHAPE_CONVEX_HULL,
        MOTION_STATIC,
        MOTION_KINEMATIC,
        MOTION_DYNAMIC,
        CONSTRAINT_FIXED,
        CONSTRAINT_POINT,
        CONSTRAINT_HINGE,
        CONSTRAINT_SLIDER,
        CONSTRAINT_DISTANCE,
        CONSTRAINT_CONE,
        BEND_NONE,
        BEND_DISTANCE,
        BEND_DIHEDRAL,
        euler_to_quat,
    )
    _HAS_CULVERIN = True
except ImportError:
    PhysicsWorld = None
    SoftBodySharedSettings = None
    _HAS_CULVERIN = False

    SHAPE_BOX = 0
    SHAPE_SPHERE = 1
    SHAPE_CAPSULE = 2
    SHAPE_CYLINDER = 3
    SHAPE_PLANE = 4
    SHAPE_MESH = 5
    SHAPE_CONVEX_HULL = 6
    MOTION_STATIC = 0
    MOTION_KINEMATIC = 1
    MOTION_DYNAMIC = 2
    CONSTRAINT_FIXED = 0
    CONSTRAINT_POINT = 1
    CONSTRAINT_HINGE = 2
    CONSTRAINT_SLIDER = 3
    CONSTRAINT_DISTANCE = 4
    CONSTRAINT_CONE = 5
    BEND_NONE = 0
    BEND_DISTANCE = 1
    BEND_DIHEDRAL = 2

    def euler_to_quat(roll: float, pitch: float, yaw: float):
        cx, sx = math.cos(roll / 2), math.sin(roll / 2)
        cy, sy = math.cos(pitch / 2), math.sin(pitch / 2)
        cz, sz = math.cos(yaw / 2), math.sin(yaw / 2)
        return (
            sx * cy * cz - cx * sy * sz,
            cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz,
            cx * cy * cz + sx * sy * sz,
        )


_SHAPE_TYPE_MAP = {
    "box": SHAPE_BOX,
    "sphere": SHAPE_SPHERE,
    "capsule": SHAPE_CAPSULE,
    "cylinder": SHAPE_CYLINDER,
    "plane": SHAPE_PLANE,
    "mesh": SHAPE_MESH,
}

_JOINT_TYPE_MAP = {
    "fixed": CONSTRAINT_FIXED,
    "point": CONSTRAINT_POINT,
    "point2point": CONSTRAINT_POINT,
    "hinge": CONSTRAINT_HINGE,
    "revolute": CONSTRAINT_HINGE,
    "slider": CONSTRAINT_SLIDER,
    "prismatic": CONSTRAINT_SLIDER,
    "distance": CONSTRAINT_DISTANCE,
    "cone": CONSTRAINT_CONE,
    "spherical": CONSTRAINT_CONE,
    "spring": CONSTRAINT_DISTANCE,
}

def _engine_project_root() -> str:
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng is not None and getattr(eng, "project_root", None):
            return os.path.normpath(eng.project_root)
    except Exception:
        pass
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_mesh_file(path: str) -> Optional[str]:
    if not path:
        return None
    if os.path.exists(path):
        return os.path.normpath(path)
    try:
        from core.components.physics.meshcol import _resolve_mesh_path
        resolved = _resolve_mesh_path(path)
        if resolved and os.path.exists(resolved):
            return os.path.normpath(resolved)
    except Exception:
        pass
    if os.path.isabs(path):
        root = _engine_project_root()
        if path[1:2] == ":":
            parts = path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    candidate = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(candidate):
                        return candidate
        return None
    candidate = os.path.normpath(os.path.join(_engine_project_root(), path))
    if os.path.exists(candidate):
        return candidate
    return None


def _layer_category(layer: int) -> int:
    try:
        return (1 << (int(layer) & 31)) & 0xFFFFFFFF
    except Exception:
        return 1


def _mask_value(mask: int) -> int:
    try:
        return int(mask) & 0xFFFFFFFF
    except Exception:
        return 0xFFFF


def _decimate_points(verts: np.ndarray, max_vertices: int) -> np.ndarray:
    n = len(verts)
    if n <= max_vertices or max_vertices < 4:
        return verts
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    extent = maxs - mins
    extent = np.where(extent < 1e-8, 1.0, extent)
    try:
        target_cell_vol = float(np.prod(extent)) / float(max_vertices)
    except Exception:
        return verts
    if not np.isfinite(target_cell_vol) or target_cell_vol <= 0.0:
        return verts
    cell_size = target_cell_vol ** (1.0 / 3.0)
    grid_res = np.maximum(1, np.ceil(extent / cell_size).astype(np.int32))
    indices = np.floor((verts - mins) / extent * grid_res).astype(np.int32)
    indices = np.clip(indices, 0, grid_res - 1)
    cell_ids = indices[:, 0] * grid_res[1] * grid_res[2] + indices[:, 1] * grid_res[2] + indices[:, 2]
    unique_ids, inverse = np.unique(cell_ids, return_inverse=True)
    centroids = np.zeros((len(unique_ids), 3), dtype=np.float32)
    np.add.at(centroids, inverse, verts.astype(np.float32))
    counts = np.bincount(inverse, minlength=len(unique_ids)).astype(np.float32)
    counts[counts == 0.0] = 1.0
    centroids /= counts[:, None]
    return centroids


def _unique_points(verts: np.ndarray) -> np.ndarray:
    if len(verts) > 1:
        try:
            return np.unique(np.ascontiguousarray(verts, dtype=np.float32), axis=0)
        except Exception:
            return verts
    return verts


def _clean_triangle_indices(verts: np.ndarray, indices: Optional[np.ndarray]) -> Optional[np.ndarray]:
    if indices is None:
        return None
    try:
        tris = np.asarray(indices).reshape(-1, 3).astype(np.int64)
    except Exception:
        return None
    n = len(verts)
    if len(tris) == 0 or n == 0:
        return None
    tris = tris[((tris >= 0) & (tris < n)).all(axis=1)]
    if len(tris) == 0:
        return None
    tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])]
    if len(tris) == 0:
        return None
    t = verts[tris]
    area2 = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
    try:
        ref = float(np.max(np.abs(verts)))
    except Exception:
        ref = 1.0
    if not np.isfinite(ref) or ref <= 0.0:
        ref = 1.0
    eps = max(1e-12, (ref * 1e-7) ** 2)
    tris = tris[area2 > eps]
    if len(tris) == 0:
        return None
    return np.ascontiguousarray(tris.astype(np.uint32)).reshape(-1)


def _load_mesh_geometry(path: str) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    try:
        from core.components.physics.meshcol import load_collision_geometry
        verts, indices, _ = load_collision_geometry(path)
        if verts is not None and len(verts) > 0:
            return verts, indices
    except Exception:
        pass
    return None, None


def _load_mesh_tscale(path: str) -> tuple[Optional[np.ndarray], Optional[np.ndarray], float]:
    try:
        from core.components.physics.meshcol import load_collision_geometry
        verts, indices, k = load_collision_geometry(path)
        if verts is not None and len(verts) > 0:
            return verts, indices, k
    except Exception:
        pass
    return None, None, 1.0


def _transform_scale(params_scale, import_scale: float) -> tuple[float, float, float]:
    try:
        k = float(import_scale or 1.0)
    except Exception:
        k = 1.0
    if abs(k) < 1e-9:
        k = 1.0
    try:
        return (float(params_scale[0]) / k, float(params_scale[1]) / k, float(params_scale[2]) / k)
    except Exception:
        return (1.0, 1.0, 1.0)


class BroadphaseMixin:

    def _create_mesh_collider(
        self, position, rot_q, mass_val, motion, shape_params,
        friction, restitution, is_trigger, collision_layer, collision_mask, body_id,
    ):
        file_path = shape_params.get("file", "")
        resolved = _resolve_mesh_file(file_path)
        if resolved is None:
            Logger.warning(f"CulverinSolver: mesh file not found: {file_path}")
            return -1, None

        raw_mode = shape_params.get("collision_mode", "auto")
        try:
            mode = str(raw_mode or "auto").lower()
        except Exception:
            mode = "auto"
        if mode not in ("auto", "mesh", "convex_hull", "box", "sphere"):
            Logger.warning(f"CulverinSolver: unknown collision_mode '{raw_mode}', using 'auto'")
            mode = "auto"
        try:
            max_vertices = int(shape_params.get("max_vertices", 0) or 0)
        except Exception:
            max_vertices = 0

        scale = shape_params.get("scale", [1.0, 1.0, 1.0])
        try:
            sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
        except Exception:
            sx = sy = sz = 1.0
        if not all(np.isfinite((sx, sy, sz))) or min(abs(sx), abs(sy), abs(sz)) < 1e-9:
            Logger.warning(f"CulverinSolver: degenerate scale for mesh '{file_path}'")
            return -1, None
        center = shape_params.get("center", [0.0, 0.0, 0.0])
        try:
            cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
        except Exception:
            cx = cy = cz = 0.0
        if not all(np.isfinite((cx, cy, cz))):
            cx = cy = cz = 0.0

        category = _layer_category(collision_layer)
        mask = _mask_value(collision_mask)

        if mode == "auto":
            mode = "mesh" if motion == MOTION_STATIC else "convex_hull"
        elif mode == "mesh" and motion != MOTION_STATIC:
            Logger.warning(f"CulverinSolver: concave mesh '{file_path}' requires a static body, using convex hull")
            mode = "convex_hull"

        verts, indices, import_scale = _load_mesh_tscale(resolved)
        if verts is None or len(verts) == 0:
            Logger.warning(f"CulverinSolver: could not read mesh '{file_path}'")
            return -1, None
        tx, ty, tz = _transform_scale(scale, import_scale)
        if not all(np.isfinite((tx, ty, tz))) or min(abs(tx), abs(ty), abs(tz)) < 1e-9:
            Logger.warning(f"CulverinSolver: degenerate scale for mesh '{file_path}'")
            return -1, None
        shaped = verts * np.array([tx, ty, tz], dtype=np.float32)
        if cx != 0.0 or cy != 0.0 or cz != 0.0:
            shaped = shaped + np.array([cx, cy, cz], dtype=np.float32)
        if not np.all(np.isfinite(shaped)):
            Logger.warning(f"CulverinSolver: mesh '{file_path}' contains invalid vertices")
            return -1, None

        if mode == "mesh":
            tris = _clean_triangle_indices(shaped, indices)
            if tris is None:
                Logger.warning(f"CulverinSolver: mesh '{file_path}' has no usable triangles, using convex hull")
            else:
                try:
                    buf_verts = np.ascontiguousarray(shaped, dtype=np.float32).tobytes()
                    buf_indices = np.ascontiguousarray(tris, dtype=np.uint32).tobytes()
                    handle = self._world.create_mesh_body(
                        pos=position, rot=rot_q,
                        vertices=buf_verts, indices=buf_indices,
                        user_data=body_id,
                        category=category, mask=mask,
                    )
                    return (handle if handle is not None else -1), None
                except Exception as e:
                    Logger.warning(f"CulverinSolver: create_mesh_body failed for '{file_path}': {e}")
                    return -1, None

        if mode == "box":
            return self._create_box_approx(
                shaped, position, rot_q, mass_val, motion,
                friction, restitution, is_trigger,
                category, mask, body_id, file_path,
            )

        if mode == "sphere":
            return self._create_sphere_approx(
                shaped, position, rot_q, mass_val, motion,
                friction, restitution, is_trigger,
                category, mask, body_id, file_path,
            )

        points = _unique_points(shaped)
        if max_vertices >= 4 and len(points) > max_vertices:
            points = _decimate_points(points, max_vertices)
        if len(points) < 4:
            Logger.warning(f"CulverinSolver: mesh '{file_path}' is degenerate, using box approximation")
            return self._create_box_approx(
                shaped, position, rot_q, mass_val, motion,
                friction, restitution, is_trigger,
                category, mask, body_id, file_path,
            )
        try:
            com = None
            if motion != MOTION_STATIC and len(points) > 0:
                try:
                    mean = points.astype(np.float64).mean(axis=0)
                    if np.all(np.isfinite(mean)):
                        com = (float(mean[0]), float(mean[1]), float(mean[2]))
                except Exception:
                    com = None
            buf = np.ascontiguousarray(points, dtype=np.float32).tobytes()
            handle = self._world.create_convex_hull(
                pos=position, rot=rot_q, points=buf,
                motion=motion, mass=mass_val,
                user_data=body_id, is_sensor=is_trigger,
                category=category, mask=mask,
                friction=friction, restitution=restitution,
            )
            return (handle if handle is not None else -1), com
        except Exception as e:
            Logger.warning(f"CulverinSolver: create_convex_hull failed for '{file_path}': {e}, using box approximation")
            return self._create_box_approx(
                shaped, position, rot_q, mass_val, motion,
                friction, restitution, is_trigger,
                category, mask, body_id, file_path,
            )
