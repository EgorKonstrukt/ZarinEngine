# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from .base import _AREA_MAP
from .base import _make_dock
from .base import register_dock
from .icons import DOCK_ICONS
from .icons import _apply_dock_icons
from .icons import _apply_plugin_dock_icon
from .layout import add_all_docks
from .layout import build_dock_layout
from .panels import register_default_docks
from .plugins import _create_plugin_dock
from .plugins import _remove_plugin_docks
from .plugins import _unique_plugin_dock_name
from .plugins import register_plugin_docks
from .plugins import subscribe_plugin_dock_updates
from .setup import setup_docks
__all__ = ["DOCK_ICONS", "_AREA_MAP", "_apply_dock_icons", "_apply_plugin_dock_icon", "_create_plugin_dock", "_make_dock", "_remove_plugin_docks", "_unique_plugin_dock_name", "add_all_docks", "build_dock_layout", "register_default_docks", "register_dock", "register_plugin_docks", "setup_docks", "subscribe_plugin_dock_updates"]
