# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import socket
import struct


HEADER_FMT = "!I"
HEADER_SIZE = 4
MAX_MESSAGE = 256 * 1024 * 1024


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf.extend(chunk)
    return bytes(buf)


def send_json(sock: socket.socket, obj: dict) -> None:
    payload = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    header = struct.pack(HEADER_FMT, len(payload))
    sock.sendall(header + payload)


def recv_json(sock: socket.socket) -> dict:
    header = _recv_exact(sock, HEADER_SIZE)
    (size,) = struct.unpack(HEADER_FMT, header)
    if size > MAX_MESSAGE or size == 0:
        raise ConnectionError("bad size")
    payload = _recv_exact(sock, size)
    return json.loads(payload.decode("utf-8"))


def send_raw(sock: socket.socket, payload: bytes) -> None:
    header = struct.pack(HEADER_FMT, len(payload))
    sock.sendall(header + payload)


def recv_raw(sock: socket.socket) -> bytes:
    header = _recv_exact(sock, HEADER_SIZE)
    (size,) = struct.unpack(HEADER_FMT, header)
    if size > MAX_MESSAGE:
        raise ConnectionError("bad size")
    if size == 0:
        return b""
    return _recv_exact(sock, size)
