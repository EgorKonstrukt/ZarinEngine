# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Any
from PyQt6.QtWidgets import QListWidget, QTreeWidget, QTableWidget, QComboBox, QFontComboBox
from core.gui.wid.base import ANCHOR_TOP_LEFT, _set_widget_bounds, _update_anchor

class ListWidget(QListWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 200, items: Optional[list[str]] = None, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT
        self._anchor_offset_x = 0.0
        self._anchor_offset_y = 0.0
        self._z_index = 0
        self._tag = ""
        self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None
        self._canvas_size = (800, 600)
        self._orig_w = w
        self._orig_h = h
        self.setObjectName("GuiListWidget")
        if items:
            self.addItems(items)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "ListWidget",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "items": [self.item(i).text() for i in range(self.count())],
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> ListWidget:
        lw = ListWidget(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 200), data.get("items"))
        lw._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        lw._z_index = data.get("z_index", 0)
        lw._tag = data.get("tag", "")
        return lw


class TreeWidget(QTreeWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 200, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT
        self._anchor_offset_x = 0.0
        self._anchor_offset_y = 0.0
        self._z_index = 0
        self._tag = ""
        self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None
        self._canvas_size = (800, 600)
        self._orig_w = w
        self._orig_h = h
        self.setObjectName("GuiTreeWidget")
        self.setHeaderLabel("Tree")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "TreeWidget",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> TreeWidget:
        tw = TreeWidget(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 200))
        tw._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        tw._z_index = data.get("z_index", 0)
        tw._tag = data.get("tag", "")
        return tw


class TableWidget(QTableWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 300, h: float = 200,
                 rows: int = 3, cols: int = 3, parent=None):
        super().__init__(rows, cols, parent)
        self._anchor = ANCHOR_TOP_LEFT
        self._anchor_offset_x = 0.0
        self._anchor_offset_y = 0.0
        self._z_index = 0
        self._tag = ""
        self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None
        self._canvas_size = (800, 600)
        self._orig_w = w
        self._orig_h = h
        self.setObjectName("GuiTableWidget")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "TableWidget",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "rows": self.rowCount(), "cols": self.columnCount(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> TableWidget:
        tw = TableWidget(data.get("x", 0), data.get("y", 0), data.get("w", 300), data.get("h", 200),
                         data.get("rows", 3), data.get("cols", 3))
        tw._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        tw._z_index = data.get("z_index", 0)
        tw._tag = data.get("tag", "")
        return tw


class Dropdown(QComboBox):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 32, items: Optional[list[str]] = None, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT
        self._anchor_offset_x = 0.0
        self._anchor_offset_y = 0.0
        self._z_index = 0
        self._tag = ""
        self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None
        self._canvas_size = (800, 600)
        self._orig_w = w
        self._orig_h = h
        self.setObjectName("GuiDropdown")
        if items:
            self.addItems(items)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Dropdown",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "items": [self.itemText(i) for i in range(self.count())],
            "current": self.currentIndex(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Dropdown:
        d = Dropdown(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 32),
                     data.get("items"))
        d.setCurrentIndex(data.get("current", 0))
        d._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        d._z_index = data.get("z_index", 0)
        d._tag = data.get("tag", "")
        return d


class FontCombo(QFontComboBox):
    def __init__(self, x: float = 0, y: float = 0, w: float = 160, h: float = 28, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiFontCombo")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "FontCombo", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        f = FontCombo(data.get("x", 0), data.get("y", 0), data.get("w", 160), data.get("h", 28))
        f._anchor = data.get("anchor", ANCHOR_TOP_LEFT); f._z_index = data.get("z_index", 0); f._tag = data.get("tag", ""); return f
