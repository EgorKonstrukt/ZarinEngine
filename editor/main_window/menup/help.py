# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def _show_bug_report(mw):
    from editor.bug_report import show_bug_report_dialog
    show_bug_report_dialog(mw)
