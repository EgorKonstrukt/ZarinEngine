# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from enum import Enum
from typing import Any, get_type_hints, get_origin, get_args
from core.components.inspector_meta import FieldType, InspectorField
from core.maths.math3d import Vec2, Vec3, Vec4
from core.foundation.curve import Curve


class Range:
    def __init__(self, min_value: float = 0.0, max_value: float = 1.0, step: float | None = None):
        self.min_value = float(min_value)
        self.max_value = float(max_value)
        self.step = step


RESOURCE_TYPE_FILTERS = {
    "mesh": "Models (*.obj *.fbx *.stl *.gltf *.glb *.usdz *.dae *.3ds *.blend)",
    "material": "Materials (*.zpem *.mat)",
    "texture": "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff *.webp *.hdr *.exr *.dds *.svg)",
    "audio": "Audio (*.wav *.mp3 *.ogg *.flac *.aiff *.m4a)",
    "script": "Python Scripts (*.py)",
    "prefab": "Prefabs (*.zpep)",
    "scene": "Scenes (*.zpes)",
    "animclip": "Animation Clips (*.animclip)",
    "animcontroller": "Animator Controllers (*.animcontroller)",
    "physicmaterial": "Physics Materials (*.zphysmat)",
}

PY_TYPE_TO_FIELD = {
    float: FieldType.FLOAT,
    int: FieldType.INT,
    bool: FieldType.BOOL,
    str: FieldType.STRING,
    Vec2: FieldType.VEC2,
    Vec3: FieldType.VEC3,
    Vec4: FieldType.VEC4,
}


class ScriptFieldsMixin:
    def get_script_public_fields(self) -> list[InspectorField]:
        if not self.script_path:
            self._cached_fields = []
            return []
        if self._cached_fields:
            return self._cached_fields
        if self._py_class is None:
            self._load_script_class()
        if self._py_class is None:
            return []
        self._cached_fields = self._build_fields_from_class(self._py_class)
        return self._cached_fields

    @staticmethod
    def _split_annotated(ann):
        try:
            if get_origin(ann) is not None and str(get_origin(ann)).endswith("Annotated"):
                args = get_args(ann)
                if args:
                    return args[0], args[1:]
        except Exception:
            pass
        origin = getattr(ann, "__origin__", None)
        if origin is not None and getattr(origin, "__name__", "") == "Annotated":
            args = getattr(ann, "__args__", ()) or ()
            if args:
                return args[0], args[1:]
        return ann, ()

    @staticmethod
    def _range_from_meta(meta) -> Range | None:
        for m in meta:
            if isinstance(m, Range):
                return m
            if isinstance(m, (list, tuple)) and len(m) >= 2:
                try:
                    return Range(float(m[0]), float(m[1]), float(m[2]) if len(m) >= 3 else None)
                except Exception:
                    continue
        return None

    def _build_fields_from_class(self, cls) -> list[InspectorField]:
        fields = []
        fields.append(InspectorField("", "Script Variables", FieldType.HEADER))
        try:
            hints = get_type_hints(cls, include_extras=True)
        except Exception:
            try:
                hints = get_type_hints(cls)
            except Exception:
                hints = getattr(cls, "__annotations__", {})
        for name, ann in hints.items():
            if name.startswith("_"):
                continue
            base_ann, meta = self._split_annotated(ann)
            default = getattr(cls, name, None)
            if name not in self._field_values:
                self._field_values[name] = default
            slider = self._range_from_meta(meta)
            if slider is not None and base_ann is float:
                fields.append(InspectorField(name, name.replace("_", " ").title(), FieldType.SLIDER,
                                             min_val=slider.min_value, max_val=slider.max_value,
                                             step=slider.step if slider.step else 0.01))
                continue
            if slider is not None and base_ann is int:
                fields.append(InspectorField(name, name.replace("_", " ").title(), FieldType.INT_SLIDER,
                                             min_val=int(slider.min_value), max_val=int(slider.max_value),
                                             step=int(slider.step) if slider.step else 1))
                continue
            ft = self._py_type_to_field_type(base_ann)
            if ft == FieldType.ENUM:
                enum_cls = base_ann if isinstance(base_ann, type) else ann
                fields.append(InspectorField(name, name.replace("_", " ").title(), ft, enum_class=enum_cls))
            else:
                fields.append(InspectorField(name, name.replace("_", " ").title(), ft))
        for attr_name in dir(cls):
            if attr_name.startswith("_") or attr_name in hints:
                continue
            val = getattr(cls, attr_name, None)
            if isinstance(val, (int, float, bool, str)):
                if attr_name not in self._field_values:
                    self._field_values[attr_name] = val
                py_type = type(val)
                ft = PY_TYPE_TO_FIELD.get(py_type, FieldType.STRING)
                fields.append(InspectorField(attr_name, attr_name.replace("_", " ").title(), ft))
        buttons = getattr(cls, "_inspector_buttons", None)
        if isinstance(buttons, list):
            for entry in buttons:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    method_name, label = entry[0], entry[1]
                    fields.append(InspectorField(method_name, label, FieldType.BUTTON))
        return fields

    def _py_type_to_field_type(self, t) -> FieldType:
        t, _meta = self._split_annotated(t)
        origin = getattr(t, "__origin__", None)
        if origin is not None:
            t = origin
        if isinstance(t, type) and issubclass(t, Enum):
            return FieldType.ENUM
        if t is float:
            return FieldType.FLOAT
        if t is int:
            return FieldType.INT
        if t is bool:
            return FieldType.BOOL
        if t is str:
            return FieldType.STRING
        if t is Vec2:
            return FieldType.VEC2
        if t is Vec3:
            return FieldType.VEC3
        if t is Vec4:
            return FieldType.VEC4
        if t is Curve:
            return FieldType.CURVE
        if isinstance(t, str):
            t_clean = t.strip("'\"")
            if t_clean == "Entity":
                return FieldType.GAMEOBJECT
        elif t.__name__ == "Entity":
            return FieldType.GAMEOBJECT
        return FieldType.FLOAT

    def get_field_value(self, name: str) -> Any:
        return self._field_values.get(name, None)

    def set_field_value(self, name: str, value: Any):
        self._field_values[name] = value

    def _resolve_entity(self, value):
        if isinstance(value, str) and value and self._entity and self._entity._scene:
            return self._entity._scene.get_entity(value)
        return value

    def _apply_fields_to_instance(self):
        if not self._py_instance:
            return
        hints = self._cached_hints
        if hints is None:
            hints = {}
            if self._py_class:
                try:
                    hints = get_type_hints(self._py_class)
                except Exception:
                    hints = getattr(self._py_class, "__annotations__", {})
            self._cached_hints = hints
        for name, value in self._field_values.items():
            try:
                hint = hints.get(name)
                if isinstance(value, list) and hint is Vec2:
                    setattr(self._py_instance, name, Vec2(value[0], value[1]))
                elif isinstance(value, list) and hint is Vec3:
                    setattr(self._py_instance, name, Vec3(value[0], value[1], value[2]))
                elif isinstance(value, list) and hint is Vec4:
                    setattr(self._py_instance, name, Vec4(value[0], value[1], value[2], value[3]))
                elif isinstance(hint, str) and hint.strip("'\"") == "Entity":
                    setattr(self._py_instance, name, self._resolve_entity(value))
                elif hint is not None and hasattr(hint, "__name__") and hint.__name__ == "Entity":
                    setattr(self._py_instance, name, self._resolve_entity(value))
                elif isinstance(hint, type) and issubclass(hint, Enum):
                    if not isinstance(value, hint):
                        value = hint(value)
                    setattr(self._py_instance, name, value)
                else:
                    setattr(self._py_instance, name, value)
            except Exception:
                pass
        self._py_instance._entity = self._entity
