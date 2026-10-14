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
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from ..itemsp import _LineItem, _ScatterItem, _FitItem, _InfLine, _FunctionItem, _RulerItem
from ..palette import next_line_color, next_scatter_color
from .constants import _AnyItem

class _ChartSeriesMixin:
    def plot(self, color: Optional[str] = None, width: int = 2,
             label: str = "", dashed: bool = False,
             right_axis: bool = False) -> _LineItem:
        c = color or next_line_color()
        pen = QPen(QColor(c), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        item = _LineItem(self, pen, label)
        if right_axis:
            self._lines_r2.append(item)
        else:
            self._lines.append(item)
        return item

    def addScatter(self, size: int = 10, color: Optional[str] = None,
                   label: str = "", right_axis: bool = False) -> _ScatterItem:
        c = color or next_scatter_color()
        item = _ScatterItem(self, size, QColor(c), label)
        if right_axis:
            self._scatters_r2.append(item)
        else:
            self._scatters.append(item)
        return item

    def addFit(self, source: _AnyItem, mode_key: Optional[str] = None,
               color: Optional[str] = None, width: int = 2,
               dashed: bool = True, label: str = "",
               show_formula: bool = False) -> _FitItem:
        key = mode_key or self._active_fit_key or "linear"
        c = color or next_line_color()
        pen = QPen(QColor(c), width,
                   Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        fit = _FitItem(self, source, key, pen, label)
        fit.show_formula = show_formula
        self._fits.append(fit)
        if self._active_fit_key is None:
            self._active_fit_key = key
            self._update_fit_mode_label()
        self._canvas.update()
        return fit

    def addLine(self, y: Optional[float] = None, x: Optional[float] = None,
                color: str = chr(35) + "f39c12", width: int = 1,
                dashed: bool = True) -> _InfLine:
        horiz = y is not None
        val = y if horiz else (x if x is not None else 0.0)
        pen = QPen(QColor(color), width,
                   Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        ln = _InfLine(self, horiz, val, pen)
        self._inflines.append(ln)
        return ln

    def addFunction(self, fn, color: Optional[str] = None, width: int = 2,
                    dashed: bool = False, label: str = "",
                    resolution: float = 1.5) -> _FunctionItem:
        c = color or next_line_color()
        pen = QPen(QColor(c), width,
                   Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        item = _FunctionItem(self, fn, pen, label, resolution)
        self._functions.append(item)
        self._canvas.update()
        return item

    def addRuler(self, x0: float = 0.0, y0: float = 0.0,
                 x1: float = 1.0, y1: float = 1.0,
                 color: str = chr(35) + "e74c3c", width: int = 2,
                 handle_radius: int = 6) -> _RulerItem:
        pen = QPen(QColor(color), width)
        ruler = _RulerItem(self, pen, handle_radius)
        ruler.x0, ruler.y0, ruler.x1, ruler.y1 = x0, y0, x1, y1
        self._rulers.append(ruler)
        return ruler

    def removeItem(self, item):
        for lst in (self._lines, self._scatters, self._fits, self._inflines,
                    self._lines_r2, self._scatters_r2,
                    self._functions, self._rulers):
            if item in lst:
                lst.remove(item)
        self._bounds_dirty = True
        self._canvas.update()

    def clearAll(self):
        self._lines.clear()
        self._scatters.clear()
        self._fits.clear()
        self._inflines.clear()
        self._lines_r2.clear()
        self._scatters_r2.clear()
        self._functions.clear()
        self._rulers.clear()
        self._bounds_dirty = True
        self._canvas.update()
