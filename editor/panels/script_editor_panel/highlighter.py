# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from .theme import Theme

try:
    from core.config.syntax_config import KEYWORDS, BUILTINS, CONSTANTS, EXCEPTIONS
except ImportError:
    try:
        from ..syntax_config import KEYWORDS, BUILTINS, CONSTANTS, EXCEPTIONS
    except ImportError:
        from syntax_config import KEYWORDS, BUILTINS, CONSTANTS, EXCEPTIONS


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._formats: dict[str, QTextCharFormat] = {}
        kw = QTextCharFormat()
        kw.setForeground(QColor(*Theme.keyword))
        self._formats["keyword"] = kw
        const = QTextCharFormat()
        const.setForeground(QColor(*Theme.keyword))
        self._formats["constant"] = const
        s = QTextCharFormat()
        s.setForeground(QColor(*Theme.string))
        s.setFontItalic(True)
        self._formats["string"] = s
        num = QTextCharFormat()
        num.setForeground(QColor(*Theme.number))
        self._formats["number"] = num
        com = QTextCharFormat()
        com.setForeground(QColor(*Theme.comment))
        self._formats["comment"] = com
        dec = QTextCharFormat()
        dec.setForeground(QColor(*Theme.decorator))
        self._formats["decorator"] = dec
        func = QTextCharFormat()
        func.setForeground(QColor(*Theme.function))
        self._formats["function"] = func
        bi = QTextCharFormat()
        bi.setForeground(QColor(*Theme.builtin))
        self._formats["builtin"] = bi
        exc = QTextCharFormat()
        exc.setForeground(QColor(*Theme.exception))
        self._formats["exception"] = exc
        link = QTextCharFormat()
        link.setForeground(QColor(*Theme.link))
        link.setFontUnderline(True)
        self._formats["link"] = link
        self._keywords = set(KEYWORDS)
        self._builtins = set(BUILTINS)
        self._constants = set(CONSTANTS)
        self._exceptions = set(EXCEPTIONS)
        self._hash = chr(35)

    def highlightBlock(self, text):
        self.setCurrentBlockState(0)
        start = 0
        prev = self.previousBlockState()
        if prev == 1 or prev == 2:
            delimiter = '"""' if prev == 1 else "'''"
            end = text.find(delimiter)
            if end == -1:
                self.setFormat(0, len(text), self._formats["string"])
                self.setCurrentBlockState(prev)
                return
            end += 3
            self.setFormat(0, end, self._formats["string"])
            start = end
        self._scan(text, start)

    def _scan(self, text, start):
        i = start
        n = len(text)
        expect_def = False
        h = self._hash
        while i < n:
            c = text[i]
            if c.isspace():
                i += 1
                continue
            if c == h:
                self.setFormat(i, n - i, self._formats["comment"])
                rest = text[i:]
                k = rest.find("https:")
                if k >= 0:
                    a = i + k
                    b = a
                    while b < n and not text[b].isspace():
                        b += 1
                    self.setFormat(a, b - a, self._formats["link"])
                return
            if text.startswith('"""', i) or text.startswith("'''", i):
                d = text[i:i + 3]
                st = 1 if d == '"""' else 2
                e = text.find(d, i + 3)
                if e == -1:
                    self.setFormat(i, n - i, self._formats["string"])
                    self.setCurrentBlockState(st)
                    return
                self.setFormat(i, e + 3 - i, self._formats["string"])
                i = e + 3
                expect_def = False
                continue
            if c == '"' or c == "'":
                q = c
                j = i + 1
                while j < n:
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == q:
                        j += 1
                        break
                    j += 1
                self.setFormat(i, j - i, self._formats["string"])
                i = j
                expect_def = False
                continue
            if c == "@":
                j = i + 1
                while j < n and (text[j].isalnum() or text[j] in "._"):
                    j += 1
                if j > i + 1:
                    self.setFormat(i, j - i, self._formats["decorator"])
                    i = j
                    expect_def = False
                    continue
                i += 1
                expect_def = False
                continue
            if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
                j = i
                if c == "0" and i + 1 < n and text[i + 1] in "xXoObB":
                    j = i + 2
                    while j < n and (text[j].isalnum() or text[j] == "_"):
                        j += 1
                else:
                    while j < n and (text[j].isdigit() or text[j] in "._"):
                        j += 1
                    if j < n and text[j] in "eE":
                        j += 1
                        if j < n and text[j] in "+-":
                            j += 1
                        while j < n and text[j].isdigit():
                            j += 1
                self.setFormat(i, j - i, self._formats["number"])
                i = j
                expect_def = False
                continue
            if c.isalpha() or c == "_":
                j = i
                while j < n and (text[j].isalnum() or text[j] == "_"):
                    j += 1
                word = text[i:j]
                k = j
                while k < n and text[k].isspace():
                    k += 1
                token = None
                if expect_def:
                    token = "function"
                    expect_def = False
                elif word in self._keywords:
                    token = "keyword"
                    if word in ("def", "class"):
                        expect_def = True
                elif word in self._constants:
                    token = "keyword"
                elif word in ("self", "cls"):
                    token = "keyword"
                elif word in self._exceptions:
                    token = "exception"
                elif word in self._builtins:
                    token = "builtin"
                elif k < n and text[k] == "(":
                    token = "function"
                if token is not None:
                    self.setFormat(i, j - i, self._formats[token])
                i = j
                continue
            i += 1
            expect_def = False
