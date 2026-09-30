# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QMessageBox, QFileDialog
from PyQt6.QtCore import pyqtSignal

from .theme import tab_stylesheet
from .editor import CodeEditor
from .highlighter import PythonHighlighter


class CloseableTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.tabCloseRequested.connect(self._on_close_requested)
        self.setStyleSheet(tab_stylesheet())

    def _on_close_requested(self, index: int):
        widget = self.widget(index)
        if widget is not None:
            try:
                widget._close_self()
            except Exception:
                pass

    def add_closeable_tab(self, widget, title: str) -> int:
        return self.addTab(widget, title)


class ScriptTab(QWidget):
    closed = pyqtSignal(QWidget)

    def __init__(self, git=None, parent=None):
        super().__init__(parent)
        self._file_path: Optional[str] = None
        self._dirty = False
        self._vcs_git = git
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._editor = CodeEditor()
        self._highlighter = PythonHighlighter(self._editor.document())
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.vcs_set_git(git)
        layout.addWidget(self._editor)

    def set_font_size(self, size: int):
        self._editor.set_font_size(size)

    def set_wrap(self, enabled: bool):
        self._editor.set_wrap(enabled)

    def set_indent_guides(self, enabled: bool):
        self._editor.set_indent_guides(enabled)

    def _on_text_changed(self):
        if not self._dirty:
            self._dirty = True
            self._update_title()

    def _tab_title(self) -> str:
        base = os.path.basename(self._file_path) if self._file_path else "Untitled"
        suffix = "*" if self._dirty else ""
        return f"{base}{suffix}"

    def _update_title(self):
        tabs = self.parent()
        while tabs is not None and not isinstance(tabs, CloseableTabWidget):
            tabs = tabs.parent()
        if tabs is not None:
            index = tabs.indexOf(self)
            if index >= 0:
                tabs.setTabText(index, self._tab_title())

    def _close_self(self):
        if self._dirty and not self._discard_prompt():
            return
        self.closed.emit(self)
        self.deleteLater()

    def _discard_prompt(self) -> bool:
        res = QMessageBox.question(
            self, "Unsaved Changes",
            f"Save changes to {self._tab_title()} before closing?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        if res == QMessageBox.StandardButton.Save:
            self.save()
            return not self._dirty
        return res == QMessageBox.StandardButton.Discard

    def set_content(self, text: str, from_remote: bool = False):
        if from_remote:
            parent_widget = self.parent()
            from .widget import ScriptEditorWidget
            while parent_widget is not None and not isinstance(parent_widget, ScriptEditorWidget):
                parent_widget = parent_widget.parent()
            if parent_widget and self._file_path:
                parent_widget.clear_pending_ops(self._file_path)
        try:
            self._editor.set_text_fast(text)
        except Exception:
            self._editor.blockSignals(True)
            self._editor.setPlainText(text)
            self._editor.blockSignals(False)
            self._editor._old_text = text
            self._editor._folded.clear()
        self._dirty = False
        self._editor.document().setModified(False)
        self._update_title()

    def open_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if len(content) > 2000000:
                content = content[:2000000]
            self._file_path = path
            try:
                self._highlighter.setDocument(None)
            except Exception:
                pass
            try:
                self._editor.set_text_fast(content)
            except Exception:
                self._editor.blockSignals(True)
                self._editor.setPlainText(content)
                self._editor.blockSignals(False)
                self._editor._old_text = content
                self._editor._folded.clear()
            try:
                self._highlighter.setDocument(self._editor.document())
            except Exception:
                pass
            self._dirty = False
            self._editor.document().setModified(False)
            self._update_title()
            try:
                from PyQt6.QtCore import QTimer as _QT
                _ed = self._editor
                _p = path
                _QT.singleShot(80, lambda: _ed.vcs_set_file(_p))
                _QT.singleShot(250, lambda: _ed._run_analysis())
            except Exception:
                self._editor.vcs_set_file(path)
            try:
                tc = self._editor.textCursor()
                tc.setPosition(0)
                self._editor.setTextCursor(tc)
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Open Error", f"Failed to open:{chr(10)}{e}")

    def save(self):
        if self._file_path:
            try:
                with open(self._file_path, "w", encoding="utf-8") as f:
                    f.write(self._editor.toPlainText())
                self._dirty = False
                self._editor.document().setModified(False)
                self._editor.vcs_set_file(self._file_path)
                self._update_title()
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save:{chr(10)}{e}")
        else:
            self.save_as()

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Script", "",
            "Python Files (*.py)"
        )
        if path:
            if not path.endswith(".py"):
                path += ".py"
            self._file_path = path
            self.save()

    def new(self):
        self._editor.clear()
        self._editor._old_text = ""
        self._editor._folded.clear()
        self._file_path = None
        self._dirty = False
        self._editor.document().setModified(False)
        self._editor._vcs_diff_data = {}
        self._editor._vcs_blame_data = {}
        self._editor._vcs_status = ""
        self._editor._vcs_branch = ""
        self._editor._diagnostic_errors = []
        self._editor._diagnostic_warnings = []
        self._editor._update_extra()
        self._update_title()


_CloseableTabWidget = CloseableTabWidget
_ScriptTab = ScriptTab
