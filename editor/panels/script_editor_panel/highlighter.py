# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

import re

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
        self._keywords = frozenset(KEYWORDS)
        self._builtins = frozenset(BUILTINS)
        self._constants = frozenset(CONSTANTS)
        self._exceptions = frozenset(EXCEPTIONS)
        self._hash = chr(35)
        self._word_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
        self._number_re = re.compile(r"\b(?:0[xXoObB][A-Za-z0-9_]+|\d[\d._]*(?:[eE][+-]?\d+)?)\b")
        self._def_re = re.compile(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")

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
        n = len(text)
        if start >= n:
            return
        h = self._hash
        segments: list[tuple[int, int]] = []
        pos = start
        while pos < n:
            ch = text[pos]
            if ch == h:
                self.setFormat(pos, n - pos, self._formats["comment"])
                k = text.find("https:", pos)
                if k >= 0:
                    b = k
                    while b < n and not text[b].isspace():
                        b += 1
                    self.setFormat(k, b - k, self._formats["link"])
                return
            if ch == '"' or ch == "'":
                if text.startswith('"""', pos) or text.startswith("'''", pos):
                    d = text[pos:pos + 3]
                    st = 1 if d == '"""' else 2
                    e = text.find(d, pos + 3)
                    if e == -1:
                        self.setFormat(pos, n - pos, self._formats["string"])
                        self.setCurrentBlockState(st)
                        return
                    self.setFormat(pos, e + 3 - pos, self._formats["string"])
                    pos = e + 3
                    continue
                q = ch
                j = pos + 1
                while j < n:
                    c2 = text[j]
                    if c2 == "\\":
                        j += 2
                        continue
                    if c2 == q:
                        j += 1
                        break
                    j += 1
                self.setFormat(pos, j - pos, self._formats["string"])
                pos = j
                continue
            nxt_q = n + 1
            q1 = text.find('"', pos)
            if q1 >= 0 and q1 < nxt_q:
                nxt_q = q1
            q2 = text.find("'", pos)
            if q2 >= 0 and q2 < nxt_q:
                nxt_q = q2
            hc = text.find(h, pos)
            if hc >= 0 and hc < nxt_q:
                nxt_q = hc
            seg_end = nxt_q if nxt_q <= n else n
            if seg_end > pos:
                segments.append((pos, seg_end))
            if nxt_q > n or nxt_q == n + 1:
                break
            pos = nxt_q
        if not segments:
            return
        kw = self._keywords
        bi = self._builtins
        cn = self._constants
        ex = self._exceptions
        fmt_kw = self._formats["keyword"]
        fmt_bi = self._formats["builtin"]
        fmt_ex = self._formats["exception"]
        fmt_fn = self._formats["function"]
        fmt_nm = self._formats["number"]
        fmt_dc = self._formats["decorator"]
        for s0, s1 in segments:
            seg = text[s0:s1]
            for m in self._number_re.finditer(seg):
                self.setFormat(s0 + m.start(), m.end() - m.start(), fmt_nm)
            if "@" in seg:
                at = s0
                while True:
                    at = text.find("@", at, s1)
                    if at < 0:
                        break
                    j = at + 1
                    while j < s1 and (text[j].isalnum() or text[j] == "_" or text[j] == "." or text[j] == "_"):
                        j += 1
                    if j > at + 1:
                        self.setFormat(at, j - at, fmt_dc)
                        at = j
                    else:
                        at += 1
            expect_def = False
            if "def " in seg or "class " in seg:
                dm = self._def_re.search(seg)
                if dm:
                    self.setFormat(s0 + dm.start(1), len(dm.group(1)), fmt_fn)
                    expect_def_pos = s0 + dm.end()
                else:
                    expect_def_pos = -1
            else:
                expect_def_pos = -1
            for m in self._word_re.finditer(seg):
                a = s0 + m.start()
                b = s0 + m.end()
                if a < s0 + 0:
                    continue
                w = m.group(0)
                if expect_def_pos >= 0 and a >= expect_def_pos and a < expect_def_pos + 64:
                    if w not in kw:
                        self.setFormat(a, b - a, fmt_fn)
                        expect_def_pos = -1
                        continue
                if w in kw:
                    self.setFormat(a, b - a, fmt_kw)
                elif w in cn or w == "self" or w == "cls":
                    self.setFormat(a, b - a, fmt_kw)
                elif w in ex:
                    self.setFormat(a, b - a, fmt_ex)
                elif w in bi:
                    self.setFormat(a, b - a, fmt_bi)
                else:
                    if b < n and text[b] == "(":
                        self.setFormat(a, b - a, fmt_fn)
