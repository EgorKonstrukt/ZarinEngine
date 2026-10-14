# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import secrets
import time
from typing import Callable, Optional
import msgpack
from core.foundation.logger import Logger
from core.network.protocol import MessageType, CHUNK_SIZE, CHUNK_THRESHOLD, estimate_msg_size
class PresenceMixin:
    def set_scene_snapshot_callback(self, cb: Callable):
        self._scene_snapshot_callback = cb
    def set_on_scene_sync(self, cb: Callable[[dict], bool]):
        self._on_scene_sync = cb
    def set_peer_joined_callback(self, cb: Callable):
        self._peer_joined_callback = cb
    def set_peer_left_callback(self, cb: Callable):
        self._peer_left_callback = cb
    def set_on_remote_scene_open(self, cb: Callable):
        self._on_remote_scene_open = cb
    def set_on_remote_tab_switch(self, cb: Callable):
        self._on_remote_tab_switch = cb
    def set_on_remote_tab_close(self, cb: Callable):
        self._on_remote_tab_close = cb
    def set_on_remote_script_open(self, cb: Callable):
        self._on_remote_script_open = cb
    def set_on_remote_script_change(self, cb: Callable):
        self._on_remote_script_change = cb
    def set_on_remote_script_cursor(self, cb: Callable):
        self._on_remote_script_cursor = cb
    def set_on_remote_script_ops(self, cb: Callable):
        self._on_remote_script_ops = cb
    def set_on_auth_failed(self, cb: Callable):
        self._on_auth_failed = cb
    def set_on_connection_change(self, cb: Callable):
        self._on_connection_change = cb
    def _notify_status(self):
        cur = bool(self.connected)
        if cur != self._last_status:
            self._last_status = cur
            cb = self._on_connection_change
            if cb is not None:
                try:
                    cb(cur)
                except Exception:
                    pass
    def _send_link(self, msg_type: int, data: dict) -> bool:
        client = self._client
        if client is None:
            return False
        try:
            if not client.connected:
                return False
        except Exception:
            return False
        try:
            payload = dict(data)
        except Exception:
            return False
        try:
            size = estimate_msg_size(int(msg_type), payload)
        except Exception:
            size = 0
        if size > CHUNK_THRESHOLD:
            return self._send_chunked(int(msg_type), payload)
        try:
            return bool(client.send(int(msg_type), payload))
        except Exception:
            return False
    def _send_chunked(self, msg_type: int, data: dict) -> bool:
        client = self._client
        if client is None:
            return False
        try:
            raw = msgpack.packb({"t": int(msg_type), "d": dict(data)}, use_bin_type=True)
        except Exception as e:
            Logger.warning(f"Collab chunk encode failed: {e}")
            return False
        target = ""
        try:
            target = str(dict(data).get("target", ""))
        except Exception:
            target = ""
        transfer_id = secrets.token_hex(8)
        total = (len(raw) + CHUNK_SIZE - 1) // CHUNK_SIZE
        if total > 4096:
            Logger.warning("Collab message too large, dropped")
            return False
        ok = True
        for idx in range(total):
            part = raw[idx * CHUNK_SIZE:(idx + 1) * CHUNK_SIZE]
            envelope = {"cid": transfer_id, "idx": int(idx), "total": int(total), "inner_type": int(msg_type), "part": part}
            if target:
                envelope["target"] = target
            try:
                r = client.send(int(MessageType.CHUNK), envelope)
                if not r:
                    ok = False
            except Exception:
                ok = False
                break
        return ok
    def send_raw(self, msg_type: int, data: dict) -> bool:
        return self._send_link(int(msg_type), dict(data))
    def send_cursor(self, screen_x: float, screen_y: float, hit_pos: Optional[list[float]] = None):
        self._send_link(MessageType.CURSOR, {"x": float(screen_x), "y": float(screen_y), "hit": hit_pos})
    def send_camera(self, pos: list[float], fwd: list[float], up: list[float]):
        self._send_link(MessageType.CAMERA, {"pos": list(pos), "fwd": list(fwd), "up": list(up)})
    def send_gizmo_state(self, mode: str, hover_axis: int, dragging: bool):
        self._send_link(MessageType.GIZMO_STATE, {"mode": str(mode), "hover": int(hover_axis), "dragging": bool(dragging)})
    def _send_ping(self):
        try:
            client = self._client
            if client is None or not client.connected:
                return
            self._ping_timestamp = time.time()
            try:
                client.send(int(MessageType.PING), {"t": float(self._ping_timestamp)})
            except Exception:
                pass
        except Exception:
            pass
    def _with_tab(self, d: dict) -> dict:
        if self._current_tab:
            d["tab"] = self._current_tab
        return d
    def _tab_matches(self, data: dict) -> bool:
        msg_tab = str(data.get("tab", ""))
        return not msg_tab or msg_tab == self._current_tab
    def _touch(self, pid: str):
        if not pid:
            return
        with self._peers_lock:
            p = self._peers.get(pid)
            if p is not None:
                p.last_seen = time.time()
    def _handle_peer_branch(self, msg_type: int, data: dict):
        if msg_type == int(MessageType.JOINED):
            peers_raw = data.get("peers", [])
            own = None
            try:
                own = self._client.peer_id if self._client else None
            except Exception:
                own = None
            for p in peers_raw if isinstance(peers_raw, list) else []:
                try:
                    pid = str(p.get("id", ""))
                except Exception:
                    continue
                if pid and pid not in self.peers and pid != own:
                    try:
                        self._add_peer(pid, str(p.get("name", "")), list(p.get("color", [0.5, 0.5, 0.5])))
                    except Exception:
                        pass
            if data.get("scene"):
                try:
                    self._apply_scene_snapshot(data["scene"])
                except Exception:
                    pass
            if self._scene_snapshot_callback:
                try:
                    self._scene_snapshot_callback(data)
                except Exception:
                    pass
            if not self._as_host:
                try:
                    self.request_asset_list()
                except Exception:
                    pass
            try:
                self._start_asset_watcher()
            except Exception:
                pass
            return True
        if msg_type == int(MessageType.PEER_JOINED):
            pid = str(data.get("id", ""))
            own = None
            try:
                own = self._client.peer_id if self._client else None
            except Exception:
                own = None
            if pid and pid not in self.peers and pid != own:
                try:
                    self._add_peer(pid, str(data.get("name", "")), list(data.get("color", [0.5, 0.5, 0.5])))
                except Exception:
                    pass
                if self._as_host and self._current_tab:
                    try:
                        self._send_full_scene_sync(pid)
                    except Exception:
                        pass
            return True
        if msg_type == int(MessageType.LEAVE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.pop(pid, None)
            if peer is not None and self._peer_left_callback:
                try:
                    self._peer_left_callback(peer)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.AUTH_FAIL):
            self._auth_error = str(data.get("reason", "auth"))
            if self._on_auth_failed is not None:
                try:
                    self._on_auth_failed(str(self._auth_error))
                except Exception:
                    pass
            return True
        return False
    def _handle_presence_branch(self, msg_type: int, data: dict):
        if msg_type == int(MessageType.CURSOR_UPDATE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.get(pid)
            if peer:
                peer.cursor_screen = (float(data.get("x", 0)), float(data.get("y", 0)))
                peer.cursor_hit = data.get("hit")
                peer.last_seen = time.time()
            return True
        if msg_type == int(MessageType.CAMERA_UPDATE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.get(pid)
            if peer:
                try:
                    peer.camera_pos = list(data.get("pos", [0, 0, 0]))
                    peer.camera_fwd = list(data.get("fwd", [0, 0, -1]))
                    peer.camera_up = list(data.get("up", [0, 1, 0]))
                    peer.last_seen = time.time()
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.PONG):
            try:
                t = float(data.get("t", 0))
                now = time.time()
                if t > 0:
                    self._latency_ms = (now - t) * 1000.0
            except Exception:
                pass
            return True
        if msg_type == int(MessageType.PLAY_MODE):
            try:
                self._play_mode_active = bool(data.get("active", False))
            except Exception:
                pass
            self._touch(str(data.get("id", "")))
            return True
        if msg_type == int(MessageType.GIZMO_STATE_UPDATE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.get(pid)
            if peer:
                peer.gizmo_mode = str(data.get("mode", "none"))
                try:
                    peer.gizmo_hover_axis = int(data.get("hover", -1))
                except Exception:
                    peer.gizmo_hover_axis = -1
                peer.gizmo_dragging = bool(data.get("dragging", False))
                peer.last_seen = time.time()
            return True
        return False
    def _handle_scene_branch(self, msg_type: int, data: dict):
        if msg_type == int(MessageType.ENTITY_CREATED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._create_remote_entity(dict(data.get("entity", {})))
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.ENTITY_DELETED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._delete_remote_entity(str(data.get("entity_id", "")))
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.TRANSFORM_UPDATED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_transform(data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.SELECTION_UPDATE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.get(pid)
            if peer:
                try:
                    peer.selected_entity_ids = list(data.get("entity_ids", []))
                    peer.last_seen = time.time()
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.COMPONENT_UPDATED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component(data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.COMPONENT_ADDED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component_add(data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.COMPONENT_REMOVED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component_remove(data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.COMPONENT_SYNC):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component_sync(data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.SCENE_SNAPSHOT):
            try:
                scene_data = data.get("scene")
                req_id = str(data.get("requesting_id", ""))
                own = self.own_peer_id
                if req_id and req_id != own:
                    return True
                if scene_data:
                    self._apply_scene_snapshot(scene_data)
            except Exception:
                pass
            return True
        if msg_type == int(MessageType.SCENE_OPEN):
            pid = str(data.get("id", ""))
            pname = str(data.get("name", ""))
            own = self.own_peer_id
            if pid != own:
                with self._peers_lock:
                    peer = self._peers.get(pid)
                    if peer is not None:
                        peer.current_tab = pname
                        peer.last_seen = time.time()
                if self._on_remote_scene_open:
                    try:
                        self._on_remote_scene_open(data)
                    except Exception:
                        pass
            return True
        if msg_type == int(MessageType.SCENE_TAB_SWITCH):
            pid = str(data.get("id", ""))
            tab = str(data.get("name", ""))
            own = self.own_peer_id
            if pid != own:
                with self._peers_lock:
                    peer = self._peers.get(pid)
                    if peer is not None:
                        peer.current_tab = tab
                        peer.last_seen = time.time()
                if tab and tab == self._current_tab:
                    try:
                        self._send_full_scene_sync(pid)
                    except Exception:
                        pass
                if self._on_remote_tab_switch:
                    try:
                        self._on_remote_tab_switch(pid, tab)
                    except Exception:
                        pass
            return True
        if msg_type == int(MessageType.SCENE_TAB_CLOSE):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own:
                with self._peers_lock:
                    peer = self._peers.get(pid)
                    if peer is not None and peer.current_tab == str(data.get("name", "")):
                        peer.current_tab = ""
                if self._on_remote_tab_close:
                    try:
                        self._on_remote_tab_close(str(data.get("name", "")))
                    except Exception:
                        pass
            return True
        return False
