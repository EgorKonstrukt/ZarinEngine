# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtWidgets import QStatusBar, QLabel
from PyQt6.QtCore import QTimer


def setup_statusbar(mw):
    mw._statusbar = QStatusBar(mw)
    mw.setStatusBar(mw._statusbar)
    mw._status_scene_lbl = QLabel("No scene")
    mw._statusbar.addPermanentWidget(mw._status_scene_lbl)
    mw._status_mode_lbl = QLabel("Edit Mode")
    mw._statusbar.addPermanentWidget(mw._status_mode_lbl)
    mw._status_fps_lbl = QLabel("FPS: 0 | TPS: 0")
    mw._statusbar.addPermanentWidget(mw._status_fps_lbl)
    mw._fps_timer = QTimer(mw)
    mw._fps_timer.timeout.connect(mw._update_status)
    mw._fps_timer.start(500)
