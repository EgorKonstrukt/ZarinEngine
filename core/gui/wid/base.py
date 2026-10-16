# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen

ANCHOR_TOP_LEFT = 0
ANCHOR_TOP_CENTER = 1
ANCHOR_TOP_RIGHT = 2
ANCHOR_CENTER_LEFT = 3
ANCHOR_CENTER = 4
ANCHOR_CENTER_RIGHT = 5
ANCHOR_BOTTOM_LEFT = 6
ANCHOR_BOTTOM_CENTER = 7
ANCHOR_BOTTOM_RIGHT = 8
ANCHOR_STRETCH_ALL = 9
ANCHOR_STRETCH_WIDTH = 10
ANCHOR_STRETCH_HEIGHT = 11

def _set_widget_bounds(w: QWidget, x: float, y: float, ww: float, h: float):
    w.setGeometry(int(x), int(y), max(1, int(ww)), max(1, int(h)))


def _update_anchor(w: QWidget, anchor: int, canvas_w: float, canvas_h: float,
                   offset_x: float, offset_y: float, gw: float, gh: float) -> tuple[float, float, float, float]:
    x, y, ww, hh = w.x(), w.y(), gw, gh
    if anchor == ANCHOR_TOP_LEFT:
        pass
    elif anchor == ANCHOR_TOP_CENTER:
        x = (canvas_w - ww) / 2 + offset_x
    elif anchor == ANCHOR_TOP_RIGHT:
        x = canvas_w - ww - offset_x
    elif anchor == ANCHOR_CENTER_LEFT:
        y = (canvas_h - hh) / 2 + offset_y
    elif anchor == ANCHOR_CENTER:
        x = (canvas_w - ww) / 2 + offset_x
        y = (canvas_h - hh) / 2 + offset_y
    elif anchor == ANCHOR_CENTER_RIGHT:
        x = canvas_w - ww - offset_x
        y = (canvas_h - hh) / 2 + offset_y
    elif anchor == ANCHOR_BOTTOM_LEFT:
        y = canvas_h - hh - offset_y
    elif anchor == ANCHOR_BOTTOM_CENTER:
        x = (canvas_w - ww) / 2 + offset_x
        y = canvas_h - hh - offset_y
    elif anchor == ANCHOR_BOTTOM_RIGHT:
        x = canvas_w - ww - offset_x
        y = canvas_h - hh - offset_y
    elif anchor == ANCHOR_STRETCH_ALL:
        x = offset_x
        y = offset_y
        ww = canvas_w - offset_x * 2
        hh = canvas_h - offset_y * 2
    elif anchor == ANCHOR_STRETCH_WIDTH:
        x = offset_x
        ww = canvas_w - offset_x * 2
    elif anchor == ANCHOR_STRETCH_HEIGHT:
        y = offset_y
        hh = canvas_h - offset_y * 2
    return x, y, ww, hh

GuiWidget = QWidget

_ANCHOR_NAMES = [
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
    "stretch-all", "stretch-width", "stretch-height",
]

_ANCHOR_LABELS: dict[int, str] = {
    ANCHOR_TOP_LEFT: "Top Left",
    ANCHOR_TOP_CENTER: "Top Center",
    ANCHOR_TOP_RIGHT: "Top Right",
    ANCHOR_CENTER_LEFT: "Center Left",
    ANCHOR_CENTER: "Center",
    ANCHOR_CENTER_RIGHT: "Center Right",
    ANCHOR_BOTTOM_LEFT: "Bottom Left",
    ANCHOR_BOTTOM_CENTER: "Bottom Center",
    ANCHOR_BOTTOM_RIGHT: "Bottom Right",
    ANCHOR_STRETCH_ALL: "Stretch All",
    ANCHOR_STRETCH_WIDTH: "Stretch Width",
    ANCHOR_STRETCH_HEIGHT: "Stretch Height",
}

class AnchorPresetSelector(QWidget):
    anchor_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anchor = ANCHOR_TOP_LEFT
        self._cell_size = 18
        self._gap = 2
        w = self._cell_size * 3 + self._gap * 2
        h = self._cell_size * 4 + self._gap * 3
        self.setFixedSize(w + 12, h + 12)
        self.setMouseTracking(True)
        self._hovered = -1

    def set_anchor(self, value: int):
        if value != self._anchor:
            self._anchor = value
            self.update()

    @property
    def anchor(self) -> int:
        return self._anchor

    def _cell_rect(self, idx: int) -> tuple[int, int, int, int]:
        col = idx % 3
        row = idx // 3
        x = 6 + col * (self._cell_size + self._gap)
        y = 6 + row * (self._cell_size + self._gap)
        return x, y, self._cell_size, self._cell_size

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor("#2d2d2d")
        selected_color = QColor("#4a7ab5")
        hover_color = QColor("#3a5a8a")
        empty_color = QColor("#444")
        text_color = QColor("#aaa")
        for i in range(9):
            rx, ry, rw, rh = self._cell_rect(i)
            if i == self._anchor:
                p.setBrush(selected_color)
                p.setPen(Qt.PenStyle.NoPen)
            elif i == self._hovered:
                p.setBrush(hover_color)
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.setBrush(empty_color)
                p.setPen(QPen(QColor("#555"), 1))
            p.drawRoundedRect(rx, ry, rw, rh, 2, 2)
        for i in range(9, 12):
            rx, ry, rw, rh = self._cell_rect(i)
            if i == self._anchor:
                p.setBrush(selected_color)
            elif i == self._hovered:
                p.setBrush(hover_color)
            else:
                p.setBrush(empty_color)
            p.setPen(QPen(QColor("#555"), 1))
            p.drawRoundedRect(rx, ry, rw, rh, 2, 2)
            label = _ANCHOR_NAMES[i].split("-")[-1]
            p.setPen(text_color)
            p.setFont(self.font())
            p.drawText(rx + 2, ry, rw - 2, rh, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        label = _ANCHOR_LABELS.get(self._anchor, "")
        if label:
            p.setPen(QColor("#ddd"))
            p.setFont(self.font())
            p.drawText(6, self.height() - 14, self.width() - 12, 14,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"Anchor: {label}")
        p.end()

    def mousePressEvent(self, event):
        mx, my = event.position().x(), event.position().y()
        for i in range(12):
            rx, ry, rw, rh = self._cell_rect(i)
            if rx <= mx <= rx + rw and ry <= my <= ry + rh:
                self._anchor = i
                self.anchor_changed.emit(i)
                self.update()
                return

    def mouseMoveEvent(self, event):
        mx, my = event.position().x(), event.position().y()
        old = self._hovered
        self._hovered = -1
        for i in range(12):
            rx, ry, rw, rh = self._cell_rect(i)
            if rx <= mx <= rx + rw and ry <= my <= ry + rh:
                self._hovered = i
                break
        if old != self._hovered:
            self.update()

_WIDGET_BASE_STYLES: dict[str, str] = {
    'GuiButton': 'background-color: #4a7ab5; color: #fff; border: 1px solid #5a8ac5; border-radius: 4px; padding: 4px 12px; font-size: 13px;',
    'GuiCalendar': 'background: #1e1e1e; color: #ddd; border: 1px solid #555;',
    'GuiChart': 'background: #1e1e1e; border: 1px solid #555;',
    'GuiDial': 'background: transparent;',
    'GuiDoubleSpinBox': 'background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; font-size: 13px;',
    'GuiDropdown': 'background-color: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; padding: 4px 6px; font-size: 13px;',
    'GuiFontCombo': 'background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; padding: 2px 4px; font-size: 12px;',
    'GuiGroupBox': 'color: #ddd; border: 1px solid #555; border-radius: 4px; font-size: 13px;',
    'GuiHtmlView': 'background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; font-size: 13px;',
    'GuiImage': 'background: transparent; border: none;',
    'GuiLCDNumber': 'color: #55ff55; background: #1a1a1a; border: 1px solid #555; padding: 4px; font-size: 20px;',
    'GuiLabel': 'color: #ddd; background: transparent; border: none; padding: 2px; font-size: 13px;',
    'GuiListWidget': 'background: #1e1e1e; color: #ddd; border: 1px solid #555;',
    'GuiMdiArea': 'background: #1e1e1e; border: 1px solid #555;',
    'GuiMdiSubWindow': 'background: #2d2d2d; color: #ddd;',
    'GuiPanel': 'background: rgba(55, 55, 65, 90); border: 1px solid #555;',
    'GuiPlainText': 'background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; font-size: 13px;',
    'GuiProgressBar': 'border: 1px solid #555; border-radius: 3px; text-align: center; color: #ddd; background: #333; font-size: 11px;',
    'GuiRadioButton': 'color: #ddd; spacing: 6px; font-size: 13px;',
    'GuiScrollBar': 'background: #2d2d2d; border: 1px solid #555;',
    'GuiScrollPanel': 'border: 1px solid #555; border-radius: 4px; background: #2d2d2d;',
    'GuiSlider': 'border: 1px solid #555; border-radius: 3px; background: #3a3a3a;',
    'GuiSpinBox': 'background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; font-size: 13px;',
    'GuiSplitter': 'border: 1px solid #555; background: #2d2d2d;',
    'GuiStackedWidget': 'background: #2d2d2d; border: 1px solid #555;',
    'GuiTabWidget': 'background: #2d2d2d;',
    'GuiTableWidget': 'background: #1e1e1e; color: #ddd; border: 1px solid #555;',
    'GuiTextEdit': 'background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; font-size: 13px;',
    'GuiTextInput': 'background-color: #1e1e1e; color: #fff; border: 1px solid #555; border-radius: 3px; padding: 4px 6px; font-size: 13px;',
    'GuiToggle': 'color: #ddd; spacing: 6px; font-size: 13px;',
    'GuiToolBox': 'background: #2d2d2d; border: 1px solid #555;',
    'GuiToolButton': 'background-color: #4a4a4a; color: #ddd; border: 1px solid #666; border-radius: 3px; padding: 2px 6px; font-size: 12px;',
    'GuiTreeWidget': 'background: #1e1e1e; color: #ddd; border: 1px solid #555;',
}

_WIDGET_EXTRA_RULES: dict[str, list[str]] = {
    'GuiButton': ['QPushButton#GuiButton:hover { background-color: #5a8ac5; }', 'QPushButton#GuiButton:pressed { background-color: #3a6aa5; }'],
    'GuiCalendar': ['QCalendarWidget QWidget { background: #1e1e1e; color: #ddd; }', 'QCalendarWidget QToolButton { color: #ddd; background: #333; border: 1px solid #555; padding: 4px; }'],
    'GuiDial': ['QDial#GuiDial { background: transparent; }'],
    'GuiDoubleSpinBox': ['QDoubleSpinBox#GuiDoubleSpinBox { background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; padding: 2px 4px; font-size: 13px; }', 'QDoubleSpinBox#GuiDoubleSpinBox::up-button { border-left: 1px solid #555; width: 16px; }', 'QDoubleSpinBox#GuiDoubleSpinBox::down-button { border-left: 1px solid #555; width: 16px; }'],
    'GuiDropdown': ['QComboBox#GuiDropdown::drop-down { border: none; width: 20px; }', 'QComboBox#GuiDropdown QAbstractItemView { background: #2d2d2d; color: #ddd; selection-background-color: #4a7ab5; }'],
    'GuiFontCombo': ['QFontComboBox#GuiFontCombo { background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; padding: 2px 4px; }', 'QFontComboBox#GuiFontCombo::drop-down { border: none; width: 18px; }', 'QFontComboBox#GuiFontCombo QAbstractItemView { background: #2d2d2d; color: #ddd; selection-background-color: #4a7ab5; }'],
    'GuiGroupBox': ['QGroupBox#GuiGroupBox { color: #ddd; border: 1px solid #555; border-radius: 4px; margin-top: 8px; padding-top: 12px; font-size: 13px; }', 'QGroupBox#GuiGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }'],
    'GuiHtmlView': ['QTextBrowser#GuiHtmlView { background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; padding: 4px; font-size: 13px; }'],
    'GuiListWidget': ['QListWidget#GuiListWidget { background: #1e1e1e; color: #ddd; border: 1px solid #555; outline: none; }', 'QListWidget#GuiListWidget::item:selected { background: #4a7ab5; }'],
    'GuiMdiArea': ['QMdiArea#GuiMdiArea { background: #1e1e1e; border: none; }'],
    'GuiMdiSubWindow': ['QMdiSubWindow#GuiMdiSubWindow { background: #2d2d2d; color: #ddd; }'],
    'GuiProgressBar': ['QProgressBar::chunk { background-color: #4a7ab5; border-radius: 2px; }'],
    'GuiRadioButton': ['QRadioButton#GuiRadioButton { color: #ddd; spacing: 6px; font-size: 13px; }'],
    'GuiScrollBar': ['QScrollBar:horizontal { border: none; background: #2d2d2d; height: 12px; }', 'QScrollBar::handle:horizontal { background: #555; min-width: 20px; border-radius: 3px; }', 'QScrollBar:vertical { border: none; background: #2d2d2d; width: 12px; }', 'QScrollBar::handle:vertical { background: #555; min-height: 20px; border-radius: 3px; }'],
    'GuiSlider': ['QSlider::groove:horizontal { border: 1px solid #555; height: 6px; background: #3a3a3a; border-radius: 3px; }', 'QSlider::handle:horizontal { background: #ddd; border: 1px solid #aaa; width: 12px; margin: -4px 0; border-radius: 4px; }', 'QSlider::sub-page:horizontal { background: #4a7ab5; border-radius: 3px; }'],
    'GuiSpinBox': ['QSpinBox#GuiSpinBox { background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; padding: 2px 4px; font-size: 13px; }', 'QSpinBox#GuiSpinBox::up-button { border-left: 1px solid #555; width: 16px; }', 'QSpinBox#GuiSpinBox::down-button { border-left: 1px solid #555; width: 16px; }'],
    'GuiSplitter': ['QSplitter::handle { background: #444; }', 'QSplitter::handle:horizontal { width: 4px; }', 'QSplitter::handle:vertical { height: 4px; }'],
    'GuiTabWidget': ['QTabWidget#GuiTabWidget::pane { border: 1px solid #555; background: #2d2d2d; }', 'QTabBar::tab { background: #333; color: #aaa; border: 1px solid #555; padding: 6px 12px; }', 'QTabBar::tab:selected { background: #4a7ab5; color: #fff; }'],
    'GuiTableWidget': ['QTableWidget#GuiTableWidget { background: #1e1e1e; color: #ddd; border: 1px solid #555; gridline-color: #444; }', 'QTableWidget#GuiTableWidget::item:selected { background: #4a7ab5; }', 'QHeaderView::section { background: #2d2d2d; color: #ccc; border: 1px solid #444; padding: 3px; }'],
    'GuiTextEdit': ['QTextEdit#GuiTextEdit { background: #1e1e1e; color: #ddd; border: 1px solid #555; border-radius: 3px; padding: 4px; font-size: 13px; }'],
    'GuiToolBox': ['QToolBox::tab { background: #333; color: #ddd; border: 1px solid #555; padding: 4px 8px; }', 'QToolBox::tab:selected { background: #4a7ab5; color: #fff; }'],
    'GuiToolButton': ['QToolButton#GuiToolButton:hover { background-color: #5a5a5a; }', 'QToolButton#GuiToolButton:pressed { background-color: #3a3a3a; }'],
    'GuiTreeWidget': ['QTreeWidget#GuiTreeWidget { background: #1e1e1e; color: #ddd; border: 1px solid #555; outline: none; }', 'QTreeWidget#GuiTreeWidget::item:selected { background: #4a7ab5; }'],
}

def get_widget_base_style(object_name: str) -> str:
    return _WIDGET_BASE_STYLES.get(object_name, "")


def get_widget_extra_rules(object_name: str) -> list[str]:
    return _WIDGET_EXTRA_RULES.get(object_name, [])


def get_widget_type_for_object(obj_name: str) -> str:
    TYPE_MAP = {
        "GuiPanel": "QWidget", "GuiLabel": "QLabel", "GuiButton": "QPushButton",
        "GuiSlider": "QSlider", "GuiTextInput": "QLineEdit", "GuiToggle": "QCheckBox",
        "GuiProgressBar": "QProgressBar", "GuiDropdown": "QComboBox",
        "GuiScrollPanel": "QScrollArea", "GuiImage": "QWidget",
        "GuiRadioButton": "QRadioButton", "GuiListWidget": "QListWidget",
        "GuiTableWidget": "QTableWidget", "GuiTreeWidget": "QTreeWidget",
        "GuiTabWidget": "QTabWidget", "GuiGroupBox": "QGroupBox",
        "GuiSpinBox": "QSpinBox", "GuiDoubleSpinBox": "QDoubleSpinBox",
        "GuiTextEdit": "QTextEdit", "GuiHtmlView": "QTextBrowser", "GuiDial": "QDial",
        "GuiSplitter": "QSplitter", "GuiStackedWidget": "QStackedWidget",
        "GuiToolBox": "QToolBox", "GuiCalendar": "QCalendarWidget",
        "GuiLCDNumber": "QLCDNumber", "GuiPlainText": "QPlainTextEdit",
        "GuiScrollBar": "QScrollBar", "GuiToolButton": "QToolButton",
        "GuiFontCombo": "QFontComboBox",
"GuiMdiArea": "QMdiArea", "GuiMdiSubWindow": "QMdiSubWindow",
        "GuiChart": "QWidget",
    }
    return TYPE_MAP.get(obj_name, "QWidget")

def apply_fusion_style(widget: QWidget):
    widget.setStyleSheet('\n        QWidget#GuiPanel {\n            background: rgba(55, 55, 65, 90);\n            border: 1px solid #555;\n        }\n        QLabel#GuiLabel {\n            color: #ddd;\n            background: transparent;\n            border: none;\n            padding: 2px;\n        }\n        QPushButton#GuiButton {\n            background-color: #4a7ab5;\n            color: #fff;\n            border: 1px solid #5a8ac5;\n            border-radius: 4px;\n            padding: 4px 12px;\n            font-size: 13px;\n        }\n        QPushButton#GuiButton:hover {\n            background-color: #5a8ac5;\n        }\n        QPushButton#GuiButton:pressed {\n            background-color: #3a6aa5;\n        }\n        QSlider::groove:horizontal {\n            border: 1px solid #555;\n            height: 6px;\n            background: #3a3a3a;\n            border-radius: 3px;\n        }\n        QSlider::handle:horizontal {\n            background: #ddd;\n            border: 1px solid #aaa;\n            width: 12px;\n            margin: -4px 0;\n            border-radius: 4px;\n        }\n        QSlider::sub-page:horizontal {\n            background: #4a7ab5;\n            border-radius: 3px;\n        }\n        QLineEdit#GuiTextInput {\n            background-color: #1e1e1e;\n            color: #fff;\n            border: 1px solid #555;\n            border-radius: 3px;\n            padding: 4px 6px;\n        }\n        QCheckBox#GuiToggle {\n            color: #ddd;\n            spacing: 6px;\n        }\n        QProgressBar#GuiProgressBar {\n            border: 1px solid #555;\n            border-radius: 3px;\n            text-align: center;\n            color: #ddd;\n            background: #333;\n        }\n        QProgressBar#GuiProgressBar::chunk {\n            background-color: #4a7ab5;\n            border-radius: 2px;\n        }\n        QComboBox#GuiDropdown {\n            background-color: #1e1e1e;\n            color: #ddd;\n            border: 1px solid #555;\n            border-radius: 3px;\n            padding: 4px 6px;\n        }\n        QComboBox#GuiDropdown::drop-down {\n            border: none;\n            width: 20px;\n        }\n        QComboBox#GuiDropdown QAbstractItemView {\n            background: #2d2d2d;\n            color: #ddd;\n            selection-background-color: #4a7ab5;\n        }\n        QScrollArea#GuiScrollPanel {\n            border: 1px solid #555;\n            border-radius: 4px;\n            background: #2d2d2d;\n        }\n        QRadioButton#GuiRadioButton {\n            color: #ddd;\n            spacing: 6px;\n            font-size: 13px;\n        }\n        QListWidget#GuiListWidget {\n            background: #1e1e1e;\n            color: #ddd;\n            border: 1px solid #555;\n            outline: none;\n        }\n        QListWidget#GuiListWidget::item:selected {\n            background: #4a7ab5;\n        }\n        QTableWidget#GuiTableWidget {\n            background: #1e1e1e;\n            color: #ddd;\n            border: 1px solid #555;\n            gridline-color: #444;\n        }\n        QTableWidget#GuiTableWidget::item:selected {\n            background: #4a7ab5;\n        }\n        QHeaderView::section {\n            background: #2d2d2d;\n            color: #ccc;\n            border: 1px solid #444;\n            padding: 3px;\n        }\n        QTreeWidget#GuiTreeWidget {\n            background: #1e1e1e;\n            color: #ddd;\n            border: 1px solid #555;\n            outline: none;\n        }\n        QTreeWidget#GuiTreeWidget::item:selected {\n            background: #4a7ab5;\n        }\n        QTabWidget#GuiTabWidget::pane {\n            border: 1px solid #555;\n            background: #2d2d2d;\n        }\n        QTabBar::tab {\n            background: #333;\n            color: #aaa;\n            border: 1px solid #555;\n            padding: 6px 12px;\n        }\n        QTabBar::tab:selected {\n            background: #4a7ab5;\n            color: #fff;\n        }\n        QGroupBox#GuiGroupBox {\n            color: #ddd;\n            border: 1px solid #555;\n            border-radius: 4px;\n            margin-top: 8px;\n            padding-top: 12px;\n            font-size: 13px;\n        }\n        QGroupBox#GuiGroupBox::title {\n            subcontrol-origin: margin;\n            left: 8px;\n            padding: 0 4px;\n        }\n        QSpinBox#GuiSpinBox {\n            background: #1e1e1e;\n            color: #ddd;\n            border: 1px solid #555;\n            border-radius: 3px;\n            padding: 2px 4px;\n            font-size: 13px;\n        }\n        QSpinBox#GuiSpinBox::up-button {\n            border-left: 1px solid #555;\n            width: 16px;\n        }\n        QSpinBox#GuiSpinBox::down-button {\n            border-left: 1px solid #555;\n            width: 16px;\n        }\n        QDoubleSpinBox#GuiDoubleSpinBox {\n            background: #1e1e1e;\n            color: #ddd;\n            border: 1px solid #555;\n            border-radius: 3px;\n            padding: 2px 4px;\n            font-size: 13px;\n        }\n        QDoubleSpinBox#GuiDoubleSpinBox::up-button {\n            border-left: 1px solid #555;\n            width: 16px;\n        }\n        QDoubleSpinBox#GuiDoubleSpinBox::down-button {\n            border-left: 1px solid #555;\n            width: 16px;\n        }\n        QTextEdit#GuiTextEdit {\n            background: #1e1e1e;\n            color: #ddd;\n            border: 1px solid #555;\n            border-radius: 3px;\n            padding: 4px;\n            font-size: 13px;\n        }\n        QDial#GuiDial {\n            background: transparent;\n        }\n    ')
