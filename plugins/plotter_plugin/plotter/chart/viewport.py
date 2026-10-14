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
from .constants import _ANIM_FRAME_MS

class _ChartViewportMixin:
    def onViewportChanged(self, callback) -> None:
        if callback not in self._viewport_changed_callbacks:
            self._viewport_changed_callbacks.append(callback)

    def removeViewportChangedCallback(self, callback) -> None:
        try:
            self._viewport_changed_callbacks.remove(callback)
        except ValueError:
            pass

    def _notify_viewport_changed(self):
        vp = (self._vx0, self._vx1, self._vy0, self._vy1)
        if vp == self._last_emitted_viewport:
            return
        self._last_emitted_viewport = vp
        for cb in self._viewport_changed_callbacks:
            try:
                cb(self._vx0, self._vx1, self._vy0, self._vy1)
            except Exception:
                pass

    def _schedule_viewport_changed(self):
        if self._viewport_notify_timer.isActive():
            return
        self._viewport_notify_timer.start(0)

    def _emit_viewport_changed(self):
        self._notify_viewport_changed()

    @property
    def viewport(self):
        class _VP:
            __slots__ = ("x0", "x1", "y0", "y1")
            def __init__(self, x0, x1, y0, y1):
                self.x0, self.x1, self.y0, self.y1 = x0, x1, y0, y1
            def __repr__(self):
                return (f"Viewport(x0={self.x0}, x1={self.x1}, "
                        f"y0={self.y0}, y1={self.y1})")
        return _VP(self._vx0, self._vx1, self._vy0, self._vy1)

    def setViewport(self, x0: float, x1: float, y0: float, y1: float,
                    animated: bool = False):
        self._autofit_timer.stop()
        if animated:
            self._anim_start = (self._vx0, self._vx1, self._vy0, self._vy1)
            self._anim_target = (x0, x1, y0, y1)
            self._anim_elapsed = 0
            if self._anim_start != self._anim_target:
                self._anim_timer.start(_ANIM_FRAME_MS)
                return
        self._vx0, self._vx1, self._vy0, self._vy1 = x0, x1, y0, y1
        self._canvas.update()
