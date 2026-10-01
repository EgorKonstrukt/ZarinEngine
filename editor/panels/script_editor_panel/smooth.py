# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, QEasingCurve


class SmoothScrollState(QObject):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._velocity = 0.0
        self._target = None
        self._anim = None
        self._scrolling = False
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(180)
        self._idle.timeout.connect(self._on_idle)
        self._tick = QTimer(self)
        self._tick.setInterval(30)
        self._tick.timeout.connect(self._on_tick)
        self._max_ahead = 30.0
        try:
            sb = self._editor.verticalScrollBar()
            sb.sliderPressed.connect(self._on_user_scroll)
            sb.sliderMoved.connect(self._on_user_scroll_value)
            sb.valueChanged.connect(self._on_value_changed)
        except Exception:
            pass

    def _on_user_scroll(self):
        try:
            self._target = None
            self._velocity = 0.0
            try:
                if self._tick.isActive():
                    self._tick.stop()
            except Exception:
                pass
            self._scrolling = True
            self._idle.start()
        except Exception:
            pass

    def _on_user_scroll_value(self, _v):
        try:
            self._target = float(_v)
            self._scrolling = True
            self._idle.start()
        except Exception:
            pass

    def _on_value_changed(self, _v):
        try:
            if not self._tick.isActive():
                self._scrolling = True
                self._idle.start()
        except Exception:
            pass

    def _on_idle(self):
        try:
            self._scrolling = False
            self._velocity = 0.0
            self._target = None
            if self._tick.isActive():
                self._tick.stop()
            try:
                self._editor._on_smooth_idle()
            except Exception:
                pass
        except Exception:
            pass

    def is_scrolling(self) -> bool:
        try:
            return self._scrolling or (self._tick.isActive())
        except Exception:
            return False

    def _clamp_target(self, sb, cur: float):
        try:
            lo = float(sb.minimum())
            hi = float(sb.maximum())
            if self._target < lo:
                self._target = lo
            if self._target > hi:
                self._target = hi
            ahead = self._target - cur
            if ahead > self._max_ahead:
                self._target = cur + self._max_ahead
            if ahead < -self._max_ahead:
                self._target = cur - self._max_ahead
            if self._target < lo:
                self._target = lo
            if self._target > hi:
                self._target = hi
        except Exception:
            pass

    def add_wheel(self, delta_y: float):
        try:
            sb = self._editor.verticalScrollBar()
        except Exception:
            return False
        try:
            lo = sb.minimum()
            hi = sb.maximum()
            if hi <= lo:
                return False
            units = delta_y / 120.0
            if units == 0:
                return True
            cur = float(sb.value())
            if self._target is None:
                self._target = cur
            self._target += (-units) * 3.0
            self._clamp_target(sb, cur)
            self._velocity = 0.0
            self._scrolling = True
            self._idle.start()
            if not self._tick.isActive():
                self._tick.start()
            return True
        except Exception:
            return False

    def add_pixels(self, pixels_y: float):
        try:
            sb = self._editor.verticalScrollBar()
        except Exception:
            return False
        try:
            lo = sb.minimum()
            hi = sb.maximum()
            if hi <= lo:
                return False
            if pixels_y == 0:
                return True
            try:
                line_h = float(self._editor._cached_line_height())
            except Exception:
                line_h = 17.0
            if line_h <= 0:
                line_h = 17.0
            cur = float(sb.value())
            if self._target is None:
                self._target = cur
            self._target += (-pixels_y) / line_h
            self._clamp_target(sb, cur)
            self._velocity = 0.0
            self._scrolling = True
            self._idle.start()
            if not self._tick.isActive():
                self._tick.start()
            return True
        except Exception:
            return False

    def _on_tick(self):
        try:
            sb = self._editor.verticalScrollBar()
        except Exception:
            try:
                self._tick.stop()
            except Exception:
                pass
            return
        try:
            if self._target is None:
                try:
                    self._tick.stop()
                except Exception:
                    pass
                return
            cur = float(sb.value())
            diff = self._target - cur
            if abs(diff) < 0.5:
                try:
                    sb.setValue(int(round(self._target)))
                except Exception:
                    pass
                self._target = None
                self._velocity = 0.0
                try:
                    self._tick.stop()
                except Exception:
                    pass
                try:
                    self._idle.start()
                except Exception:
                    pass
                return
            lo = sb.minimum()
            hi = sb.maximum()
            mag = abs(diff) * 0.34
            if mag < 1.0:
                mag = 1.0
            if mag > 3.0:
                mag = 3.0
            step = mag if diff > 0 else -mag
            nxt = cur + step
            if (diff > 0 and nxt > self._target) or (diff < 0 and nxt < self._target):
                nxt = self._target
            if nxt < float(lo):
                nxt = float(lo)
            if nxt > float(hi):
                nxt = float(hi)
            sb.setValue(int(round(nxt)))
            try:
                self._idle.start()
            except Exception:
                pass
        except Exception:
            try:
                self._tick.stop()
            except Exception:
                pass


def ease_factor() -> QEasingCurve:
    try:
        return QEasingCurve(QEasingCurve.Type.OutCubic)
    except Exception:
        return QEasingCurve()
