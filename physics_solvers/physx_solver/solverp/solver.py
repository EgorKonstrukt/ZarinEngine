# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun


from __future__ import annotations
from typing import Optional
import numpy as np
from core.foundation.logger import Logger
from core.physics.physics_solver import IPhysicsSolver
from physics_solvers.physx_solver.solverp.bodies import BodiesMixin
from physics_solvers.physx_solver.solverp.scenes import ScenesMixin, _quat_to_euler


class PhysXSolver(BodiesMixin, ScenesMixin, IPhysicsSolver):

    def __init__(self):
        self._initialized = False
        self._ov_physx = None
        self._usd_handle = None
        self._usd_path: str = ""
        self._body_count = 0
        self._next_body_id = 1
        self._body_id_to_prim: dict[int, str] = {}
        self._entity_id_to_body_id: dict[str, int] = {}
        self._body_id_to_entity_id: dict[int, str] = {}
        self._gravity: tuple[float, float, float] = (0.0, -9.81, 0.0)
        self._debug_enabled = False
        self._all_body_ids: list[int] = []
        self._device = "auto"
        self._bodies_dirty = False
        self._body_specs: dict[int, dict] = {}
        self._sim_time = 0.0

        self._pose_tb = None
        self._vel_tb = None
        self._wrench_tb = None
        self._pose_buf: np.ndarray | None = None
        self._vel_buf: np.ndarray | None = None
        self._wrench_buf: np.ndarray | None = None

        self._dynamic_prim_paths: list[str] = []
        self._prim_path_to_idx: dict[str, int] = {}

        self._pending_vel: dict[int, tuple[float, float, float]] = {}
        self._pending_ang_vel: dict[int, tuple[float, float, float]] = {}
        self._pending_wrench: dict[int, list[float]] = {}

        self._joint_specs: dict[int, dict] = {}
        self._next_joint_id = 1
        self._joint_id_to_prim: dict[int, str] = {}
        self._joint_count = 0


    def initialize(self, settings: Optional[dict] = None) -> bool:
        if self._initialized:
            return True
        try:
            from ovphysx import PhysX
            opts = settings or {}
            device = opts.get("physx_device", opts.get("device", "cpu"))
            self._device = device
            self._ov_physx = PhysX(device=device)
            gx = opts.get("gravity_x", 0.0)
            gy = opts.get("gravity_y", -9.81)
            gz = opts.get("gravity_z", 0.0)
            self._gravity = (gx, gy, gz)
            self._initialized = True
            Logger.info(f"PhysXSolver initialized (device={device})")
            return True
        except ImportError:
            Logger.error("PhysXSolver: ovphysx not installed. Run: pip install ovphysx")
            return False
        except Exception as e:
            Logger.error(f"PhysXSolver init failed: {e}")
            return False


    def shutdown(self):
        self._destroy_scene()
        if self._ov_physx is not None:
            try:
                self._ov_physx.release()
            except Exception:
                pass
            self._ov_physx = None
        self._initialized = False
        self._body_count = 0
        self._next_body_id = 1
        self._body_id_to_prim.clear()
        self._entity_id_to_body_id.clear()
        self._body_id_to_entity_id.clear()
        self._all_body_ids.clear()
        self._body_specs.clear()
        self._dynamic_prim_paths.clear()
        self._prim_path_to_idx.clear()
        self._pending_vel.clear()
        self._pending_ang_vel.clear()
        self._pending_wrench.clear()
        self._joint_specs.clear()
        self._joint_id_to_prim.clear()
        self._joint_count = 0
        self._next_joint_id = 1
        self._bodies_dirty = False
        Logger.info("PhysXSolver shutdown.")


    @property
    def body_count(self) -> int:
        return self._body_count


    @property
    def debug_draw(self):
        return self._debug_enabled


    @debug_draw.setter
    def debug_draw(self, enabled: bool):
        pass


    def _get_body_idx(self, body_id: int) -> int | None:
        prim = self._body_id_to_prim.get(body_id)
        if prim:
            return self._prim_path_to_idx.get(prim)
        return None


    def _is_dynamic(self, body_id: int) -> bool:
        spec = self._body_specs.get(body_id)
        return bool(spec and spec.get("mass", 0) > 0 and not spec.get("is_trigger", False))


    def _flush_pending(self):
        if self._vel_tb is None and self._wrench_tb is None:
            return
        self._ensure_scene()
        if self._vel_tb is None and self._wrench_tb is None:
            return

        if self._pending_vel or self._pending_ang_vel:
            if self._vel_tb is not None:
                if self._vel_buf is None:
                    self._vel_buf = np.zeros(self._vel_tb.shape, dtype=np.float32)
                self._vel_tb.read(self._vel_buf)
                for body_id, vel in self._pending_vel.items():
                    idx = self._get_body_idx(body_id)
                    if idx is not None and idx < len(self._vel_buf):
                        self._vel_buf[idx, 0] = vel[0]
                        self._vel_buf[idx, 1] = vel[1]
                        self._vel_buf[idx, 2] = vel[2]
                for body_id, av in self._pending_ang_vel.items():
                    idx = self._get_body_idx(body_id)
                    if idx is not None and idx < len(self._vel_buf):
                        self._vel_buf[idx, 3] = av[0]
                        self._vel_buf[idx, 4] = av[1]
                        self._vel_buf[idx, 5] = av[2]
                self._vel_tb.write(self._vel_buf)
            self._pending_vel.clear()
            self._pending_ang_vel.clear()

        if self._pending_wrench:
            if self._wrench_tb is not None:
                if self._wrench_buf is None:
                    self._wrench_buf = np.zeros(self._wrench_tb.shape, dtype=np.float32)
                self._wrench_buf.fill(0.0)
                for body_id, w in self._pending_wrench.items():
                    idx = self._get_body_idx(body_id)
                    if idx is not None and idx < len(self._wrench_buf):
                        self._wrench_buf[idx, 0] = w[0]
                        self._wrench_buf[idx, 1] = w[1]
                        self._wrench_buf[idx, 2] = w[2]
                        self._wrench_buf[idx, 3] = w[3]
                        self._wrench_buf[idx, 4] = w[4]
                        self._wrench_buf[idx, 5] = w[5]
                self._wrench_tb.write(self._wrench_buf)
            self._pending_wrench.clear()


    def step_simulation(self, dt: float):
        if self._ov_physx is None:
            return
        self._ensure_scene()
        if self._usd_handle is None:
            return
        self._flush_pending()
        try:
            self._sim_time += dt
            self._ov_physx.step(dt, self._sim_time)
            self._ov_physx.wait_all()
            self._pull_transforms()
        except Exception as e:
            Logger.warning(f"PhysXSolver step error: {e}")


    def _pull_transforms(self):
        if self._pose_tb is None or self._body_count == 0:
            return
        try:
            if self._pose_buf is None:
                self._pose_buf = np.zeros(self._pose_tb.shape, dtype=np.float32)
            self._pose_tb.read(self._pose_buf)
        except Exception:
            return

        for prim_path, idx in self._prim_path_to_idx.items():
            if idx >= len(self._pose_buf):
                continue
            pose = self._pose_buf[idx]
            px_, py, pz = float(pose[0]), float(pose[1]), float(pose[2])
            qx, qy, qz, qw = float(pose[3]), float(pose[4]), float(pose[5]), float(pose[6])
            body_id = next(
                (bid for bid, pp in self._body_id_to_prim.items() if pp == prim_path),
                None,
            )
            if body_id is None:
                continue
            spec = self._body_specs.get(body_id)
            if spec:
                spec["position"] = (px_, py, pz)
                euler = _quat_to_euler((qx, qy, qz, qw))
                spec["rotation"] = euler


    def set_gravity(self, gravity: tuple[float, float, float]):
        self._gravity = gravity
        self._bodies_dirty = True


    def ray_cast(
        self,
        origin: tuple[float, float, float],
        direction: tuple[float, float, float],
        max_distance: float = 100.0,
    ) -> Optional[dict]:
        if self._ov_physx is None:
            return None
        try:
            results = self._ov_physx.raycast(origin, direction, max_distance)
        except Exception:
            return None
        if not results:
            return None

        hit = results[0]
        hit_pos = hit["position"]

        best_body_id = None
        best_dist = float("inf")

        for body_id, spec in self._body_specs.items():
            pos = spec["position"]
            dx = hit_pos[0] - pos[0]
            dy = hit_pos[1] - pos[1]
            dz = hit_pos[2] - pos[2]
            d2 = dx * dx + dy * dy + dz * dz
            if d2 < best_dist:
                best_dist = d2
                best_body_id = body_id

        return {
            "body_id": best_body_id,
            "position": hit_pos,
            "normal": hit.get("normal", (0.0, 0.0, 0.0)),
            "distance": hit.get("distance", 0.0),
        }


    def get_collision_events(self) -> list[dict]:
        if self._ov_physx is None:
            return []
        try:
            cr = self._ov_physx.get_contact_report()
        except Exception:
            return []
        if cr.get("num_headers", 0) == 0 and cr.get("num_points", 0) == 0:
            return []

        events = []
        for i in range(cr.get("num_headers", 0)):
            h = cr["headers"][i]
            try:
                body0 = h.body0 if hasattr(h, "body0") else getattr(h, "actor0", None)
                body1 = h.body1 if hasattr(h, "body1") else getattr(h, "actor1", None)
            except Exception:
                continue
            if body0 is None or body1 is None:
                continue

            ncd = getattr(h, "numContactData", 1)
            pts = []
            base = getattr(h, "baseIndex", 0)
            for j in range(base, min(base + ncd, cr.get("num_points", 0))):
                p = cr["points"][j]
                pts.append({
                    "position": getattr(p, "position", (0, 0, 0)),
                    "normal": getattr(p, "normal", (0, 0, 0)),
                    "impulse": getattr(p, "impulse", 0.0),
                    "separation": getattr(p, "separation", 0.0),
                })

            events.append({
                "body_a": body0,
                "body_b": body1,
                "type": "collision",
                "points": pts,
            })
        return events
