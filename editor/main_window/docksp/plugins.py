# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PySide6.QtWidgets import QDockWidget
from PySide6.QtCore import Qt

from .base import _AREA_MAP
from .base import _make_dock
from .base import register_dock
from .icons import _apply_plugin_dock_icon


def _unique_plugin_dock_name(mw, base: str) -> str:
    taken = {d.objectName() for d in getattr(mw, "_docks", [])}
    name = base
    n = 2
    while name in taken:
        name = f"{base}_{n}"
        n += 1
    return name


def _create_plugin_dock(mw, info: dict):
    try:
        widget = info["widget_factory"]()
        if widget is None:
            return None
        title = info["title"]
        area = _AREA_MAP.get(info.get("area", "left"), Qt.DockWidgetArea.LeftDockWidgetArea)
        plugin_name = info.get("plugin", "plugin")
        obj_name = _unique_plugin_dock_name(mw, f"PluginDock_{plugin_name}_{title.replace(' ', '_')}")
        dock = _make_dock(mw, title, widget, obj_name)
        _apply_plugin_dock_icon(dock, info)
        register_dock(mw, dock, area)
        mw.addDockWidget(area, dock)
        group = info.get("tab_group")
        if group:
            groups = getattr(mw, "_plugin_tab_groups", None)
            if groups is None:
                groups = {}
                mw._plugin_tab_groups = groups
            anchor_name = groups.get(group)
            anchor = next((d for d in mw._docks if d.objectName() == anchor_name), None)
            if anchor is not None and anchor is not dock:
                mw.tabifyDockWidget(anchor, dock)
            else:
                groups[group] = obj_name
        setter = getattr(widget, "set_active", None)
        if callable(setter):
            dock.visibilityChanged.connect(setter)
        return dock
    except Exception as e:
        from core.foundation.logger import Logger
        Logger.error(f"Failed to create plugin dock '{info.get('title', '?')}': {e}")
        return None


def _remove_plugin_docks(mw, plugin_name: str):
    prefix = f"PluginDock_{plugin_name}_"
    for dock in [d for d in list(getattr(mw, "_docks", [])) if d.objectName().startswith(prefix)]:
        try:
            mw.removeDockWidget(dock)
            mw._docks.remove(dock)
            dock.deleteLater()
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"Failed to remove plugin dock '{dock.objectName()}': {e}")


def subscribe_plugin_dock_updates(mw):
    reg = mw._engine.plugin_ui_registry
    listeners = reg.setdefault("runtime_listeners", [])
    for cb in listeners:
        if getattr(cb, "_zpl_scope", None) == "docks" and getattr(cb, "_zpl_mw", None) is mw:
            return
    def _on_runtime(payload):
        try:
            name = payload.get("unregistered")
            if name:
                _remove_plugin_docks(mw, name)
                return
            for info in payload.get("docks", []) or []:
                _create_plugin_dock(mw, info)
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"[Plugin] dock update failed: {e}", e)
    _on_runtime._zpl_scope = "docks"
    _on_runtime._zpl_mw = mw
    listeners.append(_on_runtime)


def register_plugin_docks(mw):
    registry = mw._engine.plugin_ui_registry
    for info in list(registry.get("docks", [])):
        _create_plugin_dock(mw, info)
    subscribe_plugin_dock_updates(mw)
