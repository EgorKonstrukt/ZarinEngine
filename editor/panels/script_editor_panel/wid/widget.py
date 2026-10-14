# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QLabel, QComboBox, QMenuBar, QStatusBar
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QAction, QKeySequence, QColor

from core.config.editor_scale import scale, scale_xy

from ..theme import menubar_stylesheet, toolbar_stylesheet, statusbar_stylesheet
from ..tabsp import CloseableTabWidget, ScriptTab
from ..edit import CodeEditor
from ..icons import qta_icon
from .tabs_host import TabsHostMixin
from .status import StatusMixin

try:
    from editor.panels.vcsp import _Git
except ImportError:
    _Git = None


class ScriptEditorWidget(TabsHostMixin, StatusMixin, QWidget):
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


_ScriptEditorWidget = ScriptEditorWidget
