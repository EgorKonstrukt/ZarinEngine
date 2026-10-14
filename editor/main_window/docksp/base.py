# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtWidgets import QDockWidget
from PyQt6.QtCore import Qt

_AREA_MAP = {
    "left": Qt.DockWidgetArea.LeftDockWidgetArea,
    "right": Qt.DockWidgetArea.RightDockWidgetArea,
    "top": Qt.DockWidgetArea.TopDockWidgetArea,
    "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
}


def _make_dock(mw, title: str, widget, obj_name: str = "") -> QDockWidget:
    dock = QDockWidget(title, mw)
    if obj_name:
        dock.setObjectName(obj_name)
    dock.setWidget(widget)
    dock.setMinimumSize(40, 40)
    dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable)
    return dock


def register_dock(mw, dock: QDockWidget, area: Qt.DockWidgetArea) -> QDockWidget:
    dock.setMinimumSize(40, 40)
    mw._docks.append(dock)
    return dock
