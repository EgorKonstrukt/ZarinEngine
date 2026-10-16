# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PySide6.QtCore import Qt


def add_all_docks(mw):
    area = Qt.DockWidgetArea.LeftDockWidgetArea
    mw.addDockWidget(area, mw._hierarchy)
    mw.addDockWidget(area, mw._viewport_dock)
    mw.addDockWidget(area, mw._inspector)
    mw.addDockWidget(area, mw._play_dock)
    mw.addDockWidget(area, mw._gui_editor)
    mw.addDockWidget(area, mw._console)
    mw.addDockWidget(area, mw._profiler)
    mw.addDockWidget(area, mw._project)
    mw.addDockWidget(area, mw._terminal)
    mw.addDockWidget(area, mw._undo_history)
    mw.addDockWidget(area, mw._plugin_mgr)
    mw.addDockWidget(area, mw._package_mgr)
    mw.addDockWidget(area, mw._collab_panel)
    mw.addDockWidget(area, mw._mesh_editor)
    mw.addDockWidget(area, mw._terrain_editor)
    mw.addDockWidget(area, mw._animation)
    mw.addDockWidget(area, mw._animator)
    mw.addDockWidget(area, mw._scripts)
    mw.addDockWidget(area, mw._script_editor)
    mw.addDockWidget(area, mw._tracemalloc)
    mw.addDockWidget(area, mw._time_travel)
    mw.addDockWidget(area, mw._vcs)
    for dock in mw._docks:
        if dock not in (                         mw._hierarchy, mw._viewport_dock, mw._inspector,
                        mw._play_dock, mw._gui_editor,
                        mw._console, mw._profiler, mw._project,
                        mw._terminal, mw._undo_history, mw._plugin_mgr,
                        mw._package_mgr,
                        mw._collab_panel, mw._mesh_editor, mw._terrain_editor, mw._animation,
                        mw._animator, mw._scripts, mw._script_editor, mw._tracemalloc,
                        mw._time_travel, mw._vcs):
            mw.addDockWidget(area, dock)


def build_dock_layout(mw):
    def _by_exact(name):
        for d in getattr(mw, "_docks", []):
            if d.objectName() == name:
                return d
        return None
    def _by_prefix(prefix):
        for d in getattr(mw, "_docks", []):
            if d.objectName().startswith(prefix):
                return d
        return None
    def _all_by_prefix(prefix):
        return [d for d in getattr(mw, "_docks", []) if d.objectName().startswith(prefix)]
    hierarchy = _by_exact("HierarchyDock")
    viewport = _by_exact("ViewportDock")
    inspector = _by_exact("InspectorDock")
    console = _by_exact("ConsoleDock")
    project = _by_exact("ProjectDock")
    terminal = _by_exact("TerminalDock")
    collab = _by_exact("CollaborationDock")
    vcs = _by_exact("VersionControlDock")
    undo = _by_exact("UndoHistoryDock")
    profiler = _by_exact("ProfilerDock")
    plugin_mgr = _by_exact("PluginManagerDock")
    package_mgr = _by_exact("PackageManagerDock")
    play = _by_exact("PlayDock")
    gui = _by_exact("GuiEditorDock")
    mesh = _by_exact("MeshEditorDock")
    terrain = _by_exact("TerrainEditorDock")
    animation = _by_exact("AnimationDock")
    animator = _by_exact("AnimatorDock")
    shaders = _by_exact("ShadersDock")
    script_editor = _by_exact("ScriptEditorDock")
    tracemalloc = _by_exact("TracemallocDebugDock")
    time_travel = _by_exact("TimeTravelDock")
    physics = _by_prefix("PluginDock_PhysicsVisualisation")
    if physics is None:
        physics = _by_prefix("PluginDock_Physics")
    if physics is None:
        for d in getattr(mw, "_docks", []):
            if "Physics Visualisation" in d.windowTitle():
                physics = d
                break
    plotter_docks = _all_by_prefix("PluginDock_PlotterPlugin_Plotter")
    if not plotter_docks:
        plotter_docks = _all_by_prefix("PluginDock_Plotter")
    tracker = _by_prefix("PluginDock_TrackerMusicPlugin_Tracker")
    if tracker is None:
        tracker = _by_prefix("PluginDock_Tracker")
    zarinmcp = _by_prefix("PluginDock_ZarinMCP")
    vr = _by_prefix("PluginDock_VR")
    if hierarchy is not None and viewport is not None:
        mw.splitDockWidget(hierarchy, viewport, Qt.Orientation.Horizontal)
    if viewport is not None and inspector is not None:
        mw.splitDockWidget(viewport, inspector, Qt.Orientation.Horizontal)
    left_bottom_anchor = physics or collab
    if hierarchy is not None and left_bottom_anchor is not None and left_bottom_anchor is not hierarchy:
        mw.splitDockWidget(hierarchy, left_bottom_anchor, Qt.Orientation.Vertical)
    if viewport is not None and project is not None:
        mw.splitDockWidget(viewport, project, Qt.Orientation.Vertical)
    if inspector is not None and console is not None:
        mw.splitDockWidget(inspector, console, Qt.Orientation.Vertical)
    if left_bottom_anchor is not None:
        left_order = [d for d in [physics, collab, vcs, undo] if d is not None]
        for i in range(1, len(left_order)):
            if left_order[i] is not left_order[0]:
                mw.tabifyDockWidget(left_order[0], left_order[i])
    if viewport is not None:
        top_order = [d for d in [viewport, terrain, script_editor, gui, tracemalloc, play, mesh, shaders, animator, time_travel] if d is not None]
        for i in range(1, len(top_order)):
            if top_order[i] is not top_order[0]:
                mw.tabifyDockWidget(top_order[0], top_order[i])
    if project is not None or tracker is not None:
        bottom_anchor = tracker or project
        bottom_order = [d for d in [tracker, project, animation, zarinmcp, plugin_mgr, package_mgr, profiler, vr] if d is not None]
        if bottom_anchor is not None and len(bottom_order) > 1:
            for i in range(len(bottom_order)):
                if bottom_order[i] is not bottom_anchor:
                    mw.tabifyDockWidget(bottom_anchor, bottom_order[i])
    if inspector is not None:
        for pd in plotter_docks:
            if pd is not inspector:
                mw.tabifyDockWidget(inspector, pd)
    if console is not None and terminal is not None and terminal is not console:
        mw.tabifyDockWidget(console, terminal)
    for d in getattr(mw, "_docks", []):
        try:
            d.setVisible(True)
        except Exception:
            pass
    if physics is not None:
        physics.raise_()
    if viewport is not None:
        viewport.raise_()
    if hierarchy is not None:
        hierarchy.raise_()
    if inspector is not None:
        inspector.raise_()
    if project is not None:
        project.raise_()
    if console is not None:
        console.raise_()
