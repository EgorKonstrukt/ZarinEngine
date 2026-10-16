# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGroupBox, QTabWidget, QStackedWidget, QSplitter, QScrollArea, QWidget, QMdiArea, QMdiSubWindow, QToolBox
from core.gui.wid.base import ANCHOR_TOP_LEFT, _set_widget_bounds, _update_anchor

class Panel(QFrame):
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
        self.setObjectName("GuiPanel")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Panel",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Panel:
        p = Panel(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 200))
        p._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        p._z_index = data.get("z_index", 0)
        p._tag = data.get("tag", "")
        return p


class GroupBox(QGroupBox):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 200, title: str = "Group", parent=None):
        super().__init__(title, parent)
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
        self.setObjectName("GuiGroupBox")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "GroupBox",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "title": self.title(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> GroupBox:
        gb = GroupBox(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 200),
                      data.get("title", "Group"))
        gb._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        gb._z_index = data.get("z_index", 0)
        gb._tag = data.get("tag", "")
        return gb


class TabWidget(QTabWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 300, h: float = 200, parent=None):
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
        self.setObjectName("GuiTabWidget")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "TabWidget",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "tab_count": self.count(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> TabWidget:
        tw = TabWidget(data.get("x", 0), data.get("y", 0), data.get("w", 300), data.get("h", 200))
        tw._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        tw._z_index = data.get("z_index", 0)
        tw._tag = data.get("tag", "")
        return tw


class StackedWidget(QStackedWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 200, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiStackedWidget")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "StackedWidget", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        s = StackedWidget(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 200))
        s._anchor = data.get("anchor", ANCHOR_TOP_LEFT); s._z_index = data.get("z_index", 0); s._tag = data.get("tag", ""); return s


class Splitter(QSplitter):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 200, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiSplitter")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "Splitter", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        s = Splitter(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 200))
        s._anchor = data.get("anchor", ANCHOR_TOP_LEFT); s._z_index = data.get("z_index", 0); s._tag = data.get("tag", ""); return s


class ScrollPanel(QScrollArea):
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
        self.setObjectName("GuiScrollPanel")
        self.setWidgetResizable(True)
        _set_widget_bounds(self, x, y, w, h)
        self._scroll_content = QWidget()
        self.setWidget(self._scroll_content)

    @property
    def scroll_content(self) -> QWidget:
        return self._scroll_content

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "ScrollPanel",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> ScrollPanel:
        s = ScrollPanel(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 200))
        s._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        s._z_index = data.get("z_index", 0)
        s._tag = data.get("tag", "")
        return s


class MdiSubWindow(QMdiSubWindow):
    def __init__(self, x: float = 0, y: float = 0, w: float = 300, h: float = 200, title: str = "Window", parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiMdiSubWindow")
        self.setWindowTitle(title)
        self.setWidget(QWidget(self))
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "MdiSubWindow", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "title": self.windowTitle(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        m = MdiSubWindow(data.get("x", 0), data.get("y", 0), data.get("w", 300), data.get("h", 200), data.get("title", "Window"))
        m._anchor = data.get("anchor", ANCHOR_TOP_LEFT); m._z_index = data.get("z_index", 0); m._tag = data.get("tag", ""); return m


class MdiArea(QMdiArea):
    def __init__(self, x: float = 0, y: float = 0, w: float = 400, h: float = 300, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiMdiArea")
        _set_widget_bounds(self, x, y, w, h)
    def add_sub_window(self, widget: QWidget, title: str = "Window") -> MdiSubWindow:
        sw = QMdiSubWindow(self)
        sw.setWidget(widget)
        sw.setWindowTitle(title)
        sw.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.addSubWindow(sw)
        return sw
    def tile_windows(self):
        self.tileSubWindows()
    def cascade_windows(self):
        self.cascadeSubWindows()
    def close_all(self):
        self.closeAllSubWindows()
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "MdiArea", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        m = MdiArea(data.get("x", 0), data.get("y", 0), data.get("w", 400), data.get("h", 300))
        m._anchor = data.get("anchor", ANCHOR_TOP_LEFT); m._z_index = data.get("z_index", 0); m._tag = data.get("tag", ""); return m


class ToolBox(QToolBox):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 300, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiToolBox")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "ToolBox", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        t = ToolBox(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 300))
        t._anchor = data.get("anchor", ANCHOR_TOP_LEFT); t._z_index = data.get("z_index", 0); t._tag = data.get("tag", ""); return t
