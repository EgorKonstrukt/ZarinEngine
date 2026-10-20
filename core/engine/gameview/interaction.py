# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QKeyEvent, QMouseEvent, QCursor, QGuiApplication
from core.input.inpsys import Input
from core.foundation.logger import Logger


class GameViewportInteractionMixin:

    def _sync_cursor(self):
        locked = Input.cursorLocked
        visible = Input.cursorVisible
        if self._mouse_captured:
            if not self._cursor_blank:
                QGuiApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
                self._cursor_blank = True
            return
        want_blank = not visible
        want_grab = locked
        if want_grab and not self._mouse_captured:
            self._mouse_captured = True
            self.grabMouse()
            self._center_cursor()
        elif not want_grab and self._mouse_captured:
            self._mouse_captured = False
            self.releaseMouse()
        if want_blank and not self._cursor_blank:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
            self._cursor_blank = True
        elif not want_blank and self._cursor_blank:
            QGuiApplication.restoreOverrideCursor()
            self._cursor_blank = False

    def _release_mouse(self):
        if self._mouse_captured:
            self._mouse_captured = False
            self.releaseMouse()
        if self._cursor_blank:
            QGuiApplication.restoreOverrideCursor()
            self._cursor_blank = False

    def _center_cursor(self):
        center = self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))
        QCursor.setPos(center)

    def keyPressEvent(self, event: QKeyEvent):
        if self._engine.play_mode:
            kc = self._input_manager.qt_key_to_vk(event.key())
            if kc is not None:
                with self._input_manager._lock:
                    self._input_manager._pending.append((kc, True))
            if event.key() == Qt.Key.Key_Escape and self._mouse_captured:
                self._release_mouse()
            if event.key() == Qt.Key.Key_F3 and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                try:
                    _dbg = self._debug_shift_f3
                except Exception:
                    _dbg = True
                if _dbg:
                    self._stats_enabled = not self._stats_enabled
                event.accept()
                return
            event.accept()
            return
        event.ignore()

    def keyReleaseEvent(self, event: QKeyEvent):
        if self._engine.play_mode:
            kc = self._input_manager.qt_key_to_vk(event.key())
            if kc is not None:
                with self._input_manager._lock:
                    self._input_manager._pending.append((kc, False))
            event.accept()
            return
        event.ignore()

    def _mouse_button_index(self, qt_btn) -> int:
        from PySide6.QtCore import Qt
        if qt_btn == Qt.MouseButton.LeftButton:
            return 0
        if qt_btn == Qt.MouseButton.RightButton:
            return 1
        if qt_btn == Qt.MouseButton.MiddleButton:
            return 2
        return 0

    def mousePressEvent(self, event: QMouseEvent):
        if self._engine.play_mode:
            btn = self._mouse_button_index(event.button())
            self._input_manager.feed_mouse_button(btn, True)
            if event.button() == Qt.MouseButton.RightButton and not self._mouse_captured:
                self._mouse_captured = True
                self._cursor_blank = True
                self.grabMouse()
                QGuiApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
                self._center_cursor()
            pos = event.position()
            self._last_mouse_x = int(pos.x())
            self._last_mouse_y = int(pos.y())
            self._forward_to_editor_cam("on_mouse_press", btn, 0, 0, bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))
            event.accept()
            return
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._mouse_captured:
            center = QPoint(self.width() // 2, self.height() // 2)
            local_pos = event.position()
            dx = local_pos.x() - center.x()
            dy = local_pos.y() - center.y()
            with self._input_manager._lock:
                self._input_manager._pending_mouse_delta.append((dx, dy))
            self._forward_to_editor_cam_delta(dx, dy)
            self._center_cursor()
            event.accept()
            return
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._engine.play_mode:
            btn = self._mouse_button_index(event.button())
            self._input_manager.feed_mouse_button(btn, False)
            if event.button() == Qt.MouseButton.RightButton and self._mouse_captured:
                Input.set_cursor_visible(True)
                self._mouse_captured = False
                self.releaseMouse()
                QGuiApplication.restoreOverrideCursor()
                self._cursor_blank = False
            self._forward_to_editor_cam("on_mouse_release", btn)
            event.accept()
            return
        event.ignore()

    def wheelEvent(self, event):
        if self._engine.play_mode:
            delta = event.angleDelta()
            self._input_manager.feed_scroll(delta.x(), delta.y())
            self._forward_to_editor_cam("on_scroll", delta.y())
            event.accept()
            return
        event.ignore()

    def _forward_to_editor_cam(self, method: str, *args, **kwargs):
        try:
            from core.components.rendering.cameras.editor_camera import EditorCamera
            scene = self._engine.scene
            if not scene:
                return
            for e in scene.get_entities_with_component(EditorCamera):
                if e.active:
                    comp = e.get_component(EditorCamera)
                    if comp.enabled:
                        getattr(comp, method)(*args, **kwargs)
        except Exception as e:
            Logger.warning(f"_forward_to_editor_cam error: {e}")

    def _forward_to_editor_cam_delta(self, dx: float, dy: float):
        try:
            from core.components.rendering.cameras.editor_camera import EditorCamera
            scene = self._engine.scene
            if not scene:
                return
            for e in scene.get_entities_with_component(EditorCamera):
                if e.active:
                    comp = e.get_component(EditorCamera)
                    if comp.enabled:
                        comp.on_mouse_delta(dx, dy)
        except Exception as e:
            Logger.warning(f"_forward_to_editor_cam_delta error: {e}")

    def leaveEvent(self, event):
        if self._mouse_captured:
            Input.set_cursor_visible(True)
            self._release_mouse()

    def focusOutEvent(self, event):
        if self._mouse_captured:
            Input.set_cursor_visible(True)
            self._release_mouse()
        super().focusOutEvent(event)
