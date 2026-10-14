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
from PyQt6.QtGui import QFont
from ..sidebar import SidebarLabel

class _ChartDisplayMixin:
    def setToolbarVisible(self, visible: bool):
        self._toolbar_widget.setVisible(visible)

    def setSidebarVisible(self, visible: bool):
        if self._sidebar:
            self._sidebar.setVisible(visible)

    def sidebar(self) -> Optional[SidebarLabel]:
        return self._sidebar

    def setLabel(self, side: str, text: str):
        if side == "left": self._label_left = text
        elif side == "bottom": self._label_bottom = text
        elif side == "right": self._label_right = text
        self._canvas.update()

    def setTitle(self, text: str, font: Optional[QFont] = None):
        self._label_title = text
        self._title_font = font
        self._canvas.update()

    def setFont(self, font: QFont):
        self._font = font
        self._canvas.update()

    def setLegendVisible(self, visible: bool):
        self._show_legend = visible
        self._canvas.update()

    def setAutofitEnabled(self, enabled: bool):
        self._autofit_enabled = enabled

    def setLatestPointVisible(self, visible: bool):
        self._canvas._show_latest = visible
        self._canvas.update()

    def setOriginAxesVisible(self, visible: bool):
        self._canvas._show_origin_axes = visible
        self._canvas.update()

    def setCrosshairVisible(self, visible: bool):
        self._canvas._crosshair_enabled = visible
        self._canvas.update()

    def setThreadedFit(self, threaded: bool):
        self._threaded_fit = threaded

    def setGridDensity(self, px_x: int, px_y: int):
        self._grid_px_x = max(20, px_x)
        self._grid_px_y = max(20, px_y)
        self._canvas.update()

    def setLogScale(self, x: Optional[bool] = None, y: Optional[bool] = None):
        if x is not None:
            self._log_x = x
        if y is not None:
            self._log_y = y
        self._canvas.update()

    def setZoomLock(self, lock: str):
        self._canvas.setZoomLock(lock)

    def setRangeSelection(self, x_lo: float, x_hi: float):
        self._canvas._range_sel_x = (x_lo, x_hi)
        self._canvas.update()

    def clearRangeSelection(self):
        self._canvas.clearRangeSelection()

    def setSnapToData(self, enabled: bool):
        self._canvas._snap_to_data = enabled
        self._canvas.update()

    def setShowDataDots(self, enabled: bool):
        self._canvas._show_dots = enabled
        self._canvas.update()

    def setShowTangent(self, enabled: bool):
        self._canvas._show_tangent = enabled
        self._canvas.update()

    def update(self):
        self._canvas.update()
        super().update()
