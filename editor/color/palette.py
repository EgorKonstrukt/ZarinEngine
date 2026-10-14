# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PyQt6.QtWidgets import QDialog, QLineEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDialogButtonBox, QApplication
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QPen
from .wheel import _ColorWheelWidget


class _AlphaWidget(QWidget):
    alphaChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 20)
        self._alpha = 1.0
        self._color = QColor.fromRgbF(1, 1, 1)
        self._dragging = False

    def set_alpha(self, a):
        self._alpha = max(0, min(1, a))
        self.update()

    def set_color(self, c: QColor):
        self._color = c
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        for x in range(0, w, 8):
            for y in range(0, h, 8):
                even = (x // 8 + y // 8) % 2 == 0
                p.fillRect(x, y, 8, 8, Qt.GlobalColor.white if even else Qt.GlobalColor.lightGray)
        r, g, b = self._color.redF(), self._color.greenF(), self._color.blueF()
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0, QColor.fromRgbF(r, g, b, 0))
        grad.setColorAt(1, QColor.fromRgbF(r, g, b, 1))
        p.fillRect(0, 0, w, h, grad)
        x = int(self._alpha * (w - 1))
        p.setPen(QPen(Qt.GlobalColor.black, 2))
        p.drawLine(x, 0, x, h)

    def mousePressEvent(self, event):
        self._dragging = True
        self._update_alpha(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_alpha(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._update_alpha(event)

    def _update_alpha(self, event):
        w = self.width()
        if w < 1:
            return
        self._alpha = max(0, min(1, event.position().x() / (w - 1)))
        self.update()
        self.alphaChanged.emit(self._alpha)


class ColorDialog(QDialog):
    colorChanged = pyqtSignal(object)

    def __init__(self, initial: QColor = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Color")
        self.setMinimumWidth(300)
        self.setPalette(QApplication.palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet("""
            QDialog { background: palette(window); }
            QLabel { color: palette(text); background: transparent; }
            QSpinBox {
                background: palette(base); color: palette(text);
                border: 1px solid palette(mid); border-radius: 2px; padding: 2px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: palette(button); border: 1px solid palette(mid);
                border-radius: 2px; width: 16px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: palette(light);
            }
            QLineEdit {
                background: palette(base); color: palette(text);
                border: 1px solid palette(mid); border-radius: 2px; padding: 2px;
            }
            QPushButton {
                background: palette(button); color: palette(ButtonText);
                border: 1px solid palette(mid); border-radius: 2px; padding: 4px 16px;
            }
            QPushButton:hover { background: palette(light); }
            QPushButton:pressed { background: palette(dark); color: palette(text); }
            QDialogButtonBox { background: transparent; }
        """)
        self._color = initial.toRgb() if initial and initial.isValid() else QColor.fromRgbF(1, 1, 1)
        h, s, v, a = self._color.hueF(), self._color.saturationF(), self._color.valueF(), self._color.alphaF()
        if h < 0:
            h = 0
        layout = QVBoxLayout(self)
        self._wheel = _ColorWheelWidget()
        self._wheel.set_hue(h * 360)
        self._wheel.set_sv(s, v)
        layout.addWidget(self._wheel, alignment=Qt.AlignmentFlag.AlignCenter)
        self._alpha_slider = _AlphaWidget()
        self._alpha_slider.set_alpha(a)
        self._alpha_slider.set_color(self._color)
        layout.addWidget(self._alpha_slider)
        rgb_layout = QHBoxLayout()
        self._r_spin = QSpinBox()
        self._r_spin.setRange(0, 255)
        self._r_spin.setValue(int(self._color.redF() * 255))
        self._g_spin = QSpinBox()
        self._g_spin.setRange(0, 255)
        self._g_spin.setValue(int(self._color.greenF() * 255))
        self._b_spin = QSpinBox()
        self._b_spin.setRange(0, 255)
        self._b_spin.setValue(int(self._color.blueF() * 255))
        self._a_spin = QSpinBox()
        self._a_spin.setRange(0, 255)
        self._a_spin.setValue(int(a * 255))
        rgb_layout.addWidget(QLabel("R:"))
        rgb_layout.addWidget(self._r_spin)
        rgb_layout.addWidget(QLabel("G:"))
        rgb_layout.addWidget(self._g_spin)
        rgb_layout.addWidget(QLabel("B:"))
        rgb_layout.addWidget(self._b_spin)
        rgb_layout.addWidget(QLabel("A:"))
        rgb_layout.addWidget(self._a_spin)
        layout.addLayout(rgb_layout)
        hex_layout = QHBoxLayout()
        hex_layout.addWidget(QLabel("Hex:"))
        self._hex_edit = QLineEdit()
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        hex_layout.addWidget(self._hex_edit)
        layout.addLayout(hex_layout)
        self._preview = QLabel()
        self._preview.setFixedHeight(30)
        self._update_preview()
        layout.addWidget(self._preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._wheel.colorChanged.connect(self._on_wheel_changed)
        self._wheel.hueChanged.connect(self._on_wheel_hue_changed)
        self._alpha_slider.alphaChanged.connect(self._on_alpha_changed)
        self._r_spin.valueChanged.connect(self._on_rgb_spin)
        self._g_spin.valueChanged.connect(self._on_rgb_spin)
        self._b_spin.valueChanged.connect(self._on_rgb_spin)
        self._a_spin.valueChanged.connect(self._on_a_spin)
        self._hex_edit.editingFinished.connect(self._on_hex_edited)

    def _on_wheel_changed(self):
        s, v = self._wheel.get_sv()
        a = self._color.alphaF()
        self._color.setHsvF(self._wheel.get_hue() / 360.0, s, v, a)
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_wheel_hue_changed(self, h):
        self._color.setHsvF(h / 360.0, self._wheel._sat, self._wheel._val, self._color.alphaF())
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_alpha_changed(self, a):
        self._color.setAlphaF(a)
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_rgb_spin(self):
        self._color.setRgb(self._r_spin.value(), self._g_spin.value(), self._b_spin.value(), self._a_spin.value())
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_a_spin(self, v):
        self._color.setAlpha(v)
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_hex_edited(self):
        text = self._hex_edit.text().strip()
        c = QColor(text)
        if c.isValid():
            self._color = c.toRgb()
            self._sync_from_color()
            self.colorChanged.emit(self._color)

    def _sync_from_color(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        h, s, v = self._color.hueF(), self._color.saturationF(), self._color.valueF()
        if h < 0:
            h = 0
        self._r_spin.blockSignals(True)
        self._g_spin.blockSignals(True)
        self._b_spin.blockSignals(True)
        self._a_spin.blockSignals(True)
        self._r_spin.setValue(r)
        self._g_spin.setValue(g)
        self._b_spin.setValue(b)
        self._a_spin.setValue(a)
        self._r_spin.blockSignals(False)
        self._g_spin.blockSignals(False)
        self._b_spin.blockSignals(False)
        self._a_spin.blockSignals(False)
        af = self._color.alphaF()
        self._alpha_slider.set_alpha(af)
        self._alpha_slider.set_color(self._color)
        self._wheel.set_hue(h * 360)
        self._wheel.set_sv(s, v)
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._update_preview()

    def _update_preview(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        self._preview.setStyleSheet(f"background: rgba({r},{g},{b},{a/255});")

    def get_color(self) -> QColor:
        return self._color

    @staticmethod
    def getColor(initial: QColor = None, parent=None, title="") -> QColor:
        from PyQt6.QtGui import QCursor
        dlg = ColorDialog(initial, None)
        if title:
            dlg.setWindowTitle(title)
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
        result = dlg.exec()
        c = dlg.get_color()
        if result == QDialog.DialogCode.Accepted:
            return c
        return initial if initial and initial.isValid() else QColor()
