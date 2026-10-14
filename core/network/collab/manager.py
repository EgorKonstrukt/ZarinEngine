# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import asyncio, threading, time
from typing import Callable, Optional
from core.foundation.logger import Logger
from core.network.protocol import MessageType, normalize_room, normalize_relay_url, generate_room_code, build_direct_invite, build_relay_invite, parse_invite
from core.network.server import CollabServer
from core.network.client import CollabClient
from .models import CollabSettings; from .poll import _PollThread; from .util import get_lan_ips
from .presence import PresenceMixin; from .scene_sync import SceneSyncMixin; from .script_sync import ScriptSyncMixin; from .asset_sync import AssetSyncMixin; from .upnp import UpnpMixin; from .settings import SettingsMixin
class CollaborationManager(PresenceMixin, SceneSyncMixin, ScriptSyncMixin, AssetSyncMixin, UpnpMixin, SettingsMixin):
    def __init__(self, engine):
        self._engine = engine
        self._server = None
        self._server_loop = None
        self._server_thread = None
        self._server_ready = None
        self._client = None
        self._relay_server = None
        self._peers = {}
        self._peers_lock = threading.Lock()
        self._own_name: str = "User"
        self._room: str = ""
        self._password: str = ""
        self._mode: str = "none"
        self._relay_url: str = ""
        self._direct_host: str = ""
        self._direct_port: int = 9876
        self._scene_snapshot_callback = None
        self._on_scene_sync = None
        self._peer_joined_callback = None
        self._peer_left_callback = None
        self._on_remote_script_open = None
        self._on_remote_script_change = None
        self._on_remote_script_cursor = None
        self._on_remote_script_ops = None
        self._on_auth_failed = None
        self._on_connection_change = None
        self._entity_synced_ids = {}
        self._local_entity_ids = {}
        self._pending_scene_sync = False
        self.settings = CollabSettings()
        self._load_settings_from_config()
        self._shutdown = threading.Event()
        self._poll_thread = _PollThread(self._poll_messages, self.settings.poll_interval, self._shutdown)
        self._poll_thread.start()
        self._ping_thread = _PollThread(self._send_ping, int(self.settings.ping_interval * 1000), self._shutdown)
        self._ping_thread.start()
        self._sweep_thread = _PollThread(self._sweep_peers, 5000, self._shutdown)
        self._sweep_thread.start()
        self._as_host = False
        self._play_mode_active = False
        self._latency_ms: float = 0.0
        self._ping_timestamp: float = 0.0
        self._asset_syncing = False
        self._asset_sync_progress: dict = {"total": 0, "current": 0, "current_file": "", "failed": 0}
        self._asset_checksums = {}
        self._asset_watcher = None
        self._on_asset_progress = None
        self._asset_write_lock = threading.Lock()
        self._asset_write_count = 0
        self._suppressed_paths = set()
        self._suppressed_lock = threading.Lock()
        self._custom_handlers = {}
        self._on_remote_scene_open = None
        self._on_remote_tab_switch = None
        self._on_remote_tab_close = None
        self._current_tab: str = ""
        self._chunk_in = {}
        self._chunk_lock = threading.Lock()
        self._last_scene_sync = 0.0
        self._last_scene_hash = ""
        self._auth_error = ""
        self._last_connect = None
        self._reconnect_attempts = 0
        self._reconnect_next = 0.0
        self._manual_stop = False
        self._last_status = False
        self._upnp = None
        self._upnp_lock = threading.Lock()
        self._upnp_status: dict = {"state": "idle", "external_ip": "", "external_port": 0, "internal_port": 0, "error": "", "gateway": ""}
        self._upnp_extras: dict = {}
        self._on_upnp_status = None
    @property
    def peers(self) -> dict:
        with self._peers_lock:
            return dict(self._peers)
    @property
    def connected(self) -> bool:
        try:
            return self._client is not None and bool(self._client.connected)
        except Exception:
            return False
    @property
    def connection_mode(self) -> str:
        if not self.connected:
            return "none"
        return str(self._mode)
    @property
    def room(self) -> str:
        return str(self._room)
    @property
    def is_host(self) -> bool:
        return bool(self._as_host)
    def start_server(self, host: str = "0.0.0.0", port: int = 9876, password: str = "", room: str = "", max_clients: int = 32, use_upnp: Optional[bool] = None):
        self._manual_stop = False
        self._stop_link_only()
        self._stop_server_only()
        self._as_host = True
        self._mode = "direct"
        self._room = normalize_room(room)
        self._password = str(password or "")
        self._direct_host = str(host or "0.0.0.0")
        self._direct_port = int(port)
        self._relay_url = ""
        self._server = CollabServer(host, port, password=self._password, room=self._room, max_clients=max_clients)
        self._server_ready = threading.Event()
        srv = self._server
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._server_loop = loop
            try:
                loop.run_until_complete(srv.start())
            except Exception as e:
                Logger.error(f"Collab server start failed: {e}")
            try:
                self._server_ready.set()
            except Exception:
                pass
            try:
                loop.run_forever()
            except Exception:
                pass
        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()
        try:
            self._server_ready.wait(timeout=5.0)
        except Exception:
            pass
        self._start_asset_watcher()
        Logger.info(f"Collab server started on {host}:{port}")
        try:
            if use_upnp is not None:
                self.settings.upnp_enabled = bool(use_upnp)
            bind_all = str(host or "") in ("0.0.0.0", "", "::", "0:0:0:0:0:0:0:0")
            if bind_all:
                self._start_upnp_for_port(int(port), f"ZarinEngine-Collab-{int(port)}", True)
            else:
                with self._upnp_lock:
                    self._upnp_status = {"state": "disabled", "external_ip": "", "external_port": 0, "internal_port": int(port), "error": "bound_to_localhost", "gateway": ""}
        except Exception:
            pass
    def connect(self, host: str = "127.0.0.1", port: int = 9876, name: str = "User", password: str = "", room: str = ""):
        keep_host = self._server is not None
        self._manual_stop = False
        self._stop_link_only()
        if self._server is not None and self._engine.scene:
            try:
                self.update_server_scene(self._engine.scene)
            except Exception:
                pass
        self._own_name = str(name or "User")[:32]
        if password:
            self._password = str(password)
        if room:
            self._room = normalize_room(room)
        if not keep_host:
            self._as_host = False
            self._mode = "direct"
        else:
            self._mode = "direct"
        self._direct_host = str(host or "127.0.0.1")
        self._direct_port = int(port)
        self._relay_url = ""
        self._reconnect_attempts = 0
        self._reconnect_next = 0.0
        self._last_connect = {"kind": "direct", "host": self._direct_host, "port": self._direct_port, "name": self._own_name, "password": self._password, "room": self._room}
        client = CollabClient()
        try:
            client.set_on_disconnected(self._on_disconnected)
        except Exception:
            pass
        try:
            client.set_on_auth_failed(self._on_auth_failed_inner)
        except Exception:
            pass
        self._client = client
        client.connect(self._direct_host, self._direct_port, self._own_name, password=self._password, room=self._room)
    def host_relay(self, relay_url: str, room: str = "", password: str = "", name: str = "User") -> str:
        from core.network.relay import RelayClient
        self._manual_stop = False
        self._stop_link_only()
        self._stop_server_only()
        self._as_host = True
        self._mode = "relay"
        r = normalize_room(room) or generate_room_code(6)
        self._room = r
        if password:
            self._password = str(password)
        self._own_name = str(name or "User")[:32]
        self._relay_url = normalize_relay_url(relay_url) or str(self.settings.relay_url)
        self._reconnect_attempts = 0
        self._reconnect_next = 0.0
        self._last_connect = {"kind": "relay", "relay": self._relay_url, "room": self._room, "name": self._own_name, "password": self._password, "host": True}
        client = RelayClient()
        try:
            client.set_on_disconnected(self._on_disconnected)
        except Exception:
            pass
        try:
            client.set_on_auth_failed(self._on_auth_failed_inner)
        except Exception:
            pass
        self._client = client
        client.connect(self._relay_url, self._room, self._own_name, password=self._password)
        self._start_asset_watcher()
        return str(self._room)
    def join_relay(self, relay_url: str, room: str, password: str = "", name: str = "User"):
        from core.network.relay import RelayClient
        self._manual_stop = False
        self._stop_link_only()
        self._stop_server_only()
        self._as_host = False
        self._mode = "relay"
        self._room = normalize_room(room)
        if password:
            self._password = str(password)
        self._own_name = str(name or "User")[:32]
        self._relay_url = normalize_relay_url(relay_url) or str(self.settings.relay_url)
        self._reconnect_attempts = 0
        self._reconnect_next = 0.0
        self._last_connect = {"kind": "relay", "relay": self._relay_url, "room": self._room, "name": self._own_name, "password": self._password, "host": False}
        client = RelayClient()
        try:
            client.set_on_disconnected(self._on_disconnected)
        except Exception:
            pass
        try:
            client.set_on_auth_failed(self._on_auth_failed_inner)
        except Exception:
            pass
        self._client = client
        client.connect(self._relay_url, self._room, self._own_name, password=self._password)
    def create_invite(self, public: bool = True) -> str:
        locked = bool(self._password)
        if self._mode == "relay" and self._room:
            return build_relay_invite(self._relay_url or str(self.settings.relay_url), self._room, locked)
        if bool(public):
            try:
                snap = self.upnp_status
            except Exception:
                snap = {}
            if str(snap.get("state", "")) == "mapped" and str(snap.get("external_ip", "")):
                try:
                    return build_direct_invite(str(snap["external_ip"]), int(snap.get("external_port", self._direct_port)), self._room, locked)
                except Exception:
                    pass
        host = self._direct_host
        if host in ("0.0.0.0", "", "0:0:0:0:0:0:0:0"):
            ips = get_lan_ips()
            host = ips[0] if ips else "127.0.0.1"
        return build_direct_invite(host, int(self._direct_port), self._room, locked)
    def create_lan_invite(self) -> str:
        return self.create_invite(public=False)
    def join_invite(self, code: str, name: str, password: str = "") -> bool:
        try:
            obj = parse_invite(code)
        except Exception as e:
            Logger.warning(f"Bad invite: {e}")
            return False
        mode = str(obj.get("mode", "direct"))
        pwd = str(password or "")
        if mode == "relay":
            relay = str(obj.get("relay", "")) or str(self.settings.relay_url)
            room = str(obj.get("room", ""))
            if not room:
                return False
            self._password = pwd
            self.join_relay(relay, room, pwd, name)
            return True
        host = str(obj.get("host", "127.0.0.1"))
        try:
            port = int(obj.get("port", 9876))
        except Exception:
            port = 9876
        room = str(obj.get("room", ""))
        self._password = pwd
        self.connect(host, port, name, password=pwd, room=room)
        return True
    def stop(self):
        self._manual_stop = True
        self._mode = "none"
        try:
            self._clear_upnp_mappings()
        except Exception:
            pass
        try:
            with self._upnp_lock:
                self._upnp_status = {"state": "idle", "external_ip": "", "external_port": 0, "internal_port": 0, "error": "", "gateway": ""}
        except Exception:
            pass
        self._stop_asset_watcher()
        self._stop_link_only()
        self._stop_server_only()
        with self._peers_lock:
            self._peers.clear()
        with self._chunk_lock:
            self._chunk_in.clear()
        self._entity_synced_ids.clear()
        self._local_entity_ids.clear()
        self._as_host = False
        self._asset_syncing = False
        self._auth_error = ""
        self._last_connect = None
        self._reconnect_attempts = 0
        self._room = ""
        Logger.info("Collab stopped")
    def shutdown(self):
        try:
            self._clear_upnp_mappings()
        except Exception:
            pass
        try:
            self._manual_stop = True
        except Exception:
            pass
        try:
            self._shutdown.set()
        except Exception:
            pass
        try:
            self._stop_asset_watcher()
        except Exception:
            pass
        try:
            self._stop_link_only()
        except Exception:
            pass
        try:
            self._stop_server_only()
        except Exception:
            pass
    def _poll_messages(self):
        try:
            client = self._client
            if client is None:
                self._maybe_reconnect()
                self._notify_status()
                return
            try:
                ok = bool(client.connected)
            except Exception:
                ok = False
            if not ok:
                self._notify_status()
                return
            try:
                msgs = client.poll_messages()
            except Exception:
                msgs = []
            for msg_type, data in msgs:
                try:
                    self._handle_message(int(msg_type), dict(data) if isinstance(data, dict) else {})
                except Exception:
                    pass
            try:
                self._sync_server_scene()
            except Exception:
                pass
            self._notify_status()
        except Exception:
            pass
    def _sweep_peers(self):
        try:
            now = time.time()
            timeout = max(10.0, float(self.settings.heartbeat_timeout))
            dead: list[str] = []
            with self._peers_lock:
                for pid, p in list(self._peers.items()):
                    if now - float(p.last_seen) > timeout:
                        dead.append(pid)
                for pid in dead:
                    peer = self._peers.pop(pid, None)
                    if peer is not None and self._peer_left_callback is not None:
                        try:
                            self._peer_left_callback(peer)
                        except Exception:
                            pass
        except Exception:
            pass
    def _handle_message(self, msg_type: int, data: dict):
        try:
            if self._handle_peer_branch(int(msg_type), dict(data)):
                return
        except Exception:
            pass
        try:
            if self._handle_presence_branch(int(msg_type), dict(data)):
                return
        except Exception:
            pass
        try:
            if self._handle_scene_branch(int(msg_type), dict(data)):
                return
        except Exception:
            pass
        try:
            if self._handle_script_branch(int(msg_type), dict(data)):
                return
        except Exception:
            pass
        try:
            if self._handle_asset_branch(int(msg_type), dict(data)):
                return
        except Exception:
            pass
        if msg_type == int(MessageType.CHUNK):
            try:
                self._handle_chunk(data)
            except Exception:
                pass
            return
        handler = self._custom_handlers.get(int(msg_type))
        if handler is not None:
            try:
                handler(data)
            except Exception:
                pass
        self._touch(str(data.get("id", "")))
    def _handle_chunk(self, data: dict):
        try:
            return self._handle_chunk_impl(dict(data))
        except Exception:
            return None
    def register_handler(self, msg_type: int, callback: Callable[[dict], None]):
        try:
            self._custom_handlers[int(msg_type)] = callback
        except Exception:
            pass
    def unregister_handler(self, msg_type: int):
        try:
            self._custom_handlers.pop(int(msg_type), None)
        except Exception:
            pass
