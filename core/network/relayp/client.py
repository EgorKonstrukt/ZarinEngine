# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import asyncio
import threading
import time
from collections import deque
from typing import Optional, Callable
import msgpack
from core.foundation.logger import Logger
from core.network.protocol import MessageType, PROTOCOL_VERSION, normalize_room, normalize_relay_url


class RelayClient:
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._connected = False
        self._peer_id: Optional[str] = None
        self._name = ""
        self._color: list[float] = [0.5, 0.5, 0.5]
        self._room = ""
        self._incoming: deque[tuple[int, dict]] = deque()
        self._lock = threading.Lock()
        self._on_connected: Optional[Callable] = None
        self._on_disconnected: Optional[Callable] = None
        self._on_auth_failed: Optional[Callable] = None
        self._stopped = False
        self._bytes_sent = 0
        self._bytes_received = 0
        self._relay_url = ""
        self._token = ""
        self._auth_error = ""
        self._timeout = 10.0

    @property
    def connected(self) -> bool:
        return bool(self._connected)

    @property
    def peer_id(self) -> Optional[str]:
        return self._peer_id

    @property
    def color(self) -> list[float]:
        return list(self._color)

    @property
    def bytes_sent(self) -> int:
        return int(self._bytes_sent)

    @property
    def bytes_received(self) -> int:
        return int(self._bytes_received)

    @property
    def auth_error(self) -> str:
        return str(self._auth_error)

    @property
    def room(self) -> str:
        return str(self._room)

    def set_on_connected(self, cb: Callable):
        self._on_connected = cb

    def set_on_disconnected(self, cb: Callable):
        self._on_disconnected = cb

    def set_on_auth_failed(self, cb: Callable):
        self._on_auth_failed = cb

    def connect(self, relay_url: str, room: str, name: str = "User", password: str = "", timeout: float = 10.0):
        if self._connected:
            return
        try:
            self.disconnect()
        except Exception:
            pass
        import hashlib as _hl
        self._relay_url = normalize_relay_url(relay_url)
        self._room = normalize_room(room)
        self._name = str(name or "User")[:32]
        pwd = str(password or "")
        if pwd:
            self._token = _hl.sha256((self._room + "\x00" + pwd).encode("utf-8")).hexdigest()
        else:
            self._token = ""
        self._timeout = max(3.0, float(timeout or 10.0))
        self._auth_error = ""
        self._peer_id = None
        self._stopped = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def wait_connected(self, timeout: float = 10.0) -> bool:
        deadline = time.time() + max(0.1, float(timeout))
        while time.time() < deadline:
            if self._connected and self._peer_id:
                return True
            if self._auth_error:
                return False
            time.sleep(0.02)
        return bool(self._connected and self._peer_id)

    def disconnect(self):
        self._stopped = True
        lp = self._loop
        if lp is not None and not lp.is_closed() and lp.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._async_close(), lp)
                try:
                    fut.result(timeout=2.0)
                except Exception:
                    pass
            except Exception:
                pass
        self._connected = False
        th = self._thread
        if th is not None and th.is_alive() and th is not threading.current_thread():
            try:
                th.join(timeout=2.0)
            except Exception:
                pass
        self._thread = None
        self._ws = None

    async def _async_close(self):
        try:
            ws = self._ws
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
        except Exception:
            pass

    def _run_loop(self, *args):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session())
        except Exception as e:
            Logger.error(f"RelayClient error: {e}")
            self._connected = False
            if not self._stopped and self._on_disconnected:
                try:
                    self._on_disconnected()
                except Exception:
                    pass
        try:
            pending = asyncio.all_tasks(self._loop)
            for t in list(pending):
                try:
                    t.cancel()
                except Exception:
                    pass
            try:
                self._loop.run_until_complete(asyncio.gather(*list(pending), return_exceptions=True))
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._loop.close()
        except Exception:
            pass

    async def _session(self):
        from websockets.asyncio.client import connect as _connect
        try:
            async with _connect(self._relay_url, max_size=8 * 1024 * 1024, open_timeout=self._timeout) as ws:
                self._ws = ws
                hello = {"op": "join", "room": self._room, "token": self._token, "name": self._name, "version": int(PROTOCOL_VERSION)}
                raw = msgpack.packb(hello, use_bin_type=True)
                await ws.send(raw)
                self._bytes_sent += len(raw)
                try:
                    first = await asyncio.wait_for(ws.recv(), timeout=self._timeout)
                except asyncio.TimeoutError:
                    self._auth_error = "timeout"
                    return
                if isinstance(first, str):
                    first = first.encode("utf-8")
                self._bytes_received += len(first)
                try:
                    obj = msgpack.unpackb(first, raw=False)
                except Exception:
                    self._auth_error = "protocol"
                    return
                if not isinstance(obj, dict):
                    self._auth_error = "protocol"
                    return
                if obj.get("op") == "fail":
                    self._auth_error = str(obj.get("reason", "auth"))
                    with self._lock:
                        self._incoming.append((int(MessageType.AUTH_FAIL), {"reason": str(self._auth_error)}))
                    if self._on_auth_failed:
                        try:
                            self._on_auth_failed(str(self._auth_error))
                        except Exception:
                            pass
                    return
                if obj.get("op") != "welcomed":
                    self._auth_error = "protocol"
                    return
                self._peer_id = str(obj.get("your_id", ""))
                try:
                    self._color = list(obj.get("your_color", [0.5, 0.5, 0.5]))
                except Exception:
                    self._color = [0.5, 0.5, 0.5]
                self._connected = True
                with self._lock:
                    peers = obj.get("peers", [])
                    self._incoming.append((int(MessageType.JOINED), {"your_id": self._peer_id, "your_color": list(self._color), "peers": list(peers) if isinstance(peers, list) else [], "room": str(obj.get("room", self._room)), "version": int(obj.get("version", int(PROTOCOL_VERSION)))}))
                if self._on_connected:
                    try:
                        self._on_connected()
                    except Exception:
                        pass
                await self._read_loop(ws)
        except OSError as e:
            Logger.warning(f"RelayClient connect failed: {e}")
        except Exception as e:
            Logger.error(f"RelayClient session error: {e}")
        finally:
            self._connected = False
            if not self._stopped and self._on_disconnected:
                try:
                    self._on_disconnected()
                except Exception:
                    pass

    async def _read_loop(self, ws):
        while not self._stopped:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    ping = msgpack.packb({"op": "ping", "t": time.time()}, use_bin_type=True)
                    await ws.send(ping)
                    self._bytes_sent += len(ping)
                    continue
                except Exception:
                    break
            except Exception:
                break
            try:
                if isinstance(msg, str):
                    msg = msg.encode("utf-8")
                self._bytes_received += len(msg)
                obj = msgpack.unpackb(msg, raw=False)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            op = str(obj.get("op", ""))
            if op == "data":
                try:
                    t = int(obj.get("t", 0))
                except Exception:
                    continue
                d = obj.get("d", {})
                if not isinstance(d, dict):
                    continue
                with self._lock:
                    self._incoming.append((t, dict(d)))
            elif op == "peer_joined":
                pid = str(obj.get("id", ""))
                if pid:
                    with self._lock:
                        self._incoming.append((int(MessageType.PEER_JOINED), {"id": pid, "name": str(obj.get("name", "")), "color": list(obj.get("color", [0.5, 0.5, 0.5]))}))
            elif op == "peer_left":
                pid = str(obj.get("id", ""))
                if pid:
                    with self._lock:
                        self._incoming.append((int(MessageType.LEAVE), {"id": pid}))
            elif op == "pong":
                with self._lock:
                    self._incoming.append((int(MessageType.PONG), {"t": obj.get("t", 0)}))
            elif op == "fail":
                self._auth_error = str(obj.get("reason", "auth"))
                with self._lock:
                    self._incoming.append((int(MessageType.AUTH_FAIL), {"reason": str(self._auth_error)}))
                break

    def send(self, msg_type: int, data: dict):
        if not self._connected or self._ws is None or self._loop is None or self._loop.is_closed():
            return False
        try:
            payload = dict(data)
            target = str(payload.get("target", ""))
            envelope = {"op": "data", "to": target, "t": int(msg_type), "d": payload}
            raw = msgpack.packb(envelope, use_bin_type=True)
            if len(raw) > 7 * 1024 * 1024:
                Logger.warning("RelayClient send too large")
                return False
            asyncio.run_coroutine_threadsafe(self._async_send(raw), self._loop)
            return True
        except Exception as e:
            Logger.warning(f"RelayClient send error: {e}")
            return False

    async def _async_send(self, raw: bytes):
        try:
            ws = self._ws
            if ws is None:
                return
            await ws.send(raw)
            self._bytes_sent += len(raw)
        except Exception:
            pass

    def poll_messages(self) -> list[tuple[int, dict]]:
        with self._lock:
            msgs = list(self._incoming)
            self._incoming.clear()
            return msgs
