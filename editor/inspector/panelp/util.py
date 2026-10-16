# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QFontMetrics
from core.config.editor_scale import scale


def _smart_label_width(label: QLabel, base: int = 120) -> int:
    fm = QFontMetrics(label.font())
    text_w = fm.horizontalAdvance(label.text())
    scaled = scale(base)
    if text_w <= 60:
        return text_w + 4
    elif text_w <= 100:
        return min(int(text_w * 0.6), scaled)
    else:
        return max(min(int(text_w * 0.42), scaled), scale(36))
