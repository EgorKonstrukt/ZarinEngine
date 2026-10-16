# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import threading
from core.physics import PhysicsProcess, PhysicsScene
from core.foundation.logger import Logger
try:
    from core._physics_sync import sync_read_to_ecs as _COMPILED_SYNC_READ, sync_write_from_ecs as _COMPILED_SYNC_WRITE
except (ImportError, AttributeError):
    _COMPILED_SYNC_READ = None
    _COMPILED_SYNC_WRITE = None
class PhysicsUiMixin:
    def _register_physics_ui(self):
        try: self.add_menu_item("Physics", "Toggle Physics", self._toggle_physics_ui)
        except Exception: pass
        try: self.add_toolbar_button("Physics", self._toggle_physics_ui, tooltip="Toggle physics")
        except Exception: pass
        try: self.register_dock("Physics", self._create_physics_panel, area="right")
        except Exception: pass
    def _toggle_physics_ui(self):
        try: self._enabled = not self._enabled
        except Exception: pass
    def _create_physics_panel(self):
        try:
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
            w = QWidget(); lay = QVBoxLayout(w); lab = QLabel(str("Physics")); lay.addWidget(lab)
            return w
        except Exception: return None
    def _bringup_process_async(self, gen: int, scene, sm, sc, settings, old_proc) -> None:
        try:
            if old_proc is not None: old_proc.shutdown(500)
        except Exception: pass
        try: alive = self._is_alive_for_bringup(gen, scene)
        except Exception: alive = False
        if not alive: return
        new_proc = PhysicsProcess(project_root=self._project_root)
        try:
            if not new_proc.spawn(sm, sc, settings):
                try: new_proc.shutdown(500)
                except Exception: pass
                return
        except Exception: return
        if not self._is_alive_for_bringup(gen, scene):
            try: new_proc.shutdown(500)
            except Exception: pass
            return
        if new_proc.wait_init(timeout=10.0) is not True: return
        if not self._is_alive_for_bringup(gen, scene):
            try: new_proc.shutdown(500)
            except Exception: pass
            return
        try:
            bodies = []
            try: entities = scene.get_all_entities()
            except Exception: entities = []
            for entity in entities:
                try:
                    if gen != self._play_gen:
                        try: new_proc.shutdown(500)
                        except Exception: pass
                        return
                except Exception: return
                try:
                    rb = entity._components.get("Rigidbody"); rb2d = entity._components.get("Rigidbody2D"); tr = entity._components.get("Transform")
                    if (not rb and not rb2d) or not tr: continue
                    bd = self._body_with_slot_in_process(entity, tr, new_proc)
                    if bd: bodies.append(bd)
                except Exception: continue
        except Exception: bodies = []
        if not self._is_alive_for_bringup(gen, scene):
            try: new_proc.shutdown(500)
            except Exception: pass
            return
        try: softs = self._collect_soft_dicts(scene, new_proc)
        except Exception: softs = []
        if not bodies and not softs:
            try: self._physics_process = new_proc
            except Exception: pass
            return
        if bodies:
            try: new_proc.send({"type": "load_bodies", "bodies": bodies})
            except Exception:
                try: new_proc.shutdown(500)
                except Exception: pass
                return
            if self._wait_gen(new_proc, "load_bodies", 5.0, gen) is None:
                Logger.error(str("PhysicsPlugin load timeout"))
                try: new_proc.shutdown(500)
                except Exception: pass
                try: self._clear_soft_remote()
                except Exception: pass
                return
            try: Logger.info(str("PhysicsPlugin bodies loaded"))
            except Exception: pass
        if softs:
            try: new_proc.send({"type": "load_soft_bodies", "softs": softs})
            except Exception:
                try: new_proc.shutdown(500)
                except Exception: pass
                return
            ack = self._wait_gen(new_proc, "soft_loaded", 60.0, gen)
            if ack is None:
                try:
                    if gen == self._play_gen: Logger.error(str("PhysicsPlugin soft timeout"))
                except Exception: pass
            else:
                try: self._harvest_soft_created(new_proc, scene, [ack])
                except Exception: pass
            try: Logger.info(str("PhysicsPlugin soft loaded"))
            except Exception: pass
        if not self._is_alive_for_bringup(gen, scene):
            try: new_proc.shutdown(500)
            except Exception: pass
            return
        try: self._physics_process = new_proc
        except Exception:
            try: new_proc.shutdown(500)
            except Exception: pass
    def on_play_start(self):
        Logger.info(str("PhysicsPlugin play start"))
        self._scanned_entity_ids.clear(); self._last_entity_count = -1; self._prev_frame_contacts.clear()
        self._collision_listener_sig = None; self._collision_cache_valid = False
        self._clear_soft_remote()
        if self._engine is None: return
        scene = self._engine.scene
        if scene is None: return
        if self._simulation_mode == "single":
            if self._physics_scene is None: return
            self._physics_scene.load_scene(scene)
            Logger.info(str("PhysicsPlugin single loaded"))
        elif self._simulation_mode == "per_layer_process":
            for proc in self._layer_processes.values(): proc.drain()
            self._layer_processes.clear()
            layer_bodies: dict[int, list[dict]] = {}
            for entity in scene.get_all_entities():
                rb = entity._components.get("Rigidbody"); rb2d = entity._components.get("Rigidbody2D"); tr = entity._components.get("Transform")
                if (not rb and not rb2d) or not tr: continue
                layer = self._get_entity_layer(entity)
                proc = self._get_layer_process(layer)
                bd = self._body_with_slot_in_process(entity, tr, proc)
                if bd: layer_bodies.setdefault(layer, []).append(bd)
            for layer, bodies in layer_bodies.items(): self._layer_processes[layer].send({"type": "load_bodies", "bodies": bodies})
            for layer, proc in list(self._layer_processes.items()):
                if proc.wait_for_result("load_bodies", timeout=5.0) is None: Logger.error(str("PhysicsPlugin layer timeout"))
            Logger.info(str("PhysicsPlugin layers loaded"))
            layer_softs: dict[int, list[dict]] = {}
            try:
                for entity in scene.get_all_entities():
                    try:
                        from core.components.physics.soft_body import SoftBody
                        soft = entity.get_component(SoftBody)
                    except Exception: continue
                    if soft is None or not getattr(soft, "enabled", True): continue
                    tr = entity._components.get("Transform")
                    if tr is None: continue
                    if entity.id in self._soft_remote: continue
                    layer = self._get_entity_layer(entity)
                    proc = self._get_layer_process(layer)
                    d = self._build_soft_dict(entity, tr, soft, proc)
                    if d is None: continue
                    self._track_soft_dict(entity, soft, tr, proc, d["slot"], d)
                    layer_softs.setdefault(layer, []).append(d)
            except Exception: layer_softs = {}
            for layer, softs in layer_softs.items(): self._layer_processes[layer].send({"type": "load_soft_bodies", "softs": softs})
            for layer, proc in list(self._layer_processes.items()):
                if layer not in layer_softs: continue
                ack = proc.wait_for_result("soft_loaded", timeout=60.0)
                if ack is None: Logger.error(str("PhysicsPlugin soft timeout"))
                else: self._harvest_soft_created(proc, scene, [ack])
        else:
            try: self._play_gen += 1
            except Exception: self._play_gen = 1
            try: _gen = self._play_gen
            except Exception: _gen = 1
            try: _old_proc = self._physics_process
            except Exception: _old_proc = None
            try: self._physics_process = None
            except Exception: pass
            try: self._step_caches.clear()
            except Exception: pass
            try: self._clear_soft_remote()
            except Exception: pass
            try: _sm, _sc = self._solver_module_class(); _settings = self._get_physics_settings()
            except Exception: _sm, _sc, _settings = None, None, None
            if _sm is None:
                Logger.error(str("PhysicsPlugin start failed"))
                return
            try:
                _t = threading.Thread(target=self._bringup_process_async, args=(_gen, scene, _sm, _sc, _settings, _old_proc), daemon=True)
                _t.start()
            except Exception:
                try: self._bringup_process_async(_gen, scene, _sm, _sc, _settings, _old_proc)
                except Exception: pass
    def on_play_stop(self):
        try: self._play_gen += 1
        except Exception: self._play_gen = 1
        self._scanned_entity_ids.clear(); self._last_entity_count = -1; self._prev_frame_contacts.clear()
        self._clear_soft_remote()
        self._reset_entity_velocities()
        if self._simulation_mode == "per_layer_process":
            for proc in self._layer_processes.values(): proc.clear_slots(); proc.clear_soft_slots(); self._unload_no_wait(proc)
        elif self._simulation_mode == "single":
            if self._physics_scene: self._physics_scene.shutdown()
        else:
            if self._physics_process:
                self._physics_process.clear_slots(); self._physics_process.clear_soft_slots()
                if not self._unload_no_wait(self._physics_process):
                    try: self._physics_process.shutdown(500)
                    except Exception: pass
                    try: self._physics_process = None
                    except Exception: pass
            self._step_caches.clear()
    def pre_step(self, dt: float):
        if not self._enabled: return
        if not self._engine or not self._engine.scene: return
        scene = self._engine.scene
        if self._simulation_mode == "single":
            if self._physics_scene is None: return
            entity_count = len(scene._entities)
            if entity_count != self._last_entity_count or not self._scanned_entity_ids:
                self._last_entity_count = entity_count
                scanned = self._scanned_entity_ids
                for eid, entity in scene._entities.items():
                    if eid in scanned: continue
                    scanned.add(eid)
                    try: self._physics_scene._create_entity_soft(entity)
                    except Exception: pass
                    rb = entity._components.get("Rigidbody"); rb2d = entity._components.get("Rigidbody2D"); tr = entity._components.get("Transform")
                    if (not rb and not rb2d) or not tr: continue
                    if eid in self._physics_scene._entity_to_body: continue
                    self._physics_scene._create_entity_bodies(entity)
            return
        if self._simulation_mode == "per_layer_process":
            entities_dict = scene._entities
            for eid, entity in entities_dict.items():
                if eid in self._scanned_entity_ids: continue
                self._scanned_entity_ids.add(eid)
                tr = entity._components.get("Transform")
                if tr is not None and eid not in self._soft_remote:
                    try:
                        from core.components.physics.soft_body import SoftBody
                        soft = entity.get_component(SoftBody)
                    except Exception: soft = None
                    if soft is not None and getattr(soft, "enabled", True):
                        try: layer = self._get_entity_layer(entity); proc = self._get_layer_process(layer)
                        except Exception: proc = None
                        if proc is not None:
                            try: d = self._build_soft_dict(entity, tr, soft, proc)
                            except Exception: d = None
                            if d is not None:
                                self._track_soft_dict(entity, soft, tr, proc, d["slot"], d)
                                try: proc.send({"type": "add_soft_body", "soft": d})
                                except Exception: pass
                rb = entity._components.get("Rigidbody"); rb2d = entity._components.get("Rigidbody2D")
                if (not rb and not rb2d) or not tr: continue
                layer = self._get_entity_layer(entity)
                if layer in self._layer_processes: proc = self._layer_processes[layer]
                else: proc = self._get_layer_process(layer)
                if eid in proc.entity_slot_map: continue
                bd = self._body_with_slot_in_process(entity, tr, proc)
                if bd: proc.send({"type": "add_body", "body": bd})
            return
        if self._physics_process is None: return
        entities_dict = scene._entities
        entity_count = len(entities_dict)
        if entity_count != self._last_entity_count or not self._scanned_entity_ids:
            self._last_entity_count = entity_count
            scanned = self._scanned_entity_ids
            for eid, entity in entities_dict.items():
                if eid in scanned: continue
                scanned.add(eid)
                tr = entity._components.get("Transform")
                if tr is not None and eid not in self._soft_remote:
                    try:
                        from core.components.physics.soft_body import SoftBody
                        soft = entity.get_component(SoftBody)
                    except Exception: soft = None
                    if soft is not None and getattr(soft, "enabled", True):
                        try: d = self._build_soft_dict(entity, tr, soft, self._physics_process)
                        except Exception: d = None
                        if d is not None:
                            self._track_soft_dict(entity, soft, tr, self._physics_process, d["slot"], d)
                            try: self._physics_process.send({"type": "add_soft_body", "soft": d})
                            except Exception: pass
                rb = entity._components.get("Rigidbody"); rb2d = entity._components.get("Rigidbody2D")
                if (not rb and not rb2d) or not tr: continue
                if eid in self._physics_process.entity_slot_map: continue
                bd = self._body_with_slot(entity, tr)
                if bd: self._physics_process.send({"type": "add_body", "body": bd})
    def step(self, dt: float):
        if not self._enabled: return
        if not self._engine or not self._engine.scene: return
        scene = self._engine.scene
        prof = self._engine.profiler
        if self._simulation_mode == "single":
            if self._physics_scene is None: return
            prof.start("physics_step"); self._physics_scene.step(dt); prof.stop("physics_step")
            return
        prof.start("physics_collect_results")
        try: need_coll = self._has_collision_listeners(scene)
        except Exception: need_coll = None
        if self._simulation_mode == "per_layer_process":
            for proc in list(self._layer_processes.values()):
                events = self._step_process(proc, scene, dt, prof, need_coll)
                if events: self._process_collisions(scene, events)
        elif self._physics_process:
            events = self._step_process(self._physics_process, scene, dt, prof, need_coll)
            if events: self._process_collisions(scene, events)
        prof.stop("physics_collect_results")
    def _step_process(self, proc: PhysicsProcess, scene, dt: float, prof, need_coll=None) -> list:
        shared = proc.shared; ets = proc.entity_slot_map; entities = scene._entities
        proc_id = id(proc)
        gen_key = (len(ets), self._cache_version)
        entry = self._step_caches.get(proc_id)
        if entry is None or entry[0] != gen_key: self._step_caches[proc_id] = (gen_key, self._rebuild_step_cache(proc, entities))
        _cache = self._step_caches[proc_id][1]
        pending_results = []
        result = proc.poll()
        while result is not None:
            if result.get("type") == "step_result": pending_results.append(result)
            result = proc.poll()
        if pending_results:
            _read = _COMPILED_SYNC_READ
            if _read is not None: _read(shared, _cache)
            else: self._read_results_python(shared, _cache)
            try:
                if scene._dirty_roots: scene._transform_version_pending = True
            except Exception: pass
        if need_coll is None:
            try: need_coll = self._has_collision_listeners(scene)
            except Exception: need_coll = True
        if not need_coll:
            for r in pending_results:
                if r.get("collision_events"): self._prev_frame_contacts.clear(); break
            events_accum = []
        else:
            events_accum = []
            for r in pending_results:
                ev = r.get("collision_events", [])
                if ev:
                    if len(events_accum) + len(ev) > 2048: events_accum.extend(ev[: max(0, 2048 - len(events_accum))])
                    else: events_accum.extend(ev)
        _write = _COMPILED_SYNC_WRITE
        if _write is not None: max_slot = _write(shared, _cache)
        else: max_slot = self._write_inputs_python(shared, _cache)
        shared.set_num_entities(max_slot + 1 if max_slot >= 0 else 0)
        if need_coll is None:
            try: need_coll = self._has_collision_listeners(scene)
            except Exception: need_coll = True
        soft_velocities = None
        try: soft_velocities = self._sync_soft_remote(proc, scene, dt, pending_results)
        except Exception: soft_velocities = None
        msg = {"type": "step", "dt": dt, "need_collisions": need_coll}
        if soft_velocities: msg["soft_velocities"] = soft_velocities
        proc.send(msg)
        return events_accum
    def _has_collision_listeners(self, scene) -> bool:
        if scene is None: return False
        sig = (len(scene._entities), sum(len(e._components) for e in scene._entities.values()))
        if sig != self._collision_listener_sig: self._collision_listener_sig = sig; self._collision_cache_valid = False
        if self._collision_cache_valid: return self._has_collision_cache
        self._collision_cache_valid = True; self._has_collision_cache = False
        for ent in scene._entities.values():
            for comp in ent._components.values():
                if type(comp).__name__ == "ScriptComponent":
                    inst = getattr(comp, "_py_instance", None)
                    if inst is None: continue
                    if hasattr(inst, "on_collision_enter") or hasattr(inst, "on_collision_stay") or hasattr(inst, "on_collision_exit"): self._has_collision_cache = True; return True
                elif hasattr(comp, "on_collision_enter"): self._has_collision_cache = True; return True
        return False
    def _process_collisions(self, scene, events: list):
        if not events: return
        if len(events) > 2048: events = events[:2048]
        entities = scene._entities
        current: set = set()
        forces: dict = {}
        for ev in events:
            ea, eb = ev.get("entity_a", ""), ev.get("entity_b", "")
            if ea and eb:
                if ea > eb: ea, eb = eb, ea
                pair = (ea, eb)
                if pair not in current: current.add(pair); forces[pair] = float(ev.get("force", 0.0) or 0.0)
                else:
                    f = float(ev.get("force", 0.0) or 0.0)
                    if f > forces[pair]: forces[pair] = f
        prev = self._prev_frame_contacts
        entered = current - prev; exited = prev - current; stayed = current & prev
        for pair in entered:
            e0, e1 = pair
            self._dispatch_collision(entities, e0, e1, "on_collision_enter", forces.get(pair, 0.0))
            self._dispatch_collision(entities, e1, e0, "on_collision_enter", forces.get(pair, 0.0))
        for pair in exited:
            e0, e1 = pair
            self._dispatch_collision(entities, e0, e1, "on_collision_exit", forces.get(pair, 0.0))
            self._dispatch_collision(entities, e1, e0, "on_collision_exit", forces.get(pair, 0.0))
        for pair in stayed:
            e0, e1 = pair
            self._dispatch_collision(entities, e0, e1, "on_collision_stay", forces.get(pair, 0.0))
            self._dispatch_collision(entities, e1, e0, "on_collision_stay", forces.get(pair, 0.0))
        self._prev_frame_contacts = current
    def _dispatch_collision(self, entities, eid: str, other_eid: str, callback: str, force: float = 0.0):
        entity = entities.get(eid)
        if not entity: return
        from core.components import ScriptComponent
        for sc in entity.get_components(ScriptComponent):
            inst = sc._py_instance
            if inst and hasattr(inst, callback):
                try:
                    if getattr(sc, "_py_collision_arity", {}).get(callback, 1) >= 2: getattr(inst, callback)(other_eid, force)
                    else: getattr(inst, callback)(other_eid)
                except Exception: Logger.error(str("Script collision error"))
        for comp in entity.get_all_components():
            if isinstance(comp, ScriptComponent): continue
            if hasattr(comp, callback):
                try: getattr(comp, callback)(other_eid, force)
                except Exception: Logger.error(str("Component collision error"))
