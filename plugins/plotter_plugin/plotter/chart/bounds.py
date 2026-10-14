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
import time
from typing import Tuple
from .constants import _AUTOFIT_DEBOUNCE_MS, _ANIM_FRAME_MS, _RAPID_THRESHOLD_S

class _ChartBoundsMixin:
    def _data_bounds(self) -> Tuple[float, float, float, float]:
        if not self._bounds_dirty:
            return self._bounds_cache
        items_main = [it for it in self._lines + self._scatters if it.xs]
        if not items_main:
            self._bounds_cache = (0.0, 1.0, 0.0, 1.0)
        else:
            x0 = min(min(it.xs) for it in items_main)
            x1 = max(max(it.xs) for it in items_main)
            y0 = min(min(it.ys) for it in items_main)
            y1 = max(max(it.ys) for it in items_main)
            for ln in self._inflines:
                if ln.visible:
                    if ln.horizontal:
                        y0 = min(y0, ln.value)
                        y1 = max(y1, ln.value)
                    else:
                        x0 = min(x0, ln.value)
                        x1 = max(x1, ln.value)
            if x0 == x1:
                x0 -= 1.0; x1 += 1.0
            if y0 == y1:
                y0 -= 1.0; y1 += 1.0
            px = (x1 - x0) * 0.05
            py = (y1 - y0) * 0.08
            self._bounds_cache = (x0 - px, x1 + px, y0 - py, y1 + py)
        items_r2 = [it for it in self._lines_r2 + self._scatters_r2 if it.xs]
        if items_r2:
            y0r = min(min(it.ys) for it in items_r2)
            y1r = max(max(it.ys) for it in items_r2)
            if y0r == y1r:
                y0r -= 1.0; y1r += 1.0
            py = (y1r - y0r) * 0.08
            self._bounds_r2_cache = (y0r - py, y1r + py)
        else:
            self._bounds_r2_cache = (0.0, 1.0)
        self._bounds_dirty = False
        return self._bounds_cache

    def _schedule_autofit(self):
        self._bounds_dirty = True
        if self._autofit_enabled:
            self._autofit_timer.start(_AUTOFIT_DEBOUNCE_MS)

    def _deferred_autofit(self):
        if self._autofit_enabled:
            self._run_autofit(animated=False)

    def autofit(self):
        self._autofit_timer.stop()
        self._bounds_dirty = True
        self._run_autofit(animated=True)

    def _run_autofit(self, animated: bool = True):
        tgt = self._data_bounds()
        self._vy0_r, self._vy1_r = self._bounds_r2_cache
        now = time.monotonic()
        rapid = (now - self._last_autofit_t) < _RAPID_THRESHOLD_S
        self._last_autofit_t = now
        if not animated or rapid:
            self._anim_timer.stop()
            self._vx0, self._vx1, self._vy0, self._vy1 = tgt
            self._canvas.update()
            return
        self._anim_start = (self._vx0, self._vx1, self._vy0, self._vy1)
        self._anim_target = tgt
        self._anim_elapsed = 0
        if self._anim_start != self._anim_target:
            self._anim_timer.start(_ANIM_FRAME_MS)
        else:
            self._vx0, self._vx1, self._vy0, self._vy1 = tgt
            self._canvas.update()

    def _step_animation(self):
        self._anim_elapsed += _ANIM_FRAME_MS
        p = min(1.0, self._anim_elapsed / self._anim_dur)
        f = self._anim_easing.valueForProgress(p)
        bounds = [s + (t - s) * f for s, t in zip(self._anim_start, self._anim_target)]
        self._vx0, self._vx1, self._vy0, self._vy1 = bounds
        self._canvas.update()
        if p >= 1.0:
            self._anim_timer.stop()
