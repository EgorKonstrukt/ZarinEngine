# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea
from PySide6.QtCore import Signal
from PySide6.QtGui import QPalette
from .sampling import _default_gradient, _sample_gradient
from .widgets import GradientPreview, _GradientBar, _StopRow


class GradientEditorDialog(QDialog):
    def __init__(self, stops=None, title="Gradient Editor", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(450, 350)
        self.resize(500, 400)
        self._stops = [list(s) for s in (stops or _default_gradient())]
        self._updating = False
        pal = self.palette()
        bg = pal.color(QPalette.ColorRole.Window)
        fg = pal.color(QPalette.ColorRole.WindowText)
        mid = pal.color(QPalette.ColorRole.Mid)
        highlight = pal.color(QPalette.ColorRole.Highlight)
        self.setStyleSheet(
            f"QDialog {{ background: {bg.name()}; }}\n"
            f"QLabel {{ color: {fg.name()}; font-size: 11px; background: transparent; }}\n"
            f"QDoubleSpinBox {{ background: {bg.name()}; color: {fg.name()}; border: 1px solid {mid.name()}; border-radius: 3px; padding: 1px 2px 1px 4px; font-size: 11px; min-height: 20px; selection-background-color: {highlight.name()}; }}\n"
            f"QDoubleSpinBox:hover {{ border-color: {mid.name()}; }}\n"
            f"QDoubleSpinBox:focus {{ border-color: {highlight.name()}; }}\n"
            f"QPushButton {{ color: {fg.name()}; background: {bg.name()}; border: 1px solid {mid.name()}; border-radius: 3px; padding: 4px 16px; font-size: 11px; }}\n"
            f"QPushButton:hover {{ background: {mid.name()}; color: {fg.name()}; }}\n"
            "QScrollArea { border: none; background: transparent; }\n"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._bar = _GradientBar()
        self._bar.set_stops(self._stops)
        self._bar.stopMoved.connect(self._on_bar_moved)
        self._bar.stopAdded.connect(self._on_bar_add)
        layout.addWidget(self._bar)
        stops_label = QLabel("Stops:")
        layout.addWidget(stops_label)
        self._stop_container = QWidget()
        self._stop_layout = QVBoxLayout(self._stop_container)
        self._stop_layout.setContentsMargins(0, 0, 0, 0)
        self._stop_layout.setSpacing(2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._stop_container)
        scroll.setMaximumHeight(200)
        layout.addWidget(scroll, 1)
        self._rebuild_stop_rows()
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ Add Stop")
        add_btn.clicked.connect(self._add_stop)
        btn_layout.addWidget(add_btn)
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _rebuild_stop_rows(self):
        while self._stop_layout.count():
            item = self._stop_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (pos, rgba) in enumerate(self._stops):
            self._add_stop_row(i, pos, rgba)

    def _add_stop_row(self, idx, pos, rgba):
        row = _StopRow(idx, pos, rgba)
        row.changed.connect(self._on_row_changed)
        row.removeRequested.connect(self._remove_stop)
        self._stop_layout.addWidget(row)

    def _on_row_changed(self):
        if self._updating:
            return
        self._sync_stops_from_rows()

    def _sync_stops_from_rows(self):
        self._stops.clear()
        for i in range(self._stop_layout.count()):
            item = self._stop_layout.itemAt(i)
            if item and item.widget():
                row = item.widget()
                self._stops.append(row.get_data())
        self._stops.sort(key=lambda s: s[0])
        self._bar.set_stops(self._stops)

    def _on_bar_moved(self):
        if self._updating:
            return
        self._stops = self._bar._stops[:]
        self._rebuild_stop_rows()

    def _on_bar_add(self, pos):
        rgba = _sample_gradient(self._stops, pos)
        self._stops.append([pos, rgba])
        self._stops.sort(key=lambda s: s[0])
        self._bar.set_stops(self._stops)
        self._rebuild_stop_rows()

    def _add_stop(self):
        pos = 0.5
        rgba = _sample_gradient(self._stops, pos)
        self._stops.append([pos, rgba])
        self._stops.sort(key=lambda s: s[0])
        self._bar.set_stops(self._stops)
        self._rebuild_stop_rows()

    def _remove_stop(self, idx):
        if len(self._stops) <= 2:
            return
        del self._stops[idx]
        self._bar.set_stops(self._stops)
        self._rebuild_stop_rows()

    def get_stops(self):
        return [tuple(s) for s in self._stops]


class GradientLineEdit(QWidget):
    gradientChanged = Signal(object)

    def __init__(self, stops=None, parent=None):
        super().__init__(parent)
        try:
            _v = stops or _default_gradient()
            _n = []
            for _s in _v:
                try:
                    _p = float(_s[0])
                    _c = list(_s[1])
                    if len(_c) < 4:
                        continue
                    _n.append([max(0.0, min(1.0, _p)), [max(0.0, min(1.0, float(_c[0]))), max(0.0, min(1.0, float(_c[1]))), max(0.0, min(1.0, float(_c[2]))), max(0.0, min(1.0, float(_c[3])))]])
                except Exception:
                    continue
            self._stops = _n if len(_n) >= 2 else [list(s) for s in _default_gradient()]
        except Exception:
            self._stops = [list(s) for s in _default_gradient()]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._preview = GradientPreview()
        self._preview.set_stops(self._stops)
        self._preview.setToolTip("Click to edit gradient")
        layout.addWidget(self._preview, 1)
        self._edit_btn = QPushButton("Edit")
        layout.addWidget(self._edit_btn)
        self._preview.clicked.connect(self._open_editor)
        self._edit_btn.clicked.connect(self._open_editor)

    def _open_editor(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QCursor
        dlg = GradientEditorDialog(self._stops, "Edit Gradient", None)
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
        if dlg.exec():
            self._stops = [list(s) for s in dlg.get_stops()]
            self._preview.set_stops(self._stops)
            self.gradientChanged.emit(self._stops)

    def set_stops(self, stops):
        try:
            _n = []
            for _s in (stops or []):
                try:
                    _p = float(_s[0])
                    _c = list(_s[1])
                    if len(_c) < 4:
                        continue
                    _n.append([max(0.0, min(1.0, _p)), [max(0.0, min(1.0, float(_c[0]))), max(0.0, min(1.0, float(_c[1]))), max(0.0, min(1.0, float(_c[2]))), max(0.0, min(1.0, float(_c[3])))]])
                except Exception:
                    continue
            if len(_n) >= 2:
                self._stops = _n
                self._preview.set_stops(self._stops)
        except Exception:
            pass

    def get_stops(self):
        return [tuple(s) for s in self._stops]
