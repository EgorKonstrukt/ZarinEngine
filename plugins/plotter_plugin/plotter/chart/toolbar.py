# MIT License
#
# Copyright (c) 2026 Zarrakun
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QToolButton, QHBoxLayout, QStyle, QMenu
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from ..i18n import tr
from ..mathx import get_fit_modes, get_fit_mode

class _ChartToolbarMixin:
    def _make_btn(self, icon_sp: str, lbl_key: str, tip_key: str, slot) -> QToolButton:
        btn = QToolButton(self)
        btn.setText(tr(lbl_key))
        btn.setToolTip(tr(tip_key))
        btn.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap, icon_sp)))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setFixedHeight(24)
        btn.clicked.connect(slot)
        return btn

    def _make_toggle_btn(self, lbl_key: str, tip_key: str,
                         default_checked: bool, slot) -> QToolButton:
        btn = QToolButton(self)
        btn.setText(tr(lbl_key))
        btn.setToolTip(tr(tip_key))
        btn.setCheckable(True)
        btn.setChecked(default_checked)
        btn.setFixedHeight(24)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.toggled.connect(slot)
        return btn

    def _build_toolbar(self) -> QHBoxLayout:
        self._btn_autofit_toggle = self._make_toggle_btn(
            "chart_widget.btn_autofit_toggle",
            "chart_widget.btn_autofit_toggle_tip",
            True,
            self.setAutofitEnabled,
        )
        self._btn_latest_toggle = self._make_toggle_btn(
            "chart_widget.btn_latest",
            "chart_widget.btn_latest_tip",
            False,
            self.setLatestPointVisible,
        )
        self._btn_origin_axes = self._make_toggle_btn(
            "chart_widget.btn_origin_axes",
            "chart_widget.btn_origin_axes_tip",
            False,
            self.setOriginAxesVisible,
        )
        self._btn_crosshair = self._make_toggle_btn(
            "chart_widget.btn_crosshair",
            "chart_widget.btn_crosshair_tip",
            True,
            self.setCrosshairVisible,
        )
        self._btn_fit = self._make_btn("SP_FileDialogContentsView",
                                       "chart_widget.btn_fit",
                                       "chart_widget.btn_fit_tip",
                                       self.autofit)
        self._btn_stats = self._make_btn("SP_FileDialogInfoView",
                                         "chart_widget.btn_analytics",
                                         "chart_widget.btn_analytics_tip",
                                         self._canvas.toggleAnalytics)
        self._btn_csv = self._make_btn("SP_DialogSaveButton",
                                       "chart_widget.btn_csv",
                                       "chart_widget.btn_csv_tip",
                                       self.exportCsv)
        self._btn_img = self._make_btn("SP_DialogSaveButton",
                                       "chart_widget.btn_img",
                                       "chart_widget.btn_img_tip",
                                       self.exportImage)
        self._btn_fit_mode = QToolButton(self)
        self._btn_fit_mode.setToolTip(tr("chart_widget.btn_fit_mode_tip"))
        self._btn_fit_mode.setFixedHeight(24)
        self._btn_fit_mode.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_fit_mode.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._fit_menu = QMenu(self._btn_fit_mode)
        none_act = QAction("None", self)
        none_act.triggered.connect(lambda: self._on_fit_mode_selected(None))
        self._fit_menu.addAction(none_act)
        for mode in get_fit_modes():
            act = QAction(mode.label, self)
            act.setData(mode.key)
            act.triggered.connect(lambda checked, k=mode.key: self._on_fit_mode_selected(k))
            self._fit_menu.addAction(act)
        self._btn_fit_mode.setMenu(self._fit_menu)
        self._update_fit_mode_label()
        tb = QHBoxLayout()
        tb.setContentsMargins(2, 2, 2, 2)
        tb.setSpacing(2)
        tb.addStretch()
        for w in (self._btn_autofit_toggle, self._btn_latest_toggle,
                  self._btn_origin_axes, self._btn_crosshair,
                  self._btn_fit, self._btn_stats, self._btn_fit_mode,
                  self._btn_csv, self._btn_img):
            tb.addWidget(w)
        return tb

    def _on_fit_mode_selected(self, key: Optional[str]):
        self._active_fit_key = key
        self._update_fit_mode_label()
        for fit in self._fits:
            if key is not None:
                fit.setModeKey(key)
        self._canvas.update()

    def _update_fit_mode_label(self):
        if self._active_fit_key is None:
            self._btn_fit_mode.setText("Approx")
            return
        mode = get_fit_mode(self._active_fit_key)
        lbl = mode.label if mode else self._active_fit_key
        self._btn_fit_mode.setText(f"{lbl} ")

    def refreshFitMenu(self):
        self._fit_menu.clear()
        none_act = QAction("None", self)
        none_act.triggered.connect(lambda: self._on_fit_mode_selected(None))
        self._fit_menu.addAction(none_act)
        for mode in get_fit_modes():
            act = QAction(mode.label, self)
            act.setData(mode.key)
            act.triggered.connect(lambda checked, k=mode.key: self._on_fit_mode_selected(k))
            self._fit_menu.addAction(act)
