# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QPainter, QBrush, QPen, QImage, QPalette


def _hsv_to_rgb(h, s, v):
    h = h % 360
    s = max(0, min(1, s))
    v = max(0, min(1, v))
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (r + m, g + m, b + m)


def _rgb_to_hsv(r, g, b):
    mx = max(r, g, b)
    mn = min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0
    elif mx == r:
        h = 60 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60 * (((b - r) / d) + 2)
    else:
        h = 60 * (((r - g) / d) + 4)
    s = 0 if mx == 0 else d / mx
    v = mx
    return (h % 360, s, v)


def _hue_to_screen_angle(hue_deg):
    return math.radians((hue_deg - 90) % 360)


def _screen_angle_to_hue(angle_rad):
    return (math.degrees(angle_rad) + 90 + 360) % 360


class _ColorWheelWidget(QWidget):
    colorChanged = Signal()
    hueChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 220)
        self._hue = 0.0
        self._sat = 1.0
        self._val = 1.0
        self._wheel_pixmap = None
        self._tri_image = None
        self._dragging = None

    @property
    def _cx(self):
        return self.width() / 2

    @property
    def _cy(self):
        return self.height() / 2

    @property
    def _R_outer(self):
        return min(self.width(), self.height()) / 2 - 2

    @property
    def _R_inner(self):
        return self._R_outer - 22

    @property
    def _R_tri(self):
        return self._R_inner - 6

    def set_hue(self, h):
        h = h % 360
        if h != self._hue:
            self._hue = h
            self._tri_image = None
            self.update()

    def set_sv(self, s, v):
        self._sat = max(0, min(1, s))
        self._val = max(0, min(1, v))
        self.update()

    def get_hue(self):
        return self._hue

    def get_sv(self):
        return (self._sat, self._val)

    def _tri_vertices(self):
        hue_rad = _hue_to_screen_angle(self._hue)
        offset = 2 * math.pi / 3
        r = self._R_tri
        cx, cy = self._cx, self._cy
        return [
            (cx + r * math.cos(hue_rad), cy + r * math.sin(hue_rad)),
            (cx + r * math.cos(hue_rad + offset), cy + r * math.sin(hue_rad + offset)),
            (cx + r * math.cos(hue_rad - offset), cy + r * math.sin(hue_rad - offset)),
        ]

    def paintEvent(self, event):
        if self._wheel_pixmap is None:
            self._render_wheel()
        if self._tri_image is None:
            self._render_triangle()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QApplication.palette().color(QPalette.ColorRole.Window))
        p.drawPixmap(0, 0, self._wheel_pixmap)
        p.drawImage(0, 0, self._tri_image)
        self._draw_tri_indicator(p)
        self._draw_wheel_indicator(p)

    def _render_wheel(self):
        w, h = self.width(), self.height()
        cx, cy = self._cx, self._cy
        R_out = self._R_outer
        R_in = self._R_inner
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(0)
        for py in range(h):
            dy = py - cy
            for px in range(w):
                dx = px - cx
                dist = math.hypot(dx, dy)
                if dist < R_in or dist > R_out:
                    continue
                ang = math.atan2(dy, dx)
                hue = (math.degrees(ang) + 90 + 360) % 360
                c = QColor.fromHsvF((hue % 360) / 360.0, 1.0, 1.0)
                img.setPixel(px, py, c.rgba())
        pm = QPixmap.fromImage(img)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QApplication.palette().color(QPalette.ColorRole.Window)))
        p.drawEllipse(int(cx - R_in), int(cy - R_in), int(R_in * 2), int(R_in * 2))
        p.end()
        self._wheel_pixmap = pm

    def _render_triangle(self):
        w, h = self.width(), self.height()
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(0)
        verts = self._tri_vertices()
        ax, ay = verts[0]
        bx, by = verts[1]
        cx_v, cy_v = verts[2]
        area2 = (bx - ax) * (cy_v - ay) - (cx_v - ax) * (by - ay)
        if abs(area2) < 0.001:
            self._tri_image = img
            return
        min_x = max(0, int(min(ax, bx, cx_v)))
        max_x = min(w, int(max(ax, bx, cx_v)) + 1)
        min_y = max(0, int(min(ay, by, cy_v)))
        max_y = min(h, int(max(ay, by, cy_v)) + 1)
        for py in range(min_y, max_y):
            for px in range(min_x, max_x):
                u = ((bx - px) * (cy_v - py) - (cx_v - px) * (by - py)) / area2
                v = ((cx_v - px) * (ay - py) - (ax - px) * (cy_v - py)) / area2
                wv = 1 - u - v
                if u >= 0 and v >= 0 and wv >= 0:
                    s = u
                    val = 1 - wv
                    r, g, b = _hsv_to_rgb(self._hue, s, val)
                    rgb = (0xFF << 24) | (int(r * 255) << 16) | (int(g * 255) << 8) | int(b * 255)
                    img.setPixel(px, py, rgb)
        self._tri_image = img

    def _draw_wheel_indicator(self, p):
        R_mid = (self._R_outer + self._R_inner) / 2
        hue_rad = _hue_to_screen_angle(self._hue)
        ix = self._cx + R_mid * math.cos(hue_rad)
        iy = self._cy + R_mid * math.sin(hue_rad)
        p.setPen(QPen(Qt.GlobalColor.black, 1))
        p.setBrush(QBrush(Qt.GlobalColor.white))
        p.drawEllipse(int(ix) - 5, int(iy) - 5, 10, 10)
        p.setPen(QPen(Qt.GlobalColor.black, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(ix) - 5, int(iy) - 5, 10, 10)

    def _draw_tri_indicator(self, p):
        verts = self._tri_vertices()
        ax, ay = verts[0]
        bx, by = verts[1]
        cx_v, cy_v = verts[2]
        u = self._sat
        wv = 1 - self._val
        v = 1 - u - wv
        total = u + v + wv
        if total > 0:
            u /= total
            v /= total
            wv /= total
        else:
            u, v, wv = 1, 0, 0
        px = u * ax + v * bx + wv * cx_v
        py = u * ay + v * by + wv * cy_v
        lum = self._val * 0.299 + self._sat * 0.587 + (1 - self._val) * 0.114
        pen = QPen(Qt.GlobalColor.black if lum > 0.5 else Qt.GlobalColor.white)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(px) - 5, int(py) - 5, 10, 10)

    def mousePressEvent(self, event):
        px = event.position().x()
        py = event.position().y()
        dx = px - self._cx
        dy = py - self._cy
        dist = math.hypot(dx, dy)
        if self._R_inner <= dist <= self._R_outer:
            self._dragging = "wheel"
            self._update_hue(px, py)
        elif dist < self._R_inner:
            self._dragging = "triangle"
            self._update_sv(px, py)

    def mouseMoveEvent(self, event):
        if self._dragging == "wheel":
            self._update_hue(event.position().x(), event.position().y())
        elif self._dragging == "triangle":
            self._update_sv(event.position().x(), event.position().y())

    def mouseReleaseEvent(self, event):
        if self._dragging == "wheel":
            self._update_hue(event.position().x(), event.position().y())
        elif self._dragging == "triangle":
            self._update_sv(event.position().x(), event.position().y())
        self._dragging = None

    def _update_hue(self, px, py):
        dx = px - self._cx
        dy = py - self._cy
        angle = math.atan2(dy, dx)
        new_hue = _screen_angle_to_hue(angle)
        if new_hue != self._hue:
            self._hue = new_hue
            self._tri_image = None
            self.update()
            self.hueChanged.emit(self._hue)
            self.colorChanged.emit()

    def _update_sv(self, px, py):
        verts = self._tri_vertices()
        ax, ay = verts[0]
        bx, by = verts[1]
        cx_v, cy_v = verts[2]
        area2 = (bx - ax) * (cy_v - ay) - (cx_v - ax) * (by - ay)
        if abs(area2) < 0.001:
            return
        u = ((bx - px) * (cy_v - py) - (cx_v - px) * (by - py)) / area2
        v = ((cx_v - px) * (ay - py) - (ax - px) * (cy_v - py)) / area2
        wv = 1 - u - v
        if u < 0:
            d = v + wv
            if d > 0:
                v /= d
                wv /= d
            u = 0
            v = max(0, min(1, v))
            wv = max(0, min(1, 1 - v))
        elif v < 0:
            d = u + wv
            if d > 0:
                u /= d
                wv /= d
            u = max(0, min(1, u))
            wv = max(0, min(1, 1 - u))
            v = 0
        elif wv < 0:
            d = u + v
            if d > 0:
                u /= d
                v /= d
            u = max(0, min(1, u))
            v = max(0, min(1, 1 - u))
            wv = 0
        new_sat = u
        new_val = 1 - wv
        if new_sat != self._sat or new_val != self._val:
            self._sat = new_sat
            self._val = new_val
            self.update()
            self.colorChanged.emit()
