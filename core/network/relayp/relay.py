# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
from core.network.protocol import MessageType


_RELAY_COLORS = [
    [0.2, 0.6, 1.0],
    [1.0, 0.3, 0.3],
    [0.3, 1.0, 0.3],
    [1.0, 1.0, 0.2],
    [1.0, 0.5, 0.0],
    [0.8, 0.2, 1.0],
    [0.2, 1.0, 1.0],
    [1.0, 0.6, 0.6],
]


def _route_pair(msg_type: int) -> int:
    try:
        mt = int(msg_type)
    except Exception:
        return int(msg_type)
    mapping = {
        int(MessageType.CURSOR): int(MessageType.CURSOR_UPDATE),
        int(MessageType.CAMERA): int(MessageType.CAMERA_UPDATE),
        int(MessageType.ENTITY_CREATE): int(MessageType.ENTITY_CREATED),
        int(MessageType.ENTITY_DELETE): int(MessageType.ENTITY_DELETED),
        int(MessageType.TRANSFORM_UPDATE): int(MessageType.TRANSFORM_UPDATED),
        int(MessageType.SELECTION): int(MessageType.SELECTION_UPDATE),
        int(MessageType.COMPONENT_UPDATE): int(MessageType.COMPONENT_UPDATED),
        int(MessageType.COMPONENT_ADD): int(MessageType.COMPONENT_ADDED),
        int(MessageType.COMPONENT_REMOVE): int(MessageType.COMPONENT_REMOVED),
        int(MessageType.GIZMO_STATE): int(MessageType.GIZMO_STATE_UPDATE),
    }
    return mapping.get(mt, mt)


class _RoomPeer:
    __slots__ = ("peer_id", "name", "color", "ws", "last_seen")
    def __init__(self, peer_id: str, name: str, color: list[float], ws):
        self.peer_id = peer_id
        self.name = name
        self.color = color
        self.ws = ws
        self.last_seen = time.monotonic()


class _Room:
    __slots__ = ("code", "token", "peers", "color_idx", "created")
    def __init__(self, code: str, token: str):
        self.code = code
        self.token = token
        self.peers: dict[str, _RoomPeer] = {}
        self.color_idx = 0
        self.created = time.monotonic()
