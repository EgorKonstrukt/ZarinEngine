# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import threading
import time
from typing import Callable, Optional
from .models import RemotePeer
try:
    from core.network.upnp import UpnpMapper
except Exception:
    UpnpMapper = None
class UpnpMixin:
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
    def get_peer(self, peer_id: str) -> Optional[RemotePeer]:
        with self._peers_lock:
            return self._peers.get(str(peer_id))
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
                    import asyncio
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
                    import asyncio
                    loop2 = asyncio.new_event_loop()
                    loop2.run_until_complete(srv.stop())
                    loop2.close()
                except Exception:
                    pass
        elif srv is not None:
            try:
                import asyncio
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
    def _on_auth_failed_inner(self, reason: str):
        self._auth_error = str(reason or "auth")
        cb = self._on_auth_failed
        if cb is not None:
            try:
                cb(str(self._auth_error))
            except Exception:
                pass
        from core.foundation.logger import Logger
        Logger.warning(f"Collab auth failed: {self._auth_error}")
    def _on_disconnected(self):
        with self._peers_lock:
            self._peers.clear()
        self._notify_status()
        from core.foundation.logger import Logger
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
