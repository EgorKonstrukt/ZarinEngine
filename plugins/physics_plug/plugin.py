# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from typing import Optional
from core.foundation.plugins import PluginBase
from core.foundation.logger import Logger
from core.physics import PhysicsProcess, PhysicsScene
from core.maths.math3d import Vec2, Vec3
from core.config.config import get_project_config
from physics_solvers.registry import DEFAULT_SOLVER, get_info, get_module_class, is_available, normalize
from plugins.physics_plug.sync import PhysicsSyncMixin
from plugins.physics_plug.ui import PhysicsUiMixin
class PhysicsPlugin(PhysicsSyncMixin, PhysicsUiMixin, PluginBase):
    NAME = "PhysicsPlugin"
    VERSION = "0.4.0"
    DESCRIPTION = "Physics system with shared-memory parallel simulation."
    SYSTEM = True
    def __init__(self):
        super().__init__()
        self._enabled: bool = True
        self._scanned_entity_ids: set[str] = set()
        self._last_entity_count: int = -1
        self._physics_process: Optional[PhysicsProcess] = None
        self._physics_scene: Optional[PhysicsScene] = None
        self._solver = None
        self._simulation_mode: str = "multi_threaded"
        self._layer_processes: dict[int, PhysicsProcess] = {}
        self._prev_frame_contacts: set = set()
        self._project_root: str = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._step_caches: dict[int, tuple] = {}
        self._cache_version: int = 0
        self._play_gen: int = 0
        self._collision_listener_sig: tuple = None
        self._has_collision_cache: bool = False
        self._collision_cache_valid: bool = False
        self._soft_remote: dict[str, dict] = {}
        self._soft_sync_helper = None
        self._soft_over_cap_warned: set[str] = set()
    @property
    def enabled(self) -> bool:
        return self._enabled
    @enabled.setter
    def enabled(self, v: bool):
        self._enabled = v
    @property
    def physics_scene(self) -> Optional[PhysicsScene]:
        return self._physics_scene
    def _get_physics_settings(self) -> dict:
        project_path = getattr(self._engine, "_project_path", None) or "." if self._engine else "."
        cfg = get_project_config(project_path)
        out = {}
        prefix = "physics."
        keys = ("solver", "physx_device", "simulation_mode", "gravity_x", "gravity_y", "gravity_z", "fixed_time_step", "num_sub_steps", "solver_iterations", "erp", "contact_erp", "friction_erp", "contact_breaking_threshold", "restitution", "linear_damping", "angular_damping", "max_contacts_per_body", "culverin_max_bodies", "culverin_max_pairs", "culverin_max_contact_constraints", "culverin_temp_allocator_size", "culverin_max_physics_jobs", "culverin_max_physics_barriers", "culverin_num_threads", "culverin_penetration_slop", "culverin_enable_ccd", "culverin_enable_sleeping")
        for k in keys:
            v = cfg.get(prefix + k)
            if v is not None:
                out[k] = v
        return out
    def initialize(self, engine):
        super().initialize(engine)
        settings = self._get_physics_settings()
        self._simulation_mode = settings.get("simulation_mode", "multi_threaded")
        solver_name = normalize(settings.get("solver", DEFAULT_SOLVER))
        solver_module, solver_class = get_module_class(solver_name)
        if not is_available(solver_name):
            Logger.warning(str("PhysicsPlugin solver fallback"))
            solver_name = DEFAULT_SOLVER
            solver_module, solver_class = get_module_class(solver_name)
        Logger.info(str("PhysicsPlugin using solver"))
        if self._simulation_mode == "single":
            self._init_single(solver_module, solver_class, settings, solver_name)
        elif self._simulation_mode == "per_layer_process":
            Logger.info(str("PhysicsPlugin per-layer mode"))
        else:
            self._physics_process = PhysicsProcess(project_root=self._project_root)
            ok = self._physics_process.start(solver_module, solver_class, settings)
            if not ok:
                Logger.warning(str("PhysicsPlugin fallback single"))
                self._physics_process = None
                self._simulation_mode = "single"
                self._init_single(solver_module, solver_class, settings, solver_name)
            else:
                Logger.info(str("PhysicsPlugin shared-memory started"))
        try:
            self._register_physics_ui()
        except Exception:
            pass
    def ensure_single_mode(self) -> bool:
        if self._simulation_mode == "single" and self._solver is not None:
            return True
        self._clear_soft_remote()
        if self._simulation_mode == "single" and self._solver is None:
            self._init_single(*self._solver_module_class_with_settings())
            return self._solver is not None
        try:
            if self._physics_process is not None:
                self._physics_process.shutdown(5000)
                self._physics_process = None
        except Exception:
            self._physics_process = None
        self._simulation_mode = "single"
        self._init_single(*self._solver_module_class_with_settings())
        if self._solver is not None:
            Logger.info(str("PhysicsPlugin single-threaded"))
        return self._solver is not None
    def _solver_module_class_with_settings(self) -> tuple:
        settings = self._get_physics_settings()
        solver_name = normalize(settings.get("solver", DEFAULT_SOLVER))
        sm, sc = get_module_class(solver_name)
        return (sm, sc, settings, solver_name)
    def _init_single(self, solver_module: str, solver_class: str, settings: dict, solver_name: str):
        import importlib
        try:
            mod = importlib.import_module(solver_module)
            cls = getattr(mod, solver_class)
            self._solver = cls()
            if not self._solver.initialize(settings):
                Logger.error(str("PhysicsPlugin single init failed"))
                self._solver = None
                self._physics_scene = None
                return
            self._physics_scene = PhysicsScene(self._solver)
            Logger.info(str("PhysicsPlugin in-process"))
        except Exception as e:
            Logger.error(str("PhysicsPlugin single init failed"))
            self._solver = None
            self._physics_scene = None
    def _solver_module_class(self) -> tuple[str, str]:
        settings = self._get_physics_settings()
        return get_module_class(normalize(settings.get("solver", DEFAULT_SOLVER)))
    def _get_layer_process(self, layer: int) -> PhysicsProcess:
        if layer not in self._layer_processes:
            sm, sc = self._solver_module_class()
            settings = self._get_physics_settings()
            proc = PhysicsProcess(project_root=self._project_root)
            if proc.start(sm, sc, settings):
                self._layer_processes[layer] = proc
                Logger.info(str("PhysicsPlugin layer process"))
            else:
                raise RuntimeError(str("Physics layer start failed"))
        return self._layer_processes[layer]
    def on_scene_loaded(self, scene):
        self._scanned_entity_ids.clear(); self._last_entity_count = -1; self._prev_frame_contacts.clear(); self._step_caches.clear()
        self._collision_listener_sig = None; self._collision_cache_valid = False
        self._clear_soft_remote()
    def on_project_opened(self):
        settings = self._get_physics_settings()
        new_mode = settings.get("simulation_mode", "multi_threaded")
        if new_mode == self._simulation_mode:
            return
        Logger.info(str("PhysicsPlugin project opened"))
        self._clear_soft_remote()
        if self._simulation_mode == "per_layer_process":
            for proc in self._layer_processes.values():
                proc.shutdown(1000)
            self._layer_processes.clear()
        elif self._simulation_mode == "single":
            if self._physics_scene is not None:
                self._physics_scene.shutdown()
                self._physics_scene = None
            self._solver = None
        else:
            if self._physics_process is not None:
                self._physics_process.shutdown(1000)
                self._physics_process = None
        self._simulation_mode = new_mode
        if new_mode == "single":
            self._init_single(*self._solver_module_class_with_settings())
        elif new_mode == "per_layer_process":
            Logger.info(str("PhysicsPlugin per-layer mode"))
        else:
            solver_module, solver_class = self._solver_module_class()
            self._physics_process = PhysicsProcess(project_root=self._project_root)
            if not self._physics_process.start(solver_module, solver_class, settings):
                Logger.warning(str("PhysicsPlugin fallback single"))
                self._physics_process = None
                self._simulation_mode = "single"
                self._init_single(*self._solver_module_class_with_settings())
    def on_scene_unloaded(self, scene):
        self._scanned_entity_ids.clear(); self._last_entity_count = -1; self._prev_frame_contacts.clear(); self._step_caches.clear()
        self._collision_listener_sig = None; self._collision_cache_valid = False
        self._clear_soft_remote()
        self._reset_entity_velocities(scene)
        if self._simulation_mode == "per_layer_process":
            for proc in self._layer_processes.values():
                proc.clear_slots(); proc.clear_soft_slots()
                proc.send({"type": "unload_all"})
        elif self._simulation_mode == "single":
            if self._physics_scene:
                self._physics_scene.shutdown()
        else:
            if self._physics_process:
                self._physics_process.clear_slots(); self._physics_process.clear_soft_slots()
                self._physics_process.send({"type": "unload_all"})
    def _start_fresh_process(self) -> bool:
        if self._physics_process is not None:
            self._physics_process.shutdown(500)
            self._physics_process = None
        self._step_caches.clear()
        self._clear_soft_remote()
        sm, sc = self._solver_module_class()
        settings = self._get_physics_settings()
        new_proc = PhysicsProcess(project_root=self._project_root)
        if new_proc.start(sm, sc, settings):
            self._physics_process = new_proc
            return True
        Logger.error(str("PhysicsPlugin start failed"))
        return False
    def _wait_gen(self, proc: PhysicsProcess, typ: str, total: float, gen: int):
        try:
            remain = max(0.0, float(total))
        except Exception:
            remain = 0.0
        while remain > 0.0:
            try:
                if gen != self._play_gen:
                    return None
            except Exception:
                return None
            try:
                chunk = min(remain, 0.25)
            except Exception:
                chunk = 0.25
            try:
                r = proc.wait_for_result(typ, timeout=chunk)
            except Exception:
                r = None
            if r is not None:
                return r
            try:
                remain -= chunk
            except Exception:
                return None
        return None
    def _is_alive_for_bringup(self, gen: int, scene) -> bool:
        try:
            if gen != self._play_gen:
                return False
        except Exception:
            return False
        try:
            eng = self._engine
            if eng is None or eng.scene is not scene:
                return False
        except Exception:
            return False
        return True
    def _reset_entity_velocities(self, scene=None):
        if scene is None:
            if not self._engine or not self._engine.scene:
                return
            scene = self._engine.scene
        for entity in scene.get_all_entities():
            rb = entity._components.get("Rigidbody")
            if rb:
                rb._velocity = Vec3.zero(); rb._angular_velocity = Vec3.zero(); rb._force_accum = Vec3.zero(); rb._torque_accum = Vec3.zero()
            rb2d = entity._components.get("Rigidbody2D")
            if rb2d:
                rb2d._velocity = Vec2.zero(); rb2d._angular_velocity = 0.0; rb2d._force_accum = Vec2.zero(); rb2d._torque_accum = 0.0
    def _unload_no_wait(self, proc: PhysicsProcess):
        try:
            if proc is None:
                return False
            try:
                alive = proc.is_alive()
            except Exception:
                alive = False
            if not alive:
                return False
            try:
                proc.send({"type": "unload_all"})
            except Exception:
                return False
            return True
        except Exception:
            return False
    def _unload_and_wait(self, proc: PhysicsProcess):
        proc.send({"type": "unload_all"})
        if proc.wait_for_result("unload_all", timeout=3.0) is None:
            Logger.warning(str("PhysicsPlugin unload timeout"))
            proc.shutdown(500)
    def shutdown(self):
        if self._simulation_mode == "per_layer_process":
            for proc in self._layer_processes.values():
                proc.shutdown(500)
            self._layer_processes.clear()
        elif self._simulation_mode == "single":
            if self._physics_scene:
                self._physics_scene.shutdown()
                self._physics_scene = None
            if self._solver:
                self._solver.shutdown()
                self._solver = None
        else:
            if self._physics_process:
                self._physics_process.shutdown(500)
                self._physics_process = None
    def _rebuild_step_cache(self, proc, entities):
        _cache = []
        for eid, slot in proc.entity_slot_map.items():
            entity = entities.get(eid)
            if not entity or not entity._active:
                continue
            rb = entity._components.get("Rigidbody")
            rb2d = entity._components.get("Rigidbody2D")
            tr = entity._components.get("Transform")
            if not tr:
                continue
            _cache.append((entity, rb, rb2d, tr, slot))
        return _cache
    def _read_results_python(self, shared, cache) -> None:
        _flags = shared._flags_nd
        _rdata = shared._rdata_nd
        for entity, rb, rb2d, tr, slot in cache:
            if getattr(tr, "_physics_dirty", False):
                continue
            if rb2d is not None and rb2d.is_kinematic:
                continue
            if rb is not None and rb.is_kinematic:
                continue
            fl = int(_flags[slot])
            if not (fl & 1) or (fl & 4):
                continue
            if rb2d:
                nx = float(_rdata[slot, 0]); ny = float(_rdata[slot, 1]); nqz = float(_rdata[slot, 5]); nqw = float(_rdata[slot, 6])
                same = abs(tr._local_pos._x - nx) < 1e-5 and abs(tr._local_pos._y - ny) < 1e-5 and abs(tr._local_rot._z - nqz) < 1e-4 and abs(tr._local_rot._w - nqw) < 1e-4
                if same:
                    if not getattr(rb2d, "_velocity_dirty", False):
                        rb2d._velocity._x = float(_rdata[slot, 7]); rb2d._velocity._y = float(_rdata[slot, 8]); rb2d._angular_velocity = float(_rdata[slot, 12])
                    rb2d._force_accum._x = 0.0; rb2d._force_accum._y = 0.0; rb2d._torque_accum = 0.0
                    continue
                tr._local_pos._x = nx; tr._local_pos._y = ny; tr._local_pos._z = 0.0
                tr._local_rot._x = 0.0; tr._local_rot._y = 0.0; tr._local_rot._z = nqz; tr._local_rot._w = nqw
                tr._dirty = True
                scn = entity._scene
                if scn is not None:
                    scn._dirty_roots.add(tr); scn._spatial_dirty_entities.add(entity.id); scn._spatial_dirty = True
                if not getattr(rb2d, "_velocity_dirty", False):
                    rb2d._velocity._x = float(_rdata[slot, 7]); rb2d._velocity._y = float(_rdata[slot, 8]); rb2d._angular_velocity = float(_rdata[slot, 12])
                rb2d._force_accum._x = 0.0; rb2d._force_accum._y = 0.0; rb2d._torque_accum = 0.0
            elif rb:
                nx = float(_rdata[slot, 0]); ny = float(_rdata[slot, 1]); nz = float(_rdata[slot, 2])
                nqx = float(_rdata[slot, 3]); nqy = float(_rdata[slot, 4]); nqz = float(_rdata[slot, 5]); nqw = float(_rdata[slot, 6])
                same = abs(tr._local_pos._x - nx) < 1e-5 and abs(tr._local_pos._y - ny) < 1e-5 and abs(tr._local_pos._z - nz) < 1e-5 and abs(tr._local_rot._x - nqx) < 1e-4 and abs(tr._local_rot._y - nqy) < 1e-4 and abs(tr._local_rot._z - nqz) < 1e-4 and abs(tr._local_rot._w - nqw) < 1e-4
                if same:
                    if not getattr(rb, "_velocity_dirty", False):
                        rb._velocity._x = float(_rdata[slot, 7]); rb._velocity._y = float(_rdata[slot, 8]); rb._velocity._z = float(_rdata[slot, 9])
                        rb._angular_velocity._x = float(_rdata[slot, 10]); rb._angular_velocity._y = float(_rdata[slot, 11]); rb._angular_velocity._z = float(_rdata[slot, 12])
                    continue
                tr._local_pos._x = nx; tr._local_pos._y = ny; tr._local_pos._z = nz
                tr._local_rot._x = nqx; tr._local_rot._y = nqy; tr._local_rot._z = nqz; tr._local_rot._w = nqw
                tr._dirty = True
                scn = entity._scene
                if scn is not None:
                    scn._dirty_roots.add(tr); scn._spatial_dirty_entities.add(entity.id); scn._spatial_dirty = True
                if not getattr(rb, "_velocity_dirty", False):
                    rb._velocity._x = float(_rdata[slot, 7]); rb._velocity._y = float(_rdata[slot, 8]); rb._velocity._z = float(_rdata[slot, 9])
                    rb._angular_velocity._x = float(_rdata[slot, 10]); rb._angular_velocity._y = float(_rdata[slot, 11]); rb._angular_velocity._z = float(_rdata[slot, 12])
    def _write_inputs_python(self, shared, cache) -> int:
        _flags = shared._flags_nd
        _edata = shared._edata_nd
        _fdata = shared._fdata_nd
        slots, pos_x, pos_y, pos_z, qx_l, qy_l, qz_l, qw_l, vel_x, vel_y, vel_z, av_x, av_y, av_z, f_x, f_y, f_z, t_x, t_y, t_z, flv = [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], []
        max_slot = -1
        for entity, rb, rb2d, tr, slot in cache:
            if not entity._active:
                continue
            lp = tr._local_pos
            slots.append(slot)
            if rb2d:
                q = tr._local_rot
                fa = rb2d._force_accum
                if getattr(tr, "_physics_dirty", False) or rb2d.is_kinematic:
                    pos_x.append(lp._x); pos_y.append(lp._y); pos_z.append(0.0)
                    qx_l.append(0.0); qy_l.append(0.0); qz_l.append(q._z); qw_l.append(q._w)
                    vel_x.append(rb2d._velocity._x); vel_y.append(rb2d._velocity._y); vel_z.append(0.0)
                    av_x.append(0.0); av_y.append(0.0); av_z.append(rb2d._angular_velocity)
                    f_x.append(fa._x); f_y.append(fa._y); f_z.append(0.0)
                    t_x.append(0.0); t_y.append(0.0); t_z.append(rb2d._torque_accum)
                    flv.append(15)
                    tr._physics_dirty = False
                else:
                    pos_x.append(0.0); pos_y.append(0.0); pos_z.append(0.0)
                    qx_l.append(0.0); qy_l.append(0.0); qz_l.append(0.0); qw_l.append(0.0)
                    vel_x.append(rb2d._velocity._x); vel_y.append(rb2d._velocity._y); vel_z.append(0.0)
                    av_x.append(0.0); av_y.append(0.0); av_z.append(rb2d._angular_velocity)
                    f_x.append(fa._x); f_y.append(fa._y); f_z.append(0.0)
                    t_x.append(0.0); t_y.append(0.0); t_z.append(rb2d._torque_accum)
                    flv.append(11 if rb2d.consume_velocity_dirty() else 9)
            elif rb:
                q = tr._local_rot
                fa = rb._force_accum
                ta = rb._torque_accum
                if getattr(tr, "_physics_dirty", False) or rb.is_kinematic:
                    pos_x.append(lp._x); pos_y.append(lp._y); pos_z.append(lp._z)
                    qx_l.append(q._x); qy_l.append(q._y); qz_l.append(q._z); qw_l.append(q._w)
                    vel_x.append(rb._velocity._x); vel_y.append(rb._velocity._y); vel_z.append(rb._velocity._z)
                    av_x.append(rb._angular_velocity._x); av_y.append(rb._angular_velocity._y); av_z.append(rb._angular_velocity._z)
                    f_x.append(fa._x); f_y.append(fa._y); f_z.append(fa._z)
                    t_x.append(ta._x); t_y.append(ta._y); t_z.append(ta._z)
                    flv.append(7)
                    tr._physics_dirty = False
                else:
                    pos_x.append(0.0); pos_y.append(0.0); pos_z.append(0.0)
                    qx_l.append(0.0); qy_l.append(0.0); qz_l.append(0.0); qw_l.append(0.0)
                    vel_x.append(rb._velocity._x); vel_y.append(rb._velocity._y); vel_z.append(rb._velocity._z)
                    av_x.append(rb._angular_velocity._x); av_y.append(rb._angular_velocity._y); av_z.append(rb._angular_velocity._z)
                    f_x.append(fa._x); f_y.append(fa._y); f_z.append(fa._z)
                    t_x.append(ta._x); t_y.append(ta._y); t_z.append(ta._z)
                    flv.append(3 if rb.consume_velocity_dirty() else 1)
                fa._x = 0.0; fa._y = 0.0; fa._z = 0.0; ta._x = 0.0; ta._y = 0.0; ta._z = 0.0
            if slot > max_slot:
                max_slot = slot
        if slots:
            _edata[slots, 0] = pos_x; _edata[slots, 1] = pos_y; _edata[slots, 2] = pos_z
            _edata[slots, 3] = qx_l; _edata[slots, 4] = qy_l; _edata[slots, 5] = qz_l; _edata[slots, 6] = qw_l
            _edata[slots, 7] = vel_x; _edata[slots, 8] = vel_y; _edata[slots, 9] = vel_z
            _edata[slots, 10] = av_x; _edata[slots, 11] = av_y; _edata[slots, 12] = av_z
            _fdata[slots, 0] = f_x; _fdata[slots, 1] = f_y; _fdata[slots, 2] = f_z
            _fdata[slots, 3] = t_x; _fdata[slots, 4] = t_y; _fdata[slots, 5] = t_z
            _flags[slots] = flv
        return max_slot
