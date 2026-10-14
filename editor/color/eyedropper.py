# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit, QApplication
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from .palette import ColorDialog


class ColorLineEdit(QWidget):
    colorChanged = pyqtSignal(object)

    def __init__(self, color=None, parent=None):
        super().__init__(parent)
        self._color = self._parse_color(color) if color is not None else QColor.fromRgbF(1, 1, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._preview = QPushButton()
        self._preview.setFixedSize(28, 22)
        self._update_swatch()
        self._preview.clicked.connect(self._open_dialog)
        layout.addWidget(self._preview)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("rrggbb or rgb(r,g,b)")
        self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit, 1)

    @staticmethod
    def _parse_color(color):
        try:
            if isinstance(color, QColor):
                return color.toRgb()
            if isinstance(color, (list, tuple)):
                try:
                    vals = []
                    for v in (list(color) + [1.0, 1.0, 1.0, 1.0])[:4]:
                        try:
                            vals.append(max(0.0, min(1.0, float(v))))
                        except Exception:
                            vals.append(1.0)
                    return QColor.fromRgbF(vals[0], vals[1], vals[2], vals[3]).toRgb()
                except Exception:
                    return QColor.fromRgbF(1, 1, 1)
            if isinstance(color, str):
                try:
                    c = QColor(color.strip())
                    if c.isValid():
                        return c.toRgb()
                except Exception:
                    pass
        except Exception:
            pass
        return QColor.fromRgbF(1, 1, 1)

    def _update_swatch(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        self._preview.setStyleSheet(
            f"background: rgba({r},{g},{b},{a/255}); border-radius: 3px;"
        )

    def _open_dialog(self):
        from PyQt6.QtGui import QCursor
        dlg = ColorDialog(self._color, None)
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

        def _on_dialog_color(c):
            self._color = c.toRgb()
            self._update_swatch()
            self._edit.blockSignals(True)
            self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
            self._edit.blockSignals(False)
            self.colorChanged.emit(self._color)

        dlg.colorChanged.connect(_on_dialog_color)
        dlg.exec()
        try:
            dlg.colorChanged.disconnect(_on_dialog_color)
        except TypeError:
            pass
        self._color = dlg.get_color().toRgb()
        self._update_swatch()
        self._edit.blockSignals(True)
        self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._edit.blockSignals(False)
        self.colorChanged.emit(self._color)

    def _on_text_changed(self, text):
        c = QColor(text.strip())
        if c.isValid():
            self._color = c.toRgb()
            self._update_swatch()
            self.colorChanged.emit(self._color)

    def set_color(self, color):
        if isinstance(color, (list, tuple)):
            fmt = tuple(float(v) for v in color)
            if len(fmt) >= 3:
                r, g, b = fmt[0], fmt[1], fmt[2]
                a = fmt[3] if len(fmt) > 3 else 1.0
                self._color = QColor.fromRgbF(r, g, b, a)
            else:
                self._color = QColor.fromRgbF(1, 1, 1)
        elif isinstance(color, QColor):
            self._color = color.toRgb()
        else:
            c = QColor(str(color))
            self._color = c.toRgb() if c.isValid() else QColor.fromRgbF(1, 1, 1)
        self._update_swatch()
        self._edit.blockSignals(True)
        self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._edit.blockSignals(False)

    def get_color(self) -> QColor:
        return self._color

    def get_color_rgba(self) -> list[float]:
        return [self._color.redF(), self._color.greenF(), self._color.blueF(), self._color.alphaF()]
