# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import time
from typing import Optional, TYPE_CHECKING
import editor.icons as qta
from PySide6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                              QTreeWidget, QTreeWidgetItem, QPushButton,
                              QMenu, QLineEdit, QLabel, QInputDialog, QAbstractItemView,
                              QStyledItemDelegate, QApplication, QHeaderView)
from PySide6.QtCore import Qt, Signal, QTimer, QMimeData
from PySide6.QtGui import QKeySequence, QAction, QDrag, QColor, QKeyEvent, QBrush, QPixmap, QIcon
from editor.inspector.helpersp import _flash_overlay
if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.engine.eng import Engine
_ENTITY_MIME = "application/x-zpe-entity"
_COMPONENT_MIME = "application/x-zpe-component"

import os
from core.config.editor_scale import scale, scale_xy

_ICON_PIXMAP_CACHE: dict = {}
_ICON_PATH_CACHE: dict = {}
_ICON_QICON_CACHE: dict = {}
def _cached_icon(cls) -> QIcon | None:
    key = (getattr(cls, "__name__", ""), getattr(cls, "_icon", None))
    hit = _ICON_QICON_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        pix = _get_component_icon_pixmap(cls, 16)
    except Exception:
        return None
    try:
        icon = QIcon(pix)
    except Exception:
        return None
    _ICON_QICON_CACHE[key] = icon
    return icon
def _get_component_icon_pixmap(cls, size: int = 16) -> QPixmap:
    cache_key = (getattr(cls, "__name__", ""), getattr(cls, "_icon", None), int(size))
    cached = _ICON_PIXMAP_CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached
    resolved = _ICON_PATH_CACHE.get(cache_key)
    if resolved is None and cache_key not in _ICON_PATH_CACHE:
        icon_name = getattr(cls, "_icon", None)
        found = ""
        if icon_name:
            icons_dir = os.path.join(os.path.dirname(__file__), "..", "..", "core", "components", "icons")
            icon_path = os.path.join(icons_dir, icon_name)
            try:
                if os.path.exists(icon_path):
                    found = icon_path
            except Exception:
                found = ""
        if not found:
            gizmo_dir = os.path.join(os.path.dirname(__file__), "..", "gizmo_icons")
            alt = os.path.join(gizmo_dir, f"{getattr(cls, '__name__', '')}.png")
            try:
                if os.path.exists(alt):
                    found = alt
            except Exception:
                found = ""
        _ICON_PATH_CACHE[cache_key] = found
        resolved = found
    if resolved:
        try:
            pix = QPixmap(resolved).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if not pix.isNull():
                _ICON_PIXMAP_CACHE[cache_key] = pix
                return pix
        except Exception:
            pass
    r, g, b = getattr(cls, "_gizmo_icon_color", (140, 60, 200))
    label = getattr(cls, "_gizmo_icon_label", "?")
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    from PySide6.QtGui import QPainter, QColor as QC, QFont as QF, QBrush as QB
    from PySide6.QtCore import QRect
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QB(QC(r, g, b)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, 3, 3)
    if label:
        p.setPen(QC(255, 255, 255))
        f = QF("Segoe UI", size // 2, QF.Weight.Bold)
        p.setFont(f)
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, label[0].upper())
    p.end()
    _ICON_PIXMAP_CACHE[cache_key] = pix
    return pix
class HierarchyTree(QTreeWidget):
    entity_reparented = Signal(object, object)
    delete_requested = Signal(list)
    copy_requested = Signal()
    paste_requested = Signal()
    component_drop_requested = Signal(object, object, object)
    def __init__(self, panel: HierarchyPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setDragDropMode(QTreeWidget.DragDropMode.DragDrop)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._press_item = None
        self._press_pos = None
        self._drag_started = False
    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
    def mimeTypes(self):
        return [_ENTITY_MIME]
    def mimeData(self, items):
        mime = QMimeData()
        eids = []
        for item in items:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            if eid:
                eids.append(eid)
        if eids:
            mime.setData(_ENTITY_MIME, ",".join(eids).encode("utf-8"))
        return mime
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._press_item = self.itemAt(self._press_pos)
            if self._press_item:
                self._drag_started = False
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_item and self._press_pos:
            delta = event.position().toPoint() - self._press_pos
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._drag_started = True
                items = self.selectedItems()
                if not items:
                    items = [self._press_item]
                elif self._press_item not in items:
                    items.append(self._press_item)
                mime = self.mimeData(items)
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
                self._press_item = None
                self._press_pos = None
                return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_started:
            self._drag_started = False
            self._press_item = None
            self._press_pos = None
            return
        super().mouseReleaseEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            event.acceptProposedAction()
            return
        if not event.mimeData().hasFormat(_ENTITY_MIME):
            event.ignore()
            return
        target_item = self.itemAt(event.position().toPoint())
        dragged_ids = bytes(event.mimeData().data(_ENTITY_MIME)).decode("utf-8").split(",")
        if target_item is not None:
            target_eid = target_item.data(0, Qt.ItemDataRole.UserRole)
            if not target_eid or not dragged_ids:
                event.ignore()
                return
            if target_eid in dragged_ids:
                event.ignore()
                return
            for did in dragged_ids:
                dragged_item = self._find_item_by_id(did)
                if dragged_item and self._is_descendant(target_item, dragged_item):
                    event.ignore()
                    return
        event.acceptProposedAction()
    def _find_item_by_id(self, eid: str):
        return self._find_recursive(eid, self.invisibleRootItem())
    def _find_recursive(self, eid: str, parent_item):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == eid:
                return child
            found = self._find_recursive(eid, child)
            if found:
                return found
        return None
    def _is_descendant(self, ancestor_item, check_item):
        if not check_item or not ancestor_item:
            return False
        parent = check_item.parent()
        while parent:
            if parent == ancestor_item:
                return True
            parent = parent.parent()
        return False
    def dropEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            raw = bytes(event.mimeData().data(_COMPONENT_MIME)).decode("utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                event.ignore()
                return
            target_item = self.itemAt(event.position().toPoint())
            if target_item is not None:
                target_eid = target_item.data(0, Qt.ItemDataRole.UserRole)
                if target_eid:
                    is_copy = event.proposedAction() == Qt.DropAction.CopyAction
                    self.component_drop_requested.emit(target_eid, data, is_copy)
                    event.acceptProposedAction()
                    return
            event.ignore()
            return
        if not event.mimeData().hasFormat(_ENTITY_MIME):
            event.ignore()
            return
        target_item = self.itemAt(event.position().toPoint())
        dragged_ids = bytes(event.mimeData().data(_ENTITY_MIME)).decode("utf-8").split(",")
        if not dragged_ids:
            event.ignore()
            return
        if target_item is None:
            for did in dragged_ids:
                self.entity_reparented.emit(did, None)
            event.acceptProposedAction()
            return
        target_eid = target_item.data(0, Qt.ItemDataRole.UserRole)
        if not target_eid:
            event.ignore()
            return
        for did in dragged_ids:
            if did == target_eid:
                event.ignore()
                return
        pos = self.dropIndicatorPosition()
        if pos in (QAbstractItemView.DropIndicatorPosition.AboveItem, QAbstractItemView.DropIndicatorPosition.BelowItem):
            target_parent = target_item.parent()
            if target_parent:
                parent_eid = target_parent.data(0, Qt.ItemDataRole.UserRole)
            else:
                parent_eid = None
            for did in dragged_ids:
                self.entity_reparented.emit(did, parent_eid)
        else:
            for did in dragged_ids:
                self.entity_reparented.emit(did, target_eid)
        event.acceptProposedAction()
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mods = event.modifiers()
        nvk = event.nativeVirtualKey()
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_requested.emit()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_requested.emit()
            event.accept()
            return
        if mods & Qt.KeyboardModifier.ControlModifier and mods & Qt.KeyboardModifier.ShiftModifier and key == Qt.Key.Key_A:
            items = self.selectedItems()
            if items:
                eids = []
                for item in items:
                    eid = item.data(0, Qt.ItemDataRole.UserRole)
                    if eid:
                        eids.append(eid)
                if eids:
                    self._panel._toggle_active_by_ids(eids)
            event.accept()
            return
        if key == Qt.Key.Key_F2:
            items = self.selectedItems()
            if items:
                self.editItem(items[0], 0)
        elif key == Qt.Key.Key_F:
            try:
                self._panel._frame_selected()
            except Exception:
                pass
        elif key == Qt.Key.Key_Delete:
            items = self.selectedItems()
            eids = []
            for item in items:
                eid = item.data(0, Qt.ItemDataRole.UserRole)
                if eid:
                    eids.append(eid)
            if eids:
                self.delete_requested.emit(eids)
        else:
            super().keyPressEvent(event)
