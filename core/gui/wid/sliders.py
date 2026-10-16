# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSlider, QScrollBar, QProgressBar, QDial, QSpinBox, QDoubleSpinBox
from core.gui.wid.base import ANCHOR_TOP_LEFT, _set_widget_bounds, _update_anchor

class Slider(QSlider):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 30, min_val: int = 0, max_val: int = 100, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
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
        self.setObjectName("GuiSlider")
        self.setRange(min_val, max_val)
        self.setValue(0)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Slider",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "min": self.minimum(), "max": self.maximum(), "value": self.value(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Slider:
        s = Slider(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 30),
                   data.get("min", 0), data.get("max", 100))
        s.setValue(data.get("value", 0))
        s._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        s._z_index = data.get("z_index", 0)
        s._tag = data.get("tag", "")
        return s


class ScrollBar(QScrollBar):
    def __init__(self, x: float = 0, y: float = 0, w: float = 120, h: float = 20, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiScrollBar")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "ScrollBar", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        s = ScrollBar(data.get("x", 0), data.get("y", 0), data.get("w", 120), data.get("h", 20))
        s._anchor = data.get("anchor", ANCHOR_TOP_LEFT); s._z_index = data.get("z_index", 0); s._tag = data.get("tag", ""); return s


class ProgressBar(QProgressBar):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 24, min_val: int = 0, max_val: int = 100, parent=None):
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
        self.setObjectName("GuiProgressBar")
        self.setRange(min_val, max_val)
        self.setValue(0)
        self.setTextVisible(True)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "ProgressBar",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "min": self.minimum(), "max": self.maximum(), "value": self.value(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> ProgressBar:
        p = ProgressBar(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 24),
                        data.get("min", 0), data.get("max", 100))
        p.setValue(data.get("value", 0))
        p._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        p._z_index = data.get("z_index", 0)
        p._tag = data.get("tag", "")
        return p


class Dial(QDial):
    def __init__(self, x: float = 0, y: float = 0, w: float = 80, h: float = 80,
                 min_val: int = 0, max_val: int = 100, parent=None):
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
        self.setObjectName("GuiDial")
        self.setRange(min_val, max_val)
        self.setWrapping(False)
        self.setNotchesVisible(True)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Dial",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "min": self.minimum(), "max": self.maximum(), "value": self.value(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Dial:
        d = Dial(data.get("x", 0), data.get("y", 0), data.get("w", 80), data.get("h", 80),
                data.get("min", 0), data.get("max", 100))
        d.setValue(data.get("value", 0))
        d._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        d._z_index = data.get("z_index", 0)
        d._tag = data.get("tag", "")
        return d


class SpinBox(QSpinBox):
    def __init__(self, x: float = 0, y: float = 0, w: float = 100, h: float = 32,
                 min_val: int = 0, max_val: int = 100, parent=None):
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
        self.setObjectName("GuiSpinBox")
        self.setRange(min_val, max_val)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "SpinBox",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "min": self.minimum(), "max": self.maximum(), "value": self.value(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> SpinBox:
        sb = SpinBox(data.get("x", 0), data.get("y", 0), data.get("w", 100), data.get("h", 32),
                     data.get("min", 0), data.get("max", 100))
        sb.setValue(data.get("value", 0))
        sb._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        sb._z_index = data.get("z_index", 0)
        sb._tag = data.get("tag", "")
        return sb


class DoubleSpinBox(QDoubleSpinBox):
    def __init__(self, x: float = 0, y: float = 0, w: float = 120, h: float = 32,
                 min_val: float = 0.0, max_val: float = 100.0, decimals: int = 2, parent=None):
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
        self.setObjectName("GuiDoubleSpinBox")
        self.setRange(min_val, max_val)
        self.setDecimals(decimals)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "DoubleSpinBox",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "min": self.minimum(), "max": self.maximum(),
            "value": self.value(), "decimals": self.decimals(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> DoubleSpinBox:
        dsb = DoubleSpinBox(data.get("x", 0), data.get("y", 0), data.get("w", 120), data.get("h", 32),
                           data.get("min", 0.0), data.get("max", 100.0), data.get("decimals", 2))
        dsb.setValue(data.get("value", 0.0))
        dsb._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        dsb._z_index = data.get("z_index", 0)
        dsb._tag = data.get("tag", "")
        return dsb
