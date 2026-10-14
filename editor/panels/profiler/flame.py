# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QFontMetrics, QPalette
from .timeline import _name_to_color, _FONT, _FONT_SMALL, _FONT_TINY


class FlameGraphWidget(QWidget):
    ROW_H = 21
    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples: list = []
        self._frame_time_ms: float = 1.0
        self._work_time_ms: float = 1.0
        self._hovered: tuple | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(120)
    def set_data(self, samples: list, frame_time_ms: float):
        self._samples = samples
        self._frame_time_ms = max(frame_time_ms, 0.001)
        work_ms = self._frame_time_ms
        for s in samples:
            if s.name == "frame" and s.depth == 0:
                work_ms = max(s.duration_ms, 0.001)
                break
        self._work_time_ms = work_ms
        h = (max((s.depth for s in samples), default=0) + 2) * self.ROW_H
        self.setMinimumHeight(max(h, 120))
        self.update()
    def clear_data(self):
        self._samples = []
        self._frame_time_ms = 1.0
        self._work_time_ms = 1.0
        self._hovered = None
        self.setMinimumHeight(120)
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        txt = pal.color(QPalette.ColorRole.Text)
        mut = pal.color(QPalette.ColorRole.PlaceholderText)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, base)
        if not self._samples:
            p.setPen(mut)
            p.setFont(_FONT)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No profile data")
            p.end()
            return
        margin = 8
        plot_w = w - margin * 2
        if plot_w < 10:
            p.end()
            return
        bft = max(getattr(self, "_work_time_ms", 1.0), 0.001)
        pft = max(self._frame_time_ms, 0.001)
        frame_end_ms = 0.0
        for s in self._samples:
            if s.name == "frame" and s.depth == 0:
                frame_end_ms = s.start_ms + s.duration_ms
                break
        if frame_end_ms > 0 and frame_end_ms < self._frame_time_ms:
            idle_x = margin + (frame_end_ms / bft) * plot_w
            if idle_x < w - margin:
                p.setPen(mut)
                p.setFont(_FONT_TINY)
                idle_pct = (self._frame_time_ms - frame_end_ms) / self._frame_time_ms * 100
                p.drawText(QRectF(idle_x + 4, 4, w - idle_x - 12, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                           "Idle " + format(idle_pct, ".0f") + " %")
        ordered = sorted(self._samples, key=lambda s: (s.depth, s.start_ms))
        for s in ordered:
            x = margin + (s.start_ms / bft) * plot_w
            bw = max(2, (s.duration_ms / bft) * plot_w)
            y = s.depth * self.ROW_H + 6
            bh = self.ROW_H - 4
            if x + bw < 0 or x > w:
                continue
            color = _name_to_color(s.name)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(QRectF(x, y, bw, bh), 3, 3)
            p.setPen(QPen(QColor(0, 0, 0, 70), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, bw - 1, bh - 1), 3, 3)
            if bw > 46:
                p.setPen(QColor(22, 22, 22))
                p.setFont(_FONT_SMALL)
                pct = s.duration_ms / pft * 100.0
                label = s.name + "  " + format(pct, ".1f") + " %"
                tw = QFontMetrics(_FONT_SMALL).horizontalAdvance(label)
                if tw < bw - 10:
                    p.drawText(QRectF(x + 6, y, bw - 12, bh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            elif bw > 22 and s.depth > 0:
                p.setPen(QColor(22, 22, 22))
                p.setFont(_FONT_TINY)
                pct = s.duration_ms / pft * 100.0
                label = format(pct, ".0f") + " %"
                tw = QFontMetrics(_FONT_TINY).horizontalAdvance(label)
                if tw < bw - 6:
                    p.drawText(QRectF(x + 3, y, bw - 6, bh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        if self._hovered:
            sx, sy, sample = self._hovered
            pct = sample.duration_ms / pft * 100.0
            info = sample.name + "  " + format(sample.duration_ms, ".3f") + "ms  " + format(pct, ".1f") + " %"
            fm = QFontMetrics(_FONT)
            tw = fm.horizontalAdvance(info) + 18
            tx = sx
            if tx < 4:
                tx = 4
            if tx + tw > w - 4:
                tx = w - tw - 4
            ty = sy - 26
            if ty < 2:
                ty = sy + 24
            p.setPen(QPen(mid, 1))
            tip = QColor(base)
            tip.setAlpha(240)
            p.setBrush(QBrush(tip))
            p.drawRoundedRect(tx, ty, tw, 21, 4, 4)
            p.setPen(txt)
            p.setFont(_FONT)
            p.drawText(tx, ty, tw, 21, Qt.AlignmentFlag.AlignCenter, info)
        p.end()
    def mouseMoveEvent(self, event):
        x, y = event.position().x(), event.position().y()
        margin = 8
        w = self.width()
        plot_w = w - margin * 2
        ft = max(getattr(self, "_work_time_ms", 1.0), 0.001)
        self._hovered = None
        if plot_w > 0 and self._samples:
            for s in self._samples:
                sx = margin + (s.start_ms / ft) * plot_w
                bw = max(2, (s.duration_ms / ft) * plot_w)
                sy = s.depth * self.ROW_H + 6
                bh = self.ROW_H - 4
                if sx <= x <= sx + bw and sy <= y <= sy + bh:
                    self._hovered = (int(sx), int(sy), s)
                    break
        self.update()
    def leaveEvent(self, event):
        self._hovered = None
        self.update()
