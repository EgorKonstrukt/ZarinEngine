# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os


def _show_build_settings(mw):
    from editor.build_settings_dialog import BuildSettingsDialog
    project_root = mw._engine._project_path or os.getcwd()
    dlg = BuildSettingsDialog(project_root, mw)
    dlg.exec()
