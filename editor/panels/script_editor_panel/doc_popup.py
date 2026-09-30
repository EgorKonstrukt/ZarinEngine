# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from .theme import doc_stylesheet
from . import doc_provider as _docs


class DocPopup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet(doc_stylesheet())
        from core.config.editor_scale import scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scale(12), scale(10), scale(12), scale(8))
        layout.setSpacing(scale(6))
        self._title = QLabel("", self)
        tf = QFont("Consolas", 13)
        tf.setWeight(QFont.Weight.Bold)
        self._title.setFont(tf)
        self._title.setStyleSheet("color: rgb(255,255,255);")
        layout.addWidget(self._title)
        self._body = QTextEdit(self)
        self._body.setReadOnly(True)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setFont(QFont("Consolas", 9))
        self._body.setFixedSize(scale(620), scale(300))
        layout.addWidget(self._body)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self._edit_hint = QLabel("?", self)
        try:
            self._edit_hint.setText(chr(9998) + "  " + chr(8942))
        except Exception:
            self._edit_hint.setText("..")
        self._edit_hint.setStyleSheet("color: rgb(150,150,150);")
        bottom.addWidget(self._edit_hint)
        layout.addLayout(bottom)
        self.hide()
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(scale(18))
        shadow.setOffset(0, scale(4))
        shadow.setColor(QColor(0, 0, 0))
        self.setGraphicsEffect(shadow)
        self._current_word = ""

    def show_documentation(self, word: str, global_pos) -> bool:
        try:
            info = _docs.get_documentation(word)
        except Exception:
            info = None
        if info is None:
            self.hide()
            return False
        title, body = info
        self._current_word = word
        self._title.setText(title[:220])
        self._body.setPlainText(body[:6000])
        self.move(global_pos)
        self.show()
        self.raise_()
        return True

    def current_word(self) -> str:
        return self._current_word
