# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import io
import sys
import traceback
from typing import Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPlainTextEdit, QApplication
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont, QKeyEvent, QKeySequence


class _ReplInput(QPlainTextEdit):
    execute_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[str] = []
        self._history_index: int = -1
        self._saved_text: str = ""
        self.setTabChangesFocus(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMaximumBlockCount(100)
        self.setPlaceholderText(">>>")

    def keyPressEvent(self, event: QKeyEvent):
        mods = event.modifiers()
        key = event.key()
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            if mods & Qt.KeyboardModifier.ControlModifier:
                self._do_execute()
                return
            text = self.toPlainText()
            if _is_balanced(text) or text.strip().startswith(("class ", "def ", "@", "if ", "elif ", "else:", "for ", "while ", "try:", "with ")):
                self._do_execute()
            else:
                super().keyPressEvent(event)
            return
        if key == Qt.Key.Key_Up:
            cursor = self.textCursor()
            if cursor.blockNumber() == 0 and not cursor.movePosition(QTextCursor.MoveOperation.Up):
                self._history_up()
                return
        elif key == Qt.Key.Key_Down:
            cursor = self.textCursor()
            if cursor.blockNumber() == self.blockCount() - 1 and not cursor.movePosition(QTextCursor.MoveOperation.Down):
                self._history_down()
                return
        elif event.matches(QKeySequence.StandardKey.Copy):
            if not self.textCursor().hasSelection():
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
                QApplication.clipboard().setText(cursor.selectedText())
                return
        super().keyPressEvent(event)

    def _do_execute(self):
        code = self.toPlainText()
        if code.strip():
            self._history.append(code)
            self._history_index = len(self._history)
            self.execute_requested.emit(code)
        self.clear()

    def _history_up(self):
        if not self._history:
            return
        if self._history_index == len(self._history):
            self._saved_text = self.toPlainText()
        if self._history_index > 0:
            self._history_index -= 1
            self.setPlainText(self._history[self._history_index])
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)

    def _history_down(self):
        if not self._history:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.setPlainText(self._history[self._history_index])
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
        elif self._history_index == len(self._history) - 1:
            self._history_index = len(self._history)
            self.setPlainText(self._saved_text)
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)


def _is_balanced(text: str) -> bool:
    depth = 0
    in_str = False
    str_char = None
    for c in text:
        if in_str:
            if c == str_char:
                in_str = False
            continue
        if c in ("'", '"'):
            in_str = True
            str_char = c
            continue
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth -= 1
            if depth < 0:
                return True
    return depth == 0


_CODE_COLORS = {
    "keyword": QColor(chr(35) + "569cd6"),
    "string": QColor(chr(35) + "ce9178"),
    "number": QColor(chr(35) + "b5cea8"),
    "builtin": QColor(chr(35) + "dcdcaa"),
    "comment": QColor(chr(35) + "6a9955"),
    "error": QColor(chr(35) + "f44747"),
    "result": QColor(chr(35) + "9cdcfe"),
    "prompt": QColor(chr(35) + "6a9955"),
    "stdout": QColor(chr(35) + "ffffff"),
}


class _CaptureWriter(io.StringIO):
    pass


class TerminalTab(QWidget):
    _font_family: str = "Courier New"
    _font_size: int = 10

    def __init__(self, namespace: dict[str, Any], font_family: str = "", font_size: int = 0, parent=None):
        super().__init__(parent)
        self._namespace = namespace
        if font_family:
            self._font_family = font_family
        if font_size:
            self._font_size = font_size
        self._setup_ui()

    def _make_font(self) -> QFont:
        font = QFont(self._font_family, self._font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        return font

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(self._make_font())
        self._output.setMinimumHeight(60)
        layout.addWidget(self._output)
        self._input = _ReplInput()
        self._input.setFont(self._make_font())
        self._input.setMaximumBlockCount(50)
        self._input.setMinimumHeight(28)
        self._input.setMaximumHeight(120)
        self._input.execute_requested.connect(self._execute)
        layout.addWidget(self._input)

    def _execute(self, code: str):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        proxy = _CaptureWriter()
        sys.stdout = proxy
        sys.stderr = proxy
        error_text = None
        try:
            compiled = compile(code, "<repl>", "exec")
            ns = self._namespace
            exec(compiled, ns)
        except Exception:
            error_text = traceback.format_exc().rstrip()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        self._write_output(f">>> {code}", _CODE_COLORS["prompt"])
        if error_text:
            self._write_output(error_text, _CODE_COLORS["error"])
            self._namespace.pop("_", None)
            return
        out = proxy.getvalue()
        if out:
            self._write_output(out.rstrip(), _CODE_COLORS["stdout"])
        self._namespace.pop("_", None)
        try:
            expr_val = eval(code, self._namespace)
            if expr_val is not None:
                self._namespace["_"] = expr_val
                self._write_output(repr(expr_val), _CODE_COLORS["result"])
        except Exception:
            pass

    def _write_output(self, text: str, color: QColor):
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.insertText(text + "\n", fmt)
        scroll = self._output.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def set_namespace(self, ns: dict):
        self._namespace = ns
