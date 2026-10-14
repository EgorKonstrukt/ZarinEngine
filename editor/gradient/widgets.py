# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import qtawesome as qta
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QDoubleSpinBox
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QLinearGradient, QPolygonF, QPalette
from editor.color import ColorLineEdit
from .sampling import _default_gradient


class GradientPreview(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stops = _default_gradient()
        self.setMinimumSize(100, 24)
        self.setMaximumHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_stops(self, stops):
        self._stops = stops
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self._stops:
            p.fillRect(0, 0, w, h, self.palette().color(QPalette.ColorRole.Window))
            p.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "empty")
            p.end()
            return
        grad = QLinearGradient(0, 0, w, 0)
        stops = sorted(self._stops, key=lambda s: s[0])
        for pos, rgba in stops:
            r, g, b, a = rgba
            grad.setColorAt(pos, QColor.fromRgbF(r, g, b, a))
        p.fillRect(0, 0, w, h, grad)
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.Window).darker(130), 1))
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()

    def mousePressEvent(self, event):
        self.clicked.emit()


class _GradientBar(QWidget):
    stopMoved = pyqtSignal()
    stopAdded = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stops = _default_gradient()
        self._selected_idx = -1
        self._dragging = False
        self.setMinimumSize(300, 40)
        self.setMaximumHeight(50)
        self.setMouseTracking(True)

    def set_stops(self, stops):
        self._stops = stops
        self.update()

    def _stop_positions(self):
        w = self.width() - 20
        if w < 1:
            return []
        return [(s[0] * w + 10, s[0]) for s in self._stops]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bar_top = 8
        bar_h = h - 24
        bar_rect = QRectF(10, bar_top, w - 20, bar_h)
        grad = QLinearGradient(bar_rect.topLeft(), bar_rect.topRight())
        stops = sorted(self._stops, key=lambda s: s[0])
        for pos, rgba in stops:
            r, g, b, a = rgba
            grad.setColorAt(pos, QColor.fromRgbF(r, g, b, a))
        p.fillRect(bar_rect, grad)
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.Window).darker(130), 1))
        p.drawRect(bar_rect)
        for i, (pos, rgba) in enumerate(self._stops):
            x = pos * (w - 20) + 10
            r, g, b, a = rgba
            is_sel = i == self._selected_idx
            tri_size = 6
            tri_y = bar_top + bar_h
            path = [
                (x, tri_y + tri_size),
                (x - tri_size, tri_y),
                (x + tri_size, tri_y),
            ]
            p.setPen(QPen(Qt.GlobalColor.black if is_sel else self.palette().color(QPalette.ColorRole.Dark), 1))
            col = QColor.fromRgbF(r, g, b)
            p.setBrush(col)
            poly = QPolygonF()
            for a, b in path:
                poly.append(QPointF(a, b))
            p.drawPolygon(poly)
        p.end()

    def mousePressEvent(self, event):
        px = event.position().x()
        w = self.width() - 20
        if w < 1:
            return
        self._selected_idx = -1
        for i, (pos, _) in enumerate(self._stops):
            sx = pos * w + 10
            if abs(px - sx) < 10:
                self._selected_idx = i
                self._dragging = True
                self.update()
                return
        self._selected_idx = -1
        self.update()

    def mouseMoveEvent(self, event):
        if self._dragging and self._selected_idx >= 0:
            w = self.width() - 20
            if w < 1:
                return
            new_pos = max(0, min(1, (event.position().x() - 10) / w))
            self._stops[self._selected_idx] = (new_pos, self._stops[self._selected_idx][1])
            self._stops.sort(key=lambda s: s[0])
            new_idx = next(i for i, s in enumerate(self._stops) if abs(s[0] - new_pos) < 0.001)
            self._selected_idx = new_idx
            self.update()
            self.stopMoved.emit()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.update()
            self.stopMoved.emit()

    def mouseDoubleClickEvent(self, event):
        w = self.width() - 20
        if w < 1:
            return
        pos = max(0, min(1, (event.position().x() - 10) / w))
        self.stopAdded.emit(pos)

    def selected_index(self):
        return self._selected_idx


class _StopRow(QWidget):
    removeRequested = pyqtSignal(int)
    changed = pyqtSignal()

    def __init__(self, index, pos, color, parent=None):
        super().__init__(parent)
        self._index = index
        self._pos = pos
        self._color = color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(4)
        self._pos_spin = QDoubleSpinBox()
        self._pos_spin.setRange(0.0, 1.0)
        self._pos_spin.setSingleStep(0.01)
        self._pos_spin.setDecimals(3)
        self._pos_spin.setValue(pos)
        self._pos_spin.setFixedWidth(70)
        layout.addWidget(self._pos_spin)
        self._color_edit = ColorLineEdit(color)
        layout.addWidget(self._color_edit, 1)
        self._remove_btn = QPushButton(qta.icon("fa5s.times", color=chr(35) + "d4d4d4"), "")
        self._remove_btn.setFixedSize(24, 24)
        self._remove_btn.setToolTip("Remove stop")
        layout.addWidget(self._remove_btn)
        self._pos_spin.valueChanged.connect(self._on_changed)
        self._color_edit.colorChanged.connect(self._on_changed)
        self._remove_btn.clicked.connect(lambda: self.removeRequested.emit(self._index))

    def _on_changed(self):
        self.changed.emit()

    def get_data(self):
        return (self._pos_spin.value(), self._color_edit.get_color_rgba())

    def set_index(self, idx):
        self._index = idx
        self._remove_btn.setEnabled(idx >= 0)

    def sync_pos(self, pos):
        self._pos_spin.blockSignals(True)
        self._pos_spin.setValue(pos)
        self._pos_spin.blockSignals(False)
