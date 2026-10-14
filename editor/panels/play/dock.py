# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import TYPE_CHECKING
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame
from PyQt6.QtCore import Qt
from .viewport import PlayViewport
if TYPE_CHECKING:
    from core.engine.eng import Engine


class PlayDockPanel(QDockWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Game", parent)
        self._engine = engine
        self._paused = False
        self._setup_ui()
        self.setObjectName("PlayDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)

    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 2)
        step_btn = QPushButton("Step")
        step_btn.clicked.connect(self._step)
        toolbar.addWidget(step_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)
        self._viewport = PlayViewport(self._engine, self)
        layout.addWidget(self._viewport, 1)
        self.setWidget(w)

    def _toggle_pause(self):
        self._paused = not self._paused
        mw = self.parent()
        ts = mw._ts_sb.value() if hasattr(mw, "_ts_sb") else 1.0
        self._engine.time_scale = 0.0 if self._paused else ts

    def _step(self):
        if self._paused:
            self._engine.time_scale = self._engine.fixed_dt
            self._engine.tick()
            self._engine.time_scale = 0.0
