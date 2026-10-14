# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QWheelEvent, QEnterEvent
from PyQt6.QtWidgets import QWidget, QApplication


class CanvasEventsMixin:
    def toggle_selection(self, widget: QWidget):
        if widget in self._selected_widgets:
            self._selected_widgets.remove(widget)
            self._selected_widget = self._selected_widgets[-1] if self._selected_widgets else None
        else:
            self._selected_widgets.append(widget)
            self._selected_widget = widget
        self.widget_selected.emit(self._selected_widget)
        self.update()

    def _select_widgets_in_rect(self, x1, y1, x2, y2):
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        selected = []
        for child in self._root.children():
            if not isinstance(child, QWidget) or not child.isVisible():
                continue
            ox, oy = self._get_widget_root_offset(child)
            cx, cy = child.x() + ox, child.y() + oy
            cw, ch = child.width(), child.height()
            if cx < x2 and cx + cw > x1 and cy < y2 and cy + ch > y1:
                selected.append(child)
        self._selected_widgets = selected[:]
        self._selected_widget = selected[-1] if selected else None
        self.widget_selected.emit(self._selected_widget)

    def _store_drag_start_positions(self):
        self._drag_start_positions.clear()
        for w in self._selected_widgets:
            try:
                self._drag_start_positions[id(w)] = (w.x(), w.y())
            except RuntimeError:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_root_geometry()
        self._update_all_anchors(self.width(), self.height())

    def _resize_from_handle(self, w: QWidget, handle: str, dx: float, dy: float):
        if dx == 0 and dy == 0:
            return
        ox = self._drag_start_x
        oy = self._drag_start_y
        ow = self._drag_start_w
        oh = self._drag_start_h

        left, right = ox, ox + ow
        top, bottom = oy, oy + oh

        if "n" in handle: top = oy + dy
        if "s" in handle: bottom = oy + oh + dy
        if "w" in handle: left = ox + dx
        if "e" in handle: right = ox + ow + dx

        if "n" in handle: top = self._snap_value(top)
        if "s" in handle: bottom = self._snap_value(bottom)
        if "w" in handle: left = self._snap_value(left)
        if "e" in handle: right = self._snap_value(right)

        is_corner = len(handle) == 2
        if is_corner and ow > 0 and oh > 0:
            mods = QApplication.keyboardModifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                aspect = ow / oh
                rw, rh = right - left, bottom - top
                if abs(dx) >= abs(dy):
                    rh = round(rw / aspect)
                else:
                    rw = round(rh * aspect)
                if "n" in handle: top = bottom - rh
                if "w" in handle: left = right - rw
                if "e" in handle: right = left + rw
                if "s" in handle: bottom = top + rh

        if self._auto_align:
            left, top, right, bottom, gl = self._snap_resize_edges(w, left, top, right, bottom, handle)
            self._guide_lines = gl
        else:
            self._guide_lines = []

        nw = right - left
        nh = bottom - top

        if nw >= 8 and nh >= 8:
            w.setGeometry(int(left), int(top), int(nw), int(nh))

    def mousePressEvent(self, event: QMouseEvent):
        if not self._edit_mode:
            super().mousePressEvent(event)
            return
        mx, my = event.position().x(), event.position().y()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start_mx = int(mx)
            self._pan_start_my = int(my)
            self._pan_start_px = self._pan_x
            self._pan_start_py = self._pan_y
            return
        rx, ry = self._to_root(mx, my)
        for w in list(self._selected_widgets):
            handle = self._get_handle_at(rx, ry, w)
            if handle:
                self._drag_widget = w
                self._drag_handle = handle
                self._drag_start_x = w.x()
                self._drag_start_y = w.y()
                self._drag_start_w = w.width()
                self._drag_start_h = w.height()
                self._drag_start_mx = mx
                self._drag_start_my = my
                self._store_drag_start_positions()
                return
        hit = self.hit_test_widget(mx, my)
        if hit:
            sub = self._find_sub_window(hit)
            target = sub or hit
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.toggle_selection(target)
            else:
                self.selected_widget = target
            self._drag_widget = target
            self._drag_handle = "move"
            self._drag_start_x = target.x()
            self._drag_start_y = target.y()
            self._drag_start_w = target.width()
            self._drag_start_h = target.height()
            self._drag_start_mx = mx
            self._drag_start_my = my
            self._store_drag_start_positions()
        else:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self.selected_widget = None
            self._selection_box_start = (mx, my)
            self._is_selecting = True

    def mouseMoveEvent(self, event):
        if not self._edit_mode:
            super().mouseMoveEvent(event)
            return
        mx, my = event.position().x(), event.position().y()
        if self._is_panning:
            dx = mx - self._pan_start_mx
            dy = my - self._pan_start_my
            self._pan_x = self._pan_start_px - dx
            self._pan_y = self._pan_start_py - dy
            self._update_root_geometry()
            self.update()
            return
        if self._is_selecting and self._selection_box_start:
            sx, sy = self._selection_box_start
            self._selection_rect = (min(sx, mx), min(sy, my), abs(mx - sx), abs(my - sy))
            self.update()
            return
        if self._drag_widget and self._drag_handle:
            dx = mx - self._drag_start_mx
            dy = my - self._drag_start_my
            if self._drag_handle == "move":
                if dx == 0 and dy == 0:
                    self._guide_lines = []
                    self.update()
                    return
                for w in list(self._selected_widgets):
                    try:
                        sx, sy = self._drag_start_positions[id(w)]
                    except (KeyError, RuntimeError):
                        continue
                    w.move(int(self._snap_value(sx + dx)), int(self._snap_value(sy + dy)))
                if self._auto_align and len(self._selected_widgets) == 1:
                    new_x = self._snap_value(self._drag_start_x + dx)
                    new_y = self._snap_value(self._drag_start_y + dy)
                    nx, ny = self._snap_move_widget(self._drag_widget, new_x, new_y)
                    self._drag_widget.move(int(nx), int(ny))
            else:
                self._resize_from_handle(self._drag_widget, self._drag_handle, dx, dy)
            self.update()
        elif self._selected_widget:
            rx, ry = self._to_root(mx, my)
            handle = self._get_handle_at(rx, ry, self._selected_widget)
            cursor_map = {
                "nw": Qt.CursorShape.SizeFDiagCursor, "ne": Qt.CursorShape.SizeBDiagCursor,
                "sw": Qt.CursorShape.SizeBDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
                "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
                "w": Qt.CursorShape.SizeHorCursor, "e": Qt.CursorShape.SizeHorCursor,
            }
            self.setCursor(cursor_map.get(handle, Qt.CursorShape.ArrowCursor))

    def enterEvent(self, event: QEnterEvent):
        if self._edit_mode:
            self.setFocus()
        super().enterEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if self._edit_mode:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            factor = 1.1 if delta > 0 else 1 / 1.1
            mx, my = event.position().x(), event.position().y()
            rx, ry = self._to_root(mx, my)
            old_zoom = self._zoom
            self._zoom = max(0.1, min(10.0, self._zoom * factor))
            zoom_factor = self._zoom / old_zoom
            self._pan_x = rx * zoom_factor - mx
            self._pan_y = ry * zoom_factor - my
            self._update_display()
            self.zoom_changed.emit(self._zoom)
        else:
            super().wheelEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if self._is_panning:
            self._is_panning = False
            return
        if self._is_selecting and self._selection_box_start:
            self._is_selecting = False
            if self._selection_rect:
                sx, sy, sw, sh = self._selection_rect
                rx1, ry1 = self._to_root(sx, sy)
                rx2, ry2 = self._to_root(sx + sw, sy + sh)
                self._select_widgets_in_rect(rx1, ry1, rx2, ry2)
            self._selection_box_start = None
            self._selection_rect = None
            self.update()
            return
        widget = self._drag_widget
        self._drag_widget = None
        self._drag_handle = ""
        self._drag_start_positions.clear()
        if self._guide_lines:
            self._guide_lines.clear()
            self.update()
        if widget:
            self.widget_changed.emit(widget)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)

    def keyReleaseEvent(self, event):
        if not self._edit_mode:
            super().keyReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if not self._edit_mode:
            super().keyPressEvent(event)
            return
        key = event.key()
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C and self._selected_widget:
                self.copy_requested.emit()
                return
            elif key == Qt.Key.Key_V:
                self.paste_requested.emit()
                return
        if not self._selected_widgets:
            return
        step = self._grid_size if self._snap_to_grid else 1
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for w in list(self._selected_widgets):
                self.remove_widget(w)
            self._selected_widgets.clear()
            self._selected_widget = None
            self.widget_selected.emit(None)
            self.update()
        elif key == Qt.Key.Key_Up:
            for w in self._selected_widgets:
                w.move(w.x(), int(self._snap_value(w.y() - step)))
            self.update()
            self.widget_changed.emit(self._selected_widget)
        elif key == Qt.Key.Key_Down:
            for w in self._selected_widgets:
                w.move(w.x(), int(self._snap_value(w.y() + step)))
            self.update()
            self.widget_changed.emit(self._selected_widget)
        elif key == Qt.Key.Key_Left:
            for w in self._selected_widgets:
                w.move(int(self._snap_value(w.x() - step)), w.y())
            self.update()
            self.widget_changed.emit(self._selected_widget)
        elif key == Qt.Key.Key_Right:
            for w in self._selected_widgets:
                w.move(int(self._snap_value(w.x() + step)), w.y())
            self.update()
            self.widget_changed.emit(self._selected_widget)
