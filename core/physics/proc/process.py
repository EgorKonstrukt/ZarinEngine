# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import multiprocessing
import queue
import os
import time
from typing import Optional
from core.physics.shared_buffer import SharedPhysicsBuffer, MAX_ENTITIES
from core.physics.soft_shared_buffer import SoftSharedBuffer
from core.physics.proc.sync import _create_body, _create_soft_worker, _drop_entity_bodies, _drop_entity_soft, _process_step_shared


class PhysicsProcess:
    def __init__(self, project_root: str = ""):
        self._project_root = project_root or os.getcwd()
        self._cmd_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._result_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._process: Optional[multiprocessing.Process] = None
        self._solver_module: str = ""
        self._solver_class: str = ""
        self._shared = SharedPhysicsBuffer()
        self._shared.create()
        self._soft_shared = SoftSharedBuffer()
        self._soft_shared.create()
        self._entity_to_slot: dict[str, int] = {}
        self._slot_free: list[int] = []
        self._entity_to_soft_slot: dict[str, int] = {}
        self._soft_slot_free: list[int] = []

    @property
    def shared(self) -> SharedPhysicsBuffer:
        return self._shared

    @property
    def soft_shared(self) -> SoftSharedBuffer:
        return self._soft_shared

    @property
    def entity_slot_map(self) -> dict[str, int]:
        return self._entity_to_slot

    @property
    def entity_soft_slot_map(self) -> dict[str, int]:
        return self._entity_to_soft_slot

    def clear_slots(self):
        self._entity_to_slot.clear()
        self._slot_free.clear()

    def clear_soft_slots(self):
        self._entity_to_soft_slot.clear()
        self._soft_slot_free.clear()

    def alloc_slot(self) -> int:
        if self._slot_free:
            return self._slot_free.pop()
        slot = len(self._entity_to_slot)
        if slot >= MAX_ENTITIES:
            raise RuntimeError(f"Max {MAX_ENTITIES} physics entities exceeded")
        return slot

    def free_slot(self, slot: int):
        self._slot_free.append(slot)
        self._shared.set_active(slot, False)

    def alloc_soft_slot(self) -> int:
        from core.physics.soft_shared_buffer import MAX_SOFT_BODIES
        if self._soft_slot_free:
            return self._soft_slot_free.pop()
        slot = len(self._entity_to_soft_slot)
        if slot >= MAX_SOFT_BODIES:
            raise RuntimeError(f"Max {MAX_SOFT_BODIES} soft bodies exceeded")
        return slot

    def free_soft_slot(self, slot: int):
        self._soft_slot_free.append(slot)
        try:
            self._soft_shared.clear_slot(slot)
        except Exception:
            pass

    def spawn(self, solver_module: str, solver_class: str, settings: dict) -> bool:
        try:
            self._solver_module = solver_module
            self._solver_class = solver_class
            self._shared.set_num_entities(0)
            self._process = multiprocessing.Process(
                target=_physics_loop,
                args=(self._cmd_queue, self._result_queue,
                      self._shared.name, self._soft_shared.name,
                      self._project_root, solver_module, solver_class, settings),
                daemon=True,
            )
            self._process.start()
            return True
        except Exception:
            try:
                self._process = None
            except Exception:
                pass
            return False

    def wait_init(self, timeout: float = 10.0) -> bool:
        try:
            result = self.wait_for_result("init", timeout=timeout)
        except Exception:
            result = None
        ok = result is not None and result.get("success", False)
        if not ok:
            from core.foundation.logger import Logger
            Logger.warning(f"  PhysicsProcess.start FAILED, killing process")
            try:
                if self._process and self._process.is_alive():
                    self._process.terminate()
                    self._process.join(2)
            except Exception:
                pass
            try:
                self._process = None
                self._shared.close()
                self._shared.unlink()
                self._soft_shared.close()
                self._soft_shared.unlink()
            except Exception:
                pass
        return ok

    def start(self, solver_module: str, solver_class: str, settings: dict) -> bool:
        if not self.spawn(solver_module, solver_class, settings):
            return False
        return self.wait_init(timeout=10.0)

    def send(self, cmd: dict):
        self._cmd_queue.put(cmd)

    def poll(self) -> Optional[dict]:
        try:
            return self._result_queue.get_nowait()
        except queue.Empty:
            return None

    def drain(self) -> list[dict]:
        results = []
        while True:
            r = self.poll()
            if r is None:
                break
            results.append(r)
        return results

    def wait_for_result(self, expected_type: str, timeout: float = 5.0) -> Optional[dict]:
        deadline = time.monotonic() + timeout
        while True:
            r = self.poll()
            if r and r.get("type") == expected_type:
                return r
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.001)

    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def shutdown(self, timeout: int = 5000):
        if self._process is None or not self._process.is_alive():
            self._process = None
            self._shared.close()
            self._shared.unlink()
            self._soft_shared.close()
            self._soft_shared.unlink()
            return
        try:
            try:
                self._cmd_queue.put_nowait({"type": "shutdown"})
            except Exception:
                try:
                    self._cmd_queue.put({"type": "shutdown"}, timeout=0.2)
                except Exception:
                    pass
            budget = max(0.0, timeout / 1000)
            waited = 0.0
            while waited < budget:
                if not self._process.is_alive():
                    break
                time.sleep(0.02)
                waited += 0.02
        except Exception:
            pass
        if self._process and self._process.is_alive():
            try:
                self._process.terminate()
            except Exception:
                pass
            try:
                self._process.join(1)
            except Exception:
                pass
        self._process = None
        self._shared.close()
        self._shared.unlink()
        self._soft_shared.close()
        self._soft_shared.unlink()


def _physics_loop(
    cmd_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
    shared_name: str,
    soft_shared_name: str,
    project_root: str,
    solver_module: str,
    solver_class_name: str,
    settings: dict,
):
    import sys
    import os
    project_root = os.path.normpath(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    os.chdir(project_root)
    import importlib
    from core.foundation.logger import Logger
    shared = SharedPhysicsBuffer()
    shared.attach(shared_name)
    from core.physics.soft_shared_buffer import SoftSharedBuffer
    soft_shared = SoftSharedBuffer()
    soft_shared.attach(soft_shared_name)
    try:
        mod = importlib.import_module(solver_module)
        SolverCls = getattr(mod, solver_class_name)
    except Exception as e:
        Logger.error(f"PhysicsProcess: cannot import solver: {e}")
        result_queue.put({"type": "init", "success": False})
        shared.close()
        soft_shared.close()
        return
    solver = SolverCls()
    if not solver.initialize(settings):
        Logger.error("PhysicsProcess: solver init failed")
        result_queue.put({"type": "init", "success": False})
        shared.close()
        soft_shared.close()
        return
    from core.physics.scene import PhysicsScene
    physics_scene = PhysicsScene(solver)
    _slot_to_body: dict[int, int] = {}
    _soft_states: dict[str, dict] = {}
    _pending_soft_created: list[dict] = []
    result_queue.put({"type": "init", "success": True})
    running = True
    while running:
        try:
            cmd = cmd_queue.get(timeout=0.05)
        except queue.Empty:
            continue
        except (EOFError, OSError):
            break
        t = cmd.get("type")
        try:
            if t == "step":
                dt = float(cmd.get("dt", 0.02))
                while True:
                    try:
                        nxt = cmd_queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt.get("type") == "step":
                        dt += float(nxt.get("dt", 0.02))
                    else:
                        cmd_queue.put(nxt)
                        break
                cmd["dt"] = dt
                _process_step_shared(cmd, solver, physics_scene, result_queue, shared, _slot_to_body,
                                     soft_shared, _soft_states, _pending_soft_created)
            elif t == "load_bodies":
                _slot_to_body.clear()
                solver.remove_all_joints()
                solver.remove_all_bodies()
                physics_scene._entity_to_body.clear()
                physics_scene._body_to_entity.clear()
                if hasattr(physics_scene, "_entity_to_extra_bodies"):
                    physics_scene._entity_to_extra_bodies.clear()
                physics_scene._entity_to_joint.clear()
                physics_scene._joint_to_entity.clear()
                physics_scene._cached_shape.clear()
                physics_scene._cached_shape_info.clear()
                physics_scene._prev_frame_contacts.clear()
                for body in cmd.get("bodies", []):
                    _create_body(body, solver, physics_scene, shared, _slot_to_body)
                result_queue.put({"type": "load_bodies"})
            elif t == "add_body":
                _create_body(cmd["body"], solver, physics_scene, shared, _slot_to_body)
            elif t == "load_soft_bodies":
                _soft_states.clear()
                _pending_soft_created.clear()
                try:
                    solver.remove_all_soft_bodies()
                except Exception:
                    pass
                created = []
                for soft in cmd.get("softs", []):
                    created.append(_create_soft_worker(solver, soft, _soft_states))
                _pending_soft_created.extend(created)
                result_queue.put({"type": "soft_loaded", "soft_created": created})
            elif t == "add_soft_body":
                _pending_soft_created.append(_create_soft_worker(solver, cmd["soft"], _soft_states))
            elif t == "update_soft_body":
                soft = cmd["soft"]
                _drop_entity_soft(_soft_states, solver, soft.get("entity_id", ""))
                _pending_soft_created.append(_create_soft_worker(solver, soft, _soft_states))
            elif t == "remove_bodies":
                for eid in cmd.get("entity_ids", []):
                    _drop_entity_bodies(physics_scene, solver, eid)
                    _drop_entity_soft(_soft_states, solver, eid)
                for slot in cmd.get("slots", []):
                    _slot_to_body.pop(slot, None)
                    shared.set_active(slot, False)
            elif t == "unload_all":
                _slot_to_body.clear()
                _soft_states.clear()
                _pending_soft_created.clear()
                solver.remove_all_joints()
                solver.remove_all_bodies()
                try:
                    solver.remove_all_soft_bodies()
                except Exception:
                    pass
                physics_scene._entity_to_body.clear()
                physics_scene._body_to_entity.clear()
                if hasattr(physics_scene, "_entity_to_extra_bodies"):
                    physics_scene._entity_to_extra_bodies.clear()
                physics_scene._entity_to_joint.clear()
                physics_scene._joint_to_entity.clear()
                physics_scene._cached_shape.clear()
                physics_scene._cached_shape_info.clear()
                physics_scene._prev_frame_contacts.clear()
                shared.set_num_entities(0)
                result_queue.put({"type": "unload_all"})
            elif t == "shutdown":
                running = False
        except Exception as e:
            Logger.error(f"PhysicsProcess: error processing cmd '{t}': {e}")
            import traceback
            Logger.error(traceback.format_exc())
            result_queue.put({"type": t, "error": str(e)})
    solver.shutdown()
    shared.close()
    soft_shared.close()
