# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class SystemPrefabEntry:
    menu_path: str
    name: str
    order: int = 100
    description: str = ""
    build: Optional[Callable] = None
    prefab: Optional[object] = None
    icon: str = ""


_ENTRIES: dict[str, SystemPrefabEntry] = {}
_BUILTINS_LOADED: bool = False


def _normalize_menu_path(path: str) -> str:
    parts = [p.strip() for p in str(path).split("/") if p.strip()]
    return "/".join(parts)


def register_system_prefab(menu_path=None, build=None, *, name: Optional[str] = None,
                            order: int = 100, description: str = "",
                            prefab=None, overwrite: bool = False, icon: str = ""):
    if callable(menu_path) and build is None and name is None and prefab is None:
        fn = menu_path
        derived = getattr(fn, "__name__", "Prefab").replace("_", " ").strip().title()
        return _register_entry(derived, fn, derived, order, description, None, overwrite, icon)
    if build is not None and callable(build) and prefab is None:
        entry_path = _normalize_menu_path(menu_path)
        entry_name = name or (entry_path.split("/")[-1] if entry_path else "Prefab")
        return _register_entry(entry_path, build, entry_name, order, description, None, overwrite, icon)

    def decorator(fn):
        entry_path = _normalize_menu_path(menu_path)
        entry_name = name or (entry_path.split("/")[-1] if entry_path else getattr(fn, "__name__", "Prefab"))
        return _register_entry(entry_path, fn, entry_name, order, description, None, overwrite, icon)
    if prefab is not None:
        entry_path = _normalize_menu_path(menu_path)
        entry_name = name or (entry_path.split("/")[-1] if entry_path else getattr(prefab, "name", "Prefab"))
        return _register_entry(entry_path, None, entry_name, order, description, prefab, overwrite, icon)
    return decorator


def _register_entry(menu_path: str, build, name: str, order: int,
                    description: str, prefab, overwrite: bool, icon: str = "") -> SystemPrefabEntry:
    key = _normalize_menu_path(menu_path)
    if not key:
        raise ValueError("menu_path must not be empty")
    if key in _ENTRIES and not overwrite:
        raise ValueError(f"System prefab already registered: {key}")
    entry = SystemPrefabEntry(menu_path=key, name=name, order=order,
                              description=description, build=build, prefab=prefab, icon=icon)
    _ENTRIES[key] = entry
    return entry


def system_prefab(menu_path=None, build=None, *, name: Optional[str] = None,
                   order: int = 100, description: str = "",
                   prefab=None, overwrite: bool = False, icon: str = ""):
    return register_system_prefab(menu_path, build, name=name, order=order,
                                  description=description, prefab=prefab,
                                  overwrite=overwrite, icon=icon)


def unregister_system_prefab(menu_path: str) -> bool:
    return _ENTRIES.pop(_normalize_menu_path(menu_path), None) is not None


def get_system_prefab(menu_path: str) -> Optional[SystemPrefabEntry]:
    return _ENTRIES.get(_normalize_menu_path(menu_path))


def ensure_builtin_prefabs() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
    try:
        from core.prefabs import builtins as _builtins
        _builtins.register_all()
    except Exception:
        pass


def get_system_prefabs() -> list[SystemPrefabEntry]:
    ensure_builtin_prefabs()
    return sorted(_ENTRIES.values(), key=lambda e: (e.order, e.menu_path.lower()))


def create_system_prefab(menu_path: str, scene, parent=None) -> list:
    ensure_builtin_prefabs()
    entry = _ENTRIES.get(_normalize_menu_path(menu_path))
    if entry is None:
        return []
    spawned: list = []
    if entry.build is not None:
        result = entry.build(scene)
        if result is None:
            return []
        items = result if isinstance(result, list) else [result]
        for entity in items:
            if entity is None:
                continue
            if parent is not None and getattr(entity, "_parent", None) is None:
                try:
                    entity.set_parent(parent)
                except Exception:
                    pass
            spawned.append(entity)
        return spawned
    if entry.prefab is not None:
        try:
            from core.engine.engine import Engine
            registry = Engine.instance()._component_registry
        except Exception:
            registry = None
        if registry is None:
            return []
        try:
            spawned = entry.prefab.instantiate_plain(scene, registry, parent)
        except Exception:
            try:
                spawned = entry.prefab.instantiate(scene, registry, parent)
                from core.ecs.prefab import Prefab as _Prefab
                for root in spawned:
                    _Prefab.unpack(root)
            except Exception:
                return []
        return list(spawned)
    return []
