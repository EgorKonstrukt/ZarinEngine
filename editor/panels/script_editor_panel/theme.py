# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont


def rgb(r: int, g: int, b: int) -> QColor:
    return QColor(r, g, b)


class Theme:
    background = (30, 30, 30)
    gutter = (24, 24, 24)
    gutter_current = (34, 34, 34)
    current_line = (27, 60, 150)
    selection = (38, 79, 120)
    line_number = (90, 90, 90)
    line_number_current = (200, 200, 200)
    indent_guide = (47, 47, 47)
    indent_guide_active = (107, 140, 179)
    lens = (120, 130, 140)
    lens_green = (110, 180, 110)
    lens_blue = (70, 140, 200)
    warn_yellow = (255, 180, 0)
    warn_wave = (255, 204, 0)
    error_red = (255, 80, 80)
    error_stripe = (200, 60, 60)
    added = (60, 155, 60)
    modified = (60, 110, 155)
    deleted = (155, 60, 60)
    stripe_bg = (22, 22, 22)
    viewport_indicator = (58, 110, 165)
    doc_bg = (32, 28, 48)
    doc_border = (80, 80, 80)
    doc_text = (220, 220, 220)
    keyword = (204, 120, 50)
    string = (106, 135, 89)
    number = (104, 151, 187)
    comment = (128, 128, 128)
    decorator = (185, 185, 80)
    function = (255, 198, 109)
    builtin = (136, 136, 198)
    exception = (104, 151, 187)
    link = (104, 151, 187)


def editor_stylesheet() -> str:
    return (
        "QPlainTextEdit { "
        "background: rgb(30,30,30); color: rgb(212,212,212); "
        "font-family: JetBrains Mono, Consolas, monospace; "
        "border: none; "
        "selection-background-color: rgb(38,79,120); "
        "}"
    )


def tab_stylesheet() -> str:
    return (
        "QTabWidget::pane { border: none; background: rgb(30,30,30); } "
        "QTabBar::tab { background: rgb(37,37,38); color: rgb(212,212,212); "
        "padding: 4px 10px; border: 1px solid rgb(30,30,30); border-bottom: none; } "
        "QTabBar::tab:selected { background: rgb(30,30,30); } "
        "QTabBar::tab:hover { background: rgb(42,45,46); }"
    )


def menubar_stylesheet() -> str:
    return (
        "QMenuBar { background: rgb(31,31,31); color: rgb(212,212,212); "
        "spacing: 2px; padding: 1px; } "
        "QMenuBar::item { padding: 3px 8px; border-radius: 3px; } "
        "QMenuBar::item:selected { background: rgb(62,62,62); } "
        "QMenu { background: rgb(45,45,45); color: rgb(212,212,212); "
        "border: 1px solid rgb(68,68,68); } "
        "QMenu::item:selected { background: rgb(38,79,120); }"
    )


def toolbar_stylesheet() -> str:
    return (
        "QToolBar { background: rgb(45,45,45); border: none; spacing: 2px; padding: 2px; } "
        "QToolButton { background: transparent; border: none; padding: 3px; border-radius: 3px; } "
        "QToolButton:hover { background: rgb(62,62,62); } "
        "QToolButton:pressed { background: rgb(80,80,80); }"
    )


def statusbar_stylesheet() -> str:
    return (
        "QStatusBar { background: rgb(31,31,31); color: rgb(154,154,154); padding: 1px 4px; } "
        "QStatusBar::item { border: none; }"
    )


def doc_stylesheet() -> str:
    return (
        "QFrame { background: rgb(32,28,48); border: 1px solid rgb(80,80,80); border-radius: 4px; } "
        "QLabel { background: transparent; color: rgb(220,220,220); } "
        "QTextEdit { background: transparent; border: none; color: rgb(220,220,220); }"
    )


def editor_font(size: int) -> QFont:
    f = QFont("JetBrains Mono", size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def small_font() -> QFont:
    return QFont("JetBrains Mono", 9)
