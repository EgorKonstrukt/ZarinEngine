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

class _ChartPropsMixin:
    @property
    def vx0(self): return self._vx0
    @property
    def vx1(self): return self._vx1
    @property
    def vy0(self): return self._vy0
    @property
    def vy1(self): return self._vy1
    @property
    def vy0_r(self): return self._vy0_r
    @property
    def vy1_r(self): return self._vy1_r
    @property
    def log_x(self): return self._log_x
    @property
    def log_y(self): return self._log_y
    @property
    def font(self): return self._font
    @property
    def fits(self): return self._fits
    @property
    def lines(self): return self._lines
    @property
    def lines_r2(self): return self._lines_r2
    @property
    def scatters(self): return self._scatters
    @property
    def scatters_r2(self): return self._scatters_r2
    @property
    def inflines(self): return self._inflines
    @property
    def show_legend(self): return self._show_legend
    @property
    def label_left(self): return self._label_left
    @property
    def label_right(self): return self._label_right
    @property
    def label_bottom(self): return self._label_bottom
    @property
    def label_title(self): return self._label_title
    @property
    def title_font(self): return self._title_font
    @property
    def grid_px_x(self): return self._grid_px_x
    @property
    def grid_px_y(self): return self._grid_px_y
    @property
    def functions(self): return self._functions
    @property
    def rulers(self): return self._rulers
