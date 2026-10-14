# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
from typing import Optional
from core.foundation.logger import Logger
from core.network.protocol import MessageType
from core.ecs import Scene, Entity, ComponentRegistry
class SceneSyncMixin:
    @property
    def current_tab(self) -> str:
        return self._current_tab
    def set_current_tab(self, tab_name: str):
        self._current_tab = str(tab_name or "")
    def send_scene_open(self, name: str, path: str, data: dict):
        ok = self._send_link(MessageType.SCENE_OPEN, {"name": str(name), "path": str(path), "data": dict(data)})
        if not ok:
            Logger.warning("Collab scene_open not sent: offline")
    def send_scene_tab_switch(self, name: str):
        self._send_link(MessageType.SCENE_TAB_SWITCH, {"name": str(name)})
    def send_scene_tab_close(self, name: str):
        self._send_link(MessageType.SCENE_TAB_CLOSE, {"name": str(name)})
    def _send_full_scene_sync(self, target_peer_id: str):
        if not self._current_tab:
            return
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if not scene:
            return
        try:
            entities = list(scene._entities.items())
        except Exception:
            return
        for eid, entity in entities:
            try:
                entity_data = entity.serialize()
            except Exception:
                continue
            self._send_link(MessageType.ENTITY_CREATE, self._with_tab({"entity": entity_data, "target": str(target_peer_id)}))
            try:
                t = entity.transform
            except Exception:
                t = None
            if t is not None:
                try:
                    pos = t.local_position.to_list()
                    rot = t.local_rotation.to_list()
                    scl = t.local_scale.to_list()
                    self._send_link(MessageType.TRANSFORM_UPDATE, self._with_tab({"entity_id": eid, "p": pos, "r": rot, "s": scl, "target": str(target_peer_id)}))
                except Exception:
                    pass
    def send_entity_create(self, entity_data: dict):
        self._send_link(MessageType.ENTITY_CREATE, self._with_tab({"entity": dict(entity_data)}))
    def send_entity_delete(self, entity_id: str):
        self._send_link(MessageType.ENTITY_DELETE, self._with_tab({"entity_id": str(entity_id)}))
    def send_transform(self, entity_id: str, pos: list[float], rot: list[float], scale: list[float]):
        self._send_link(MessageType.TRANSFORM_UPDATE, self._with_tab({"entity_id": str(entity_id), "p": list(pos), "r": list(rot), "s": list(scale)}))
    def send_selection(self, entity_ids: list[str]):
        self._send_link(MessageType.SELECTION, self._with_tab({"entity_ids": list(entity_ids)}))
    @staticmethod
    def _collapse_value(v):
        if hasattr(v, 'to_list'):
            try:
                return v.to_list()
            except Exception:
                pass
        if hasattr(v, '__iter__') and not isinstance(v, (str, bytes, dict)):
            try:
                return list(v)
            except Exception:
                pass
        if isinstance(v, dict):
            return {k: SceneSyncMixin._collapse_value(v) for k, v in v.items()}
        return v
    def send_component_update(self, entity_id: str, component_key: str, prop: str, value):
        self._send_link(MessageType.COMPONENT_UPDATE, self._with_tab({"entity_id": str(entity_id), "component_key": str(component_key), "prop": str(prop), "value": self._collapse_value(value)}))
    def send_component_sync(self, entity_id: str, component_key: str, data: dict):
        self._send_link(MessageType.COMPONENT_SYNC, self._with_tab({"entity_id": str(entity_id), "component_key": str(component_key), "data": self._collapse_value(dict(data))}))
    def send_component_add(self, entity_id: str, component_key: str, comp_data: dict):
        self._send_link(MessageType.COMPONENT_ADD, self._with_tab({"entity_id": str(entity_id), "component_key": str(component_key), "data": self._collapse_value(dict(comp_data))}))
    def send_component_remove(self, entity_id: str, component_key: str):
        self._send_link(MessageType.COMPONENT_REMOVE, self._with_tab({"entity_id": str(entity_id), "component_key": str(component_key)}))
    def send_play_mode(self, active: bool):
        self._send_link(MessageType.PLAY_MODE, {"active": bool(active)})
        self._play_mode_active = bool(active)
    def request_scene_snapshot(self):
        self._send_link(MessageType.SCENE_SNAPSHOT_REQ, {})
    def update_server_scene(self, scene: Scene):
        if self._server:
            try:
                data = scene.serialize()
                self._server.update_scene_data(data)
                self._last_scene_hash = self._scene_hash(scene)
            except Exception as e:
                Logger.warning(f"Collab scene snapshot failed: {e}")
    def _apply_scene_snapshot(self, scene_data: dict):
        try:
            tab_name = str(scene_data.get("name", "SyncedScene"))
            path = str(scene_data.get("path", ""))
        except Exception:
            return
        if self._on_remote_scene_open:
            try:
                self._on_remote_scene_open({"name": tab_name, "path": path, "data": scene_data})
            except Exception:
                pass
    def _create_remote_entity(self, entity_data: dict):
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if not scene:
            return
        eid = str(entity_data.get("id", ""))
        if not eid:
            return
        try:
            entities = scene._entities
        except Exception:
            return
        if eid not in entities:
            try:
                e = Entity.deserialize(entity_data, ComponentRegistry)
            except Exception:
                return
            try:
                scene.add_entity(e)
            except Exception:
                return
            try:
                pid = entity_data.get("parent")
                if pid and pid in entities:
                    parent = entities.get(pid)
                    if parent:
                        e.set_parent(parent)
            except Exception:
                pass
        else:
            try:
                e = entities[eid]
                for cd in entity_data.get("components", []) if isinstance(entity_data.get("components", []), list) else []:
                    try:
                        ctype = cd.get("type")
                        comp_cls = ComponentRegistry.get(ctype)
                        if not comp_cls:
                            continue
                        existing = e.get_component(comp_cls)
                        if existing:
                            for k, v in cd.items():
                                if k not in ("type", "_key"):
                                    try:
                                        setattr(existing, k, v)
                                    except Exception:
                                        pass
                        else:
                            try:
                                comp = comp_cls.deserialize(cd)
                                e.add_component(comp)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass
    def _delete_remote_entity(self, entity_id: str):
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if scene:
            try:
                if entity_id in scene._entities:
                    scene.remove_entity(entity_id)
            except Exception:
                pass
    def _apply_remote_transform(self, data: dict):
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if not scene:
            return
        entity_id = str(data.get("entity_id", ""))
        try:
            e = scene.get_entity(entity_id)
        except Exception:
            e = None
        if not e:
            return
        try:
            t = e.transform
        except Exception:
            t = None
        if not t:
            return
        p = data.get("p")
        r = data.get("r")
        s = data.get("s")
        if p:
            try:
                from core.maths.math3d import Vec3
                old_local = Vec3(t.local_position.x, t.local_position.y, t.local_position.z)
                t.local_position = p
                pid = str(data.get("id", ""))
                with self._peers_lock:
                    peer = self._peers.get(pid)
                if peer:
                    dx = float(p[0]) - float(old_local.x)
                    dy = float(p[1]) - float(old_local.y)
                    dz = float(p[2]) - float(old_local.z)
                    if abs(dx) > 0.0001 or abs(dy) > 0.0001 or abs(dz) > 0.0001:
                        peer.transform_deltas[entity_id] = {"pos": [dx, dy, dz], "time": time.time()}
            except Exception:
                pass
        if r:
            try:
                from core.maths.math3d import Quat
                t.local_rotation = Quat(r[0], r[1], r[2], r[3])
            except Exception:
                pass
        if s:
            try:
                t.local_scale = s
            except Exception:
                pass
    def _apply_remote_component_sync(self, data: dict):
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if not scene:
            return
        entity_id = str(data.get("entity_id", ""))
        try:
            e = scene.get_entity(entity_id)
        except Exception:
            e = None
        if not e:
            return
        comp_key = str(data.get("component_key", ""))
        comp_data = data.get("data", {})
        if not isinstance(comp_data, dict):
            return
        try:
            comp = e.get_component_by_name(comp_key)
        except Exception:
            comp = None
        if comp:
            for k, v in comp_data.items():
                if not hasattr(comp, k):
                    continue
                try:
                    current = getattr(comp, k)
                    if hasattr(current, 'from_list') and isinstance(v, list):
                        current.from_list(v)
                    elif hasattr(current, 'x') and isinstance(v, (list, tuple)) and len(v) == 3:
                        from core.maths.math3d import Vec3
                        setattr(comp, k, Vec3(v[0], v[1], v[2]))
                    elif hasattr(current, 'x') and isinstance(v, (list, tuple)) and len(v) == 4:
                        from core.maths.math3d import Quat
                        setattr(comp, k, Quat(v[0], v[1], v[2], v[3]))
                    else:
                        setattr(comp, k, v)
                except Exception:
                    pass
        else:
            try:
                registry = ComponentRegistry
                if comp_key in registry._component_types:
                    comp_cls = registry._component_types[comp_key]
                    comp = comp_cls.deserialize(comp_data)
                    if comp:
                        e.add_component(comp)
            except Exception:
                pass
    def _apply_remote_component(self, data: dict):
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if not scene:
            return
        entity_id = str(data.get("entity_id", ""))
        try:
            e = scene.get_entity(entity_id)
        except Exception:
            e = None
        if not e:
            return
        comp_key = str(data.get("component_key", ""))
        try:
            comp = e.get_component_by_name(comp_key)
        except Exception:
            comp = None
        if not comp:
            return
        prop = str(data.get("prop", ""))
        value = data.get("value")
        if not hasattr(comp, prop):
            return
        try:
            current = getattr(comp, prop)
            if hasattr(current, 'from_list') and isinstance(value, list):
                current.from_list(value)
            elif hasattr(current, 'x') and isinstance(value, (list, tuple)) and len(value) == 3:
                from core.maths.math3d import Vec3
                setattr(comp, prop, Vec3(value[0], value[1], value[2]))
            elif hasattr(current, 'x') and isinstance(value, (list, tuple)) and len(value) == 4:
                from core.maths.math3d import Quat
                setattr(comp, prop, Quat(value[0], value[1], value[2], value[3]))
            else:
                setattr(comp, prop, value)
        except Exception as e:
            Logger.warning(f"Collab apply remote component failed: {e}")
    def _apply_remote_component_add(self, data: dict):
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if not scene:
            return
        entity_id = str(data.get("entity_id", ""))
        try:
            e = scene.get_entity(entity_id)
        except Exception:
            e = None
        if not e:
            return
        comp_key = str(data.get("component_key", ""))
        comp_data = data.get("data", {})
        if not isinstance(comp_data, dict):
            return
        from core.ecs import ComponentRegistry
        registry = ComponentRegistry
        try:
            comp_cls = registry.get(comp_key)
        except Exception:
            comp_cls = None
        if not comp_cls:
            return
        try:
            can_multiple = bool(getattr(comp_cls, '_allow_multiple', False))
        except Exception:
            can_multiple = False
        if not can_multiple:
            try:
                if e.get_component_by_name(comp_key):
                    return
            except Exception:
                pass
        try:
            comp = comp_cls.deserialize(comp_data)
            if comp:
                e.add_component(comp)
        except Exception:
            pass
    def _apply_remote_component_remove(self, data: dict):
        scene = None
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if not scene:
            return
        entity_id = str(data.get("entity_id", ""))
        try:
            e = scene.get_entity(entity_id)
        except Exception:
            e = None
        if not e:
            return
        comp_key = str(data.get("component_key", ""))
        try:
            for key in list(e._components.keys()):
                if key == comp_key or key.startswith(comp_key + "."):
                    e.remove_component_by_key(key)
                    return
        except Exception:
            pass
