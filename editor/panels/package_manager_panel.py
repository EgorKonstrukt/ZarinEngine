# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import threading

from PyQt6.QtCore import Qt, QObject, QTimer, QItemSelectionModel, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.panels import package_manager_core as core

try:
    import qtawesome as qta
except ImportError:
    qta = None


FILTER_ALL = "All"
FILTER_UPDATES = "Updates available"
FILTER_UPTODATE = "Up to date"

TREE_DEPS = "Dependencies"
TREE_REVERSE = "Dependents"


class _TaskBridge(QObject):
    line = pyqtSignal(str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class PackageManagerPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Python Packages", parent)
        self.setObjectName("PackageManagerDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self._packages: list[core.PackageInfo] = []
        self._by_key: dict[str, core.PackageInfo] = {}
        self._latest: dict[str, str] = {}
        self._client = core.PyPiClient()
        self._index = core.SimpleIndex()
        self._busy = 0
        self._cancel = threading.Event()
        self._pending_detail = ""
        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        self._detail_timer.setInterval(400)
        self._detail_timer.timeout.connect(self._flush_pending_detail)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self._install_btn = self._tool_button("Install...", "fa5s.plus-circle", self._open_install)
        self._update_btn = self._tool_button("Update", "fa5s.level-up-alt", self._update_selected)
        self._update_all_btn = self._tool_button("Update All", "fa5s.cloud-upload-alt", self._update_all)
        self._uninstall_btn = self._tool_button("Uninstall", "fa5s.trash-alt", self._uninstall_selected)
        self._download_btn = self._tool_button("Download...", "fa5s.download", self._open_download)
        self._check_btn = self._tool_button("Check Updates", "fa5s.sync-alt", self._check_updates_online)
        self._refresh_btn = self._tool_button("Refresh", "fa5s.redo", self.refresh)
        for b in (self._install_btn, self._update_btn, self._update_all_btn,
                  self._uninstall_btn, self._download_btn, self._check_btn, self._refresh_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        self._stop_btn = self._tool_button("Stop", "fa5s.stop", self._cancel_running)
        self._stop_btn.setEnabled(False)
        bar.addWidget(self._stop_btn)
        layout.addLayout(bar)

        file_bar = QHBoxLayout()
        file_bar.setSpacing(4)
        self._export_btn = self._tool_button("Export requirements.txt", "fa5s.file-export", self._export_requirements)
        self._import_btn = self._tool_button("Install from requirements.txt", "fa5s.file-import", self._install_requirements)
        self._freeze_btn = self._tool_button("Freeze to Log", "fa5s.icicles", self._freeze_to_log)
        for b in (self._export_btn, self._import_btn, self._freeze_btn):
            file_bar.addWidget(b)
        file_bar.addStretch(1)
        layout.addLayout(file_bar)

        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(4)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by name or summary...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._fill_table)
        filter_bar.addWidget(self._search, 1)
        self._filter = QComboBox()
        self._filter.addItems([FILTER_ALL, FILTER_UPDATES, FILTER_UPTODATE])
        self._filter.currentTextChanged.connect(self._fill_table)
        filter_bar.addWidget(self._filter)
        self._count_label = QLabel("0 packages")
        self._count_label.setStyleSheet("color: #9a9a9a;")
        filter_bar.addWidget(self._count_label)
        layout.addLayout(filter_bar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Name", "Installed", "Latest", "Size", "Status"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._table_context_menu)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(self._on_double_click)
        self._splitter.addWidget(self._table)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_details_tab(), "Details")
        self._tabs.addTab(self._build_tree_tab(), "Dependency Tree")
        self._tabs.addTab(self._build_log_tab(), "Log")
        self._splitter.addWidget(self._tabs)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([620, 460])
        layout.addWidget(self._splitter, 1)

        bottom = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setFixedWidth(160)
        self._progress.setTextVisible(False)
        bottom.addWidget(self._progress)
        self._status = QLabel("")
        self._status.setStyleSheet("color: #9a9a9a;")
        bottom.addWidget(self._status, 1)
        layout.addLayout(bottom)

        self.setWidget(root)

    def _tool_button(self, text: str, icon: str, slot) -> QPushButton:
        btn = QPushButton(text)
        if qta is not None:
            try:
                btn.setIcon(qta.icon(icon, color="#d4d4d4"))
            except Exception:
                pass
        btn.clicked.connect(lambda _checked=False, _slot=slot: _slot())
        btn.setStyleSheet("padding: 4px 10px;")
        return btn

    def _build_details_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self._detail_title = QLabel("No package selected")
        f = QFont()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self._detail_title.setFont(f)
        self._detail_title.setWordWrap(True)
        layout.addWidget(self._detail_title)
        self._detail_summary = QLabel("")
        self._detail_summary.setWordWrap(True)
        self._detail_summary.setStyleSheet("color: #c8c8e8;")
        layout.addWidget(self._detail_summary)
        form = QGroupBox("Metadata")
        form_layout = QFormLayout(form)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._detail_fields: dict[str, QLabel] = {}
        for key, label in (("latest", "Latest release"), ("author", "Author"), ("license", "License"),
                           ("requires_python", "Requires Python"), ("home_page", "Home page"),
                           ("location", "Location"), ("size", "Size")):
            val = QLabel("-")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setWordWrap(True)
            form_layout.addRow(label + ":", val)
            self._detail_fields[key] = val
        layout.addWidget(form)
        req_group = QGroupBox("Requires")
        req_layout = QVBoxLayout(req_group)
        self._detail_requires = QTreeWidget()
        self._detail_requires.setHeaderLabels(["Requirement", "Installed"])
        self._detail_requires.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._detail_requires.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._detail_requires.itemDoubleClicked.connect(self._jump_to_item_package)
        req_layout.addWidget(self._detail_requires)
        layout.addWidget(req_group, 1)
        self._detail_notes = QLabel("")
        self._detail_notes.setWordWrap(True)
        self._detail_notes.setStyleSheet("color: #e0a040;")
        layout.addWidget(self._detail_notes)
        return w

    def _build_tree_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self._tree_mode = QComboBox()
        self._tree_mode.addItems([TREE_DEPS, TREE_REVERSE])
        self._tree_mode.currentTextChanged.connect(self._fill_tree)
        bar.addWidget(QLabel("Show:"))
        bar.addWidget(self._tree_mode)
        expand_btn = QPushButton("Expand all")
        expand_btn.clicked.connect(lambda: self._tree.expandAll())
        bar.addWidget(expand_btn)
        collapse_btn = QPushButton("Collapse all")
        collapse_btn.clicked.connect(lambda: self._tree.collapseAll())
        bar.addWidget(collapse_btn)
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_tree)
        bar.addWidget(copy_btn)
        self._tree_scope = QCheckBox("Selected only")
        self._tree_scope.setChecked(True)
        self._tree_scope.stateChanged.connect(self._fill_tree)
        bar.addWidget(self._tree_scope)
        self._tree_extras = QCheckBox("Include optional extras")
        self._tree_extras.stateChanged.connect(self._fill_tree)
        bar.addWidget(self._tree_extras)
        bar.addStretch(1)
        layout.addLayout(bar)
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Package", "Version", "Spec", "Note"])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemDoubleClicked.connect(self._jump_to_item_package)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._tree_context_menu)
        layout.addWidget(self._tree, 1)
        self._tree_label = QLabel("")
        self._tree_label.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(self._tree_label)
        return w

    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        bar = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self._log_view.clear())
        bar.addWidget(clear_btn)
        copy_btn = QPushButton("Copy all")
        copy_btn.clicked.connect(self._copy_log)
        bar.addWidget(copy_btn)
        bar.addStretch(1)
        layout.addLayout(bar)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(8000)
        self._log_view.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")
        layout.addWidget(self._log_view, 1)
        return w

    def _append_log(self, text: str):
        self._log_view.appendPlainText(text)
        sb = self._log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_log(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._log_view.toPlainText())
        self._status.setText("Log copied to clipboard")

    def _set_busy(self, busy: bool):
        self._busy = max(0, self._busy + (1 if busy else -1))
        running = self._busy > 0
        self._progress.setRange(0, 0 if running else 1)
        self._stop_btn.setEnabled(running)
        for b in (self._install_btn, self._update_all_btn, self._refresh_btn, self._check_btn,
                  self._import_btn, self._download_btn):
            b.setEnabled(not running)

    def _cancel_running(self):
        self._cancel.set()
        self._append_log("Stopping current operation...")

    def _run_async(self, work, on_done=None, on_failed=None, on_line=None):
        bridge = _TaskBridge(self)
        if on_line is not None:
            bridge.line.connect(on_line)
        if on_done is not None:
            bridge.done.connect(on_done)
        if on_failed is not None:
            bridge.failed.connect(on_failed)
        else:
            bridge.failed.connect(self._on_task_failed)

        def runner():
            try:
                result = work(bridge)
                bridge.done.emit(result)
            except Exception as e:
                bridge.failed.emit(str(e))

        self._set_busy(True)
        threading.Thread(target=runner, daemon=True).start()
        return bridge

    def _on_task_failed(self, message: str):
        self._set_busy(False)
        self._append_log(f"ERROR: {message}")
        self._status.setText("Ready")

    def _pip_task(self, args: list[str], label: str, after=None):
        self._append_log(f"$ pip {' '.join(args)}")

        def work(bridge):
            def on_line(line):
                bridge.line.emit(line)
            code = core.run_pip_streaming(args, on_line=on_line, cancel_event=self._cancel)
            return code

        def on_line(line):
            self._append_log(line)

        def on_done(code):
            self._set_busy(False)
            self._cancel.clear()
            self._append_log(f"{label} finished with code {code}")
            if after is not None:
                after(code)
            self.refresh(check_updates=False)

        self._run_async(work, on_done=on_done, on_line=on_line)

    def refresh(self, check_updates: bool = True):
        self._status.setText("Reading installed packages...")
        known_latest = dict(self._latest)

        def load(bridge):
            return core.list_installed(with_size=True)

        def check(bridge):
            return core.check_outdated()

        def on_outdated(result):
            outdated, raw = result
            self._set_busy(False)
            merged = dict(self._latest)
            merged.update(outdated)
            self._latest = {k: v for k, v in merged.items() if k in self._by_key}
            self._apply_latest()
            self._fill_table()
            self._update_status()
            updates = sum(1 for p in self._packages if p.status == "update")
            self._append_log(f"Update check done: {updates} package(s) can be updated")
            if raw and not outdated and "ERROR" in raw.upper():
                self._append_log(raw)

        def on_loaded(packages):
            self._packages = packages
            self._by_key = {p.key: p for p in packages}
            self._latest = {k: v for k, v in known_latest.items() if k in self._by_key}
            self._apply_latest()
            self._set_busy(False)
            self._fill_table()
            self._fill_tree()
            self._update_details()
            self._update_status()
            self._append_log(f"Loaded {len(packages)} installed packages")
            if check_updates:
                self._status.setText("Checking for updates...")
                self._run_async(check, on_done=on_outdated)

        self._run_async(load, on_done=on_loaded)

    def _apply_latest(self):
        for p in self._packages:
            latest = self._latest.get(p.key, "")
            p.latest = latest
            if not latest:
                p.status = "editable" if p.editable else "unknown"
            elif latest == p.version:
                p.status = "up to date"
            else:
                p.status = "update"

    def _visible_packages(self) -> list[core.PackageInfo]:
        query = self._search.text().strip().lower()
        mode = self._filter.currentText()
        out = []
        for p in self._packages:
            if mode == FILTER_UPDATES and p.status != "update":
                continue
            if mode == FILTER_UPTODATE and p.status != "up to date":
                continue
            if query and query not in p.name.lower() and query not in (p.summary or "").lower():
                continue
            out.append(p)
        return out

    def _fill_table(self, *_):
        selected = set(self._selected_keys())
        packages = self._visible_packages()
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._table.setRowCount(len(packages))
        for row, p in enumerate(packages):
            name_item = QTableWidgetItem(p.name)
            name_item.setData(Qt.ItemDataRole.UserRole, p.key)
            inst_item = QTableWidgetItem(p.version)
            inst_item.setData(Qt.ItemDataRole.UserRole, p.version)
            inst_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            latest_item = QTableWidgetItem(p.latest or "-")
            latest_item.setData(Qt.ItemDataRole.UserRole, p.latest or "")
            latest_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            size_item = QTableWidgetItem(core.format_size(p.size))
            size_item.setData(Qt.ItemDataRole.UserRole, p.size)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            status_item = QTableWidgetItem(p.status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if p.status == "update":
                status_item.setForeground(QColor("#7ec699"))
                latest_item.setForeground(QColor("#7ec699"))
            elif p.status == "up to date":
                status_item.setForeground(QColor("#8a8a8a"))
            elif p.status == "editable":
                status_item.setForeground(QColor("#d7ba7d"))
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, inst_item)
            self._table.setItem(row, 2, latest_item)
            self._table.setItem(row, 3, size_item)
            self._table.setItem(row, 4, status_item)
        if selected:
            sm = self._table.selectionModel()
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) in selected:
                    index = self._table.model().index(row, 0)
                    sm.select(index, QItemSelectionModel.SelectionFlag.Select |
                              QItemSelectionModel.SelectionFlag.Rows)
        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)
        self._update_details()
        updates = sum(1 for p in self._packages if p.status == "update")
        self._count_label.setText(f"{len(packages)} shown / {len(self._packages)} installed · {updates} updates")

    def _selected_keys(self) -> list[str]:
        keys = []
        for index in self._table.selectionModel().selectedRows():
            item = self._table.item(index.row(), 0)
            if item is not None:
                key = item.data(Qt.ItemDataRole.UserRole)
                if key and key not in keys:
                    keys.append(key)
        return keys

    def _selected_packages(self) -> list[core.PackageInfo]:
        return [self._by_key[k] for k in self._selected_keys() if k in self._by_key]

    def _on_selection_changed(self):
        self._update_details()
        self._fill_tree()

    def _on_double_click(self, item):
        key = item.data(Qt.ItemDataRole.UserRole) if item.column() == 0 else None
        if not key:
            row = item.row()
            name_item = self._table.item(row, 0)
            key = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        if key:
            self._show_on_pypi(key)

    def _update_details(self):
        keys = self._selected_keys()
        if not keys:
            self._detail_title.setText("No package selected")
            self._detail_summary.setText("")
            for label in self._detail_fields.values():
                label.setText("-")
            self._detail_requires.clear()
            self._detail_notes.setText("")
            return
        if len(keys) > 1:
            total = sum(self._by_key[k].size for k in keys if k in self._by_key)
            self._detail_title.setText(f"{len(keys)} packages selected")
            self._detail_summary.setText("")
            self._detail_fields["size"].setText(core.format_size(total))
            self._detail_notes.setText("")
            return
        key = keys[0]
        p = self._by_key.get(key)
        if p is None:
            return
        self._detail_title.setText(f"{p.name} {p.version}")
        self._detail_summary.setText(p.summary or "")
        self._detail_fields["latest"].setText(p.latest or "-")
        self._detail_fields["author"].setText(p.author or "-")
        self._detail_fields["license"].setText((p.license or "-")[:120])
        self._detail_fields["requires_python"].setText("-")
        self._detail_fields["home_page"].setText(p.home_page or "-")
        self._detail_fields["location"].setText(p.location or "-")
        self._detail_fields["size"].setText(core.format_size(p.size))
        self._detail_requires.clear()
        for raw in p.requires:
            req = core.parse_requirement(raw)
            target = self._by_key.get(req.key)
            label = req.display
            if core.requirement_is_optional(req):
                label += "  [extra]"
            node = QTreeWidgetItem([label, target.version if target else "missing"])
            if target is None:
                node.setForeground(1, QColor("#e06c75"))
            self._detail_requires.addTopLevelItem(node)
        if not p.requires:
            self._detail_requires.addTopLevelItem(QTreeWidgetItem(["(no declared requirements)", ""]))
        note = ""
        if p.status == "update":
            note = f"Update available: {p.version} → {p.latest}"
        elif p.status == "editable":
            note = "Editable / development install"
        self._detail_notes.setText(note)
        self._pending_detail = p.name
        self._detail_timer.start()

    def _flush_pending_detail(self):
        name = self._pending_detail
        self._pending_detail = ""
        if name:
            self._fetch_online_details(name)

    def _fetch_online_details(self, name: str):
        if self._client.cached_project(name) is not None:
            try:
                meta = self._client.metadata(name)
            except Exception:
                return
            self._apply_online_details(name, meta)
            return

        def work(bridge):
            return self._client.metadata(name)

        def on_done(meta):
            self._set_busy(False)
            self._apply_online_details(name, meta)

        self._run_async(work, on_done=on_done)

    def _apply_online_details(self, name: str, meta: dict):
        keys = self._selected_keys()
        if len(keys) != 1:
            return
        p = self._by_key.get(keys[0])
        if p is None or core.normalize_name(p.name) != core.normalize_name(name):
            return
        if meta.get("version"):
            self._detail_fields["latest"].setText(str(meta["version"]))
        self._detail_fields["requires_python"].setText(str(meta.get("requires_python") or "-"))
        if meta.get("home_page"):
            self._detail_fields["home_page"].setText(str(meta["home_page"]))
        if meta.get("author") and not p.author:
            self._detail_fields["author"].setText(str(meta["author"]))
        if meta.get("license") and not p.license:
            self._detail_fields["license"].setText(str(meta["license"])[:120])
        online_reqs = meta.get("requires_dist") or []
        if online_reqs:
            existing = {self._detail_requires.topLevelItem(i).text(0).replace("  [extra]", "")
                        for i in range(self._detail_requires.topLevelItemCount())}
            for raw in online_reqs:
                req = core.parse_requirement(raw)
                if req.display in existing:
                    continue
                target = self._by_key.get(req.key)
                label = req.display
                if core.requirement_is_optional(req):
                    label += "  [extra]"
                node = QTreeWidgetItem([label, target.version if target else "missing"])
                if target is None:
                    node.setForeground(1, QColor("#e06c75"))
                self._detail_requires.addTopLevelItem(node)
        latest = str(meta.get("version") or "")
        if latest and latest != self._latest.get(p.key):
            self._latest[p.key] = latest
            p.latest = latest
            self._apply_latest()
            self._fill_table()

    def _fill_tree(self, *_):
        self._tree.clear()
        if not self._packages:
            self._tree_label.setText("No installed packages")
            return
        reverse = self._tree_mode.currentText() == TREE_REVERSE
        keys = self._selected_keys()
        selected_only = self._tree_scope.isChecked()
        roots = keys if (selected_only and keys) else None
        try:
            nodes = core.build_dependency_tree(
                self._packages,
                reverse=reverse,
                roots=roots,
                include_extras=self._tree_extras.isChecked())
        except Exception as e:
            self._tree_label.setText(f"Tree build failed: {e}")
            return
        total = 0
        for node in nodes:
            item = self._make_tree_item(node)
            self._tree.addTopLevelItem(item)
            total += 1 + self._count_items(item)
        self._tree.expandToDepth(0)
        if selected_only and keys:
            scope = ", ".join(self._by_key[k].name for k in keys if k in self._by_key)
            self._tree_label.setText(f"{TREE_REVERSE if reverse else TREE_DEPS} of: {scope} · {total} nodes")
        else:
            self._tree_label.setText(
                f"Full {TREE_REVERSE if reverse else TREE_DEPS} forest over "
                f"{len(self._packages)} packages · {total} nodes")

    def _count_items(self, item: QTreeWidgetItem) -> int:
        total = item.childCount()
        for i in range(item.childCount()):
            total += self._count_items(item.child(i))
        return total

    def _make_tree_item(self, node: core.TreeNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name, node.version or "-", node.spec or "", node.note])
        item.setData(0, Qt.ItemDataRole.UserRole, core.normalize_name(node.name))
        if node.cyclic or node.shared:
            item.setForeground(3, QColor("#d7ba7d"))
        elif node.missing or not node.installed:
            item.setForeground(3, QColor("#e06c75"))
            item.setForeground(0, QColor("#e06c75"))
        if node.extras:
            item.setToolTip(0, f"extras: {node.extras}")
        for child in node.children:
            item.addChild(self._make_tree_item(child))
        return item

    def _copy_tree(self):
        lines = []
        def walk(item: QTreeWidgetItem, depth: int):
            text = "  " * depth + item.text(0)
            if item.text(1) and item.text(1) != "-":
                text += f" {item.text(1)}"
            if item.text(2):
                text += f"  {item.text(2)}"
            if item.text(3):
                text += f"  [{item.text(3)}]"
            lines.append(text)
            for i in range(item.childCount()):
                walk(item.child(i), depth + 1)
        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i), 0)
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))
        self._status.setText("Dependency tree copied to clipboard")

    def _jump_to_item_package(self, item: QTreeWidgetItem, *_):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key:
            key = core.normalize_name(item.text(0))
        self._select_key_in_table(key)

    def _select_key_in_table(self, key: str):
        key = core.normalize_name(key)
        self._search.clear()
        self._filter.setCurrentText(FILTER_ALL)
        self._fill_table()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                self._table.clearSelection()
                self._table.selectRow(row)
                self._table.scrollToItem(item)
                return

    def _tree_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole) or ""
        menu = QMenu(self)
        act_select = menu.addAction("Select in list")
        act_deps = menu.addAction("Show dependencies")
        act_rev = menu.addAction("Show dependents")
        act_pypi = menu.addAction("Open on PyPI")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen is act_select:
            self._select_key_in_table(key)
        elif chosen is act_deps:
            self._tree_mode.setCurrentText(TREE_DEPS)
            self._tree_scope.setChecked(True)
            self._select_key_in_table(key)
            self._fill_tree()
        elif chosen is act_rev:
            self._tree_mode.setCurrentText(TREE_REVERSE)
            self._tree_scope.setChecked(True)
            self._select_key_in_table(key)
            self._fill_tree()
        elif chosen is act_pypi:
            self._show_on_pypi(item.text(0))

    def _table_context_menu(self, pos):
        keys = self._selected_keys()
        menu = QMenu(self)
        act_install = menu.addAction("Install package...")
        act_update = menu.addAction("Update selected")
        act_uninstall = menu.addAction("Uninstall selected")
        menu.addSeparator()
        act_spec = menu.addAction("Install specific version...")
        act_download = menu.addAction("Download wheel...")
        menu.addSeparator()
        act_deps = menu.addAction("Show dependency tree")
        act_rev = menu.addAction("Show dependents")
        act_pypi = menu.addAction("Open on PyPI")
        act_copy = menu.addAction("Copy name==version")
        act_loc = menu.addAction("Open location")
        act_update.setEnabled(bool(keys))
        act_uninstall.setEnabled(bool(keys))
        act_spec.setEnabled(len(keys) == 1)
        act_download.setEnabled(bool(keys))
        act_deps.setEnabled(bool(keys))
        act_rev.setEnabled(bool(keys))
        act_pypi.setEnabled(len(keys) == 1)
        act_copy.setEnabled(bool(keys))
        act_loc.setEnabled(len(keys) == 1)
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_install:
            self._open_install()
        elif chosen is act_update:
            self._update_selected()
        elif chosen is act_uninstall:
            self._uninstall_selected()
        elif chosen is act_spec:
            self._open_install(package_name=self._by_key[keys[0]].name)
        elif chosen is act_download:
            self._open_download()
        elif chosen is act_deps:
            self._tree_mode.setCurrentText(TREE_DEPS)
            self._tree_scope.setChecked(True)
            self._fill_tree()
            self._tabs.setCurrentIndex(1)
        elif chosen is act_rev:
            self._tree_mode.setCurrentText(TREE_REVERSE)
            self._tree_scope.setChecked(True)
            self._fill_tree()
            self._tabs.setCurrentIndex(1)
        elif chosen is act_pypi:
            self._show_on_pypi(self._by_key[keys[0]].name)
        elif chosen is act_copy:
            text = "\n".join(f"{p.name}=={p.version}" for p in self._selected_packages())
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self._status.setText("Copied to clipboard")
        elif chosen is act_loc:
            path = self._by_key[keys[0]].location
            if path and os.path.isdir(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _show_on_pypi(self, name: str):
        QDesktopServices.openUrl(QUrl(core.PYPI_PROJECT_URL.format(name=core.normalize_name(name))))

    def _open_install(self, package_name: str = ""):
        if not isinstance(package_name, str):
            package_name = ""
        dlg = _InstallDialog(self, self._client, package_name, self._index)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        spec = dlg.spec()
        if not spec:
            return
        self._cancel.clear()
        self._pip_task(core.install_args(spec, upgrade=dlg.upgrade_enabled(),
                                         no_deps=dlg.no_deps_enabled(),
                                         pre=dlg.pre_enabled(),
                                         extra=dlg.extra_args()),
                       "Install")

    def _open_download(self):
        selected = self._selected_packages()
        default_spec = selected[0].name if selected else ""
        dlg = _DownloadDialog(self, default_spec)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        spec = dlg.spec()
        if not spec:
            return
        dest = dlg.destination()
        os.makedirs(dest, exist_ok=True)
        self._cancel.clear()
        self._pip_task(core.download_args(spec, dest, with_deps=dlg.with_deps(), pre=dlg.pre_enabled()),
                       "Download")

    def _update_selected(self):
        packages = self._selected_packages()
        if not packages:
            QMessageBox.information(self, "Update", "Select one or more packages first.")
            return
        self._cancel.clear()
        names = [p.name for p in packages]
        self._pip_task(core.install_args(names, upgrade=True), "Update")

    def _update_all(self):
        self._status.setText("Checking for updates...")

        def work(bridge):
            outdated, raw = core.check_outdated()
            return outdated, raw

        def on_done(result):
            self._set_busy(False)
            outdated, raw = result
            if not outdated:
                self._append_log("Everything is up to date")
                self._status.setText("Everything is up to date")
                self.refresh()
                return
            names = sorted(outdated.keys())
            self._append_log(f"Updating {len(names)} packages: {', '.join(names)}")
            self._cancel.clear()
            self._pip_task(core.install_args(names, upgrade=True), "Update all")

        self._run_async(work, on_done=on_done)

    def _uninstall_selected(self):
        packages = self._selected_packages()
        if not packages:
            QMessageBox.information(self, "Uninstall", "Select one or more packages first.")
            return
        names = ", ".join(p.name for p in packages)
        answer = QMessageBox.question(
            self, "Uninstall packages",
            f"Uninstall {len(packages)} package(s)?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._cancel.clear()
        self._pip_task(core.uninstall_args([p.name for p in packages]), "Uninstall")

    def _check_updates_online(self):
        self._status.setText("Querying PyPI...")
        names = [p.name for p in self._packages]
        if not names:
            return

        def work(bridge):
            def on_result(name, latest):
                bridge.line.emit(f"{name} -> {latest}")
            return core.fetch_latest_versions(names, client=self._client, on_result=on_result)

        def on_line(line):
            self._append_log(line)

        def on_done(result):
            self._set_busy(False)
            self._latest.update(result)
            self._apply_latest()
            self._fill_table()
            self._update_details()
            updates = sum(1 for p in self._packages if p.status == "update")
            self._status.setText(f"PyPI check done: {len(result)} resolved, {updates} updates available")
            self._append_log(f"PyPI check done: {updates} updates available")

        self._run_async(work, on_done=on_done, on_line=on_line)

    def _export_requirements(self):
        packages = self._visible_packages() or self._packages
        path, _ = QFileDialog.getSaveFileName(self, "Export requirements.txt", "requirements.txt",
                                              "Requirements (*.txt);;All files (*.*)")
        if not path:
            return
        try:
            core.write_requirements(path, packages, pinned=True)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self._append_log(f"Exported {len(packages)} packages to {path}")
        self._status.setText(f"Exported {len(packages)} packages")

    def _install_requirements(self):
        path, _ = QFileDialog.getOpenFileName(self, "Install from requirements.txt", "",
                                              "Requirements (*.txt);;All files (*.*)")
        if not path:
            return
        self._cancel.clear()
        self._pip_task(["install", "-r", path], "Install requirements")

    def _freeze_to_log(self):
        def work(bridge):
            code, out = core.run_pip_capture(["freeze"])
            return code, out

        def on_done(result):
            self._set_busy(False)
            code, out = result
            self._append_log(out.strip() or "(empty)")
            self._status.setText("pip freeze output written to log")

        self._run_async(work, on_done=on_done)

    def _update_status(self):
        updates = sum(1 for p in self._packages if p.status == "update")
        total_size = sum(p.size for p in self._packages)
        self._status.setText(
            f"Python {core.python_version_label()} · {core.python_executable()} · "
            f"{len(self._packages)} packages · {core.format_size(total_size)} · {updates} updates")

    def closeEvent(self, event):
        self._cancel.set()
        super().closeEvent(event)


class _InstallDialog(QDialog):
    def __init__(self, parent=None, client: core.PyPiClient | None = None,
                 package_name: str = "", index: core.SimpleIndex | None = None):
        super().__init__(parent)
        self.setWindowTitle("Install Python Package")
        self.setMinimumWidth(480)
        self._client = client or core.PyPiClient()
        self._index = index or core.SimpleIndex()
        self._setup_ui(package_name)

    def _setup_ui(self, package_name: str):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(package_name)
        self._name.setPlaceholderText("package name, e.g. requests or requests==2.32.0")
        form.addRow("Package:", self._name)
        self._version = QComboBox()
        self._version.setEditable(True)
        self._version.addItem("latest")
        form.addRow("Version:", self._version)
        self._fetch_btn = QPushButton("Load versions from PyPI")
        self._fetch_btn.clicked.connect(self._fetch_versions)
        form.addRow("", self._fetch_btn)
        layout.addLayout(form)

        search_row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Search PyPI packages...")
        self._query.returnPressed.connect(self._search_pypi)
        search_row.addWidget(self._query, 1)
        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._search_pypi)
        search_row.addWidget(self._search_btn)
        layout.addLayout(search_row)
        self._results = QListWidget()
        self._results.setMaximumHeight(130)
        self._results.itemDoubleClicked.connect(self._pick_result)
        layout.addWidget(self._results)
        self._index_status = QLabel("")
        self._index_status.setWordWrap(True)
        self._index_status.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(self._index_status)

        opts = QHBoxLayout()
        self._upgrade = QCheckBox("Upgrade if installed")
        self._upgrade.setChecked(True)
        opts.addWidget(self._upgrade)
        self._no_deps = QCheckBox("No dependencies")
        opts.addWidget(self._no_deps)
        self._pre = QCheckBox("Include pre-releases")
        opts.addWidget(self._pre)
        opts.addStretch(1)
        layout.addLayout(opts)

        extra_row = QHBoxLayout()
        extra_row.addWidget(QLabel("Extra pip args:"))
        self._extra = QLineEdit()
        self._extra.setPlaceholderText("--index-url ... --no-cache-dir")
        extra_row.addWidget(self._extra)
        layout.addLayout(extra_row)

        self._preview = QLabel("")
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(self._preview)
        self._name.textChanged.connect(self._update_preview)
        self._version.currentTextChanged.connect(self._update_preview)
        self._update_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Install")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_preview(self):
        self._preview.setText(f"pip install {self.spec()}")

    def _fetch_versions(self):
        name = self._name.text().strip()
        if not name:
            return
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("Loading...")

        def work(bridge):
            return self._client.versions(name, include_pre=self._pre.isChecked())

        def on_done(versions):
            self._fetch_btn.setEnabled(True)
            self._fetch_btn.setText("Load versions from PyPI")
            current = self._version.currentText()
            self._version.blockSignals(True)
            self._version.clear()
            self._version.addItem("latest")
            self._version.addItems(versions[:200])
            if current:
                self._version.setCurrentText(current)
            self._version.blockSignals(False)
            self._update_preview()

        def on_failed(message):
            self._fetch_btn.setEnabled(True)
            self._fetch_btn.setText("Load versions from PyPI")
            self._preview.setText(f"Version lookup failed: {message}")

        bridge = _TaskBridge(self)
        bridge.done.connect(on_done)
        bridge.failed.connect(on_failed)
        threading.Thread(target=lambda: self._safe_work(bridge, work), daemon=True).start()

    @staticmethod
    def _safe_work(bridge, work):
        try:
            bridge.done.emit(work(bridge))
        except Exception as e:
            bridge.failed.emit(str(e))

    def _search_pypi(self):
        query = self._query.text().strip()
        if not query:
            return
        self._search_btn.setEnabled(False)
        self._search_btn.setText("Searching...")
        if not self._index.is_fresh():
            self._index_status.setText("Downloading the PyPI package index (one time, about 45 MB)...")

        def work(bridge):
            return self._index.search(query, limit=80)

        def on_done(names):
            self._search_btn.setEnabled(True)
            self._search_btn.setText("Search")
            self._results.clear()
            for name in names:
                item = QListWidgetItem(name)
                self._results.addItem(item)
            self._index_status.setText(f"{len(names)} match(es) for '{query}' · double-click to use")
            if names:
                self._results.setCurrentRow(0)

        def on_failed(message):
            self._search_btn.setEnabled(True)
            self._search_btn.setText("Search")
            self._index_status.setText(f"Search failed: {message}")

        bridge = _TaskBridge(self)
        bridge.done.connect(on_done)
        bridge.failed.connect(on_failed)
        threading.Thread(target=lambda: self._safe_work(bridge, work), daemon=True).start()

    def _pick_result(self, item: QListWidgetItem):
        name = item.text().strip()
        if not name:
            return
        self._name.setText(name)
        self._version.setCurrentText("latest")
        self._fetch_versions()

    def spec(self) -> str:
        raw = self._name.text().strip()
        if not raw:
            return ""
        version = self._version.currentText().strip()
        if any(op in raw for op in ("==", ">=", "<=", "~=", "!=", ">", "<")):
            return raw
        if version and version != "latest":
            return f"{raw}=={version}"
        return raw

    def upgrade_enabled(self) -> bool:
        return self._upgrade.isChecked()

    def no_deps_enabled(self) -> bool:
        return self._no_deps.isChecked()

    def pre_enabled(self) -> bool:
        return self._pre.isChecked()

    def extra_args(self) -> list[str]:
        text = self._extra.text().strip()
        return text.split() if text else []


class _DownloadDialog(QDialog):
    def __init__(self, parent=None, package_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Download Package")
        self.setMinimumWidth(480)
        self._setup_ui(package_name)

    def _setup_ui(self, package_name: str):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._spec = QLineEdit(package_name)
        self._spec.setPlaceholderText("package or requirement spec, e.g. numpy==2.1.0")
        form.addRow("Package:", self._spec)
        self._dest = QLineEdit(os.path.join(os.getcwd(), "dist", "wheels"))
        form.addRow("Folder:", self._dest)
        layout.addLayout(form)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        layout.addWidget(browse, 0, Qt.AlignmentFlag.AlignRight)
        opts = QHBoxLayout()
        self._deps = QCheckBox("Download dependencies")
        self._deps.setChecked(True)
        opts.addWidget(self._deps)
        self._pre = QCheckBox("Include pre-releases")
        opts.addWidget(self._pre)
        opts.addStretch(1)
        layout.addLayout(opts)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Download")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self._dest.text().strip() or ".")
        if d:
            self._dest.setText(d)

    def spec(self) -> str:
        return self._spec.text().strip()

    def destination(self) -> str:
        return self._dest.text().strip() or os.path.join(os.getcwd(), "dist", "wheels")

    def with_deps(self) -> bool:
        return self._deps.isChecked()

    def pre_enabled(self) -> bool:
        return self._pre.isChecked()
