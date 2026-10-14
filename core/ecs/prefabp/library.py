# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from typing import Optional
from core.foundation.progress import task_complete, task_start
from core.ecs.prefabp.prefab import Prefab


class PrefabLibrary:
    _prefabs: dict[str, Prefab] = {}
    _guids: dict[str, str] = {}

    @classmethod
    def register(cls, path: str, prefab: Prefab):
        cls._prefabs[path] = prefab
        cls._guids[prefab.guid] = path

    @classmethod
    def load(cls, path: str) -> Optional[Prefab]:
        if not os.path.exists(path):
            return None
        if path in cls._prefabs:
            return cls._prefabs[path]
        task_start("prefab_load:" + path, f"Loading prefab {os.path.basename(path)}...")
        try:
            p = Prefab.load(path)
            if p:
                cls._prefabs[path] = p
                cls._guids[p.guid] = path
            return p
        finally:
            task_complete("prefab_load:" + path)

    @classmethod
    def get_all(cls) -> dict[str, Prefab]:
        return dict(cls._prefabs)

    @classmethod
    def path_for_guid(cls, guid: str) -> Optional[str]:
        return cls._guids.get(guid)

    @classmethod
    def invalidate(cls, path: str):
        p = cls._prefabs.pop(path, None)
        if p:
            cls._guids.pop(p.guid, None)

    @classmethod
    def clear(cls):
        cls._prefabs.clear()
        cls._guids.clear()
