# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QLabel, QFileDialog, QPlainTextEdit, QMessageBox, QComboBox, QMenuBar, QStatusBar, QDialog
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QAction, QKeySequence, QColor

from core.config.editor_scale import scale, scale_xy

from .theme import menubar_stylesheet, toolbar_stylesheet, statusbar_stylesheet
from .tabs import CloseableTabWidget, ScriptTab
from .editor import CodeEditor
from .icons import qta_icon
from . import ot as ot_mod

try:
    from editor.panels.vcs_panel import _Git
except ImportError:
    _Git = None


class ScriptEditorWidget(QWidget):
    tab_opened = pyqtSignal(str)
    tab_closed = pyqtSignal(str)
    tab_switched = pyqtSignal(str)
    collab_file_opened = pyqtSignal(str, str)
    collab_file_saved = pyqtSignal(str, str)
    collab_cursor_changed = pyqtSignal(str, int, int, int)
    collab_ops_ready = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom = CodeEditor.DEFAULT_FONT
        self._wrap = False
        self._remote_cursors: dict[str, dict[str, dict]] = {}
        self._ops_buffers: dict[str, list] = {}
        self._pending_local_ops: dict[str, list] = {}
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._do_auto_save)
        self._cursor_sync_timer = QTimer(self)
        self._cursor_sync_timer.setSingleShot(True)
        self._cursor_sync_timer.timeout.connect(self._send_cursor_sync)
        self._ops_flush_timer = QTimer(self)
        self._ops_flush_timer.setSingleShot(True)
        self._ops_flush_timer.timeout.connect(self._flush_and_send_ops)
        self._full_sync_timer = QTimer(self)
        self._full_sync_timer.timeout.connect(self._do_full_sync)
        self._full_sync_timer.start(10000)
        try:
            self._git = _Git() if _Git is not None else None
        except Exception:
            self._git = None
        self._git_available = False
        self._vcs_last_project = ""
        self._vcs_last_file = ""
        self._vcs_cached_branch = ""
        self._vcs_branch_time = 0.0
        self._vcs_refresh_timer = QTimer(self)
        self._vcs_refresh_timer.timeout.connect(self._vcs_timer_tick)
        self._vcs_refresh_timer.start(3000)
        self._setup_ui()
        self._try_detect_repo()

    def _try_detect_repo(self):
        eng = None
        try:
            from core.engine.engine import Engine
            eng = Engine.instance()
        except Exception:
            pass
        if eng and self._git is not None:
            project_path = getattr(eng, "_project_path", "") or ""
            if project_path:
                try:
                    self._git_available = self._git.detect(project_path)
                except Exception:
                    self._git_available = False
                self._update_vcs_statusbar()
                return
        self._git_available = False
        self._update_vcs_statusbar()

    def _vcs_timer_tick(self):
        if not self.isVisible():
            return
        eng = None
        try:
            from core.engine.engine import Engine
            eng = Engine.instance()
        except Exception:
            pass
        if eng:
            project_path = getattr(eng, "_project_path", "") or ""
            if project_path:
                if project_path != self._vcs_last_project:
                    self._vcs_last_project = project_path
                    try:
                        self._git_available = self._git.detect(project_path) if self._git is not None else False
                    except Exception:
                        self._git_available = False
                    self._vcs_last_file = ""
                    self._vcs_branch_time = 0.0
                tab = self._current_tab()
                file_path = tab._file_path if tab and tab._file_path else ""
                if file_path != self._vcs_last_file:
                    self._vcs_last_file = file_path
                    if tab and file_path and self._git_available:
                        tab._editor.vcs_refresh()
                self._update_vcs_statusbar()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._make_actions()
        menubar = QMenuBar()
        menubar.setNativeMenuBar(False)
        menubar.setStyleSheet(menubar_stylesheet())
        self._build_menubar(menubar)
        layout.addWidget(menubar)
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(*scale_xy(18, 18)))
        toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly if qta_icon("new").isNull()
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        toolbar.setStyleSheet(toolbar_stylesheet())
        toolbar.addAction(self._act_new)
        toolbar.addAction(self._act_open)
        toolbar.addAction(self._act_save)
        toolbar.addAction(self._act_save_as)
        toolbar.addSeparator()
        toolbar.addAction(self._act_undo)
        toolbar.addAction(self._act_redo)
        toolbar.addAction(self._act_cut)
        toolbar.addAction(self._act_copy)
        toolbar.addAction(self._act_paste)
        toolbar.addSeparator()
        toolbar.addAction(self._act_wrap)
        toolbar.addAction(self._act_indent)
        toolbar.addAction(self._act_zoom_out)
        self._zoom_combo = QComboBox()
        self._zoom_combo.setEditable(False)
        self._zoom_combo.addItems(["8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28"])
        self._zoom_combo.setCurrentText(str(self._zoom))
        self._zoom_combo.setFixedWidth(scale(56))
        self._zoom_combo.setToolTip("Font Size")
        self._zoom_combo.currentTextChanged.connect(
            lambda t: self._apply_zoom(0, int(t) if t.isdigit() else self._zoom)
        )
        toolbar.addWidget(self._zoom_combo)
        toolbar.addAction(self._act_zoom_in)
        toolbar.addSeparator()
        toolbar.addAction(self._act_run)
        toolbar.addAction(self._act_doc)
        from PyQt6.QtWidgets import QSizePolicy
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self._diag_label = QLabel("")
        self._diag_label.setStyleSheet("color: rgb(200,150,100); padding: 0 6px;")
        toolbar.addWidget(self._diag_label)
        self._vcs_branch_label = QLabel("")
        self._vcs_branch_label.setStyleSheet("color: rgb(154,154,154); padding: 0 4px; font-weight: bold;")
        toolbar.addWidget(self._vcs_branch_label)
        self._vcs_status_label = QLabel("")
        self._vcs_status_label.setStyleSheet("color: rgb(154,154,154); padding: 0 4px;")
        toolbar.addWidget(self._vcs_status_label)
        self._file_label = QLabel("  No file")
        self._file_label.setStyleSheet("color: rgb(154,154,154); padding: 0 6px;")
        toolbar.addWidget(self._file_label)
        layout.addWidget(toolbar)
        self._tabs = CloseableTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)
        statusbar = QStatusBar()
        statusbar.setStyleSheet(statusbar_stylesheet())
        self._status_pos = QLabel("Ln 1, Col 1")
        self._status_info = QLabel("")
        statusbar.addPermanentWidget(self._status_info, 1)
        statusbar.addPermanentWidget(self._status_pos)
        layout.addWidget(statusbar)
        self._statusbar = statusbar
        self._new_tab()

    def _make_actions(self):
        self._act_new = QAction(qta_icon("new"), "New", self)
        self._act_new.setToolTip("New Script")
        self._act_new.setShortcut(QKeySequence("Ctrl+N"))
        self._act_new.triggered.connect(self._new_tab)
        self._act_open = QAction(qta_icon("open"), "Open", self)
        self._act_open.setToolTip("Open Script")
        self._act_open.setShortcut(QKeySequence("Ctrl+O"))
        self._act_open.triggered.connect(self._open_tab)
        self._act_save = QAction(qta_icon("save"), "Save", self)
        self._act_save.setToolTip("Save")
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.triggered.connect(self._save_current)
        self._act_save_as = QAction(qta_icon("save_as"), "Save As", self)
        self._act_save_as.setToolTip("Save As")
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self._save_current_as)
        self._act_undo = QAction(qta_icon("undo"), "Undo", self)
        self._act_undo.setToolTip("Undo (Ctrl+Z)")
        self._act_undo.triggered.connect(self._undo)
        self._act_redo = QAction(qta_icon("redo"), "Redo", self)
        self._act_redo.setToolTip("Redo (Ctrl+Y)")
        self._act_redo.triggered.connect(self._redo)
        self._act_cut = QAction(qta_icon("cut"), "Cut", self)
        self._act_cut.setToolTip("Cut")
        self._act_cut.triggered.connect(self._cut)
        self._act_copy = QAction(qta_icon("copy"), "Copy", self)
        self._act_copy.setToolTip("Copy")
        self._act_copy.triggered.connect(self._copy)
        self._act_paste = QAction(qta_icon("paste"), "Paste", self)
        self._act_paste.setToolTip("Paste")
        self._act_paste.triggered.connect(self._paste)
        self._act_wrap = QAction(qta_icon("word_wrap"), "Word Wrap", self)
        self._act_wrap.setToolTip("Toggle Word Wrap")
        self._act_wrap.setCheckable(True)
        self._act_wrap.triggered.connect(self._toggle_wrap)
        self._act_indent = QAction(qta_icon("indent"), "Indent Guides", self)
        self._act_indent.setToolTip("Toggle Indentation Guides")
        self._act_indent.setCheckable(True)
        self._act_indent.setChecked(True)
        self._act_indent.triggered.connect(self._toggle_indent)
        self._act_zoom_out = QAction(qta_icon("zoom_out"), "Zoom Out", self)
        self._act_zoom_out.setToolTip("Zoom Out")
        self._act_zoom_out.triggered.connect(lambda: self._apply_zoom(-1))
        self._act_zoom_in = QAction(qta_icon("zoom_in"), "Zoom In", self)
        self._act_zoom_in.setToolTip("Zoom In")
        self._act_zoom_in.triggered.connect(lambda: self._apply_zoom(1))
        self._act_run = QAction(qta_icon("run"), "Check", self)
        self._act_run.setToolTip("Check script for errors")
        self._act_run.triggered.connect(self._check_current)
        self._act_doc = QAction("Docs", self)
        self._act_doc.setToolTip("Show Python documentation (Ctrl+Q)")
        self._act_doc.setShortcut(QKeySequence("Ctrl+Q"))
        self._act_doc.triggered.connect(self._show_docs)
        self._act_blame = QAction("Annotate with Git Blame", self)
        self._act_blame.setToolTip("Toggle git blame annotations")
        self._act_blame.setCheckable(True)
        self._act_blame.setChecked(True)
        self._act_blame.triggered.connect(self._toggle_blame)
        self._act_vcs_commit = QAction("Commit File...", self)
        self._act_vcs_commit.setToolTip("Commit current file")
        self._act_vcs_commit.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self._act_vcs_commit.triggered.connect(self._vcs_commit)
        self._act_vcs_diff = QAction("Diff with HEAD", self)
        self._act_vcs_diff.setToolTip("Show diff of current file against HEAD")
        self._act_vcs_diff.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self._act_vcs_diff.triggered.connect(self._vcs_diff)
        self._act_vcs_history = QAction("Show History", self)
        self._act_vcs_history.setToolTip("Show git log for current file")
        self._act_vcs_history.setShortcut(QKeySequence("Ctrl+Shift+H"))
        self._act_vcs_history.triggered.connect(self._vcs_history)
        self._act_vcs_revert = QAction("Revert File...", self)
        self._act_vcs_revert.setToolTip("Discard changes and revert to HEAD")
        self._act_vcs_revert.triggered.connect(self._vcs_revert)

    def _build_menubar(self, menubar: QMenuBar):
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self._act_new)
        file_menu.addAction(self._act_open)
        file_menu.addSeparator()
        file_menu.addAction(self._act_save)
        file_menu.addAction(self._act_save_as)
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self._act_undo)
        edit_menu.addAction(self._act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act_cut)
        edit_menu.addAction(self._act_copy)
        edit_menu.addAction(self._act_paste)
        view_menu = menubar.addMenu("View")
        self._act_wrap_m = QAction("Word Wrap", self)
        self._act_wrap_m.setCheckable(True)
        self._act_wrap_m.setChecked(self._wrap)
        self._act_wrap_m.triggered.connect(self._toggle_wrap_menu)
        view_menu.addAction(self._act_wrap_m)
        self._act_indent_m = QAction("Indentation Guides", self)
        self._act_indent_m.setCheckable(True)
        self._act_indent_m.setChecked(True)
        self._act_indent_m.triggered.connect(self._toggle_indent_menu)
        view_menu.addAction(self._act_indent_m)
        view_menu.addSeparator()
        view_menu.addAction(self._act_blame)
        act_zoom_in = QAction("Zoom In", self)
        act_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        act_zoom_in.triggered.connect(lambda: self._apply_zoom(1))
        view_menu.addAction(act_zoom_in)
        act_zoom_out = QAction("Zoom Out", self)
        act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        act_zoom_out.triggered.connect(lambda: self._apply_zoom(-1))
        view_menu.addAction(act_zoom_out)
        vcs_menu = menubar.addMenu("VCS")
        vcs_menu.addAction(self._act_vcs_commit)
        vcs_menu.addAction(self._act_vcs_diff)
        vcs_menu.addAction(self._act_vcs_history)
        vcs_menu.addSeparator()
        vcs_menu.addAction(self._act_vcs_revert)
        run_menu = menubar.addMenu("Run")
        self._act_run_m = QAction("Check Script", self)
        self._act_run_m.triggered.connect(self._check_current)
        run_menu.addAction(self._act_run_m)
        help_menu = menubar.addMenu("Help")
        act_doc_m = QAction("Python Documentation", self)
        act_doc_m.setShortcut(QKeySequence("Ctrl+Q"))
        act_doc_m.triggered.connect(self._show_docs)
        help_menu.addAction(act_doc_m)

    def _current_tab(self) -> Optional[ScriptTab]:
        return self._tabs.currentWidget()

    def _active_editor(self) -> Optional[CodeEditor]:
        tab = self._current_tab()
        return tab._editor if tab is not None else None

    def _bind_tab_signals(self, tab: ScriptTab):
        tab._editor.cursorMoved.connect(self._on_cursor)
        tab._editor.modificationChanged.connect(self._on_modified)
        tab._editor.textChanged.connect(self._on_local_text_changed)
        tab._editor.cursorPositionChanged.connect(self._on_local_cursor_moved)
        tab._editor.diagnostics_changed.connect(lambda e, w: self._on_diagnostics(e, w))
        tab._editor.set_ops_callback(lambda pos, removed, added: self._on_op_captured(tab, pos, removed, added))

    def _on_diagnostics(self, errors: int, warnings: int):
        try:
            if errors > 0:
                self._diag_label.setText("✖ " + str(errors) + "  ⚠ " + str(warnings))
            elif warnings > 0:
                self._diag_label.setText("⚠ " + str(warnings))
            else:
                self._diag_label.setText("✓ clean")
        except Exception:
            pass

    def _show_docs(self):
        ed = self._active_editor()
        if ed is not None:
            ed.show_documentation_at_cursor()

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

    def _vcs_commit(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            QMessageBox.information(self, "No Repository", "No git repository detected.")
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        rc, _, _ = self._git.add([rel])
        if rc != 0:
            QMessageBox.warning(self, "Stage Failed", "Failed to stage file.")
            return
        from PyQt6.QtWidgets import QInputDialog
        msg, ok = QInputDialog.getText(self, "Commit", "Commit message:")
        if not ok or not msg.strip():
            self._git.unstage([rel])
            return
        rc, out, err = self._git.commit(msg.strip())
        if rc == 0:
            QMessageBox.information(self, "Committed", f"Committed:{chr(10)}{msg.strip()}")
            tab._editor.vcs_refresh()
            self._update_vcs_statusbar()
        else:
            QMessageBox.critical(self, "Commit Failed", f"Error:{chr(10)}{err or out}")

    def _vcs_diff(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        diff = self._git.file_diff(rel)
        if not diff:
            diff = self._git.file_diff(rel, staged=True)
        if not diff:
            diff = "No changes against HEAD"
        from editor.panels.vcs_panel import _DiffView
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Diff: {os.path.basename(tab._file_path)}")
        dlg.setMinimumSize(scale(700), scale(500))
        layout = QVBoxLayout(dlg)
        diff_view = _DiffView()
        diff_view.show_diff(diff)
        layout.addWidget(diff_view)
        dlg.exec()

    def _vcs_history(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        rc, out, _ = self._git.run_sync("log", "--oneline", "--decorate", "--", rel, timeout=15)
        if rc != 0 or not out.strip():
            QMessageBox.information(self, "History", "No history for this file.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"History: {os.path.basename(tab._file_path)}")
        dlg.setMinimumSize(scale(600), scale(400))
        layout = QVBoxLayout(dlg)
        te = QPlainTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Courier New", 10))
        te.setPlainText(out)
        layout.addWidget(te)
        dlg.exec()

    def _vcs_revert(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            return
        reply = QMessageBox.question(
            self, "Revert File",
            f"Discard all changes to {os.path.basename(tab._file_path)}?{chr(10)}"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        rc, _, err = self._git.restore([rel])
        if rc == 0:
            tab.open_file(tab._file_path)
            self._update_vcs_statusbar()
        else:
            QMessageBox.critical(self, "Revert Failed", f"Error:{chr(10)}{err}")

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

    def _on_cursor(self, line: int, col: int):
        self._status_pos.setText(f"Ln {line}, Col {col}")

    def _on_modified(self, modified: bool):
        tab = self._current_tab()
        if tab is not None:
            self._status_info.setText("Modified" if modified else "")

    def _on_local_text_changed(self):
        self._auto_save_timer.start(2000)

    def _do_auto_save(self):
        tab = self._current_tab()
        if tab is None or not tab._file_path or not tab._dirty:
            return
        try:
            with open(tab._file_path, "w", encoding="utf-8") as f:
                f.write(tab._editor.toPlainText())
            tab._dirty = False
            tab._editor.document().setModified(False)
            tab._editor.vcs_set_file(tab._file_path)
            tab._update_title()
            if tab._file_path:
                self.collab_file_saved.emit(tab._file_path, tab._editor.toPlainText())
        except Exception:
            pass

    def _on_op_captured(self, tab, pos: int, removed: int, added: str):
        path = tab._file_path
        if not path:
            return
        self._pending_local_ops.setdefault(path, []).append((pos, removed, added))
        self._ops_buffers.setdefault(path, []).append((pos, removed, added))
        if not self._ops_flush_timer.isActive():
            self._ops_flush_timer.start(100)

    def _flush_and_send_ops(self):
        for path, buffer in list(self._ops_buffers.items()):
            if buffer:
                batch = list(buffer)
                buffer.clear()
                self.collab_ops_ready.emit(path, batch)

    def apply_remote_ops(self, path: str, ops: list):
        from PyQt6.QtGui import QTextCursor as _QTC
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, ScriptTab) and tab._file_path == path:
                editor = tab._editor
                pending = list(self._pending_local_ops.get(path, []))
                transformed = []
                for rop in ops:
                    for lop in pending:
                        rop = ot_mod.transform_op(rop, lop)
                    transformed.append(rop)
                editor._suppress_ops = True
                editor.document().blockSignals(True)
                for pos, removed, added in transformed:
                    if pos < 0:
                        continue
                    text_len = len(editor.toPlainText())
                    if removed and removed > 0 and pos + removed > text_len:
                        continue
                    tc = editor.textCursor()
                    tc.setPosition(pos)
                    if removed and removed > 0:
                        end = min(pos + removed, text_len)
                        tc.setPosition(end, _QTC.MoveMode.KeepAnchor)
                    tc.insertText(added)
                editor.document().blockSignals(False)
                editor._old_text = editor.toPlainText()
                editor._suppress_ops = False
                new_pending = []
                for lop in pending:
                    for rop in transformed:
                        lop = ot_mod.transform_op(lop, rop)
                    new_pending.append(lop)
                self._pending_local_ops[path] = new_pending
                return

    def clear_pending_ops(self, path: str):
        self._pending_local_ops.pop(path, None)
        self._ops_buffers.pop(path, None)

    def _do_full_sync(self):
        tab = self._current_tab()
        if tab and tab._file_path:
            self.clear_pending_ops(tab._file_path)
            self.collab_file_saved.emit(tab._file_path, tab._editor.toPlainText())

    def _on_local_cursor_moved(self):
        self._cursor_sync_timer.start(50)

    def _send_cursor_sync(self):
        tab = self._current_tab()
        if tab is None or not tab._file_path:
            return
        cursor = tab._editor.textCursor()
        pos = cursor.position()
        self.collab_cursor_changed.emit(tab._file_path, pos, cursor.anchor(), pos)

    def update_remote_cursor(self, peer_id: str, path: str, pos: int, sel_anchor: int, sel_end: int, color: list[float], name: str):
        if not path:
            return
        cursors_for_path = self._remote_cursors.setdefault(path, {})
        cursors_for_path[peer_id] = {
            "pos": pos,
            "sel_anchor": sel_anchor,
            "sel_end": sel_end,
            "color": QColor.fromRgbF(*color[:3]),
            "name": name,
        }
        tab = self._current_tab()
        if tab and tab._file_path == path:
            tab._editor.set_remote_cursors(cursors_for_path)

    def _update_label(self):
        tab = self._current_tab()
        if tab is None:
            self._file_label.setText("  No file")
        elif tab._file_path:
            self._file_label.setText(f"  {os.path.basename(tab._file_path)}")
        else:
            self._file_label.setText("  Untitled Script")

    def _update_vcs_statusbar(self):
        import time as _time
        branch = ""
        status = ""
        if self._git_available and self._git is not None:
            try:
                repo = self._git.repo_root
            except Exception:
                repo = ""
            if repo:
                if _time.perf_counter() - self._vcs_branch_time > 30.0 or not self._vcs_cached_branch:
                    try:
                        self._vcs_cached_branch = self._git.current_branch() or ""
                    except Exception:
                        self._vcs_cached_branch = ""
                    self._vcs_branch_time = _time.perf_counter()
                branch = self._vcs_cached_branch
                tab = self._current_tab()
                if isinstance(tab, ScriptTab):
                    ed = tab._editor
                    file_status = ed.vcs_file_status()
                    if file_status:
                        status_labels = {
                            "modified": " modified",
                            "untracked": " untracked",
                            "deleted": " deleted",
                            "conflict": " conflict",
                        }
                        status = status_labels.get(file_status, file_status)
        if branch:
            self._vcs_branch_label.setText(f"  [{branch}]  ")
            self._vcs_branch_label.show()
            self._vcs_status_label.setText(status)
            self._vcs_status_label.show()
        else:
            self._vcs_branch_label.hide()
            self._vcs_status_label.hide()


_ScriptEditorWidget = ScriptEditorWidget
