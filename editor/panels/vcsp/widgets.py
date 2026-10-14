# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
from PyQt6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QHeaderView, QListWidget, QListWidgetItem, QMenu, QPushButton, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from core.config.editor_scale import scale

class _FileItemDelegate(QStyledItemDelegate):
    _status_colors = {
        "staged": ("#6a9955", "\u2713 "),
        "unstaged": ("#dcdcaa", "~ "),
        "untracked": ("#f44747", "? "),
        "conflict": ("#ce9178", "! "),
        "modified": ("#569cd6", "M "),
    }

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.column() != 0:
            return
        status = index.data(Qt.ItemDataRole.UserRole + 1)
        if status not in self._status_colors:
            return
        color_str, prefix = self._status_colors[status]
        painter.save()
        painter.setPen(QColor(color_str))
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        text_rect = option.rect.adjusted(4, 0, 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, prefix)
        painter.restore()


class _StatusTree(QTreeWidget):
    file_selected = pyqtSignal(str, bool)
    file_action_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Path", "Status"])
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.setAlternatingRowColors(True)
        self.setRootIsDecorated(True)
        self.setAnimated(True)
        self.setItemDelegate(_FileItemDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemClicked.connect(self._on_item_clicked)
        self._entries: list[dict] = []

    def set_entries(self, entries: list[dict]):
        self._entries = entries
        self.clear()
        sections: dict[str, list[dict]] = {
            "staged": [],
            "unstaged": [],
            "untracked": [],
            "conflict": [],
        }
        for e in entries:
            s = e["status"]
            if s not in sections:
                s = "unstaged"
            sections[s].append(e)

        section_labels = {
            "staged": "Staged",
            "conflict": "Conflicts",
            "unstaged": "Unstaged",
            "untracked": "Untracked",
        }
        for key in ["staged", "conflict", "unstaged", "untracked"]:
            items = sections[key]
            if not items:
                continue
            section_item = QTreeWidgetItem([f"{section_labels[key]} ({len(items)})", ""])
            section_item.setFlags(section_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            bold_font = self.font()
            bold_font.setBold(True)
            section_item.setFont(0, bold_font)
            self.addTopLevelItem(section_item)
            for e in items:
                child = QTreeWidgetItem([e["path"], e["status"]])
                child.setData(0, Qt.ItemDataRole.UserRole + 1, e["status"])
                child.setData(0, Qt.ItemDataRole.UserRole, e["path"])
                section_item.addChild(child)

        self.expandAll()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            staged = False
            parent = item.parent()
            if parent:
                parent_text = parent.text(0)
                if parent_text.startswith("Staged"):
                    staged = True
                elif parent_text.startswith("Conflict"):
                    staged = False
            self.file_selected.emit(path, staged)

    def _on_context_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        parent = item.parent()
        section = parent.text(0) if parent else ""
        menu = QMenu(self)
        if section.startswith("Staged"):
            a1 = menu.addAction("Unstage")
            a1.triggered.connect(lambda: self.file_action_requested.emit(path, "unstage"))
        elif section.startswith("Unstaged"):
            a2 = menu.addAction("Stage")
            a2.triggered.connect(lambda: self.file_action_requested.emit(path, "stage"))
            a3 = menu.addAction("Discard Changes")
            a3.triggered.connect(lambda: self.file_action_requested.emit(path, "discard"))
        elif section.startswith("Conflict"):
            a4 = menu.addAction("Stage (Mark Resolved)")
            a4.triggered.connect(lambda: self.file_action_requested.emit(path, "stage"))
            a5 = menu.addAction("Open File")
            a5.triggered.connect(lambda: self.file_action_requested.emit(path, "open"))
        elif section.startswith("Untracked"):
            a6 = menu.addAction("Stage (Add)")
            a6.triggered.connect(lambda: self.file_action_requested.emit(path, "stage"))
            a7 = menu.addAction("Add to .gitignore")
            a7.triggered.connect(lambda: self.file_action_requested.emit(path, "gitignore"))
        menu.addSeparator()
        a8 = menu.addAction("Copy Path")
        a8.triggered.connect(lambda: QApplication.clipboard().setText(path))
        menu.exec(self.viewport().mapToGlobal(pos))


class _LogTree(QTreeWidget):
    commit_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Graph", "Commit", "Author", "Date", "Message"])
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.header().resizeSection(0, scale(120))
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.header().resizeSection(1, scale(70))
        self.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.header().resizeSection(3, scale(100))
        self.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.setAlternatingRowColors(True)
        self.setRootIsDecorated(False)
        self.setFont(QFont("Courier New", 9))
        self.itemClicked.connect(self._on_click)
        self._commits: list[dict] = []

    def set_log(self, graph_text: str, commits: list[dict]):
        self._commits = commits
        self.clear()
        g_lines = graph_text.strip().split("\n") if graph_text else []
        for i, c in enumerate(commits):
            graph_part = g_lines[i] if i < len(g_lines) else ""
            date_str = time.strftime("%Y-%m-%d %H:%M",
                                     time.gmtime(c["time"])) if c["time"] else ""
            items = [
                graph_part,
                c["short"],
                c["author"],
                date_str,
                c["message"],
            ]
            item = QTreeWidgetItem(items)
            item.setData(1, Qt.ItemDataRole.UserRole, c["hash"])
            item.setToolTip(0, graph_part)
            item.setToolTip(1, c["hash"])
            item.setToolTip(4, c["message"])
            self.addTopLevelItem(item)

    def _on_click(self, item: QTreeWidgetItem, column: int):
        h = item.data(1, Qt.ItemDataRole.UserRole)
        if h:
            self.commit_selected.emit(h)


class _BranchList(QListWidget):
    branch_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def set_branches(self, branches_text: str, current: str):
        self.clear()
        for line in branches_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            is_current = line.startswith("*")
            name = line[2:] if line.startswith("* ") else line
            name = name.strip()
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if is_current:
                bold = self.font()
                bold.setBold(True)
                item.setFont(bold)
            self.addItem(item)

    def _on_double_click(self, item: QListWidgetItem):
        name = item.data(Qt.ItemDataRole.UserRole)
        if name:
            self.branch_selected.emit(name)

    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        menu = QMenu(self)
        a1 = menu.addAction("Switch")
        a1.triggered.connect(lambda: self.branch_selected.emit(name))
        a2 = menu.addAction("Delete")
        a2.triggered.connect(lambda: self._request_delete(name))
        a3 = menu.addAction("Merge into current")
        a3.triggered.connect(lambda: self._request_merge(name))
        menu.exec(self.viewport().mapToGlobal(pos))

    def _request_delete(self, name: str):
        self.parent().parent().parent()._delete_branch(name)

    def _request_merge(self, name: str):
        self.parent().parent().parent()._merge_branch(name)


class _StashList(QListWidget):
    stash_action = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def set_stashes(self, stashes: list[dict]):
        self.clear()
        for s in stashes:
            msg = s["message"]
            date_str = time.strftime("%Y-%m-%d %H:%M",
                                     time.gmtime(s["time"])) if s["time"] else ""
            item = QListWidgetItem(f"{s['ref']}: {msg} ({date_str})")
            item.setData(Qt.ItemDataRole.UserRole, s["ref"])
            self.addItem(item)

    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        ref = item.data(Qt.ItemDataRole.UserRole)
        if not ref:
            return
        menu = QMenu(self)
        a1 = menu.addAction("Pop")
        a1.triggered.connect(lambda: self.stash_action.emit(ref, "pop"))
        a2 = menu.addAction("Drop")
        a2.triggered.connect(lambda: self.stash_action.emit(ref, "drop"))
        menu.exec(self.viewport().mapToGlobal(pos))


class _RemoteWidget(QWidget):
    push_requested = pyqtSignal(str, str)
    pull_requested = pyqtSignal(str, str)
    fetch_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._list = QListWidget()
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._remote_combo = QComboBox()
        btn_row.addWidget(self._remote_combo)
        self._branch_combo = QComboBox()
        btn_row.addWidget(self._branch_combo)
        layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        self._push_btn = QPushButton("Push")
        self._push_btn.clicked.connect(self._on_push)
        btn_row2.addWidget(self._push_btn)
        self._pull_btn = QPushButton("Pull")
        self._pull_btn.clicked.connect(self._on_pull)
        btn_row2.addWidget(self._pull_btn)
        self._fetch_btn = QPushButton("Fetch")
        self._fetch_btn.clicked.connect(self._on_fetch)
        btn_row2.addWidget(self._fetch_btn)
        layout.addLayout(btn_row2)

    def set_remotes(self, remotes: list[dict], branches: list[str],
                    current_branch: str = ""):
        self._list.clear()
        for r in remotes:
            self._list.addItem(f"{r['name']}  {r['url']}")
        self._remote_combo.clear()
        self._remote_combo.addItems([r["name"] for r in remotes])
        self._branch_combo.clear()
        self._branch_combo.addItem("(current)")
        for b in branches:
            self._branch_combo.addItem(b)
        idx = self._branch_combo.findText(current_branch)
        if idx >= 0:
            self._branch_combo.setCurrentIndex(idx)

    def _on_push(self):
        remote = self._remote_combo.currentText()
        branch = self._branch_combo.currentText()
        if branch == "(current)":
            branch = ""
        self.push_requested.emit(remote, branch)

    def _on_pull(self):
        remote = self._remote_combo.currentText()
        branch = self._branch_combo.currentText()
        if branch == "(current)":
            branch = ""
        self.pull_requested.emit(remote, branch)

    def _on_fetch(self):
        remote = self._remote_combo.currentText()
        self.fetch_requested.emit(remote)
