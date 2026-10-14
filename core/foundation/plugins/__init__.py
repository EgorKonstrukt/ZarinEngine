# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.foundation.plugins.base import PluginBase, _zarin_user_dir, current_architecture
from core.foundation.plugins.manager import PluginManager
from core.foundation.plugins.openers import open_file_with_plugin

__all__ = ["PluginBase", "PluginManager", "open_file_with_plugin"]
