# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter

from .theme import Theme


class InspectionOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._errors = 0
        self._warnings = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        from core.config.editor_scale import scale
        self.setFixedHeight(scale(18))
        self.setFont(QFont("Consolas", 9))

    def set_counts(self, errors: int, warnings: int):
        self._errors = int(errors)
        self._warnings = int(warnings)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setFont(self.font())
        fm = p.fontMetrics()
        from core.config.editor_scale import scale
        if self._errors > 0:
            s_err = "✖ " + str(self._errors) + "   "
        else:
            s_err = ""
        s_warn = "⚠ " + str(self._warnings) + "   "
        s_ok = "✓" if self._errors == 0 else ""
        total = s_err + s_warn + s_ok + "  ^"
        total_w = fm.horizontalAdvance(total) + scale(12)
        x0 = max(0, self.width() - total_w)
        yb = fm.ascent() + scale(3)
        x = x0
        if s_err:
            p.setPen(QColor(*Theme.error_red))
            p.drawText(x, yb, "✖ ")
            x += fm.horizontalAdvance("✖ ")
            p.setPen(QColor(200, 200, 200))
            p.drawText(x, yb, str(self._errors) + "   ")
            x += fm.horizontalAdvance(str(self._errors) + "   ")
        p.setPen(QColor(*Theme.warn_yellow))
        p.drawText(x, yb, "⚠ ")
        x += fm.horizontalAdvance("⚠ ")
        p.setPen(QColor(200, 200, 200))
        p.drawText(x, yb, str(self._warnings) + "   ")
        x += fm.horizontalAdvance(str(self._warnings) + "   ")
        if s_ok:
            p.setPen(QColor(110, 200, 110))
            p.drawText(x, yb, "✓")
            x += fm.horizontalAdvance("✓")
        p.setPen(QColor(200, 200, 200))
        p.drawText(x, yb, "  ^")
        p.end()
