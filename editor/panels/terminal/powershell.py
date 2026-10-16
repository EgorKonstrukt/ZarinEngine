# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import subprocess
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPlainTextEdit
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont, QKeyEvent


class PsReader(QThread):
    line_received = Signal(str)

    def __init__(self, proc: subprocess.Popen):
        super().__init__()
        self._proc = proc

    def run(self):
        for line in iter(self._proc.stdout.readline, ""):
            line = line.rstrip("\r\n")
            if line:
                self.line_received.emit(line)


class PowershellInput(QPlainTextEdit):
    send_cmd = Signal(str)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            text = self.toPlainText().strip()
            if text:
                self.send_cmd.emit(text)
                self.clear()
        else:
            super().keyPressEvent(event)


class PowershellTab(QWidget):
    _font_family: str = "Segoe UI"
    _font_size: int = 10

    def __init__(self, assets_path: str, font_family: str = "", font_size: int = 0, parent=None):
        super().__init__(parent)
        self._proc: subprocess.Popen | None = None
        self._reader: PsReader | None = None
        if font_family:
            self._font_family = font_family
        if font_size:
            self._font_size = font_size
        self._setup_ui()
        self._start_powershell(assets_path)

    def _make_font(self) -> QFont:
        return QFont(self._font_family, self._font_size)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(self._make_font())
        self._output.setMinimumHeight(60)
        self._output.setStyleSheet(
            "QTextEdit { background: " + chr(35) + "012456; color: " + chr(35) + "ffffff;"
            " border: 1px solid " + chr(35) + "003366; }")
        layout.addWidget(self._output)
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)
        self._input = PowershellInput()
        self._input.setFont(self._make_font())
        self._input.setMaximumBlockCount(10)
        self._input.setMinimumHeight(28)
        self._input.setMaximumHeight(80)
        self._input.setStyleSheet(
            "QPlainTextEdit { background: " + chr(35) + "001a4a; color: " + chr(35) + "ffffff;"
            " border: 1px solid " + chr(35) + "003366; padding: 4px 8px; }")
        self._input.setPlaceholderText("Enter PowerShell command...")
        self._input.send_cmd.connect(self._send_command)
        input_layout.addWidget(self._input)
        layout.addLayout(input_layout)

    def _start_powershell(self, assets_path: str):
        try:
            setup = (
                f"[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                f"$OutputEncoding = [Text.Encoding]::UTF8; "
                f"cd \"{assets_path}\""
            )
            self._proc = subprocess.Popen(
                ["powershell.exe", "-NoExit", "-Command", setup],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=assets_path,
                bufsize=0,
                text=True,
                encoding="utf-8",
            )
            self._reader = PsReader(self._proc)
            self._reader.line_received.connect(self._on_line)
            self._reader.start()
        except Exception as e:
            self._write_output(f"Failed to start PowerShell: {e}", QColor(chr(35) + "f44747"))
            self._input.setEnabled(False)

    def _on_line(self, text: str):
        QTimer.singleShot(0, lambda: self._write_output(text, QColor(chr(35) + "ffffff")))

    def _write_output(self, text: str, color: QColor):
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.insertText(text + "\n", fmt)
        scroll = self._output.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def _send_command(self, cmd: str):
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write(cmd + "\n")
                self._proc.stdin.flush()
            except Exception as e:
                self._write_output(f"Error: {e}", QColor(chr(35) + "f44747"))

    def terminate(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                pass
