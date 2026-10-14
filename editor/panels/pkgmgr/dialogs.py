# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import threading
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout
from editor.panels import pkgcore as core
from editor.panels.pkgmgr.bridge import _TaskBridge
class _InstallDialog(QDialog):
    def __init__(self, parent=None, client: core.PyPiClient | None = None, package_name: str = "", index: core.SimpleIndex | None = None):
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
        self._index_status.setStyleSheet("color: " + chr(35) + "9a9a9a;")
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
        self._preview.setStyleSheet("color: " + chr(35) + "9a9a9a;")
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
            self._index_status.setText(f"{len(names)} match(es) for '{query}' \u00b7 double-click to use")
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
