# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import importlib.util
import os
import sys
from typing import Optional, TYPE_CHECKING
from core.foundation.logger import Logger
from core.foundation.plugins.base import PluginBase
from core.foundation.plugins.discovery import DiscoveryMixin
from core.foundation.plugins.lifecycle import _split_plugin_require
from core.foundation.plugins.loader import LoaderMixin
from core.foundation.plugins.lifecycle import LifecycleMixin
from core.foundation.plugins.ui_registry import UiRegistryMixin
if TYPE_CHECKING:
    from core.engine.eng import Engine


class PluginManager(DiscoveryMixin, LoaderMixin, LifecycleMixin, UiRegistryMixin):
    def __init__(self):
        self._plugins: dict[str, PluginBase] = {}
        self._load_order: list[str] = []
        self._engine: Optional[Engine] = None
        self._status: dict[str, dict] = {}
        self._pending: list[dict] = []
        self._libraries: dict[str, dict] = {}
        self._library_packs: dict[str, dict] = {}
        self._lib_owners: list[tuple] = []

    def plugin_status(self, name: str) -> dict:
        return dict(self._status.get(name, {"state": "unknown", "reason": ""}))

    def all_plugin_statuses(self) -> dict:
        return {n: dict(v) for n, v in self._status.items()}

    def _set_status(self, name: str, state: str, reason: str = ""):
        self._status[str(name)] = {"state": state, "reason": str(reason or "")}

    def set_engine(self, engine: Engine):
        self._engine = engine

    def _origin_is_user(self, origin) -> bool:
        parts = str(origin or "").replace("\\", "/").replace(".", "/").split("/")
        return "user" in parts

    def register(self, plugin: PluginBase):
        name = plugin.NAME
        if name in self._plugins:
            old = self._plugins[name]
            new_path = str(getattr(plugin, "_native_plugin_path", "") or "")
            old_path = str(getattr(old, "_native_plugin_path", "") or "")
            if new_path and new_path != old_path and self._origin_is_user(new_path) and not self._origin_is_user(old_path):
                Logger.warning(f"Plugin '{name}' from user dir overrides '{old_path}'.")
                self.unregister(name)
            else:
                Logger.warning(f"Plugin '{name}' already registered from '{old_path}', skipping '{new_path}'.")
                return
        plugin._manager = self
        try:
            plugin.initialize(self._engine)
            self._plugins[name] = plugin
            self._load_order.append(name)
            Logger.info(f"Plugin '{name}' v{plugin.VERSION} loaded.")
            self._set_status(name, "loaded")
            self._notify_ui_registrations(plugin)
        except Exception as e:
            Logger.error(f"Failed to init plugin '{name}': {e}", e)
            self._set_status(name, "failed", str(e))

    def unregister(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        try:
            plugin.shutdown()
        except Exception as e:
            Logger.error(f"Error shutting down plugin '{name}': {e}", e)
        self._plugins.pop(name, None)
        if name in self._load_order:
            self._load_order.remove(name)
        for entries in (plugin._docks, plugin._toolbar_actions,
                        plugin._menu_items, plugin._file_openers):
            for entry in entries:
                if isinstance(entry, dict):
                    entry.pop("_synced", None)
        eng = self._engine
        reg = getattr(eng, "plugin_ui_registry", None) if eng is not None else None
        if reg is not None:
            for kind in ("docks", "toolbar_actions", "menu_items", "file_openers"):
                try:
                    reg[kind] = [e for e in reg.get(kind, []) if e.get("plugin") != name]
                except Exception as e:
                    Logger.warning(f"[Plugin] registry cleanup failed for '{kind}': {e}")
            self._fire_runtime({"unregistered": name}, reg)
        plugin._manager = None
        return True

    def reload_plugin_package(self, dirpath: str) -> bool:
        norm = os.path.normpath(dirpath)
        doomed = [n for n, p in self._plugins.items()
                  if os.path.normpath(str(getattr(p, "_native_plugin_path", "") or "")) == norm]
        for n in doomed:
            self.unregister(n)
        base = os.path.basename(norm)
        prefixes = ("plugins." + base, "_plugin_" + base)
        for modname in [m for m in list(sys.modules)
                        if m in prefixes or m.startswith(prefixes[0] + ".") or m.startswith(prefixes[1] + ".")]:
            try:
                del sys.modules[modname]
            except Exception:
                pass
        try:
            self.load_package(dirpath)
            return True
        except Exception as e:
            Logger.error(f"Failed to reload plugin package '{dirpath}': {e}", e)
            return False

    def _register_instances(self, mod, path: str, bundled_libs: Optional[str] = None,
                            manifest: Optional[dict] = None, payload_dir: Optional[str] = None) -> bool:
        registered = False
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and issubclass(obj, PluginBase) and obj is not PluginBase:
                inst = obj()
                inst._native_plugin_path = path
                inst._bundled_library_dir = bundled_libs
                if manifest:
                    inst._manifest = manifest
                if payload_dir:
                    inst._payload_dir = payload_dir
                self.register(inst)
                registered = True
        return registered

    def _load_python_plugin(self, mod_name: str, path: str, bundled_libs: Optional[str] = None,
                            manifest: Optional[dict] = None, native_compiled: bool = False):
        spec = importlib.util.spec_from_file_location(mod_name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._register_instances(mod, path, bundled_libs, manifest)
        comp_dir = os.path.splitext(path)[0] + "_components"
        self._auto_load_components(comp_dir, None)

    def _topo_plan(self, entries):
        by_name = {}
        for kind, path, manifest in entries:
            name = str(manifest.get("name", "") or path)
            by_name.setdefault(name, []).append((kind, path, manifest))
        names = sorted(by_name)
        deps = {}
        for name in names:
            want = set()
            for kind, path, manifest in by_name[name]:
                for req in manifest.get("requires", []) or []:
                    rn, _rs = _split_plugin_require(req)
                    if rn and rn in by_name and rn != name:
                        want.add(rn)
            deps[name] = want
        ordered, done = [], set()
        while len(done) < len(names):
            progressed = False
            for name in names:
                if name in done:
                    continue
                if deps[name] <= done:
                    ordered.append(name)
                    done.add(name)
                    progressed = True
            if not progressed:
                for name in names:
                    if name not in done:
                        ordered.append(name)
                        done.add(name)
                break
        out = []
        for name in ordered:
            out.extend(by_name[name])
        return out

    def _load_planned_entry(self, kind: str, path: str, manifest: dict):
        if manifest and not self._gate_or_defer(kind, path, manifest):
            return
        if kind == "zplugin":
            self.load_zplugin(path)
        else:
            self.load_package(path)

    def library_conflicts(self) -> list:
        by_mod = {}
        for mod, owner, path in self._lib_owners:
            by_mod.setdefault(mod, []).append({"owner": owner, "path": path})
        out = []
        for mod in sorted(by_mod):
            owners = by_mod[mod]
            if len({o["path"] for o in owners}) > 1:
                out.append({"module": mod, "owners": owners})
        return out

    def doctor(self) -> dict:
        by_state = {}
        for n, s in self._status.items():
            by_state.setdefault(s.get("state", "unknown"), {})[n] = s.get("reason", "")
        return {
            "conflicts": self.library_conflicts(),
            "unresolved": by_state.get("unresolved", {}),
            "blocked": by_state.get("blocked", {}),
            "failed": by_state.get("failed", {}),
            "libraries": {k: dict(v) for k, v in self._library_packs.items()},
        }

    def get(self, name: str) -> Optional[PluginBase]:
        return self._plugins.get(name)

    def get_all(self) -> list[PluginBase]:
        return [self._plugins[n] for n in self._load_order if n in self._plugins]

    def get_system_plugins(self) -> list[PluginBase]:
        return [p for p in self.get_all() if p.SYSTEM]
