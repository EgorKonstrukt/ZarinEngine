# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
from typing import Optional
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
