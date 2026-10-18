# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import editor.icons as qta
from PySide6.QtWidgets import QMessageBox, QFileDialog
from PySide6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen


def open_global_settings(mw):
    from core.config.config import get_global_config
    from editor.settings import SettingsDialog
    cfg = get_global_config()
    dlg = SettingsDialog("Global Settings", cfg, mw)
    dlg.config_changed.connect(lambda key, value: on_global_config_changed(mw, key, value))
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dlg.show()


def _mirror_toolbar_key(cfg, key: str, value) -> None:
    try:
        from editor.toolbar_registry import get_toolbar_defs
        for entry in get_toolbar_defs():
            try:
                primary = entry.get("config_key", "")
                mirrors = list(entry.get("mirror_keys", []) or [])
                if key == primary:
                    for mirror in mirrors:
                        try:
                            cfg.set(mirror, value, notify=False)
                        except Exception:
                            pass
                    cfg.save()
                    return
                if key in mirrors:
                    try:
                        cfg.set(primary, value, notify=False)
                    except Exception:
                        pass
                    cfg.save()
                    return
            except Exception:
                pass
    except Exception:
        pass


def _is_toolbar_related(key: str) -> bool:
    try:
        from editor.toolbar_registry import get_toolbar_defs
        for entry in get_toolbar_defs():
            try:
                keys = [entry.get("config_key")] + list(entry.get("mirror_keys", []) or [])
                if key in keys:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def on_global_config_changed(mw, key: str, value):
    from core.config.config import get_global_config
    cfg = get_global_config()
    if key == "editor.ui_scale":
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
        base_size = cfg.get("editor.font_size", 12)
        f = QFont()
        f.setPointSizeF(base_size * value / 100.0)
        QApplication.setFont(f)
        return
    try:
        _mirror_toolbar_key(cfg, key, value)
    except Exception:
        pass
    try:
        mw._viewport.load_config(cfg)
    except Exception:
        pass
    try:
        mw._viewport.camera.load_config(cfg)
    except Exception:
        pass
    try:
        mw._viewport.gizmo.load_config(cfg)
    except Exception:
        pass
    if mw._viewport.renderer:
        try:
            mw._viewport.renderer.load_config(cfg)
        except Exception:
            pass
    mw._hierarchy.load_config(cfg)
    mw._inspector.load_config(cfg)
    mw._console.load_config(cfg)
    mw._profiler.load_config(cfg)
    mw._project.load_config(cfg)
    if hasattr(mw, '_terminal'):
        mw._terminal.load_config(cfg)
    try:
        if _is_toolbar_related(key):
            from editor.toolbar_registry import get_toolbar_registry
            reg = get_toolbar_registry(mw)
            reg.sync_key(key, mw)
    except Exception:
        pass


def open_project_settings(mw):
    from core.config.config import get_project_config
    from editor.settings import SettingsDialog
    path = getattr(mw._engine, "_project_path", ".")
    cfg = get_project_config(path)
    dlg = SettingsDialog("Project Settings", cfg, mw)
    dlg.config_changed.connect(lambda key, value: on_project_config_changed(mw, key, value))
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dlg.show()


def on_project_config_changed(mw, key: str, value):
    pass


def show_build_dialog(mw):
    from editor.build_dialog import show_build_dialog as _show_build_dialog
    _show_build_dialog(mw)


def show_about(mw):
    from editor.about import AboutDialog
    dlg = AboutDialog(mw)
    dlg.exec()
