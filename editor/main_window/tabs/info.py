# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from typing import Optional

from core.ecs import Scene
from core.foundation.cmd import CommandHistory


class SceneTabInfo:
    __slots__ = ("name", "path", "scene", "dirty", "camera_state",
                 "selected_entity_ids", "play_mode", "scene_snapshot",
                 "prefab_path", "origin_tab", "pending_snapshot",
                 "restored_snapshot", "history", "pinned", "model_path")

    def __init__(self, name: str = "Scene", path: Optional[str] = None, scene: Optional[Scene] = None, model_path: str = ""):
        self.name = name
        self.path = path
        self.scene = scene
        self.dirty = False
        self.camera_state: Optional[dict] = None
        self.selected_entity_ids: list[str] = []
        self.play_mode: bool = False
        self.scene_snapshot: Optional[dict] = None
        self.prefab_path: Optional[str] = None
        self.origin_tab: Optional[str] = None
        self.pending_snapshot: str = ""
        self.restored_snapshot: str = ""
        self.history = CommandHistory()
        self.pinned: bool = False
        self.model_path: str = model_path or ""
