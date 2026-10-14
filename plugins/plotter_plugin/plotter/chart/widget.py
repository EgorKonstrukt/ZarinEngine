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
from typing import List, Optional, Tuple
from PyQt6.QtWidgets import QWidget, QSizePolicy, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import QTimer, QEasingCurve
from PyQt6.QtGui import QFont
from ..canvas_backend import make_canvas as _make_canvas
from ..itemsp import _LineItem, _ScatterItem, _FitItem, _InfLine, _FunctionItem, _RulerItem
from ..sidebar import SidebarLabel
from .toolbar import _ChartToolbarMixin
from .display import _ChartDisplayMixin
from .series import _ChartSeriesMixin
from .viewport import _ChartViewportMixin
from .bounds import _ChartBoundsMixin
from .export import _ChartExportMixin
from .props import _ChartPropsMixin

class ChartWidget(_ChartToolbarMixin, _ChartDisplayMixin, _ChartSeriesMixin, _ChartViewportMixin, _ChartBoundsMixin, _ChartExportMixin, _ChartPropsMixin, QWidget):
    def __init__(self, parent=None, *,
                 show_toolbar: bool = True,
                 show_legend: bool = False,
                 show_sidebar: bool = False,
                 font: Optional[QFont] = None,
                 anim_duration: int = 450,
                 anim_easing: QEasingCurve.Type = QEasingCurve.Type.OutQuint,
                 threaded_fit: bool = False,
                 grid_px_x: int = 80,
                 grid_px_y: int = 60,
                 origin_axes: bool = False,):
        super().__init__(parent)
        self._lines: List[_LineItem] = []
        self._scatters: List[_ScatterItem] = []
        self._lines_r2: List[_LineItem] = []
        self._scatters_r2: List[_ScatterItem] = []
        self._fits: List[_FitItem] = []
        self._inflines: List[_InfLine] = []
        self._functions: List[_FunctionItem] = []
        self._rulers: List[_RulerItem] = []
        self._viewport_changed_callbacks = []
        self._last_emitted_viewport: Optional[tuple] = None
        self._label_left = ""
        self._label_right = ""
        self._label_bottom = ""
        self._label_title = ""
        self._title_font: Optional[QFont] = None
        self._font = font or QFont("Arial", 8)
        self._vx0 = 0.0; self._vx1 = 1.0
        self._vy0 = 0.0; self._vy1 = 1.0
        self._vy0_r = 0.0; self._vy1_r = 1.0
        self._log_x = False
        self._log_y = False
        self._show_legend = show_legend
        self._active_fit_key: Optional[str] = None
        self._autofit_enabled = True
        self._threaded_fit = threaded_fit
        self._grid_px_x = max(20, grid_px_x)
        self._grid_px_y = max(20, grid_px_y)
        self._bounds_dirty = True
        self._bounds_cache: Tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0)
        self._bounds_r2_cache: Tuple[float, float] = (0.0, 1.0)
        self._last_autofit_t = 0.0
        self._canvas = _make_canvas(self)
        if self._canvas is None:
            raise RuntimeError(
                "make_canvas() returned None - check that plugins/plotter_plugin/plotter/canvas.py "
                "exists and that _PlotCanvas can be imported from it."
            )
        self._canvas._show_origin_axes = origin_axes
        self._toolbar_layout = self._build_toolbar()
        self._toolbar_widget = QWidget(self)
        self._toolbar_widget.setLayout(self._toolbar_layout)
        self._sidebar = SidebarLabel(self) if show_sidebar else None
        self._toolbar_widget.setVisible(show_toolbar)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._step_animation)
        self._anim_dur = anim_duration
        self._anim_easing = QEasingCurve(anim_easing)
        self._anim_start: Optional[Tuple] = None
        self._anim_target: Optional[Tuple] = None
        self._anim_elapsed = 0
        self._viewport_notify_timer = QTimer(self)
        self._viewport_notify_timer.setSingleShot(True)
        self._viewport_notify_timer.timeout.connect(self._emit_viewport_changed)
        self._autofit_timer = QTimer(self)
        self._autofit_timer.setSingleShot(True)
        self._autofit_timer.timeout.connect(self._deferred_autofit)
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        if self._sidebar:
            content.addWidget(self._sidebar)
        content.addWidget(self._canvas, 1)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._toolbar_widget)
        root.addLayout(content, 1)
        self.setMinimumSize(200, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
