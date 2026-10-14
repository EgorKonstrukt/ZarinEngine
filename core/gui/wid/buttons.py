# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Any
from PyQt6.QtWidgets import QPushButton, QCheckBox, QRadioButton, QToolButton
from core.gui.wid.base import ANCHOR_TOP_LEFT, _set_widget_bounds, _update_anchor

class Button(QPushButton):
    def __init__(self, x: float = 0, y: float = 0, w: float = 100, h: float = 40, text: str = "Button", parent=None):
        super().__init__(text, parent)
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
        self.setObjectName("GuiButton")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Button",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "text": self.text(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Button:
        b = Button(data.get("x", 0), data.get("y", 0), data.get("w", 100), data.get("h", 40), data.get("text", "Button"))
        b._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        b._z_index = data.get("z_index", 0)
        b._tag = data.get("tag", "")
        return b


class Toggle(QCheckBox):
    def __init__(self, x: float = 0, y: float = 0, w: float = 100, h: float = 30, text: str = "Toggle", parent=None):
        super().__init__(text, parent)
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
        self.setObjectName("GuiToggle")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Toggle",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "text": self.text(), "checked": self.isChecked(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Toggle:
        t = Toggle(data.get("x", 0), data.get("y", 0), data.get("w", 100), data.get("h", 30), data.get("text", "Toggle"))
        t.setChecked(data.get("checked", False))
        t._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        t._z_index = data.get("z_index", 0)
        t._tag = data.get("tag", "")
        return t


class RadioButton(QRadioButton):
    def __init__(self, x: float = 0, y: float = 0, w: float = 100, h: float = 30, text: str = "Radio", parent=None):
        super().__init__(text, parent)
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
        self.setObjectName("GuiRadioButton")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "RadioButton",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "text": self.text(), "checked": self.isChecked(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> RadioButton:
        r = RadioButton(data.get("x", 0), data.get("y", 0), data.get("w", 100), data.get("h", 30), data.get("text", "Radio"))
        r.setChecked(data.get("checked", False))
        r._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        r._z_index = data.get("z_index", 0)
        r._tag = data.get("tag", "")
        return r


class ToolButton(QToolButton):
    def __init__(self, x: float = 0, y: float = 0, w: float = 30, h: float = 30, text: str = "", parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiToolButton")
        _set_widget_bounds(self, x, y, w, h)
        if text: self.setText(text)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "ToolButton", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "text": self.text(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        t = ToolButton(data.get("x", 0), data.get("y", 0), data.get("w", 30), data.get("h", 30), data.get("text", ""))
        t._anchor = data.get("anchor", ANCHOR_TOP_LEFT); t._z_index = data.get("z_index", 0); t._tag = data.get("tag", ""); return t
