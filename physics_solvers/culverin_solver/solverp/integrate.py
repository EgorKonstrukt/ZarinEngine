# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from typing import Optional
import numpy as np
from core.foundation.logger import Logger
from physics_solvers.culverin_solver.solverp.broadphase import SoftBodySharedSettings, BEND_NONE, BEND_DISTANCE, BEND_DIHEDRAL, euler_to_quat, _layer_category, _mask_value

_SOFT_SETTINGS_CACHE: dict = {}


def _soft_digest(verts: np.ndarray, faces: np.ndarray) -> tuple:
    try:
        v = np.ascontiguousarray(verts, dtype=np.float32)
        f = np.ascontiguousarray(faces, dtype=np.uint32)
        return (v.shape, f.shape, int(v.nbytes + f.nbytes), float(np.sum(v)) + float(np.sum(f)))
    except Exception:
        return (0, 0, 0, 0.0)


def _compact_soft_mesh(verts: np.ndarray, faces: np.ndarray, max_vertices: int):
    try:
        tris = np.asarray(faces).reshape(-1, 3).astype(np.int64)
    except Exception:
        return None, None
    try:
        n = len(verts)
    except Exception:
        return None, None
    if len(tris) == 0 or n == 0:
        return None, None
    tris = tris[((tris >= 0) & (tris < n)).all(axis=1)]
    tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])]
    if len(tris) == 0:
        return None, None
    try:
        maxv = int(max_vertices or 0)
    except Exception:
        maxv = 0
    if maxv < 4:
        return _finalize_compact(verts, tris)
    if _unique_count(tris) <= maxv:
        return _finalize_compact(verts, tris)
    try:
        v = np.ascontiguousarray(np.asarray(verts, dtype=np.float32).reshape(-1, 3))
    except Exception:
        return None, None
    try:
        mins = v.min(axis=0).astype(np.float64)
        maxs = v.max(axis=0).astype(np.float64)
    except Exception:
        return None, None
    extent = maxs - mins
    extent = np.where(np.isfinite(extent) & (extent > 1e-9), extent, 1.0)
    try:
        vol = float(np.prod(extent))
    except Exception:
        vol = 1.0
    if not np.isfinite(vol) or vol <= 0.0:
        vol = 1.0
    base_cell = (vol / float(maxv)) ** (1.0 / 3.0)
    if not np.isfinite(base_cell) or base_cell <= 0.0:
        base_cell = 1.0
    cell = base_cell
    best = None
    for _ in range(12):
        try:
            rel = (v.astype(np.float64) - mins) / cell
            ijk = np.floor(rel).astype(np.int64)
            lo = ijk.min(axis=0)
            ijk = ijk - lo
            key = (ijk[:, 0].astype(np.int64) * np.int64(73856093)) ^ (ijk[:, 1].astype(np.int64) * np.int64(19349663)) ^ (ijk[:, 2].astype(np.int64) * np.int64(83492791))
            ukey, rep = np.unique(key, return_inverse=True)
            nrep = int(len(ukey))
        except Exception:
            return None, None
        if nrep > maxv:
            try:
                grow = (float(nrep) / float(maxv)) ** (1.0 / 3.0)
            except Exception:
                grow = 2.0
            if not np.isfinite(grow) or grow < 1.05:
                grow = 1.5
            cell = cell * grow
            continue
        try:
            sums = np.zeros((nrep, 3), dtype=np.float64)
            np.add.at(sums, rep, v.astype(np.float64))
            counts = np.bincount(rep, minlength=nrep).astype(np.float64)
            counts[counts <= 0.0] = 1.0
            cents = (sums / counts[:, None]).astype(np.float32)
            mapped = rep[tris]
            keep = (mapped[:, 0] != mapped[:, 1]) & (mapped[:, 1] != mapped[:, 2]) & (mapped[:, 2] != mapped[:, 0])
            kt = mapped[keep]
            if len(kt) == 0:
                cell = cell * 0.5
                best = None
                continue
            out = _finalize_compact(cents, kt)
            if out[0] is None:
                cell = cell * 0.5
                continue
            if len(out[0]) <= maxv:
                return out
            best = out
            cell = cell * 0.85
        except Exception:
            return None, None
    if best is not None:
        return best
    return _finalize_compact(verts, tris[:max(1, maxv // 2)])


def _unique_count(tris) -> int:
    try:
        return int(np.unique(tris.reshape(-1)).size)
    except Exception:
        return 0


def _finalize_compact(verts: np.ndarray, tris: np.ndarray):
    try:
        used, remap = np.unique(tris.reshape(-1), return_inverse=True)
    except Exception:
        return None, None
    try:
        out_verts = np.ascontiguousarray(np.asarray(verts)[used].astype(np.float32))
        out_faces = np.ascontiguousarray(remap.reshape(-1, 3).astype(np.uint32))
    except Exception:
        return None, None
    if len(out_verts) < 3 or len(out_faces) == 0:
        return None, None
    return out_verts, out_faces


def _soft_vertex_precision() -> tuple[bool, object]:
    try:
        import culverin as _culv
        if bool(getattr(_culv, "USE_DOUBLE_PRECISION", False)):
            return True, np.float64
    except Exception:
        pass
    return False, np.float32


def _quat_to_euler(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    qx, qy, qz, qw = q
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2.0 * (qw * qy - qz * qx)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return (roll, pitch, yaw)


def _rotate_vector_by_quat(
    v: tuple[float, float, float],
    q: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    vx, vy, vz = v
    qw, qx, qy, qz = q
    uv_x = qy * vz - qz * vy
    uv_y = qz * vx - qx * vz
    uv_z = qx * vy - qy * vx
    uv2_x = qy * uv_z - qz * uv_y
    uv2_y = qz * uv_x - qx * uv_z
    uv2_z = qx * uv_y - qy * uv_x
    return (
        vx + 2.0 * (qw * uv_x + uv2_x),
        vy + 2.0 * (qw * uv_y + uv2_y),
        vz + 2.0 * (qw * uv_z + uv2_z),
    )


def _rot_vec_by_quat_xyzw(
    v: tuple[float, float, float],
    q: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    vx, vy, vz = v
    qx, qy, qz, qw = q
    uv_x = qy * vz - qz * vy
    uv_y = qz * vx - qx * vz
    uv_z = qx * vy - qy * vx
    uv2_x = qy * uv_z - qz * uv_y
    uv2_y = qz * uv_x - qx * uv_z
    uv2_z = qx * uv_y - qy * uv_x
    return (
        vx + 2.0 * (qw * uv_x + uv2_x),
        vy + 2.0 * (qw * uv_y + uv2_y),
        vz + 2.0 * (qw * uv_z + uv2_z),
    )


def _shifted_pos(
    position: tuple[float, float, float],
    rot_q: tuple[float, float, float, float],
    com: Optional[tuple[float, float, float]],
    sign: float,
) -> tuple[float, float, float]:
    if com is None:
        return position
    try:
        ox, oy, oz = _rot_vec_by_quat_xyzw((float(com[0]), float(com[1]), float(com[2])), rot_q)
    except Exception:
        return position
    return (position[0] + sign * ox, position[1] + sign * oy, position[2] + sign * oz)


class IntegrateMixin:

    def _resolve_soft_id(self, soft_id: int) -> Optional[int]:
        try:
            return self._soft_id_to_handle.get(int(soft_id))
        except Exception:
            return None

    def create_soft_body(
        self,
        entity_id: str,
        vertices,
        indices,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float],
        mass: float = 1.0,
        compliance: float = 0.001,
        bend_mode: int = 1,
        pressure: float = 0.0,
        damping: float = 0.1,
        iterations: int = 10,
        gravity_factor: float = 1.0,
        friction: float = 0.2,
        restitution: float = 0.0,
        vertex_radius: float = 0.05,
        max_velocity: float = 500.0,
        max_vertices: int = 0,
        pin_mode: str = "none",
        pin_fraction: float = 0.1,
        double_sided: bool = True,
        update_com: bool = True,
        collision_layer: int = 0,
        collision_mask: int = 0xFFFF,
    ) -> int:
        if self._world is None or SoftBodySharedSettings is None:
            return -1
        try:
            verts = np.ascontiguousarray(np.asarray(vertices, dtype=np.float32).reshape(-1, 3))
            faces = np.ascontiguousarray(np.asarray(indices, dtype=np.uint32).reshape(-1))
        except Exception:
            return -1
        if len(verts) < 3 or faces.size < 3 or faces.size % 3 != 0:
            return -1
        if not np.all(np.isfinite(verts)):
            return -1
        try:
            mv = int(max_vertices or 0)
        except Exception:
            mv = 0
        if mv >= 4:
            verts, faces = _compact_soft_mesh(verts, faces, mv)
            if verts is None or faces is None:
                return -1
        try:
            n = len(verts)
            total_mass = max(float(mass), 1e-6)
            pinned_set: set[int] = set()
            try:
                pmode = str(pin_mode or "none").lower()
            except Exception:
                pmode = "none"
            if pmode in ("top", "bottom"):
                try:
                    frac = max(0.0, min(0.5, float(pin_fraction)))
                except Exception:
                    frac = 0.1
                ys = verts[:, 1]
                lo, hi = float(ys.min()), float(ys.max())
                band = (hi - lo) * frac
                if pmode == "top":
                    pinned_set = set(int(i) for i in np.where(ys >= hi - band)[0].tolist())
                else:
                    pinned_set = set(int(i) for i in np.where(ys <= lo + band)[0].tolist())
            inv = np.full(n, float(n) / total_mass, dtype=np.float32)
            for i in pinned_set:
                if 0 <= i < n:
                    inv[i] = 0.0
        except Exception:
            return -1
        try:
            comp_val = max(float(compliance), 0.0)
        except Exception:
            comp_val = 0.001
        try:
            bend_val = int(bend_mode)
        except Exception:
            try:
                bend_val = {"none": BEND_NONE, "distance": BEND_DISTANCE, "dihedral": BEND_DIHEDRAL}.get(
                    str(bend_mode or "").lower(), BEND_DISTANCE)
            except Exception:
                bend_val = BEND_DISTANCE
        if bend_val not in (BEND_NONE, BEND_DISTANCE, BEND_DIHEDRAL):
            bend_val = BEND_DISTANCE
        digest = (_soft_digest(verts, faces), comp_val, bend_val, inv.tobytes())
        settings = _SOFT_SETTINGS_CACHE.get(digest)
        if settings is None:
            try:
                settings = SoftBodySharedSettings()
                settings.add_vertices(verts.tobytes(), inv_masses=inv.tobytes())
                settings.add_faces(faces.tobytes())
                settings.create_constraints(comp_val, bend_val)
                settings.optimize()
            except Exception as e:
                Logger.warning(f"CulverinSolver: soft body settings failed: {e}")
                return -1
            _SOFT_SETTINGS_CACHE[digest] = settings
            if len(_SOFT_SETTINGS_CACHE) > 32:
                _SOFT_SETTINGS_CACHE.pop(next(iter(_SOFT_SETTINGS_CACHE)))
        try:
            rot_q = euler_to_quat(rotation[0], rotation[1], rotation[2])
        except Exception:
            rot_q = (0.0, 0.0, 0.0, 1.0)
        try:
            bmin = verts.min(axis=0).astype(np.float64)
            bmax = verts.max(axis=0).astype(np.float64)
            diag = float(np.linalg.norm(bmax - bmin))
        except Exception:
            diag = 0.0
        try:
            eff_radius = max(float(vertex_radius), 1e-4)
            if diag > 1e-9 and n > 0:
                spacing = diag / max(1.0, float(n) ** (1.0 / 3.0))
                if np.isfinite(spacing):
                    eff_radius = max(eff_radius, float(spacing) * 0.5)
        except Exception:
            try:
                eff_radius = max(float(vertex_radius), 1e-4)
            except Exception:
                eff_radius = 0.05
        try:
            handle = self._world.create_soft_body(
                shared_settings=settings,
                pos=(float(position[0]), float(position[1]), float(position[2])),
                rot=rot_q,
                pressure=max(float(pressure), 0.0),
                vertex_radius=max(float(eff_radius), 1e-4),
                linear_damping=max(float(damping), 0.0),
                num_iterations=max(int(iterations), 1),
                max_linear_velocity=max(float(max_velocity), 1.0),
                gravity_factor=float(gravity_factor),
                friction=float(friction),
                restitution=float(restitution),
                faces_double_sided=bool(double_sided),
                update_position=bool(update_com),
                user_data=0,
                category=_layer_category(collision_layer),
                mask=_mask_value(collision_mask),
            )
        except Exception as e:
            Logger.warning(f"CulverinSolver: create_soft_body failed: {e}")
            return -1
        if handle is None or handle < 0:
            return -1
        soft_id = self._next_soft_id
        self._next_soft_id -= 1
        try:
            self._world.set_user_data(handle, soft_id)
        except Exception:
            pass
        self._soft_handles.append(handle)
        self._soft_handle_to_id[handle] = soft_id
        self._soft_id_to_handle[soft_id] = handle
        if entity_id:
            self._soft_to_entity[soft_id] = entity_id
            self._entity_to_soft[entity_id] = soft_id
        try:
            layer_i = int(collision_layer)
        except Exception:
            layer_i = 0
        try:
            mask_i = int(collision_mask) & 0xFFFFFFFF
        except Exception:
            mask_i = 0xFFFF
        self._soft_specs[soft_id] = {
            "entity_id": entity_id,
            "count": n,
            "pinned": sorted(pinned_set),
            "verts": np.ascontiguousarray(verts.astype(np.float32)).copy(),
            "faces": np.ascontiguousarray(faces.reshape(-1).astype(np.int32)).copy(),
            "radius": float(eff_radius),
            "layer": layer_i,
            "mask": mask_i,
            "mass": max(float(mass), 1e-6),
        }
        return soft_id
