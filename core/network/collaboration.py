# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import hashlib
import json
import os
import secrets
import socket
import time
import threading
import asyncio
import urllib.request
from collections import deque
from typing import Optional, Callable
import msgpack
from core.foundation.logger import Logger
from core.network.protocol import MessageType, PROTOCOL_VERSION, CHUNK_SIZE, CHUNK_THRESHOLD, normalize_room, normalize_relay_url, is_relay_url, generate_room_code, hash_password, make_invite, parse_invite, build_direct_invite, build_relay_invite, estimate_msg_size
from core.network.server import CollabServer
from core.network.client import CollabClient
try:
    from core.network.upnp import UpnpMapper
except Exception:
    UpnpMapper = None
from core.ecs.ecs import Scene, Entity, ComponentRegistry
from core.config.config import get_global_config


def _compute_hash(path: str) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def _scan_assets_dir(assets_dir: str) -> dict[str, dict]:
    result = {}
    if not os.path.isdir(assets_dir):
        return result
    for root, dirs, files in os.walk(assets_dir):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, assets_dir)
            try:
                size = os.path.getsize(full)
                mtime = os.path.getmtime(full)
            except Exception:
                continue
            result[rel] = {"size": size, "mtime": mtime, "hash": ""}
    return result


def get_lan_ips() -> list[str]:
    out: list[str] = []
    try:
        hn = socket.gethostname()
        try:
            _, _, addrs = socket.gethostbyname_ex(hn)
            for a in addrs:
                if a and not a.startswith("127.") and a not in out:
                    out.append(a)
        except Exception:
            pass
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip not in out:
                out.append(ip)
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass
    except Exception:
        pass
    return out


def get_public_ip(timeout: float = 4.0) -> str:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZarinEngine"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ip = r.read().decode("utf-8", errors="ignore").strip()
                if ip and len(ip) < 64 and "." in ip:
                    return ip
        except Exception:
            continue
    return ""


class _AssetWatcher(threading.Thread):
    def __init__(self, assets_dir: str, interval: float, on_change: Callable, on_delete: Callable):
        super().__init__(daemon=True)
        self._assets_dir = assets_dir
        self._interval = max(0.5, float(interval))
        self._on_change = on_change
        self._on_delete = on_delete
        self._stop_event = threading.Event()
        self._snapshots: dict[str, float] = {}
        self._lock = threading.Lock()
        self._refresh()

    def _refresh(self):
        with self._lock:
            self._snapshots.clear()
            if not os.path.isdir(self._assets_dir):
                return
            for root, dirs, files in os.walk(self._assets_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, self._assets_dir)
                    try:
                        self._snapshots[rel] = os.path.getmtime(full)
                    except Exception:
                        pass

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                return
            if not os.path.isdir(self._assets_dir):
                continue
            current: dict[str, float] = {}
            for root, dirs, files in os.walk(self._assets_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, self._assets_dir)
                    try:
                        current[rel] = os.path.getmtime(full)
                    except Exception:
                        pass
            with self._lock:
                old = dict(self._snapshots)
            for rel, mtime in current.items():
                o = old.get(rel)
                if o is None:
                    try:
                        self._on_change(rel)
                    except Exception:
                        pass
                elif abs(mtime - o) > 0.1:
                    try:
                        self._on_change(rel)
                    except Exception:
                        pass
            for rel in list(old.keys()):
                if rel not in current:
                    try:
                        self._on_delete(rel)
                    except Exception:
                        pass
            with self._lock:
                self._snapshots = current


class _PollThread(threading.Thread):
    def __init__(self, callback, interval_ms, stop_event):
        super().__init__(daemon=True)
        self._callback = callback
        self._interval = max(0.001, float(interval_ms) / 1000.0)
        self._stop_event = stop_event

    def run(self):
        while not self._stop_event.is_set():
            try:
                self._callback()
            except Exception:
                pass
            self._stop_event.wait(self._interval)


class RemotePeer:
    __slots__ = ("peer_id", "name", "color", "current_tab",
                 "cursor_screen", "cursor_hit",
                 "camera_pos", "camera_fwd", "camera_up",
                 "selected_entity_ids", "transform_data", "transform_deltas", "last_seen",
                 "ping_ms", "ping_timestamp",
                 "gizmo_mode", "gizmo_hover_axis", "gizmo_dragging")

    def __init__(self, peer_id: str, name: str, color: list[float]):
        self.peer_id = peer_id
        self.name = name
        self.color = list(color)
        self.current_tab: str = ""
        self.cursor_screen: tuple[float, float] = (0, 0)
        self.cursor_hit: Optional[list[float]] = None
        self.camera_pos: list[float] = [0, 0, 0]
        self.camera_fwd: list[float] = [0, 0, -1]
        self.camera_up: list[float] = [0, 1, 0]
        self.selected_entity_ids: list[str] = []
        self.transform_data: dict[str, dict] = {}
        self.transform_deltas: dict[str, dict] = {}
        self.last_seen: float = time.time()
        self.ping_ms: float = 0.0
        self.ping_timestamp: float = 0.0
        self.gizmo_mode: str = "none"
        self.gizmo_hover_axis: int = -1
        self.gizmo_dragging: bool = False


class CollabSettings:
    __slots__ = ("cursor_interval", "camera_interval", "transform_interval",
                 "gizmo_interval", "ping_interval", "poll_interval", "scene_sync_interval",
                 "relay_url", "auto_reconnect", "heartbeat_timeout",
                 "upnp_enabled", "upnp_lease")

    def __init__(self):
        self.cursor_interval: float = 1.0 / 30.0
        self.camera_interval: float = 1.0 / 15.0
        self.transform_interval: float = 1.0 / 20.0
        self.gizmo_interval: float = 1.0 / 10.0
        self.ping_interval: float = 3.0
        self.poll_interval: int = 8
        self.scene_sync_interval: float = 2.0
        self.relay_url: str = "ws://127.0.0.1:8765"
        self.auto_reconnect: bool = True
        self.heartbeat_timeout: float = 30.0
        self.upnp_enabled: bool = True
        self.upnp_lease: int = 3600


class CollaborationManager:
    def __init__(self, engine):
        self._engine = engine
        self._server: Optional[CollabServer] = None
        self._server_loop: Optional[asyncio.AbstractEventLoop] = None
        self._server_thread: Optional[threading.Thread] = None
        self._server_ready: Optional[threading.Event] = None
        self._client = None
        self._relay_server = None
        self._peers: dict[str, RemotePeer] = {}
        self._peers_lock = threading.Lock()
        self._own_name: str = "User"
        self._room: str = ""
        self._password: str = ""
        self._mode: str = "none"
        self._relay_url: str = ""
        self._direct_host: str = ""
        self._direct_port: int = 9876
        self._scene_snapshot_callback: Optional[Callable] = None
        self._on_scene_sync: Optional[Callable[[dict], bool]] = None
        self._peer_joined_callback: Optional[Callable] = None
        self._peer_left_callback: Optional[Callable] = None
        self._on_remote_script_open: Optional[Callable] = None
        self._on_remote_script_change: Optional[Callable] = None
        self._on_remote_script_cursor: Optional[Callable] = None
        self._on_remote_script_ops: Optional[Callable] = None
        self._on_auth_failed: Optional[Callable] = None
        self._on_connection_change: Optional[Callable] = None
        self._entity_synced_ids: dict[str, str] = {}
        self._local_entity_ids: dict[str, str] = {}
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
        self._asset_checksums: dict[str, str] = {}
        self._asset_watcher: Optional[_AssetWatcher] = None
        self._on_asset_progress: Optional[Callable[[dict], None]] = None
        self._asset_write_lock = threading.Lock()
        self._asset_write_count = 0
        self._suppressed_paths: set[str] = set()
        self._suppressed_lock = threading.Lock()
        self._custom_handlers: dict[int, Callable] = {}
        self._on_remote_scene_open: Optional[Callable] = None
        self._on_remote_tab_switch: Optional[Callable] = None
        self._on_remote_tab_close: Optional[Callable] = None
        self._current_tab: str = ""
        self._chunk_in: dict[tuple[str, str], dict] = {}
        self._chunk_lock = threading.Lock()
        self._last_scene_sync = 0.0
        self._last_scene_hash = ""
        self._auth_error = ""
        self._last_connect: Optional[dict] = None
        self._reconnect_attempts = 0
        self._reconnect_next = 0.0
        self._manual_stop = False
        self._last_status = False
        self._upnp = None
        self._upnp_lock = threading.Lock()
        self._upnp_status: dict = {"state": "idle", "external_ip": "", "external_port": 0, "internal_port": 0, "error": "", "gateway": ""}
        self._upnp_extras: dict = {}
        self._on_upnp_status: Optional[Callable] = None

    @property
    def current_tab(self) -> str:
        return self._current_tab

    def set_current_tab(self, tab_name: str):
        self._current_tab = str(tab_name or "")

    @property
    def peers(self) -> dict[str, RemotePeer]:
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
    def relay_url(self) -> str:
        return str(self._relay_url)

    @property
    def auth_error(self) -> str:
        if self._auth_error:
            return str(self._auth_error)
        try:
            if self._client is not None:
                return str(getattr(self._client, "auth_error", "") or "")
        except Exception:
            pass
        return ""

    @property
    def is_host(self) -> bool:
        return bool(self._as_host)

    @property
    def own_peer_id(self) -> Optional[str]:
        try:
            return self._client.peer_id if self._client else None
        except Exception:
            return None

    @property
    def play_mode_active(self) -> bool:
        return bool(self._play_mode_active)

    @property
    def bytes_sent(self) -> int:
        try:
            return int(self._client.bytes_sent) if self._client else 0
        except Exception:
            return 0

    @property
    def bytes_received(self) -> int:
        try:
            return int(self._client.bytes_received) if self._client else 0
        except Exception:
            return 0

    @property
    def latency_ms(self) -> float:
        return float(self._latency_ms)

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

    def send_script_open(self, path: str, content: str):
        self._send_link(MessageType.SCRIPT_OPEN, {"path": str(path), "content": str(content)})

    def send_script_change(self, path: str, content: str):
        self._send_link(MessageType.SCRIPT_CHANGE, {"path": str(path), "content": str(content)})

    def send_script_cursor(self, path: str, pos: int, sel_anchor: int, sel_end: int):
        self._send_link(MessageType.SCRIPT_CURSOR, {"path": str(path), "pos": int(pos), "sel_anchor": int(sel_anchor), "sel_end": int(sel_end)})

    def send_script_ops(self, path: str, ops: list):
        self._send_link(MessageType.SCRIPT_OPS, {"path": str(path), "ops": list(ops)})

    def send_scene_open(self, name: str, path: str, data: dict):
        ok = self._send_link(MessageType.SCENE_OPEN, {"name": str(name), "path": str(path), "data": dict(data)})
        if not ok:
            Logger.warning("Collab scene_open not sent: offline")

    def send_scene_tab_switch(self, name: str):
        self._send_link(MessageType.SCENE_TAB_SWITCH, {"name": str(name)})

    def send_scene_tab_close(self, name: str):
        self._send_link(MessageType.SCENE_TAB_CLOSE, {"name": str(name)})

    def get_peer(self, peer_id: str) -> Optional[RemotePeer]:
        with self._peers_lock:
            return self._peers.get(str(peer_id))

    def _stop_link_only(self):
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

    def _stop_server_only(self):
        try:
            self._clear_upnp_mappings()
        except Exception:
            pass
        srv = self._server
        lp = self._server_loop
        th = self._server_thread
        self._server = None
        self._server_loop = None
        self._server_thread = None
        self._server_ready = None
        if srv is not None and lp is not None:
            try:
                if lp.is_running():
                    fut = asyncio.run_coroutine_threadsafe(srv.stop(), lp)
                    try:
                        fut.result(timeout=3.0)
                    except Exception:
                        pass
                    try:
                        lp.call_soon_threadsafe(lp.stop)
                    except Exception:
                        pass
            except Exception:
                try:
                    loop2 = asyncio.new_event_loop()
                    loop2.run_until_complete(srv.stop())
                    loop2.close()
                except Exception:
                    pass
        elif srv is not None:
            try:
                loop2 = asyncio.new_event_loop()
                loop2.run_until_complete(srv.stop())
                loop2.close()
            except Exception:
                pass
        if th is not None and th.is_alive():
            try:
                th.join(timeout=2.0)
            except Exception:
                pass

    @property
    def upnp_status(self) -> dict:
        with self._upnp_lock:
            return dict(self._upnp_status)

    @property
    def upnp_external_ip(self) -> str:
        with self._upnp_lock:
            return str(self._upnp_status.get("external_ip", ""))

    @property
    def upnp_mapped(self) -> bool:
        with self._upnp_lock:
            return str(self._upnp_status.get("state", "")) == "mapped"

    def set_on_upnp_status(self, cb: Callable):
        self._on_upnp_status = cb

    def set_upnp_enabled(self, enabled: bool):
        try:
            self.settings.upnp_enabled = bool(enabled)
        except Exception:
            pass
        if not enabled:
            self._clear_upnp_mappings()
            with self._upnp_lock:
                self._upnp_status = {"state": "disabled", "external_ip": "", "external_port": 0, "internal_port": 0, "error": "", "gateway": ""}
            self._upnp_notify()

    def _upnp_notify(self):
        cb = self._on_upnp_status
        if cb is None:
            return
        try:
            snap = self.upnp_status
        except Exception:
            return
        try:
            cb(snap)
        except Exception:
            pass

    def _upnp_set(self, **kwargs):
        with self._upnp_lock:
            self._upnp_status.update(kwargs)
        self._upnp_notify()

    def _ensure_upnp_mapper(self):
        if UpnpMapper is None:
            return None
        if self._upnp is None:
            try:
                self._upnp = UpnpMapper(lease=int(self.settings.upnp_lease))
            except Exception:
                try:
                    self._upnp = UpnpMapper()
                except Exception:
                    return None
        return self._upnp

    def _clear_upnp_mappings(self):
        mapper = self._upnp
        self._upnp = None
        try:
            self._upnp_extras = {}
        except Exception:
            pass
        if mapper is None:
            return
        try:
            stale = mapper.tracked()
        except Exception:
            stale = []
        try:
            gw = mapper.gateway
        except Exception:
            gw = None
        try:
            mapper.forget()
        except Exception:
            pass
        if not stale or gw is None:
            return

        def _drop():
            cur = self._upnp
            skip: set = set()
            if cur is not None:
                try:
                    skip = set(cur.tracked())
                except Exception:
                    skip = set()
            for ext, proto in stale:
                if (int(ext), str(proto)) in skip:
                    continue
                try:
                    gw.delete_mapping(int(ext), str(proto), timeout=8.0)
                except Exception:
                    pass

        t = threading.Thread(target=_drop, daemon=True)
        t.start()

    def _run_upnp_map(self, internal_port: int, description: str, main: bool):
        mapper = self._ensure_upnp_mapper()
        if mapper is None:
            if main:
                self._upnp_set(state="failed", error="unavailable")
            return
        if main:
            self._upnp_set(state="discovering", internal_port=int(internal_port), error="")
        try:
            res = mapper.map_port(int(internal_port), int(internal_port), "TCP", str(description), try_alternatives=True, timeout=12.0)
        except Exception as e:
            if main:
                self._upnp_set(state="failed", error=str(e)[:120])
            return
        if main:
            if res.get("ok"):
                self._upnp_set(state="mapped", external_ip=str(res.get("external_ip", "")), external_port=int(res.get("external", internal_port)), internal_port=int(internal_port), error="", gateway=str(mapper.snapshot().get("gateway", "")))
            else:
                self._upnp_set(state="failed", external_ip="", external_port=0, error=str(res.get("error", "map_failed"))[:120])
        else:
            try:
                with self._upnp_lock:
                    self._upnp_extras[int(internal_port)] = {"external": int(res.get("external", internal_port)), "ok": bool(res.get("ok")), "error": str(res.get("error", ""))}
            except Exception:
                pass

    def _start_upnp_for_port(self, port: int, description: str, main: bool):
        use = False
        try:
            use = bool(self.settings.upnp_enabled)
        except Exception:
            use = True
        if not use or UpnpMapper is None:
            if main:
                with self._upnp_lock:
                    self._upnp_status = {"state": "disabled", "external_ip": "", "external_port": 0, "internal_port": int(port), "error": "", "gateway": ""}
            return
        t = threading.Thread(target=self._run_upnp_map, args=(int(port), str(description), bool(main)), daemon=True)
        t.start()

    def map_extra_port(self, port: int, description: str = "ZarinEngine") -> None:
        self._start_upnp_for_port(int(port), str(description or "ZarinEngine"), False)

    def unmap_extra_port(self, port: int) -> None:
        mapper = self._upnp
        if mapper is None:
            return
        try:
            with self._upnp_lock:
                info = self._upnp_extras.pop(int(port), None)
        except Exception:
            info = None
        try:
            ext = int((info or {}).get("external", int(port)))
        except Exception:
            ext = int(port)

        def _drop():
            cur = self._upnp
            if cur is not None and cur is not mapper:
                try:
                    if (int(ext), "TCP") in set(cur.tracked()):
                        return
                except Exception:
                    pass
            try:
                mapper.unmap_port(ext, "TCP")
            except Exception:
                pass

        t = threading.Thread(target=_drop, daemon=True)
        t.start()

    def refresh_upnp(self) -> None:
        port = 0
        try:
            port = int(self._direct_port)
        except Exception:
            port = 0
        if self._server is None or not port:
            return
        use = False
        try:
            use = bool(self.settings.upnp_enabled)
        except Exception:
            use = False
        if not use:
            return
        self._start_upnp_for_port(port, f"ZarinEngine-Collab-{port}", True)

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

    def _on_auth_failed_inner(self, reason: str):
        self._auth_error = str(reason or "auth")
        cb = self._on_auth_failed
        if cb is not None:
            try:
                cb(str(self._auth_error))
            except Exception:
                pass
        Logger.warning(f"Collab auth failed: {self._auth_error}")

    def _on_disconnected(self):
        with self._peers_lock:
            self._peers.clear()
        self._notify_status()
        Logger.info("Collab disconnected")
        if self.settings.auto_reconnect and not self._manual_stop and self._last_connect:
            self._reconnect_attempts = 0
            self._reconnect_next = time.time() + 1.0

    def _maybe_reconnect(self):
        if self._manual_stop:
            return
        if not self.settings.auto_reconnect:
            return
        if self._last_connect is None:
            return
        try:
            if self._client is not None and self._client.connected:
                self._reconnect_attempts = 0
                return
        except Exception:
            pass
        if self._client is not None:
            return
        now = time.time()
        if now < self._reconnect_next:
            return
        if self._reconnect_attempts >= 8:
            return
        info = dict(self._last_connect)
        self._reconnect_attempts += 1
        self._reconnect_next = now + min(30.0, 1.0 * (2 ** self._reconnect_attempts))
        try:
            if info.get("kind") == "relay":
                self.join_relay(str(info.get("relay", "")), str(info.get("room", "")), str(info.get("password", "")), str(info.get("name", "User")))
                if info.get("host"):
                    self._as_host = True
            else:
                self.connect(str(info.get("host", "127.0.0.1")), int(info.get("port", 9876)), str(info.get("name", "User")), password=str(info.get("password", "")), room=str(info.get("room", "")))
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

    def _scene_hash(self, scene) -> str:
        try:
            data = scene.serialize()
            raw = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
            return hashlib.md5(raw).hexdigest()
        except Exception:
            return ""

    def _sync_server_scene(self):
        if not self._as_host:
            return
        if self._mode != "direct":
            return
        if not self._server:
            return
        now = time.time()
        if now - float(self._last_scene_sync) < float(self.settings.scene_sync_interval):
            return
        self._last_scene_sync = now
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if scene:
            try:
                h = self._scene_hash(scene)
            except Exception:
                h = ""
            if h and h == self._last_scene_hash:
                return
            self._last_scene_hash = str(h)
            try:
                self.update_server_scene(scene)
            except Exception:
                pass

    def _touch(self, pid: str):
        if not pid:
            return
        with self._peers_lock:
            p = self._peers.get(pid)
            if p is not None:
                p.last_seen = time.time()

    def _handle_message(self, msg_type: int, data: dict):
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
        elif msg_type == int(MessageType.PEER_JOINED):
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
        elif msg_type == int(MessageType.LEAVE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.pop(pid, None)
            if peer is not None and self._peer_left_callback:
                try:
                    self._peer_left_callback(peer)
                except Exception:
                    pass
        elif msg_type == int(MessageType.AUTH_FAIL):
            self._auth_error = str(data.get("reason", "auth"))
            if self._on_auth_failed is not None:
                try:
                    self._on_auth_failed(str(self._auth_error))
                except Exception:
                    pass
        elif msg_type == int(MessageType.CURSOR_UPDATE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.get(pid)
            if peer:
                peer.cursor_screen = (float(data.get("x", 0)), float(data.get("y", 0)))
                peer.cursor_hit = data.get("hit")
                peer.last_seen = time.time()
        elif msg_type == int(MessageType.CAMERA_UPDATE):
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
        elif msg_type == int(MessageType.ENTITY_CREATED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._create_remote_entity(dict(data.get("entity", {})))
                except Exception:
                    pass
        elif msg_type == int(MessageType.ENTITY_DELETED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._delete_remote_entity(str(data.get("entity_id", "")))
                except Exception:
                    pass
        elif msg_type == int(MessageType.TRANSFORM_UPDATED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_transform(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.SELECTION_UPDATE):
            pid = str(data.get("id", ""))
            with self._peers_lock:
                peer = self._peers.get(pid)
            if peer:
                try:
                    peer.selected_entity_ids = list(data.get("entity_ids", []))
                    peer.last_seen = time.time()
                except Exception:
                    pass
        elif msg_type == int(MessageType.COMPONENT_UPDATED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.COMPONENT_ADDED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component_add(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.COMPONENT_REMOVED):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component_remove(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.PONG):
            try:
                t = float(data.get("t", 0))
                now = time.time()
                if t > 0:
                    self._latency_ms = (now - t) * 1000.0
            except Exception:
                pass
        elif msg_type == int(MessageType.PLAY_MODE):
            try:
                self._play_mode_active = bool(data.get("active", False))
            except Exception:
                pass
            self._touch(str(data.get("id", "")))
        elif msg_type == int(MessageType.COMPONENT_SYNC):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._tab_matches(data):
                self._touch(pid)
                try:
                    self._apply_remote_component_sync(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.GIZMO_STATE_UPDATE):
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
        elif msg_type == int(MessageType.SCENE_SNAPSHOT):
            try:
                scene_data = data.get("scene")
                req_id = str(data.get("requesting_id", ""))
                own = self.own_peer_id
                if req_id and req_id != own:
                    return
                if scene_data:
                    self._apply_scene_snapshot(scene_data)
            except Exception:
                pass
        elif msg_type == int(MessageType.ASSET_LIST_REQ):
            pid = str(data.get("id", ""))
            self._touch(pid)
            if self._as_host and pid:
                try:
                    self.send_asset_list(pid)
                except Exception:
                    pass
        elif msg_type == int(MessageType.ASSET_LIST):
            own = self.own_peer_id
            target = str(data.get("target", ""))
            if target and target != own:
                return
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_list(data)
            except Exception:
                pass
        elif msg_type == int(MessageType.ASSET_SYNC):
            own = self.own_peer_id
            target = str(data.get("target", ""))
            if target and target != own:
                return
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_sync(data)
            except Exception:
                pass
        elif msg_type == int(MessageType.ASSET_WATCH):
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_watch(data)
            except Exception:
                pass
        elif msg_type == int(MessageType.ASSET_DELETE):
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_delete(data)
            except Exception:
                pass
        elif msg_type == int(MessageType.ASSET_REQUEST):
            pid = str(data.get("id", ""))
            self._touch(pid)
            target = str(data.get("target", ""))
            own = self.own_peer_id
            if target and target != own and not self._as_host:
                return
            if self._as_host:
                try:
                    self._handle_asset_request(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.CHUNK):
            try:
                self._handle_chunk(data)
            except Exception:
                pass
        elif msg_type == int(MessageType.SCENE_OPEN):
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
        elif msg_type == int(MessageType.SCENE_TAB_SWITCH):
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
        elif msg_type == int(MessageType.SCENE_TAB_CLOSE):
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
        elif msg_type == int(MessageType.SCRIPT_OPEN):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_open:
                self._touch(pid)
                try:
                    self._on_remote_script_open(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.SCRIPT_CHANGE):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_change:
                self._touch(pid)
                try:
                    self._on_remote_script_change(data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.SCRIPT_CURSOR):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_cursor:
                self._touch(pid)
                try:
                    self._on_remote_script_cursor(pid, data)
                except Exception:
                    pass
        elif msg_type == int(MessageType.SCRIPT_OPS):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_ops:
                self._touch(pid)
                try:
                    self._on_remote_script_ops(pid, data)
                except Exception:
                    pass
        else:
            handler = self._custom_handlers.get(int(msg_type))
            if handler is not None:
                try:
                    handler(data)
                except Exception:
                    pass
            self._touch(str(data.get("id", "")))

    def _handle_chunk(self, data: dict):
        pid = str(data.get("id", ""))
        cid = str(data.get("cid", ""))
        if not cid or not pid:
            return
        try:
            idx = int(data.get("idx", 0))
            total = int(data.get("total", 0))
            inner_type = int(data.get("inner_type", 0))
        except Exception:
            return
        part = data.get("part")
        if part is None or total <= 0 or total > 4096 or idx < 0 or idx >= total:
            return
        if isinstance(part, str):
            part = part.encode("utf-8")
        key = (pid, cid)
        with self._chunk_lock:
            entry = self._chunk_in.get(key)
            if entry is None:
                entry = {"total": total, "inner_type": inner_type, "parts": {}, "time": time.time()}
                self._chunk_in[key] = entry
            if entry.get("total") != total:
                return
            parts = entry["parts"]
            if idx not in parts:
                parts[idx] = bytes(part)
            if len(parts) < total:
                return
            ordered = b"".join(parts[i] for i in range(total))
            try:
                del self._chunk_in[key]
            except Exception:
                pass
        try:
            obj = msgpack.unpackb(ordered, raw=False)
            t = int(obj["t"])
            d = dict(obj["d"])
        except Exception:
            return
        d["id"] = pid
        try:
            self._handle_message(int(t), d)
        except Exception:
            pass
        now = time.time()
        with self._chunk_lock:
            for k in [k for k, v in self._chunk_in.items() if now - float(v.get("time", now)) > 30.0]:
                try:
                    del self._chunk_in[k]
                except Exception:
                    pass

    def _handle_asset_list(self, data: dict):
        paths = data.get("assets", [])
        checksums = data.get("checksums", {})
        if not isinstance(paths, list):
            return
        if not isinstance(checksums, dict):
            checksums = {}
        assets_dir = self._get_assets_dir()
        try:
            os.makedirs(assets_dir, exist_ok=True)
        except Exception:
            pass
        need_sync = []
        for rel in paths:
            if not isinstance(rel, str) or not rel or ".." in rel.replace("\\", "/").split("/"):
                continue
            full = os.path.join(assets_dir, rel)
            expected = str(checksums.get(rel, ""))
            if os.path.exists(full):
                try:
                    actual = _compute_hash(full)
                except Exception:
                    actual = ""
                if actual == expected and expected:
                    continue
                if not expected and os.path.exists(full):
                    continue
            need_sync.append(rel)
        self._asset_syncing = True
        self._asset_sync_progress = {"total": len(need_sync), "current": 0, "current_file": "", "failed": 0}
        own = self.own_peer_id
        sender = str(data.get("id", ""))
        for rel in need_sync:
            self._asset_sync_progress["current_file"] = rel
            if self._on_asset_progress:
                try:
                    self._on_asset_progress(dict(self._asset_sync_progress))
                except Exception:
                    pass
            try:
                self._send_link(MessageType.ASSET_REQUEST, {"path": rel, "target": sender})
            except Exception:
                pass
        if not need_sync:
            self._asset_syncing = False
            self._asset_sync_progress["current_file"] = ""
            self._asset_sync_progress["current"] = 0
            if self._on_asset_progress:
                try:
                    self._on_asset_progress(dict(self._asset_sync_progress))
                except Exception:
                    pass

    def _handle_asset_sync(self, data: dict):
        rel = str(data.get("path", ""))
        raw = data.get("data")
        checksum = str(data.get("checksum", ""))
        if not rel or raw is None:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        assets_dir = self._get_assets_dir()
        full = os.path.join(assets_dir, rel)
        try:
            os.makedirs(os.path.dirname(full) or assets_dir, exist_ok=True)
        except Exception:
            pass
        with self._suppressed_lock:
            self._suppressed_paths.add(rel)
        with self._asset_write_lock:
            self._asset_write_count += 1
        try:
            with open(full, "wb") as f:
                f.write(bytes(raw))
        except Exception as e:
            Logger.error(f"Collab asset write failed '{rel}': {e}")
            with self._asset_write_lock:
                self._asset_write_count = max(0, self._asset_write_count - 1)
            try:
                self._asset_sync_progress["failed"] += 1
            except Exception:
                pass
            return
        with self._asset_write_lock:
            self._asset_write_count = max(0, self._asset_write_count - 1)
        if checksum:
            try:
                actual = _compute_hash(full)
                if actual != checksum:
                    Logger.warning(f"Collab asset '{rel}' checksum mismatch")
            except Exception:
                pass
        try:
            self._asset_sync_progress["current"] += 1
            if self._asset_sync_progress["current"] >= self._asset_sync_progress["total"]:
                self._asset_syncing = False
                self._asset_sync_progress["current_file"] = ""
            if self._on_asset_progress:
                self._on_asset_progress(dict(self._asset_sync_progress))
        except Exception:
            pass

    def _handle_asset_watch(self, data: dict):
        rel = str(data.get("path", ""))
        raw = data.get("data")
        if not rel or raw is None:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        assets_dir = self._get_assets_dir()
        full = os.path.join(assets_dir, rel)
        try:
            os.makedirs(os.path.dirname(full) or assets_dir, exist_ok=True)
        except Exception:
            pass
        with self._suppressed_lock:
            self._suppressed_paths.add(rel)
        with self._asset_write_lock:
            self._asset_write_count += 1
        try:
            with open(full, "wb") as f:
                f.write(bytes(raw))
        except Exception as e:
            Logger.error(f"Collab watched asset write failed '{rel}': {e}")
        finally:
            with self._asset_write_lock:
                self._asset_write_count = max(0, self._asset_write_count - 1)

    def _handle_asset_delete(self, data: dict):
        rel = str(data.get("path", ""))
        if not rel:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        assets_dir = self._get_assets_dir()
        full = os.path.join(assets_dir, rel)
        with self._suppressed_lock:
            self._suppressed_paths.add(rel)
        with self._asset_write_lock:
            self._asset_write_count += 1
        try:
            if os.path.exists(full):
                os.remove(full)
                Logger.info(f"Collab removed asset '{rel}'")
        except Exception as e:
            Logger.error(f"Collab remove asset '{rel}' failed: {e}")
        finally:
            with self._asset_write_lock:
                self._asset_write_count = max(0, self._asset_write_count - 1)

    def send_cursor(self, screen_x: float, screen_y: float, hit_pos: Optional[list[float]] = None):
        self._send_link(MessageType.CURSOR, {"x": float(screen_x), "y": float(screen_y), "hit": hit_pos})

    def send_camera(self, pos: list[float], fwd: list[float], up: list[float]):
        self._send_link(MessageType.CAMERA, {"pos": list(pos), "fwd": list(fwd), "up": list(up)})

    def _with_tab(self, d: dict) -> dict:
        if self._current_tab:
            d["tab"] = self._current_tab
        return d

    def _tab_matches(self, data: dict) -> bool:
        msg_tab = str(data.get("tab", ""))
        return not msg_tab or msg_tab == self._current_tab

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
            return {k: CollaborationManager._collapse_value(v) for k, v in v.items()}
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

    def apply_settings(self):
        try:
            self._poll_thread._interval = max(0.001, float(self.settings.poll_interval) / 1000.0)
        except Exception:
            pass

    def _load_settings_from_config(self):
        try:
            cfg = get_global_config()
        except Exception:
            return
        s = self.settings
        try:
            s.cursor_interval = 1.0 / max(1.0, float(cfg.get("collab.cursor_rate", 30.0)))
            s.camera_interval = 1.0 / max(1.0, float(cfg.get("collab.camera_rate", 15.0)))
            s.transform_interval = 1.0 / max(1.0, float(cfg.get("collab.transform_rate", 20.0)))
            s.gizmo_interval = 1.0 / max(1.0, float(cfg.get("collab.gizmo_rate", 10.0)))
            s.ping_interval = float(cfg.get("collab.ping_interval", 3.0))
            s.poll_interval = int(cfg.get("collab.poll_interval", 8))
            s.scene_sync_interval = float(cfg.get("collab.scene_sync_interval", 2.0))
            s.relay_url = str(cfg.get("collab.relay_url", s.relay_url))
            s.auto_reconnect = bool(cfg.get("collab.auto_reconnect", True))
            s.heartbeat_timeout = float(cfg.get("collab.heartbeat_timeout", 30.0))
            s.upnp_enabled = bool(cfg.get("collab.upnp_enabled", True))
            s.upnp_lease = int(cfg.get("collab.upnp_lease", 3600))
        except Exception:
            pass

    def save_settings_to_config(self):
        try:
            cfg = get_global_config()
        except Exception:
            return
        s = self.settings
        try:
            cfg.set("collab.cursor_rate", 1.0 / max(0.001, float(s.cursor_interval)))
            cfg.set("collab.camera_rate", 1.0 / max(0.001, float(s.camera_interval)))
            cfg.set("collab.transform_rate", 1.0 / max(0.001, float(s.transform_interval)))
            cfg.set("collab.gizmo_rate", 1.0 / max(0.001, float(s.gizmo_interval)))
            cfg.set("collab.ping_interval", float(s.ping_interval))
            cfg.set("collab.poll_interval", int(s.poll_interval))
            cfg.set("collab.scene_sync_interval", float(s.scene_sync_interval))
            cfg.set("collab.relay_url", str(s.relay_url))
            cfg.set("collab.auto_reconnect", bool(s.auto_reconnect))
            cfg.set("collab.heartbeat_timeout", float(s.heartbeat_timeout))
            cfg.set("collab.upnp_enabled", bool(s.upnp_enabled))
            cfg.set("collab.upnp_lease", int(s.upnp_lease))
            cfg.save()
        except Exception:
            pass

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

    def set_asset_progress_callback(self, cb: Callable[[dict], None]):
        self._on_asset_progress = cb

    @property
    def asset_syncing(self) -> bool:
        return bool(self._asset_syncing)

    @property
    def asset_sync_progress(self) -> dict:
        try:
            return dict(self._asset_sync_progress)
        except Exception:
            return {"total": 0, "current": 0, "current_file": "", "failed": 0}

    def _get_assets_dir(self) -> str:
        try:
            root = self._engine.project_root if getattr(self._engine, "project_root", None) else os.getcwd()
        except Exception:
            root = os.getcwd()
        return os.path.join(str(root), "assets")

    def _scan_assets(self) -> dict[str, dict]:
        return _scan_assets_dir(self._get_assets_dir())

    def _load_checksums(self, manifest: dict[str, dict]) -> dict[str, str]:
        cache = {}
        base = self._get_assets_dir()
        for rel in manifest.keys():
            full = os.path.join(base, rel)
            if os.path.exists(full):
                try:
                    cache[rel] = _compute_hash(full)
                except Exception:
                    cache[rel] = ""
            else:
                cache[rel] = ""
        return cache

    def request_asset_list(self):
        self._send_link(MessageType.ASSET_LIST_REQ, {})

    def send_asset_list(self, target_peer_id: str):
        manifest = self._scan_assets()
        self._asset_checksums = self._load_checksums(manifest)
        paths = list(manifest.keys())
        self._send_link(MessageType.ASSET_LIST, {"target": str(target_peer_id), "assets": paths, "checksums": {p: self._asset_checksums.get(p, "") for p in paths}})

    def send_asset_file(self, relative_path: str, target_peer_id: str = ""):
        full = os.path.join(self._get_assets_dir(), str(relative_path))
        if not os.path.exists(full):
            return
        try:
            with open(full, "rb") as f:
                raw = f.read()
        except Exception as e:
            Logger.error(f"Collab read asset '{relative_path}' failed: {e}")
            return
        try:
            checksum = _compute_hash(full)
        except Exception:
            checksum = ""
        payload = {"path": str(relative_path), "data": raw, "checksum": checksum, "size": len(raw)}
        if target_peer_id:
            payload["target"] = str(target_peer_id)
        self._send_link(MessageType.ASSET_SYNC, payload)

    def send_asset_request(self, relative_path: str, target_peer_id: str = ""):
        payload = {"path": str(relative_path)}
        if target_peer_id:
            payload["target"] = str(target_peer_id)
        else:
            try:
                if self._as_host:
                    pass
            except Exception:
                pass
        self._send_link(MessageType.ASSET_REQUEST, payload)

    def _handle_asset_request(self, data: dict):
        rel = str(data.get("path", ""))
        if not rel:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        target = str(data.get("id", ""))
        try:
            self.send_asset_file(rel, target)
        except Exception:
            pass

    def send_asset_delete(self, relative_path: str):
        self._send_link(MessageType.ASSET_DELETE, {"path": str(relative_path)})

    def _send_watch_update(self, relative_path: str):
        try:
            with self._asset_write_lock:
                busy = self._asset_write_count > 0
        except Exception:
            busy = False
        if busy or self._asset_syncing:
            return
        client = self._client
        if client is None:
            return
        try:
            if not client.connected:
                return
        except Exception:
            return
        full = os.path.join(self._get_assets_dir(), str(relative_path))
        if not os.path.exists(full):
            return
        try:
            with open(full, "rb") as f:
                raw = f.read()
        except Exception:
            return
        self._send_link(MessageType.ASSET_WATCH, {"path": str(relative_path), "data": raw, "size": len(raw)})

    def _start_asset_watcher(self):
        try:
            self._stop_asset_watcher()
        except Exception:
            pass
        ad = self._get_assets_dir()
        if not os.path.isdir(ad):
            return

        def _on_watch_change(rel):
            try:
                with self._suppressed_lock:
                    if rel in self._suppressed_paths:
                        self._suppressed_paths.discard(rel)
                        return
                self._send_watch_update(rel)
            except Exception:
                pass

        def _on_watch_delete(rel):
            try:
                with self._suppressed_lock:
                    if rel in self._suppressed_paths:
                        self._suppressed_paths.discard(rel)
                        return
                self.send_asset_delete(rel)
            except Exception:
                pass

        try:
            self._asset_watcher = _AssetWatcher(ad, 2.0, on_change=_on_watch_change, on_delete=_on_watch_delete)
            self._asset_watcher.start()
        except Exception:
            self._asset_watcher = None

    def _stop_asset_watcher(self):
        if self._asset_watcher:
            try:
                self._asset_watcher.stop()
            except Exception:
                pass
            self._asset_watcher = None

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

    def _add_peer(self, peer_id: str, name: str, color: list[float]):
        with self._peers_lock:
            if peer_id in self._peers:
                return
            peer = RemotePeer(peer_id, name, color)
            self._peers[peer_id] = peer
        if self._peer_joined_callback:
            try:
                self._peer_joined_callback(peer)
            except Exception:
                pass

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
        from core.ecs.ecs import ComponentRegistry
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
