# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Any
from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QTextEdit
from core.gui.wid.base import ANCHOR_TOP_LEFT, _set_widget_bounds, _update_anchor

class Label(QLabel):
    def __init__(self, x: float = 0, y: float = 0, w: float = 100, h: float = 30, text: str = "Label", parent=None):
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
        self.setObjectName("GuiLabel")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "Label",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "text": self.text(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> Label:
        l = Label(data.get("x", 0), data.get("y", 0), data.get("w", 100), data.get("h", 30), data.get("text", "Label"))
        l._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        l._z_index = data.get("z_index", 0)
        l._tag = data.get("tag", "")
        return l


class TextInput(QLineEdit):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 36, placeholder: str = "", parent=None):
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
        self.setObjectName("GuiTextInput")
        self.setPlaceholderText(placeholder)
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "TextInput",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "text": self.text(), "placeholder": self.placeholderText(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> TextInput:
        t = TextInput(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 36),
                      data.get("placeholder", ""))
        t.setText(data.get("text", ""))
        t._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        t._z_index = data.get("z_index", 0)
        t._tag = data.get("tag", "")
        return t


class PlainText(QPlainTextEdit):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 150, text: str = "", parent=None):
        super().__init__(text, parent)
        self._anchor = ANCHOR_TOP_LEFT; self._anchor_offset_x = 0.0; self._anchor_offset_y = 0.0
        self._z_index = 0; self._tag = ""; self._widget_id: Optional[str] = None
        self._canvas_ref: Optional[Any] = None; self._canvas_size = (800, 600)
        self._orig_w = w; self._orig_h = h; self.setObjectName("GuiPlainText")
        _set_widget_bounds(self, x, y, w, h)
    def update_anchor(self, canvas_w, canvas_h):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h, self._anchor_offset_x, self._anchor_offset_y, self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)
    def serialize(self):
        return {"type": "PlainText", "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "text": self.toPlainText(), "anchor": self._anchor, "z_index": self._z_index, "tag": self._tag}
    @staticmethod
    def deserialize(data):
        p = PlainText(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 150), data.get("text", ""))
        p._anchor = data.get("anchor", ANCHOR_TOP_LEFT); p._z_index = data.get("z_index", 0); p._tag = data.get("tag", ""); return p


class TextEdit(QTextEdit):
    def __init__(self, x: float = 0, y: float = 0, w: float = 200, h: float = 150, text: str = "", parent=None):
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
        self.setObjectName("GuiTextEdit")
        _set_widget_bounds(self, x, y, w, h)

    def update_anchor(self, canvas_w: float, canvas_h: float):
        nx, ny, nw, nh = _update_anchor(self, self._anchor, canvas_w, canvas_h,
                                         self._anchor_offset_x, self._anchor_offset_y,
                                         self._orig_w, self._orig_h)
        _set_widget_bounds(self, nx, ny, nw, nh)

    def serialize(self) -> dict:
        return {
            "type": "TextEdit",
            "x": self.x(), "y": self.y(),
            "w": self.width(), "h": self.height(),
            "text": self.toPlainText(),
            "anchor": self._anchor,
            "z_index": self._z_index,
            "tag": self._tag,
        }

    @staticmethod
    def deserialize(data: dict) -> TextEdit:
        te = TextEdit(data.get("x", 0), data.get("y", 0), data.get("w", 200), data.get("h", 150), data.get("text", ""))
        te._anchor = data.get("anchor", ANCHOR_TOP_LEFT)
        te._z_index = data.get("z_index", 0)
        te._tag = data.get("tag", "")
        return te
