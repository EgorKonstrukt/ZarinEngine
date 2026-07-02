# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPixmap, QMouseEvent, QWheelEvent
from PyQt6.QtCore import Qt
from typing import Optional
from editor.gl_offscreen import render_mesh


class ModelPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._verts: Optional[np.ndarray] = None
        self._normals: Optional[np.ndarray] = None
        self._indices: Optional[np.ndarray] = None
        self._radius: float = 1.0
        self._theta: float = 0.5
        self._phi: float = 0.3
        self._zoom: float = 1.0
        self._last_mouse: Optional[tuple[int, int]] = None
        self._pixmap: Optional[QPixmap] = None
        self._dirty: bool = True
        self.setMinimumSize(120, 120)
        self.setMouseTracking(True)

    def set_mesh(self, verts: np.ndarray, indices: np.ndarray, normals: Optional[np.ndarray] = None):
        self._verts = verts
        self._normals = normals
        self._indices = indices
        if verts is not None and len(verts) >= 3:
            pts = verts.reshape(-1, 3)
            center = pts.mean(axis=0)
            r = np.max(np.linalg.norm(pts - center, axis=1))
            self._radius = max(r, 0.01)
        self._dirty = True
        self.update()

    def _render(self):
        dpr = self.devicePixelRatio()
        pw = max(2, int(self.width() * dpr))
        ph = max(2, int(self.height() * dpr))
        if self._verts is None or self._indices is None:
            self._pixmap = None
            return
        dist = self._radius * 3.5 / max(self._zoom, 0.01)
        pm = render_mesh(
            pw, ph,
            self._verts, self._indices,
            self._theta, self._phi, dist,
            normals=self._normals,
        )
        self._pixmap = pm
        self._dirty = False

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        if w < 2 or h < 2:
            return
        dpr = self.devicePixelRatio()
        need_resize = self._pixmap is not None and (self._pixmap.width() != int(dpr * w) or self._pixmap.height() != int(dpr * h))
        if self._dirty or self._pixmap is None or need_resize:
            self._render()
        if self._pixmap is not None and not self._pixmap.isNull():
            p.drawPixmap(0, 0, w, h, self._pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._dirty = True

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = (int(event.position().x()), int(event.position().y()))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = None

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse is None:
            return
        dx = event.position().x() - self._last_mouse[0]
        dy = event.position().y() - self._last_mouse[1]
        self._theta += dx * 0.01
        self._phi += dy * 0.01
        self._phi = max(-math.pi / 2 + 0.05, min(math.pi / 2 - 0.05, self._phi))
        self._last_mouse = (int(event.position().x()), int(event.position().y()))
        self._dirty = True
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        self._zoom *= 1.0 + event.angleDelta().y() * 0.001
        self._zoom = max(0.2, min(5.0, self._zoom))
        self._dirty = True
        self.update()
