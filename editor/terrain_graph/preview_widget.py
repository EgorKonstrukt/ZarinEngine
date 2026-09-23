# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from PyQt6 import QtWidgets, QtCore, QtGui
from editor.NodeGraphQt.widgets.node_widgets import NodeBaseWidget


class NodePreviewWidget(NodeBaseWidget):
    PREVIEW_SIZE = 64
    _placeholder = None

    def __init__(self, parent=None, name="_preview", label="Preview"):
        super(NodePreviewWidget, self).__init__(parent, name, label)
        self._img_label = QtWidgets.QLabel()
        self._img_label.setFixedSize(self.PREVIEW_SIZE, self.PREVIEW_SIZE)
        self._img_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self._img_label.setStyleSheet(
            "background: #1a1a1a; border: 1px solid #333; border-radius: 2px;"
        )
        self._img_label.setText("--")
        self._img_label.setPixmap(self._shared_placeholder())
        self.set_custom_widget(self._img_label)
        self.widget().setMaximumWidth(self.PREVIEW_SIZE + 8)
        self._last_hf = None

    @property
    def type_(self):
        return "PreviewNodeWidget"

    def get_value(self):
        return ""

    def set_value(self, text):
        pass

    @classmethod
    def _shared_placeholder(cls) -> QtGui.QPixmap:
        pm = cls._placeholder
        if pm is not None and not pm.isNull():
            return pm
        pm = QtGui.QPixmap(cls.PREVIEW_SIZE, cls.PREVIEW_SIZE)
        pm.fill(QtGui.QColor("#1a1a1a"))
        painter = QtGui.QPainter(pm)
        painter.setPen(QtGui.QColor("#555"))
        painter.drawText(pm.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "?")
        painter.end()
        cls._placeholder = pm
        return pm

    def set_preview(self, heightfield: np.ndarray | None):
        if heightfield is None or heightfield.size == 0:
            self._last_hf = None
            self._img_label.setPixmap(self._shared_placeholder())
            return
        if heightfield is self._last_hf:
            return
        self._last_hf = heightfield
        try:
            h, w = heightfield.shape[0], heightfield.shape[1]
        except Exception:
            return
        try:
            hmin = float(np.min(heightfield))
            hmax = float(np.max(heightfield))
        except Exception:
            return
        if hmax - hmin < 1e-8:
            gray = np.zeros((h, w), dtype=np.uint8)
        else:
            inv = 255.0 / (hmax - hmin)
            gray = ((heightfield - hmin) * inv).clip(0.0, 255.0).astype(np.uint8, copy=False)
        if not gray.flags["C_CONTIGUOUS"]:
            gray = np.ascontiguousarray(gray)
        bytes_per_line = w
        qimg = QtGui.QImage(gray.tobytes(), w, h, bytes_per_line, QtGui.QImage.Format.Format_Grayscale8)
        pixmap = QtGui.QPixmap.fromImage(qimg)
        if w != self.PREVIEW_SIZE or h != self.PREVIEW_SIZE:
            pixmap = pixmap.scaled(
                self.PREVIEW_SIZE, self.PREVIEW_SIZE,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.FastTransformation,
            )
        self._img_label.setPixmap(pixmap)

    def _make_placeholder(self) -> QtGui.QPixmap:
        return self._shared_placeholder()
