# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from core.foundation.curve import TangentMode


class CurveKeysMixin:

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last = pos
            self._pan_moved = False
            self._pan_deselect = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._selected_key:
                for side in ("in", "out"):
                    hpos = self._tangent_handle_pos(self._selected_key, side)
                    if hpos and math.hypot(pos.x() - hpos[0], pos.y() - hpos[1]) <= 7:
                        self._drag_tangent = side
                        self._dragging = True
                        self.update()
                        return
            for k in self._curve.keys:
                if self._get_key_rect(k).contains(pos):
                    self._selected_key = k
                    self._dragging = True
                    self.update()
                    return
            for k in self._curve.keys:
                for side in ("in", "out"):
                    hpos = self._tangent_handle_pos(k, side)
                    if hpos and math.hypot(pos.x() - hpos[0], pos.y() - hpos[1]) <= 7:
                        self._selected_key = k
                        self._drag_tangent = side
                        self._dragging = True
                        self.update()
                        return
            self._panning = True
            self._pan_last = pos
            self._pan_moved = False
            self._pan_deselect = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        if self._panning:
            dx = pos.x() - self._pan_last.x()
            dy = pos.y() - self._pan_last.y()
            self._pan_last = pos
            if abs(dx) > 2 or abs(dy) > 2:
                self._pan_moved = True
            m = 30
            pw = max(self.width() - m * 2, 1)
            ph = max(self.height() - m * 2, 1)
            dt = dx / pw * (self._view_t1 - self._view_t0)
            dv = dy / ph * (self._view_v1 - self._view_v0)
            self._view_t0 -= dt
            self._view_t1 -= dt
            self._view_v0 += dv
            self._view_v1 += dv
            self.update()
            return
        if self._dragging and self._selected_key:
            if self._drag_tangent:
                k = self._selected_key
                sx, sy = self._key_to_screen(k)
                pw, ph, t_min, t_max, v_min, v_max = self._view_metrics()
                dx = pos.x() - sx
                dy = pos.y() - sy
                if abs(dx) < 1e-3:
                    dx = 1e-3 if dx >= 0 else -1e-3
                slope = -(dy / dx) * pw * (v_max - v_min) / (ph * (t_max - t_min))
                slope = max(-100.0, min(100.0, slope))
                if self._drag_tangent == "in":
                    k.in_tangent = slope
                else:
                    k.out_tangent = slope
                k.tangent_mode = TangentMode.FREE
                self.curve_changed.emit()
                self.update()
                return
            t, v = self._screen_to_value(pos.x(), pos.y())
            t = max(0.0, min(1.0, t))
            k = self._selected_key
            k.time = round(t, 4)
            k.value = round(v, 4)
            self._curve.keys.sort(key=lambda x: x.time)
            self.curve_changed.emit()
            self.update()
            return
        for k in self._curve.keys:
            if self._get_key_rect(k).contains(pos):
                self._hovered_key = k
                self.update()
                return
        self._hovered_key = None
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._panning:
                self._panning = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                if self._pan_deselect and not self._pan_moved:
                    self._selected_key = None
                self.update()
                return
            was_tangent_drag = self._drag_tangent is not None
            self._dragging = False
            self._drag_tangent = None
            if not was_tangent_drag:
                self._curve._auto_smooth()
            self.curve_changed.emit()
            self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            t, v = self._screen_to_value(event.position().x(), event.position().y())
            t = max(0.0, min(1.0, t))
            v = max(0.0, min(1.0, v))
            k = self._curve.add_key(round(t, 4), round(v, 4))
            self._selected_key = k
            self.curve_changed.emit()
            self.update()

    def wheelEvent(self, event):
        pos = event.position()
        t, v = self._screen_to_value(pos.x(), pos.y())
        m = 30
        pw = max(self.width() - m * 2, 1)
        ph = max(self.height() - m * 2, 1)
        fx = (pos.x() - m) / pw
        fy = (pos.y() - m) / ph
        factor = math.pow(1.1, event.angleDelta().y() / 120.0)
        tw = (self._view_t1 - self._view_t0) / factor
        vh = (self._view_v1 - self._view_v0) / factor
        tw = max(min(tw, 1e6), 1e-4)
        vh = max(min(vh, 1e6), 1e-4)
        self._view_t0 = t - fx * tw
        self._view_t1 = self._view_t0 + tw
        self._view_v0 = v - (1.0 - fy) * vh
        self._view_v1 = self._view_v0 + vh
        self.update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            if self._selected_key and len(self._curve.keys) > 1:
                self._curve.remove_key(self._selected_key)
                self._selected_key = None
                self.curve_changed.emit()
                self.update()
        elif event.key() == Qt.Key.Key_F:
            self.fit_view()
        elif event.key() == Qt.Key.Key_Space:
            if self._selected_key:
                k = self._selected_key
                modes = list(TangentMode)
                idx = modes.index(k.tangent_mode)
                k.tangent_mode = modes[(idx + 1) % len(modes)]
                self._curve._auto_smooth()
                self.curve_changed.emit()
                self.update()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for mode in TangentMode:
            action = menu.addAction(mode.value.capitalize())
            action.triggered.connect(lambda checked, m=mode: self._set_tangent_mode(m))
        menu.exec(event.globalPos())

    def _set_tangent_mode(self, mode: TangentMode):
        if self._selected_key:
            self._selected_key.tangent_mode = mode
            self._curve._auto_smooth()
            self.curve_changed.emit()
            self.update()
