# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional
from core.ecs import Component
from core.components.inspector_meta import InspectorField, FieldType


class _BaseWidgetCore(Component):
    _allow_multiple = False
    _show_gizmo_icon = True
    _gizmo_icon_color = (74, 122, 181)
    _gizmo_icon_label = "UI"
    _widget_class = None
    _widget_obj_name = "QWidget"
    _default_text = "Widget"
    _default_w = 120.0
    _default_h = 36.0
    widget_text: str = "Widget"
    widget_width: float = 120.0
    widget_height: float = 36.0
    _anchor: int = 0
    _bg_color: list[float] = None
    _text_color: list[float] = None
    _border_color: list[float] = None
    _border_width: float = 1.0
    _border_radius: float = 4.0
    _font_size: float = 14.0
    _font_bold: bool = False
    _opacity: float = 1.0
    _visible: bool = True

    def __init__(self, **kwargs):
        self._widget_ref = None
        self._sub_window_ref = None
        self.widget_width = float(self._default_w)
        self.widget_height = float(self._default_h)
        self._bg_color = None
        self._text_color = None
        self._border_color = None
        self._border_width = 1.0
        self._border_radius = 4.0
        self._font_size = 14.0
        self._font_bold = False
        self._opacity = 1.0
        self._visible = True
        for k, v in kwargs.items():
            if hasattr(self.__class__, k):
                setattr(self, k, v)

    def _get_zoom(self):
        cr = getattr(self._widget_ref, '_canvas_ref', None) if self._widget_ref else None
        if cr:
            return getattr(cr, '_zoom', 1.0)
        return 1.0

    def _logical_to_screen(self, lx: float, ly: float, lw: float, lh: float):
        zoom = self._get_zoom()
        sx = int(lx * zoom)
        sy = int(ly * zoom)
        sw = max(1, int(lw * zoom))
        sh = max(1, int(lh * zoom))
        return sx, sy, sw, sh

    def _screen_to_logical(self, sx: float, sy: float, sw: float, sh: float):
        zoom = self._get_zoom()
        if zoom == 0:
            zoom = 1.0
        lx = sx / zoom
        ly = sy / zoom
        lw = sw / zoom
        lh = sh / zoom
        return lx, ly, lw, lh

    def _rgb_to_hex(self, rgb: Optional[list[float]]) -> str:
        if not rgb or len(rgb) < 3:
            return ""
        return f"#{int(rgb[0]*255):02x}{int(rgb[1]*255):02x}{int(rgb[2]*255):02x}"

    def serialize(self) -> dict:
        d = super().serialize()
        d["widget_text"] = self.widget_text
        d["widget_width"] = self.widget_width
        d["widget_height"] = self.widget_height
        d["_bg_color"] = self._bg_color
        d["_text_color"] = self._text_color
        d["_border_color"] = self._border_color
        d["_border_width"] = self._border_width
        d["_border_radius"] = self._border_radius
        d["_font_size"] = self._font_size
        d["_font_bold"] = self._font_bold
        d["_opacity"] = self._opacity
        d["_visible"] = self._visible
        d["_anchor"] = self._anchor
        return d

    @classmethod
    def _common_inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Content", FieldType.HEADER),
            InspectorField("widget_text", "Text", FieldType.STRING),
            InspectorField("widget_width", "Width", FieldType.FLOAT, min_val=1, max_val=10000),
            InspectorField("widget_height", "Height", FieldType.FLOAT, min_val=1, max_val=10000),
            InspectorField("", "Layout", FieldType.HEADER),
            InspectorField("_anchor", "Anchor", FieldType.ANCHOR),
            InspectorField("_visible", "Visible", FieldType.BOOL),
            InspectorField("", "Appearance", FieldType.HEADER),
            InspectorField("_bg_color", "BG Color", FieldType.COLOR),
            InspectorField("_text_color", "Text Color", FieldType.COLOR),
            InspectorField("_border_color", "Border", FieldType.COLOR),
            InspectorField("_border_width", "Border W", FieldType.FLOAT, min_val=0, max_val=20),
            InspectorField("_border_radius", "Radius", FieldType.FLOAT, min_val=0, max_val=20),
            InspectorField("_font_size", "Font Size", FieldType.FLOAT, min_val=6, max_val=72),
            InspectorField("_font_bold", "Bold", FieldType.BOOL),
            InspectorField("_opacity", "Opacity", FieldType.FLOAT, min_val=0, max_val=1, step=0.01, decimals=2),
        ]
