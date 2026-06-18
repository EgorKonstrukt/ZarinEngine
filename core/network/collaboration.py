from __future__ import annotations
import json
import time
import uuid
import threading
import asyncio
from typing import Optional, Callable
from PyQt6.QtCore import QTimer
from core.logger import Logger
from core.network.protocol import MessageType
from core.network.server import CollabServer
from core.network.client import CollabClient
from core.ecs import Scene, Entity, ComponentRegistry
from core.config import get_global_config


class RemotePeer:
    __slots__ = ("peer_id", "name", "color", "cursor_screen", "cursor_hit",
                 "camera_pos", "camera_fwd", "camera_up",
                 "selected_entity_ids", "transform_data", "last_seen",
                 "ping_ms", "ping_timestamp",
                 "gizmo_mode", "gizmo_hover_axis", "gizmo_dragging")

    def __init__(self, peer_id: str, name: str, color: list[float]):
        self.peer_id = peer_id
        self.name = name
        self.color = color
        self.cursor_screen: tuple[float, float] = (0, 0)
        self.cursor_hit: Optional[list[float]] = None
        self.camera_pos: list[float] = [0, 0, 0]
        self.camera_fwd: list[float] = [0, 0, -1]
        self.camera_up: list[float] = [0, 1, 0]
        self.selected_entity_ids: list[str] = []
        self.transform_data: dict[str, dict] = {}
        self.last_seen: float = time.time()
        self.ping_ms: float = 0.0
        self.ping_timestamp: float = 0.0
        self.gizmo_mode: str = "none"
        self.gizmo_hover_axis: int = -1
        self.gizmo_dragging: bool = False


class CollabSettings:
    __slots__ = ("cursor_interval", "camera_interval", "transform_interval",
                 "gizmo_interval", "ping_interval", "poll_interval", "scene_sync_interval")

    def __init__(self):
        self.cursor_interval: float = 1.0 / 30.0
        self.camera_interval: float = 1.0 / 15.0
        self.transform_interval: float = 1.0 / 20.0
        self.gizmo_interval: float = 1.0 / 10.0
        self.ping_interval: float = 3.0
        self.poll_interval: int = 8
        self.scene_sync_interval: float = 1.0


class CollaborationManager:
    def __init__(self, engine):
        self._engine = engine
        self._server: Optional[CollabServer] = None
        self._client: Optional[CollabClient] = None
        self._peers: dict[str, RemotePeer] = {}
        self._own_name: str = "User"
        self._scene_snapshot_callback: Optional[Callable] = None
        self._on_scene_sync: Optional[Callable[[dict], bool]] = None
        self._peer_joined_callback: Optional[Callable] = None
        self._peer_left_callback: Optional[Callable] = None
        self._entity_synced_ids: dict[str, str] = {}
        self._local_entity_ids: dict[str, str] = {}
        self._pending_scene_sync = False
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_messages)
        self._poll_timer.setInterval(8)
        self._poll_timer.start()
        self._as_host = False
        self._server_ready: Optional[threading.Event] = None
        self._play_mode_active = False
        self._latency_ms: float = 0.0
        self._ping_timestamp: float = 0.0
        self.settings = CollabSettings()
        self._load_settings_from_config()
        self._ping_timer = QTimer()
        self._ping_timer.timeout.connect(self._send_ping)
        self._ping_timer.setInterval(int(self.settings.ping_interval * 1000))
        self._ping_timer.start()
        self._poll_timer.setInterval(self.settings.poll_interval)

    @property
    def peers(self) -> dict[str, RemotePeer]:
        return self._peers

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.connected

    @property
    def is_host(self) -> bool:
        return self._as_host

    @property
    def own_peer_id(self) -> Optional[str]:
        return self._client.peer_id if self._client else None

    @property
    def play_mode_active(self) -> bool:
        return self._play_mode_active

    @property
    def bytes_sent(self) -> int:
        return self._client.bytes_sent if self._client else 0

    @property
    def bytes_received(self) -> int:
        return self._client.bytes_received if self._client else 0

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    def set_scene_snapshot_callback(self, cb: Callable):
        self._scene_snapshot_callback = cb

    def set_on_scene_sync(self, cb: Callable[[dict], bool]):
        self._on_scene_sync = cb

    def set_peer_joined_callback(self, cb: Callable):
        self._peer_joined_callback = cb

    def set_peer_left_callback(self, cb: Callable):
        self._peer_left_callback = cb

    def get_peer(self, peer_id: str) -> Optional[RemotePeer]:
        return self._peers.get(peer_id)

    def start_server(self, host: str = "0.0.0.0", port: int = 9876):
        if self._client:
            self.stop()
        self._as_host = True
        self._server = CollabServer(host, port)
        self._server_thread_task = None

        self._server_ready = threading.Event()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._server.start())
            self._server_ready.set()
            loop.run_forever()

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()
        self._server_ready.wait(timeout=5)
        Logger.info(f"Collab server started on {host}:{port}")

    def connect(self, host: str = "127.0.0.1", port: int = 9876, name: str = "User"):
        if self._client:
            self.stop()
        if self._server and self._engine.scene:
            self.update_server_scene(self._engine.scene)
        self._own_name = name
        self._as_host = False
        self._client = CollabClient()
        self._client.set_on_disconnected(self._on_disconnected)
        self._client.connect(host, port, name)

    def stop(self):
        if self._client:
            self._client.disconnect()
            self._client = None
        if self._server:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._server.stop())
                loop.close()
            except Exception:
                pass
            self._server = None
        self._peers.clear()
        self._entity_synced_ids.clear()
        self._local_entity_ids.clear()
        self._as_host = False
        Logger.info("Collab stopped")

    def _on_disconnected(self):
        self._peers.clear()
        Logger.info("Collab disconnected")

    def _poll_messages(self):
        if not self._client or not self._client.connected:
            return
        msgs = self._client.poll_messages()
        for msg_type, data in msgs:
            self._handle_message(msg_type, data)
        self._sync_server_scene()

    def _sync_server_scene(self):
        if not self._as_host or not self._server:
            return
        now = time.time()
        if now - getattr(self, "_last_scene_sync", 0) < 1.0:
            return
        self._last_scene_sync = now
        scene = self._engine.scene
        if scene:
            self.update_server_scene(scene)

    def _handle_message(self, msg_type: int, data: dict):
        if msg_type == MessageType.JOINED:
            peers_raw = data.get("peers", [])
            for p in peers_raw:
                pid = p["id"]
                if pid not in self._peers and pid != self._client.peer_id:
                    self._add_peer(pid, p["name"], p["color"])
            if data.get("scene"):
                self._apply_scene_snapshot(data["scene"])
            if self._scene_snapshot_callback:
                self._scene_snapshot_callback(data)
        elif msg_type == MessageType.PEER_JOINED:
            pid = data.get("id", "")
            if pid and pid not in self._peers and pid != self._client.peer_id:
                self._add_peer(pid, data.get("name", ""), data.get("color", [0.5, 0.5, 0.5]))
        elif msg_type == MessageType.LEAVE:
            pid = data.get("id", "")
            if pid in self._peers:
                peer = self._peers.pop(pid)
                if self._peer_left_callback:
                    self._peer_left_callback(peer)
        elif msg_type == MessageType.CURSOR_UPDATE:
            pid = data.get("id", "")
            peer = self._peers.get(pid)
            if peer:
                peer.cursor_screen = (data.get("x", 0), data.get("y", 0))
                peer.cursor_hit = data.get("hit")
                peer.last_seen = time.time()
        elif msg_type == MessageType.CAMERA_UPDATE:
            pid = data.get("id", "")
            peer = self._peers.get(pid)
            if peer:
                peer.camera_pos = data.get("pos", [0, 0, 0])
                peer.camera_fwd = data.get("fwd", [0, 0, -1])
                peer.camera_up = data.get("up", [0, 1, 0])
        elif msg_type == MessageType.ENTITY_CREATED:
            pid = data.get("id", "")
            if pid != self._client.peer_id:
                entity_data = data.get("entity", {})
                self._create_remote_entity(entity_data)
        elif msg_type == MessageType.ENTITY_DELETED:
            pid = data.get("id", "")
            if pid != self._client.peer_id:
                entity_id = data.get("entity_id", "")
                self._delete_remote_entity(entity_id)
        elif msg_type == MessageType.TRANSFORM_UPDATED:
            pid = data.get("id", "")
            if pid != self._client.peer_id:
                self._apply_remote_transform(data)
        elif msg_type == MessageType.SELECTION_UPDATE:
            pid = data.get("id", "")
            peer = self._peers.get(pid)
            if peer:
                peer.selected_entity_ids = data.get("entity_ids", [])
        elif msg_type == MessageType.COMPONENT_UPDATED:
            pid = data.get("id", "")
            if pid != self._client.peer_id:
                self._apply_remote_component(data)
        elif msg_type == MessageType.COMPONENT_ADDED:
            pid = data.get("id", "")
            if pid != self._client.peer_id:
                self._apply_remote_component_add(data)
        elif msg_type == MessageType.COMPONENT_REMOVED:
            pid = data.get("id", "")
            if pid != self._client.peer_id:
                self._apply_remote_component_remove(data)
        elif msg_type == MessageType.PONG:
            now = time.time()
            self._latency_ms = (now - self._ping_timestamp) * 500
        elif msg_type == MessageType.PLAY_MODE:
            self._play_mode_active = data.get("active", False)
        elif msg_type == MessageType.COMPONENT_SYNC:
            pid = data.get("id", "")
            if pid != self._client.peer_id:
                self._apply_remote_component_sync(data)
        elif msg_type == MessageType.GIZMO_STATE_UPDATE:
            pid = data.get("id", "")
            peer = self._peers.get(pid)
            if peer:
                peer.gizmo_mode = data.get("mode", "none")
                peer.gizmo_hover_axis = data.get("hover", -1)
                peer.gizmo_dragging = data.get("dragging", False)
        elif msg_type == MessageType.SCENE_SNAPSHOT:
            scene_data = data.get("scene")
            req_id = data.get("requesting_id", "")
            if req_id and req_id != self._client.peer_id:
                pass
            elif scene_data:
                self._apply_scene_snapshot(scene_data)

    def send_cursor(self, screen_x: float, screen_y: float, hit_pos: Optional[list[float]] = None):
        if self._client and self._client.connected:
            self._client.send(MessageType.CURSOR, {
                "x": screen_x, "y": screen_y, "hit": hit_pos
            })

    def send_camera(self, pos: list[float], fwd: list[float], up: list[float]):
        if self._client and self._client.connected:
            self._client.send(MessageType.CAMERA, {
                "pos": pos, "fwd": fwd, "up": up
            })

    def send_entity_create(self, entity_data: dict):
        if self._client and self._client.connected:
            self._client.send(MessageType.ENTITY_CREATE, {"entity": entity_data})

    def send_entity_delete(self, entity_id: str):
        if self._client and self._client.connected:
            self._client.send(MessageType.ENTITY_DELETE, {"entity_id": entity_id})

    def send_transform(self, entity_id: str, pos: list[float], rot: list[float], scale: list[float]):
        if self._client and self._client.connected:
            self._client.send(MessageType.TRANSFORM_UPDATE, {
                "entity_id": entity_id, "p": pos, "r": rot, "s": scale
            })

    def send_selection(self, entity_ids: list[str]):
        if self._client and self._client.connected:
            self._client.send(MessageType.SELECTION, {"entity_ids": entity_ids})

    def send_component_update(self, entity_id: str, component_key: str,
                              prop: str, value):
        if self._client and self._client.connected:
            self._client.send(MessageType.COMPONENT_UPDATE, {
                "entity_id": entity_id, "component_key": component_key,
                "prop": prop, "value": value
            })

    def send_component_sync(self, entity_id: str, component_key: str, data: dict):
        if self._client and self._client.connected:
            self._client.send(MessageType.COMPONENT_SYNC, {
                "entity_id": entity_id, "component_key": component_key, "data": data
            })

    def send_component_add(self, entity_id: str, component_key: str, comp_data: dict):
        if self._client and self._client.connected:
            self._client.send(MessageType.COMPONENT_ADD, {
                "entity_id": entity_id, "component_key": component_key, "data": comp_data
            })

    def send_component_remove(self, entity_id: str, component_key: str):
        if self._client and self._client.connected:
            self._client.send(MessageType.COMPONENT_REMOVE, {
                "entity_id": entity_id, "component_key": component_key
            })

    def send_play_mode(self, active: bool):
        if self._client and self._client.connected:
            self._client.send(MessageType.PLAY_MODE, {"active": active})
            self._play_mode_active = active

    def apply_settings(self):
        self._ping_timer.setInterval(int(self.settings.ping_interval * 1000))
        self._poll_timer.setInterval(self.settings.poll_interval)

    def _load_settings_from_config(self):
        cfg = get_global_config()
        s = self.settings
        s.cursor_interval = 1.0 / max(1, cfg.get("collab.cursor_rate", 30.0))
        s.camera_interval = 1.0 / max(1, cfg.get("collab.camera_rate", 15.0))
        s.transform_interval = 1.0 / max(1, cfg.get("collab.transform_rate", 20.0))
        s.gizmo_interval = 1.0 / max(1, cfg.get("collab.gizmo_rate", 10.0))
        s.ping_interval = cfg.get("collab.ping_interval", 3.0)
        s.poll_interval = cfg.get("collab.poll_interval", 8)

    def save_settings_to_config(self):
        cfg = get_global_config()
        s = self.settings
        cfg.set("collab.cursor_rate", 1.0 / max(0.001, s.cursor_interval))
        cfg.set("collab.camera_rate", 1.0 / max(0.001, s.camera_interval))
        cfg.set("collab.transform_rate", 1.0 / max(0.001, s.transform_interval))
        cfg.set("collab.gizmo_rate", 1.0 / max(0.001, s.gizmo_interval))
        cfg.set("collab.ping_interval", s.ping_interval)
        cfg.set("collab.poll_interval", s.poll_interval)
        cfg.save()

    def send_gizmo_state(self, mode: str, hover_axis: int, dragging: bool):
        if self._client and self._client.connected:
            self._client.send(MessageType.GIZMO_STATE, {
                "mode": mode, "hover": hover_axis, "dragging": dragging
            })

    def _send_ping(self):
        if self._client and self._client.connected:
            self._ping_timestamp = time.time()
            self._client.send(MessageType.PING, {"t": self._ping_timestamp})

    def request_scene_snapshot(self):
        if self._client and self._client.connected:
            self._client.send(MessageType.SCENE_SNAPSHOT_REQ, {})

    def update_server_scene(self, scene: Scene):
        if self._server:
            data = scene.serialize()
            self._server.update_scene_data(data)

    def _add_peer(self, peer_id: str, name: str, color: list[float]):
        if peer_id not in self._peers:
            peer = RemotePeer(peer_id, name, color)
            self._peers[peer_id] = peer
            if self._peer_joined_callback:
                self._peer_joined_callback(peer)

    def _apply_scene_snapshot(self, scene_data: dict):
        scene = self._engine.scene
        if not scene:
            return
        if self._on_scene_sync:
            if not self._on_scene_sync(scene_data):
                return
        self._engine.load_scene_from_data(scene_data)

    def _create_remote_entity(self, entity_data: dict):
        scene = self._engine.scene
        if not scene:
            return
        eid = entity_data.get("id", "")
        if eid and eid not in scene._entities:
            e = Entity.deserialize(entity_data, ComponentRegistry)
            scene.add_entity(e)
            pid = entity_data.get("parent")
            if pid and pid in scene._entities:
                parent = scene._entities.get(pid)
                if parent:
                    e.set_parent(parent)

    def _delete_remote_entity(self, entity_id: str):
        scene = self._engine.scene
        if scene and entity_id in scene._entities:
            scene.remove_entity(entity_id)

    def _apply_remote_transform(self, data: dict):
        scene = self._engine.scene
        if not scene:
            return
        entity_id = data.get("entity_id", "")
        e = scene.get_entity(entity_id)
        if not e:
            return
        t = e.get_component_by_name("Transform")
        if not t:
            return
        p = data.get("p")
        r = data.get("r")
        s = data.get("s")
        if p:
            t.local_position = p
        if r:
            from core.math3d import Quat
            t.local_rotation = Quat(r[0], r[1], r[2], r[3])
        if s:
            t.local_scale = s

    def _apply_remote_component_sync(self, data: dict):
        scene = self._engine.scene
        if not scene:
            return
        entity_id = data.get("entity_id", "")
        e = scene.get_entity(entity_id)
        if not e:
            return
        comp_key = data.get("component_key", "")
        comp_data = data.get("data", {})
        comp = e.get_component_by_name(comp_key)
        if comp:
            for k, v in comp_data.items():
                if hasattr(comp, k):
                    try:
                        setattr(comp, k, v)
                    except Exception:
                        pass
        else:
            registry = ComponentRegistry
            if comp_key in registry._component_types:
                comp_cls = registry._component_types[comp_key]
                comp = comp_cls.deserialize(comp_data)
                if comp:
                    e.add_component(comp)

    def _apply_remote_component(self, data: dict):
        scene = self._engine.scene
        if not scene:
            return
        entity_id = data.get("entity_id", "")
        e = scene.get_entity(entity_id)
        if not e:
            return
        comp_key = data.get("component_key", "")
        comp = e.get_component_by_name(comp_key)
        if not comp:
            return
        prop = data.get("prop", "")
        value = data.get("value")
        if not hasattr(comp, prop):
            return
        try:
            current = getattr(comp, prop)
            if hasattr(current, 'from_list') and isinstance(value, list):
                current.from_list(value)
            elif hasattr(current, 'x') and isinstance(value, (list, tuple)) and len(value) == 3:
                from core.math3d import Vec3
                setattr(comp, prop, Vec3(value[0], value[1], value[2]))
            elif hasattr(current, 'x') and isinstance(value, (list, tuple)) and len(value) == 4:
                from core.math3d import Quat
                setattr(comp, prop, Quat(value[0], value[1], value[2], value[3]))
            else:
                setattr(comp, prop, value)
        except Exception as e:
            Logger.warning(f"Collab: apply remote component error: {e}")

    def _apply_remote_component_add(self, data: dict):
        scene = self._engine.scene
        if not scene:
            return
        entity_id = data.get("entity_id", "")
        e = scene.get_entity(entity_id)
        if not e:
            return
        comp_key = data.get("component_key", "")
        comp_data = data.get("data", {})
        from core.ecs import ComponentRegistry
        registry = ComponentRegistry
        comp_cls = registry.get(comp_key)
        if not comp_cls:
            return
        can_multiple = getattr(comp_cls, '_allow_multiple', False)
        if not can_multiple and e.get_component_by_name(comp_key):
            return
        comp = comp_cls.deserialize(comp_data)
        if comp:
            e.add_component(comp)

    def _apply_remote_component_remove(self, data: dict):
        scene = self._engine.scene
        if not scene:
            return
        entity_id = data.get("entity_id", "")
        e = scene.get_entity(entity_id)
        if not e:
            return
        comp_key = data.get("component_key", "")
        for key in list(e._components.keys()):
            if key == comp_key or key.startswith(comp_key + "."):
                e.remove_component_by_key(key)
                return
