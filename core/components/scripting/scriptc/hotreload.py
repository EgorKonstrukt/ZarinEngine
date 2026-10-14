# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import inspect
import importlib.util
import os
from typing import Optional, Any, get_type_hints
from core.foundation.logger import Logger
from core.input.inpsys import Input, KeyCode
from core.maths.math3d import Vec2, Vec3, Vec4
from core.foundation.curve import Curve
from core.components.scripting.scriptc.fields import Range


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


class ScriptHotReloadMixin:
    _inspect_error_cache: dict[str, str] = {}
    _inspect_error_mtime: dict[str, float] = {}

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
                from core.engine.eng import Engine
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
        for node in __import__("ast").walk(tree):
            if isinstance(node, __import__("ast").ImportFrom):
                mod_name = node.module or ""
                if not mod_name.startswith("core."):
                    continue
                try:
                    spec = importlib.util.find_spec(mod_name)
                    if spec is None:
                        errors.append(f"{script_path}:{node.lineno}: No module named '{mod_name}' (did you mean 'core.maths.math3d' instead of 'core.math3d'?)")
                        continue
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
        if not errors:
            try:
                spec = importlib.util.spec_from_file_location("_user_script_check", script_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    self._inject_script_api(mod)
                    spec.loader.exec_module(mod)
            except Exception as ex:
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
            from core.components.scripting import cythonp as cython_support
            script_dir = cython_support.prepare_script_imports(script_path)
        except Exception:
            script_dir = ""
        if (self._py_class is not None and mtime is not None
                and self._py_mtime == mtime):
            return
        errors = self._collect_script_errors(script_path)
        if errors:
            key = self.script_path
            prev_mtime = self._inspect_error_mtime.get(key, None)
            prev_errors = self._inspect_error_cache.get(key, "")
            cur_sig = "\n".join(errors)
            if prev_mtime != mtime or prev_errors != cur_sig:
                msg = f"Script '{self.script_path}' has {len(errors)} error(s):\n" + "\n".join(f"  {e}" for e in errors)
                Logger.error(msg)
                self._inspect_error_cache[key] = cur_sig
                self._inspect_error_mtime[key] = mtime if mtime else 0
            self._py_instance = None
            self._cached_fields = []
            self._cached_hints = None
            return
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
            self._inject_script_api(mod)
            spec.loader.exec_module(mod)
            self._py_module = mod
            self._py_mtime = mtime
            try:
                from core.components.scripting import cythonp as _cy
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
            key = self.script_path
            if key not in self._inspect_error_cache:
                Logger.error(f"Script inspect error '{self.script_path}': {e}")
                self._inspect_error_cache[key] = str(e)
            pass

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
                    self._cached_hints = getattr(self._py_class, "__annotations__", {})
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
            from core.components.scripting import cythonp as _cy
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
