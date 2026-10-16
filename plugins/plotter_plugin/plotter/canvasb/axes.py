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
from .canvas import _GRID_PRESETS_X, _GRID_PRESETS_Y, _ORIGIN_AXIS_ALPHA, _ORIGIN_TICK_LEN, _SNAP_DOT_R, _TOOLTIP_MARGIN, _TANGENT_HALF_FRAC, _LATEST_TAG_PAD, _LATEST_TAG_ROUND, _fmt_axis


class CanvasAxesMixin:
    def _paint_origin_axes(self, p, pr, x0, dx, y0, dy, fg):
        c = self._chart
        log_x, log_y = c.log_x, c.log_y
        fm = QFontMetrics(c.font)
        axis_col = QColor(fg)
        axis_col.setAlpha(_ORIGIN_AXIS_ALPHA)
        tick_col = QColor(fg)
        tick_col.setAlpha(120)
        lbl_col = QColor(fg)
        lbl_col.setAlpha(180)
        p.save()
        p.setClipRect(pr)
        origin_x_screen = pr.left() + (0.0 - x0) / dx * pr.width() if not log_x else None
        origin_y_screen = pr.bottom() - (0.0 - y0) / dy * pr.height() if not log_y else None
        if origin_x_screen is not None and pr.left() <= origin_x_screen <= pr.right():
            sx = int(origin_x_screen)
            p.setPen(QPen(axis_col, 1.5))
            p.drawLine(sx, pr.top(), sx, pr.bottom())
            n_y = max(2, pr.height() // max(1, c.grid_px_y))
            yt = nice_ticks(y0, y0 + dy, n_y) if not log_y else nice_log_ticks(10 ** y0, 10 ** (y0 + dy))
            p.setPen(QPen(tick_col, 1))
            p.setFont(c.font)
            for tv in yt:
                ty_log = to_log(tv) if log_y else tv
                sy = int(pr.bottom() - (ty_log - y0) / dy * pr.height())
                if pr.top() <= sy <= pr.bottom() and abs(tv) > 1e-12:
                    p.drawLine(sx - _ORIGIN_TICK_LEN, sy, sx + _ORIGIN_TICK_LEN, sy)
                    lbl = _fmt_axis(tv)
                    lw = fm.horizontalAdvance(lbl)
                    lx_pos = sx + _ORIGIN_TICK_LEN + 2
                    if lx_pos + lw > pr.right():
                        lx_pos = sx - lw - _ORIGIN_TICK_LEN - 2
                    p.setPen(lbl_col)
                    p.drawText(lx_pos, sy + fm.ascent() // 2, lbl)
                    p.setPen(QPen(tick_col, 1))
            p.setPen(lbl_col)
            lbl_y = tr("chart_widget.origin_y_label")
            p.drawText(sx + 4, pr.top() + fm.height(), lbl_y)
        if origin_y_screen is not None and pr.top() <= origin_y_screen <= pr.bottom():
            sy = int(origin_y_screen)
            p.setPen(QPen(axis_col, 1.5))
            p.drawLine(pr.left(), sy, pr.right(), sy)
            n_x = max(2, pr.width() // max(1, c.grid_px_x))
            xt = nice_ticks(x0, x0 + dx, n_x) if not log_x else nice_log_ticks(10 ** x0, 10 ** (x0 + dx))
            p.setPen(QPen(tick_col, 1))
            p.setFont(c.font)
            for tv in xt:
                tx_log = to_log(tv) if log_x else tv
                sx_t = int(pr.left() + (tx_log - x0) / dx * pr.width())
                if pr.left() <= sx_t <= pr.right() and abs(tv) > 1e-12:
                    p.drawLine(sx_t, sy - _ORIGIN_TICK_LEN, sx_t, sy + _ORIGIN_TICK_LEN)
                    lbl = _fmt_axis(tv)
                    lw = fm.horizontalAdvance(lbl)
                    ly_pos = sy + fm.height() + 2
                    if ly_pos + fm.height() > pr.bottom():
                        ly_pos = sy - 4
                    p.setPen(lbl_col)
                    p.drawText(sx_t - lw // 2, ly_pos, lbl)
                    p.setPen(QPen(tick_col, 1))
            p.setPen(lbl_col)
            lbl_x = tr("chart_widget.origin_x_label")
            p.drawText(pr.right() - fm.horizontalAdvance(lbl_x) - 4, sy - 4, lbl_x)
        if (origin_x_screen is not None and pr.left() <= origin_x_screen <= pr.right() and
                origin_y_screen is not None and pr.top() <= origin_y_screen <= pr.bottom()):
            dot_col = QColor(fg)
            dot_col.setAlpha(200)
            p.setPen(QPen(dot_col, 1))
            p.setBrush(QBrush(dot_col))
            p.drawEllipse(QPointF(origin_x_screen, origin_y_screen), 3.0, 3.0)
        p.restore()

    def _paint_crosshair_lines(self, p, pr, snap, fg):
        ch_col = QColor(fg)
        ch_col.setAlpha(80)
        p.setPen(QPen(ch_col, 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(int(snap.x()), pr.top(), int(snap.x()), pr.bottom())
        p.drawLine(pr.left(), int(snap.y()), pr.right(), int(snap.y()))

    def _paint_snap_dot(self, p, snap, fg):
        dot_col = QColor(fg)
        dot_col.setAlpha(220)
        p.setPen(QPen(dot_col, 1))
        p.setBrush(QBrush(dot_col))
        p.drawEllipse(snap, _SNAP_DOT_R, _SNAP_DOT_R)

    def _paint_crosshair_axis_labels(self, p, pr, xi, yi, snap, fm, fg, bg):
        pad = 4
        th = fm.height() + pad
        rnd = 3
        bg_ = QColor(bg)
        bg_.setAlpha(215)
        br_ = QColor(fg)
        br_.setAlpha(100)
        lbl_col = QColor(fg)
        lbl_col.setAlpha(220)
        x_lbl = _fmt_axis(xi)
        xlw = fm.horizontalAdvance(x_lbl)
        x_tw = xlw + pad * 2
        xtx = int(snap.x()) - x_tw // 2
        xty = pr.bottom() + 2
        if pr.left() <= snap.x() <= pr.right():
            p.setBrush(QBrush(bg_))
            p.setPen(QPen(br_, 1))
            p.drawRoundedRect(xtx, xty, x_tw, th, rnd, rnd)
            p.setPen(lbl_col)
            p.drawText(xtx + pad, xty + fm.ascent() + pad // 2, x_lbl)
        y_lbl = _fmt_axis(yi)
        ylw = fm.horizontalAdvance(y_lbl)
        y_tw = ylw + pad * 2
        ytx = pr.left() - y_tw - 4
        yty = int(snap.y()) - th // 2
        if pr.top() <= snap.y() <= pr.bottom():
            p.setBrush(QBrush(bg_))
            p.setPen(QPen(br_, 1))
            p.drawRoundedRect(ytx, yty, y_tw, th, rnd, rnd)
            p.setPen(lbl_col)
            p.drawText(ytx + pad, yty + fm.ascent() + pad // 2, y_lbl)

    def _paint_crosshair_overlay(self, p, pr, x0, dx, y0, dy, fm, fg, bg):
        mp = self._mouse_pos
        c = self._chart
        nearest = self._find_nearest(mp, pr, x0, dx, y0, dy)
        if nearest is None:
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
                tg_col = QColor(fg)
                tg_col.setAlpha(140)
                p.setPen(QPen(tg_col, 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawLine(tp0, tp1)
        self._paint_tooltip(p, pr, xi, yi, snap, fg, bg, fm, item)
        self._paint_crosshair_axis_labels(p, pr, xi, yi, snap, fm, fg, bg)

    def _paint_tooltip(self, p, pr, xi, yi, snap, fg, bg, fm, item=None):
        p.setFont(self._chart.font)
        slope = None
        if self._show_tangent and item is not None:
            slope = self._tangent_slope(item, xi)
        series_lbl = ""
        if item is not None and hasattr(item, "label") and item.label:
            series_lbl = item.label
        lx = f"{tr('chart_widget.tooltip_x')}: {fmt(xi)}"
        ly = f"{tr('chart_widget.tooltip_y')}: {fmt(yi)}"
        lines = [lx, ly]
        if slope is not None:
            lines.append(f"{tr('chart_widget.tooltip_slope')}: {fmt(slope)}")
        if series_lbl:
            lines.insert(0, series_lbl)
        tw = max(fm.horizontalAdvance(l) for l in lines) + 16
        th = fm.height() * len(lines) + 12
        tx = int(snap.x()) + _TOOLTIP_MARGIN
        ty = int(snap.y()) - th - 4
        if tx + tw > pr.right():
            tx = int(snap.x()) - tw - _TOOLTIP_MARGIN
        if ty < pr.top():
            ty = int(snap.y()) + 8
        bg_ = QColor(bg)
        bg_.setAlpha(215)
        br_ = QColor(fg)
        br_.setAlpha(100)
        p.setBrush(QBrush(bg_))
        p.setPen(QPen(br_, 1))
        p.drawRoundedRect(tx, ty, tw, th, 4, 4)
        p.setPen(fg)
        for i, line in enumerate(lines):
            p.drawText(tx + 8, ty + fm.ascent() + 4 + i * fm.height(), line)

    def _paint_latest_points(self, p, pr, x0, dx, y0, dy, fm):
        from ..palette import contrast_color
        c = self._chart
        entries = []
        for it in c.lines:
            if it.visible and it.xs:
                entries.append((it.xs[-1], it.ys[-1], it.pen.color()))
        for it in c.scatters:
            if it.visible and it.xs:
                entries.append((it.xs[-1], it.ys[-1], it.color))
        p.setFont(c.font)
        pad = _LATEST_TAG_PAD
        rnd = _LATEST_TAG_ROUND
        th = fm.height()
        p.save()
        p.setClipRect(pr)
        log_x, log_y = c.log_x, c.log_y
        for xi, yi, color in entries:
            lx = to_log(xi) if log_x else xi
            ly = to_log(yi) if log_y else yi
            sx = pr.left() + (lx - x0) / dx * pr.width()
            sy = pr.bottom() - (ly - y0) / dy * pr.height()
            line_col = QColor(color)
            line_col.setAlpha(180)
            p.setPen(QPen(line_col, 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if pr.top() <= sy <= pr.bottom():
                p.drawLine(int(sx), int(sy), int(sx), pr.bottom())
            if pr.left() <= sx <= pr.right():
                p.drawLine(pr.left(), int(sy), int(sx), int(sy))
        p.restore()
        for xi, yi, color in entries:
            lx = to_log(xi) if log_x else xi
            ly = to_log(yi) if log_y else yi
            sx = pr.left() + (lx - x0) / dx * pr.width()
            sy = pr.bottom() - (ly - y0) / dy * pr.height()
            txt_col = contrast_color(color)
            x_lbl = _fmt_axis(xi)
            xlw = fm.horizontalAdvance(x_lbl)
            x_tw = xlw + pad * 2
            xtx = int(sx) - x_tw // 2
            xty = pr.bottom() + 2
            if pr.left() - x_tw <= sx <= pr.right() + x_tw:
                p.setBrush(QBrush(color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(xtx, xty, x_tw, th, rnd, rnd)
                p.setPen(txt_col)
                p.drawText(xtx + pad, xty + fm.ascent(), x_lbl)
            y_lbl = _fmt_axis(yi)
            ylw = fm.horizontalAdvance(y_lbl)
            y_tw = ylw + pad * 2
            ytx = pr.left() - y_tw - 4
            yty = int(sy) - th // 2
            if pr.top() - th <= sy <= pr.bottom() + th:
                p.setBrush(QBrush(color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(ytx, yty, y_tw, th, rnd, rnd)
                p.setPen(txt_col)
                p.drawText(ytx + pad, yty + fm.ascent(), y_lbl)

    def _build_context_menu(self) -> QMenu:
        c = self._chart
        menu = QMenu(self)

        act_autofit = QAction(tr("chart_widget.btn_autofit_toggle"), menu)
        act_autofit.setCheckable(True)
        act_autofit.setChecked(c._autofit_enabled)
        act_autofit.triggered.connect(c.setAutofitEnabled)
        menu.addAction(act_autofit)

        act_latest = QAction(tr("chart_widget.btn_latest"), menu)
        act_latest.setCheckable(True)
        act_latest.setChecked(self._show_latest)
        act_latest.triggered.connect(self._set_latest)
        menu.addAction(act_latest)

        act_analytics = QAction(tr("chart_widget.btn_analytics"), menu)
        act_analytics.setCheckable(True)
        act_analytics.setChecked(self._show_analytics)
        act_analytics.triggered.connect(self._set_analytics)
        menu.addAction(act_analytics)

        act_legend = QAction(tr("chart_widget.ctx_legend"), menu)
        act_legend.setCheckable(True)
        act_legend.setChecked(c.show_legend)
        act_legend.triggered.connect(c.setLegendVisible)
        menu.addAction(act_legend)

        menu.addSeparator()

        display_menu = menu.addMenu(tr("chart_widget.ctx_display"))

        act_origin = QAction(tr("chart_widget.ctx_origin_axes"), display_menu)
        act_origin.setCheckable(True)
        act_origin.setChecked(self._show_origin_axes)
        act_origin.triggered.connect(self._set_origin_axes)
        display_menu.addAction(act_origin)

        act_crosshair = QAction(tr("chart_widget.ctx_crosshair"), display_menu)
        act_crosshair.setCheckable(True)
        act_crosshair.setChecked(self._crosshair_enabled)
        act_crosshair.triggered.connect(self._set_crosshair)
        display_menu.addAction(act_crosshair)

        act_tangent = QAction(tr("chart_widget.ctx_tangent"), display_menu)
        act_tangent.setCheckable(True)
        act_tangent.setChecked(self._show_tangent)
        act_tangent.triggered.connect(self._set_show_tangent)
        display_menu.addAction(act_tangent)

        act_snap = QAction(tr("chart_widget.ctx_snap_to_data"), display_menu)
        act_snap.setCheckable(True)
        act_snap.setChecked(self._snap_to_data)
        act_snap.triggered.connect(self._set_snap_to_data)
        display_menu.addAction(act_snap)

        act_dots = QAction(tr("chart_widget.ctx_show_dots"), display_menu)
        act_dots.setCheckable(True)
        act_dots.setChecked(self._show_dots)
        act_dots.triggered.connect(self._set_show_dots)
        display_menu.addAction(act_dots)

        menu.addSeparator()

        log_menu = menu.addMenu(tr("chart_widget.ctx_log_scale"))
        act_log_x = QAction("Log X", log_menu)
        act_log_x.setCheckable(True)
        act_log_x.setChecked(c.log_x)
        act_log_x.triggered.connect(lambda v: c.setLogScale(x=v))
        log_menu.addAction(act_log_x)
        act_log_y = QAction("Log Y", log_menu)
        act_log_y.setCheckable(True)
        act_log_y.setChecked(c.log_y)
        act_log_y.triggered.connect(lambda v: c.setLogScale(y=v))
        log_menu.addAction(act_log_y)

        lock_menu = menu.addMenu(tr("chart_widget.ctx_zoom_lock"))
        grp_lock = QActionGroup(lock_menu)
        grp_lock.setExclusive(True)
        for key, lbl in (
            ("both", tr("chart_widget.ctx_zoom_both")),
            ("x", tr("chart_widget.ctx_zoom_x")),
            ("y", tr("chart_widget.ctx_zoom_y")),
        ):
            act = QAction(lbl, lock_menu)
            act.setCheckable(True)
            act.setChecked(self._zoom_lock == key)
            act.triggered.connect(lambda checked, k=key: self.setZoomLock(k))
            lock_menu.addAction(act)
            grp_lock.addAction(act)

        menu.addSeparator()

        fit_menu = menu.addMenu(tr("chart_widget.ctx_approximation"))
        grp = QActionGroup(fit_menu)
        grp.setExclusive(True)
        none_act = QAction("None", fit_menu)
        none_act.setCheckable(True)
        none_act.setChecked(c._active_fit_key is None)
        none_act.triggered.connect(lambda: c._on_fit_mode_selected(None))
        fit_menu.addAction(none_act)
        grp.addAction(none_act)
        for mode in get_fit_modes():
            act = QAction(mode.label, fit_menu)
            act.setCheckable(True)
            act.setChecked(c._active_fit_key == mode.key)
            act.triggered.connect(lambda checked, k=mode.key: c._on_fit_mode_selected(k))
            fit_menu.addAction(act)
            grp.addAction(act)

        menu.addSeparator()

        grid_menu = menu.addMenu(tr("chart_widget.ctx_grid"))
        x_menu = grid_menu.addMenu(tr("chart_widget.ctx_grid_x"))
        grp_x = QActionGroup(x_menu)
        grp_x.setExclusive(True)
        for key, px in _GRID_PRESETS_X:
            act = QAction(tr(key), x_menu)
            act.setCheckable(True)
            act.setChecked(c.grid_px_x == px)
            act.triggered.connect(lambda checked, v=px: c.setGridDensity(v, c.grid_px_y))
            x_menu.addAction(act)
            grp_x.addAction(act)
        y_menu = grid_menu.addMenu(tr("chart_widget.ctx_grid_y"))
        grp_y = QActionGroup(y_menu)
        grp_y.setExclusive(True)
        for key, px in _GRID_PRESETS_Y:
            act = QAction(tr(key), y_menu)
            act.setCheckable(True)
            act.setChecked(c.grid_px_y == px)
            act.triggered.connect(lambda checked, v=px: c.setGridDensity(c.grid_px_x, v))
            y_menu.addAction(act)
            grp_y.addAction(act)

        menu.addSeparator()

        rulers_menu = menu.addMenu(tr("chart_widget.ctx_rulers"))
        act_add_ruler = QAction(tr("chart_widget.ctx_add_ruler"), rulers_menu)
        act_add_ruler.triggered.connect(self._add_ruler_at_view_center)
        rulers_menu.addAction(act_add_ruler)
        if c.rulers:
            act_clear_rulers = QAction(tr("chart_widget.ctx_clear_rulers"), rulers_menu)
            act_clear_rulers.triggered.connect(self._clear_all_rulers)
            rulers_menu.addAction(act_clear_rulers)

        menu.addSeparator()

        if self._range_sel_x is not None:
            menu.addAction(tr("chart_widget.ctx_clear_range"), self.clearRangeSelection)

        act_copy = QAction(tr("chart_widget.ctx_copy_coords"), menu)
        act_copy.triggered.connect(self._copy_coords_to_clipboard)
        menu.addAction(act_copy)

        menu.addAction(tr("chart_widget.ctx_export_csv"), c.exportCsv)
        menu.addAction(tr("chart_widget.ctx_export_img"), c.exportImage)
        menu.addSeparator()
        menu.addAction(tr("chart_widget.ctx_reset_view"), c.autofit)
        return menu
