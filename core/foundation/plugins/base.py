# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import os
import platform
import sys
from typing import Any, Callable, Optional, TYPE_CHECKING
from core.foundation.logger import Logger
if TYPE_CHECKING:
    from core.engine.eng import Engine


def _zarin_user_dir(name: str = "") -> str:
    base = os.path.join(os.path.expanduser("~"), ".zarin")
    if name:
        base = os.path.join(base, name)
    os.makedirs(base, exist_ok=True)
    return base


def current_architecture() -> str:
    sys_name = sys.platform
    machine = platform.machine().lower()
    if sys_name == "win32":
        sys_name = "win"
    elif sys_name == "darwin":
        sys_name = "macos"
    if machine in ("amd64", "x86_64", "x64"):
        machine = "x86_64"
    elif machine in ("aarch64", "arm64"):
        machine = "arm64"
    elif machine in ("i386", "i686", "x86"):
        machine = "x86"
    return f"{sys_name}_{machine}"


def _platform_matches(manifest_arch: str) -> bool:
    if not manifest_arch or manifest_arch == "any":
        return True
    current = current_architecture()
    if manifest_arch == current:
        return True
    return False


def _plugin_cache_root() -> str:
    return _zarin_user_dir("plugins")


def _resolve_zplugin(name: str, version: str) -> str:
    safe = name.replace("/", "_").replace("\\", "_").strip()
    return os.path.join(_plugin_cache_root(), f"{safe}-{version}")


def _project_root():
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(cur) == "core":
            return os.path.dirname(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PLUGIN_API_VERSION = 1


class PluginBase:
    NAME: str = "UnnamedPlugin"
    VERSION: str = "0.0.1"
    DESCRIPTION: str = ""
    SYSTEM: bool = False

    def __init__(self):
        self._engine: Optional[Engine] = None
        self._manager: Optional[PluginManager] = None
        self._enabled: bool = True
        self._config: dict = {}
        self._config_path: Optional[str] = None
        self._docks: list[dict] = []
        self._toolbar_actions: list[dict] = []
        self._toolbar_items: list[dict] = []
        self._menu_items: list[dict] = []
        self._file_openers: list[dict] = []
        self._components: list[type] = []
        self._patches = None
        self._bundled_library_dir: Optional[str] = None

    def initialize(self, engine: Engine):
        self._engine = engine
        self._load_config()

    def shutdown(self):
        self._save_config()
        self.unpatch_all()

    @property
    def patches(self):
        if self._patches is None:
            from core.foundation.patcher import PatchTracker
            self._patches = PatchTracker()
        return self._patches

    def unpatch_all(self):
        if self._patches is not None:
            try:
                self._patches.restore_all()
            except Exception as e:
                Logger.warning(f"[{self.NAME}] Failed to restore patches: {e}")
            self._patches = None

    def patch_component(self, component_name: str, method_patches: Optional[dict[str, Callable]] = None,
                        extra_inspector_fields: Optional[list] = None,
                        filter_extensions: Optional[dict[str, str]] = None,
                        wraps: Optional[dict[str, dict]] = None):
        return self.patches.patch_component(
            component_name,
            method_patches=method_patches,
            extra_inspector_fields=extra_inspector_fields,
            filter_extensions=filter_extensions,
            wraps=wraps,
        )

    def add_inspector_field(self, component_name: str, field):
        return self.patches.add_inspector_field(component_name, field)

    def extend_file_filter(self, component_name: str, field_name: str, extra_filter: str):
        return self.patches.extend_file_filter(component_name, field_name, extra_filter)

    def patch_function(self, module, func_name: str, wrapper: Callable):
        self.patches.patch_function(module, func_name, wrapper)

    @property
    def bundled_library_dir(self) -> Optional[str]:
        return self._bundled_library_dir

    @property
    def resource_dir(self) -> Optional[str]:
        path = getattr(self, "_native_plugin_path", None)
        if path:
            base = os.path.splitext(path)[0]
            res = base + "_resources"
            if os.path.isdir(res):
                return res
        return None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, v: bool):
        self._enabled = v

    def step(self, dt: float):
        pass

    def pre_step(self, dt: float):
        pass

    def on_viewport_ready(self, viewport):
        pass

    def on_scene_loaded(self, scene):
        pass

    def on_scene_unloaded(self, scene):
        pass

    def on_project_opened(self):
        pass

    def on_play_start(self):
        pass

    def on_play_stop(self):
        pass

    def on_main_window_ready(self, main_window):
        pass

    @property
    def engine(self) -> Optional[Engine]:
        return self._engine

    def main_window(self):
        eng = self._engine
        if eng is None:
            return None
        get = getattr(eng, "get_main_window", None)
        if not callable(get):
            return None
        try:
            return get()
        except Exception:
            return None

    def get_config(self, key: str, default: Any = None, section: Optional[str] = None) -> Any:
        if section:
            sec = self._config.get(section)
            if isinstance(sec, dict):
                return sec.get(key, default)
            return default
        return self._config.get(key, default)

    def set_config(self, key: str, value: Any, section: Optional[str] = None):
        if section:
            sec = self._config.get(section)
            if not isinstance(sec, dict):
                sec = {}
                self._config[section] = sec
            sec[key] = value
        else:
            self._config[key] = value
        self._save_config()

    def save_config(self):
        self._save_config()

    def _config_dir(self) -> str:
        base = os.path.join(_project_root(), "config", "plugins")
        os.makedirs(base, exist_ok=True)
        return base

    def _load_config(self):
        name = self.NAME.replace("/", "_").replace("\\", "_")
        self._config_path = os.path.join(self._config_dir(), f"{name}.json")
        try:
            if os.path.isfile(self._config_path):
                with open(self._config_path, "r") as f:
                    self._config = json.load(f)
        except Exception as e:
            Logger.warning(f"[{self.NAME}] Failed to load config: {e}")
            self._config = {}

    def _save_config(self):
        if not self._config_path:
            return
        try:
            with open(self._config_path, "w") as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            Logger.warning(f"[{self.NAME}] Failed to save config: {e}")

    def _sync_ui(self, kind: str, entry: dict):
        mgr = getattr(self, "_manager", None)
        eng = self._engine
        if mgr is None or eng is None:
            return
        try:
            mgr.sync_plugin_ui(self, kind, entry)
        except Exception as e:
            Logger.error(f"[{self.NAME}] UI sync failed: {e}", e)

    def register_dock(self, title: str, widget_factory: Callable[[], Any],
                      area: str = "left", tab_group: Optional[str] = None,
                      icon: Optional[str] = None):
        entry = {
            "title": title,
            "widget_factory": widget_factory,
            "area": area,
            "tab_group": tab_group,
            "icon": icon,
        }
        self._docks.append(entry)
        self._sync_ui("docks", entry)
        return entry

    def add_toolbar_button(self, text: str, callback: Callable,
                           icon: Optional[str] = None, tooltip: str = ""):
        entry = {
            "text": text,
            "callback": callback,
            "icon": icon,
            "tooltip": tooltip or text,
        }
        self._toolbar_actions.append(entry)
        self._sync_ui("toolbar_actions", entry)
        return entry

    def add_toolbar_toggle(self, item_id: str, text: str, default: bool = False,
                           icon: Optional[str] = None, tooltip: str = "",
                           config_key: Optional[str] = None, on_toggled: Optional[Callable] = None):
        try:
            from editor.toolbar_registry import define_toolbar_item
            key = config_key or f"toolbar_plugins.{self.NAME}.{item_id}"
            define_toolbar_item(f"plugin.{self.NAME}.{item_id}", key, bool(default), kind="check")
        except Exception:
            key = config_key or f"toolbar_plugins.{self.NAME}.{item_id}"
        entry = {
            "item_id": f"plugin.{self.NAME}.{item_id}",
            "kind": "check",
            "text": text,
            "default": bool(default),
            "config_key": key,
            "icon": icon,
            "tooltip": tooltip or text,
            "callback": on_toggled,
        }
        self._toolbar_items.append(entry)
        self._sync_ui("toolbar_items", entry)
        return entry

    def add_toolbar_combo(self, item_id: str, options: list, default: Optional[str] = None,
                          tooltip: str = "", config_key: Optional[str] = None,
                          on_changed: Optional[Callable] = None):
        opts = list(options or [])
        first = opts[0] if opts else ""
        try:
            from editor.toolbar_registry import define_toolbar_item
            key = config_key or f"toolbar_plugins.{self.NAME}.{item_id}"
            define_toolbar_item(f"plugin.{self.NAME}.{item_id}", key, default if default is not None else first, kind="combo", options=opts)
        except Exception:
            key = config_key or f"toolbar_plugins.{self.NAME}.{item_id}"
        entry = {
            "item_id": f"plugin.{self.NAME}.{item_id}",
            "kind": "combo",
            "options": opts,
            "default": default if default is not None else first,
            "config_key": key,
            "tooltip": tooltip,
            "callback": on_changed,
        }
        self._toolbar_items.append(entry)
        self._sync_ui("toolbar_items", entry)
        return entry

    def add_toolbar_spin(self, item_id: str, default: float = 0.0,
                         minimum: float = 0.0, maximum: float = 100.0,
                         tooltip: str = "", config_key: Optional[str] = None,
                         on_changed: Optional[Callable] = None):
        try:
            from editor.toolbar_registry import define_toolbar_item
            key = config_key or f"toolbar_plugins.{self.NAME}.{item_id}"
            define_toolbar_item(f"plugin.{self.NAME}.{item_id}", key, float(default), kind="spin")
        except Exception:
            key = config_key or f"toolbar_plugins.{self.NAME}.{item_id}"
        entry = {
            "item_id": f"plugin.{self.NAME}.{item_id}",
            "kind": "spin",
            "default": float(default),
            "minimum": float(minimum),
            "maximum": float(maximum),
            "config_key": key,
            "tooltip": tooltip,
            "callback": on_changed,
        }
        self._toolbar_items.append(entry)
        self._sync_ui("toolbar_items", entry)
        return entry

    def add_menu_item(self, menu_name: str, text: str, callback: Callable,
                      shortcut: Optional[str] = None, icon: Optional[str] = None):
        entry = {
            "menu": menu_name,
            "text": text,
            "callback": callback,
            "shortcut": shortcut,
            "icon": icon,
        }
        self._menu_items.append(entry)
        self._sync_ui("menu_items", entry)
        return entry

    def register_file_opener(self, extensions, handler: Callable[[str], Any],
                             label: str = ""):
        if isinstance(extensions, str):
            extensions = [extensions]
        normed = []
        for ext in extensions:
            e = str(ext).strip().lower()
            if not e:
                continue
            if not e.startswith("."):
                e = "." + e
            if e not in normed:
                normed.append(e)
        if not normed or not callable(handler):
            Logger.warning(f"[{self.NAME}] register_file_opener needs extensions and a handler")
            return None
        entry = {
            "extensions": normed,
            "handler": handler,
            "label": label or self.NAME,
        }
        self._file_openers.append(entry)
        self._sync_ui("file_openers", entry)
        return entry

    def register_component(self, comp_cls: type):
        if not isinstance(comp_cls, type):
            Logger.warning(f"[{self.NAME}] register_component expects a class, got {type(comp_cls).__name__}")
            return
        from core.ecs import Component, ComponentRegistry
        if not issubclass(comp_cls, Component):
            Logger.warning(f"[{self.NAME}] register_component: {comp_cls.__name__} must inherit from Component")
            return
        ComponentRegistry.register(comp_cls)
        self._components.append(comp_cls)
