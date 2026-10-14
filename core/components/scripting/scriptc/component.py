# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from core.ecs import Component, ComponentRegistry
from core.foundation.logger import Logger
from core.components.inspector_meta import FieldType, InspectorField
from core.maths.math3d import Vec2, Vec3, Vec4
from core.foundation.curve import Curve
from core.components.scripting.scriptc.fields import Range, RESOURCE_TYPE_FILTERS, PY_TYPE_TO_FIELD, ScriptFieldsMixin
from core.components.scripting.scriptc.hotreload import _METHOD_ALIASES, _COLLISION_CALLBACKS, _SCRIPT_DETECT_NAMES, ScriptHotReloadMixin


@ComponentRegistry.register
class ScriptComponent(ScriptFieldsMixin, ScriptHotReloadMixin, Component):
    _icon = "Script.png"
    _allow_multiple = True
    _gizmo_pass = "script"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Script Component", FieldType.HEADER),
            InspectorField("script_path", "Script", FieldType.RESOURCE_PATH, file_filter="Python Scripts (*.py)"),
        ]

    def __init__(self):
        super().__init__()
        self.script_path: str = ""
        self.hot_reload: bool = True
        self._py_instance: Optional[Any] = None
        self._py_module: Optional[Any] = None
        self._py_class: Optional[type] = None
        self._py_methods: dict[str, Any] = {}
        self._py_collision_arity: dict[str, int] = {}
        self._py_ext_sources: dict = {}
        self._field_values: dict[str, Any] = {}
        self._cached_fields: list[InspectorField] = []
        self._cached_hints: dict[str, Any] | None = None
        self._py_has_update: bool = False
        self._py_has_fixed_update: bool = False
        self._py_has_awake: bool = False
        self._py_has_start: bool = False
        self._py_has_destroy: bool = False
        self._py_has_enable: bool = False
        self._py_has_disable: bool = False
        self._py_mtime: Optional[float] = None
        self._last_failed_mtime: Optional[float] = None

    def on_start(self):
        if self.script_path:
            self._load_script()
        self._apply_fields_to_instance()
        self._call_py("on_awake")
        self._call_py("on_start")

    def on_update(self, dt: float):
        self._check_hot_reload()
        if self._py_instance and self._py_has_update:
            self._apply_fields_to_instance()
            self._call_py("on_update", dt)

    def on_fixed_update(self, dt: float):
        self._check_hot_reload()
        if self._py_instance and self._py_has_fixed_update:
            self._apply_fields_to_instance()
            self._call_py("on_fixed_update", dt)

    def on_enable(self):
        self._call_py("on_enable")

    def on_disable(self):
        self._call_py("on_disable")

    def on_destroy(self):
        self._call_py("on_destroy")

    def gizmo_lines(self):
        if not self._py_instance and self.script_path:
            self._load_script()
        if self._py_instance and hasattr(self._py_instance, "gizmo_lines"):
            try:
                return self._py_instance.gizmo_lines()
            except Exception as e:
                Logger.error(f"Script gizmo_lines error: {e}")
        return []

    def gizmo_meshes(self):
        if not self._py_instance and self.script_path:
            self._load_script()
        if self._py_instance and hasattr(self._py_instance, "gizmo_meshes"):
            try:
                return self._py_instance.gizmo_meshes()
            except Exception as e:
                Logger.error(f"Script gizmo_meshes error: {e}")
        return []

    @classmethod
    def gizmo_collect_meshes(cls, scene):
        meshes = []
        for entity in scene.get_entities_with_component(cls):
            if not entity.active:
                continue
            for c in entity.get_components(cls):
                try:
                    msh = c.gizmo_meshes()
                    if msh:
                        meshes.extend(msh)
                except Exception:
                    pass
        return meshes

    def __getattr__(self, name):
        if name.startswith("_script_"):
            field_name = name[8:]
            if field_name in self._field_values:
                return self._field_values[field_name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name.startswith("_script_"):
            field_name = name[8:]
            self._field_values[field_name] = value
        else:
            super().__setattr__(name, value)

    def serialize(self) -> dict:
        d = super().serialize()
        d["script_path"] = self.script_path
        fields = {}
        for name, value in self._field_values.items():
            if isinstance(value, Vec2):
                fields[name] = [value.x, value.y]
            elif isinstance(value, Vec3):
                fields[name] = [value.x, value.y, value.z]
            elif isinstance(value, Vec4):
                fields[name] = [value.x, value.y, value.z, value.w]
            elif isinstance(value, Enum):
                fields[name] = value.value
            elif isinstance(value, Curve):
                fields[name] = value.to_dict()
            else:
                fields[name] = value
        d["script_fields"] = fields
        return d

    @classmethod
    def deserialize(cls, data: dict) -> ScriptComponent:
        sc = cls()
        sc.enabled = data.get("enabled", True)
        sc.script_path = data.get("script_path", "")
        raw_fields = data.get("script_fields", {})
        field_values = {}
        for name, value in raw_fields.items():
            if isinstance(value, dict) and "keys" in value:
                try:
                    field_values[name] = Curve.from_dict(value)
                    continue
                except Exception:
                    pass
            field_values[name] = value
        sc._field_values = field_values
        return sc
