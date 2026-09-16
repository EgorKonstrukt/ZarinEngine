# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import queue
import sys
import shutil
import datetime
import subprocess
import tempfile
import threading
import time
from typing import Optional, TYPE_CHECKING
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                             QTreeWidget, QTreeWidgetItem, QPushButton,
                             QLabel, QLineEdit, QMenu, QFileDialog, QSplitter,
                             QListWidget, QListWidgetItem, QAbstractItemView,
                             QToolButton, QSlider, QFileIconProvider,
                             QStackedWidget, QFrame, QHeaderView, QSizePolicy,
                             QGraphicsDropShadowEffect, QStyledItemDelegate,
                             QAbstractItemDelegate, QApplication)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal, QMimeData, QByteArray, QSize, QFileInfo, QUrl, QTimer
from PyQt6.QtGui import (QAction, QDrag, QIcon, QWheelEvent, QKeyEvent, QGuiApplication,
                          QShortcut, QKeySequence, QColor, QPainter, QPainterPath, QFont,
                          QPen, QBrush, QPixmap, QFontMetrics, QPalette)

try:
    import qtawesome as qta
except ImportError:
    qta = None

_QTA_COLORS = {
    "folder": "#d4d4d4",
    "file": "#d4d4d4",
    "nav": "#d4d4d4",
    "create": "#9ccc65",
    "refresh": "#d4d4d4",
    "dual": "#d4d4d4",
    "view": "#d4d4d4",
}


def _qta_icon(name: str, color: str | None = None) -> QIcon:
    if qta is None:
        return QIcon()
    c = color if color else _QTA_COLORS.get(name.split(".")[-1] if "." in name else name, "#d4d4d4")
    return qta.icon(name, color=c)


def _system_accent() -> QColor:
    try:
        app = QApplication.instance()
        if app is not None:
            c = app.palette().color(QPalette.ColorRole.Highlight)
            if c.isValid():
                return c
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            import winreg
            for sub in ("Software\\Microsoft\\Windows\\DWM", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Accent"):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                        for val in ("AccentColor", "AccentColorMenu"):
                            try:
                                v, _ = winreg.QueryValueEx(k, val)
                                b = v & 0xFF
                                g = (v >> 8) & 0xFF
                                r = (v >> 16) & 0xFF
                                if r + g + b > 30:
                                    return QColor(r, g, b)
                            except Exception:
                                continue
                except Exception:
                    continue
    except Exception:
        pass
    return QColor("#0078d7")


def _accent_hex() -> str:
    try:
        return _system_accent().name()
    except Exception:
        return "#0078d7"


def _accent_rgba(alpha: int) -> str:
    try:
        c = _system_accent()
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"
    except Exception:
        return f"rgba(0,120,215,{alpha})"

if TYPE_CHECKING:
    from core.engine.engine import Engine
from editor.resource_picker import _get_thumbnail, _format_size, _thumb_resolution
from editor.hover_preview import attach_project_list_hover, attach_project_tree_hover

try:
    from editor.shell_context_menu import show_shell_context_menu
    _HAS_SHELL_MENU = (sys.platform == "win32")
except Exception:
    show_shell_context_menu = None
    _HAS_SHELL_MENU = False

from editor.constants import MIN_THUMB, MAX_THUMB, VIEW_ICON, VIEW_LIST, VIEW_DETAILS
from editor.inspector.helpers import _flash_overlay

_ENTITY_MIME = "application/x-zpe-entity"
from core.config.editor_scale import scale, scale_xy

_file_clipboard: list[str] = []
_clipboard_is_cut: bool = False

_VCS_COLORS = {
    "untracked": QColor("#3C9B3C"),
    "added":     QColor("#3C9B3C"),
    "modified":  QColor("#3C6E9B"),
    "staged":    QColor("#3C6E9B"),
    "unstaged":  QColor("#3C6E9B"),
    "deleted":   QColor("#9B3C3C"),
    "conflict":  QColor("#9B3C3C"),
    "renamed":   QColor("#9B6E3C"),
}


def _parse_vcs_status(project_path: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for candidate in ["git.exe", "git"]:
        try:
            r = subprocess.run([candidate, "--version"], capture_output=True,
                               text=True, timeout=5)
            if r.returncode == 0:
                break
        except FileNotFoundError:
            continue
    else:
        return result
    try:
        r = subprocess.run([candidate, "status", "--porcelain", "-u"],
                           capture_output=True, text=True,
                           cwd=project_path, timeout=15)
    except Exception:
        return result
    for line in r.stdout.strip().split("\n"):
        line = line.rstrip()
        if not line or len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:]
        if xy[0] == "?" and xy[1] == "?":
            result[path.replace("\\", "/")] = "untracked"
        elif xy[0] == "A" or xy[0] == "A ":
            result[path.replace("\\", "/")] = "added"
        elif xy[0] == "M" or xy[1] == "M":
            result[path.replace("\\", "/")] = "modified"
        elif xy[0] == "D" or xy[1] == "D":
            result[path.replace("\\", "/")] = "deleted"
        elif xy[0] == "R" or xy[1] == "R":
            result[path.replace("\\", "/")] = "renamed"
        elif xy[0] == "U" or xy[1] == "U":
            result[path.replace("\\", "/")] = "conflict"
    return result


class _NavButton(QToolButton):
    def __init__(self, icon_name="", tooltip="", parent=None):
        super().__init__(parent)
        if icon_name and qta is not None:
            self.setIcon(qta.icon(icon_name, color="#d4d4d4"))
            self.setIconSize(QSize(*scale_xy(18, 18)))
        self.setToolTip(tooltip)
        self.setFixedSize(scale(34), scale(32))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0;
            }}
            QToolButton:hover {{
            }}
            QToolButton:pressed {{
                background: #444;
            }}
            QToolButton:disabled {{
                color: #3a3a3a;
            }}
        """)

class _AddressBar(QLineEdit):
    path_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet(f"""
            QLineEdit {{
                border-radius: 2px;
                padding: 2px 8px;
                font-size: 12px;
                min-height: 22px;
            }}
            QLineEdit:focus {{
            }}
        """)

class _SearchBar(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Search...")
        self.setClearButtonEnabled(True)
        self.setMaximumWidth(scale(200))
        self.setStyleSheet(f"""
            QLineEdit {{
                border-radius: 2px;
                padding: 2px 24px 2px 8px;
                font-size: 11px;
                min-height: 22px;
            }}
            QLineEdit:focus {{
            }}
            QLineEdit::placeholder {{
            }}
        """)

class _GroupHeader(QWidget):
    def __init__(self, text, count=0, parent=None):
        super().__init__(parent)
        self._text = text
        self._count = count
        self.setFixedHeight(scale(26))
        self.setStyleSheet(f"""
        """)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = p.font()
        font.setPointSize(9)
        font.setBold(False)
        p.setFont(font)
        x = scale(8)
        y = (self.height() - p.fontMetrics().height()) // 2 + p.fontMetrics().ascent()
        p.drawText(x, y, self._text)
        if self._count > 0:
            count_text = f" ({self._count})"
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(self._text)
            p.drawText(x + text_w + scale(4), y, count_text)
        p.end()

class FileListWidget(QListWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setAcceptDrops(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        try:
            attach_project_list_hover(self)
        except Exception:
            pass

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta != 0:
                step = 8 if abs(delta) > 120 else 4
                new_val = self._panel._thumb_size + (step if delta > 0 else -step)
                new_val = max(MIN_THUMB, min(new_val, MAX_THUMB))
                self._panel._thumb_size = new_val
                self._panel._zoom_slider.setValue(new_val)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_F2:
            items = self.selectedItems()
            if items:
                self.editItem(items[0])
            return
        if key == Qt.Key.Key_Delete:
            self._panel._delete_selected()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            items = self.selectedItems()
            if items:
                self._panel._open_item(items[0])
            return
        if key == Qt.Key.Key_Backspace or (event.modifiers() == Qt.KeyboardModifier.AltModifier and key == Qt.Key.Key_Up):
            self._panel._go_to_parent()
            return
        if key == Qt.Key.Key_Home:
            self._panel._go_to_root()
            return
        if key == Qt.Key.Key_F5:
            self._panel._refresh()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self._panel._set_active_pane_by_widget(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        try:
            pos = event.position().toPoint()
        except Exception:
            pos = event.pos()
        if self.itemAt(pos) is None:
            self._panel._go_to_parent()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME):
            self._panel._on_entity_drop(event)
        elif event.mimeData().hasUrls() or event.mimeData().hasText():
            self._panel._on_file_list_drop(event)
        else:
            super().dropEvent(event)

    def startDrag(self, supportedActions):
        self._panel._start_drag_list(supportedActions)

    def _open_item(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._panel._open_path(path)

class FileDetailWidget(QTreeWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setAcceptDrops(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        try:
            attach_project_tree_hover(self)
        except Exception:
            pass

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta != 0:
                step = 8 if abs(delta) > 120 else 4
                new_val = self._panel._thumb_size + (step if delta > 0 else -step)
                new_val = max(MIN_THUMB, min(new_val, MAX_THUMB))
                self._panel._thumb_size = new_val
                self._panel._zoom_slider.setValue(new_val)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_F2:
            items = self.selectedItems()
            if items:
                self.editItem(items[0], 0)
            return
        if key == Qt.Key.Key_Delete:
            self._panel._delete_selected()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            items = self.selectedItems()
            if items:
                self._panel._open_item_by_path(items[0].data(0, Qt.ItemDataRole.UserRole))
            return
        if key == Qt.Key.Key_Backspace or (event.modifiers() == Qt.KeyboardModifier.AltModifier and key == Qt.Key.Key_Up):
            self._panel._go_to_parent()
            return
        if key == Qt.Key.Key_Home:
            self._panel._go_to_root()
            return
        if key == Qt.Key.Key_F5:
            self._panel._refresh()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self._panel._set_active_pane_by_widget(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        try:
            pos = event.position().toPoint()
        except Exception:
            pos = event.pos()
        try:
            hit = self.itemAt(pos)
        except Exception:
            hit = None
        if hit is None:
            self._panel._go_to_parent()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME):
            self._panel._on_entity_drop(event)
        elif event.mimeData().hasUrls() or event.mimeData().hasText():
            self._panel._on_detail_tree_drop(event)
        else:
            super().dropEvent(event)

    def startDrag(self, supportedActions):
        self._panel._start_drag_detail(supportedActions)

class FolderTreeWidget(QTreeWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setAcceptDrops(True)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setIndentation(scale(12))
        self.setUniformRowHeights(True)
        self.setStyleSheet(f"""
            QTreeWidget {{
                border: none;
                outline: none;
                font-size: 12px;
                padding: 2px;
            }}
            QTreeWidget::item {{
                padding: 1px 4px;
                border: 1px solid transparent;
                border-radius: 2px;
                min-height: 19px;
            }}
            QTreeWidget::item:selected {{
            }}
            QTreeWidget::item:hover:!selected {{
            }}
            QTreeWidget::branch {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                min-height: 30px;
                border-radius: 4px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #666;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        try:
            attach_project_tree_hover(self)
        except Exception:
            pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(_ENTITY_MIME):
            self._panel._on_entity_drop(event)
        elif event.mimeData().hasUrls() or event.mimeData().hasText():
            self._panel._on_folder_tree_drop(event)
        else:
            super().dropEvent(event)

class _AddressBreadcrumb(QLineEdit):
    def __init__(self, pane: _FilePane, parent=None):
        super().__init__(parent)
        self._pane = pane
        self._editing = False
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 2px;
                padding: 2px 6px;
                font-size: 12px;
                min-height: 20px;
            }}
            QLineEdit:focus {{
                padding: 2px 6px;
            }}
        """)

    def mousePressEvent(self, event):
        try:
            self._pane._panel._set_active_pane(self._pane)
        except Exception:
            pass
        if not self._editing:
            self._enter_edit_mode()
        super().mousePressEvent(event)

    def focusInEvent(self, event):
        try:
            self._pane._panel._set_active_pane(self._pane)
        except Exception:
            pass
        if not self._editing:
            self._enter_edit_mode()
        super().focusInEvent(event)

    def _enter_edit_mode(self):
        self._editing = True
        self.setReadOnly(False)
        self.setText(self._pane._current_dir)
        self.selectAll()
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setStyleSheet(f"""
            QLineEdit {{
                border-radius: 2px;
                padding: 2px 6px;
                font-size: 12px;
                min-height: 20px;
            }}
        """)

    def _exit_edit_mode(self):
        self._editing = False
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pane.rebuild_breadcrumb()
        try:
            self._pane.set_active(self._pane._active)
        except Exception:
            self.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 2px;
                padding: 2px 6px;
                font-size: 12px;
                min-height: 20px;
            }}
            QLineEdit:focus {{
                padding: 2px 6px;
            }}
        """)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            path = self.text().strip()
            if path and os.path.isdir(path):
                self._pane._panel._navigate_to(self._pane, path, record=True)
            self._exit_edit_mode()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._exit_edit_mode()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self._exit_edit_mode()
        super().focusOutEvent(event)

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
        widget = self._detail_tree
        widget.blockSignals(True)
        widget.clear()
        self._add_up_row_detail(widget, dirpath)
        use_thumbs = self._panel._thumb_size >= 20
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
        need_sizes = []
        for entry, full, is_dir, _sz, _mt, _ex in ordered:
            if entry.startswith("."):
                continue
            if filter_text and filter_text.lower() not in entry.lower():
                continue
            item = QTreeWidgetItem()
            if is_dir:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                try:
                    item.setIcon(0, self._panel._icon_provider.icon(QFileIconProvider.IconType.Folder))
                except Exception:
                    pass
                item.setText(0, entry)
                item.setText(1, "[DIR]")
                try:
                    mt = os.path.getmtime(full)
                    dt = datetime.datetime.fromtimestamp(mt)
                    item.setText(2, dt.strftime("%Y-%m-%d %H:%M"))
                except Exception:
                    item.setText(2, "")
                try:
                    norm = os.path.normpath(full)
                    cached = self._panel._dir_size_cache.get(norm)
                    if cached is not None:
                        item.setText(3, _format_size(int(cached)))
                        item.setData(0, Qt.ItemDataRole.UserRole + 2, int(cached))
                        try:
                            item.setForeground(3, self._panel._size_brush(int(cached)))
                        except Exception:
                            pass
                    else:
                        item.setText(3, "…")
                        need_sizes.append(full)
                except Exception:
                    item.setText(3, "…")
                    try:
                        need_sizes.append(full)
                    except Exception:
                        pass
                item.setToolTip(0, f"Folder: {full}")
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                if use_thumbs:
                    pm = _get_thumbnail(full, _thumb_resolution())
                    if pm and not pm.isNull():
                        item.setIcon(0, QIcon(pm))
                    else:
                        try:
                            fi = QFileInfo(full)
                            icon = self._panel._icon_provider.icon(fi)
                            if icon and not icon.isNull():
                                item.setIcon(0, icon)
                        except Exception:
                            pass
                else:
                    try:
                        fi = QFileInfo(full)
                        icon = self._panel._icon_provider.icon(fi)
                        if icon and not icon.isNull():
                            item.setIcon(0, icon)
                    except Exception:
                        pass
                item.setText(0, entry)
                item.setText(1, self._type_label(entry, False))
                try:
                    mtime = os.path.getmtime(full)
                    dt = datetime.datetime.fromtimestamp(mtime)
                    item.setText(2, dt.strftime("%Y-%m-%d %H:%M"))
                except OSError:
                    item.setText(2, "")
                try:
                    sz = os.path.getsize(full)
                    item.setText(3, _format_size(sz))
                    item.setData(0, Qt.ItemDataRole.UserRole + 2, int(sz))
                    try:
                        item.setForeground(3, self._panel._size_brush(int(sz)))
                    except Exception:
                        pass
                except OSError:
                    item.setText(3, "")
            item.setData(0, Qt.ItemDataRole.UserRole, full)
            try:
                item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            except Exception:
                pass
            widget.addTopLevelItem(item)
        widget.blockSignals(False)
        try:
            self._panel._apply_sort_indicators()
        except Exception:
            pass
        try:
            self._panel._apply_vcs_colors()
        except Exception:
            pass
        if need_sizes:
            try:
                self._panel._request_dir_sizes(need_sizes)
            except Exception:
                pass

    def active_widget(self):
        return self._detail_tree if self._panel._view_mode == VIEW_DETAILS else self._file_list

    def refresh(self):
        self.populate_files(self._current_dir)

class _NavBar(QWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setFixedHeight(scale(34))
        self.setStyleSheet(f"""
            QWidget {{
            }}
        """)
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
        self._address_bar.setStyleSheet(f"""
            QLineEdit {{
                border-radius: 2px;
                padding: 2px 8px;
                font-size: 11px;
                min-height: 18px;
            }}
            QLineEdit:focus {{
            }}
        """)
        layout.addWidget(self._address_bar, 1)

        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText(" Search...")
        self._search_bar.setClearButtonEnabled(True)
        self._search_bar.setMaximumWidth(scale(180))
        self._search_bar.textChanged.connect(self._on_search)
        self._search_bar.setStyleSheet(f"""
            QLineEdit {{
                border-radius: 2px;
                padding: 2px 24px 2px 8px;
                font-size: 11px;
                min-height: 18px;
            }}
            QLineEdit:focus {{
            }}
            QLineEdit::placeholder {{
            }}
        """)
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
        self.setStyleSheet(f"""
            QWidget {{
            }}
        """)
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

class _FileListDelegate(QStyledItemDelegate):
    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._panel = panel

    def paint(self, painter, option, index):
        group_type = index.data(Qt.ItemDataRole.UserRole + 1)
        if group_type == "group_header":
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = option.rect
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawLine(rect.x(), rect.y(), rect.x() + rect.width(), rect.y())
            painter.drawLine(rect.x(), rect.y() + rect.height() - 1, rect.x() + rect.width(), rect.y() + rect.height() - 1)
            font = painter.font()
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            text = index.data(Qt.ItemDataRole.UserRole + 2) or ""
            count = index.data(Qt.ItemDataRole.UserRole + 3) or 0
            fm = QFontMetrics(font)
            x = rect.x() + scale(8)
            y = rect.y() + (rect.height() + fm.ascent() - fm.descent()) // 2
            painter.drawText(x, y, text)
            if count > 0:
                count_text = f" ({count})"
                text_w = fm.horizontalAdvance(text)
                painter.drawText(x + text_w + scale(2), y, count_text)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):
        group_type = index.data(Qt.ItemDataRole.UserRole + 1)
        if group_type == "group_header":
            return QSize(0, scale(24))
        return super().sizeHint(option, index)

class ProjectPanel(QDockWidget):
    file_double_clicked = pyqtSignal(str)
    prefab_drag_started = pyqtSignal(str)
    import_model_requested = pyqtSignal(str)
    file_selected = pyqtSignal(str)
    _vcs_result_ready = pyqtSignal(dict)
    _dir_size_ready = pyqtSignal(str, int, int)

    def __init__(self, engine: Engine, project_root: str = "assets", parent=None):
        super().__init__("Project", parent)
        self._engine = engine
        self._project_root = os.path.abspath(project_root)
        self._thumb_size = 64
        self._icon_provider = QFileIconProvider()
        self._view_mode = VIEW_DETAILS
        self._dual_pane = False
        self._history = [[], []]
        self._history_index = 0
        self._nav_bar = None
        self._status_bar = None
        self._file_undo: list = []
        self._file_redo: list = []
        self._in_file_undo = False
        self._restoring_state = False
        self._sort_col = 0
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._sort_guard = False
        self._dir_size_cache: dict[str, int] = {}
        self._dir_size_gen = 0
        self._dir_size_queue: queue.Queue = queue.Queue()
        self._dir_size_thread: threading.Thread | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_state_now)
        self._vcs_status: dict[str, str] = {}
        self._vcs_refreshing: bool = False
        self._vcs_pending: bool = False
        self._vcs_timer = QTimer(self)
        self._vcs_timer.timeout.connect(self._refresh_vcs_status)
        self._vcs_timer.start(10000)
        self._vcs_result_ready.connect(self._on_vcs_result)
        try:
            self._dir_size_ready.connect(self._on_dir_size_ready, Qt.ConnectionType.QueuedConnection)
        except Exception:
            pass
        self._refresh_vcs_status()
        self._setup_ui()
        self._populate_tree()
        self._push_history(self._project_root)
        try:
            self._pane_splitter.splitterMoved.connect(lambda *a: self._schedule_save())
        except Exception:
            pass

    def load_config(self, config) -> None:
        try:
            thumb_size = config.get("project.thumb_size", self._thumb_size)
            self._thumb_size = max(MIN_THUMB, min(int(thumb_size), MAX_THUMB))
        except Exception:
            pass
        try:
            vm = int(config.get("project.view_mode", self._view_mode))
            if vm in (VIEW_ICON, VIEW_LIST, VIEW_DETAILS):
                self._view_mode = vm
        except Exception:
            pass
        try:
            self._dual_pane = bool(config.get("project.dual_pane", False))
        except Exception:
            pass
        try:
            sc = int(config.get("project.sort_column", 0))
            if sc in (0, 1, 2, 3):
                self._sort_col = sc
        except Exception:
            pass
        try:
            so = int(config.get("project.sort_order", 0))
            self._sort_order = Qt.SortOrder.DescendingOrder if so == 1 else Qt.SortOrder.AscendingOrder
        except Exception:
            pass
        if hasattr(self, "_zoom_slider"):
            try:
                self._zoom_slider.blockSignals(True)
                self._zoom_slider.setValue(self._thumb_size)
                self._zoom_slider.blockSignals(False)
            except Exception:
                pass
        if hasattr(self, "_dual_pane_btn"):
            try:
                self._dual_pane_btn.blockSignals(True)
                self._dual_pane_btn.setChecked(self._dual_pane)
                self._dual_pane_btn.blockSignals(False)
            except Exception:
                pass
        self._restoring_state = True
        try:
            self._apply_dual_pane_state()
            self._apply_view_mode()
            self._update_view_mode_icon()
            self._restore_pane_dirs(config)
        finally:
            self._restoring_state = False
        try:
            self._update_nav_buttons()
        except Exception:
            pass

    def save_config(self, config) -> None:
        config.set("project.thumb_size", self._thumb_size)
        config.set("project.dual_pane", self._dual_pane)
        config.set("project.view_mode", self._view_mode)
        try:
            config.set("project.sort_column", int(self._sort_col))
        except Exception:
            pass
        try:
            config.set("project.sort_order", 1 if self._sort_order == Qt.SortOrder.DescendingOrder else 0)
        except Exception:
            pass
        try:
            config.set("project.pane_a_dir", self._rel_or_abs(self._pane_a._current_dir))
        except Exception:
            pass
        try:
            if self._pane_b is not None:
                config.set("project.pane_b_dir", self._rel_or_abs(self._pane_b._current_dir))
            else:
                config.set("project.pane_b_dir", self._rel_or_abs(self._pane_a._current_dir))
        except Exception:
            pass
        try:
            if hasattr(self, "_pane_splitter") and self._pane_b is not None:
                config.set("project.splitter", list(self._pane_splitter.sizes()))
        except Exception:
            pass

    def _rel_or_abs(self, path: str) -> str:
        try:
            rel = os.path.relpath(os.path.normpath(path), self._project_root)
            if rel == ".":
                return "."
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except Exception:
            pass
        return os.path.normpath(path)

    def _abs_from_saved(self, saved) -> str:
        if not saved:
            return self._project_root
        try:
            s = str(saved).replace("/", os.sep)
            cand = s
            if not os.path.isabs(cand):
                cand = os.path.normpath(os.path.join(self._project_root, cand))
            else:
                cand = os.path.normpath(cand)
            try:
                common = os.path.commonpath([cand, self._project_root])
            except Exception:
                return self._project_root
            if common != self._project_root:
                return self._project_root
            if os.path.isdir(cand):
                return cand
        except Exception:
            pass
        return self._project_root

    def _restore_pane_dirs(self, config):
        try:
            a_dir = self._abs_from_saved(config.get("project.pane_a_dir", self._project_root))
        except Exception:
            a_dir = self._project_root
        try:
            b_dir = self._abs_from_saved(config.get("project.pane_b_dir", a_dir))
        except Exception:
            b_dir = a_dir
        try:
            self._pane_a._hist_back = []
            self._pane_a._hist_fwd = []
            self._pane_a.populate_files(a_dir)
        except Exception:
            pass
        if self._pane_b is not None:
            try:
                self._pane_b._hist_back = []
                self._pane_b._hist_fwd = []
                self._pane_b.populate_files(b_dir)
            except Exception:
                pass
        try:
            sizes = config.get("project.splitter", None)
            if self._pane_b is not None and isinstance(sizes, (list, tuple)) and len(sizes) == 2:
                self._pane_splitter.setSizes([int(sizes[0]), int(sizes[1])])
        except Exception:
            pass
        try:
            self._set_active_pane(self._pane_a)
        except Exception:
            pass

    def _get_file_icon(self, path: str) -> QIcon:
        ext = os.path.splitext(path)[1].lower()
        ext_map = {
            ".py": "fa5s.file-code", ".txt": "fa5s.file-alt", ".json": "fa5s.file-code",
            ".xml": "fa5s.file-code", ".csv": "fa5s.file-csv", ".ini": "fa5s.file-code",
            ".cfg": "fa5s.file-code", ".toml": "fa5s.file-code", ".yaml": "fa5s.file-code",
            ".yml": "fa5s.file-code",
        }
        if ext in ext_map:
            return _qta_icon(ext_map[ext], "#d4d4d4")
        if ext == ".zpes":
            from editor.resource_picker import _draw_scene_icon
            return QIcon(_draw_scene_icon(self._thumb_size))
        if ext == ".zpep":
            from editor.resource_picker import _draw_prefab_icon
            return QIcon(_draw_prefab_icon(self._thumb_size))
        if ext == ".mat":
            from editor.resource_picker import _get_material_thumbnail, _draw_material_icon
            pm = _get_material_thumbnail(path, self._thumb_size)
            if pm:
                return QIcon(pm)
            return QIcon(_draw_material_icon(self._thumb_size))
        if ext in (".animclip", ".animcontroller"):
            from editor.resource_picker import _draw_file_icon
            return QIcon(_draw_file_icon(self._thumb_size))
        return None

    def _active_pane(self) -> _FilePane:
        try:
            if self._dual_pane and self._pane_b is not None and self._pane_b._active:
                return self._pane_b
        except Exception:
            pass
        return self._pane_a

    def _set_active_pane(self, pane) -> None:
        if pane is None:
            return
        if pane is not self._pane_a and pane is not getattr(self, "_pane_b", None):
            return
        other = self._pane_b if pane is self._pane_a else self._pane_a
        pane.set_active(True)
        if other is not None:
            other.set_active(False)
        try:
            if self._nav_bar:
                self._nav_bar.update_address(pane._current_dir)
                self._nav_bar._back_btn.setEnabled(len(pane._hist_back) > 0)
                self._nav_bar._forward_btn.setEnabled(len(pane._hist_fwd) > 0)
            if self._status_bar:
                self._status_bar.update_path(pane._current_dir)
                try:
                    entries = os.listdir(pane._current_dir)
                    visible = [e for e in entries if not e.startswith(".") and not e.endswith(".import")]
                    self._status_bar.update_counts(len(visible))
                except Exception:
                    pass
        except Exception:
            pass

    def _set_active_pane_by_widget(self, widget) -> None:
        try:
            for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                if widget is pane._file_list or widget is pane._detail_tree or widget is pane._breadcrumb_bar or widget is pane:
                    if not pane._active:
                        self._set_active_pane(pane)
                    return
                try:
                    if widget in pane._file_list.children() or widget in pane._detail_tree.children():
                        if not pane._active:
                            self._set_active_pane(pane)
                        return
                except Exception:
                    pass
            obj = widget
            while obj is not None:
                for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                    if pane is not None and obj is pane:
                        if not pane._active:
                            self._set_active_pane(pane)
                        return
                try:
                    obj = obj.parent()
                except Exception:
                    break
        except Exception:
            pass

    def _is_inside_root(self, path: str) -> bool:
        try:
            ap = os.path.normpath(os.path.abspath(path))
            root = os.path.normpath(self._project_root)
            return os.path.commonpath([ap, root]) == root
        except Exception:
            return False

    def _navigate_to(self, pane, path: str, record: bool = True) -> None:
        if pane is None or not path:
            return
        try:
            target = os.path.normpath(os.path.abspath(path))
        except Exception:
            return
        if not self._is_inside_root(target):
            return
        if not os.path.isdir(target):
            try:
                os.makedirs(target, exist_ok=True)
            except Exception:
                return
        cur = os.path.normpath(pane._current_dir) if pane._current_dir else ""
        if cur == target:
            try:
                pane.populate_files(target)
            except Exception:
                pass
            return
        if record and not pane._navigating:
            try:
                pane._hist_back.append(pane._current_dir)
                if len(pane._hist_back) > 100:
                    pane._hist_back = pane._hist_back[-100:]
                pane._hist_fwd.clear()
            except Exception:
                pass
        self._set_active_pane(pane)
        try:
            pane.populate_files(target)
        except Exception:
            pass
        try:
            self._sync_tree_selection(target)
        except Exception:
            pass
        try:
            self._schedule_save()
        except Exception:
            pass

    def _push_history(self, path: str, pane=None):
        try:
            if pane is None:
                pane = self._active_pane()
            target = os.path.normpath(os.path.abspath(path))
            cur = os.path.normpath(pane._current_dir)
            if cur == target:
                self._update_nav_buttons()
                return
            self._navigate_to(pane, target, record=True)
        except Exception:
            pass

    def _go_back(self):
        pane = self._active_pane()
        if pane._hist_back:
            try:
                pane._navigating = True
                pane._hist_fwd.append(pane._current_dir)
                path = pane._hist_back.pop()
                pane.populate_files(path)
                try:
                    self._sync_tree_selection(path)
                except Exception:
                    pass
            finally:
                pane._navigating = False
            self._update_nav_buttons()
            try:
                self._schedule_save()
            except Exception:
                pass

    def _go_forward(self):
        pane = self._active_pane()
        if pane._hist_fwd:
            try:
                pane._navigating = True
                pane._hist_back.append(pane._current_dir)
                path = pane._hist_fwd.pop()
                pane.populate_files(path)
                try:
                    self._sync_tree_selection(path)
                except Exception:
                    pass
            finally:
                pane._navigating = False
            self._update_nav_buttons()
            try:
                self._schedule_save()
            except Exception:
                pass

    def _update_nav_buttons(self):
        try:
            pane = self._active_pane()
            if self._nav_bar:
                self._nav_bar._back_btn.setEnabled(len(pane._hist_back) > 0)
                self._nav_bar._forward_btn.setEnabled(len(pane._hist_fwd) > 0)
        except Exception:
            pass

    def _update_pane_selection_style(self, pane) -> None:
        try:
            accent = _accent_hex()
        except Exception:
            accent = "#0078d7"
        try:
            is_active = bool(pane._active)
        except Exception:
            is_active = True
        try:
            if is_active:
                sel = f"QTreeWidget::item:selected {{ background: {accent}; color: white; }} QTreeWidget::item:selected:!active {{ background: {accent}; color: white; }} QListWidget::item:selected {{ background: {accent}; color: white; }}"
            else:
                sel = "QTreeWidget::item:selected { background: #4a4a4a; color: white; } QTreeWidget::item:selected:!active { background: #3d3d3d; color: #d4d4d4; } QListWidget::item:selected { background: #4a4a4a; color: white; }"
            base_tree = f"QTreeWidget {{ border: none; outline: none; show-decoration-selected: 1; background: #252526; alternate-background-color: #2a2a2d; }} QTreeWidget::item {{ padding: 1px 2px; min-height: 20px; }} QTreeWidget::item:alternate {{ background: #2a2a2d; }} {sel}"
            base_list = f"QListWidget {{ border: none; outline: none; }} {sel}"
            try:
                pane._detail_tree.setStyleSheet(base_tree)
            except Exception:
                pass
            try:
                pane._file_list.setStyleSheet(base_list)
            except Exception:
                pass
        except Exception:
            pass

    def _schedule_save(self) -> None:
        try:
            if self._restoring_state:
                return
            if not self._save_timer.isActive():
                self._save_timer.start()
        except Exception:
            pass

    def _save_state_now(self) -> None:
        try:
            if self._restoring_state:
                return
            from core.config.config import get_global_config
            cfg = get_global_config()
            self.save_config(cfg)
            try:
                cfg.save()
            except Exception:
                pass
        except Exception:
            pass

    def _on_sort_changed(self, pane, logical: int) -> None:
        try:
            if self._sort_guard:
                return
            order = pane._detail_tree.header().sortIndicatorOrder()
            self._sort_col = int(logical)
            self._sort_order = order
            self._apply_sort_indicators()
            pane.refresh()
            if getattr(self, "_pane_b", None) is not None:
                try:
                    self._pane_b.refresh()
                except Exception:
                    pass
            self._schedule_save()
        except Exception:
            pass

    def _apply_sort_indicators(self) -> None:
        try:
            self._sort_guard = True
            for pane in (getattr(self, "_pane_a", None), getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                try:
                    h = pane._detail_tree.header()
                    h.blockSignals(True)
                    h.setSortIndicator(self._sort_col, self._sort_order)
                    h.blockSignals(False)
                except Exception:
                    pass
        finally:
            try:
                self._sort_guard = False
            except Exception:
                pass

    def _sorted_entries(self, dirpath: str, entries: list[str]):
        try:
            reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        except Exception:
            reverse = False
        col = getattr(self, "_sort_col", 0)
        rows = []
        for e in entries:
            full = os.path.join(dirpath, e)
            try:
                is_dir = os.path.isdir(full)
            except Exception:
                is_dir = False
            try:
                sz = os.path.getsize(full) if not is_dir else int(self._dir_size_cache.get(os.path.normpath(full), -1))
            except Exception:
                sz = -1
            try:
                mt = os.path.getmtime(full)
            except Exception:
                mt = 0
            ext = os.path.splitext(e)[1].lower() if not is_dir else ""
            rows.append((e, full, is_dir, sz, mt, ext))
        try:
            if col == 3:
                rows.sort(key=lambda r: (r[3] < 0, r[3], r[0].lower()), reverse=reverse)
            elif col == 2:
                rows.sort(key=lambda r: (r[4], r[0].lower()), reverse=reverse)
            elif col == 1:
                rows.sort(key=lambda r: (r[5] if not r[2] else "", r[0].lower()), reverse=reverse)
            else:
                rows.sort(key=lambda r: r[0].lower(), reverse=reverse)
        except Exception:
            pass
        dirs = [r for r in rows if r[2]]
        files = [r for r in rows if not r[2]]
        return dirs + files

    def _ensure_size_thread(self) -> None:
        try:
            if self._dir_size_thread is not None and self._dir_size_thread.is_alive():
                return
            t = threading.Thread(target=self._dir_size_loop, daemon=True)
            self._dir_size_thread = t
            t.start()
        except Exception:
            pass

    def _dir_size_loop(self) -> None:
        while True:
            try:
                gen, path = self._dir_size_queue.get()
            except Exception:
                continue
            try:
                if gen != self._dir_size_gen:
                    continue
                norm = os.path.normpath(path)
                if norm in self._dir_size_cache:
                    continue
                total = self._compute_dir_size_fast(path, gen)
                if total is None:
                    continue
                if gen != self._dir_size_gen:
                    continue
                self._dir_size_cache[norm] = int(total)
                try:
                    self._dir_size_ready.emit(path, int(total), int(gen))
                except Exception:
                    pass
            except Exception:
                pass

    def _compute_dir_size_fast(self, root: str, gen: int):
        total = 0
        try:
            stack = [root]
            steps = 0
            while stack:
                if gen != self._dir_size_gen:
                    return None
                cur = stack.pop()
                try:
                    with os.scandir(cur) as it:
                        for entry in it:
                            steps += 1
                            if steps % 2000 == 0 and gen != self._dir_size_gen:
                                return None
                            try:
                                if entry.is_symlink():
                                    continue
                                if entry.is_dir(follow_symlinks=False):
                                    stack.append(entry.path)
                                elif entry.is_file(follow_symlinks=False):
                                    try:
                                        total += entry.stat(follow_symlinks=False).st_size
                                    except Exception:
                                        pass
                            except Exception:
                                continue
                except Exception:
                    continue
            return total
        except Exception:
            return total

    def _request_dir_sizes(self, folder_paths: list[str]) -> None:
        try:
            self._ensure_size_thread()
            gen = int(self._dir_size_gen)
            for p in folder_paths:
                try:
                    norm = os.path.normpath(p)
                    if norm in self._dir_size_cache:
                        continue
                    self._dir_size_queue.put((gen, p))
                except Exception:
                    continue
        except Exception:
            pass

    def _on_dir_size_ready(self, path: str, size: int, gen: int) -> None:
        try:
            norm = os.path.normpath(path)
            self._dir_size_cache[norm] = int(size)
            for pane in (getattr(self, "_pane_a", None), getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                try:
                    if os.path.normpath(pane._current_dir) != os.path.normpath(os.path.dirname(path)):
                        continue
                except Exception:
                    pass
                try:
                    tree = pane._detail_tree
                    for i in range(tree.topLevelItemCount()):
                        it = tree.topLevelItem(i)
                        try:
                            if it.data(0, Qt.ItemDataRole.UserRole) == path:
                                it.setText(3, _format_size(int(size)))
                                it.setData(0, Qt.ItemDataRole.UserRole + 2, int(size))
                                it.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                                try:
                                    it.setForeground(3, self._size_brush(int(size)))
                                except Exception:
                                    pass
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            try:
                self._refresh_status_sizes()
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_status_sizes(self) -> None:
        try:
            pane = self._active_pane()
            if pane is None or self._status_bar is None:
                return
            total = 0
            has_total = False
            try:
                for i in range(pane._detail_tree.topLevelItemCount()):
                    it = pane._detail_tree.topLevelItem(i)
                    try:
                        p = it.data(0, Qt.ItemDataRole.UserRole)
                        if not p or os.path.basename(p) == "..":
                            continue
                        if os.path.isdir(p):
                            v = self._dir_size_cache.get(os.path.normpath(p))
                            if v is not None:
                                total += int(v)
                                has_total = True
                        else:
                            try:
                                total += os.path.getsize(p)
                                has_total = True
                            except Exception:
                                pass
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                if has_total:
                    self._status_bar.update_total(_format_size(total))
                else:
                    self._status_bar.update_total("")
            except Exception:
                pass
        except Exception:
            pass

    def _invalidate_dir_size(self, path: str) -> None:
        try:
            cur = os.path.normpath(os.path.abspath(path))
            root = os.path.normpath(self._project_root)
            for _ in range(32):
                try:
                    self._dir_size_cache.pop(cur, None)
                except Exception:
                    pass
                if cur == root:
                    break
                nxt = os.path.normpath(os.path.dirname(cur))
                if nxt == cur:
                    break
                cur = nxt
        except Exception:
            pass

    def _setup_ui(self):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setFixedHeight(scale(38))
        toolbar.setStyleSheet(f"""
            QWidget {{
            }}
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(scale(8), scale(4), scale(8), scale(4))
        toolbar_layout.setSpacing(scale(6))

        create_btn = QToolButton()
        if qta is not None:
            create_btn.setIcon(qta.icon("fa5s.plus", color="#9ccc65"))
            create_btn.setIconSize(QSize(*scale_xy(18, 18)))
        create_btn.setText(" New")
        create_btn.setToolTip("Create new asset")
        create_btn.setFixedHeight(scale(30))
        create_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        create_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 12px;
                padding: 0 10px;
            }}
            QToolButton:hover {{
            }}
            QToolButton:pressed {{
                background: #444;
            }}
        """)
        create_menu = QMenu(self)
        for name, cb in [
            ("Folder", self._create_new_folder),
            ("Scene", self._create_new_scene),
            ("Material", self._create_new_material),
            ("Physic Material", self._create_new_physic_material),
            ("Animation Clip", self._create_new_animclip),
            ("Animator Controller", self._create_new_animcontroller),
            ("Python Script", self._create_new_script),
        ]:
            a = QAction(name, self)
            a.triggered.connect(cb)
            create_menu.addAction(a)
        create_btn.setMenu(create_menu)
        toolbar_layout.addWidget(create_btn)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFixedWidth(1)
        toolbar_layout.addWidget(sep1)

        self._view_mode_btn = QToolButton()
        self._view_mode_btn.setFixedSize(scale(32), scale(30))
        self._view_mode_btn.setToolTip("View Mode")
        self._view_mode_btn.clicked.connect(self._toggle_view_mode)
        self._update_view_mode_icon()
        self._view_mode_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 13px;
                padding: 2px;
            }}
            QToolButton:hover {{
            }}
        """)
        toolbar_layout.addWidget(self._view_mode_btn)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setFixedWidth(scale(110))
        self._zoom_slider.setRange(MIN_THUMB, MAX_THUMB)
        self._zoom_slider.setValue(self._thumb_size)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar_layout.addWidget(self._zoom_slider)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFixedWidth(1)
        toolbar_layout.addWidget(sep2)

        self._dual_pane_btn = QToolButton()
        self._dual_pane_btn.setFixedSize(scale(32), scale(30))
        self._dual_pane_btn.setToolTip("Dual Pane")
        self._dual_pane_btn.setCheckable(True)
        self._dual_pane_btn.setChecked(False)
        if qta is not None:
            self._dual_pane_btn.setIcon(qta.icon("fa5s.columns", color="#d4d4d4"))
            self._dual_pane_btn.setIconSize(QSize(*scale_xy(18, 18)))
        self._dual_pane_btn.toggled.connect(self._toggle_dual_pane)
        self._dual_pane_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 11px;
                padding: 2px;
            }}
            QToolButton:hover {{
            }}
            QToolButton:checked {{
            }}
        """)
        toolbar_layout.addWidget(self._dual_pane_btn)

        refresh_btn = QToolButton()
        refresh_btn.setFixedSize(scale(32), scale(30))
        refresh_btn.setToolTip("Refresh (F5)")
        if qta is not None:
            refresh_btn.setIcon(qta.icon("fa5s.sync-alt", color="#d4d4d4"))
            refresh_btn.setIconSize(QSize(*scale_xy(18, 18)))
        refresh_btn.clicked.connect(self._refresh)
        refresh_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                font-size: 14px;
            }}
            QToolButton:hover {{
            }}
        """)
        toolbar_layout.addWidget(refresh_btn)

        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar)

        self._nav_bar = _NavBar(self)
        main_layout.addWidget(self._nav_bar)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._folder_tree = FolderTreeWidget(self)
        self._folder_tree.setMinimumWidth(scale(100))
        self._folder_tree.setMaximumWidth(scale(240))
        self._folder_tree.itemClicked.connect(self._on_folder_selected)
        self._folder_tree.setDragEnabled(True)
        content_layout.addWidget(self._folder_tree)

        tree_separator = QFrame()
        tree_separator.setFrameShape(QFrame.Shape.VLine)
        tree_separator.setFixedWidth(1)
        content_layout.addWidget(tree_separator)

        self._pane_a = _FilePane(self)
        self._pane_a.set_active(True)
        self._install_pane_focus(self._pane_a)

        self._pane_b = None
        self._pane_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._pane_splitter.setHandleWidth(1)
        self._pane_splitter.setStyleSheet(f"""
            QSplitter::handle {{
            }}
            QSplitter::handle:horizontal {{
                width: 1px;
            }}
        """)
        self._pane_splitter.addWidget(self._pane_a)

        self._setup_shortcuts()
        self._apply_view_mode()
        content_layout.addWidget(self._pane_splitter, 1)
        main_layout.addWidget(content, 1)

        self._status_bar = _StatusBar(self)
        main_layout.addWidget(self._status_bar)

        self.setWidget(w)

        from editor.resource_picker import _get_thumb_service
        from editor.thumb_cache import cache_root_for_project
        _get_thumb_service().set_cache_dir(cache_root_for_project(self._project_root))
        self._connect_mesh_loader()
        self._pane_a.populate_files(self._project_root)

    def _refresh_vcs_status(self):
        if not self.isVisible():
            return
        if self._vcs_refreshing:
            self._vcs_pending = True
            return
        self._vcs_refreshing = True
        root = self._project_root
        threading.Thread(target=self._vcs_worker, args=(root,), daemon=True).start()

    def _vcs_worker(self, root: str):
        try:
            result = _parse_vcs_status(root)
        except Exception:
            result = {}
        self._vcs_result_ready.emit(result)

    def _on_vcs_result(self, result: dict[str, str]):
        self._vcs_refreshing = False
        self._vcs_status = result
        if hasattr(self, "_pane_a"):
            try:
                self._apply_vcs_colors()
            except RuntimeError:
                pass
        if self._vcs_pending:
            self._vcs_pending = False
            self._refresh_vcs_status()

    def _vcs_status_of(self, full_path: str) -> str:
        if not self._vcs_status or not full_path:
            return ""
        try:
            rel = os.path.relpath(full_path, self._project_root)
        except ValueError:
            return ""
        rel = rel.replace("\\", "/")
        return self._vcs_status.get(rel, "")

    def _apply_vcs_colors(self):
        if not self._vcs_status:
            return
        default = QBrush()
        for pane in (self._pane_a, self._pane_b):
            if not pane:
                continue
            for i in range(pane._file_list.count()):
                item = pane._file_list.item(i)
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.isfile(path):
                    status = self._vcs_status_of(path)
                    item.setForeground(_VCS_COLORS.get(status, default))
            for i in range(pane._detail_tree.topLevelItemCount()):
                item = pane._detail_tree.topLevelItem(i)
                path = item.data(0, Qt.ItemDataRole.UserRole)
                if path and os.path.isfile(path):
                    status = self._vcs_status_of(path)
                    item.setForeground(0, _VCS_COLORS.get(status, default))

    def _git_run(self, *args: str) -> tuple[int, str, str]:
        for candidate in ["git.exe", "git"]:
            try:
                r = subprocess.run([candidate, "--version"], capture_output=True,
                                   text=True, timeout=5)
                if r.returncode == 0:
                    break
            except FileNotFoundError:
                continue
        else:
            return -1, "", "git not found"
        try:
            r = subprocess.run([candidate] + list(args), capture_output=True,
                               text=True, cwd=self._project_root, timeout=30)
            return r.returncode, r.stdout, r.stderr
        except Exception as e:
            return -1, "", str(e)

    def _git_add_file(self, path: str):
        if not isinstance(path, str) or not path:
            return
        try:
            rel = os.path.relpath(path, self._project_root)
        except ValueError:
            return
        rc, _, err = self._git_run("add", "--", rel)
        if rc == 0:
            self._refresh_vcs_status()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Git Add Failed", err[:200])

    def _git_unstage_file(self, path: str):
        if not isinstance(path, str) or not path:
            return
        try:
            rel = os.path.relpath(path, self._project_root)
        except ValueError:
            return
        rc, _, err = self._git_run("restore", "--staged", "--", rel)
        if rc == 0:
            self._refresh_vcs_status()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Git Unstage Failed", err[:200])

    def _git_ignore_file(self, path: str):
        if not isinstance(path, str) or not path:
            return
        try:
            rel = os.path.relpath(path, self._project_root)
        except ValueError:
            return
        gi_path = os.path.join(self._project_root, ".gitignore")
        try:
            with open(gi_path, "a", encoding="utf-8") as f:
                f.write(f"\n/{rel}\n")
            self._refresh_vcs_status()
        except OSError as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Could not update .gitignore:\n{e}")

    def _connect_mesh_loader(self):
        from editor.resource_picker import _get_thumb_service
        loader = _get_thumb_service()
        loader.thumbnail_ready.connect(self._on_mesh_data_ready, Qt.ConnectionType.QueuedConnection)

    def _on_mesh_data_ready(self, path: str, size: int, pixmap):
        if pixmap is None or pixmap.isNull():
            return
        icon = QIcon(pixmap)
        for pane in (self._pane_a, self._pane_b):
            if not pane:
                continue
            if self._view_mode == VIEW_DETAILS:
                tree = pane._detail_tree
                for i in range(tree.topLevelItemCount()):
                    item = tree.topLevelItem(i)
                    item_path = item.data(0, Qt.ItemDataRole.UserRole)
                    if item_path == path:
                        item.setIcon(0, icon)
            else:
                fl = pane._file_list
                for i in range(fl.count()):
                    item = fl.item(i)
                    item_path = item.data(Qt.ItemDataRole.UserRole)
                    if item_path == path:
                        item.setIcon(icon)

    def _apply_dual_pane_state(self):
        want = bool(self._dual_pane)
        if want:
            if self._pane_b is None:
                self._pane_b = _FilePane(self)
                self._pane_splitter.addWidget(self._pane_b)
                try:
                    self._pane_b._current_dir = self._pane_a._current_dir
                    self._pane_b.populate_files(self._pane_a._current_dir)
                except Exception:
                    pass
                self._install_pane_focus(self._pane_b)
                self._apply_view_mode()
                try:
                    self._pane_splitter.setSizes([self._pane_splitter.width() // 2] * 2)
                except Exception:
                    pass
            self._set_active_pane(self._active_pane())
        else:
            if getattr(self, "_pane_b", None) is not None:
                try:
                    self._pane_b.setParent(None)
                    self._pane_b.deleteLater()
                except Exception:
                    pass
                self._pane_b = None
            try:
                self._set_active_pane(self._pane_a)
            except Exception:
                pass

    def _toggle_dual_pane(self, checked):
        if self._restoring_state:
            self._dual_pane = bool(checked)
            return
        self._dual_pane = bool(checked)
        self._apply_dual_pane_state()
        try:
            self._schedule_save()
        except Exception:
            pass

    def _install_pane_focus(self, pane):
        try:
            pane._file_list.installEventFilter(self)
            pane._detail_tree.installEventFilter(self)
            pane._breadcrumb_bar.installEventFilter(self)
            pane.installEventFilter(self)
            pane._file_list.viewport().installEventFilter(self)
            pane._detail_tree.viewport().installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            t = event.type()
            if t == QEvent.Type.FocusIn:
                for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                    if pane is not None and (pane._file_list is obj or pane._detail_tree is obj or pane._breadcrumb_bar is obj):
                        self._set_active_pane(pane)
                        break
            elif t == QEvent.Type.MouseButtonPress:
                for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                    if pane is None:
                        continue
                    match = False
                    try:
                        if obj is pane or obj is pane._file_list or obj is pane._detail_tree or obj is pane._breadcrumb_bar:
                            match = True
                        elif obj is pane._file_list.viewport() or obj is pane._detail_tree.viewport():
                            match = True
                    except Exception:
                        pass
                    if match:
                        self._set_active_pane(pane)
                        break
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _is_rename_editing(self) -> bool:
        try:
            fw = QApplication.focusWidget()
            if fw is None:
                return False
            for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                try:
                    if isinstance(fw, QLineEdit):
                        return True
                except Exception:
                    pass
            from PyQt6.QtWidgets import QAbstractItemView
            try:
                if isinstance(fw, QLineEdit):
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _project_has_focus(self) -> bool:
        try:
            fw = QApplication.focusWidget()
            if fw is None:
                return False
            cur = fw
            while cur is not None:
                if cur is self:
                    return True
                try:
                    cur = cur.parent()
                except Exception:
                    break
            for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                for w in (pane._file_list, pane._detail_tree, pane._breadcrumb_bar, pane):
                    try:
                        if fw is w:
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def _setup_shortcuts(self):
        sc = Qt.ShortcutContext.WidgetWithChildrenShortcut
        mapping = {
            "Ctrl+C": self._copy_selected,
            "Ctrl+X": self._cut_selected,
            "Ctrl+V": self._paste_clipboard,
            "Ctrl+D": self._duplicate_selected,
            "Ctrl+A": lambda: self._active_widget().selectAll(),
            "Ctrl+Shift+N": self._create_new_folder,
            "Alt+Left": self._go_back,
            "Alt+Right": self._go_forward,
            "Alt+Up": self._go_to_parent,
        }
        for seq_str, cb in mapping.items():
            s = QShortcut(QKeySequence(seq_str), self)
            s.activated.connect(cb)
            s.setContext(sc)
        for seq_str, cb in [("Ctrl+Z", self._undo_file_op), ("Ctrl+Y", self._redo_file_op), ("Ctrl+Shift+Z", self._redo_file_op)]:
            s = QShortcut(QKeySequence(seq_str), self)
            s.setContext(sc)
            s.activated.connect(cb)

    def _active_widget(self):
        return self._active_pane().active_widget()

    def _update_view_mode_icon(self):
        icon_map = {
            VIEW_ICON: ("fa5s.th", "Icon View"),
            VIEW_DETAILS: ("fa5s.list", "Details View"),
        }
        icon_name, tip = icon_map.get(self._view_mode, ("fa5s.th", "View Mode"))
        if qta is not None:
            self._view_mode_btn.setIcon(qta.icon(icon_name, color="#d4d4d4"))
            self._view_mode_btn.setIconSize(QSize(*scale_xy(18, 18)))
            self._view_mode_btn.setText("")
        self._view_mode_btn.setToolTip(tip)

    def _toggle_view_mode(self):
        if self._view_mode == VIEW_ICON:
            self._view_mode = VIEW_DETAILS
        else:
            self._view_mode = VIEW_ICON
        self._apply_view_mode()
        self._update_view_mode_icon()
        self._pane_a.refresh()
        if self._pane_b:
            self._pane_b.refresh()
        try:
            self._schedule_save()
        except Exception:
            pass

    def _apply_view_mode(self):
        is_detail = self._view_mode == VIEW_DETAILS
        for pane in (self._pane_a, self._pane_b):
            if not pane:
                continue
            pane._stack.setCurrentIndex(1 if is_detail else 0)
            fl = pane._file_list
            if not is_detail:
                fl.setViewMode(QListWidget.ViewMode.IconMode)
                fl.setIconSize(QSize(self._thumb_size, self._thumb_size))
                fl.setGridSize(QSize(self._thumb_size + scale(20), self._thumb_size + scale(36)))
                fl.setWordWrap(True)
                fl.setSpacing(2)
                fl.setUniformItemSizes(True)
                fl.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._zoom_slider.setVisible(True)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta != 0:
                step = 8 if abs(delta) > 120 else 4
                new_val = self._thumb_size + (step if delta > 0 else -step)
                new_val = max(MIN_THUMB, min(MAX_THUMB, new_val))
                self._thumb_size = new_val
                self._zoom_slider.setValue(new_val)
            event.accept()
        else:
            super().wheelEvent(event)

    def _on_zoom_changed(self, val: int):
        self._thumb_size = val
        if self._view_mode == VIEW_ICON:
            for pane in (self._pane_a, self._pane_b):
                if not pane:
                    continue
                pane._file_list.setIconSize(QSize(val, val))
                pane._file_list.setGridSize(QSize(val + scale(20), val + scale(36)))
        else:
            icon_sz = max(16, min(64, int(val * 0.5)))
            for pane in (self._pane_a, self._pane_b):
                if not pane:
                    continue
                pane._detail_tree.setIconSize(QSize(icon_sz, icon_sz))
        try:
            self._schedule_save()
        except Exception:
            pass

    def _try_plugin_opener(self, path: str) -> bool:
        try:
            from core.foundation.plugin_manager import open_file_with_plugin
            return bool(open_file_with_plugin(self._engine, path))
        except Exception:
            return False

    def _open_path(self, path: str):
        pane = self._active_pane()
        if os.path.isdir(path):
            self._navigate_to(pane, path, record=True)
        else:
            if self._try_plugin_opener(path):
                return
            ext = os.path.splitext(path)[1].lower()
            if ext == ".zpes":
                self._engine.load_scene_async(path)
            elif ext == ".zpep":
                self.file_double_clicked.emit(path)
            elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                self.import_model_requested.emit(path)
            elif ext in (".animclip", ".animcontroller"):
                self.file_double_clicked.emit(path)
            else:
                self.file_double_clicked.emit(path)

    def _open_item_by_path(self, path: str):
        if path:
            self._open_path(path)

    def _go_to_parent(self):
        pane = self._active_pane()
        try:
            cur = os.path.normpath(pane._current_dir)
            parent = os.path.normpath(os.path.dirname(cur))
        except Exception:
            return
        if parent and self._is_inside_root(parent) and parent != cur:
            self._navigate_to(pane, parent, record=True)

    def _go_to_root(self):
        self._navigate_to(self._active_pane(), self._project_root, record=True)

    def _populate_tree(self):
        self._folder_tree.clear()
        root_item = QTreeWidgetItem(self._folder_tree)
        root_item.setText(0, os.path.basename(self._project_root))
        root_item.setData(0, Qt.ItemDataRole.UserRole, self._project_root)
        root_item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
        self._add_subfolders(root_item, self._project_root)
        root_item.setExpanded(True)

    def _add_subfolders(self, parent_item: QTreeWidgetItem, dirpath: str):
        try:
            entries = sorted(os.listdir(dirpath))
        except PermissionError:
            return
        for entry in entries:
            full = os.path.join(dirpath, entry)
            if os.path.isdir(full) and not entry.startswith(".") and entry != "__pycache__":
                item = QTreeWidgetItem(parent_item)
                item.setText(0, entry)
                item.setData(0, Qt.ItemDataRole.UserRole, full)
                item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
                status = self._vcs_status_of(full)
                c = _VCS_COLORS.get(status)
                if c:
                    item.setForeground(0, c)
                self._add_subfolders(item, full)

    def _on_list_item_changed(self, item: QListWidgetItem):
        if self._in_file_undo:
            return
        try:
            if self._is_up_item(item):
                return
        except Exception:
            pass
        old_path = item.data(Qt.ItemDataRole.UserRole)
        if not old_path or not os.path.exists(old_path):
            return
        new_name = item.text()
        if not new_name:
            return
        old_name = os.path.basename(old_path)
        if new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        if os.path.exists(new_path):
            item.blockSignals(True)
            item.setText(old_name)
            item.blockSignals(False)
            return
        try:
            os.rename(old_path, new_path)
            item.setData(Qt.ItemDataRole.UserRole, new_path)
            self._push_file_undo({"kind": "rename", "old": old_path, "new": new_path, "label": "Rename"})
            old_tip = item.toolTip()
            if "\n" in old_tip:
                item.setToolTip(new_name + "\n" + old_tip.split("\n", 1)[1])
            else:
                item.setToolTip(new_name)
        except OSError as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Could not rename:\n{e}")
            item.blockSignals(True)
            item.setText(old_name)
            item.blockSignals(False)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, col: int):
        if col != 0:
            return
        if self._in_file_undo:
            return
        try:
            if self._is_up_item(item):
                return
        except Exception:
            pass
        old_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not old_path or not os.path.exists(old_path):
            return
        new_name = item.text(0)
        if not new_name:
            return
        old_name = os.path.basename(old_path)
        if new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        if os.path.exists(new_path):
            item.blockSignals(True)
            item.setText(0, old_name)
            item.blockSignals(False)
            return
        try:
            os.rename(old_path, new_path)
            item.setData(0, Qt.ItemDataRole.UserRole, new_path)
            self._push_file_undo({"kind": "rename", "old": old_path, "new": new_path, "label": "Rename"})
            if not os.path.isdir(new_path):
                try:
                    item.setText(1, self._active_pane()._type_label(new_name, False))
                except Exception:
                    pass
            new_p = item.data(0, Qt.ItemDataRole.UserRole)
            if new_p and os.path.isfile(new_p):
                self.file_selected.emit(new_p)
        except OSError:
            pass

    def _on_file_single_click(self, item):
        if isinstance(item, QTreeWidgetItem):
            path = item.data(0, Qt.ItemDataRole.UserRole)
        elif hasattr(item, 'data'):
            path = item.data(Qt.ItemDataRole.UserRole)
        else:
            path = None
        if path and os.path.isfile(path):
            self.file_selected.emit(path)

    def _on_file_double_click(self, item):
        if isinstance(item, QTreeWidgetItem):
            path = item.data(0, Qt.ItemDataRole.UserRole)
        else:
            path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        if os.path.isdir(path):
            self._navigate_to(self._active_pane(), path, record=True)
        else:
            if self._try_plugin_opener(path):
                return
            ext = os.path.splitext(path)[1].lower()
            if ext == ".zpes":
                self._engine.load_scene_async(path)
            elif ext == ".zpep":
                self.file_double_clicked.emit(path)
            elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                self.import_model_requested.emit(path)
            elif ext in (".animclip", ".animcontroller"):
                self.file_double_clicked.emit(path)
            elif ext == ".zterr":
                self.file_double_clicked.emit(path)
            else:
                self._open_path_with_default_app(path)

    def _sync_tree_selection(self, dirpath: str):
        root = self._folder_tree.topLevelItem(0)
        if not root:
            return
        stack = [(root, root.data(0, Qt.ItemDataRole.UserRole))]
        while stack:
            item, path = stack.pop()
            if path == dirpath:
                self._folder_tree.setCurrentItem(item)
                self._folder_tree.scrollToItem(item)
                return
            for i in range(item.childCount()):
                child = item.child(i)
                stack.append((child, child.data(0, Qt.ItemDataRole.UserRole)))

    def _refresh(self):
        self._refresh_vcs_status()
        self._populate_tree()
        self._pane_a.refresh()
        if self._pane_b:
            self._pane_b.refresh()

    def _force_refresh_thumbnails(self):
        from editor.resource_picker import _get_thumb_service
        _get_thumb_service().invalidate_thumbnails()
        from editor.thumb_cache import cache_root_for_project
        _get_thumb_service().set_cache_dir(cache_root_for_project(self._project_root))
        self._refresh()

    def _on_folder_selected(self, item, col):
        dirpath = item.data(0, Qt.ItemDataRole.UserRole)
        if dirpath and os.path.isdir(dirpath):
            self._navigate_to(self._active_pane(), dirpath, record=True)

    def _show_file_context_menu(self, pos):
        widget = self.sender()
        item = widget.itemAt(pos) if isinstance(widget, (QTreeWidget, QListWidget)) else None
        if _HAS_SHELL_MENU and show_shell_context_menu is not None:
            if item:
                path = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                        else item.data(Qt.ItemDataRole.UserRole))
            else:
                path = None
            if path:
                paths = self._get_selected_paths() or [path]
            else:
                paths = [self._active_pane()._current_dir]
            if paths:
                try:
                    from PyQt6.QtGui import QCursor
                    cursor_pos = QCursor.pos()
                    if cursor_pos is not None and not cursor_pos.isNull():
                        try:
                            inside = widget.rect().contains(widget.mapFromGlobal(cursor_pos))
                        except Exception:
                            inside = True
                        if inside:
                            menu_x, menu_y = int(cursor_pos.x()), int(cursor_pos.y())
                        else:
                            mapped = widget.mapToGlobal(pos)
                            menu_x, menu_y = int(mapped.x()), int(mapped.y())
                    else:
                        mapped = widget.mapToGlobal(pos)
                        menu_x, menu_y = int(mapped.x()), int(mapped.y())
                    if show_shell_context_menu(
                            paths, int(self.winId()), menu_x, menu_y,
                            self._build_shell_extra_actions(path)):
                        return
                except Exception:
                    pass
        menu = QMenu(self)
        if item:
            path = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                    else item.data(Qt.ItemDataRole.UserRole))
            if not path:
                pass
            elif os.path.isdir(path):
                open_act = QAction("Open", self)
                open_act.triggered.connect(lambda p=path: self._navigate_to(self._active_pane(), p, record=True))
                menu.addAction(open_act)
            else:
                ext = os.path.splitext(path)[1].lower() if path else ""
                if ext == ".zpes":
                    act = QAction("Open Scene", self)
                    act.triggered.connect(lambda: self._engine.load_scene_async(path))
                    menu.addAction(act)
                elif ext == ".zpep":
                    act = QAction("Instantiate Prefab", self)
                    act.triggered.connect(lambda: self._instantiate_prefab(path))
                    menu.addAction(act)
                elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                    act = QAction("Add to Scene", self)
                    act.triggered.connect(lambda p=path: self.import_model_requested.emit(p))
                    menu.addAction(act)
                elif ext in (".py",):
                    act = QAction("Run Script", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext in (".wav", ".mp3", ".ogg", ".flac"):
                    act = QAction("Play", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext in (".png", ".jpg", ".jpeg"):
                    act = QAction("View Image", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext in (".animclip", ".animcontroller"):
                    act = QAction("Open", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext == ".zterr":
                    act = QAction("Open in Terrain Editor", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                menu.addSeparator()
                cut_act = QAction("Cut\tCtrl+X", self)
                cut_act.triggered.connect(lambda: self._cut_selected())
                menu.addAction(cut_act)
                copy_act = QAction("Copy\tCtrl+C", self)
                copy_act.triggered.connect(lambda: self._copy_selected())
                menu.addAction(copy_act)
                paste_act = QAction("Paste\tCtrl+V", self)
                paste_act.triggered.connect(self._paste_clipboard)
                menu.addAction(paste_act)
                menu.addSeparator()
                rename_act = QAction("Rename\tF2", self)
                rename_act.triggered.connect(lambda: self._rename_item(widget, item))
                menu.addAction(rename_act)
                delete_act = QAction("Delete\tDel", self)
                delete_act.triggered.connect(lambda: self._delete_selected())
                menu.addAction(delete_act)
                menu.addSeparator()
                dup_act = QAction("Duplicate\tCtrl+D", self)
                dup_act.triggered.connect(lambda: self._duplicate_selected())
                menu.addAction(dup_act)
                menu.addSeparator()
                reveal_act = QAction("Show in File Manager", self)
                reveal_act.triggered.connect(lambda: self._reveal_file(path))
                menu.addAction(reveal_act)
                menu.addSeparator()
                status = self._vcs_status_of(path) if path else ""
                if status:
                    label = {"untracked": "Untracked", "added": "Added",
                             "modified": "Modified", "deleted": "Deleted",
                             "conflict": "Conflict", "renamed": "Renamed"}
                    info = QAction(f"VCS: {label.get(status, status)}", self)
                    info.setEnabled(False)
                    menu.addAction(info)
                if status in ("untracked", "modified", "deleted"):
                    add_act = QAction("Add to VCS", self)
                    add_act.triggered.connect(lambda p=path: self._git_add_file(p))
                    menu.addAction(add_act)
                if status == "added":
                    unstage_act = QAction("Unstage", self)
                    unstage_act.triggered.connect(lambda p=path: self._git_unstage_file(p))
                    menu.addAction(unstage_act)
                ignore_act = QAction("Ignore in Git", self)
                ignore_act.triggered.connect(lambda p=path: self._git_ignore_file(p))
                menu.addAction(ignore_act)
        menu.addSeparator()
        copy_path_act = QAction("Copy Path", self)
        if item:
            p = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                 else item.data(Qt.ItemDataRole.UserRole))
            copy_path_act.triggered.connect(lambda: self._copy_path(p))
        else:
            copy_path_act.triggered.connect(lambda: self._copy_path(self._active_pane()._current_dir))
        menu.addAction(copy_path_act)
        menu.exec(widget.mapToGlobal(pos))

    def _build_shell_extra_actions(self, path):
        actions = []
        if not path:
            actions.append(("Copy Path", lambda: self._copy_path(self._active_pane()._current_dir)))
            return actions
        if not os.path.isdir(path):
            ext = os.path.splitext(path)[1].lower()
            if ext == ".zpes":
                actions.append(("Open Scene", lambda: self._engine.load_scene_async(path)))
            elif ext == ".zpep":
                actions.append(("Instantiate Prefab", lambda: self._instantiate_prefab(path)))
            elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                actions.append(("Add to Scene", lambda p=path: self.import_model_requested.emit(p)))
            elif ext == ".py":
                actions.append(("Run Script", lambda: self.file_double_clicked.emit(path)))
            elif ext in (".wav", ".mp3", ".ogg", ".flac"):
                actions.append(("Play", lambda: self.file_double_clicked.emit(path)))
            elif ext in (".png", ".jpg", ".jpeg"):
                actions.append(("View Image", lambda: self.file_double_clicked.emit(path)))
            elif ext in (".animclip", ".animcontroller"):
                actions.append(("Open", lambda: self.file_double_clicked.emit(path)))
            elif ext == ".zterr":
                actions.append(("Open in Terrain Editor", lambda: self.file_double_clicked.emit(path)))
            actions.append(("Show in File Manager", lambda p=path: self._reveal_file(p)))
            actions.append(("Copy Path", lambda p=path: self._copy_path(p)))
        else:
            actions.append(("Copy Path", lambda p=path: self._copy_path(p)))
        return actions

    def _norm(self, p: str) -> str:
        try:
            return os.path.normcase(os.path.normpath(os.path.abspath(p)))
        except Exception:
            return os.path.normpath(p)

    def _is_subpath(self, parent: str, child: str) -> bool:
        try:
            pn = self._norm(parent)
            cn = self._norm(child)
            return cn == pn or cn.startswith(pn + os.sep)
        except Exception:
            return False

    def _unique_dst(self, dest_dir: str, name: str) -> str:
        dst = os.path.join(dest_dir, name)
        if not os.path.exists(dst):
            return dst
        base, ext = os.path.splitext(name)
        counter = 1
        while True:
            cand = os.path.join(dest_dir, f"{base} ({counter}){ext}")
            if not os.path.exists(cand):
                return cand
            counter += 1

    def _trash_base(self) -> str:
        try:
            base = os.path.join(tempfile.gettempdir(), "zarin_project_trash", str(os.getpid()))
            os.makedirs(base, exist_ok=True)
            return base
        except Exception:
            base = os.path.join(self._project_root, ".trash_tmp")
            try:
                os.makedirs(base, exist_ok=True)
            except Exception:
                pass
            return base

    def _push_file_undo(self, op: dict) -> None:
        if self._in_file_undo:
            return
        try:
            self._file_undo.append(op)
            if len(self._file_undo) > 100:
                self._file_undo = self._file_undo[-100:]
            self._file_redo.clear()
        except Exception:
            pass
        try:
            kind = op.get("kind")
            if kind == "rename":
                try:
                    self._invalidate_dir_size(op.get("old", ""))
                except Exception:
                    pass
                try:
                    self._invalidate_dir_size(op.get("new", ""))
                except Exception:
                    pass
            elif kind in ("move", "copy"):
                for s, d in op.get("items", []):
                    try:
                        self._invalidate_dir_size(s)
                    except Exception:
                        pass
                    try:
                        self._invalidate_dir_size(d)
                    except Exception:
                        pass
            elif kind == "delete":
                for o, _b in op.get("items", []):
                    try:
                        self._invalidate_dir_size(o)
                    except Exception:
                        pass
            elif kind == "create":
                for p in op.get("paths", []):
                    try:
                        self._invalidate_dir_size(p)
                    except Exception:
                        pass
        except Exception:
            pass

    def _fs_copy(self, src: str, dst: str) -> bool:
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    return False
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return True
        except Exception:
            return False

    def _fs_move(self, src: str, dst: str) -> bool:
        try:
            if self._norm(src) == self._norm(dst):
                return False
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            return True
        except Exception:
            return False

    def _fs_remove(self, path: str) -> bool:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    return True
            return True
        except Exception:
            return False

    def _decide_is_move(self, srcs: list[str], dest_dir: str) -> bool:
        try:
            mods = QApplication.keyboardModifiers()
        except Exception:
            mods = Qt.KeyboardModifier.NoModifier
        if mods & Qt.KeyboardModifier.ControlModifier:
            return False
        if mods & Qt.KeyboardModifier.ShiftModifier:
            return True
        try:
            root = self._norm(self._project_root)
            for s in srcs:
                sn = self._norm(s)
                if not (sn == root or sn.startswith(root + os.sep)):
                    return False
            dn = self._norm(dest_dir)
            if not (dn == root or dn.startswith(root + os.sep)):
                return False
            return True
        except Exception:
            return False

    def _drop_target_dir(self, event, default_dir: str) -> str:
        try:
            pos = event.position().toPoint()
        except Exception:
            try:
                pos = event.pos()
            except Exception:
                return default_dir
        try:
            pane = self._active_pane()
            if pane is None:
                return default_dir
            try:
                it = pane._file_list.itemAt(pos)
                if it is not None:
                    p = it.data(Qt.ItemDataRole.UserRole)
                    if p and os.path.isdir(p) and self._is_inside_root(p):
                        return os.path.normpath(p)
                    return default_dir
            except Exception:
                pass
            try:
                it = pane._detail_tree.itemAt(pos)
                if it is not None:
                    p = it.data(0, Qt.ItemDataRole.UserRole)
                    if p and os.path.isdir(p) and self._is_inside_root(p):
                        return os.path.normpath(p)
                    return default_dir
            except Exception:
                pass
        except Exception:
            pass
        return default_dir

    def _undo_file_op(self):
        try:
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit) and fw.isReadOnly() is False:
                try:
                    if fw.isUndoAvailable():
                        fw.undo()
                        return
                except Exception:
                    return
        except Exception:
            pass
        if not self._file_undo:
            return
        op = self._file_undo.pop()
        self._in_file_undo = True
        try:
            kind = op.get("kind")
            if kind == "rename":
                old = op.get("old")
                new = op.get("new")
                if new and old and os.path.exists(new) and not os.path.exists(old):
                    try:
                        os.rename(new, old)
                    except Exception:
                        pass
            elif kind == "move":
                for src, dst in reversed(op.get("items", [])):
                    if dst and os.path.exists(dst) and not os.path.exists(src):
                        try:
                            os.makedirs(os.path.dirname(src), exist_ok=True)
                            shutil.move(dst, src)
                        except Exception:
                            pass
            elif kind == "copy":
                for src, dst in reversed(op.get("items", [])):
                    if dst and os.path.exists(dst):
                        self._fs_remove(dst)
            elif kind == "delete":
                for orig, backup in op.get("items", []):
                    if backup and os.path.exists(backup) and not os.path.exists(orig):
                        try:
                            os.makedirs(os.path.dirname(orig), exist_ok=True)
                            shutil.move(backup, orig)
                        except Exception:
                            pass
            elif kind == "create":
                paths = op.get("paths", [])
                trash_items = []
                try:
                    trash_dir = os.path.join(self._trash_base(), f"create_{int(time.time()*1000)}")
                    os.makedirs(trash_dir, exist_ok=True)
                except Exception:
                    trash_dir = self._trash_base()
                for p in reversed(paths):
                    if p and os.path.exists(p):
                        b = os.path.join(trash_dir, os.path.basename(p))
                        k = 1
                        bb = b
                        while os.path.exists(bb):
                            base, ext = os.path.splitext(os.path.basename(p))
                            bb = os.path.join(trash_dir, f"{base} ({k}){ext}")
                            k += 1
                        try:
                            shutil.move(p, bb)
                            trash_items.append((p, bb))
                        except Exception:
                            pass
                op["trash_items"] = trash_items
                op["trash_dir"] = trash_dir
            self._file_redo.append(op)
        finally:
            self._in_file_undo = False
        try:
            try:
                k = op.get("kind")
                if k == "rename":
                    self._invalidate_dir_size(op.get("old", ""))
                    self._invalidate_dir_size(op.get("new", ""))
                elif k in ("move", "copy"):
                    for s, d in op.get("items", []):
                        self._invalidate_dir_size(s)
                        self._invalidate_dir_size(d)
                elif k == "delete":
                    for o, _b in op.get("items", []):
                        self._invalidate_dir_size(o)
                elif k == "create":
                    for p in op.get("paths", []):
                        self._invalidate_dir_size(p)
            except Exception:
                pass
            self._refresh()
        except Exception:
            pass

    def _redo_file_op(self):
        try:
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit) and fw.isReadOnly() is False:
                try:
                    if fw.isRedoAvailable():
                        fw.redo()
                        return
                except Exception:
                    return
        except Exception:
            pass
        if not self._file_redo:
            return
        op = self._file_redo.pop()
        self._in_file_undo = True
        try:
            kind = op.get("kind")
            if kind == "rename":
                old = op.get("old")
                new = op.get("new")
                if old and new and os.path.exists(old) and not os.path.exists(new):
                    try:
                        os.rename(old, new)
                    except Exception:
                        pass
            elif kind == "move":
                for src, dst in op.get("items", []):
                    if src and os.path.exists(src) and not os.path.exists(dst):
                        try:
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.move(src, dst)
                        except Exception:
                            pass
                    elif src and os.path.exists(src) and os.path.exists(dst):
                        alt = self._unique_dst(os.path.dirname(dst), os.path.basename(dst))
                        try:
                            shutil.move(src, alt)
                        except Exception:
                            pass
            elif kind == "copy":
                for src, dst in op.get("items", []):
                    if src and os.path.exists(src):
                        target = dst
                        if os.path.exists(target):
                            target = self._unique_dst(os.path.dirname(dst), os.path.basename(dst))
                        self._fs_copy(src, target)
            elif kind == "delete":
                for orig, backup in op.get("items", []):
                    if orig and os.path.exists(orig):
                        try:
                            os.makedirs(os.path.dirname(backup), exist_ok=True)
                            shutil.move(orig, backup)
                        except Exception:
                            pass
            elif kind == "create":
                for p, b in op.get("trash_items", []):
                    if b and os.path.exists(b) and not os.path.exists(p):
                        try:
                            os.makedirs(os.path.dirname(p), exist_ok=True)
                            shutil.move(b, p)
                        except Exception:
                            pass
            self._file_undo.append(op)
        finally:
            self._in_file_undo = False
        try:
            try:
                k = op.get("kind")
                if k == "rename":
                    self._invalidate_dir_size(op.get("old", ""))
                    self._invalidate_dir_size(op.get("new", ""))
                elif k in ("move", "copy"):
                    for s, d in op.get("items", []):
                        self._invalidate_dir_size(s)
                        self._invalidate_dir_size(d)
                elif k == "delete":
                    for o, _b in op.get("items", []):
                        self._invalidate_dir_size(o)
                elif k == "create":
                    for p, _b in op.get("trash_items", []):
                        self._invalidate_dir_size(p)
            except Exception:
                pass
            self._refresh()
        except Exception:
            pass

    def _rename_item(self, widget, item):
        if isinstance(item, QTreeWidgetItem):
            widget.editItem(item, 0)
        else:
            widget.editItem(item)

    def _start_drag_list(self, supported_actions):
        fl = self._active_pane()._file_list
        items = [i for i in fl.selectedItems() if not self._is_up_item(i)]
        if not items:
            return
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in items if i.data(Qt.ItemDataRole.UserRole)]
        paths = [p for p in paths if p]
        if not paths:
            return
        drag = QDrag(fl)
        mime = QMimeData()
        uri_paths = ["file:///" + os.path.abspath(p).replace("\\", "/") for p in paths]
        mime.setUrls([QUrl(u) for u in uri_paths])
        mime.setText("\n".join(paths))
        if len(paths) == 1:
            ext = os.path.splitext(paths[0])[1].lower()
            if ext == ".zpep":
                mime.setData("application/x-zpep", QByteArray(paths[0].encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def _on_file_list_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths:
            return
        base = self._active_pane()._current_dir
        target = self._drop_target_dir(event, base)
        self._move_or_copy_files(paths, dest_dir=target)
        event.acceptProposedAction()

    def _on_detail_tree_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths:
            return
        base = self._active_pane()._current_dir
        target = self._drop_target_dir(event, base)
        self._move_or_copy_files(paths, dest_dir=target)
        event.acceptProposedAction()

    def _on_folder_tree_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths:
            return
        try:
            target_item = self._folder_tree.itemAt(event.position().toPoint())
        except Exception:
            target_item = None
        if target_item:
            target_path = target_item.data(0, Qt.ItemDataRole.UserRole)
        else:
            root = self._folder_tree.topLevelItem(0)
            target_path = root.data(0, Qt.ItemDataRole.UserRole) if root else self._project_root
        self._move_or_copy_files(paths, dest_dir=target_path)
        event.acceptProposedAction()

    def _on_entity_drop(self, event):
        if not event.mimeData().hasFormat(_ENTITY_MIME):
            return
        raw = bytes(event.mimeData().data(_ENTITY_MIME)).decode("utf-8")
        eids = [x.strip() for x in raw.split(",") if x.strip()]
        if not eids or not self._engine.scene:
            return
        from core.ecs.prefab import Prefab
        entity = self._engine.scene.get_entity(eids[0])
        if not entity:
            return
        prefab = Prefab(entity.name)
        prefab.capture([entity])
        ext = ".zpep"
        name = entity.name.replace(" ", "_").replace("/", "_")
        dest_dir = self._active_pane()._current_dir
        path = os.path.join(dest_dir, f"{name}{ext}")
        counter = 1
        while os.path.exists(path):
            path = os.path.join(dest_dir, f"{name}_{counter}{ext}")
            counter += 1
        prefab.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create prefab"})
        self._refresh()
        event.acceptProposedAction()

    def _extract_drop_paths(self, event):
        if event.mimeData().hasUrls():
            out = []
            for u in event.mimeData().urls():
                try:
                    lf = u.toLocalFile()
                except Exception:
                    continue
                if lf:
                    out.append(os.path.normpath(lf))
            if out:
                return out
        if event.mimeData().hasText():
            paths = []
            for line in event.mimeData().text().splitlines():
                line = line.strip().strip('"')
                if line:
                    paths.append(os.path.normpath(line))
            return paths
        return []

    def _move_or_copy_files(self, paths, dest_dir=None, force_move=None):
        if not dest_dir:
            dest_dir = self._active_pane()._current_dir
        try:
            dest_dir = os.path.normpath(os.path.abspath(dest_dir))
        except Exception:
            return
        if not os.path.isdir(dest_dir):
            try:
                os.makedirs(dest_dir, exist_ok=True)
            except Exception:
                return
        clean = []
        for s in paths:
            if not s:
                continue
            try:
                sn = os.path.normpath(os.path.abspath(s))
            except Exception:
                continue
            if not os.path.exists(sn):
                continue
            if sn not in clean:
                clean.append(sn)
        if not clean:
            return
        if force_move is None:
            is_move = self._decide_is_move(clean, dest_dir)
        else:
            is_move = bool(force_move)
        moved = []
        copied = []
        errors = []
        for src in clean:
            name = os.path.basename(src)
            src_n = self._norm(src)
            dest_n = self._norm(dest_dir)
            if src_n == dest_n:
                continue
            if dest_n.startswith(src_n + os.sep):
                errors.append(f"{name}: target inside itself")
                continue
            same_dir = self._norm(os.path.dirname(src)) == dest_n
            if same_dir and is_move:
                continue
            dst = os.path.join(dest_dir, name)
            if self._norm(src) == self._norm(dst):
                continue
            if self._norm(dst).startswith(src_n + os.sep):
                errors.append(f"{name}: target inside itself")
                continue
            if os.path.exists(dst):
                if is_move:
                    try:
                        if os.path.samefile(src, dst):
                            continue
                    except Exception:
                        pass
                dst = self._unique_dst(dest_dir, name)
            try:
                if is_move:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)
                    moved.append((src, dst))
                else:
                    ok = self._fs_copy(src, dst)
                    if ok:
                        copied.append((src, dst))
                    else:
                        errors.append(f"{name}: copy failed")
            except Exception as e:
                errors.append(f"{name}: {e}")
        if moved:
            self._push_file_undo({"kind": "move", "items": moved, "label": "Move"})
        if copied:
            self._push_file_undo({"kind": "copy", "items": copied, "label": "Copy"})
        try:
            for s, d in moved + copied:
                try:
                    self._invalidate_dir_size(s)
                except Exception:
                    pass
                try:
                    self._invalidate_dir_size(d)
                except Exception:
                    pass
            try:
                self._invalidate_dir_size(dest_dir)
            except Exception:
                pass
        except Exception:
            pass
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Import Errors", "\n".join(errors))

    def _open_path_with_default_app(self, path):
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _start_drag_detail(self, supported_actions):
        dt = self._active_pane()._detail_tree
        items = [i for i in dt.selectedItems() if not self._is_up_item(i)]
        if not items:
            return
        paths = [i.data(0, Qt.ItemDataRole.UserRole) for i in items]
        paths = [p for p in paths if p]
        if not paths:
            return
        drag = QDrag(dt)
        mime = QMimeData()
        uri_paths = ["file:///" + os.path.abspath(p).replace("\\", "/") for p in paths]
        mime.setUrls([QUrl(u) for u in uri_paths])
        mime.setText("\n".join(paths))
        ext = os.path.splitext(paths[0])[1].lower()
        if len(paths) == 1 and ext == ".zpep":
            mime.setData("application/x-zpep", QByteArray(paths[0].encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def _instantiate_prefab(self, path: str):
        if not self._engine.scene:
            return
        from core.ecs.prefab import Prefab
        from core.engine.engine import Engine
        pref = Prefab.load(path)
        if pref:
            e = pref.instantiate(self._engine.scene, Engine.instance()._component_registry)
            if e:
                self._engine._emit_event("entity_created", e)

    def _reveal_file(self, path: str):
        import subprocess, sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def _copy_path(self, path: str):
        QGuiApplication.clipboard().setText(path)

    def _is_up_item(self, item) -> bool:
        try:
            if isinstance(item, QTreeWidgetItem):
                if item.data(0, Qt.ItemDataRole.UserRole + 1) == "up":
                    return True
                if item.text(0) == "..":
                    return True
            else:
                if item.data(Qt.ItemDataRole.UserRole + 1) == "up":
                    return True
                if item.text() == "..":
                    return True
        except Exception:
            pass
        return False

    def _get_selected_paths(self):
        widget = self._active_widget()
        paths = []
        for item in widget.selectedItems():
            try:
                if self._is_up_item(item):
                    continue
            except Exception:
                pass
            d = item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem) else item.data(Qt.ItemDataRole.UserRole)
            if d:
                paths.append(d)
        return paths

    def _copy_selected(self):
        global _file_clipboard, _clipboard_is_cut
        paths = self._get_selected_paths()
        if paths:
            _file_clipboard = list(paths)
            _clipboard_is_cut = False

    def _cut_selected(self):
        global _file_clipboard, _clipboard_is_cut
        paths = self._get_selected_paths()
        if paths:
            _file_clipboard = list(paths)
            _clipboard_is_cut = True

    def _paste_clipboard(self):
        global _file_clipboard, _clipboard_is_cut
        if not _file_clipboard:
            return
        target = self._active_pane()._current_dir
        try:
            target = os.path.normpath(os.path.abspath(target))
        except Exception:
            return
        moved = []
        copied = []
        errors = []
        for src in list(_file_clipboard):
            if not src or not os.path.exists(src):
                continue
            try:
                src_n = os.path.normpath(os.path.abspath(src))
            except Exception:
                continue
            name = os.path.basename(src)
            dst = os.path.join(target, name)
            if self._norm(src_n) == self._norm(dst):
                if _clipboard_is_cut:
                    continue
                dst = self._unique_dst(target, name)
            elif os.path.exists(dst):
                try:
                    if _clipboard_is_cut and os.path.samefile(src_n, dst):
                        continue
                except Exception:
                    pass
                dst = self._unique_dst(target, name)
            if self._norm(dst).startswith(self._norm(src_n) + os.sep):
                errors.append(f"{name}: target inside itself")
                continue
            try:
                if _clipboard_is_cut:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src_n, dst)
                    moved.append((src_n, dst))
                else:
                    ok = self._fs_copy(src_n, dst)
                    if ok:
                        copied.append((src_n, dst))
                    else:
                        errors.append(f"{name}: copy failed")
            except Exception as e:
                errors.append(f"{name}: {e}")
        if _clipboard_is_cut:
            _file_clipboard = []
            _clipboard_is_cut = False
        if moved:
            self._push_file_undo({"kind": "move", "items": moved, "label": "Paste move"})
        if copied:
            self._push_file_undo({"kind": "copy", "items": copied, "label": "Paste copy"})
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Paste Errors", "\n".join(errors))

    def _duplicate_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        copied = []
        errors = []
        for src in paths:
            if not os.path.exists(src):
                continue
            name = os.path.basename(src)
            dst = self._unique_dst(os.path.dirname(src), name)
            if self._norm(dst).startswith(self._norm(src) + os.sep):
                continue
            try:
                ok = self._fs_copy(src, dst)
                if ok:
                    copied.append((src, dst))
                else:
                    errors.append(f"{name}: copy failed")
            except Exception as e:
                errors.append(f"{name}: {e}")
        if copied:
            self._push_file_undo({"kind": "copy", "items": copied, "label": "Duplicate"})
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Duplicate Errors", "\n".join(errors))

    def _delete_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        from PyQt6.QtWidgets import QMessageBox
        names = "\n".join(os.path.basename(p) for p in paths[:10])
        if len(paths) > 10:
            names += f"\n... and {len(paths) - 10} more"
        reply = QMessageBox.question(self, "Delete",
            f"Delete {len(paths)} item(s)?\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                trash_dir = os.path.join(self._trash_base(), f"del_{int(time.time()*1000)}")
                os.makedirs(trash_dir, exist_ok=True)
            except Exception:
                trash_dir = self._trash_base()
            items = []
            errors = []
            for p in paths:
                if not os.path.exists(p):
                    continue
                b = os.path.join(trash_dir, os.path.basename(p))
                k = 1
                bb = b
                while os.path.exists(bb):
                    base, ext = os.path.splitext(os.path.basename(p))
                    bb = os.path.join(trash_dir, f"{base} ({k}){ext}")
                    k += 1
                try:
                    shutil.move(p, bb)
                    items.append((p, bb))
                except Exception as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
            if items:
                self._push_file_undo({"kind": "delete", "items": items, "label": "Delete"})
            self._refresh()
            if errors:
                QMessageBox.warning(self, "Delete Errors", "\n".join(errors))

    def _current_dir(self):
        return self._active_pane()._current_dir

    def _create_new_folder(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Create Folder", "Folder name:")
        if ok and name:
            try:
                target = os.path.join(self._current_dir(), name)
                os.makedirs(target, exist_ok=True)
                self._push_file_undo({"kind": "create", "paths": [target], "label": "Create folder"})
                self._refresh()
            except OSError as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")

    def _create_new_scene(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Scene", self._current_dir(), "Scenes (*.zpes)")
        if not path:
            return
        if not path.endswith(".zpes"):
            path += ".zpes"
        import json
        data = {"name": os.path.splitext(os.path.basename(path))[0], "entities": {}}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create scene"})
        self._refresh()

    def _create_new_material(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Material", self._current_dir(), "Materials (*.mat)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext != ".mat":
            path += ".mat"
        from core.assets.material import Material
        mat = Material(os.path.splitext(os.path.basename(path))[0])
        mat.save(path, self._engine.project_root)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create material"})
        self._refresh()

    def _create_new_physic_material(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Physic Material", self._current_dir(), "Physics Materials (*.zphysmat)")
        if not path:
            return
        if not path.endswith(".zphysmat"):
            path += ".zphysmat"
        from core.assets.physics_material import PhysicsMaterial
        mat = PhysicsMaterial(os.path.splitext(os.path.basename(path))[0])
        mat.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create material"})
        self._refresh()

    def _create_new_animclip(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Animation Clip", self._current_dir(), "Animation Clips (*.animclip)")
        if not path:
            return
        if not path.endswith(".animclip"):
            path += ".animclip"
        from core.components.animation.animation_clip import AnimationClip
        clip = AnimationClip(os.path.splitext(os.path.basename(path))[0])
        clip.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create clip"})
        self._refresh()

    def _create_new_animcontroller(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Animator Controller", self._current_dir(), "Animator Controllers (*.animcontroller)")
        if not path:
            return
        if not path.endswith(".animcontroller"):
            path += ".animcontroller"
        from core.components.animation.animator_controller import AnimatorController
        ctrl = AnimatorController(os.path.splitext(os.path.basename(path))[0])
        ctrl.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create controller"})
        self._refresh()

    def _create_new_script(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Script", self._current_dir(), "Python Scripts (*.py)")
        if not path:
            return
        if not path.endswith(".py"):
            path += ".py"
        template = '''from __future__ import annotations
from core.ecs.ecs import Component, ComponentRegistry
@ComponentRegistry.register
class NewScript(Component):
    def __init__(self):
        super().__init__()
        self.my_var: float = 0.0
    def update(self, dt: float):
        pass
'''
        with open(path, "w") as f:
            f.write(template)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create script"})
        self._refresh()

    def _resolve_resource_path(self, path: str) -> str:
        if not path:
            return ""
        if os.path.exists(path) or os.path.isabs(path):
            return path
        root = self._engine.project_root if self._engine else None
        if root:
            cand = os.path.normpath(os.path.join(root, path))
            if os.path.exists(cand):
                return cand
        return path

    def open_resource(self, path: str):
        path = self._resolve_resource_path(path)
        if os.path.isdir(path):
            return
        if self._try_plugin_opener(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".zpes":
            self._engine.load_scene_async(path)
        elif ext == ".zpep":
            self.file_double_clicked.emit(path)
        elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
            self.import_model_requested.emit(path)
        elif ext in (".animclip", ".animcontroller"):
            self.file_double_clicked.emit(path)
        elif ext == ".zterr":
            self.file_double_clicked.emit(path)
        else:
            self._open_path_with_default_app(path)

    def reveal_resource(self, path: str):
        norm = os.path.normpath(self._resolve_resource_path(path))
        if not os.path.exists(norm):
            return
        target = os.path.dirname(norm) if os.path.isfile(norm) else norm
        if not self._is_inside_root(target):
            return
        pane = self._active_pane()
        self._navigate_to(pane, target, record=True)
        item = self._find_item_by_path(norm)
        if item:
            pane.active_widget().setCurrentItem(item)
            pane.active_widget().scrollToItem(item)
            self._flash_item(item)

    def flash_resource(self, path: str):
        norm = os.path.normpath(self._resolve_resource_path(path))
        if not os.path.exists(norm):
            return
        target = os.path.dirname(norm) if os.path.isfile(norm) else norm
        if not self._is_inside_root(target):
            return
        pane = self._active_pane()
        cur = os.path.normpath(pane._current_dir)
        if cur != os.path.normpath(target):
            self._navigate_to(pane, target, record=True)
        item = self._find_item_by_path(norm)
        if item:
            pane.active_widget().scrollToItem(item)
            self._flash_item(item)

    def _find_item_by_path(self, norm):
        pane = self._active_pane()
        if self._view_mode == VIEW_DETAILS:
            tree = pane._detail_tree
            for i in range(tree.topLevelItemCount()):
                it = tree.topLevelItem(i)
                if it and it.data(0, Qt.ItemDataRole.UserRole) == norm:
                    return it
        else:
            lst = pane._file_list
            for i in range(lst.count()):
                it = lst.item(i)
                if it and it.data(Qt.ItemDataRole.UserRole) == norm:
                    return it
        return None

    @staticmethod
    def _flash_item(item):
        try:
            if isinstance(item, QTreeWidgetItem):
                tree = item.treeWidget()
                if not tree:
                    return
                _flash_overlay(tree.viewport(), tree.visualItemRect(item))
            else:
                lst = item.listWidget()
                if not lst:
                    return
                _flash_overlay(lst.viewport(), lst.visualItemRect(item))
        except RuntimeError:
            pass

    def set_project_root(self, path: str):
        self._project_root = os.path.abspath(path)
        try:
            self._dir_size_cache.clear()
            self._dir_size_gen += 1
        except Exception:
            pass
        a_dir = self._project_root
        b_dir = self._project_root
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            try:
                a_dir = self._abs_from_saved(cfg.get("project.pane_a_dir", self._project_root))
            except Exception:
                pass
            try:
                b_dir = self._abs_from_saved(cfg.get("project.pane_b_dir", a_dir))
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._pane_a._hist_back = []
            self._pane_a._hist_fwd = []
            self._pane_a._current_dir = a_dir
            self._pane_a.populate_files(a_dir)
        except Exception:
            pass
        if getattr(self, "_pane_b", None):
            try:
                self._pane_b._hist_back = []
                self._pane_b._hist_fwd = []
                self._pane_b._current_dir = b_dir
                self._pane_b.populate_files(b_dir)
            except Exception:
                pass
        try:
            self._set_active_pane(self._pane_a)
        except Exception:
            pass
        self._refresh_vcs_status()
        self._populate_tree()
        try:
            self._update_nav_buttons()
        except Exception:
            pass
        try:
            self._apply_sort_indicators()
        except Exception:
            pass
