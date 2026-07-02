# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import importlib
import pkgutil
import os

_package_dir = os.path.dirname(__file__)

for _module_info in pkgutil.iter_modules([_package_dir]):
    if _module_info.name.startswith("_"):
        continue
    if _module_info.name in ("inspector_meta",):
        continue
    importlib.import_module(f"{__name__}.{_module_info.name}")
    if _module_info.ispkg:
        for _sub_info in pkgutil.iter_modules([os.path.join(_package_dir, _module_info.name)]):
            if _sub_info.name.startswith("_"):
                continue
            importlib.import_module(f"{__name__}.{_module_info.name}.{_sub_info.name}")

from core.ecs import ComponentRegistry
from core.components.rendering.camera import CameraProjection
from core.components.lighting.light import LightType, LightAreaType

__all__ = ["ComponentRegistry", "CameraProjection", "LightType", "LightAreaType"]
for _name, _cls in ComponentRegistry.all().items():
    globals()[_name] = _cls
    __all__.append(_name)
