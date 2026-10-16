# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PySide6.QtWidgets import QDockWidget

from .panels import register_default_docks
from .plugins import register_plugin_docks
from .layout import add_all_docks
from .layout import build_dock_layout


def setup_docks(mw):
    mw._docks: list[QDockWidget] = []
    register_default_docks(mw)
    register_plugin_docks(mw)
    add_all_docks(mw)
    state = mw._settings.value("windowState")
    if state is not None and mw.restoreState(state):
        mw._layout_restored = True
    else:
        mw._layout_restored = False
        build_dock_layout(mw)
