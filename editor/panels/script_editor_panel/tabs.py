# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QMessageBox, QFileDialog, QMenu
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QAction

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
        self._closed_stack: list[dict] = []
        self._max_closed = 25
        try:
            bar = self.tabBar()
            bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            bar.customContextMenuRequested.connect(self._on_context_menu)
        except Exception:
            pass
        try:
            self._reopen_action = QAction("Reopen Closed Tab", self)
            self._reopen_action.triggered.connect(lambda: self.reopen_closed_tab())
            self.addAction(self._reopen_action)
        except Exception:
            pass

    def _on_close_requested(self, index: int):
        self.close_tab_at(index)

    def _norm_key(self, index: int) -> str:
        try:
            w = self.widget(index)
            p = getattr(w, "_file_path", "") or ""
            if p:
                return os.path.normcase(os.path.normpath(p))
            return ""
        except Exception:
            return ""

    def _duplicate_indices(self, index: int) -> list[int]:
        try:
            if index < 0 or index >= self.count():
                return []
            key = self._norm_key(index)
            w0 = self.widget(index)
            p0 = getattr(w0, "_file_path", "") if w0 is not None else ""
            out: list[int] = []
            for i in range(self.count()):
                if i == index:
                    continue
                if self._norm_key(i) != key:
                    continue
                if not key:
                    out.append(i)
                else:
                    out.append(i)
            if not key:
                return out
            return out
        except Exception:
            return []

    def duplicate_count(self, index: int) -> int:
        return len(self._duplicate_indices(index))

    def can_reopen(self) -> bool:
        return len(self._closed_stack) > 0

    def _snapshot_at(self, index: int):
        try:
            if index < 0 or index >= self.count():
                return None
            w = self.widget(index)
            if w is None:
                return None
            try:
                path = getattr(w, "_file_path", "") or ""
            except Exception:
                path = ""
            try:
                content = w._editor.toPlainText()
            except Exception:
                content = ""
            try:
                dirty = bool(w._dirty)
            except Exception:
                dirty = False
            try:
                git = getattr(w, "_vcs_git", None)
            except Exception:
                git = None
            try:
                title = self.tabText(index)
            except Exception:
                title = ""
            return {"path": path, "content": content, "dirty": dirty, "index": index, "git": git, "title": title}
        except Exception:
            return None

    def _push_closed(self, entry):
        try:
            if entry is None:
                return
            self._closed_stack.append(entry)
            while len(self._closed_stack) > self._max_closed:
                self._closed_stack.pop(0)
        except Exception:
            pass

    def close_tab_at(self, index: int) -> bool:
        try:
            if index < 0 or index >= self.count():
                return False
            snap = self._snapshot_at(index)
            w = self.widget(index)
            if w is None:
                return False
            try:
                before = self.count()
            except Exception:
                before = -1
            try:
                w._close_self()
            except Exception:
                pass
            try:
                still = False
                for k in range(self.count()):
                    try:
                        if self.widget(k) is w:
                            still = True
                            break
                    except Exception:
                        continue
                if still:
                    return False
                if before >= 0 and self.count() >= before:
                    return False
            except Exception:
                pass
            if snap is not None:
                self._push_closed(snap)
            return True
        except Exception:
            return False

    def close_other_tabs(self, keep: int):
        try:
            if keep < 0 or keep >= self.count():
                return
            indices = [i for i in range(self.count()) if i != keep]
            indices.sort(reverse=True)
            for i in indices:
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    try:
                        if i < self.count() and self.widget(i) is not None:
                            break
                    except Exception:
                        break
        except Exception:
            pass

    def close_tabs_left(self, index: int):
        try:
            if index <= 0 or index >= self.count():
                return
            for i in range(index - 1, -1, -1):
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def close_tabs_right(self, index: int):
        try:
            if index < 0 or index >= self.count() - 1:
                return
            for i in range(self.count() - 1, index, -1):
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def close_duplicate_tabs(self, index: int):
        try:
            dup = self._duplicate_indices(index)
            dup.sort(reverse=True)
            for i in dup:
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def _parent_editor(self):
        try:
            p = self.parent()
            while p is not None:
                try:
                    if hasattr(p, "open_script") and hasattr(p, "_tabs"):
                        return p
                except Exception:
                    pass
                try:
                    p = p.parent()
                except Exception:
                    break
            return None
        except Exception:
            return None

    def reopen_closed_tab(self) -> bool:
        try:
            if not self._closed_stack:
                return False
            entry = self._closed_stack.pop()
            path = entry.get("path", "") or ""
            content = entry.get("content", "") or ""
            dirty = bool(entry.get("dirty", False))
            pos = int(entry.get("index", 0))
            git = entry.get("git", None)
            ed = self._parent_editor()
            if ed is not None:
                try:
                    if path and os.path.isfile(path):
                        already = None
                        try:
                            for i in range(self.count()):
                                try:
                                    w = self.widget(i)
                                    if getattr(w, "_file_path", None) == path:
                                        already = w
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            already = None
                        if already is None:
                            try:
                                ed.open_script(path)
                            except Exception:
                                pass
                            try:
                                for i in range(self.count()):
                                    try:
                                        w = self.widget(i)
                                        if getattr(w, "_file_path", None) == path:
                                            already = w
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                        if already is not None and dirty and content:
                            try:
                                cur = already._editor.toPlainText()
                            except Exception:
                                cur = ""
                            if cur != content:
                                try:
                                    already._editor.blockSignals(True)
                                    already._editor.setPlainText(content)
                                    already._editor.blockSignals(False)
                                    try:
                                        already._editor._old_text = content
                                    except Exception:
                                        pass
                                    already._dirty = True
                                    already._update_title()
                                except Exception:
                                    pass
                        if already is not None:
                            try:
                                cur_idx = self.indexOf(already)
                                dest = max(0, min(pos, self.count() - 1))
                                if cur_idx != dest and cur_idx >= 0:
                                    self.tabBar().moveTab(cur_idx, dest)
                                self.setCurrentIndex(dest)
                            except Exception:
                                pass
                        return True
                    else:
                        try:
                            ed._new_tab()
                        except Exception:
                            pass
                        try:
                            w = self.currentWidget()
                            if w is not None and content:
                                try:
                                    w._editor.blockSignals(True)
                                    w._editor.setPlainText(content)
                                    w._editor.blockSignals(False)
                                    try:
                                        w._editor._old_text = content
                                    except Exception:
                                        pass
                                    w._dirty = bool(dirty) or True
                                    if path:
                                        try:
                                            w._file_path = path
                                        except Exception:
                                            pass
                                    w._update_title()
                                except Exception:
                                    pass
                            try:
                                cur_idx = self.currentIndex()
                                dest = max(0, min(pos, self.count() - 1))
                                if cur_idx != dest:
                                    self.tabBar().moveTab(cur_idx, dest)
                                self.setCurrentIndex(dest)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        return True
                except Exception:
                    pass
            tab = ScriptTab(git=git)
            try:
                if path and os.path.isfile(path):
                    tab.open_file(path)
                    if dirty and content:
                        try:
                            cur = tab._editor.toPlainText()
                        except Exception:
                            cur = ""
                        if cur != content:
                            try:
                                tab._editor.blockSignals(True)
                                tab._editor.setPlainText(content)
                                tab._editor.blockSignals(False)
                                try:
                                    tab._editor._old_text = content
                                except Exception:
                                    pass
                                tab._dirty = True
                            except Exception:
                                pass
                else:
                    if content:
                        try:
                            tab._editor.blockSignals(True)
                            tab._editor.setPlainText(content)
                            tab._editor.blockSignals(False)
                            try:
                                tab._editor._old_text = content
                            except Exception:
                                pass
                            tab._dirty = bool(dirty) or True
                            if path:
                                tab._file_path = path
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                dest = max(0, min(pos, self.count()))
                idx = self.insertTab(dest, tab, tab._tab_title())
                self.setCurrentIndex(idx)
            except Exception:
                try:
                    idx = self.add_closeable_tab(tab, tab._tab_title())
                    self.setCurrentIndex(idx)
                except Exception:
                    return False
            return True
        except Exception:
            return False

    def _on_context_menu(self, pos):
        try:
            bar = self.tabBar()
            idx = bar.tabAt(pos)
            menu = QMenu(bar)
            if idx < 0:
                act = menu.addAction("Reopen Closed Tab")
                act.setEnabled(self.can_reopen())
                act.triggered.connect(lambda: self.reopen_closed_tab())
                try:
                    menu.exec(bar.mapToGlobal(pos))
                except Exception:
                    pass
                return
            close_act = menu.addAction("Close Tab")
            close_act.triggered.connect(lambda checked=False, _i=idx: self.close_tab_at(_i))
            dup = self.duplicate_count(idx)
            if dup > 0:
                dup_act = menu.addAction(f"Close Duplicate Tabs ({dup})")
            else:
                dup_act = menu.addAction("Close Duplicate Tabs")
                dup_act.setEnabled(False)
            dup_act.triggered.connect(lambda checked=False, _i=idx: self.close_duplicate_tabs(_i))
            multi = menu.addMenu("Close Multiple Tabs")
            left = idx
            right = self.count() - idx - 1
            left_act = multi.addAction("Close Tabs to the Left")
            left_act.setEnabled(left > 0)
            left_act.triggered.connect(lambda checked=False, _i=idx: self.close_tabs_left(_i))
            if right > 0:
                right_act = multi.addAction(f"Close Tabs to the Right ({right})")
            else:
                right_act = multi.addAction("Close Tabs to the Right")
                right_act.setEnabled(False)
            right_act.triggered.connect(lambda checked=False, _i=idx: self.close_tabs_right(_i))
            other_act = multi.addAction("Close Other Tabs")
            other_act.setEnabled(self.count() > 1)
            other_act.triggered.connect(lambda checked=False, _i=idx: self.close_other_tabs(_i))
            reopen_act = menu.addAction("Reopen Closed Tab")
            reopen_act.setEnabled(self.can_reopen())
            reopen_act.triggered.connect(lambda: self.reopen_closed_tab())
            try:
                menu.exec(bar.mapToGlobal(pos))
            except Exception:
                pass
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
