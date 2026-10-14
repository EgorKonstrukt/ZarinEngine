# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional, Type
from .component import Component
_SUBCLASS_CACHE: dict = {}
_SUBCLASS_CACHE_VERSION: int = 0


def _subclass_names(key: str, cls) -> list:
    cached = _SUBCLASS_CACHE.get(key)
    if cached is not None and cached[0] == _SUBCLASS_CACHE_VERSION:
        return cached[1]
    found: list = []
    try:
        for reg_name, reg_cls in ComponentRegistry._registry.items():
            if reg_name != key and issubclass(reg_cls, cls):
                found.append(reg_name)
    except Exception:
        found = []
    _SUBCLASS_CACHE[key] = (_SUBCLASS_CACHE_VERSION, found)
    return found


class ComponentRegistry:
    _registry: dict[str, Type[Component]] = {}
    _aliases: dict[str, str] = {"Sky": "ProceduralSky"}
    _categories: dict[str, list[str]] = {}
    _category_name_map: dict[str, str] = {
        "transform": "Transform",
        "rendering": "Rendering",
        "physics": "Physics",
        "physics2d": "Physics 2D",
        "lighting": "Lighting",
        "audio": "Audio",
        "constraints": "Constraints",
        "network": "Network",
        "scripting": "Scripting",
    }
    @classmethod
    def register(cls, comp_cls: Type[Component]):
        global _SUBCLASS_CACHE_VERSION
        name = comp_cls.__name__
        cls._registry[name] = comp_cls
        _SUBCLASS_CACHE_VERSION += 1
        category = cls._infer_category(comp_cls)
        if category:
            cls._categories[name] = [category]
        return comp_cls
    @classmethod
    def _infer_category(cls, comp_cls: Type[Component]) -> Optional[str]:
        module = getattr(comp_cls, "__module__", "")
        parts = module.split(".")
        for i, part in enumerate(parts):
            if part == "components" and i + 1 < len(parts):
                sub = parts[i + 1]
                return cls._category_name_map.get(sub, sub.capitalize())
        return None
    @classmethod
    def get(cls, name: str) -> Optional[Type[Component]]:
        comp = cls._registry.get(name)
        if comp is None and name:
            alias = cls._aliases.get(name)
            if alias is not None:
                comp = cls._registry.get(alias)
        return comp
    @classmethod
    def all(cls) -> dict[str, Type[Component]]:
        return dict(cls._registry)
    @classmethod
    def get_categories(cls, comp_name: str) -> list[str]:
        return list(cls._categories.get(comp_name, []))
    @classmethod
    def all_categories(cls) -> dict[str, list[str]]:
        return dict(cls._categories)
