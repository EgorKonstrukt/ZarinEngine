# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
from PyQt6.QtWidgets import QWidget, QMdiArea, QMdiSubWindow


class CanvasOverlayMixin:
    def is_point_over_widget(self, px: float, py: float) -> bool:
        hit = self.hit_test_widget(px, py)
        return hit is not None and hit is not self._root

    def resize_canvas(self, w: float, h: float):
        pass

    def _update_display(self):
        self._update_root_geometry()
        self._update_all_anchors(self.width(), self.height())
        self.update()

    def _update_root_geometry(self):
        self._root.setGeometry(int(-self._pan_x), int(-self._pan_y), self.width(), self.height())

    def _snap_value(self, v: float) -> float:
        if self._snap_to_grid and self._grid_size > 0:
            return round(v / self._grid_size) * self._grid_size
        return v

    def _get_all_widget_edges(self, exclude_widget) -> list[tuple[str, float]]:
        edges: list[tuple[str, float]] = []
        for child in self._root.children():
            if not isinstance(child, QWidget) or child is exclude_widget or child is self._root:
                continue
            if not child.isVisible():
                continue
            ox, oy = self._get_widget_root_offset(child)
            cl = child.x() + ox
            ct = child.y() + oy
            cr = cl + child.width()
            cb = ct + child.height()
            cx = (cl + cr) / 2
            cy = (ct + cb) / 2
            edges += [('left', cl), ('right', cr), ('cx', cx),
                      ('top', ct), ('bottom', cb), ('cy', cy)]
        edges += [('left', 0), ('right', self._screen_w),
                  ('top', 0), ('bottom', self._screen_h),
                  ('cx', self._screen_w / 2), ('cy', self._screen_h / 2)]
        return edges

    def _snap_axis(self, moving: dict[str, float], others: list[tuple[str, float]],
                   threshold: float) -> tuple[float | None, str | None, float | None, tuple | None]:
        best_dist = threshold
        best_my_name: str | None = None
        best_other_val: float | None = None
        best_guide: tuple | None = None
        for my_name, my_val in moving.items():
            for other_name, other_val in others:
                dist = abs(my_val - other_val)
                if dist < best_dist:
                    best_dist = dist
                    best_my_name = my_name
                    best_other_val = other_val
                    is_vert = my_name in ('left', 'right', 'cx')
                    v = other_val - self._pan_x if is_vert else other_val - self._pan_y
                    if is_vert:
                        best_guide = (v, 0, v, self.height())
                    else:
                        best_guide = (0, v, self.width(), v)
        return best_dist, best_my_name, best_other_val, best_guide

    def _snap_move_widget(self, widget: QWidget, new_x: float, new_y: float) -> tuple[float, float]:
        w_off_x, w_off_y = self._get_widget_root_offset(widget)
        rw = widget.width()
        rh = widget.height()
        vert = {'left': new_x + w_off_x, 'right': new_x + w_off_x + rw, 'cx': new_x + w_off_x + rw / 2}
        horiz = {'top': new_y + w_off_y, 'bottom': new_y + w_off_y + rh, 'cy': new_y + w_off_y + rh / 2}
        others = self._get_all_widget_edges(widget)
        t = 6.0
        _, sx_name, sx_val, gx = self._snap_axis(vert, others, t)
        _, sy_name, sy_val, gy = self._snap_axis(horiz, others, t)
        self._guide_lines = []
        if gx: self._guide_lines.append(gx)
        if gy: self._guide_lines.append(gy)
        nrx = new_x + w_off_x
        nry = new_y + w_off_y
        if sx_name and sx_val is not None:
            nrx = (sx_val if sx_name == 'left' else
                   sx_val - rw if sx_name == 'right' else
                   sx_val - rw / 2)
        if sy_name and sy_val is not None:
            nry = (sy_val if sy_name == 'top' else
                   sy_val - rh if sy_name == 'bottom' else
                   sy_val - rh / 2)
        return nrx - w_off_x, nry - w_off_y

    def _snap_resize_edges(self, widget: QWidget, left: float, top: float,
                           right: float, bottom: float, handle: str
                           ) -> tuple[float, float, float, float, list]:
        w_off_x, w_off_y = self._get_widget_root_offset(widget)
        moving_vert: dict[str, float] = {}
        moving_horiz: dict[str, float] = {}
        if "w" in handle: moving_vert['left'] = left + w_off_x
        if "e" in handle: moving_vert['right'] = right + w_off_x
        if "n" in handle: moving_horiz['top'] = top + w_off_y
        if "s" in handle: moving_horiz['bottom'] = bottom + w_off_y
        if not moving_vert and not moving_horiz:
            return left, top, right, bottom, []
        others = self._get_all_widget_edges(widget)
        t = 6.0
        _, sx_name, sx_val, gx = self._snap_axis(moving_vert, others, t)
        _, sy_name, sy_val, gy = self._snap_axis(moving_horiz, others, t)
        guides = []
        if gx: guides.append(gx)
        if gy: guides.append(gy)
        if sx_val is not None and sx_name == 'left':
            left = sx_val - w_off_x
        elif sx_val is not None and sx_name == 'right':
            right = sx_val - w_off_x
        if sy_val is not None and sy_name == 'top':
            top = sy_val - w_off_y
        elif sy_val is not None and sy_name == 'bottom':
            bottom = sy_val - w_off_y
        return left, top, right, bottom, guides

    def _get_widget_root_offset(self, w: QWidget) -> tuple[int, int]:
        try:
            ox, oy = 0, 0
            p = w.parent()
            while p and p is not self._root:
                ox += p.x()
                oy += p.y()
                p = p.parent()
            return ox, oy
        except RuntimeError:
            return 0, 0

    def _get_handle_at(self, wx: float, wy: float, w: QWidget) -> str:
        try:
            _ = w.parent()
        except RuntimeError:
            return ""
        ox, oy = self._get_widget_root_offset(w)
        lx = wx - (w.x() + ox)
        ly = wy - (w.y() + oy)
        gw, gh = w.width(), w.height()
        hs = 6
        if abs(lx) < hs and abs(ly) < hs: return "nw"
        if abs(lx - gw) < hs and abs(ly) < hs: return "ne"
        if abs(lx) < hs and abs(ly - gh) < hs: return "sw"
        if abs(lx - gw) < hs and abs(ly - gh) < hs: return "se"
        if abs(lx - gw / 2) < hs and abs(ly) < hs: return "n"
        if abs(lx - gw / 2) < hs and abs(ly - gh) < hs: return "s"
        if abs(lx) < hs and abs(ly - gh / 2) < hs: return "w"
        if abs(lx - gw) < hs and abs(ly - gh / 2) < hs: return "e"
        return ""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        vw, vh = self.width(), self.height()
        painter.fillRect(0, 0, vw, vh, self._background_color)
        if self._show_grid and self._edit_mode:
            gs = int(self._grid_size * self._zoom)
            if gs > 0:
                painter.setPen(QPen(QColor(51, 51, 51), 1))
                start_x = int((-self._pan_x) % gs) if gs > 0 else 0
                for gx in range(start_x, vw, gs):
                    painter.drawLine(gx, 0, gx, vh)
                start_y = int((-self._pan_y) % gs) if gs > 0 else 0
                for gy in range(start_y, vh, gs):
                    painter.drawLine(0, gy, vw, gy)
        if self._edit_mode:
            self._draw_screen_overlay(painter)
            if self._show_selection and self._selected_widgets:
                self._draw_selection(painter)
        if self._edit_mode and self._selection_rect:
            sx, sy, sw, sh = self._selection_rect
            painter.setPen(QPen(QColor(74, 122, 181), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(74, 122, 181, 40)))
            painter.drawRect(int(sx), int(sy), int(sw), int(sh))
        if self._auto_align and self._guide_lines:
            painter.setPen(QPen(QColor(255, 68, 68), 1, Qt.PenStyle.DashLine))
            for x1, y1, x2, y2 in self._guide_lines:
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        painter.end()

    def _find_sub_window(self, widget: QWidget) -> Optional[QWidget]:
        p = widget.parent()
        while p and p is not self._root:
            if isinstance(p, QMdiSubWindow):
                return p
            p = p.parent()
        return None

    def hit_test_widget(self, px: float, py: float) -> Optional[QWidget]:
        rx, ry = self._to_root(px, py)
        px, py = int(rx), int(ry)
        def _deepest(parent, off_x=0, off_y=0):
            for child in reversed(list(parent.children())):
                if not isinstance(child, QWidget) or not child.isVisible():
                    continue
                cg = child.geometry()
                cx, cy = off_x + cg.x(), off_y + cg.y()
                if cx <= px <= cx + cg.width() and cy <= py <= cy + cg.height():
                    deeper = _deepest(child, cx, cy)
                    if deeper:
                        return deeper
                    if isinstance(child, QMdiArea):
                        continue
                    return child
            return None
        return _deepest(self._root)

    def _render_overlay(self, painter: QPainter):
        if self._edit_mode:
            self._draw_screen_overlay(painter)

    def _draw_screen_overlay(self, painter: QPainter):
        sw = int(self._screen_w * self._zoom)
        sh = int(self._screen_h * self._zoom)
        px = int(-self._pan_x)
        py = int(-self._pan_y)
        painter.setPen(QPen(QColor(106, 138, 181), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(px, py, sw, sh)
        painter.setPen(QColor(106, 138, 181))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        label = f"{self._screen_w} Г— {self._screen_h}"
        painter.drawText(px + 6, py + sh - 6, label)

    def _draw_selection(self, painter: QPainter):
        if not self._selected_widgets:
            return
        hs = 5
        for w in list(self._selected_widgets):
            try:
                _ = w.parent()
            except RuntimeError:
                self._selected_widgets.remove(w)
                continue
            ox, oy = self._get_widget_root_offset(w)
            gx, gy = w.x() + ox, w.y() + oy
            gw, gh = w.width(), w.height()
            sx = int(gx - self._pan_x)
            sy = int(gy - self._pan_y)
            painter.setPen(QPen(QColor(74, 122, 181), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sx, sy, gw, gh)
            handles = [
                (sx, sy), (int(sx + gw / 2), sy), (sx + gw, sy),
                (sx, int(sy + gh / 2)), (sx + gw, int(sy + gh / 2)),
                (sx, sy + gh), (int(sx + gw / 2), sy + gh), (sx + gw, sy + gh),
            ]
            painter.setBrush(QBrush(QColor(74, 122, 181)))
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            for hx, hy in handles:
                painter.drawRect(int(hx - hs / 2), int(hy - hs / 2), hs, hs)
        sel = self._selected_widget
        if not sel:
            return
        try:
            _ = sel.parent()
        except RuntimeError:
            self._selected_widget = None
            return
        ox, oy = self._get_widget_root_offset(sel)
        gx, gy = sel.x() + ox, sel.y() + oy
        gw, gh = sel.width(), sel.height()
        sx = int(gx - self._pan_x)
        sy = int(gy - self._pan_y)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        if self._drag_widget is sel:
            if self._drag_handle == "move":
                dd = f" О”x:{sel.x() - self._drag_start_x:+d} О”y:{sel.y() - self._drag_start_y:+d}"
            else:
                dd = f" О”w:{sel.width() - self._drag_start_w:+d} О”h:{sel.height() - self._drag_start_h:+d}"
        else:
            dd = ""
        info = f"x:{gx} y:{gy}  {gw}Г—{gh}{dd}"
        iw = painter.fontMetrics().horizontalAdvance(info) + 8
        ih = painter.fontMetrics().height() + 2
        ix = sx
        iy = sy - ih - 2
        if iy < 0:
            iy = sy + gh + 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
        painter.drawRect(ix, iy, iw, ih)
        painter.setPen(QColor(204, 204, 204))
        painter.drawText(ix + 4, iy + ih - 3, info)
