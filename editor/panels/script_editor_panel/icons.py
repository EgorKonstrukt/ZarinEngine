# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtGui import QIcon

try:
    import qtawesome as qta
except ImportError:
    qta = None


QTA_COLORS = {
    "new": "white",
    "open": "white",
    "save": "white",
    "save_as": "white",
    "cut": "white",
    "copy": "white",
    "paste": "white",
    "undo": "white",
    "redo": "white",
    "word_wrap": "white",
    "indent": "white",
    "zoom_in": "white",
    "zoom_out": "white",
    "run": "lightgreen",
}


def qta_icon(name: str) -> QIcon:
    if qta is None:
        return QIcon()
    names = {
        "new": "fa5s.file",
        "open": "fa5s.folder-open",
        "save": "fa5s.save",
        "save_as": "fa5s.save",
        "cut": "fa5s.cut",
        "copy": "fa5s.copy",
        "paste": "fa5s.paste",
        "undo": "fa5s.undo",
        "redo": "fa5s.redo",
        "word_wrap": "fa5s.align-left",
        "indent": "fa5s.indent",
        "zoom_in": "fa5s.search-plus",
        "zoom_out": "fa5s.search-minus",
        "run": "fa5s.play",
    }
    return qta.icon(names.get(name, "fa5s.file"), color=QTA_COLORS.get(name, "white"))
