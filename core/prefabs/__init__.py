# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.prefabs.registry import (
    SystemPrefabEntry,
    register_system_prefab,
    system_prefab,
    unregister_system_prefab,
    get_system_prefab,
    get_system_prefabs,
    create_system_prefab,
    ensure_builtin_prefabs,
)

__all__ = [
    "SystemPrefabEntry",
    "register_system_prefab",
    "system_prefab",
    "unregister_system_prefab",
    "get_system_prefab",
    "get_system_prefabs",
    "create_system_prefab",
    "ensure_builtin_prefabs",
]
