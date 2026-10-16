# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Any
from PySide6.QtWidgets import QWidget, QTextBrowser, QCalendarWidget, QLCDNumber, QVBoxLayout
from PySide6.QtGui import QPixmap, QPainter
from core.gui.wid.base import ANCHOR_TOP_LEFT, _set_widget_bounds, _update_anchor

class Image(QWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 100, h: float = 100, source: str = "", parent=None):
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
        self.setObjectName("GuiImage")
        _set_widget_bounds(self, x, y, w, h)
        self._pixmap: Optional[QPixmap] = None
        if source:
            self._pixmap = QPixmap(source)

    @property
    def source(self) -> str:
        return getattr(self, '_source', "")

    @source.setter
    def source(self, v: str):
        self._source = v
        self._pixmap = QPixmap(v) if v else None
        self.update()

    def paintEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            painter.drawPixmap(self.rect(), self._pixmap)
            painter.end()
        else:
            super().paintEvent(event)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Image",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "source": getattr(self, '_source', ""),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Image:
        i = Image(data.get("x", 0), data.get("y", 0), data.get("w", 100), data.get("h", 100),
                  data.get("source", ""))
        i._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        i._z_index = data.get("z_index", 0)
        i._tag = data.get("tag", "")
        return i


class HtmlView(QTextBrowser):
    def __init__(self, x: float = 0, y: float = 0, w: float = 300, h: float = 200, text: str = "", parent=None):
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
        self.setObjectName("GuiHtmlView")
        self.setOpenExternalLinks(True)
        self.setOpenLinks(True)
        _set_widget_bounds(self, x, y, w, h)
        if text:
            self.setHtml(text)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "HtmlView",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "html": self.toHtml(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> HtmlView:
        hv = HtmlView(data.get("x", 0), data.get("y", 0), data.get("w", 300), data.get("h", 200), data.get("html", ""))
        hv._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        hv._z_index = data.get("z_index", 0)
        hv._tag = data.get("tag", "")
        return hv


class Calendar(QCalendarWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 250, h: float = 200, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiCalendar")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "Calendar", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        c = Calendar(data.get("x", 0), data.get("y", 0), data.get("w", 250), data.get("h", 200))
        c._anchor = data.get("anchor", ANCHOR_TOP_LEFT); c._z_index = data.get("z_index", 0); c._tag = data.get("tag", ""); return c


class LCDNumber(QLCDNumber):
    def __init__(self, x: float = 0, y: float = 0, w: float = 120, h: float = 40, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiLCDNumber")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "LCDNumber", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        l = LCDNumber(data.get("x", 0), data.get("y", 0), data.get("w", 120), data.get("h", 40))
        l._anchor = data.get("anchor", ANCHOR_TOP_LEFT); l._z_index = data.get("z_index", 0); l._tag = data.get("tag", ""); return l


class ChartPlotter(QWidget):
    def __init__(self, x: float = 0, y: float = 0, w: float = 320, h: float = 200, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiChart")
        self._chart = None
        self._show_toolbar = False
        self._show_sidebar = False
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        _set_widget_bounds(self, x, y, w, h)

    def chart(self):
        if self._chart is not None:
            return self._chart
        from plugins.plotter_plugin.plotter import ChartWidget
        chart = ChartWidget(parent=self, show_toolbar=self._show_toolbar,
                            show_legend=True, show_sidebar=self._show_sidebar)
        self._lay.addWidget(chart)
        self._chart = chart
        return chart

    def setChartConfig(self, show_toolbar: bool = False, show_sidebar: bool = False):
        if show_toolbar != self._show_toolbar or show_sidebar != self._show_sidebar:
            self._show_toolbar = show_toolbar
            self._show_sidebar = show_sidebar
            chart = self._chart
            if chart is not None:
                chart.setToolbarVisible(show_toolbar)
                chart.setSidebarVisible(show_sidebar)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        chart = self.__dict__.get("_chart")
        if chart is not None:
            try:
                return getattr(chart, name)
            except RuntimeError:
                pass
        raise AttributeError(name)

    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self):
        return {"type": "Chart", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        c = ChartPlotter(data.get("x", 0), data.get("y", 0), data.get("w", 320), data.get("h", 200))
        c._anchor = data.get("anchor", ANCHOR_TOP_LEFT); c._z_index = data.get("z_index", 0); c._tag = data.get("tag", ""); return c
