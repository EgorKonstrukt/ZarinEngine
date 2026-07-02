# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from PyQt6.QtGui import QColor, QFont


@dataclass
class Style:
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    border_color: Optional[str] = None
    border_width: int = 1
    border_radius: int = 4
    font_size: int = 14
    font_family: str = "Segoe UI"
    font_bold: bool = False
    opacity: float = 1.0
    padding: int = 4
    margin: int = 0
    bg_hover: Optional[str] = None
    text_hover: Optional[str] = None
    bg_pressed: Optional[str] = None
    bg_disabled: Optional[str] = None
    text_disabled: Optional[str] = None

    def to_qcolor(self, color_str: str) -> QColor:
        if color_str.startswith("#"):
            return QColor(color_str)
        parts = color_str.replace("rgba(", "").replace(")", "").split(",")
        if len(parts) == 4:
            return QColor(int(parts[0]), int(parts[1]), int(parts[2]), int(float(parts[3]) * 255))
        if len(parts) == 3:
            return QColor(int(parts[0]), int(parts[1]), int(parts[2]))
        return QColor(100, 100, 100)

    def copy(self) -> Style:
        return Style(
            bg_color=self.bg_color,
            text_color=self.text_color,
            border_color=self.border_color,
            border_width=self.border_width,
            border_radius=self.border_radius,
            font_size=self.font_size,
            font_family=self.font_family,
            font_bold=self.font_bold,
            opacity=self.opacity,
            padding=self.padding,
            margin=self.margin,
            bg_hover=self.bg_hover,
            text_hover=self.text_hover,
            bg_pressed=self.bg_pressed,
            bg_disabled=self.bg_disabled,
            text_disabled=self.text_disabled,
        )

    def serialize(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @staticmethod
    def deserialize(data: dict) -> Style:
        return Style(**{k: v for k, v in data.items() if hasattr(Style, k)})


class Stylesheet:
    @staticmethod
    def default_button() -> Style:
        return Style(
            bg_color="#4a7ab5",
            text_color="#ffffff",
            border_color="#5a8ac5",
            border_width=1,
            border_radius=4,
            font_size=14,
            bg_hover="#5a8ac5",
            bg_pressed="#3a6aa5",
        )

    @staticmethod
    def default_panel() -> Style:
        return Style(
            bg_color="#2d2d2d",
            border_color="#444444",
            border_width=1,
            border_radius=4,
        )

    @staticmethod
    def default_label() -> Style:
        return Style(
            text_color="#dddddd",
            font_size=14,
        )

    @staticmethod
    def default_slider() -> Style:
        return Style(
            bg_color="#3a3a3a",
            text_color="#dddddd",
            border_color="#555555",
            border_radius=2,
        )

    @staticmethod
    def default_input() -> Style:
        return Style(
            bg_color="#1e1e1e",
            text_color="#ffffff",
            border_color="#555555",
            border_radius=3,
            padding=6,
        )

    @staticmethod
    def default_toggle() -> Style:
        return Style(
            bg_color="#3a3a3a",
            text_color="#dddddd",
            border_color="#555555",
            bg_hover="#4a7ab5",
            border_radius=3,
        )
