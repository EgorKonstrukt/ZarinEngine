# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from typing import TYPE_CHECKING
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QPainterPath
from ..canvasb import CanvasBase, _COORD_CLAMP, _SCREEN_Y_CLAMP, _TANGENT_HALF_FRAC
from ..mathx import to_log
from .paint import _CanvasPaintMixin

if TYPE_CHECKING:
    from ..chart import ChartWidget

try:
    import numpy as _np
    _NP_CANVAS = True
except ImportError:
    _NP_CANVAS = False

_SENTINEL = 1e308


def _build_fn_path_fast(fn_xs, fn_ys,
                        x0: float, dx: float, y0: float, dy: float,
                        pr_left: float, pr_bottom: float,
                        pr_width: float, pr_height: float) -> QPainterPath:
    path = QPainterPath()
    n = len(fn_xs)
    if n < 2:
        return path
    if _NP_CANVAS:
        xs_arr = _np.asarray(fn_xs, dtype=_np.float64)
        none_mask = _np.array([v is None for v in fn_ys], dtype=bool)
        ys_raw = _np.array([0.0 if v is None else v for v in fn_ys], dtype=_np.float64)
        px_arr = pr_left + (xs_arr - x0) / dx * pr_width
        py_arr = pr_bottom - (ys_raw - y0) / dy * pr_height
        _np.clip(px_arr, -_COORD_CLAMP, _COORD_CLAMP, out=px_arr)
        _np.clip(py_arr, -_SCREEN_Y_CLAMP, _SCREEN_Y_CLAMP, out=py_arr)
        path.reserve(n + 4)
        started = False
        for i in range(n):
            if none_mask[i]:
                started = False
            else:
                if not started:
                    path.moveTo(float(px_arr[i]), float(py_arr[i]))
                    started = True
                else:
                    path.lineTo(float(px_arr[i]), float(py_arr[i]))
        return path
    started = False
    for xi, yi in zip(fn_xs, fn_ys):
        if yi is None:
            started = False
            continue
        px = pr_left + (xi - x0) / dx * pr_width
        py = pr_bottom - (yi - y0) / dy * pr_height
        if not started:
            path.moveTo(px, py)
            started = True
        else:
            path.lineTo(px, py)
    return path


class _PlotCanvas(_CanvasPaintMixin, CanvasBase, QWidget):
    def __init__(self, chart: "ChartWidget"):
        QWidget.__init__(self, chart)
        self._chart = chart
        self._init_base_state()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def contextMenuEvent(self, ev):
        self._build_context_menu().exec(ev.globalPos())

    def _make_step_pts(self, xs, ys, x0, dx, y0, dy, pr, log_x, log_y):
        pts = []
        for i in range(len(xs)):
            pts.append(self._to_pt_log(xs[i], ys[i], x0, dx, y0, dy, pr, log_x, log_y))
            if i < len(xs) - 1:
                pts.append(self._to_pt_log(xs[i + 1], ys[i], x0, dx, y0, dy, pr, log_x, log_y))
        return pts

    def _paint_crosshair(self, p, pr, x0, dx, y0, dy, fg, bg, fm):
        mp = self._mouse_pos
        c = self._chart
        nearest = self._find_nearest(mp, pr, x0, dx, y0, dy)
        if nearest is None:
            ch_col = QColor(fg); ch_col.setAlpha(80)
            p.setPen(QPen(ch_col, 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(int(mp.x()), pr.top(), int(mp.x()), pr.bottom())
            p.drawLine(pr.left(), int(mp.y()), pr.right(), int(mp.y()))
            xv, yv = self._screen_to_data(mp.x(), mp.y(), x0, dx, y0, dy, pr, c.log_x, c.log_y)
            self._paint_crosshair_axis_labels(p, pr, xv, yv, mp, fm, fg, bg)
            return
        xi, yi, _, item = nearest
        snap = self._to_pt_log(xi, yi, x0, dx, y0, dy, pr, c.log_x, c.log_y)
        self._paint_crosshair_lines(p, pr, snap, fg)
        self._paint_snap_dot(p, snap, fg)
        if self._show_tangent:
            slope = self._tangent_slope(item, xi)
            if slope is not None:
                half = (c.vx1 - c.vx0) * _TANGENT_HALF_FRAC
                tp0 = self._to_pt_log(xi - half, yi - slope * half, x0, dx, y0, dy, pr, c.log_x, c.log_y)
                tp1 = self._to_pt_log(xi + half, yi + slope * half, x0, dx, y0, dy, pr, c.log_x, c.log_y)
                tg_col = QColor(fg); tg_col.setAlpha(140)
                p.setPen(QPen(tg_col, 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawLine(tp0, tp1)
        self._paint_tooltip(p, pr, xi, yi, snap, fg, bg, fm, item)
        self._paint_crosshair_axis_labels(p, pr, xi, yi, snap, fm, fg, bg)
