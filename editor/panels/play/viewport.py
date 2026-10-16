# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QKeyEvent, QMouseEvent, QCursor, QGuiApplication
from core.input.inpsys import Input
from core.foundation.logger import Logger
from .viewport_base import _PlayViewportBase
if TYPE_CHECKING:
    from core.engine.eng import Engine
    from core.gui.canvasp import GuiCanvas


class PlayViewport(_PlayViewportBase):
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
            from core.input.input_manager import InputManager
            im = InputManager.instance()
            with im._lock:
                im._pending.append((event.nativeVirtualKey(), True))
            if event.key() == Qt.Key.Key_Escape and self._mouse_captured:
                self._release_mouse()
            event.accept()
            return
        event.ignore()

    def keyReleaseEvent(self, event: QKeyEvent):
        if self._engine.play_mode:
            from core.input.input_manager import InputManager
            im = InputManager.instance()
            with im._lock:
                im._pending.append((event.nativeVirtualKey(), False))
            event.accept()
            return
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent):
        if self._engine.play_mode:
            btn = self._mouse_button_index(event.button())
            from core.input.input_manager import InputManager
            im = InputManager.instance()
            with im._lock:
                im._pending_mouse.append((event.position().x(), event.position().y(), 0))
            im.feed_mouse_button(btn, True)
            if event.button() == Qt.MouseButton.RightButton and not self._mouse_captured:
                self._mouse_captured = True
                self._cursor_blank = True
                self.grabMouse()
                QGuiApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
                self._center_cursor()
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
            from core.input.input_manager import InputManager
            im = InputManager.instance()
            with im._lock:
                im._pending_mouse_delta.append((dx, dy))
            self._forward_to_editor_cam_delta(dx, dy)
            self._center_cursor()
            event.accept()
            return
        if self._engine.play_mode:
            from core.input.input_manager import InputManager
            im = InputManager.instance()
            with im._lock:
                im._pending_mouse.append((event.position().x(), event.position().y(), 0))
            event.accept()
            return
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._engine.play_mode:
            btn = self._mouse_button_index(event.button())
            from core.input.input_manager import InputManager
            im = InputManager.instance()
            im.feed_mouse_button(btn, False)
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
            from core.input.input_manager import InputManager
            im = InputManager.instance()
            im.feed_scroll(delta.x(), delta.y())
            self._forward_to_editor_cam("on_scroll", delta.y())
            event.accept()
            return
        event.ignore()

    def _mouse_button_index(self, qt_btn) -> int:
        if qt_btn == Qt.MouseButton.LeftButton:
            return 0
        if qt_btn == Qt.MouseButton.RightButton:
            return 1
        if qt_btn == Qt.MouseButton.MiddleButton:
            return 2
        return 0

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
            Logger.warning(f"PlayViewport _forward_to_editor_cam error: {e}")

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
            Logger.warning(f"PlayViewport _forward_to_editor_cam_delta error: {e}")

    def leaveEvent(self, event):
        if self._mouse_captured:
            Input.set_cursor_visible(True)
            self._release_mouse()

    def show_overlay(self, canvas: GuiCanvas):
        self.hide_overlay()
        self._overlay_canvas = canvas
        vw, vh = self.width(), self.height()
        container = QWidget(self)
        container.setObjectName("PlayOverlayContainer")
        container.setGeometry(0, 0, vw, vh)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        container.setStyleSheet("QWidget#PlayOverlayContainer { background: transparent; }")
        container.show()
        root = canvas._root
        root.setParent(container)
        root.setGeometry(0, 0, vw, vh)
        root.setVisible(True)
        root.installEventFilter(self)
        self._overlay_root = root
        self._overlay_container = container

    def hide_overlay(self):
        canvas = self._overlay_canvas
        if canvas and self._overlay_container:
            root = canvas._root
            root.removeEventFilter(self)
            root.setParent(canvas)
            canvas._update_root_geometry()
            root.setVisible(True)
            self._overlay_container.deleteLater()
            self._overlay_container = None
        self._overlay_root = None
        self._overlay_canvas = None

    def eventFilter(self, watched, event):
        root = getattr(self, "_overlay_root", None)
        if watched is root and root is not None:
            et = event.type()
            if et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                      QEvent.Type.MouseMove, QEvent.Type.Wheel):
                pos = event.position()
                if root.childAt(int(pos.x()), int(pos.y())) is None:
                    QGuiApplication.sendEvent(self, event)
                    return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay_container and self._overlay_canvas:
            vw, vh = self.width(), self.height()
            self._overlay_container.setGeometry(0, 0, vw, vh)
            canvas = self._overlay_canvas
            canvas._update_root_geometry()

    def focusOutEvent(self, event):
        if self._mouse_captured:
            Input.set_cursor_visible(True)
            self._release_mouse()
        super().focusOutEvent(event)
