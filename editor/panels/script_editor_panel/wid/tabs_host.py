# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ..tabsp import ScriptTab
from ..edit import CodeEditor


class TabsHostMixin:

    def _new_tab(self):
        tab = ScriptTab(git=self._git)
        tab.closed.connect(self._on_tab_closed)
        tab.set_font_size(self._zoom)
        tab.set_wrap(self._wrap)
        self._bind_tab_signals(tab)
        self._tabs.add_closeable_tab(tab, "Untitled")
        self._tabs.setCurrentWidget(tab)
        self._update_label()
        self._update_vcs_statusbar()
        self._on_cursor(1, 1)
        self.tab_opened.emit("")

    def open_script(self, path: str):
        for i in range(self._tabs.count()):
            existing = self._tabs.widget(i)
            if existing._file_path == path:
                self._tabs.setCurrentWidget(existing)
                return
        tab = ScriptTab(git=self._git)
        tab.closed.connect(self._on_tab_closed)
        tab.set_font_size(self._zoom)
        tab.set_wrap(self._wrap)
        self._bind_tab_signals(tab)
        tab.open_file(path)
        self._tabs.add_closeable_tab(tab, tab._tab_title())
        self._tabs.setCurrentWidget(tab)
        self._update_label()
        self._update_vcs_statusbar()
        self._on_cursor(1, 1)
        self.tab_opened.emit(path)
        self.collab_file_opened.emit(path, tab._editor.toPlainText())

    def _open_tab(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Script", "",
            "Python Files (*.py);;All Files (*)"
        )
        if path:
            self.open_script(path)

    def _save_current(self):
        tab = self._current_tab()
        if tab is not None:
            tab.save()
            self._update_label()
            self._update_vcs_statusbar()
            if tab._file_path:
                content = tab._editor.toPlainText()
                self.collab_file_saved.emit(tab._file_path, content)

    def _save_current_as(self):
        tab = self._current_tab()
        if tab is not None:
            tab.save_as()
            self._update_label()
            self._update_vcs_statusbar()

    def _undo(self):
        ed = self._active_editor()
        if ed is not None and ed.document().isUndoAvailable():
            ed.undo()

    def _redo(self):
        ed = self._active_editor()
        if ed is not None and ed.document().isRedoAvailable():
            ed.redo()

    def _cut(self):
        ed = self._active_editor()
        if ed is not None:
            ed.cut()

    def _copy(self):
        ed = self._active_editor()
        if ed is not None:
            ed.copy()

    def _paste(self):
        ed = self._active_editor()
        if ed is not None:
            ed.paste()

    def _toggle_wrap(self, checked: bool):
        self._wrap = checked
        self._act_wrap.setChecked(checked)
        if hasattr(self, "_act_wrap_m"):
            self._act_wrap_m.setChecked(checked)
        for i in range(self._tabs.count()):
            self._tabs.widget(i).set_wrap(self._wrap)

    def _toggle_wrap_menu(self, checked: bool):
        self._toggle_wrap(checked)

    def _toggle_indent(self, checked: bool):
        self._act_indent.setChecked(checked)
        if hasattr(self, "_act_indent_m"):
            self._act_indent_m.setChecked(checked)
        for i in range(self._tabs.count()):
            self._tabs.widget(i).set_indent_guides(checked)

    def _toggle_indent_menu(self, checked: bool):
        self._toggle_indent(checked)

    def _toggle_blame(self, checked: bool):
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, ScriptTab):
                tab._editor.vcs_set_blame_visible(checked)

    def _apply_zoom(self, delta: int, size: int = 0):
        if delta != 0:
            self._zoom = max(CodeEditor.MIN_FONT, min(CodeEditor.MAX_FONT, self._zoom + delta))
        else:
            self._zoom = max(CodeEditor.MIN_FONT, min(CodeEditor.MAX_FONT, size))
        self._zoom_combo.setCurrentText(str(self._zoom))
        for i in range(self._tabs.count()):
            self._tabs.widget(i).set_font_size(self._zoom)

    def _check_current(self):
        tab = self._current_tab()
        if tab is None:
            return
        ed = tab._editor
        errs, warns = ed.diagnostic_counts()[0], ed.diagnostic_counts()[1]
        try:
            errs_list = ed._diagnostic_errors
            warns_list = ed._diagnostic_warnings
        except Exception:
            errs_list, warns_list = [], []
        if errs == 0 and warns == 0:
            QMessageBox.information(self, "Check Script", "No errors or warnings found.")
            return
        lines: list[str] = []
        for d in errs_list[:15]:
            lines.append("error [line " + str(d.line + 1) + "]: " + d.message)
        for d in warns_list[:15]:
            lines.append("warning [line " + str(d.line + 1) + "]: " + d.message)
        if errs > 0:
            QMessageBox.critical(self, "Check Script", "Found " + str(errs) + " error(s), " + str(warns) + " warning(s):" + chr(10) + chr(10) + chr(10).join(lines))
        else:
            QMessageBox.warning(self, "Check Script", "Found " + str(warns) + " warning(s):" + chr(10) + chr(10) + chr(10).join(lines))

    def _run_current(self):
        self._check_current()

    def _on_tab_changed(self, index: int):
        self._update_label()
        self._update_vcs_statusbar()
        ed = self._active_editor()
        if ed is not None:
            line = ed.textCursor().blockNumber() + 1
            col = ed.textCursor().positionInBlock() + 1
            self._on_cursor(line, col)
            try:
                e, w = ed.diagnostic_counts()
                self._on_diagnostics(e, w)
            except Exception:
                pass
        tab = self._current_tab()
        if tab is not None:
            self.tab_switched.emit(tab._file_path or "")
            fp = tab._file_path or ""
            if fp and fp in self._remote_cursors:
                tab._editor.set_remote_cursors(self._remote_cursors[fp])
            elif hasattr(tab, "_editor"):
                tab._editor.set_remote_cursors({})

    def _on_tab_closed(self, tab: QWidget):
        path = tab._file_path or ""
        self._remote_cursors.pop(path, None)
        index = self._tabs.indexOf(tab)
        if index >= 0:
            self._tabs.removeTab(index)
        if self._tabs.count() == 0:
            self._new_tab()
        self.tab_closed.emit(path)
