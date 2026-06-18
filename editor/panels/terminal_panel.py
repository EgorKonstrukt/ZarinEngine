from __future__ import annotations
import os
import sys
import io
import subprocess
from typing import Any
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QTextEdit, QTabWidget, QLineEdit,
                              QCompleter)
from PyQt6.QtCore import Qt, QStringListModel, pyqtSignal, QTimer, QThread
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont, QKeyEvent

from core.engine import Engine
from core.logger import Logger


class CodeInput(QLineEdit):
    key_up = pyqtSignal()
    key_down = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            if not self.completer() or not self.completer().popup().isVisible():
                self.key_up.emit()
                return
        elif event.key() == Qt.Key.Key_Down:
            if not self.completer() or not self.completer().popup().isVisible():
                self.key_down.emit()
                return
        super().keyPressEvent(event)


class PsReader(QThread):
    line_received = pyqtSignal(str)

    def __init__(self, proc: subprocess.Popen):
        super().__init__()
        self._proc = proc

    def run(self):
        for line in iter(self._proc.stdout.readline, ""):
            line = line.rstrip("\r\n")
            if line:
                self.line_received.emit(line)


class PowershellInput(QLineEdit):
    send_cmd = pyqtSignal(str)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self.text().strip()
            if text:
                self.send_cmd.emit(text)
                self.clear()
        else:
            super().keyPressEvent(event)


class PowershellTab(QWidget):
    _font_family: str = "Segoe UI"
    _font_size: int = 10

    def __init__(self, assets_path: str, font_family: str = "",
                 font_size: int = 0, parent=None):
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
            "QTextEdit { background: #012456; color: #ffffff;"
            " border: 1px solid #003366; }")
        layout.addWidget(self._output)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self._input = PowershellInput()
        self._input.setFont(self._make_font())
        self._input.setStyleSheet(
            "QLineEdit { background: #001a4a; color: #ffffff;"
            " border: 1px solid #003366; padding: 4px 8px; }")
        self._input.setPlaceholderText("Enter PowerShell command...")
        self._input.send_cmd.connect(self._send_command)
        input_layout.addWidget(self._input)

        layout.addLayout(input_layout)

    def _start_powershell(self, assets_path: str):
        try:
            setup = (
                f'[Console]::OutputEncoding = [Text.Encoding]::UTF8; '
                f'$OutputEncoding = [Text.Encoding]::UTF8; '
                f'cd "{assets_path}"'
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
            self._write_output(f"Failed to start PowerShell: {e}", QColor("#f44747"))
            self._input.setEnabled(False)

    def _on_line(self, text: str):
        QTimer.singleShot(0, lambda: self._write_output(text, QColor("#ffffff")))

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
                self._write_output(f"Error sending command: {e}", QColor("#f44747"))

    def terminate(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                pass


class TerminalTab(QWidget):
    _font_family: str = "Courier New"
    _font_size: int = 10

    def __init__(self, namespace: dict[str, Any], font_family: str = "",
                 font_size: int = 0, parent=None):
        super().__init__(parent)
        self._namespace = namespace
        self._history: list[str] = []
        self._history_index: int = -1
        self._current_input: str = ""
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

        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self._input = CodeInput()
        self._input.setFont(self._make_font())
        self._input.setPlaceholderText("Enter Python command...")
        self._input.returnPressed.connect(self._on_return_pressed)
        self._input.key_up.connect(self._on_history_up)
        self._input.key_down.connect(self._on_history_down)
        input_layout.addWidget(self._input)

        layout.addLayout(input_layout)

        self._setup_autocomplete()

    def _setup_autocomplete(self):
        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._input.setCompleter(self._completer)
        self._input.textChanged.connect(self._on_text_changed)

    def _get_object_attrs(self, expr: str) -> list[str]:
        parts = expr.split(".")
        obj = self._namespace.get(parts[0])
        if obj is None:
            return []
        for part in parts[1:]:
            obj = getattr(obj, part, None)
            if obj is None:
                return []
        return [x for x in dir(obj) if not x.startswith("_")]

    def _get_completions(self, prefix: str) -> list[str]:
        if "." in prefix:
            obj_expr, _, attr_prefix = prefix.rpartition(".")
            attrs = self._get_object_attrs(obj_expr)
            return sorted(a for a in attrs if a.startswith(attr_prefix))
        words = set()
        for w in dir(__builtins__):
            if w.startswith(prefix):
                words.add(w)
        for k in self._namespace:
            if k.startswith(prefix):
                words.add(k)
        words.update([
            "exec", "eval", "open", "import", "from", "as",
            "def", "class", "return", "if", "elif", "else",
            "for", "while", "try", "except", "finally",
            "with", "yield", "lambda", "pass", "break", "continue",
            "None", "True", "False", "and", "or", "not", "in", "is",
        ])
        return sorted(words)

    def _on_text_changed(self, text: str):
        if not text:
            self._completer.popup().hide()
            return
        prefix = text.split()[-1] if text.split() else ""
        if not prefix:
            self._completer.popup().hide()
            return
        words = self._get_completions(prefix)
        if not words:
            self._completer.popup().hide()
            return
        self._completer.setModel(QStringListModel(words))
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() > 0:
            self._completer.complete()

    def _on_return_pressed(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._history.append(text)
        self._history_index = len(self._history)
        self._execute(text)

    def _execute(self, code: str):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured = io.StringIO()
        sys.stdout = captured
        sys.stderr = captured

        output_lines: list[str] = []
        error_lines: list[str] = []

        try:
            compiled = compile(code, "<terminal>", "exec")
            exec(compiled, self._namespace)
            out = captured.getvalue()
            if out:
                output_lines.append(out.rstrip())
        except Exception as e:
            error_lines.append(f"Error: {e}")

        sys.stdout = old_stdout
        sys.stderr = old_stderr

        self._write_output(f">>> {code}", QColor("#569cd6"))
        for line in output_lines:
            self._write_output(line, QColor("#ffffff"))
        for line in error_lines:
            self._write_output(line, QColor("#f44747"))

    def _write_output(self, text: str, color: QColor):
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.insertText(text + "\n", fmt)
        scroll = self._output.verticalScrollBar()
        QTimer.singleShot(50, lambda: scroll.setValue(scroll.maximum()))

    def _on_history_up(self):
        if not self._history:
            return
        if self._history_index > 0:
            if self._history_index == len(self._history):
                self._current_input = self._input.text()
            self._history_index -= 1
            self._input.setText(self._history[self._history_index])

    def _on_history_down(self):
        if not self._history:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._input.setText(self._history[self._history_index])
        elif self._history_index == len(self._history) - 1:
            self._history_index = len(self._history)
            self._input.setText(self._current_input)


class TerminalPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Terminal", parent)
        self._tab_count: int = 0
        self._font_family: str = "Segoe UI"
        self._font_size: int = 10
        ns: dict[str, Any] = {}
        eng = Engine.instance()
        if eng:
            ns["engine"] = eng
            ns["scene"] = eng.scene
        ns["Logger"] = Logger
        ns["os"] = os
        ns["sys"] = sys
        self._namespace = ns
        self._pws_tabs: list[PowershellTab] = []
        self._setup_ui()

    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        add_btn = QPushButton("+")
        add_btn.setToolTip("New Python Tab")
        add_btn.setFixedWidth(24)
        add_btn.clicked.connect(self._add_tab)
        toolbar.addWidget(add_btn)

        ps_btn = QPushButton("PS")
        ps_btn.setToolTip("New PowerShell Tab (embedded)")
        ps_btn.setFixedWidth(28)
        ps_btn.clicked.connect(self._open_powershell)
        toolbar.addWidget(ps_btn)

        toolbar.addStretch()

        clear_btn = QPushButton("C")
        clear_btn.setToolTip("Clear Current Tab")
        clear_btn.setFixedWidth(24)
        clear_btn.clicked.connect(self._clear_current)
        toolbar.addWidget(clear_btn)

        reset_btn = QPushButton("R")
        reset_btn.setToolTip("Reset Python Namespace")
        reset_btn.setFixedWidth(24)
        reset_btn.clicked.connect(self._reset_namespace)
        toolbar.addWidget(reset_btn)

        layout.addLayout(toolbar)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        layout.addWidget(self._tabs)

        self.setWidget(w)
        self._add_tab()

    def _get_assets_path(self) -> str:
        assets_path = os.path.abspath("assets")
        if not os.path.isdir(assets_path):
            assets_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "assets"))
        if not os.path.isdir(assets_path):
            assets_path = os.getcwd()
        return assets_path

    def _add_tab(self):
        self._tab_count += 1
        tab = TerminalTab(self._namespace, self._font_family,
                          self._font_size, self)
        idx = self._tabs.addTab(tab, f"Python {self._tab_count}")
        self._tabs.setCurrentIndex(idx)

    def _open_powershell(self):
        self._tab_count += 1
        tab = PowershellTab(self._get_assets_path(),
                            self._font_family, self._font_size, self)
        self._pws_tabs.append(tab)
        idx = self._tabs.addTab(tab, f"PS {self._tab_count}")
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int):
        if self._tabs.count() <= 1:
            return
        w = self._tabs.widget(index)
        if isinstance(w, PowershellTab):
            w.terminate()
            if w in self._pws_tabs:
                self._pws_tabs.remove(w)
        self._tabs.removeTab(index)
        w.deleteLater()

    def _clear_current(self):
        tab = self._tabs.currentWidget()
        if tab and hasattr(tab, "_output"):
            tab._output.clear()

    def _reset_namespace(self):
        self._namespace.clear()
        eng = Engine.instance()
        if eng:
            self._namespace["engine"] = eng
            self._namespace["scene"] = eng.scene
        self._namespace["Logger"] = Logger
        self._namespace["os"] = os
        self._namespace["sys"] = sys

    def load_config(self, config) -> None:
        self._font_family = config.get("terminal.font_family", self._font_family)
        self._font_size = config.get("terminal.font_size", self._font_size)

    def save_config(self, config) -> None:
        config.set("terminal.font_family", self._font_family)
        config.set("terminal.font_size", self._font_size)

    def execute_python(self, code: str):
        tab = self._tabs.currentWidget()
        if isinstance(tab, TerminalTab):
            tab._input.setText(code)
            tab._on_return_pressed()
