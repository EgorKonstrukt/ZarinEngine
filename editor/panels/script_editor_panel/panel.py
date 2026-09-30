# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QDockWidget
from PyQt6.QtCore import Qt

from .widget import ScriptEditorWidget

if TYPE_CHECKING:
    from core.engine.engine import Engine


class ScriptEditorPanel(QDockWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Script Editor", parent)
        self._engine = engine
        self.setObjectName("ScriptEditorDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.setMinimumWidth(200)
        self._script_widget = ScriptEditorWidget()
        self.setWidget(self._script_widget)
