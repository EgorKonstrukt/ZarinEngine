# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import threading
from PyQt6.QtCore import Qt, QItemSelectionModel, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDockWidget, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QProgressBar, QPlainTextEdit, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
from editor.panels import pkgcore as core
from editor.panels.pkgmgr.ops import FILTER_ALL, FILTER_UPDATES, FILTER_UPTODATE, TREE_DEPS, TREE_REVERSE, PackageManagerOpsMixin
try:
    import editor.icons as qta
except ImportError:
    qta = None
class PackageManagerPanel(PackageManagerOpsMixin, QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Python Packages", parent)
        self.setObjectName("PackageManagerDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable | QDockWidget.DockWidgetFeature.DockWidgetClosable)
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
        for b in (self._install_btn, self._update_btn, self._update_all_btn, self._uninstall_btn, self._download_btn, self._check_btn, self._refresh_btn):
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
        self._count_label.setStyleSheet("color: " + chr(35) + "9a9a9a;")
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
        self._status.setStyleSheet("color: " + chr(35) + "9a9a9a;")
        bottom.addWidget(self._status, 1)
        layout.addLayout(bottom)
        self.setWidget(root)
    def _tool_button(self, text: str, icon: str, slot) -> QPushButton:
        btn = QPushButton(text)
        if qta is not None:
            try:
                btn.setIcon(qta.icon(icon, color=chr(35) + "d4d4d4"))
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
        self._detail_summary.setStyleSheet("color: " + chr(35) + "c8c8e8;")
        layout.addWidget(self._detail_summary)
        form = QGroupBox("Metadata")
        form_layout = QFormLayout(form)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._detail_fields: dict[str, QLabel] = {}
        for key, label in (("latest", "Latest release"), ("author", "Author"), ("license", "License"), ("requires_python", "Requires Python"), ("home_page", "Home page"), ("location", "Location"), ("size", "Size")):
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
        self._detail_notes.setStyleSheet("color: " + chr(35) + "e0a040;")
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
        self._tree_label.setStyleSheet("color: " + chr(35) + "9a9a9a;")
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
                status_item.setForeground(QColor(chr(35) + "7ec699"))
                latest_item.setForeground(QColor(chr(35) + "7ec699"))
            elif p.status == "up to date":
                status_item.setForeground(QColor(chr(35) + "8a8a8a"))
            elif p.status == "editable":
                status_item.setForeground(QColor(chr(35) + "d7ba7d"))
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
                    sm.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)
        self._update_details()
        updates = sum(1 for p in self._packages if p.status == "update")
        self._count_label.setText(f"{len(packages)} shown / {len(self._packages)} installed \u00b7 {updates} updates")
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
                node.setForeground(1, QColor(chr(35) + "e06c75"))
            self._detail_requires.addTopLevelItem(node)
        if not p.requires:
            self._detail_requires.addTopLevelItem(QTreeWidgetItem(["(no declared requirements)", ""]))
        note = ""
        if p.status == "update":
            note = f"Update available: {p.version} \u2192 {p.latest}"
            self._detail_notes.setText(note)
        elif p.status == "editable":
            note = "Editable / development install"
            self._detail_notes.setText(note)
        else:
            self._detail_notes.setText(note)
        self._pending_detail = p.name
        self._detail_timer.start()
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
            nodes = core.build_dependency_tree(self._packages, reverse=reverse, roots=roots, include_extras=self._tree_extras.isChecked())
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
            self._tree_label.setText(f"{TREE_REVERSE if reverse else TREE_DEPS} of: {scope} \u00b7 {total} nodes")
        else:
            self._tree_label.setText(f"Full {TREE_REVERSE if reverse else TREE_DEPS} forest over {len(self._packages)} packages \u00b7 {total} nodes")
    def _count_items(self, item: QTreeWidgetItem) -> int:
        total = item.childCount()
        for i in range(item.childCount()):
            total += self._count_items(item.child(i))
        return total
    def _make_tree_item(self, node: core.TreeNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name, node.version or "-", node.spec or "", node.note])
        item.setData(0, Qt.ItemDataRole.UserRole, core.normalize_name(node.name))
        if node.cyclic or node.shared:
            item.setForeground(3, QColor(chr(35) + "d7ba7d"))
        elif node.missing or not node.installed:
            item.setForeground(3, QColor(chr(35) + "e06c75"))
            item.setForeground(0, QColor(chr(35) + "e06c75"))
        if node.extras:
            item.setToolTip(0, f"extras: {node.extras}")
        for child in node.children:
            item.addChild(self._make_tree_item(child))
        return item
