# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import inspect
from enum import Enum
from typing import Optional, Any, get_type_hints, get_origin, get_args
from core.ecs.ecs import Component, ComponentRegistry
from core.foundation.logger import Logger
from core.components.inspector_meta import FieldType, InspectorField
from core.maths.math3d import Vec2, Vec3, Vec4
from core.foundation.curve import Curve
from core.input.input_system import Input, KeyCode
import importlib.util
import os


class Range:
    def __init__(self, min_value: float = 0.0, max_value: float = 1.0, step: float | None = None):
        self.min_value = float(min_value)
        self.max_value = float(max_value)
        self.step = step


_METHOD_ALIASES: dict[str, tuple[str, ...]] = {
    "on_awake": ("on_awake", "awake"),
    "on_start": ("on_start", "start"),
    "on_update": ("on_update", "update"),
    "on_fixed_update": ("on_fixed_update", "fixed_update"),
    "on_destroy": ("on_destroy", "destroy"),
    "on_enable": ("on_enable", "enable"),
    "on_disable": ("on_disable", "disable"),
}

_COLLISION_CALLBACKS: tuple[str, ...] = (
    "on_collision_enter",
    "on_collision_stay",
    "on_collision_exit",
)

_SCRIPT_DETECT_NAMES: tuple[str, ...] = tuple(
    n for names in _METHOD_ALIASES.values() for n in names
) + _COLLISION_CALLBACKS + ("gizmo_lines", "gizmo_meshes")

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

@ComponentRegistry.register
class ScriptComponent(Component):
    _icon = "Script.png"
    _allow_multiple = True
    _gizmo_pass = "script"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
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

    @staticmethod
    def _find_method(obj: Any, canonical: str):
        for name in _METHOD_ALIASES.get(canonical, (canonical,)):
            meth = getattr(obj, name, None)
            if callable(meth):
                return meth
        return None

    @staticmethod
    def _inject_script_api(mod):
        mod.Input = Input
        mod.KeyCode = KeyCode
        mod.Vec2 = Vec2
        mod.Vec3 = Vec3
        mod.Vec4 = Vec4
        mod.Curve = Curve
        mod.Range = Range
        try:
            from core.foundation.logger import Logger as _Logger
            mod.Logger = _Logger
        except Exception:
            pass

    def _resolve_script_path(self) -> str:
        script_path = self.script_path
        if script_path and not os.path.isabs(script_path) and not os.path.exists(script_path):
            try:
                from core.engine.engine import Engine
                eng = Engine.instance()
            except Exception:
                eng = None
            if eng is not None:
                try:
                    candidate = os.path.normpath(os.path.join(eng.project_root, script_path))
                except Exception:
                    candidate = ""
                if candidate and os.path.exists(candidate):
                    script_path = candidate
        return script_path

    def get_script_abs_path(self) -> str:
        resolved = self._resolve_script_path()
        if resolved and not os.path.isabs(resolved):
            try:
                return os.path.abspath(resolved)
            except Exception:
                pass
        return resolved

    def get_script_display_name(self) -> str:
        p = self.script_path or ""
        try:
            return os.path.splitext(os.path.basename(p))[0] or p
        except Exception:
            return p

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

    _inspect_error_cache: dict[str, str] = {}
    _inspect_error_mtime: dict[str, float] = {}

    def _collect_script_errors(self, script_path: str) -> list[str]:
        errors: list[str] = []
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception as ex:
            return [f"{script_path}:0: cannot read file: {ex}"]
        try:
            tree = __import__("ast").parse(source, filename=script_path)
        except SyntaxError as se:
            return [f"{script_path}:{se.lineno}:{se.offset}: SyntaxError: {se.msg}"]
        # Collect all import errors without executing
        for node in __import__("ast").walk(tree):
            if isinstance(node, __import__("ast").ImportFrom):
                mod_name = node.module or ""
                if not mod_name.startswith("core."):
                    continue
                # Try to resolve the module
                try:
                    spec = importlib.util.find_spec(mod_name)
                    if spec is None:
                        errors.append(f"{script_path}:{node.lineno}: No module named '{mod_name}' (did you mean 'core.maths.math3d' instead of 'core.math3d'?)")
                        continue
                    # Check imported names
                    mod = importlib.import_module(mod_name)
                    for alias in node.names:
                        if not hasattr(mod, alias.name):
                            errors.append(f"{script_path}:{node.lineno}: cannot import name '{alias.name}' from '{mod_name}'")
                except Exception as ex:
                    errors.append(f"{script_path}:{node.lineno}: import error for '{mod_name}': {ex}")
            elif isinstance(node, __import__("ast").Import):
                for alias in node.names:
                    mod_name = alias.name
                    if not mod_name.startswith("core."):
                        continue
                    try:
                        spec = importlib.util.find_spec(mod_name)
                        if spec is None:
                            errors.append(f"{script_path}:{node.lineno}: No module named '{mod_name}'")
                    except Exception as ex:
                        errors.append(f"{script_path}:{node.lineno}: import error '{mod_name}': {ex}")
        # Try full exec to catch runtime import errors not caught above (e.g. circular)
        if not errors:
            try:
                spec = importlib.util.spec_from_file_location("_user_script_check", script_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    ScriptComponent._inject_script_api(mod)
                    spec.loader.exec_module(mod)
            except Exception as ex:
                # Extract line number if available
                import traceback as _tb
                tb = _tb.extract_tb(ex.__traceback__)
                lineno = tb[-1].lineno if tb else 0
                errors.append(f"{script_path}:{lineno}: {type(ex).__name__}: {ex}")
        return errors

    def _load_script_class(self):
        if not self.script_path:
            return
        script_path = self._resolve_script_path()
        try:
            mtime = os.path.getmtime(script_path)
        except Exception:
            mtime = None
        try:
            from core.components.scripting import cython_support
            script_dir = cython_support.prepare_script_imports(script_path)
        except Exception:
            script_dir = ""
        if (self._py_class is not None and mtime is not None
                and self._py_mtime == mtime):
            return
        # Smart Unity-like: collect ALL errors, show once per file change
        errors = self._collect_script_errors(script_path)
        if errors:
            key = self.script_path
            prev_mtime = self._inspect_error_mtime.get(key, None)
            prev_errors = self._inspect_error_cache.get(key, "")
            cur_sig = "\n".join(errors)
            if prev_mtime != mtime or prev_errors != cur_sig:
                # Show all errors as one consolidated block like Unity
                msg = f"Script '{self.script_path}' has {len(errors)} error(s):\n" + "\n".join(f"  {e}" for e in errors)
                Logger.error(msg)
                self._inspect_error_cache[key] = cur_sig
                self._inspect_error_mtime[key] = mtime if mtime else 0
            self._py_instance = None
            self._cached_fields = []
            self._cached_hints = None
            return
        # No errors -> clear cache
        self._inspect_error_cache.pop(self.script_path, None)
        self._inspect_error_mtime.pop(self.script_path, None)
        self._py_instance = None
        self._cached_fields = []
        self._cached_hints = None
        try:
            spec = importlib.util.spec_from_file_location("_user_script_inspect", script_path)
            if spec is None:
                Logger.warning(f"Script inspect spec is None for '{self.script_path}'")
                return
            mod = importlib.util.module_from_spec(spec)
            ScriptComponent._inject_script_api(mod)
            spec.loader.exec_module(mod)
            self._py_module = mod
            self._py_mtime = mtime
            try:
                from core.components.scripting import cython_support as _cy
                self._py_ext_sources = _cy.snapshot_ext_modules(script_dir) if script_dir else {}
            except Exception:
                self._py_ext_sources = {}
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and (any(hasattr(obj, n) for n in _SCRIPT_DETECT_NAMES) or hasattr(obj, "_inspector_buttons")):
                    if getattr(obj, "__module__", None) == mod.__name__:
                        self._py_class = obj
                        return
        except Exception as e:
            # Fallback single error (should already be caught above, but keep deduplication)
            key = self.script_path
            if key not in self._inspect_error_cache:
                Logger.error(f"Script inspect error '{self.script_path}': {e}")
                self._inspect_error_cache[key] = str(e)
            pass

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
        try:
            hints = get_type_hints(cls, include_extras=True)
        except Exception:
            try:
                hints = get_type_hints(cls)
            except Exception:
                hints = getattr(cls, '__annotations__', {})
        for name, ann in hints.items():
            if name.startswith('_'):
                continue
            base_ann, meta = self._split_annotated(ann)
            default = getattr(cls, name, None)
            if name not in self._field_values:
                self._field_values[name] = default
            slider = self._range_from_meta(meta)
            if slider is not None and base_ann is float:
                fields.append(InspectorField(name, name.replace('_', ' ').title(), FieldType.SLIDER,
                                             min_val=slider.min_value, max_val=slider.max_value,
                                             step=slider.step if slider.step else 0.01))
                continue
            if slider is not None and base_ann is int:
                fields.append(InspectorField(name, name.replace('_', ' ').title(), FieldType.INT_SLIDER,
                                             min_val=int(slider.min_value), max_val=int(slider.max_value),
                                             step=int(slider.step) if slider.step else 1))
                continue
            ft = self._py_type_to_field_type(base_ann)
            if ft == FieldType.ENUM:
                enum_cls = base_ann if isinstance(base_ann, type) else ann
                fields.append(InspectorField(name, name.replace('_', ' ').title(), ft, enum_class=enum_cls))
            else:
                fields.append(InspectorField(name, name.replace('_', ' ').title(), ft))
        for attr_name in dir(cls):
            if attr_name.startswith('_') or attr_name in hints:
                continue
            val = getattr(cls, attr_name, None)
            if isinstance(val, (int, float, bool, str)):
                if attr_name not in self._field_values:
                    self._field_values[attr_name] = val
                py_type = type(val)
                ft = PY_TYPE_TO_FIELD.get(py_type, FieldType.STRING)
                fields.append(InspectorField(attr_name, attr_name.replace('_', ' ').title(), ft))
        buttons = getattr(cls, '_inspector_buttons', None)
        if isinstance(buttons, list):
            for entry in buttons:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    method_name, label = entry[0], entry[1]
                    fields.append(InspectorField(method_name, label, FieldType.BUTTON))
        return fields

    def _py_type_to_field_type(self, t) -> FieldType:
        t, _meta = self._split_annotated(t)
        origin = getattr(t, '__origin__', None)
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
            if t_clean == 'Entity':
                return FieldType.GAMEOBJECT
        elif t.__name__ == 'Entity':
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
                    hints = getattr(self._py_class, '__annotations__', {})
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
                elif isinstance(hint, str) and hint.strip("'\"") == 'Entity':
                    setattr(self._py_instance, name, self._resolve_entity(value))
                elif hint is not None and hasattr(hint, '__name__') and hint.__name__ == 'Entity':
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

    def _load_script(self):
        if not self.script_path:
            return
        try:
            self.get_script_public_fields()
            self._load_script_class()
            if self._py_class:
                self._py_instance = self._py_class()
                try:
                    self._cached_hints = get_type_hints(self._py_class)
                except Exception:
                    self._cached_hints = getattr(self._py_class, '__annotations__', {})
                inst = self._py_instance
                self._py_methods = {}
                for canonical in _METHOD_ALIASES:
                    meth = self._find_method(inst, canonical)
                    if meth is not None:
                        self._py_methods[canonical] = meth
                self._py_has_update = "on_update" in self._py_methods
                self._py_has_fixed_update = "on_fixed_update" in self._py_methods
                self._py_has_awake = "on_awake" in self._py_methods
                self._py_has_start = "on_start" in self._py_methods
                self._py_has_destroy = "on_destroy" in self._py_methods
                self._py_has_enable = "on_enable" in self._py_methods
                self._py_has_disable = "on_disable" in self._py_methods
                self._py_collision_arity = {}
                for cb in _COLLISION_CALLBACKS:
                    meth = getattr(inst, cb, None)
                    if callable(meth):
                        try:
                            nargs = len(inspect.signature(meth).parameters)
                        except Exception:
                            nargs = 1
                        self._py_collision_arity[cb] = 2 if nargs >= 2 else 1
                self._apply_fields_to_instance()
        except Exception as e:
            Logger.error(f"Script load error '{self.script_path}': {e}")

    def _call_py(self, canonical: str, *args):
        meth = self._py_methods.get(canonical)
        if self._py_instance is None or meth is None:
            return
        try:
            meth(*args)
        except Exception as e:
            Logger.error(f"Script {canonical} error '{self.script_path}': {e}")

    def _check_hot_reload(self):
        if not self.hot_reload or not self.script_path:
            return
        try:
            mtime = os.path.getmtime(self._resolve_script_path())
        except Exception:
            return
        try:
            from core.components.scripting import cython_support as _cy
            pyx_changed = _cy.ext_sources_changed(self._py_ext_sources)
        except Exception:
            pyx_changed = False
        if self._py_instance is not None and mtime == self._py_mtime and not pyx_changed:
            return
        if self._py_instance is None and mtime == self._last_failed_mtime and not pyx_changed:
            return
        if pyx_changed:
            try:
                _cy.unload_ext_modules(self._py_ext_sources)
            except Exception:
                pass
        old_class, old_instance = self._py_class, self._py_instance
        old_methods, old_arity = self._py_methods, self._py_collision_arity
        old_ext, old_mtime = self._py_ext_sources, self._py_mtime
        self._py_class = None
        self._py_instance = None
        self._py_methods = {}
        self._cached_fields = []
        self._cached_hints = None
        self._load_script()
        if self._py_instance is not None:
            self._last_failed_mtime = None
            Logger.info(f"Script hot-reloaded '{self.script_path}'")
            self._call_py("on_awake")
            self._call_py("on_start")
        else:
            self._py_class, self._py_instance = old_class, old_instance
            self._py_methods, self._py_collision_arity = old_methods, old_arity
            self._py_ext_sources, self._py_mtime = old_ext, old_mtime
            self._last_failed_mtime = mtime

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
        if name.startswith('_script_'):
            field_name = name[8:]
            if field_name in self._field_values:
                return self._field_values[field_name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name.startswith('_script_'):
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
