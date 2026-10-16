# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import statistics
from bisect import bisect_left
from typing import List, Optional, Tuple, TYPE_CHECKING
from PySide6.QtCore import Qt, QRect, QRectF, QPointF
from PySide6.QtGui import (QPen, QColor, QBrush, QFont, QFontMetrics,
                         QPixmap, QWheelEvent, QMouseEvent)
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu
from ..mathx import nice_ticks, nice_log_ticks, to_log, decimated, fmt, get_fit_modes
from ..itemsp import _LineItem, _FitItem, _InfLine, _FunctionItem
from ..i18n import tr

if TYPE_CHECKING:
    from ..chart import ChartWidget

_ML, _MT, _MR, _MB = 58, 14, 20, 40
_MT_TITLE = 26
_MR2 = 52
_ZOOM_FACTOR = 1.15
_ZOOM_MIN_SPAN = 1e-10
_ZOOM_MAX_SPAN = 1e15
_SNAP_RADIUS_PX = 40
_TANGENT_HALF_FRAC = 0.18
_ANALYTICS_PAD = 8
_ANALYTICS_ROW_H = 17
_ANALYTICS_MAX_SERIES = 8
_TOOLTIP_MARGIN = 14
_SNAP_DOT_R = 5.0
_LEGEND_PAD = 8
_LEGEND_SWATCH = 12
_LATEST_TAG_PAD = 3
_LATEST_TAG_ROUND = 3
_COORD_CLAMP = 1e6
_DECIMATE_THRESHOLD = 2000
_INFLINE_HIT_PX = 6
_RUBBERBAND_MIN_PX = 4
_RANGE_SEL_ALPHA = 30
_SCREEN_Y_CLAMP = 32768.0
_GRID_PRESETS_X = [
    ("chart_widget.ctx_sparse", 120),
    ("chart_widget.ctx_normal", 80),
    ("chart_widget.ctx_dense", 50),
]
_GRID_PRESETS_Y = [
    ("chart_widget.ctx_sparse", 100),
    ("chart_widget.ctx_normal", 60),
    ("chart_widget.ctx_dense", 40),
]
_ORIGIN_AXIS_ALPHA = 160
_ORIGIN_TICK_LEN = 4
_ORIGIN_TICK_STEP_PX = 60


def _fmt_axis(v: float) -> str:
    if not math.isfinite(v):
        return str(v)
    if v == 0.0:
        return "0"
    abs_v = abs(v)
    if abs_v >= 1e15:
        return f"{v:.6g}"
    if abs_v >= 1:
        if abs_v >= 1000:
            return f"{v:.0f}"
        return f"{v:.6g}"
    for digits in range(1, 10):
        s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
        if float(s) != 0.0:
            return s
    return fmt(v)


def _skewness(data: List[float]) -> Optional[float]:
    n = len(data)
    if n < 3:
        return None
    mean = statistics.mean(data)
    std = statistics.stdev(data)
    if std == 0:
        return 0.0
    return sum(((x - mean) / std) ** 3 for x in data) * n / ((n - 1) * (n - 2))


from .axes import CanvasAxesMixin
from .series import CanvasSeriesMixin


class CanvasBase(CanvasAxesMixin, CanvasSeriesMixin):
    _chart: "ChartWidget"

    def _init_base_state(self):
        self._pan_start: Optional[QPointF] = None
        self._pan_vx0 = 0.0
        self._pan_vy0 = 0.0
        self._mouse_pos: Optional[QPointF] = None
        self._show_analytics = False
        self._show_latest = False
        self._show_origin_axes = False
        self._show_dots = False
        self._show_tangent = True
        self._rb_start: Optional[QPointF] = None
        self._rb_end: Optional[QPointF] = None
        self._rb_active = False
        self._dragging_infline: Optional[_InfLine] = None
        self._zoom_lock: str = "both"
        self._range_sel_x: Optional[Tuple[float, float]] = None
        self._nearest_cache_key: Optional[tuple] = None
        self._nearest_cache_result = None
        self._dragging_ruler_pt = None
        self._snap_to_data = True
        self._crosshair_enabled = True

    def toggleAnalytics(self):
        self._show_analytics = not self._show_analytics
        self.update()

    def toggleLatestPoint(self):
        self._show_latest = not self._show_latest
        self.update()

    def toggleOriginAxes(self):
        self._show_origin_axes = not self._show_origin_axes
        self.update()

    def toggleCrosshair(self):
        self._crosshair_enabled = not self._crosshair_enabled
        self.update()

    def _set_analytics(self, v: bool):
        self._show_analytics = v
        self.update()

    def _set_latest(self, v: bool):
        self._show_latest = v
        self.update()

    def _set_origin_axes(self, v: bool):
        self._show_origin_axes = v
        self.update()

    def _set_crosshair(self, v: bool):
        self._crosshair_enabled = v
        self.update()

    def _set_show_dots(self, v: bool):
        self._show_dots = v
        self.update()

    def _set_show_tangent(self, v: bool):
        self._show_tangent = v
        self.update()

    def _set_snap_to_data(self, v: bool):
        self._snap_to_data = v
        self.update()

    def setZoomLock(self, lock: str):
        self._zoom_lock = lock

    def clearRangeSelection(self):
        self._range_sel_x = None
        self.update()

    def _has_right_axis(self) -> bool:
        return bool(self._chart.lines_r2 or self._chart.scatters_r2)

    def _plot_rect(self) -> QRect:
        ml = _ML + (4 if self._chart.label_left else 0)
        mr = (_MR2 if self._has_right_axis() else _MR) + (4 if self._chart.label_right else 0)
        mt = (_MT_TITLE if self._chart.label_title else _MT)
        return QRect(ml, mt, max(1, self.width() - ml - mr), max(1, self.height() - mt - _MB))

    def _to_pt(self, xv, yv, x0, dx, y0, dy, pr) -> QPointF:
        px = pr.left() + (xv - x0) / dx * pr.width()
        py = pr.bottom() - (yv - y0) / dy * pr.height()
        return QPointF(
            max(-_COORD_CLAMP, min(_COORD_CLAMP, px)),
            max(-_COORD_CLAMP, min(_COORD_CLAMP, py)),
        )

    def _to_pt_log(self, xv, yv, x0, dx, y0, dy, pr, log_x: bool, log_y: bool) -> QPointF:
        lx = to_log(xv) if log_x else xv
        ly = to_log(yv) if log_y else yv
        return self._to_pt(lx, ly, x0, dx, y0, dy, pr)

    def _screen_to_data(self, sx, sy, x0, dx, y0, dy, pr, log_x, log_y) -> Tuple[float, float]:
        lx = x0 + (sx - pr.left()) / pr.width() * dx
        ly = y0 + (pr.bottom() - sy) / pr.height() * dy
        xv = 10 ** lx if log_x else lx
        yv = 10 ** ly if log_y else ly
        return xv, yv

    def _view_params(self, pr):
        c = self._chart
        x0 = to_log(c.vx0) if c.log_x else c.vx0
        x1 = to_log(c.vx1) if c.log_x else c.vx1
        y0 = to_log(c.vy0) if c.log_y else c.vy0
        y1 = to_log(c.vy1) if c.log_y else c.vy1
        dx = x1 - x0 if abs(x1 - x0) > 1e-300 else 1.0
        dy = y1 - y0 if abs(y1 - y0) > 1e-300 else 1.0
        return x0, x1, y0, y1, dx, dy

    def _copy_coords_to_clipboard(self):
        from PySide6.QtWidgets import QApplication
        pr = self._plot_rect()
        if self._mouse_pos is None:
            return
        c = self._chart
        x0, x1, y0, y1, dx, dy = self._view_params(pr)
        xv, yv = self._screen_to_data(
            self._mouse_pos.x(), self._mouse_pos.y(),
            x0, dx, y0, dy, pr, c.log_x, c.log_y,
        )
        nearest = self._find_nearest(self._mouse_pos, pr, x0, dx, y0, dy)
        if nearest is not None:
            xv, yv = nearest[0], nearest[1]
        QApplication.clipboard().setText(f"{fmt(xv)}\t{fmt(yv)}")

    def _add_ruler_at_view_center(self):
        c = self._chart
        cx = (c.vx0 + c.vx1) / 2.0
        cy = (c.vy0 + c.vy1) / 2.0
        qx = (c.vx1 - c.vx0) * 0.15
        qy = (c.vy1 - c.vy0) * 0.15
        ruler = c.addRuler(cx - qx, cy - qy, cx + qx, cy + qy)
        ruler.setVisible(True)

    def _clear_all_rulers(self):
        c = self._chart
        for ruler in list(c.rulers):
            c.removeItem(ruler)

    def wheelEvent(self, ev: QWheelEvent):
        pr = self._plot_rect()
        pos = ev.position().toPoint()
        if not pr.contains(pos):
            return
        c = self._chart
        x0, x1, y0, y1, dx, dy = self._view_params(pr)
        cx_log = x0 + (pos.x() - pr.left()) / pr.width() * dx
        cy_log = y0 + (pr.bottom() - pos.y()) / pr.height() * dy
        factor = 1.0 / _ZOOM_FACTOR if ev.angleDelta().y() > 0 else _ZOOM_FACTOR
        if self._zoom_lock in ("both", "x"):
            nvx0 = cx_log + (x0 - cx_log) * factor
            nvx1 = cx_log + (x1 - cx_log) * factor
            sx = abs(nvx1 - nvx0)
            if math.isfinite(sx) and _ZOOM_MIN_SPAN <= sx <= _ZOOM_MAX_SPAN:
                c._vx0 = 10 ** nvx0 if c.log_x else nvx0
                c._vx1 = 10 ** nvx1 if c.log_x else nvx1
        if self._zoom_lock in ("both", "y"):
            nvy0 = cy_log + (y0 - cy_log) * factor
            nvy1 = cy_log + (y1 - cy_log) * factor
            sy = abs(nvy1 - nvy0)
            if math.isfinite(sy) and _ZOOM_MIN_SPAN <= sy <= _ZOOM_MAX_SPAN:
                c._vy0 = 10 ** nvy0 if c.log_y else nvy0
                c._vy1 = 10 ** nvy1 if c.log_y else nvy1
        self.update()
        ev.accept()

    def mousePressEvent(self, ev: QMouseEvent):
        pr = self._plot_rect()
        c = self._chart
        x0, x1, y0, y1, dx, dy = self._view_params(pr)
        if ev.button() == Qt.MouseButton.LeftButton:
            hit_ruler = self._find_ruler_handle_at(ev.position(), pr, x0, dx, y0, dy)
            if hit_ruler:
                self._dragging_ruler_pt = hit_ruler
                self.setCursor(Qt.CursorShape.CrossCursor)
                ev.accept()
                return
            hit_infline = self._find_infline_at(ev.position(), pr, x0, dx, y0, dy)
            if hit_infline:
                self._dragging_infline = hit_infline
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                ev.accept()
                return
            hit_scatter = self._find_scatter_point_at(ev.position(), pr, x0, dx, y0, dy)
            if hit_scatter:
                item, idx = hit_scatter
                item.selectPoint(idx)
                item.point_clicked.emit(item.xs[idx], item.ys[idx], idx)
                ev.accept()
                return
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._rb_start = ev.position()
                self._rb_end = ev.position()
                self._rb_active = True
                ev.accept()
                return
            self._pan_start = ev.position()
            self._pan_vx0 = c.vx0
            self._pan_vy0 = c.vy0
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            ev.accept()
        elif ev.button() == Qt.MouseButton.RightButton:
            ev.accept()
        elif ev.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = ev.position()
            self._pan_vx0 = c.vx0
            self._pan_vy0 = c.vy0
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent):
        pr = self._plot_rect()
        pos = ev.position()
        self._mouse_pos = pos if pr.contains(pos.toPoint()) else None
        c = self._chart
        if self._dragging_ruler_pt is not None:
            x0, x1, y0, y1, dx, dy = self._view_params(pr)
            ruler, pt_idx = self._dragging_ruler_pt
            xv, yv = self._screen_to_data(pos.x(), pos.y(), x0, dx, y0, dy, pr, c.log_x, c.log_y)
            if pt_idx == 0:
                ruler.x0, ruler.y0 = xv, yv
            else:
                ruler.x1, ruler.y1 = xv, yv
            if ruler.changed is not None:
                ruler.changed()
            self.update()
            return
        if self._dragging_infline is not None:
            x0, x1, y0, y1, dx, dy = self._view_params(pr)
            ln = self._dragging_infline
            if ln.horizontal:
                ly = y0 + (pr.bottom() - pos.y()) / pr.height() * dy
                ln.value = 10 ** ly if c.log_y else ly
            else:
                lx = x0 + (pos.x() - pr.left()) / pr.width() * dx
                ln.value = 10 ** lx if c.log_x else lx
            self._nearest_cache_key = None
            self.update()
            return
        if self._rb_active and self._rb_start is not None:
            self._rb_end = pos
            self.update()
            return
        if self._pan_start is not None:
            x0, x1, y0, y1, dx, dy = self._view_params(pr)
            ddx = (pos.x() - self._pan_start.x()) / pr.width() * dx
            ddy = (pos.y() - self._pan_start.y()) / pr.height() * dy
            new_vx0 = (to_log(self._pan_vx0) if c.log_x else self._pan_vx0) - ddx
            new_vy0 = (to_log(self._pan_vy0) if c.log_y else self._pan_vy0) + ddy
            if c.log_x:
                c._vx0 = 10 ** new_vx0
                c._vx1 = 10 ** (new_vx0 + dx)
            else:
                c._vx0 = new_vx0
                c._vx1 = new_vx0 + dx
            if c.log_y:
                c._vy0 = 10 ** new_vy0
                c._vy1 = 10 ** (new_vy0 + dy)
            else:
                c._vy0 = new_vy0
                c._vy1 = new_vy0 + dy
            self._nearest_cache_key = None
            self.update()
            return
        if pr.contains(pos.toPoint()):
            x0, x1, y0, y1, dx, dy = self._view_params(pr)
            ln = self._find_infline_at(pos, pr, x0, dx, y0, dy)
            if ln:
                self.setCursor(Qt.CursorShape.SizeAllCursor if ln.horizontal else Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if self._dragging_ruler_pt is not None:
            self._dragging_ruler_pt = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            ev.accept()
            return
        if self._dragging_infline is not None:
            self._dragging_infline = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            ev.accept()
            return
        if self._rb_active and self._rb_start and self._rb_end:
            rb = QRectF(self._rb_start, self._rb_end).normalized()
            if rb.width() >= _RUBBERBAND_MIN_PX and rb.height() >= _RUBBERBAND_MIN_PX:
                pr = self._plot_rect()
                x0, x1, y0, y1, dx, dy = self._view_params(pr)
                c = self._chart
                x_lo_v, _ = self._screen_to_data(rb.left(), rb.top(), x0, dx, y0, dy, pr, c.log_x, c.log_y)
                x_hi_v, _ = self._screen_to_data(rb.right(), rb.bottom(), x0, dx, y0, dy, pr, c.log_x, c.log_y)
                _, y_hi_v = self._screen_to_data(rb.left(), rb.top(), x0, dx, y0, dy, pr, c.log_x, c.log_y)
                _, y_lo_v = self._screen_to_data(rb.left(), rb.bottom(), x0, dx, y0, dy, pr, c.log_x, c.log_y)
                c._vx0, c._vx1 = min(x_lo_v, x_hi_v), max(x_lo_v, x_hi_v)
                c._vy0, c._vy1 = min(y_lo_v, y_hi_v), max(y_lo_v, y_hi_v)
            self._rb_active = False
            self._rb_start = None
            self._rb_end = None
            self.update()
            ev.accept()
            return
        self._pan_start = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, ev: QMouseEvent):
        pr = self._plot_rect()
        pos = ev.position().toPoint()
        if ev.button() == Qt.MouseButton.LeftButton and pr.contains(pos):
            c = self._chart
            x0, x1, y0, y1, dx, dy = self._view_params(pr)
            xv, _ = self._screen_to_data(pos.x(), pos.y(), x0, dx, y0, dy, pr, c.log_x, c.log_y)
            if self._range_sel_x is None:
                self._range_sel_x = (xv, xv)
            else:
                lo, hi = self._range_sel_x
                if abs(xv - lo) < abs(xv - hi):
                    self._range_sel_x = (xv, hi)
                else:
                    self._range_sel_x = (lo, xv)
            self.update()
        else:
            self._chart.autofit()

    def leaveEvent(self, ev):
        self._mouse_pos = None
        self.update()

    def grab_image(self) -> QPixmap:
        return self.grab()
