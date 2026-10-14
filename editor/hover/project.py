# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer, QPoint
from PyQt6.QtGui import QCursor
from editor.hover.preview import _get_popup
from editor.hover.preview import _hover_delay
class _ProjectHover(QObject):
    def __init__(self, view, mode: str):
        super().__init__(view)
        self._view = view
        self._mode = mode
        self._path = None
        self._pos = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_hover_delay())
        self._timer.timeout.connect(self._show)
        try:
            view.setMouseTracking(True)
            view.viewport().setMouseTracking(True)
            view.installEventFilter(self)
            view.viewport().installEventFilter(self)
        except Exception:
            pass
    def eventFilter(self, obj, event):
        try:
            t = event.type()
            if t == QEvent.Type.MouseMove:
                vp = None
                pos = None
                try:
                    if obj is self._view.viewport():
                        pos = event.pos()
                        vp = obj
                    elif obj is self._view:
                        try:
                            gp = QCursor.pos()
                            pos = self._view.viewport().mapFromGlobal(gp)
                            vp = self._view.viewport()
                        except Exception:
                            return False
                    else:
                        return False
                except Exception:
                    return False
                self._on_move(vp, pos)
            elif t in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.Close, QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel, QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.DragLeave, QEvent.Type.Drop):
                self._hide()
        except Exception:
            pass
        return False
    def _path_at(self, pos):
        try:
            if self._mode == "list":
                item = self._view.itemAt(pos)
                if item is None:
                    return None
                return item.data(Qt.ItemDataRole.UserRole)
            else:
                item = self._view.itemAt(pos)
                if item is None:
                    return None
                return item.data(0, Qt.ItemDataRole.UserRole)
        except Exception:
            return None
    def _on_move(self, vp, pos):
        try:
            path = self._path_at(pos)
            if not path:
                self._hide()
                return
            try:
                gp = vp.mapToGlobal(pos)
            except Exception:
                gp = QCursor.pos()
            if path != self._path:
                self._path = path
                self._pos = gp
                self._timer.stop()
                self._timer.setInterval(_hover_delay())
                self._timer.start()
            else:
                self._pos = gp
        except Exception:
            pass
    def _show(self):
        try:
            if not self._path:
                return
            try:
                still = self._view.underMouse()
            except Exception:
                still = True
            if not still:
                return
            popup = _get_popup()
            if popup is None:
                return
            pos = self._pos if self._pos is not None else QCursor.pos()
            popup.show_resource(self._path, pos)
        except Exception:
            pass
    def _hide(self):
        try:
            self._path = None
            self._pos = None
            self._timer.stop()
            popup = _get_popup()
            if popup is not None and popup.isVisible() and popup._kind == "resource":
                popup.hide_animated()
        except Exception:
            pass
def attach_project_list_hover(view):
    try:
        filt = _ProjectHover(view, "list")
        try:
            existing = getattr(view, "_hover_preview_filters", None)
            if existing is None:
                view._hover_preview_filters = [filt]
            else:
                existing.append(filt)
        except Exception:
            view._hover_preview_filter = filt
        return filt
    except Exception:
        return None
def attach_project_tree_hover(view):
    try:
        filt = _ProjectHover(view, "tree")
        try:
            existing = getattr(view, "_hover_preview_filters", None)
            if existing is None:
                view._hover_preview_filters = [filt]
            else:
                existing.append(filt)
        except Exception:
            view._hover_preview_filter = filt
        return filt
    except Exception:
        return None
