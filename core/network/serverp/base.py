# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import asyncio
import socket
import struct
import time
import uuid
from typing import Optional
from core.foundation.logger import Logger
from core.network.protocol import MessageType, make_msg, parse_msg, FRAME_HEADER_SIZE, PROTOCOL_VERSION, normalize_room
from core.config.constants import MAX_MESSAGE_SIZE


class CollabClientInfo:
    __slots__ = ("reader", "writer", "peer_id", "name", "color", "addr", "last_seen", "window_start", "window_count", "dropped")

    def __init__(self, reader, writer, peer_id: str, name: str, color: list[float], addr: str):
        self.reader = reader
        self.writer = writer
        self.peer_id = peer_id
        self.name = name
        self.color = color
        self.addr = addr
        self.last_seen = time.monotonic()
        self.window_start = time.monotonic()
        self.window_count = 0
        self.dropped = 0


_COLORS = [
    [0.2, 0.6, 1.0],
    [1.0, 0.3, 0.3],
    [0.3, 1.0, 0.3],
    [1.0, 1.0, 0.2],
    [1.0, 0.5, 0.0],
    [0.8, 0.2, 1.0],
    [0.2, 1.0, 1.0],
    [1.0, 0.6, 0.6],
]


class _ServerBase:
    def __init__(self, host: str = "0.0.0.0", port: int = 9876, password: str = "", max_clients: int = 32, room: str = "", heartbeat_timeout: float = 20.0, ssl_context=None):
        self._host = str(host or "0.0.0.0")
        self._port = int(port)
        self._password = str(password or "")
        self._max_clients = max(1, int(max_clients))
        self._room = normalize_room(room)
        self._heartbeat_timeout = max(5.0, float(heartbeat_timeout))
        self._ssl_context = ssl_context
        self._clients: dict[str, CollabClientInfo] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._color_idx = 0
        self._running = False
        self._scene_data = None
        self._sweeper_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def room(self) -> str:
        return self._room

    @property
    def has_password(self) -> bool:
        return bool(self._password)

    def set_password(self, password: str):
        self._password = str(password or "")

    def set_room(self, room: str):
        self._room = normalize_room(room)

    def set_max_clients(self, n: int):
        self._max_clients = max(1, int(n))

    async def start(self):
        kwargs = {}
        if self._ssl_context is not None:
            kwargs["ssl"] = self._ssl_context
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port, **kwargs)
        for s in self._server.sockets or []:
            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
        self._running = True
        try:
            self._sweeper_task = asyncio.create_task(self._sweep_loop())
        except Exception:
            self._sweeper_task = None
        Logger.info(f"CollabServer listening on {self._host}:{self._port}")

    async def stop(self):
        self._running = False
        if self._sweeper_task is not None:
            try:
                self._sweeper_task.cancel()
            except Exception:
                pass
            self._sweeper_task = None
        for c in list(self._clients.values()):
            try:
                c.writer.close()
                try:
                    await asyncio.wait_for(c.writer.wait_closed(), timeout=1.0)
                except Exception:
                    pass
            except Exception:
                pass
        self._clients.clear()
        if self._server:
            try:
                self._server.close()
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        Logger.info("CollabServer stopped")

    async def _sweep_loop(self):
        while self._running:
            try:
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break
            except Exception:
                continue
            now = time.monotonic()
            stale: list[str] = []
            for pid, info in list(self._clients.items()):
                if now - info.last_seen > self._heartbeat_timeout:
                    stale.append(pid)
            for pid in stale:
                info = self._clients.get(pid)
                if info is None:
                    continue
                try:
                    info.writer.close()
                except Exception:
                    pass

    async def _read_frame(self, reader: asyncio.StreamReader) -> tuple[int, dict]:
        header = await asyncio.wait_for(reader.readexactly(FRAME_HEADER_SIZE), timeout=30.0)
        payload_len = struct.unpack(">I", header)[0]
        if payload_len == 0 or payload_len > MAX_MESSAGE_SIZE:
            raise ValueError(f"bad payload_len {payload_len}")
        payload = await asyncio.wait_for(reader.readexactly(payload_len), timeout=30.0)
        return parse_msg(payload)

    def _check_rate(self, info: CollabClientInfo) -> bool:
        now = time.monotonic()
        if now - info.window_start >= 1.0:
            info.window_start = now
            info.window_count = 0
        info.window_count += 1
        if info.window_count > 400:
            info.dropped += 1
            return False
        return True

    def _auth_ok(self, data: dict) -> bool:
        if self._room:
            want = self._room
            got = normalize_room(data.get("room", ""))
            if got and got != want:
                return False
        if self._password:
            import hashlib
            r = self._room or normalize_room(data.get("room", ""))
            token = str(data.get("token", ""))
            expect = hashlib.sha256((r + "\x00" + self._password).encode("utf-8")).hexdigest()
            if token != expect:
                plain = str(data.get("password", ""))
                if plain != self._password:
                    return False
        return True

    def _broadcast(self, msg_type: int, data: dict, exclude: Optional[str] = None):
        try:
            msg = make_msg(msg_type, data)
        except Exception:
            return
        for pid, cinfo in list(self._clients.items()):
            if pid == exclude:
                continue
            try:
                cinfo.writer.write(msg)
            except Exception:
                pass

    async def _broadcast_and_drain(self, msg_type: int, data: dict, exclude: Optional[str] = None):
        self._broadcast(msg_type, data, exclude)
        tasks = []
        for cinfo in list(self._clients.values()):
            try:
                if cinfo.writer.is_closing():
                    continue
            except Exception:
                continue
            try:
                tasks.append(asyncio.create_task(asyncio.wait_for(cinfo.writer.drain(), timeout=2.0)))
            except Exception:
                pass
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass

    async def _send_to_one(self, peer_id: str, msg_type: int, data: dict):
        cinfo = self._clients.get(str(peer_id))
        if cinfo is None:
            return
        try:
            cinfo.writer.write(make_msg(msg_type, data))
            await asyncio.wait_for(cinfo.writer.drain(), timeout=2.0)
        except Exception:
            pass

    def update_scene_data(self, scene: dict):
        self._scene_data = scene
