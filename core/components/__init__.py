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

for _sub in os.listdir(_package_dir):
    _sub_path = os.path.join(_package_dir, _sub)
    if os.path.isdir(_sub_path) and not _sub.startswith("_"):
        for _module_info in pkgutil.iter_modules([_sub_path]):
            if _module_info.name.startswith("_"):
                continue
            importlib.import_module(f"{__name__}.{_sub}.{_module_info.name}")

from core.ecs import ComponentRegistry
from core.components.rendering.camera import CameraProjection
from core.components.lighting.light import LightType

__all__ = ["ComponentRegistry", "CameraProjection", "LightType"]
for _name, _cls in ComponentRegistry.all().items():
    globals()[_name] = _cls
    __all__.append(_name)
