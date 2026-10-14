# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, datetime
from PyQt6.QtWidgets import QToolButton, QLineEdit, QWidget, QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QAbstractItemView, QFileIconProvider, QStyledItemDelegate
from PyQt6.QtCore import Qt, QSize, QFileInfo, pyqtSignal
from PyQt6.QtGui import QIcon, QWheelEvent, QKeyEvent, QColor, QPainter, QPen, QBrush, QFontMetrics
from core.config.editor_scale import scale, scale_xy
from editor.constants import MIN_THUMB, MAX_THUMB, VIEW_ICON, VIEW_LIST, VIEW_DETAILS
from editor.picker import _get_thumbnail, _format_size, _thumb_resolution
from editor.hover import attach_project_list_hover, attach_project_tree_hover
from .icons import _ENTITY_MIME, qta
from typing import Optional, TYPE_CHECKING
class _NavButton(QToolButton):
    def __init__(self, icon_name="", tooltip="", parent=None):
        super().__init__(parent)
        if icon_name and qta is not None:
            self.setIcon(qta.icon(icon_name, color="#d4d4d4"))
            self.setIconSize(QSize(*scale_xy(18, 18)))
        self.setToolTip(tooltip)
        self.setFixedSize(scale(34), scale(32))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f" QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 3px; padding: 0; }} QToolButton:hover {{ }} QToolButton:pressed {{ background: #444; }} QToolButton:disabled {{ color: #3a3a3a; }} ")
class _AddressBar(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet(f" QLineEdit {{ border-radius: 2px; padding: 2px 8px; font-size: 12px; min-height: 22px; }} QLineEdit:focus {{ }} ")
class _SearchBar(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Search...")
        self.setClearButtonEnabled(True)
        self.setMaximumWidth(scale(200))
        self.setStyleSheet(f" QLineEdit {{ border-radius: 2px; padding: 2px 24px 2px 8px; font-size: 11px; min-height: 22px; }} QLineEdit:focus {{ }} QLineEdit::placeholder {{ }} ")
class _GroupHeader(QWidget):
    def __init__(self, text, count=0, parent=None):
        super().__init__(parent)
        self._text = text
        self._count = count
        self.setFixedHeight(scale(26))
        self.setStyleSheet(f" ")
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
        self.setStyleSheet(f" QTreeWidget {{ border: none; outline: none; font-size: 12px; padding: 2px; }} QTreeWidget::item {{ padding: 1px 4px; border: 1px solid transparent; border-radius: 2px; min-height: 19px; }} QTreeWidget::item:selected {{ }} QTreeWidget::item:hover:!selected {{ }} QTreeWidget::branch {{ background: transparent; }} QScrollBar:vertical {{ background: transparent; width: 8px; }} QScrollBar::handle:vertical {{ min-height: 30px; border-radius: 4px; margin: 2px; }} QScrollBar::handle:vertical:hover {{ background: #666; }} QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }} ")
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
        self.setStyleSheet(f" QLineEdit {{ background: transparent; border: 1px solid transparent; border-radius: 2px; padding: 2px 6px; font-size: 12px; min-height: 20px; }} QLineEdit:focus {{ padding: 2px 6px; }} ")
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
        self.setStyleSheet(f" QLineEdit {{ border-radius: 2px; padding: 2px 6px; font-size: 12px; min-height: 20px; }} ")
    def _exit_edit_mode(self):
        self._editing = False
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pane.rebuild_breadcrumb()
        try:
            self._pane.set_active(self._pane._active)
        except Exception:
            self.setStyleSheet(f" QLineEdit {{ background: transparent; border: 1px solid transparent; border-radius: 2px; padding: 2px 6px; font-size: 12px; min-height: 20px; }} QLineEdit:focus {{ padding: 2px 6px; }} ")
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
def _populate_detail_tree_impl(self, dirpath: str, entries: list[str], filter_text: str):
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
