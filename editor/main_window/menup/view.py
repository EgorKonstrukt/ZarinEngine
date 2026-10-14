# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def _show_mesh_editor(mw):
    mw._mesh_editor.show()
    mw._mesh_editor.raise_()
    sel = getattr(mw._viewport, "_selected_entities", None)
    if sel and len(sel) > 0:
        mw._mesh_editor.set_entity(sel[0])


def _show_terrain_editor(mw):
    mw._terrain_editor.show()
    mw._terrain_editor.raise_()
    sel = getattr(mw._viewport, "_selected_entities", None)
    if sel and len(sel) > 0:
        mw._terrain_editor.set_entity(sel[0])
