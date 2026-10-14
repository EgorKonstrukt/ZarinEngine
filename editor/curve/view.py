# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFontMetrics, QPainterPath
from core.foundation.curve import Curve, CurveKey, TangentMode


class CurvePreview(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curve: Curve = Curve()
        self._bg_color = QColor(37, 37, 37)
        self._line_color = QColor(90, 156, 245)
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_curve(self, curve: Curve):
        self._curve = curve
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self._bg_color)
        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.drawLine(0, h // 2, w, h // 2)
        if not self._curve.keys:
            p.setPen(QColor(80, 80, 80))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "empty")
            p.end()
            return
        margin = 4
        plot_w = w - margin * 2
        plot_h = h - margin * 2
        times = [k.time for k in self._curve.keys]
        vals = [k.value for k in self._curve.keys]
        t_min, t_max = min(times), max(times)
        v_min, v_max = min(vals), max(vals)
        if t_max - t_min < 1e-10:
            t_max = t_min + 1.0
        if v_max - v_min < 1e-10:
            v_max = v_min + 1.0
        path = QPainterPath()
        samples = 50
        for i in range(samples + 1):
            t = t_min + (t_max - t_min) * i / samples
            v = self._curve.evaluate(t)
            x = margin + (t - t_min) / (t_max - t_min) * plot_w
            y = margin + (1.0 - (v - v_min) / (v_max - v_min)) * plot_h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setPen(QPen(self._line_color, 2))
        p.drawPath(path)
        p.end()

    def mousePressEvent(self, event):
        self.clicked.emit()


class CurveViewMixin:

    def _get_key_rect(self, key: CurveKey) -> QRectF:
        x, y = self._key_to_screen(key)
        return QRectF(x - 5, y - 5, 10, 10)

    def _key_to_screen(self, key: CurveKey) -> tuple[float, float]:
        t_min, t_max, v_min, v_max = self._get_bounds()
        m = 30
        pw = self.width() - m * 2
        ph = self.height() - m * 2
        sx = m + (key.time - t_min) / max(t_max - t_min, 1e-10) * pw
        sy = m + (1.0 - (key.value - v_min) / max(v_max - v_min, 1e-10)) * ph
        return sx, sy

    def _screen_to_value(self, sx: float, sy: float) -> tuple[float, float]:
        t_min, t_max, v_min, v_max = self._get_bounds()
        m = 30
        pw = self.width() - m * 2
        ph = self.height() - m * 2
        t = t_min + (sx - m) / max(pw, 1) * (t_max - t_min)
        v = v_min + (1.0 - (sy - m) / max(ph, 1)) * (v_max - v_min)
        return t, v

    def _get_bounds(self) -> tuple[float, float, float, float]:
        return self._view_t0, self._view_t1, self._view_v0, self._view_v1

    def _view_metrics(self) -> tuple[float, float, float, float, float, float]:
        t_min, t_max, v_min, v_max = self._get_bounds()
        m = 30
        pw = max(self.width() - m * 2, 1)
        ph = max(self.height() - m * 2, 1)
        return pw, ph, t_min, t_max, v_min, v_max

    def _tangent_handle_offset(self, slope: float, pw: float, ph: float, t_min: float, t_max: float, v_min: float, v_max: float) -> tuple[float, float]:
        dx = pw / max(t_max - t_min, 1e-10)
        dy = -slope * ph / max(v_max - v_min, 1e-10)
        length = math.hypot(dx, dy) or 1.0
        return dx / length * self._handle_len, dy / length * self._handle_len

    def _tangent_handle_pos(self, key: CurveKey, side: str) -> tuple[float, float] | None:
        keys = self._curve.keys
        if len(keys) < 2:
            return None
        idx = keys.index(key)
        if side == "in" and idx == 0:
            return None
        if side == "out" and idx == len(keys) - 1:
            return None
        if key.tangent_mode not in (TangentMode.FREE, TangentMode.SMOOTH):
            return None
        sx, sy = self._key_to_screen(key)
        pw, ph, t_min, t_max, v_min, v_max = self._view_metrics()
        slope = key.in_tangent if side == "in" else key.out_tangent
        ox, oy = self._tangent_handle_offset(slope, pw, ph, t_min, t_max, v_min, v_max)
        if side == "in":
            ox = -ox
            oy = -oy
        return sx + ox, sy + oy

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self._bg_color)
        self._draw_grid(p)
        self._draw_curve(p)
        self._draw_tangents(p)
        self._draw_keys(p)
        self._draw_readout(p)

    def _draw_grid(self, p: QPainter):
        t_min, t_max, v_min, v_max = self._get_bounds()
        m = 30
        pw = w = self.width() - m * 2
        ph = self.height() - m * 2
        n_div = 8
        for i in range(n_div + 1):
            frac = i / n_div
            x = m + frac * pw
            p.setPen(QPen(self._grid_color, 1))
            p.drawLine(int(x), m, int(x), m + ph)
            t = t_min + frac * (t_max - t_min)
            p.setPen(self._text_color)
            lbl = f"{t:.2f}"
            fm = QFontMetrics(p.font())
            tw = fm.horizontalAdvance(lbl)
            p.drawText(int(x - tw / 2), m + ph + 14, lbl)
            y = m + frac * ph
            p.setPen(QPen(self._grid_color, 1))
            p.drawLine(m, int(y), m + pw, int(y))
            v = v_max - frac * (v_max - v_min)
            val_lbl = f"{v:.2f}"
            p.setPen(self._text_color)
            p.drawText(2, int(y + 4), val_lbl)
        p.setPen(QPen(self._major_grid_color, 1))
        p.drawRect(m, m, pw, ph)

    def _draw_curve(self, p: QPainter):
        if not self._curve.keys:
            return
        t_min, t_max, v_min, v_max = self._get_bounds()
        m = 30
        pw = self.width() - m * 2
        ph = self.height() - m * 2
        path = QPainterPath()
        samples = max(100, pw)
        for i in range(samples + 1):
            t = t_min + (t_max - t_min) * i / samples
            v = self._curve.evaluate(t)
            x = m + (t - t_min) / max(t_max - t_min, 1e-10) * pw
            y = m + (1.0 - (v - v_min) / max(v_max - v_min, 1e-10)) * ph
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setPen(QPen(self._curve_color, 2))
        p.drawPath(path)

    def _draw_tangents(self, p: QPainter):
        k = self._selected_key
        if not k:
            return
        x, y = self._key_to_screen(k)
        for side in ("in", "out"):
            pos = self._tangent_handle_pos(k, side)
            if pos is None:
                continue
            tx, ty = pos
            p.setPen(QPen(self._tangent_color, 1, Qt.PenStyle.DashLine))
            p.drawLine(int(x), int(y), int(tx), int(ty))
            p.setBrush(QBrush(self._tangent_color))
            p.drawEllipse(QPointF(tx, ty), 4, 4)

    def _draw_keys(self, p: QPainter):
        for k in self._curve.keys:
            x, y = self._key_to_screen(k)
            is_selected = k is self._selected_key
            color = self._key_selected_color if is_selected else self._key_color
            p.setBrush(QBrush(color))
            p.setPen(QPen(Qt.GlobalColor.black, 1))
            p.drawEllipse(QPointF(x, y), 6 if is_selected else 4, 6 if is_selected else 4)

    def _draw_readout(self, p: QPainter):
        if self._hovered_key:
            k = self._hovered_key
            text = f"t={k.time:.3f}  v={k.value:.3f}"
            p.setPen(self._text_color)
            p.drawText(self.width() - 180, 15, text)
        elif self._selected_key:
            k = self._selected_key
            text = f"t={k.time:.3f}  v={k.value:.3f}"
            p.setPen(self._text_color)
            p.drawText(self.width() - 180, 15, text)
