# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QScrollArea, QFrame, QLineEdit, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from core.config.editor_scale import scale


_CATEGORY_COLORS: dict[str, str] = {
    "Generator": "#2d5a3a",
    "Uv Modifier": "#5a3a5a",
    "Modifier": "#7a5a3a",
    "Math": "#4a7ab5",
    "Output": "#b55a3a",
    "Input": "#4a7ab5",
    "Texture": "#5a3a5a",
    "Vector": "#3a5a5a",
    "Container": "#3a3a3a",
    "Display": "#2d5a3a",
    "Layout": "#2a4a3a",
}


def category_color(name: str) -> str:
    if name in _CATEGORY_COLORS:
        return _CATEGORY_COLORS[name]
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    r = 58 + (h % 52)
    g = 74 + ((h >> 8) % 52)
    b = 58 + ((h >> 16) % 62)
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(hex_color: str) -> str:
    c = QColor(hex_color)
    return f"#{min(255, c.red() + 35):02x}{min(255, c.green() + 35):02x}{min(255, c.blue() + 35):02x}"


class NodePaletteButton(QPushButton):
    def __init__(self, text: str, node_key: str, color: str, tooltip: str, parent=None):
        super().__init__(text, parent)
        self._node_key = node_key
        self._color = color
        self.setFixedHeight(scale(28))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 10px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {_lighten(color)};
                border: 1px solid #4a7ab5;
            }}
            QPushButton:pressed {{
                background-color: {color};
                border: 1px solid #4a7ab5;
            }}
        """)

    @property
    def node_key(self) -> str:
        return self._node_key


class NodePalette(QFrame):
    node_chosen = pyqtSignal(str)

    def __init__(self, parent=None, title: str = "Node Palette", placeholder: str = "Search nodes...", categories: dict | None = None):
        super().__init__(parent)
        self.setMinimumWidth(scale(180))
        self.setMaximumWidth(scale(220))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._all_items: list[tuple[str, str, str, str]] = []
        self._buttons: list[NodePaletteButton] = []
        self._sections: list[QWidget] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #bbb; font-weight: bold; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(title_label)
        self._search = QLineEdit()
        self._search.setPlaceholderText(placeholder)
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e; color: #ccc; border: 1px solid #444;
                border-radius: 3px; padding: 3px 6px; font-size: 10px;
            }
        """)
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setSpacing(2)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_area.setWidget(self._scroll_content)
        layout.addWidget(self._scroll_area)
        if categories:
            self.set_categories(categories)

    def set_categories(self, categories: dict[str, list[tuple]]):
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._all_items = []
        self._buttons = []
        self._sections = []
        for cat_name, nodes in categories.items():
            section = QLabel(cat_name)
            section.setStyleSheet("color: #777; font-size: 9px; padding: 4px 4px 1px 4px;")
            section.setProperty("palette_category", cat_name)
            self._scroll_layout.addWidget(section)
            self._sections.append(section)
            color = category_color(cat_name)
            for entry in nodes:
                if len(entry) == 3:
                    display_name, key, tip = entry
                    btn_color = color
                elif len(entry) == 4:
                    display_name, key, tip, btn_color = entry
                else:
                    display_name, key = entry[0], entry[1]
                    tip = f"Add {display_name} node"
                    btn_color = color
                self._all_items.append((display_name, key, tip, cat_name))
                btn = NodePaletteButton(display_name, key, btn_color, tip)
                btn.clicked.connect(lambda checked=False, k=key: self.node_chosen.emit(k))
                self._scroll_layout.addWidget(btn)
                self._buttons.append(btn)
                btn.setProperty("palette_category", cat_name)
        self._scroll_layout.addStretch()
        self._filter(self._search.text() if hasattr(self, "_search") else "")

    def _filter(self, text: str):
        query = text.lower().strip()
        for (display_name, key, tip, cat), btn in zip(self._all_items, self._buttons):
            if not query:
                btn.setVisible(True)
            else:
                btn.setVisible(query in display_name.lower() or query in tip.lower() or query in key.lower() or query in cat.lower())
        visible_per_cat: dict[str, bool] = {}
        for (_, _, _, cat), btn in zip(self._all_items, self._buttons):
            if btn.isVisible():
                visible_per_cat[cat] = True
        for section in self._sections:
            cat = section.property("palette_category")
            section.setVisible(visible_per_cat.get(cat, False))
