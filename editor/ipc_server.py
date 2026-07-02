# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import os
import socket
import struct
import threading
from typing import Optional, Callable

from editor.constants import IPC_HOST, IPC_PORT


class IpcServer:
    def __init__(self, on_file: Callable[[str], None]):
        self._on_file = on_file
        self._server: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def try_bind(self) -> bool:
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind((IPC_HOST, IPC_PORT))
            self._server.listen(1)
            self._running = True
            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._thread.start()
            return True
        except OSError:
            self._server = None
            return False

    def _accept_loop(self):
        while self._running:
            try:
                conn, _ = self._server.accept()
                with conn:
                    size_data = conn.recv(4)
                    if len(size_data) < 4:
                        continue
                    size = struct.unpack("!I", size_data)[0]
                    data = b""
                    while len(data) < size:
                        chunk = conn.recv(size - len(data))
                        if not chunk:
                            break
                        data += chunk
                    if data:
                        msg = json.loads(data.decode("utf-8"))
                        file_path = msg.get("file", "")
                        if file_path:
                            self._on_file(file_path)
            except Exception:
                break

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass


def send_file_to_running_instance(file_path: str) -> bool:
    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(3)
        conn.connect((IPC_HOST, IPC_PORT))
        msg = json.dumps({"file": os.path.abspath(file_path)}).encode("utf-8")
        conn.sendall(struct.pack("!I", len(msg)) + msg)
        conn.close()
        return True
    except Exception:
        return False
