# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QSize, Qt


class StripeBar(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
        from core.config.editor_scale import scale
        self.setFixedWidth(scale(14))

    def sizeHint(self):
        from core.config.editor_scale import scale
        return QSize(scale(14), 0)

    def paintEvent(self, event):
        self._editor.minimap_paint(event, self)

    def mousePressEvent(self, event):
        self._editor.minimap_pressed(int(event.position().y()))
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._editor.minimap_dragged(int(event.position().y()))
            event.accept()
