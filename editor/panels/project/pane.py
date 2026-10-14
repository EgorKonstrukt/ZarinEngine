# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFrame, QLabel, QLineEdit, QHeaderView, QAbstractItemView, QFileIconProvider, QListWidgetItem, QTreeWidgetItem
from PyQt6.QtCore import Qt, QSize, QFileInfo
from PyQt6.QtGui import QIcon, QColor, QBrush
from core.config.editor_scale import scale
from editor.constants import VIEW_ICON, VIEW_LIST, VIEW_DETAILS
from editor.picker import _get_thumbnail, _format_size, _thumb_resolution
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .panel import ProjectPanel
from .icons import _accent_hex, _accent_rgba
from .widgets import FileListWidget, FileDetailWidget, _AddressBreadcrumb, _FileListDelegate, _NavButton


class _FilePane(QWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._current_dir = panel._project_root
        self._active = False
        self._view_mode_cache = panel._view_mode
        self._hist_back: list[str] = []
        self._hist_fwd: list[str] = []
        self._navigating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._breadcrumb_bar = _AddressBreadcrumb(self)
        layout.addWidget(self._breadcrumb_bar)
        self._stack = QStackedWidget()
        self._file_list = FileListWidget(panel)
        self._file_list.setDragEnabled(True)
        self._file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_list.setIconSize(QSize(scale(20), scale(20)))
        self._file_list.setSpacing(1)
        from PyQt6.QtWidgets import QStyledItemDelegate
        self._file_list.setItemDelegate(_FileListDelegate(panel))
        self._file_list.itemClicked.connect(panel._on_file_single_click)
        self._file_list.itemDoubleClicked.connect(panel._on_file_double_click)
        self._file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_list.customContextMenuRequested.connect(panel._show_file_context_menu)
        self._file_list.itemChanged.connect(panel._on_list_item_changed)
        self._stack.addWidget(self._file_list)
        self._detail_tree = FileDetailWidget(panel)
        self._detail_tree.setHeaderHidden(False)
        self._detail_tree.setColumnCount(4)
        self._detail_tree.setHeaderLabels(["Name", "Type", "Date Modified", "Size"])
        self._detail_tree.setRootIsDecorated(False)
        self._detail_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._detail_tree.setDragEnabled(True)
        self._detail_tree.setAlternatingRowColors(True)
        self._detail_tree.setUniformRowHeights(True)
        self._detail_tree.setAllColumnsShowFocus(True)
        self._detail_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._detail_tree.customContextMenuRequested.connect(panel._show_file_context_menu)
        self._detail_tree.itemClicked.connect(panel._on_file_single_click)
        self._detail_tree.itemDoubleClicked.connect(panel._on_file_double_click)
        self._detail_tree.itemChanged.connect(panel._on_tree_item_changed)
        self._detail_tree.setSortingEnabled(False)
        self._detail_tree.setIndentation(0)
        header = self._detail_tree.header()
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)
        header.setHighlightSections(False)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, scale(110))
        header.resizeSection(2, scale(130))
        header.resizeSection(3, scale(90))
        try:
            header.setSortIndicator(panel._sort_col, panel._sort_order)
        except Exception:
            pass
        try:
            header.sectionClicked.connect(lambda idx, p=self._detail_tree: panel._on_sort_changed(self, idx))
        except Exception:
            pass
        self._detail_tree.setIconSize(QSize(scale(16), scale(16)))
        self._stack.addWidget(self._detail_tree)
        layout.addWidget(self._stack, 1)
    def set_active(self, active: bool):
        self._active = active
        try:
            accent = _accent_hex()
            soft = _accent_rgba(22)
        except Exception:
            accent = "#0078d7"
            soft = "rgba(0,120,215,22)"
        if self._panel._dual_pane:
            if active:
                self._stack.setStyleSheet(f"border: 1px solid {accent};")
                self._breadcrumb_bar.setStyleSheet(
                    f"QLineEdit {{ background: {soft};"
                    " border: 1px solid transparent; border-radius: 2px;"
                    " padding: 2px 6px; font-size: 12px; min-height: 20px; }"
                )
            else:
                self._stack.setStyleSheet("border: 1px solid #3a3a3a;")
                self._breadcrumb_bar.setStyleSheet(
                    "QLineEdit { background: transparent;"
                    " border: 1px solid transparent; border-radius: 2px;"
                    " padding: 2px 6px; font-size: 12px; min-height: 20px;"
                    " color: #8a8a8a; }"
                )
        else:
            self._stack.setStyleSheet(f"border: 1px solid {accent};")
            self._breadcrumb_bar.setStyleSheet(
                f"QLineEdit {{ background: {soft};"
                " border: 1px solid transparent; border-radius: 2px;"
                " padding: 2px 6px; font-size: 12px; min-height: 20px; }"
            )
        try:
            self._panel._update_pane_selection_style(self)
        except Exception:
            pass
    def mousePressEvent(self, event):
        self._panel._set_active_pane(self)
        super().mousePressEvent(event)
    def rebuild_breadcrumb(self):
        if self._breadcrumb_bar._editing:
            return
        if self._active:
            nav_bar = self._panel._nav_bar
            if nav_bar:
                nav_bar._back_btn.setEnabled(len(self._hist_back) > 0)
                nav_bar._forward_btn.setEnabled(len(self._hist_fwd) > 0)
        try:
            base = os.path.basename(self._panel._project_root)
            display = self._current_dir.replace(self._panel._project_root, base)
        except Exception:
            display = self._current_dir
        display = display.replace("\\", " \u25B8 ").replace("/", " \u25B8 ")
        self._breadcrumb_bar.setText(display)
    def _on_search(self, text: str):
        if text:
            self._search_all(text)
        else:
            self.populate_files(self._current_dir)
    def _search_all(self, text: str):
        self._file_list.clear()
        if self._panel._view_mode == VIEW_DETAILS:
            self._detail_tree.clear()
        for root, dirs, files in os.walk(self._panel._project_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files, key=lambda s: s.lower()):
                if text.lower() in f.lower() and not f.startswith("."):
                    full = os.path.join(root, f)
                    if self._panel._view_mode == VIEW_DETAILS:
                        item = QTreeWidgetItem()
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                        try:
                            fi = QFileInfo(full)
                            icon = self._panel._icon_provider.icon(fi)
                            if icon and not icon.isNull():
                                item.setIcon(0, icon)
                        except Exception:
                            pass
                        item.setText(0, f)
                        item.setText(1, self._type_label(f, False))
                        try:
                            mt = os.path.getmtime(full)
                            dt = datetime.datetime.fromtimestamp(mt)
                            item.setText(2, dt.strftime("%Y-%m-%d %H:%M"))
                        except Exception:
                            item.setText(2, "")
                        try:
                            item.setText(3, _format_size(os.path.getsize(full)))
                        except OSError:
                            item.setText(3, "")
                        try:
                            item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        except Exception:
                            pass
                        item.setData(0, Qt.ItemDataRole.UserRole, full)
                        self._detail_tree.addTopLevelItem(item)
                    else:
                        item = QListWidgetItem()
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                        std_icon = self._panel._get_file_icon(full)
                        if std_icon:
                            item.setIcon(std_icon)
                        else:
                            pm = _get_thumbnail(full, _thumb_resolution())
                            item.setIcon(QIcon(pm))
                        item.setText(f)
                        item.setData(Qt.ItemDataRole.UserRole, full)
                        self._file_list.addItem(item)
    def _type_label(self, entry: str, is_dir: bool) -> str:
        if is_dir:
            return "[DIR]"
        ext = os.path.splitext(entry)[1].lower()
        if ext.startswith("."):
            ext = ext[1:]
        if ext:
            return ext
        return "File"
    def _size_brush(self, size: int) -> QBrush:
        try:
            if size < 0:
                return QBrush()
            if size < 1024 * 100:
                return QBrush(QColor("#7fb3d5"))
            if size < 1024 * 1024 * 10:
                return QBrush(QColor("#82c46a"))
            if size < 1024 * 1024 * 100:
                return QBrush(QColor("#d9c84a"))
            if size < 1024 * 1024 * 500:
                return QBrush(QColor("#e09a3c"))
            return QBrush(QColor("#d95f4b"))
        except Exception:
            return QBrush()
    def populate_files(self, dirpath: str, filter_text: str = ""):
        self._current_dir = os.path.normpath(dirpath)
        self.rebuild_breadcrumb()
        try:
            entries = sorted(os.listdir(dirpath), key=lambda s: s.lower())
        except (PermissionError, FileNotFoundError) as e:
            if isinstance(e, FileNotFoundError):
                os.makedirs(dirpath, exist_ok=True)
                entries = []
            else:
                return
        visible = [e for e in entries if not e.startswith(".") and not e.endswith(".import")]
        if filter_text:
            visible = [e for e in visible if filter_text.lower() in e.lower()]
        try:
            self._panel._dir_size_gen += 1
        except Exception:
            pass
        if self._panel._view_mode == VIEW_DETAILS:
            self._populate_detail_tree(dirpath, visible, filter_text)
        else:
            self._populate_list_view(dirpath, visible, filter_text)
        if self._active:
            if self._panel._status_bar:
                try:
                    extra = 1
                    try:
                        if os.path.normpath(dirpath) != os.path.normpath(self._panel._project_root):
                            extra = 0
                    except Exception:
                        pass
                    self._panel._status_bar.update_counts(len(visible) + (0 if extra else 0))
                except Exception:
                    self._panel._status_bar.update_counts(len(visible))
            if self._panel._nav_bar:
                self._panel._nav_bar.update_address(self._current_dir)
            if self._panel._status_bar:
                self._panel._status_bar.update_path(self._current_dir)
            self._panel._update_nav_buttons()
            try:
                self._panel._refresh_status_sizes()
            except Exception:
                pass
        self._panel._apply_vcs_colors()
    def _add_up_row_detail(self, widget, dirpath: str) -> None:
        try:
            if os.path.normpath(dirpath) == os.path.normpath(self._panel._project_root):
                return
            parent = os.path.normpath(os.path.dirname(os.path.normpath(dirpath)))
        except Exception:
            return
        try:
            item = QTreeWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            try:
                item.setIcon(0, self._panel._icon_provider.icon(QFileIconProvider.IconType.Folder))
            except Exception:
                pass
            item.setText(0, "..")
            item.setText(1, "Parent Folder")
            item.setText(2, "")
            item.setText(3, "")
            item.setData(0, Qt.ItemDataRole.UserRole, parent)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, "up")
            item.setToolTip(0, parent)
            widget.addTopLevelItem(item)
        except Exception:
            pass
    def _add_up_row_list(self, widget, dirpath: str) -> None:
        try:
            if os.path.normpath(dirpath) == os.path.normpath(self._panel._project_root):
                return
            parent = os.path.normpath(os.path.dirname(os.path.normpath(dirpath)))
        except Exception:
            return
        try:
            item = QListWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            try:
                item.setIcon(self._panel._icon_provider.icon(QFileIconProvider.IconType.Folder))
            except Exception:
                item.setIcon(QIcon())
            item.setText("..")
            item.setData(Qt.ItemDataRole.UserRole, parent)
            item.setData(Qt.ItemDataRole.UserRole + 1, "up")
            item.setToolTip(f"Up: {parent}")
            widget.addItem(item)
        except Exception:
            pass
    def _populate_list_view(self, dirpath: str, entries: list[str], filter_text: str):
        widget = self._file_list
        widget.blockSignals(True)
        widget.clear()
        is_icon = self._panel._view_mode == VIEW_ICON
        self._add_up_row_list(widget, dirpath)
        try:
            ordered = self._panel._sorted_entries(dirpath, entries)
        except Exception:
            ordered = []
            for entry in entries:
                full = os.path.join(dirpath, entry)
                try:
                    is_dir = os.path.isdir(full)
                except Exception:
                    is_dir = False
                ordered.append((entry, full, is_dir, 0, 0, ""))
        folders = [(e, f) for e, f, d, s, m, x in ordered if d]
        files = [(e, f) for e, f, d, s, m, x in ordered if not d]
        for entry, full in folders:
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            try:
                item.setIcon(self._panel._icon_provider.icon(QFileIconProvider.IconType.Folder))
            except Exception:
                item.setIcon(QIcon())
            item.setText(entry)
            item.setData(Qt.ItemDataRole.UserRole, full)
            item.setToolTip(f"Folder: {full}")
            widget.addItem(item)
        for entry, full in files:
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            if is_icon:
                std_icon = self._panel._get_file_icon(full)
                if std_icon:
                    item.setIcon(std_icon)
                else:
                    pm = _get_thumbnail(full, _thumb_resolution())
                    item.setIcon(QIcon(pm))
            else:
                try:
                    fi = QFileInfo(full)
                    item.setIcon(self._panel._icon_provider.icon(fi))
                except Exception:
                    item.setIcon(QIcon())
            item.setText(entry)
            item.setData(Qt.ItemDataRole.UserRole, full)
            try:
                sz = os.path.getsize(full)
            except OSError:
                sz = 0
            item.setToolTip(f"{entry}\n{_format_size(sz)}")
            widget.addItem(item)
        widget.blockSignals(False)
    def _group_files_by_date(self, files: list[tuple]) -> list[tuple[str, list]]:
        now = datetime.datetime.now()
        today = now.date()
        yesterday = today - datetime.timedelta(days=1)
        groups = {}
        for entry, full in files:
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full)).date()
            except OSError:
                mtime = today
            if mtime == today:
                group = "Today"
            elif mtime == yesterday:
                group = "Yesterday"
            elif (today - mtime).days <= 7:
                group = "Last week"
            elif mtime.month == now.month and mtime.year == now.year:
                group = "Earlier this month"
            elif mtime.year == now.year:
                group = mtime.strftime("%B %Y")
            else:
                group = str(mtime.year)
            if group not in groups:
                groups[group] = []
            groups[group].append((entry, full))
        order = ["Today", "Yesterday", "Last week", "Earlier this month"]
        result = []
        for g in order:
            if g in groups:
                result.append((g, groups.pop(g)))
        for g in sorted(groups.keys()):
            result.append((g, groups[g]))
        return result
    def _populate_detail_tree(self, dirpath: str, entries: list[str], filter_text: str):
        from .widgets import _populate_detail_tree_impl
        return _populate_detail_tree_impl(self, dirpath, entries, filter_text)
    def active_widget(self):
        return self._detail_tree if self._panel._view_mode == VIEW_DETAILS else self._file_list
    def refresh(self):
        self.populate_files(self._current_dir)
class _NavBar(QWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setFixedHeight(scale(34))
        self.setStyleSheet(f" QWidget {{ }} ")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(scale(6), scale(3), scale(6), scale(3))
        layout.setSpacing(scale(4))
        self._back_btn = _NavButton("fa5s.arrow-left", "Back (Alt+Left)")
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._panel._go_back)
        layout.addWidget(self._back_btn)
        self._forward_btn = _NavButton("fa5s.arrow-right", "Forward (Alt+Right)")
        self._forward_btn.setEnabled(False)
        self._forward_btn.clicked.connect(self._panel._go_forward)
        layout.addWidget(self._forward_btn)
        self._up_btn = _NavButton("fa5s.arrow-up", "Up (Alt+Up)")
        self._up_btn.clicked.connect(self._panel._go_to_parent)
        layout.addWidget(self._up_btn)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        layout.addWidget(sep)
        self._address_bar = QLineEdit()
        self._address_bar.setReadOnly(True)
        self._address_bar.setStyleSheet(f" QLineEdit {{ border-radius: 2px; padding: 2px 8px; font-size: 11px; min-height: 18px; }} QLineEdit:focus {{ }} ")
        layout.addWidget(self._address_bar, 1)
        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText(" Search...")
        self._search_bar.setClearButtonEnabled(True)
        self._search_bar.setMaximumWidth(scale(180))
        self._search_bar.textChanged.connect(self._on_search)
        self._search_bar.setStyleSheet(f" QLineEdit {{ border-radius: 2px; padding: 2px 24px 2px 8px; font-size: 11px; min-height: 18px; }} QLineEdit:focus {{ }} QLineEdit::placeholder {{ }} ")
        layout.addWidget(self._search_bar)
    def _on_search(self, text):
        self._panel._active_pane()._on_search(text)
    def update_address(self, path: str):
        display = path.replace(self._panel._project_root, os.path.basename(self._panel._project_root))
        display = display.replace("\\", " \u25B8 ").replace("/", " \u25B8 ")
        self._address_bar.setText(display)
class _StatusBar(QWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setFixedHeight(scale(18))
        self.setStyleSheet(f" QWidget {{ }} ")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(scale(8), 0, scale(8), 0)
        layout.setSpacing(scale(12))
        self._count_label = QLabel("0 items")
        layout.addWidget(self._count_label)
        sep = QLabel("|")
        layout.addWidget(sep)
        self._selected_label = QLabel("")
        layout.addWidget(self._selected_label)
        layout.addStretch()
        self._total_label = QLabel("")
        layout.addWidget(self._total_label)
        self._path_label = QLabel("")
        layout.addWidget(self._path_label)
    def update_counts(self, total: int, selected: int = 0):
        self._count_label.setText(f"{total} item{'s' if total != 1 else ''}")
        if selected > 0:
            self._selected_label.setText(f"{selected} selected")
        else:
            self._selected_label.setText("")
    def update_total(self, text: str):
        try:
            self._total_label.setText(text)
        except Exception:
            pass
    def update_path(self, path: str):
        short = path
        if len(short) > 60:
            short = "..." + short[-57:]
        self._path_label.setText(short)
