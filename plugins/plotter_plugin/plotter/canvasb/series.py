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
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF
from PyQt6.QtGui import (QPen, QColor, QBrush, QFont, QFontMetrics,
                         QPixmap, QWheelEvent, QMouseEvent)
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu
from ..mathx import nice_ticks, nice_log_ticks, to_log, decimated, fmt, get_fit_modes
from ..itemsp import _LineItem, _FitItem, _InfLine, _FunctionItem
from ..i18n import tr

if TYPE_CHECKING:
    from ..chart import ChartWidget
from .canvas import _DECIMATE_THRESHOLD, _SNAP_RADIUS_PX, _INFLINE_HIT_PX, _ANALYTICS_PAD, _ANALYTICS_ROW_H, _ANALYTICS_MAX_SERIES, _LEGEND_PAD, _LEGEND_SWATCH, _skewness


class CanvasSeriesMixin:
    def _nearest_on_segments(self, mouse, xs, ys, pr, x0, dx, y0, dy, log_x, log_y):
        if not xs:
            return None
        if len(xs) == 1:
            pt = self._to_pt_log(xs[0], ys[0], x0, dx, y0, dy, pr, log_x, log_y)
            return (xs[0], ys[0], math.hypot(pt.x() - mouse.x(), pt.y() - mouse.y()))
        best_d = float("inf")
        best_xi, best_yi = xs[0], ys[0]
        for i in range(len(xs) - 1):
            pt0 = self._to_pt_log(xs[i], ys[i], x0, dx, y0, dy, pr, log_x, log_y)
            pt1 = self._to_pt_log(xs[i + 1], ys[i + 1], x0, dx, y0, dy, pr, log_x, log_y)
            seg_x = pt1.x() - pt0.x()
            seg_y = pt1.y() - pt0.y()
            seg_len2 = seg_x * seg_x + seg_y * seg_y
            t = 0.0 if seg_len2 < 1e-10 else max(0.0, min(1.0,
                ((mouse.x() - pt0.x()) * seg_x + (mouse.y() - pt0.y()) * seg_y) / seg_len2))
            nx = pt0.x() + t * seg_x
            ny = pt0.y() + t * seg_y
            d = math.hypot(nx - mouse.x(), ny - mouse.y())
            if d < best_d:
                best_d = d
                best_xi = xs[i] + t * (xs[i + 1] - xs[i])
                best_yi = ys[i] + t * (ys[i + 1] - ys[i])
        return (best_xi, best_yi, best_d)

    def _find_nearest(self, mouse, pr, x0, dx, y0, dy):
        if not self._snap_to_data:
            return None
        key = (int(mouse.x()), int(mouse.y()), x0, dx, y0, dy)
        if self._nearest_cache_key == key:
            return self._nearest_cache_result
        c = self._chart
        log_x, log_y = c.log_x, c.log_y
        best_d = float("inf")
        best = None
        for item in c.scatters:
            if not item.visible:
                continue
            for xi, yi in zip(item.xs, item.ys):
                pt = self._to_pt_log(xi, yi, x0, dx, y0, dy, pr, log_x, log_y)
                d = math.hypot(pt.x() - mouse.x(), pt.y() - mouse.y())
                if d < best_d:
                    best_d = d
                    best = (xi, yi, d, item)
        for item in c.lines:
            if not item.visible or not item.xs:
                continue
            dxs, dys = decimated(item.xs, item.ys, _DECIMATE_THRESHOLD)
            r = self._nearest_on_segments(mouse, dxs, dys, pr, x0, dx, y0, dy, log_x, log_y)
            if r and r[2] < best_d:
                best_d = r[2]
                best = (r[0], r[1], r[2], item)
        for item in c.fits:
            if not item.visible or not item.xs:
                continue
            r = self._nearest_on_segments(mouse, item.xs, item.ys, pr, x0, dx, y0, dy, log_x, log_y)
            if r and r[2] < best_d:
                best_d = r[2]
                best = (r[0], r[1], r[2], item)
        for item in c.functions:
            if not item.visible or not item.xs:
                continue
            fn_xs_f = [item.xs[i] for i in range(len(item.xs)) if item.ys[i] is not None]
            fn_ys_f = [item.ys[i] for i in range(len(item.ys)) if item.ys[i] is not None]
            if not fn_xs_f:
                continue
            r = self._nearest_on_segments(mouse, fn_xs_f, fn_ys_f, pr, x0, dx, y0, dy, log_x, log_y)
            if r and r[2] < best_d:
                best_d = r[2]
                best = (r[0], r[1], r[2], item)
        result = best if best and best[2] <= _SNAP_RADIUS_PX else None
        self._nearest_cache_key = key
        self._nearest_cache_result = result
        return result

    def _find_ruler_handle_at(self, pos, pr, x0, dx, y0, dy):
        c = self._chart
        log_x, log_y = c.log_x, c.log_y
        for ruler in c.rulers:
            if not ruler.visible or not ruler.draggable:
                continue
            for idx, (xv, yv) in enumerate(((ruler.x0, ruler.y0), (ruler.x1, ruler.y1))):
                pt = self._to_pt_log(xv, yv, x0, dx, y0, dy, pr, log_x, log_y)
                if math.hypot(pt.x() - pos.x(), pt.y() - pos.y()) <= ruler.handle_radius + 4:
                    return (ruler, idx)
        return None

    def _find_infline_at(self, pos, pr, x0, dx, y0, dy):
        c = self._chart
        for ln in c.inflines:
            if not ln.visible or not ln.draggable:
                continue
            if ln.horizontal:
                sy = pr.bottom() - (ln.value - y0) / dy * pr.height()
                if abs(pos.y() - sy) <= _INFLINE_HIT_PX and pr.left() <= pos.x() <= pr.right():
                    return ln
            else:
                sx = pr.left() + (ln.value - x0) / dx * pr.width()
                if abs(pos.x() - sx) <= _INFLINE_HIT_PX and pr.top() <= pos.y() <= pr.bottom():
                    return ln
        return None

    def _find_scatter_point_at(self, pos, pr, x0, dx, y0, dy):
        c = self._chart
        log_x, log_y = c.log_x, c.log_y
        for item in c.scatters:
            if not item.visible:
                continue
            for i, (xi, yi) in enumerate(zip(item.xs, item.ys)):
                pt = self._to_pt_log(xi, yi, x0, dx, y0, dy, pr, log_x, log_y)
                if math.hypot(pt.x() - pos.x(), pt.y() - pos.y()) <= item.size:
                    return (item, i)
        return None

    def _tangent_slope(self, item, xi):
        if isinstance(item, _FunctionItem):
            pairs = [(x, y) for x, y in zip(item.xs, item.ys) if y is not None]
            if len(pairs) < 2:
                return None
            xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        elif isinstance(item, (_LineItem, _FitItem)) and len(item.xs) >= 2:
            xs, ys = item.xs, item.ys
        else:
            return None
        n = len(xs)
        pos = bisect_left(xs, xi)
        if pos >= n:
            pos = n - 1
        elif pos > 0 and abs(xs[pos - 1] - xi) < abs(xs[pos] - xi):
            pos -= 1
        if pos == 0:
            ddx, ddy = xs[1] - xs[0], ys[1] - ys[0]
        elif pos == n - 1:
            ddx, ddy = xs[-1] - xs[-2], ys[-1] - ys[-2]
        else:
            ddx, ddy = xs[pos + 1] - xs[pos - 1], ys[pos + 1] - ys[pos - 1]
        return ddy / ddx if abs(ddx) > 1e-15 else None

    def _paint_data_dots(self, p, pr, x0, dx, y0, dy):
        c = self._chart
        log_x, log_y = c.log_x, c.log_y
        p.save()
        p.setClipRect(pr)
        for item in c.lines:
            if not item.visible or not item.xs:
                continue
            col = item.pen.color()
            p.setPen(QPen(col.darker(140), 1))
            p.setBrush(QBrush(col))
            for xi, yi in zip(item.xs, item.ys):
                pt = self._to_pt_log(xi, yi, x0, dx, y0, dy, pr, log_x, log_y)
                if (pr.left() - 4 <= pt.x() <= pr.right() + 4 and
                        pr.top() - 4 <= pt.y() <= pr.bottom() + 4):
                    p.drawEllipse(pt, 2.5, 2.5)
        p.restore()

    def _paint_analytics(self, p, pr, fg, bg, fm):
        from ..mathx import trapezoid_integral
        c = self._chart
        named = []
        for i, it in enumerate(c.lines):
            if it.xs and it.visible:
                named.append((it.label or tr("chart_widget.analytics_line", n=i + 1), it))
        for i, it in enumerate(c.scatters):
            if it.xs and it.visible:
                named.append((it.label or tr("chart_widget.analytics_scatter", n=i + 1), it))
        named = named[:_ANALYTICS_MAX_SERIES]
        if not named:
            return
        range_lo, range_hi = None, None
        if self._range_sel_x is not None:
            range_lo, range_hi = sorted(self._range_sel_x)
        row_keys = [
            "chart_widget.analytics_n",
            "chart_widget.analytics_xmin",
            "chart_widget.analytics_xmax",
            "chart_widget.analytics_ymin",
            "chart_widget.analytics_ymax",
            "chart_widget.analytics_mean",
            "chart_widget.analytics_median",
            "chart_widget.analytics_std",
            "chart_widget.analytics_range",
            "chart_widget.analytics_skew",
            "chart_widget.analytics_integral",
        ]
        row_lbls = [tr(k) for k in row_keys]
        table: List[List[str]] = []
        for _, it in named:
            if range_lo is not None and range_hi is not None:
                pairs = [(x, y) for x, y in zip(it.xs, it.ys) if range_lo <= x <= range_hi]
                fxs = [pair[0] for pair in pairs]
                fys = [pair[1] for pair in pairs]
            else:
                fxs, fys = list(it.xs), list(it.ys)
            n = len(fxs)
            if n == 0:
                table.append(["-"] * len(row_keys))
                continue
            fys_finite = [v for v in fys if v is not None and math.isfinite(v)]
            n_fin = len(fys_finite)
            st = fmt(statistics.stdev(fys_finite)) if n_fin > 1 else "-"
            med = fmt(statistics.median(fys_finite)) if n_fin >= 1 else "-"
            rng = fmt(max(fys_finite) - min(fys_finite)) if n_fin >= 1 else "-"
            sk = _skewness(fys_finite)
            skew_s = fmt(sk) if sk is not None else "-"
            intg = fmt(trapezoid_integral(fxs, fys_finite))
            table.append([
                str(n),
                fmt(min(fxs)), fmt(max(fxs)),
                fmt(min(fys_finite)) if fys_finite else "-",
                fmt(max(fys_finite)) if fys_finite else "-",
                fmt(statistics.mean(fys_finite)) if n_fin >= 1 else "-",
                med, st, rng, skew_s, intg,
            ])
        lbl_w = max(fm.horizontalAdvance(l) for l in row_lbls) + 10
        val_w = max(fm.horizontalAdvance(v) for row in table for v in row) + 10
        hdr_h = fm.height() + 6
        rh = _ANALYTICS_ROW_H
        pad = _ANALYTICS_PAD
        n_ser = len(named)
        total_w = pad * 2 + lbl_w + val_w * n_ser
        total_h = pad * 2 + hdr_h + rh * len(row_lbls)
        ax = pr.right() - total_w - 4
        ay = pr.top() + 4
        bg_ = QColor(bg)
        bg_.setAlpha(210)
        brd_ = QColor(fg)
        brd_.setAlpha(70)
        p.setBrush(QBrush(bg_))
        p.setPen(QPen(brd_, 1))
        p.drawRoundedRect(ax, ay, total_w, total_h, 4, 4)
        bold_f = QFont(self._chart.font)
        bold_f.setBold(True)
        hdr_col = QColor(fg)
        hdr_col.setAlpha(220)
        lbl_col = QColor(fg)
        lbl_col.setAlpha(150)
        for ci, (name, _) in enumerate(named):
            cx = ax + pad + lbl_w + ci * val_w + val_w // 2
            p.setFont(bold_f)
            p.setPen(hdr_col)
            p.drawText(cx - fm.horizontalAdvance(name) // 2, ay + pad + fm.ascent(), name)
        p.setFont(self._chart.font)
        for ri, lbl in enumerate(row_lbls):
            ry = ay + pad + hdr_h + ri * rh
            sep_col = QColor(fg)
            sep_col.setAlpha(20)
            if ri % 2 == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(sep_col))
                p.drawRect(ax + 1, ry - 1, total_w - 2, rh)
            p.setPen(lbl_col)
            p.drawText(ax + pad, ry + fm.ascent(), lbl)
            p.setPen(hdr_col)
            for ci, row in enumerate(table):
                val = row[ri]
                cx = ax + pad + lbl_w + ci * val_w
                vw = fm.horizontalAdvance(val)
                p.drawText(cx + (val_w - vw) // 2, ry + fm.ascent(), val)

    def _paint_legend(self, p, pr, fg, bg, fm):
        c = self._chart
        entries = []
        for i, it in enumerate(c.lines + c.lines_r2):
            if not it.visible:
                continue
            suffix = " (R)" if it in c.lines_r2 else ""
            entries.append((it.label or tr("chart_widget.legend_label", n=i + 1) + suffix,
                             it.pen.color(), False))
        offset = len(c.lines) + len(c.lines_r2)
        for i, it in enumerate(c.scatters + c.scatters_r2):
            if not it.visible:
                continue
            suffix = " (R)" if it in c.scatters_r2 else ""
            color = it.color if hasattr(it, "color") else QColor(255, 255, 255)
            entries.append((it.label or tr("chart_widget.legend_label",
                             n=offset + i + 1) + suffix, color, True))
        for i, fit in enumerate(c.fits):
            if not fit.visible:
                continue
            entries.append((fit.label or tr("chart_widget.analytics_fit", n=i + 1),
                             fit.pen.color(), False))
        for i, fn_item in enumerate(c.functions):
            if not fn_item.visible:
                continue
            entries.append((fn_item.label or f"f(x) {i + 1}", fn_item.pen.color(), False))
        if not entries:
            return
        pad = _LEGEND_PAD
        sw = _LEGEND_SWATCH
        row_h = max(fm.height(), sw) + 4
        max_w = max(fm.horizontalAdvance(e[0]) for e in entries) + sw + pad * 2 + 6
        total_h = pad * 2 + row_h * len(entries)
        lx = pr.right() - max_w - 4
        ly = pr.bottom() - total_h - 4
        bg_ = QColor(bg)
        bg_.setAlpha(200)
        brd_ = QColor(fg)
        brd_.setAlpha(60)
        p.setBrush(QBrush(bg_))
        p.setPen(QPen(brd_, 1))
        p.drawRoundedRect(lx, ly, max_w, total_h, 4, 4)
        p.setFont(self._chart.font)
        for i, (label, color, is_scatter) in enumerate(entries):
            ry = ly + pad + i * row_h + (row_h - sw) // 2
            if is_scatter:
                p.setPen(QPen(color.darker(150), 1))
                p.setBrush(QBrush(color))
                p.drawEllipse(lx + pad, ry, sw, sw)
            else:
                p.setPen(QPen(color, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                mid_y = ry + sw // 2
                p.drawLine(lx + pad, mid_y, lx + pad + sw, mid_y)
            txt_col = QColor(fg)
            txt_col.setAlpha(210)
            p.setPen(txt_col)
            p.drawText(lx + pad + sw + 6, ry + fm.ascent(), label)

    def _paint_ruler(self, p, ruler, pr, x0, dx, y0, dy, fg, bg, fm):
        c = self._chart
        log_x, log_y = c.log_x, c.log_y
        pt0 = self._to_pt_log(ruler.x0, ruler.y0, x0, dx, y0, dy, pr, log_x, log_y)
        pt1 = self._to_pt_log(ruler.x1, ruler.y1, x0, dx, y0, dy, pr, log_x, log_y)
        p.setPen(ruler.pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(pt0, pt1)
        handle_col = QColor(ruler.pen.color())
        handle_col.setAlpha(200)
        p.setPen(QPen(handle_col, 1))
        p.setBrush(QBrush(handle_col))
        r = float(ruler.handle_radius)
        p.drawEllipse(pt0, r, r)
        p.drawEllipse(pt1, r, r)
        mid = QPointF((pt0.x() + pt1.x()) / 2.0, (pt0.y() + pt1.y()) / 2.0)
        angle_deg = ruler.angle_deg
        dist_lbl = tr(
            "chart_widget.ruler_label",
            d=fmt(ruler.distance),
            dx=fmt(ruler.dx),
            dy=fmt(ruler.dy),
            angle=f"{angle_deg:.1f}",
        )
        tw = fm.horizontalAdvance(dist_lbl)
        th = fm.height()
        pad = 4
        tx = int(mid.x()) - tw // 2
        ty = int(mid.y()) - th - 6
        bg_ = QColor(bg)
        bg_.setAlpha(210)
        br_ = QColor(fg)
        br_.setAlpha(80)
        p.setBrush(QBrush(bg_))
        p.setPen(QPen(br_, 1))
        p.drawRoundedRect(tx - pad, ty - pad // 2, tw + pad * 2, th + pad, 3, 3)
        p.setPen(fg)
        p.setFont(c.font)
        p.drawText(tx, ty + fm.ascent(), dist_lbl)

    def _draw_formula_tag(self, p, pt, formula, fg, bg, fm):
        pad = 4
        tw = fm.horizontalAdvance(formula) + pad * 2
        th = fm.height() + pad
        tx = int(pt.x()) + 6
        ty = int(pt.y()) - th - 4
        bg_ = QColor(bg)
        bg_.setAlpha(200)
        br_ = QColor(fg)
        br_.setAlpha(80)
        p.setBrush(QBrush(bg_))
        p.setPen(QPen(br_, 1))
        p.drawRoundedRect(tx, ty, tw, th, 3, 3)
        p.setPen(fg)
        p.drawText(tx + pad, ty + fm.ascent() + pad // 2, formula)
