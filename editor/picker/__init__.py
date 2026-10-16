# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import os
from typing import Optional
from PySide6.QtWidgets import QDialog
from editor.picker.dialog import ResourcePickerDialog
from editor.picker.format import _draw_file_icon, _draw_material_icon, _draw_prefab_icon, _draw_scene_icon, _format_size, _get_material_thumbnail
from editor.picker.thumbs import _get_thumb_service, _get_thumbnail, _peek_thumb, _thumb_resolution, _thumbnail_cache, _thumbnail_mutex

def pick_resource(parent, title: str, filter_str: str, current_path: str = "", project_root: str = "") -> Optional[str]:
    if not project_root:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng is not None:
            project_root = eng.project_root
        else:
            project_root = os.getcwd()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QCursor
    dlg = ResourcePickerDialog(title, filter_str, project_root, None)
    dlg.adjustSize()
    screen = QApplication.primaryScreen().availableGeometry()
    dw, dh = dlg.width(), dlg.height()
    cursor_pos = QCursor.pos()
    x = cursor_pos.x() - dw // 2
    y = cursor_pos.y() + 4
    if y + dh > screen.bottom():
        y = cursor_pos.y() - dh - 4
    if y < screen.top():
        y = screen.top()
    if x + dw > screen.right():
        x = screen.right() - dw
    if x < screen.left():
        x = screen.left()
    dlg.move(x, y)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.selected_path()
    return None

__all__ = ["ResourcePickerDialog", "pick_resource", "_draw_file_icon", "_draw_material_icon", "_draw_prefab_icon", "_draw_scene_icon", "_format_size", "_get_material_thumbnail", "_get_thumb_service", "_get_thumbnail", "_thumb_resolution", "_thumbnail_cache", "_thumbnail_mutex"]
