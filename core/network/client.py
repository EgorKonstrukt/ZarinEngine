# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import asyncio
import hashlib
import socket
import struct
import threading
import time
from typing import Optional, Callable
from collections import deque
from core.foundation.logger import Logger
from core.network.protocol import MessageType, make_msg, parse_msg, FRAME_HEADER_SIZE, PROTOCOL_VERSION, normalize_room
from core.config.constants import MAX_MESSAGE_SIZE


class CollabClient:
    def __init__(self):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._peer_id: Optional[str] = None
        self._name: str = ""
        self._color: list[float] = [0.5, 0.5, 0.5]
        self._incoming: deque[tuple[int, dict]] = deque()
        self._lock = threading.Lock()
        self._on_connected: Optional[Callable] = None
        self._on_disconnected: Optional[Callable] = None
        self._on_auth_failed: Optional[Callable] = None
        self._stopped = False
        self._bytes_sent = 0
        self._bytes_received = 0
        self._last_recv = 0.0
        self._room = ""
        self._auth_error = ""
        self._connect_timeout = 8.0

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

    def set_on_connected(self, cb: Callable):
        self._on_connected = cb

    def set_on_disconnected(self, cb: Callable):
        self._on_disconnected = cb

    def set_on_auth_failed(self, cb: Callable):
        self._on_auth_failed = cb

    def connect(self, host: str = "127.0.0.1", port: int = 9876, name: str = "User", password: str = "", room: str = "", timeout: float = 8.0):
        if self._connected:
            return
        try:
            self.disconnect()
        except Exception:
            pass
        self._name = str(name or "User")[:32]
        self._room = normalize_room(room)
        self._password = str(password or "")
        self._connect_timeout = max(2.0, float(timeout or 8.0))
        self._auth_error = ""
        self._peer_id = None
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run_loop, args=(str(host or "127.0.0.1"), int(port)), daemon=True
        )
        self._thread.start()

    def wait_connected(self, timeout: float = 8.0) -> bool:
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
        w = self._writer
        lp = self._loop
        if w is not None and lp is not None:
            try:
                if not lp.is_closed() and lp.is_running():
                    fut = asyncio.run_coroutine_threadsafe(self._async_close(), lp)
                    try:
                        fut.result(timeout=1.5)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                w.close()
            except Exception:
                pass
        elif w is not None:
            try:
                w.close()
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
        self._reader = None
        self._writer = None

    async def _async_close(self):
        try:
            if self._writer is not None:
                try:
                    self._writer.close()
                    await asyncio.wait_for(self._writer.wait_closed(), timeout=1.0)
                except Exception:
                    pass
        except Exception:
            pass

    def _run_loop(self, host: str, port: int):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect(host, port))
        except Exception as e:
            Logger.error(f"CollabClient connect error: {e}")
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

    def _make_join(self) -> dict:
        import hashlib as _hl
        r = self._room
        token = ""
        pwd = getattr(self, "_password", "")
        if pwd:
            token = _hl.sha256((r + "\x00" + pwd).encode("utf-8")).hexdigest()
        return {"name": self._name, "version": int(PROTOCOL_VERSION), "room": r, "token": token}

    async def _connect(self, host: str, port: int):
        try:
            self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=self._connect_timeout)
            try:
                sock = self._writer.get_extra_info("socket")
                if sock is not None:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    except Exception:
                        pass
            except Exception:
                pass
            join_msg = make_msg(MessageType.JOIN, self._make_join())
            self._writer.write(join_msg)
            self._bytes_sent += len(join_msg)
            await asyncio.wait_for(self._writer.drain(), timeout=5.0)
            header = await asyncio.wait_for(self._reader.readexactly(FRAME_HEADER_SIZE), timeout=self._connect_timeout)
            payload_len = struct.unpack(">I", header)[0]
            if payload_len == 0 or payload_len > MAX_MESSAGE_SIZE:
                raise ValueError(f"bad payload_len {payload_len}")
            payload = await asyncio.wait_for(self._reader.readexactly(payload_len), timeout=self._connect_timeout)
            self._bytes_received += FRAME_HEADER_SIZE + payload_len
            try:
                msg_type, data = parse_msg(payload)
            except ValueError:
                Logger.error("CollabClient: invalid join response")
                return
            if msg_type == MessageType.AUTH_FAIL:
                self._auth_error = str(data.get("reason", "auth"))
                with self._lock:
                    self._incoming.append((msg_type, data))
                if self._on_auth_failed:
                    try:
                        self._on_auth_failed(str(self._auth_error))
                    except Exception:
                        pass
                return
            if msg_type == MessageType.NET_KICK:
                self._auth_error = str(data.get("reason", "kicked"))
                with self._lock:
                    self._incoming.append((msg_type, data))
                if self._on_auth_failed:
                    try:
                        self._on_auth_failed(str(self._auth_error))
                    except Exception:
                        pass
                return
            if msg_type != MessageType.JOINED:
                self._auth_error = "protocol"
                return
            self._peer_id = str(data.get("your_id", ""))
            try:
                self._color = list(data.get("your_color", [0.5, 0.5, 0.5]))
            except Exception:
                self._color = [0.5, 0.5, 0.5]
            self._connected = True
            self._last_recv = time.monotonic()
            with self._lock:
                self._incoming.append((msg_type, data))
            if self._on_connected:
                try:
                    self._on_connected()
                except Exception:
                    pass
            await self._read_loop()
        except (asyncio.IncompleteReadError, ConnectionResetError, ValueError, asyncio.TimeoutError, OSError) as e:
            if not self._auth_error:
                Logger.warning(f"CollabClient connection failed: {e}")
        except Exception as e:
            Logger.error(f"CollabClient connection error: {e}")
        finally:
            self._connected = False
            if self._writer:
                try:
                    self._writer.close()
                    try:
                        await asyncio.wait_for(self._writer.wait_closed(), timeout=1.0)
                    except Exception:
                        pass
                except Exception:
                    pass
            if not self._stopped and self._on_disconnected:
                try:
                    self._on_disconnected()
                except Exception:
                    pass

    async def _read_loop(self):
        while not self._stopped and self._reader:
            try:
                header = await asyncio.wait_for(self._reader.readexactly(FRAME_HEADER_SIZE), timeout=25.0)
                payload_len = struct.unpack(">I", header)[0]
                if payload_len == 0 or payload_len > MAX_MESSAGE_SIZE:
                    raise ValueError(f"bad payload_len {payload_len}")
                payload = await asyncio.wait_for(self._reader.readexactly(payload_len), timeout=25.0)
                self._bytes_received += FRAME_HEADER_SIZE + payload_len
                self._last_recv = time.monotonic()
                try:
                    msg_type, data = parse_msg(payload)
                except ValueError:
                    continue
                if msg_type == MessageType.PING:
                    try:
                        pong = make_msg(MessageType.PONG, {"t": data.get("t", 0)})
                        self._writer.write(pong)
                        self._bytes_sent += len(pong)
                        try:
                            await asyncio.wait_for(self._writer.drain(), timeout=2.0)
                        except Exception:
                            pass
                    except Exception:
                        pass
                elif msg_type == MessageType.AUTH_FAIL:
                    self._auth_error = str(data.get("reason", "auth"))
                    with self._lock:
                        self._incoming.append((msg_type, data))
                    if self._on_auth_failed:
                        try:
                            self._on_auth_failed(str(self._auth_error))
                        except Exception:
                            pass
                    break
                elif msg_type == MessageType.NET_KICK:
                    with self._lock:
                        self._incoming.append((msg_type, data))
                    break
                else:
                    with self._lock:
                        self._incoming.append((msg_type, data))
            except (asyncio.IncompleteReadError, ConnectionResetError, ValueError, asyncio.TimeoutError):
                break
            except Exception:
                break

    def send(self, msg_type: int, data: dict):
        if not self._connected or not self._writer:
            return False
        try:
            msg = make_msg(msg_type, dict(data))
        except ValueError as e:
            Logger.warning(f"CollabClient send too large: {e}")
            return False
        except Exception as e:
            Logger.warning(f"CollabClient send encode error: {e}")
            return False
        try:
            if self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(self._async_send(msg), self._loop)
                return True
        except Exception as e:
            Logger.warning(f"CollabClient send error: {e}")
        return False

    async def _async_send(self, msg: bytes):
        try:
            if self._writer is None or self._writer.is_closing():
                return
            self._writer.write(msg)
            self._bytes_sent += len(msg)
            await asyncio.wait_for(self._writer.drain(), timeout=3.0)
        except Exception:
            pass

    def poll_messages(self) -> list[tuple[int, dict]]:
        with self._lock:
            msgs = list(self._incoming)
            self._incoming.clear()
            return msgs
