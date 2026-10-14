# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def _refresh_all_icons(mw):
    project_panel = getattr(mw, "_project", None)
    if project_panel:
        project_panel._force_refresh_thumbnails()
