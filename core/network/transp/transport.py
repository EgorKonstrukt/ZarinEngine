# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import threading
import time
from collections import deque
from typing import Optional
from core.network.protocol import MessageType
from core.network.transp.server import GameServer
from core.network.transp.client import GameClient


class Transport:
    _instance: Optional[Transport] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._incoming: deque[tuple[int, dict]] = deque()
        self._lock = threading.Lock()
        self._server: Optional[GameServer] = None
        self._client: Optional[GameClient] = None
        self._role: str = "none"
        self._local_id: int = -1
        self._connected = False

    @classmethod
    def instance(cls) -> Transport:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = Transport()
        return cls._instance

    @property
    def is_server(self) -> bool:
        return self._role == "server"

    @property
    def is_client(self) -> bool:
        return self._role == "client"

    @property
    def is_connected(self) -> bool:
        if self._role == "server":
            return self._server is not None and self._server.running
        if self._role == "client":
            return self._client is not None and self._client.connected
        return False

    @property
    def local_id(self) -> int:
        if self._role == "server":
            return 0
        if self._role == "client" and self._client:
            return self._client.peer_id
        return self._local_id

    @property
    def peer_count(self) -> int:
        if self._role == "server" and self._server:
            return self._server.client_count
        if self._role == "client":
            return 1 if self.is_connected else 0
        return 0

    @property
    def bytes_sent(self) -> int:
        if self._client:
            return self._client.bytes_sent
        return 0

    @property
    def bytes_received(self) -> int:
        if self._client:
            return self._client.bytes_received
        return 0

    def host(self, host: str = "0.0.0.0", port: int = 7777, max_players: int = 16) -> bool:
        self.disconnect()
        self._server = GameServer(host, port, self._incoming, self._lock, max_players=max_players)
        ok = self._server.start()
        if ok:
            self._role = "server"
            self._local_id = 0
            self._connected = True
        return bool(ok)

    def connect(self, host: str = "127.0.0.1", port: int = 7777, name: str = "Player") -> bool:
        self.disconnect()
        self._client = GameClient(self._incoming, self._lock)
        self._client.connect(host, port, name)
        self._role = "client"
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if self._client.connected:
                self._connected = True
                return True
            with self._lock:
                for mt, d in list(self._incoming):
                    if mt == MessageType.NET_KICK:
                        self.disconnect()
                        return False
            time.sleep(0.02)
        ok = self._client.connected
        self._connected = bool(ok)
        return bool(ok)

    def disconnect(self):
        if self._client:
            self._client.disconnect()
            self._client = None
        if self._server:
            self._server.stop()
            self._server = None
        self._role = "none"
        self._connected = False
        self._local_id = -1
        with self._lock:
            self._incoming.clear()

    def send(self, msg_type: int, data: dict):
        if self._role == "client" and self._client:
            self._client.send(msg_type, data)
        elif self._role == "server" and self._server:
            self._server.broadcast(msg_type, data)

    def send_to(self, peer_id: int, msg_type: int, data: dict):
        if self._role == "server" and self._server:
            self._server.send_to(peer_id, msg_type, data)
        elif self._role == "client" and self._client:
            self._client.send(msg_type, data)

    def broadcast(self, msg_type: int, data: dict):
        self.send(msg_type, data)

    def poll(self) -> list[tuple[int, dict]]:
        with self._lock:
            msgs = list(self._incoming)
            self._incoming.clear()
            return msgs

    def peek(self) -> list[tuple[int, dict]]:
        with self._lock:
            return list(self._incoming)

    def get_peers(self) -> list[dict]:
        if self._role == "server" and self._server:
            return [{"id": c.peer_id, "name": c.name} for c in self._server.clients.values()]
        return []


def get_transport() -> Transport:
    return Transport.instance()
