# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import sys
import json
import time as _time_module
from typing import Any
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget
import editor.icons as qta
from core.engine.eng import Engine
from core.foundation.logger import Logger
from .repl import TerminalTab
from .powershell import PowershellTab


class TerminalPanel(QDockWidget):
    _SCENE_REFRESH_MS = 500

    def __init__(self, parent=None):
        super().__init__("Terminal", parent)
        self._tab_count: int = 0
        self._font_family: str = "Segoe UI"
        self._font_size: int = 10
        self._namespace: dict[str, Any] = {}
        self._pws_tabs: list[PowershellTab] = []
        self._setup_ui()
        self._init_namespace()
        eng = Engine.instance()
        if eng:
            eng.on("scene_loaded", self._on_scene_loaded)

    def _init_namespace(self):
        ns = self._namespace
        ns.clear()
        eng = Engine.instance()
        if eng:
            ns["engine"] = eng
            ns["scene"] = eng.scene
        ns["Logger"] = Logger
        ns["os"] = os
        ns["sys"] = sys
        ns["json"] = json
        ns["math"] = _time_module
        from core.maths.math3d import Vec2, Vec3, Vec4, Quat, Mat4
        ns["Vec2"] = Vec2
        ns["Vec3"] = Vec3
        ns["Vec4"] = Vec4
        ns["Quat"] = Quat
        ns["Mat4"] = Mat4
        try:
            import numpy as np
            ns["np"] = np
        except ImportError:
            pass
        try:
            from core.ecs import Entity, Component
            ns["Entity"] = Entity
            ns["Component"] = Component
        except ImportError:
            pass

    def _on_scene_loaded(self, scene):
        self._namespace["scene"] = scene

    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        add_btn = QPushButton(qta.icon("fa5s.plus", color=chr(35) + "9ccc65"), "")
        add_btn.setToolTip("New Python Tab")
        add_btn.clicked.connect(self._add_tab)
        toolbar.addWidget(add_btn)
        ps_btn = QPushButton(qta.icon("fa5s.terminal", color=chr(35) + "d4d4d4"), "")
        ps_btn.setToolTip("New PowerShell Tab (embedded)")
        ps_btn.clicked.connect(self._open_powershell)
        toolbar.addWidget(ps_btn)
        toolbar.addStretch()
        clear_btn = QPushButton(qta.icon("fa5s.eraser", color=chr(35) + "d4d4d4"), "")
        clear_btn.setToolTip("Clear Current Tab")
        clear_btn.clicked.connect(self._clear_current)
        toolbar.addWidget(clear_btn)
        reset_btn = QPushButton(qta.icon("fa5s.sync-alt", color=chr(35) + "d4d4d4"), "")
        reset_btn.setToolTip("Reset Python Namespace")
        reset_btn.clicked.connect(self._reset_namespace)
        toolbar.addWidget(reset_btn)
        layout.addLayout(toolbar)
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        layout.addWidget(self._tabs)
        self.setWidget(w)
        self._add_tab()

    def _get_assets_path(self) -> str:
        assets_path = os.path.abspath("assets")
        if not os.path.isdir(assets_path):
            assets_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "assets"))
        if not os.path.isdir(assets_path):
            assets_path = os.getcwd()
        return assets_path

    def _add_tab(self):
        self._tab_count += 1
        tab = TerminalTab(self._namespace, self._font_family, self._font_size, self)
        idx = self._tabs.addTab(tab, f"Python {self._tab_count}")
        self._tabs.setCurrentIndex(idx)

    def _open_powershell(self):
        self._tab_count += 1
        tab = PowershellTab(self._get_assets_path(), self._font_family, self._font_size, self)
        self._pws_tabs.append(tab)
        idx = self._tabs.addTab(tab, f"PS {self._tab_count}")
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int):
        if self._tabs.count() <= 1:
            return
        w = self._tabs.widget(index)
        if isinstance(w, PowershellTab):
            w.terminate()
            if w in self._pws_tabs:
                self._pws_tabs.remove(w)
        self._tabs.removeTab(index)
        w.deleteLater()

    def _clear_current(self):
        tab = self._tabs.currentWidget()
        if tab and hasattr(tab, "_output"):
            tab._output.clear()

    def _reset_namespace(self):
        self._init_namespace()

    def load_config(self, config) -> None:
        self._font_family = config.get("terminal.font_family", self._font_family)
        self._font_size = config.get("terminal.font_size", self._font_size)

    def save_config(self, config) -> None:
        config.set("terminal.font_family", self._font_family)
        config.set("terminal.font_size", self._font_size)

    def execute_python(self, code: str):
        tab = self._tabs.currentWidget()
        if isinstance(tab, TerminalTab):
            tab._input.setPlainText(code)
            tab._execute(code)
