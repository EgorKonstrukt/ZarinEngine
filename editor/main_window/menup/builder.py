# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import qtawesome as qta
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence

from editor.main_window.handlersp import (
    new_scene, open_scene, save_scene, save_scene_as,
    toggle_play_stop, launch_external_player,
    undo, redo,
    open_global_settings, open_project_settings,
    show_build_dialog, show_about,
)
from editor.main_window.project import open_project_manager, open_project_browse
from editor.main_window.statep import reset_layout
from editor.main_window.palettep import show_command_palette
from .file import _show_build_settings
from .edit import _refresh_all_icons
from .view import _show_mesh_editor, _show_terrain_editor
from .vcs import _setup_vcs_menu
from .plugins import add_plugin_menu_items, subscribe_plugin_menu_updates
from .help import _show_bug_report


def setup_menu(mw):
    mb = mw.menuBar()
    _qta = lambda n, c=chr(35) + "d4d4d4": qta.icon(n, color=c)
    file_menu = mb.addMenu("File")
    new_act = QAction(_qta("fa5s.file"), "New Scene", mw)
    new_act.setShortcut(QKeySequence("Ctrl+N"))
    new_act.triggered.connect(lambda: new_scene(mw))
    file_menu.addAction(new_act)
    open_act = QAction(_qta("fa5s.folder-open"), "Open Scene...", mw)
    open_act.setShortcut(QKeySequence("Ctrl+O"))
    open_act.triggered.connect(lambda: open_scene(mw))
    file_menu.addAction(open_act)
    save_act = QAction(_qta("fa5s.save"), "Save Scene", mw)
    save_act.setShortcut(QKeySequence("Ctrl+S"))
    save_act.triggered.connect(lambda: save_scene(mw))
    file_menu.addAction(save_act)
    save_as_act = QAction(_qta("fa5s.save"), "Save Scene As...", mw)
    save_as_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_as_act.triggered.connect(lambda: save_scene_as(mw))
    file_menu.addAction(save_as_act)
    save_all_act = QAction(_qta("fa5s.save"), "Save All Scenes", mw)
    save_all_act.setShortcut(QKeySequence("Ctrl+Alt+S"))
    save_all_act.triggered.connect(lambda: mw._scene_tab_manager.save_all_dirty_tabs() if hasattr(mw, "_scene_tab_manager") and mw._scene_tab_manager else None)
    file_menu.addAction(save_all_act)
    file_menu.addSeparator()
    project_mgr_act = QAction(_qta("fa5s.folder"), "Project Manager...", mw)
    project_mgr_act.triggered.connect(lambda: open_project_manager(mw))
    file_menu.addAction(project_mgr_act)
    open_proj_act = QAction(_qta("fa5s.folder-open"), "Open Project...", mw)
    open_proj_act.triggered.connect(lambda: open_project_browse(mw))
    file_menu.addAction(open_proj_act)
    file_menu.addSeparator()
    exit_act = QAction(_qta("fa5s.sign-out-alt"), "Exit", mw)
    exit_act.setShortcut(QKeySequence("Alt+F4"))
    exit_act.triggered.connect(mw.close)
    file_menu.addAction(exit_act)
    edit_menu = mb.addMenu("Edit")
    mw._undo_act = QAction(_qta("fa5s.undo"), "Undo", mw)
    mw._undo_act.triggered.connect(lambda: undo(mw))
    mw._undo_act.setEnabled(False)
    edit_menu.addAction(mw._undo_act)
    mw._redo_act = QAction(_qta("fa5s.redo"), "Redo", mw)
    mw._redo_act.triggered.connect(lambda: redo(mw))
    mw._redo_act.setEnabled(False)
    edit_menu.addAction(mw._redo_act)
    edit_menu.addSeparator()
    gs_act = QAction(_qta("fa5s.cogs"), "Global Settings...", mw)
    gs_act.triggered.connect(lambda: open_global_settings(mw))
    edit_menu.addAction(gs_act)
    ps_act = QAction(_qta("fa5s.cog"), "Project Settings...", mw)
    ps_act.triggered.connect(lambda: open_project_settings(mw))
    edit_menu.addAction(ps_act)
    go_menu = mb.addMenu("GameObject")
    create_empty = QAction(_qta("fa5s.plus-square"), "Create Empty", mw)
    create_empty.setShortcut(QKeySequence("Ctrl+Shift+N"))
    create_empty.triggered.connect(mw._hierarchy._create_entity)
    go_menu.addAction(create_empty)
    add_dialog_act = QAction(_qta("fa5s.search"), "Add Entity...", mw)
    add_dialog_act.triggered.connect(lambda: mw._hierarchy._show_add_dialog(None))
    go_menu.addAction(add_dialog_act)
    go_menu.addSeparator()
    from editor.panels.add_entity_menu import populate_add_menu
    def _rebuild_gameobject_menu():
        go_menu.clear()
        go_menu.addAction(create_empty)
        go_menu.addAction(add_dialog_act)
        go_menu.addSeparator()
        populate_add_menu(
            go_menu,
            on_system=lambda mp: mw._hierarchy._create_system_prefab(mp, None),
            on_asset=lambda ap: mw._hierarchy._create_prefab_asset(ap, None),
            on_search=None,
        )
    go_menu.aboutToShow.connect(_rebuild_gameobject_menu)
    _rebuild_gameobject_menu()
    game_menu = mb.addMenu("Game")
    play_stop_act = QAction(_qta("fa5s.play"), "Play/Stop", mw)
    play_stop_act.setShortcut(QKeySequence("Shift+F10"))
    play_stop_act.triggered.connect(lambda: toggle_play_stop(mw))
    game_menu.addAction(play_stop_act)
    player_act = QAction(_qta("fa5s.gamepad"), "Launch in Player", mw)
    player_act.setShortcut(QKeySequence("F10"))
    player_act.triggered.connect(lambda: launch_external_player(mw))
    game_menu.addAction(player_act)
    view_menu = mb.addMenu("View")
    for dock in mw._docks:
        view_menu.addAction(dock.toggleViewAction())
    view_menu.addSeparator()
    goto_act = QAction(_qta("fa5s.search"), "Go to Tab...", mw)
    goto_act.setShortcut(QKeySequence("Ctrl+P"))
    goto_act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    goto_act.triggered.connect(lambda: mw._scene_tab_manager.show_quick_open() if hasattr(mw, "_scene_tab_manager") and mw._scene_tab_manager else None)
    view_menu.addAction(goto_act)
    palette_act = QAction(_qta("fa5s.terminal"), "Search Everywhere...", mw)
    palette_act.setShortcut(QKeySequence("Ctrl+F"))
    palette_act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    palette_act.triggered.connect(lambda: show_command_palette(mw))
    view_menu.addAction(palette_act)
    next_act = QAction(_qta("fa5s.arrow-right"), "Next Tab", mw)
    next_act.setShortcut(QKeySequence("Ctrl+Tab"))
    next_act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    next_act.triggered.connect(lambda: mw._scene_tab_manager.cycle_tab(1) if hasattr(mw, "_scene_tab_manager") and mw._scene_tab_manager else None)
    view_menu.addAction(next_act)
    prev_act = QAction(_qta("fa5s.arrow-left"), "Previous Tab", mw)
    prev_act.setShortcut(QKeySequence("Ctrl+Shift+Tab"))
    prev_act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    prev_act.triggered.connect(lambda: mw._scene_tab_manager.cycle_tab(-1) if hasattr(mw, "_scene_tab_manager") and mw._scene_tab_manager else None)
    view_menu.addAction(prev_act)
    view_menu.addSeparator()
    reset_layout_act = QAction(_qta("fa5s.redo-alt"), "Reset Layout", mw)
    reset_layout_act.triggered.connect(lambda: reset_layout(mw))
    view_menu.addAction(reset_layout_act)
    tools_menu = mb.addMenu("Tools")
    pm_act = QAction(_qta("fa5s.puzzle-piece"), "Plugin Manager", mw)
    pm_act.setShortcut(QKeySequence("Ctrl+Shift+P"))
    pm_act.triggered.connect(mw._plugin_mgr.show)
    tools_menu.addAction(pm_act)
    pkg_act = QAction(_qta("fa5s.box-open"), "Python Packages...", mw)
    pkg_act.setShortcut(QKeySequence("Ctrl+Shift+K"))
    pkg_act.triggered.connect(lambda: (mw._package_mgr.show(), mw._package_mgr.raise_()))
    tools_menu.addAction(pkg_act)
    tools_menu.addSeparator()
    mesh_editor_act = QAction(_qta("fa5s.draw-polygon"), "Mesh Editor", mw)
    mesh_editor_act.setShortcut(QKeySequence("Ctrl+Shift+M"))
    mesh_editor_act.triggered.connect(lambda: _show_mesh_editor(mw))
    tools_menu.addAction(mesh_editor_act)
    terrain_editor_act = QAction(_qta("fa5s.mountain"), "Terrain Editor", mw)
    terrain_editor_act.setShortcut(QKeySequence("Ctrl+Shift+T"))
    terrain_editor_act.triggered.connect(lambda: _show_terrain_editor(mw))
    tools_menu.addAction(terrain_editor_act)
    tools_menu.addSeparator()
    gui_act = QAction(_qta("fa5s.window-maximize"), "GUI Editor", mw)
    gui_act.setShortcut(QKeySequence("Ctrl+Shift+G"))
    gui_act.triggered.connect(lambda: mw._gui_editor.show() or mw._gui_editor.raise_())
    tools_menu.addAction(gui_act)
    tools_menu.addSeparator()
    bs_act = QAction(_qta("fa5s.tools"), "Build Settings...", mw)
    bs_act.setShortcut(QKeySequence("Ctrl+Shift+U"))
    bs_act.triggered.connect(lambda: _show_build_settings(mw))
    tools_menu.addAction(bs_act)
    build_act = QAction(_qta("fa5s.hammer"), "Build Project...", mw)
    build_act.setShortcut(QKeySequence("Ctrl+Shift+B"))
    build_act.triggered.connect(lambda: show_build_dialog(mw))
    tools_menu.addAction(build_act)
    tools_menu.addSeparator()
    refresh_icons_act = QAction(_qta("fa5s.sync-alt"), "Refresh All Icons", mw)
    refresh_icons_act.triggered.connect(lambda: _refresh_all_icons(mw))
    tools_menu.addAction(refresh_icons_act)
    vcs_menu = mb.addMenu("VCS")
    _setup_vcs_menu(mw, vcs_menu)
    add_plugin_menu_items(mw, mb)
    help_menu = mb.addMenu("Help")
    bug_act = QAction(_qta("fa5s.bug"), "Report Bug...", mw)
    bug_act.triggered.connect(lambda: _show_bug_report(mw))
    help_menu.addAction(bug_act)
    help_menu.addSeparator()
    about_act = QAction(_qta("fa5s.info-circle"), "About Zarin Engine", mw)
    about_act.triggered.connect(lambda: show_about(mw))
    help_menu.addAction(about_act)
    subscribe_plugin_menu_updates(mw)
