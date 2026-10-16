# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from PySide6.QtWidgets import QLabel, QFrame, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QObject, QEvent, QPropertyAnimation, QEasingCurve, QRect

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

class _NavFilter(QObject):
    def __init__(self, single_cb, double_cb=None, parent=None):
        super().__init__(parent)
        self._single = single_cb
        self._double = double_cb
    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton and self._double:
            self._double()
            return True
        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton and self._single:
            self._single()
        return super().eventFilter(obj, event)

def _navigate_resource(label: QLabel):
    p = label.toolTip()
    if p and "No " not in p:
        mw = label.window()
        if hasattr(mw, '_project'):
            mw._project.reveal_resource(p)
            mw._project.open_resource(p)

def _flash_resource(label: QLabel):
    p = label.toolTip()
    if p and "No " not in p:
        mw = label.window()
        if hasattr(mw, '_project'):
            mw._project.flash_resource(p)

def _navigate_entity(label: QLabel):
    eid = label.toolTip()
    if eid and "No " not in eid:
        mw = label.window()
        if hasattr(mw, '_hierarchy'):
            mw._hierarchy.reveal_entity(eid)

def _flash_entity(label: QLabel):
    eid = label.toolTip()
    if eid and "No " not in eid:
        mw = label.window()
        if hasattr(mw, '_hierarchy'):
            mw._hierarchy.flash_entity(eid)

def _expanded_rect(rect: QRect, factor: float) -> QRect:
    w = int(rect.width() * factor)
    h = int(rect.height() * factor)
    x = rect.center().x() - w // 2
    y = rect.center().y() - h // 2
    return QRect(x, y, w, h)

def _flash_overlay(viewport, item_rect: QRect, duration: int = 800):
    main_window = viewport.window()
    if not main_window:
        return
    global_tl = viewport.mapToGlobal(item_rect.topLeft())
    item_global = QRect(global_tl, item_rect.size())
    start_global = _expanded_rect(item_global, 1.5)
    overlay = QFrame(main_window)
    overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    overlay.setStyleSheet("background: rgba(255, 255, 0, 180); border-radius: 4px;")
    overlay.setGeometry(QRect(main_window.mapFromGlobal(start_global.topLeft()), start_global.size()))
    overlay.show()
    overlay.raise_()
    op = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(op)
    opacity_anim = QPropertyAnimation(op, b"opacity")
    opacity_anim.setStartValue(0.8)
    opacity_anim.setEndValue(0.0)
    opacity_anim.setDuration(duration)
    geo_anim = QPropertyAnimation(overlay, b"geometry")
    geo_anim.setStartValue(QRect(main_window.mapFromGlobal(start_global.topLeft()), start_global.size()))
    geo_anim.setEndValue(QRect(main_window.mapFromGlobal(item_global.topLeft()), item_global.size()))
    geo_anim.setDuration(duration // 2)
    geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    def _cleanup():
        overlay.deleteLater()
    opacity_anim.finished.connect(_cleanup)
    opacity_anim.start()
    geo_anim.start()
    overlay._opacity_anim = opacity_anim
    overlay._geo_anim = geo_anim
