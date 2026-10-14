# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os

from PyQt6.QtWidgets import QDockWidget
from PyQt6.QtCore import Qt

from editor.scene_viewport import SceneViewport
from editor.panels.hierarchy import HierarchyPanel
from editor.inspector import InspectorPanel
from editor.panels.console import ConsolePanel
from editor.panels.profiler import ProfilerPanel
from editor.panels.plugin_manager_panel import PluginManagerPanel
from editor.panels.pkgmgr import PackageManagerPanel
from editor.panels.project import ProjectPanel
from editor.panels.play import PlayDockPanel
from editor.panels.terminal import TerminalPanel
from editor.panels.undo_history_panel import UndoHistoryPanel
from editor.panels.collab import CollaborationPanel
from editor.panels.meshedit import MeshEditorPanel
from editor.panels.terrain import TerrainPanel
from editor.panels.anim import AnimationPanel
from editor.panels.animator import AnimatorPanel
from editor.panels.scripts_panel import ScriptsPanel
from editor.panels.script_editor_panel import ScriptEditorPanel
from editor.panels.tracemalloc import TracemallocPanel
from editor.panels.timetravel import TimeTravelPanel
from editor.panels.vcsp import VcsPanel
from editor.gui_editor.gui_viewport import GuiEditorViewport

from .base import register_dock
from .icons import _apply_dock_icons


def register_default_docks(mw):
    from core.config.config import get_global_config
    mw._viewport = SceneViewport(mw._engine, mw)
    mw._engine.viewport = mw._viewport
    mw._viewport.load_config(get_global_config())
    mw._viewport.camera.load_config(get_global_config())
    mw._viewport.gizmo.load_config(get_global_config())
    mw._viewport_dock = QDockWidget("Viewport", mw)
    mw._viewport_dock.setObjectName("ViewportDock")
    mw._viewport_dock.setWidget(mw._viewport)
    mw._viewport_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    mw._viewport_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._viewport_dock.setContentsMargins(0, 0, 0, 0)
    mw._viewport_dock.setStyleSheet(
        "QDockWidget { border: none; } QDockWidget::title { padding: 2px 6px; font-size: 11px; }")
    mw._viewport_dock.setMinimumSize(40, 40)
    mw._viewport_dock.topLevelChanged.connect(mw._viewport.on_dock_top_level_changed)
    register_dock(mw, mw._viewport_dock, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._hierarchy = HierarchyPanel(mw._engine, mw)
    mw._hierarchy.load_config(get_global_config())
    mw._hierarchy.setObjectName("HierarchyDock")
    mw._hierarchy.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._hierarchy.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._hierarchy, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._inspector = InspectorPanel(mw._engine, mw)
    mw._inspector.load_config(get_global_config())
    mw._inspector.setObjectName("InspectorDock")
    mw._inspector.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._inspector.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._inspector, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._console = ConsolePanel(mw)
    mw._console.load_config(get_global_config())
    mw._console.setObjectName("ConsoleDock")
    mw._console.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._console.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._console, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._profiler = ProfilerPanel(mw._engine, mw)
    mw._profiler.load_config(get_global_config())
    mw._profiler.setObjectName("ProfilerDock")
    mw._profiler.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._profiler.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._profiler, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._plugin_mgr = PluginManagerPanel(mw._engine, mw)
    mw._plugin_mgr.setObjectName("PluginManagerDock")
    mw._plugin_mgr.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._plugin_mgr.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._plugin_mgr, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._package_mgr = PackageManagerPanel(mw)
    mw._package_mgr.setObjectName("PackageManagerDock")
    mw._package_mgr.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._package_mgr.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._package_mgr, Qt.DockWidgetArea.LeftDockWidgetArea)
    _assets_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets"))
    mw._project = ProjectPanel(mw._engine, _assets_root, mw)
    mw._project.load_config(get_global_config())
    mw._project.setObjectName("ProjectDock")
    mw._project.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._project.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._project, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._play_dock = PlayDockPanel(mw._engine, mw)
    register_dock(mw, mw._play_dock, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._terminal = TerminalPanel(mw)
    mw._terminal.setObjectName("TerminalDock")
    mw._terminal.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    register_dock(mw, mw._terminal, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._gui_editor_widget = GuiEditorViewport(mw._engine, mw)
    mw._gui_editor = QDockWidget("GUI Editor", mw)
    mw._gui_editor.setObjectName("GuiEditorDock")
    mw._gui_editor.setWidget(mw._gui_editor_widget)
    mw._gui_editor.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._gui_editor.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._gui_editor, Qt.DockWidgetArea.LeftDockWidgetArea)
    from editor.main_window.handlersp import on_entity_selected
    mw._gui_editor_widget.entity_selected.connect(lambda e: on_entity_selected(mw, e))
    mw._undo_history = UndoHistoryPanel(mw)
    mw._undo_history.setObjectName("UndoHistoryDock")
    mw._undo_history.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._undo_history.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._undo_history, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._collab_panel = CollaborationPanel(mw._engine, mw)
    mw._collab_panel.setObjectName("CollaborationDock")
    mw._collab_panel.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    if mw._engine.collab_manager:
        mw._collab_panel.set_collaboration_manager(mw._engine.collab_manager)
    from editor.viewport.collaboration import setup_collab_undo_redo_hooks
    setup_collab_undo_redo_hooks(mw._engine)
    register_dock(mw, mw._collab_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._mesh_editor = MeshEditorPanel(mw._engine, mw)
    mw._mesh_editor.setObjectName("MeshEditorDock")
    register_dock(mw, mw._mesh_editor, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._terrain_editor = TerrainPanel(mw._engine, mw)
    mw._terrain_editor.setObjectName("TerrainEditorDock")
    if mw._engine.collab_manager:
        mw._terrain_editor.set_collaboration_manager(mw._engine.collab_manager)
    register_dock(mw, mw._terrain_editor, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._animation = AnimationPanel(mw._engine, mw)
    mw._animation.load_config(get_global_config())
    mw._animation.setObjectName("AnimationDock")
    mw._animation.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._animation.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._animation, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._animator = AnimatorPanel(mw._engine, mw)
    mw._animator.load_config(get_global_config())
    mw._animator.setObjectName("AnimatorDock")
    mw._animator.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._animator.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._animator, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._animator.state_selected_signal.connect(mw._inspector.show_animator_state)
    mw._animator.transition_selected_signal.connect(mw._inspector.show_animator_transition)
    mw._animator.selection_cleared.connect(mw._inspector.clear_animator_mode)
    mw._scripts = ScriptsPanel(mw._engine, mw)
    mw._scripts.setObjectName("ShadersDock")
    mw._scripts.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._scripts.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._scripts, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._script_editor = ScriptEditorPanel(mw._engine, mw)
    mw._script_editor.setObjectName("ScriptEditorDock")
    mw._script_editor.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._script_editor.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._script_editor, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._tracemalloc = TracemallocPanel(mw)
    mw._tracemalloc.setObjectName("TracemallocDebugDock")
    mw._tracemalloc.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._tracemalloc.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._tracemalloc, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._time_travel = TimeTravelPanel(mw._engine, mw)
    mw._time_travel.setObjectName("TimeTravelDock")
    mw._time_travel.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._time_travel.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._time_travel, Qt.DockWidgetArea.LeftDockWidgetArea)
    mw._vcs = VcsPanel(mw)
    mw._vcs.setObjectName("VersionControlDock")
    mw._vcs.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    mw._vcs.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    register_dock(mw, mw._vcs, Qt.DockWidgetArea.LeftDockWidgetArea)
    _apply_dock_icons(mw)
