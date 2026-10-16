# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PySide6.QtCore import QObject, QTimer, QEvent, Qt


class _UndoFilter(QObject):

    def __init__(self, mw):
        super().__init__()
        self._mw = mw
        self._ctrl_held = False
        self._z_handled = False
        self._y_handled = False
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._poll)
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(60)
        self._sync_timer.timeout.connect(self._do_sync)
        from core.foundation.cmd import get_history
        self._get_history = get_history
        from editor.main_window.handlersp import sync_after_undo
        self._sync_fn = sync_after_undo

    def _do_sync(self):
        if self._mw:
            self._sync_fn(self._mw)

    def _schedule_sync(self):
        self._sync_timer.start()

    def _is_key_down(self, vk):
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            return False

    def _project_or_text_has_focus(self) -> bool:
        try:
            from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit
            fw = QApplication.focusWidget()
            if fw is None:
                return False
            if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
                return True
            cur = fw
            while cur is not None:
                try:
                    if cur.__class__.__name__ == "ProjectPanel":
                        return True
                    if cur.__class__.__name__ in ("FileListWidget", "FileDetailWidget", "FolderTreeWidget", "_FilePane", "_AddressBreadcrumb"):
                        return True
                except Exception:
                    pass
                try:
                    cur = cur.parent()
                except Exception:
                    break
        except Exception:
            pass
        return False

    def _poll(self):
        if not self._ctrl_held:
            self._timer.stop()
            return
        if self._project_or_text_has_focus():
            return
        z_down = self._is_key_down(0x5A)
        y_down = self._is_key_down(0x59)
        handled = False
        if z_down and not self._z_handled:
            self._z_handled = True
            handled = True
            self._get_history().undo()
            self._schedule_sync()
        elif not z_down:
            self._z_handled = False
        if not handled and y_down and not self._y_handled:
            self._y_handled = True
            self._get_history().redo()
            self._schedule_sync()
        elif not y_down:
            self._y_handled = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            ke = event
            key = ke.key()
            if key == Qt.Key.Key_Control:
                self._ctrl_held = True
                self._z_handled = False
                self._y_handled = False
                self._timer.start()
                return False
            if key == Qt.Key.Key_Z and self._ctrl_held:
                if self._project_or_text_has_focus():
                    return False
                self._z_handled = True
                self._get_history().undo()
                self._schedule_sync()
                return True
            if key == Qt.Key.Key_Y and self._ctrl_held:
                if self._project_or_text_has_focus():
                    return False
                self._y_handled = True
                self._get_history().redo()
                self._schedule_sync()
                return True
        elif event.type() == QEvent.Type.KeyRelease:
            if event.key() == Qt.Key.Key_Control:
                self._ctrl_held = False
                self._z_handled = False
                self._y_handled = False
                self._timer.stop()
        return False


__all__ = ["_UndoFilter"]
