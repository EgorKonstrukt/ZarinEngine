# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import editor.icons as qta
from PySide6.QtGui import QAction, QKeySequence


def _plugin_menu(mw, mb, plugin_name: str):
    menus = getattr(mw, "_plugin_menus", None)
    if menus is None:
        menus = {}
        mw._plugin_menus = menus
    menu = menus.get(plugin_name)
    if menu is None:
        menu = mb.addMenu(plugin_name)
        menus[plugin_name] = menu
    return menu


def _find_named_menu(mb, name: str):
    want = name.replace("&", "")
    for act in mb.actions():
        m = act.menu()
        if m is not None and m.title().replace("&", "") == want:
            return m
    return None


def _plugin_action_icon(icon):
    if not icon:
        return None
    try:
        return qta.icon(icon, color=chr(35) + "d4d4d4")
    except Exception:
        try:
            from PySide6.QtGui import QIcon
            return QIcon(str(icon))
        except Exception:
            return None


def _append_plugin_menu_item(mw, mb, item: dict):
    plugin_name = item.get("plugin", "Plugins")
    target = None
    menu_name = (item.get("menu") or "").strip()
    if menu_name:
        target = _find_named_menu(mb, menu_name)
    if target is None:
        target = _plugin_menu(mw, mb, plugin_name)
    try:
        icon = _plugin_action_icon(item.get("icon"))
        act = QAction(icon, item["text"], mw) if icon is not None else QAction(item["text"], mw)
        shortcut = item.get("shortcut")
        if shortcut:
            try:
                act.setShortcut(QKeySequence(shortcut))
            except Exception:
                pass
        act.setProperty("plugin", plugin_name)
        act.triggered.connect(item["callback"])
        target.addAction(act)
    except Exception as e:
        from core.foundation.logger import Logger
        Logger.error(f"Failed to add menu item '{item.get('text', '?')}': {e}")


def _remove_plugin_menu_items(mw, plugin_name: str):
    mb = getattr(mw, "_plugin_menu_bar", None)
    if mb is None:
        return
    for act in mb.actions():
        m = act.menu()
        if m is None:
            continue
        for sub in list(m.actions()):
            try:
                if sub.property("plugin") == plugin_name:
                    m.removeAction(sub)
            except Exception as e:
                from core.foundation.logger import Logger
                Logger.warning(f"[Plugin] menu cleanup failed: {e}")


def subscribe_plugin_menu_updates(mw):
    reg = mw._engine.plugin_ui_registry
    listeners = reg.setdefault("runtime_listeners", [])
    for cb in listeners:
        if getattr(cb, "_zpl_scope", None) == "menu" and getattr(cb, "_zpl_mw", None) is mw:
            return
    def _on_runtime(payload):
        try:
            name = payload.get("unregistered")
            if name:
                _remove_plugin_menu_items(mw, name)
                return
            mb = getattr(mw, "_plugin_menu_bar", None)
            if mb is None:
                return
            for item in payload.get("menu_items", []) or []:
                _append_plugin_menu_item(mw, mb, item)
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"[Plugin] menu update failed: {e}", e)
    _on_runtime._zpl_scope = "menu"
    _on_runtime._zpl_mw = mw
    listeners.append(_on_runtime)


def add_plugin_menu_items(mw, mb):
    registry = mw._engine.plugin_ui_registry
    mw._plugin_menu_bar = mb
    items = registry.get("menu_items", [])
    if not items:
        return
    by_plugin: dict[str, list[dict]] = {}
    for item in items:
        by_plugin.setdefault(item.get("plugin", "Plugins"), []).append(item)
    for plugin_name in sorted(by_plugin.keys()):
        for item in by_plugin[plugin_name]:
            _append_plugin_menu_item(mw, mb, item)
