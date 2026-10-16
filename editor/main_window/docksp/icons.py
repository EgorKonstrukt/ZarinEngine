# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os

from PySide6.QtWidgets import QDockWidget

try:
    import editor.icons as qta
except ImportError:
    qta = None

DOCK_ICONS = {
    "ViewportDock": "fa5s.eye",
    "HierarchyDock": "fa5s.sitemap",
    "InspectorDock": "fa5s.search",
    "ConsoleDock": "fa5s.terminal",
    "ProfilerDock": "fa5s.chart-bar",
    "PluginManagerDock": "fa5s.puzzle-piece",
    "PackageManagerDock": "fa5s.box-open",
    "ProjectDock": "fa5s.folder-open",
    "PlayDock": "fa5s.play",
    "TerminalDock": "fa5s.window-maximize",
    "UndoHistoryDock": "fa5s.undo",
    "CollaborationDock": "fa5s.users",
    "MeshEditorDock": "fa5s.draw-polygon",
    "TerrainEditorDock": "fa5s.mountain",
    "AnimationDock": "fa5s.film",
    "AnimatorDock": "fa5s.running",
    "ShadersDock": "fa5s.code",
    "ScriptEditorDock": "fa5s.file-code",
    "TracemallocDebugDock": "fa5s.bug",
    "TimeTravelDock": "fa5s.clock",
    "VersionControlDock": "fa5s.code-branch",
    "GuiEditorDock": "fa5s.object-group",
    "PluginDock_PlotterPlugin_Plotter": "fa5s.chart-line",
    "PluginDock_TrackerMusicPlugin_Tracker_Editor": "fa5s.music",
}


def _apply_dock_icons(mw):
    if qta is None:
        return
    for dock in mw._docks:
        obj = dock.objectName()
        icon_name = DOCK_ICONS.get(obj)
        if icon_name:
            dock.setWindowIcon(qta.icon(icon_name, color="#d4d4d4"))


def _apply_plugin_dock_icon(dock: QDockWidget, info: dict):
    icon = info.get("icon") or DOCK_ICONS.get(dock.objectName())
    if not icon:
        prefix = "PluginDock_" + str(info.get("plugin", "")) + "_"
        for key, value in DOCK_ICONS.items():
            if key.startswith(prefix):
                icon = value
                break
    if not icon or qta is None:
        return
    try:
        if isinstance(icon, str) and not os.path.isfile(icon):
            dock.setWindowIcon(qta.icon(icon, color="#d4d4d4"))
        else:
            from PySide6.QtGui import QIcon
            dock.setWindowIcon(QIcon(str(icon)))
    except Exception as e:
        from core.foundation.logger import Logger
        Logger.error(f"Failed to apply icon to dock '{dock.objectName()}': {e}")
