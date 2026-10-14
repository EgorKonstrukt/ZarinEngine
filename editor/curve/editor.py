# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QComboBox, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QSplitter
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QColor
from core.foundation.curve import Curve, CurveKey, TangentMode
from editor.curve_presets import build_preset, PRESET_CATEGORIES
from editor.curve.view import CurvePreview, CurveViewMixin
from editor.curve.keys import CurveKeysMixin


class CurveWidget(CurveViewMixin, CurveKeysMixin, QWidget):
    curve_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curve: Curve = Curve()
        self._selected_key: CurveKey = None
        self._dragging: bool = False
        self._drag_tangent: str = None
        self._hovered_key: CurveKey = None
        self._handle_len: float = 42.0
        self._view_t0: float = 0.0
        self._view_t1: float = 1.0
        self._view_v0: float = 0.0
        self._view_v1: float = 1.0
        self._panning: bool = False
        self._pan_last: QPointF = QPointF(0, 0)
        self._pan_moved: bool = False
        self._pan_deselect: bool = False
        self._grid_color = QColor(42, 42, 42)
        self._major_grid_color = QColor(60, 60, 60)
        self._bg_color = QColor(30, 30, 30)
        self._curve_color = QColor(90, 156, 245)
        self._key_color = QColor(206, 145, 120)
        self._key_selected_color = QColor(220, 220, 220)
        self._tangent_color = QColor(160, 160, 160)
        self._text_color = QColor(140, 140, 140)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_curve(self, curve: Curve):
        self._curve = curve
        self._selected_key = None
        self.fit_view()
        self.update()

    def get_curve(self) -> Curve:
        return self._curve

    def fit_view(self):
        if not self._curve.keys:
            self._view_t0, self._view_t1, self._view_v0, self._view_v1 = 0.0, 1.0, 0.0, 1.0
            self.update()
            return
        times = [k.time for k in self._curve.keys]
        vals = [k.value for k in self._curve.keys]
        t_min, t_max = min(times), max(times)
        v_min, v_max = min(vals), max(vals)
        if t_max - t_min < 1e-10:
            t_max = t_min + 1.0
        if v_max - v_min < 1e-10:
            v_max = v_min + 1.0
        dt = (t_max - t_min) * 0.15
        dv = (v_max - v_min) * 0.15
        self._view_t0 = t_min - dt
        self._view_t1 = t_max + dt
        self._view_v0 = v_min - dv
        self._view_v1 = v_max + dv
        self.update()


class CurveEditorDialog(QDialog):
    def __init__(self, curve: Curve, title: str = "Curve Editor", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 480)
        self.resize(860, 580)
        self._curve = curve
        self.setStyleSheet(
            "QDialog { background: rgb(30,30,30); }"
            "QGroupBox { color: rgb(204,204,204); border: 1px solid rgb(60,60,60); border-radius: 4px; margin-top: 12px; padding-top: 16px; font-size: 11px; font-weight: 600; }"
            "QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 8px; color: rgb(90,156,245); }"
            "QLabel { color: rgb(204,204,204); font-size: 11px; background: transparent; }"
            "QDoubleSpinBox, QSpinBox { background: rgb(42,42,42); color: rgb(238,238,238); border: 1px solid rgb(60,60,60); border-radius: 3px; padding: 1px 2px 1px 4px; font-size: 11px; min-height: 20px; selection-background-color: rgb(90,156,245); }"
            "QDoubleSpinBox:hover, QSpinBox:hover { border-color: rgb(74,74,74); }"
            "QDoubleSpinBox:focus, QSpinBox:focus { border-color: rgb(90,156,245); }"
            "QComboBox { background: rgb(42,42,42); color: rgb(238,238,238); border: 1px solid rgb(60,60,60); border-radius: 3px; padding: 2px 4px; font-size: 11px; min-height: 20px; }"
            "QComboBox:hover { border-color: rgb(74,74,74); }"
            "QComboBox::drop-down { border: none; width: 16px; }"
            "QComboBox::down-arrow { width: 8px; height: 8px; }"
            "QComboBox QAbstractItemView { background: rgb(37,37,37); color: rgb(204,204,204); border: 1px solid rgb(60,60,60); selection-background-color: rgb(51,51,51); selection-color: rgb(238,238,238); }"
            "QPushButton { color: rgb(204,204,204); background: rgb(42,42,42); border: 1px solid rgb(74,74,74); border-radius: 3px; padding: 4px 16px; font-size: 11px; }"
            "QPushButton:hover { background: rgb(51,51,51); color: rgb(238,238,238); }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._curve_widget = CurveWidget()
        self._curve_widget.set_curve(curve)
        self._curve_widget.curve_changed.connect(self._on_curve_changed)
        top_split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)
        left_lay.addWidget(self._curve_widget, 1)
        hint = QLabel("Wheel: zoom  ·  Middle-drag / drag empty space: pan  ·  F: fit  ·  Double-click: add key  ·  Del: remove selected")
        hint.setStyleSheet("color: rgb(136,136,136); font-size: 10px;")
        left_lay.addWidget(hint)
        top_split.addWidget(left)
        top_split.addWidget(self._build_presets_panel())
        top_split.setStretchFactor(0, 3)
        top_split.setStretchFactor(1, 2)
        layout.addWidget(top_split, 1)
        info_group = QGroupBox("Selected Key")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(4)
        self._time_spin = QDoubleSpinBox()
        self._time_spin.setRange(0.0, 1.0)
        self._time_spin.setSingleStep(0.01)
        self._time_spin.setDecimals(4)
        self._value_spin = QDoubleSpinBox()
        self._value_spin.setRange(-10.0, 10.0)
        self._value_spin.setSingleStep(0.01)
        self._value_spin.setDecimals(4)
        self._in_tangent_spin = QDoubleSpinBox()
        self._in_tangent_spin.setRange(-100.0, 100.0)
        self._in_tangent_spin.setSingleStep(0.1)
        self._in_tangent_spin.setDecimals(4)
        self._out_tangent_spin = QDoubleSpinBox()
        self._out_tangent_spin.setRange(-100.0, 100.0)
        self._out_tangent_spin.setSingleStep(0.1)
        self._out_tangent_spin.setDecimals(4)
        self._tangent_combo = QComboBox()
        for mode in TangentMode:
            self._tangent_combo.addItem(mode.value.capitalize(), mode)
        self._tangent_combo.currentIndexChanged.connect(self._on_tangent_mode_changed)
        info_layout.addWidget(QLabel("Time:"), 0, 0)
        info_layout.addWidget(self._time_spin, 0, 1)
        info_layout.addWidget(QLabel("Value:"), 0, 2)
        info_layout.addWidget(self._value_spin, 0, 3)
        info_layout.addWidget(QLabel("In Tangent:"), 1, 0)
        info_layout.addWidget(self._in_tangent_spin, 1, 1)
        info_layout.addWidget(QLabel("Out Tangent:"), 1, 2)
        info_layout.addWidget(self._out_tangent_spin, 1, 3)
        info_layout.addWidget(QLabel("Mode:"), 2, 0)
        info_layout.addWidget(self._tangent_combo, 2, 1, 1, 3)
        self._time_spin.valueChanged.connect(self._on_spin_changed)
        self._value_spin.valueChanged.connect(self._on_spin_changed)
        self._in_tangent_spin.valueChanged.connect(self._on_tangent_spin_changed)
        self._out_tangent_spin.valueChanged.connect(self._on_tangent_spin_changed)
        layout.addWidget(info_group)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        btn_layout.addStretch()
        fit_btn = QPushButton("Fit View")
        fit_btn.clicked.connect(self._curve_widget.fit_view)
        btn_layout.addWidget(fit_btn)
        add_btn = QPushButton("Add Key (0,0)")
        add_btn.clicked.connect(lambda: self._add_key_at(0.0, 0.0))
        btn_layout.addWidget(add_btn)
        add_btn2 = QPushButton("Add Key (1,1)")
        add_btn2.clicked.connect(lambda: self._add_key_at(1.0, 1.0))
        btn_layout.addWidget(add_btn2)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        self._updating = False
        self._curve_widget.curve_changed.connect(self._sync_spins)

    def _on_curve_changed(self):
        self._sync_spins()

    def _build_presets_panel(self) -> QWidget:
        group = QGroupBox("Presets")
        vlay = QVBoxLayout(group)
        vlay.setContentsMargins(4, 4, 4, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        cvlay = QVBoxLayout(content)
        cvlay.setContentsMargins(2, 2, 2, 2)
        cvlay.setSpacing(6)
        cols = 3
        for cat, names in PRESET_CATEGORIES:
            cat_lbl = QLabel(cat)
            cat_lbl.setStyleSheet("color: rgb(90,156,245); font-size: 10px; font-weight: 600; padding: 2px 0;")
            cvlay.addWidget(cat_lbl)
            grid = QGridLayout()
            grid.setSpacing(4)
            grid.setContentsMargins(0, 0, 0, 0)
            for i, name in enumerate(names):
                grid.addWidget(self._make_preset_item(name), i // cols, i % cols)
            cvlay.addLayout(grid)
        cvlay.addStretch()
        scroll.setWidget(content)
        vlay.addWidget(scroll)
        return group

    def _make_preset_item(self, name: str) -> QWidget:
        item = QWidget()
        item.setCursor(Qt.CursorShape.PointingHandCursor)
        vlay = QVBoxLayout(item)
        vlay.setContentsMargins(2, 2, 2, 2)
        vlay.setSpacing(2)
        pv = CurvePreview()
        pv.setFixedSize(78, 46)
        pv.set_curve(build_preset(name))
        lbl = QLabel(name)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: rgb(204,204,204); font-size: 10px;")
        lbl.setWordWrap(True)
        vlay.addWidget(pv)
        vlay.addWidget(lbl)

        def _on_click(event):
            self._apply_preset(name)

        item.mousePressEvent = _on_click
        pv.mousePressEvent = _on_click
        return item

    def _apply_preset(self, name: str):
        preset = build_preset(name)
        self._curve.keys = [
            CurveKey(
                time=k.time, value=k.value, in_tangent=k.in_tangent,
                out_tangent=k.out_tangent, tangent_mode=k.tangent_mode,
            )
            for k in preset.keys
        ]
        self._curve.pre_wrap = preset.pre_wrap
        self._curve.post_wrap = preset.post_wrap
        self._curve_widget.set_curve(self._curve)
        self._curve_widget.curve_changed.emit()
        self._sync_spins()

    def _sync_spins(self):
        if self._updating:
            return
        self._updating = True
        k = self._curve_widget._selected_key
        if k:
            self._time_spin.setValue(k.time)
            self._value_spin.setValue(k.value)
            self._in_tangent_spin.setValue(k.in_tangent)
            self._out_tangent_spin.setValue(k.out_tangent)
            idx = self._tangent_combo.findData(k.tangent_mode)
            if idx >= 0:
                self._tangent_combo.setCurrentIndex(idx)
            self._time_spin.setEnabled(True)
            self._value_spin.setEnabled(True)
            self._in_tangent_spin.setEnabled(True)
            self._out_tangent_spin.setEnabled(True)
            self._tangent_combo.setEnabled(True)
        else:
            self._time_spin.setEnabled(False)
            self._value_spin.setEnabled(False)
            self._in_tangent_spin.setEnabled(False)
            self._out_tangent_spin.setEnabled(False)
            self._tangent_combo.setEnabled(False)
        self._updating = False

    def _on_spin_changed(self):
        if self._updating:
            return
        k = self._curve_widget._selected_key
        if k:
            k.time = round(self._time_spin.value(), 4)
            k.value = round(self._value_spin.value(), 4)
            self._curve._auto_smooth()
            self._curve_widget.update()

    def _on_tangent_spin_changed(self):
        if self._updating:
            return
        k = self._curve_widget._selected_key
        if k:
            k.in_tangent = self._in_tangent_spin.value()
            k.out_tangent = self._out_tangent_spin.value()
            k.tangent_mode = TangentMode.FREE
            self._curve_widget.update()

    def _on_tangent_mode_changed(self, idx):
        if self._updating:
            return
        k = self._curve_widget._selected_key
        if k:
            mode = self._tangent_combo.currentData()
            k.tangent_mode = mode
            self._curve._auto_smooth()
            self._curve_widget.update()

    def _add_key_at(self, t: float, v: float):
        self._curve.add_key(t, v)
        self._curve_widget.update()

    def get_curve(self) -> Curve:
        return self._curve_widget.get_curve()
