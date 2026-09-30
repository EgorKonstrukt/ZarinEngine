# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QMouseEvent


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event):
        self._editor.line_number_paint(event, self)

    def mouseMoveEvent(self, event: QMouseEvent):
        self._editor.line_number_mouse_move(event, self)

    def leaveEvent(self, event):
        self._editor.line_number_mouse_leave(event)

    def mousePressEvent(self, event: QMouseEvent):
        self._editor.line_number_mouse_press(event, self)


class VcsBlameGutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.blame_gutter_width(), 0)

    def paintEvent(self, event):
        self._editor.blame_gutter_paint(event, self)
