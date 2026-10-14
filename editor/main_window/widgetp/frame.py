# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QMainWindow, QDockWidget, QWidget
from PyQt6.QtCore import Qt, QSettings, QTimer, QThread
from PyQt6.QtGui import QCloseEvent

from core.engine.eng import Engine

from editor.main_window.docksp import setup_docks
from editor.main_window.menup import setup_menu
from editor.main_window.toolbar import setup_toolbar
from editor.main_window.statusbar import setup_statusbar
from editor.main_window.connections import connect_signals
from editor.main_window.statep import restore_camera, save_state
from editor.main_window.postinit import post_init
from editor.main_window.handlersp import on_scene_loaded
from editor.main_window.tabs import SceneTabManager

from .status import _HwMonitorWorker, _StatusMixin
from .toolbar_host import _ToolbarHostMixin


class EditorMainWindow(_ToolbarHostMixin, _StatusMixin, QMainWindow):
    def __init__(self, engine: Engine):
        super().__init__()
        self._engine = engine
        from editor.scene_async import call_on_main
        engine._gui_poster = call_on_main
        self._settings = QSettings("Zarin", "Editor")
        self._play_dock: Optional[QDockWidget] = None
        self._prefab_mode: bool = False
        self._saved_scene = None
        self._prefab_path: Optional[str] = None
        self._global_settings_dlg = None
        self._project_settings_dlg = None
        self.setWindowTitle("Zarin Engine Editor")
        self.setMinimumSize(1280, 720)
        self.setContentsMargins(0, 0, 0, 0)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks |
            QMainWindow.DockOption.AnimatedDocks |
            QMainWindow.DockOption.AllowTabbedDocks)
        self._dummy_central = QWidget()
        self._dummy_central.setMinimumSize(0, 0)
        self._dummy_central.setMaximumSize(0, 0)
        self.setCentralWidget(self._dummy_central)
        self._restored_geometry_once = False
        setup_docks(self)
        setup_menu(self)
        setup_toolbar(self)
        self._scene_tab_manager = SceneTabManager(self._engine, self._scene_tab_bar, self)
        self._init_collab_scene_tabs()
        self._init_script_tabs()
        setup_statusbar(self)
        self._hw_worker = _HwMonitorWorker()
        self._hw_thread = QThread(self)
        self._hw_worker.moveToThread(self._hw_thread)
        self._hw_thread.started.connect(self._hw_worker.start)
        self._hw_worker.hw_updated.connect(self._on_hw_updated)
        self._hw_thread.start()
        connect_signals(self)
        restore_camera(self)
        if not self._layout_restored:
            save_state(self, include_tabs=False)
        self._session_save_pending = False
        self._session_timer = QTimer(self)
        self._session_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._session_timer.timeout.connect(self._flush_session_autosave)
        self._session_timer.start(60000)
        engine.on("scene_loaded", lambda s: on_scene_loaded(self, s))
        self._setup_engine_events()
        QTimer.singleShot(0, lambda: post_init(self))
        engine.set_main_window(self)

    def _schedule_session_autosave(self, delay_ms: int = 5000):
        try:
            if self._session_save_pending:
                return
            self._session_save_pending = True
            QTimer.singleShot(delay_ms, self._flush_session_autosave)
        except Exception:
            pass

    def _flush_session_autosave(self):
        self._session_save_pending = False
        try:
            mgr = getattr(self, "_scene_tab_manager", None)
            if mgr is not None and getattr(mgr, "_restoring", False):
                return
            if getattr(self._engine, "play_mode", False):
                return
            save_state(self)
        except Exception:
            pass

    def _setup_engine_events(self):
        from editor.main_window.handlersp import on_play_start, on_play_stop
        self._engine.on("play_start", lambda _: on_play_start(self, _))
        self._engine.on("play_stop", lambda _: on_play_stop(self, _))

    def closeEvent(self, event: QCloseEvent):
        if self._engine.play_mode:
            self._engine.stop_play()
        from core.config.config import get_global_config
        cfg = get_global_config()
        if hasattr(self, "_terminal") and hasattr(self._terminal, "save_config"):
            self._terminal.save_config(cfg)
        if hasattr(self, "_project"):
            self._project.save_config(cfg)
        cfg.save()
        try:
            mgr = getattr(self, "_scene_tab_manager", None)
            dirty = mgr.dirty_scene_tabs() if mgr is not None else []
        except Exception:
            dirty = []
        if dirty:
            from PyQt6.QtWidgets import QMessageBox
            shown = list(dirty[:10])
            names = "\n".join(f"• {n}" for n in shown)
            if len(dirty) > 10:
                names += f"\n… and {len(dirty) - 10} more"
            box = QMessageBox(self)
            box.setWindowTitle("Unsaved Changes")
            box.setText(f"{len(dirty)} scenes have unsaved changes:\n{names}\n\nSave them before closing?")
            box.addButton("Save All", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Close without Saving", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is None:
                event.ignore()
                return
            role = box.buttonRole(clicked)
            if role == QMessageBox.ButtonRole.RejectRole:
                event.ignore()
                return
            if role == QMessageBox.ButtonRole.AcceptRole and mgr is not None:
                mgr.save_all_dirty_tabs()
        save_state(self)
        try:
            vp = getattr(self, "_viewport", None)
            bw = getattr(vp, "_block_watch", None)
            if bw is not None:
                bw.stop()
        except Exception:
            pass
        self._engine.shutdown()
        event.accept()
