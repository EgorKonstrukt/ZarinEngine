# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PySide6.QtWidgets import QPushButton, QDoubleSpinBox, QSpinBox, QFrame

_STYLE_BTN = ("QPushButton { border-radius: 3px; padding: 4px 8px; font-size: 11px; }")
_STYLE_BTN_ACCENT = ("QPushButton { border-radius: 3px; padding: 4px 8px; font-size: 11px; }")
_STYLE_LABEL = "font-size: 10px; padding: 2px 0;"
_STYLE_GROUP = ("QGroupBox { font-size: 11px; font-weight: bold; "
                "border: 1px solid; border-radius: 4px; margin-top: 8px; padding-top: 14px; } "
                "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")


def _make_btn(text: str, tooltip: str = "", accent: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(_STYLE_BTN_ACCENT if accent else _STYLE_BTN)
    btn.setMinimumHeight(24)
    return btn


def _make_spin(val: float, lo: float = -1e9, hi: float = 1e9, step: float = 0.1, decimals: int = 4) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    sb.setValue(val)
    sb.setMinimumWidth(60)
    return sb


def _make_int_spin(val: int, lo: int = 1, hi: int = 128) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setMinimumWidth(50)
    return sb


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f
