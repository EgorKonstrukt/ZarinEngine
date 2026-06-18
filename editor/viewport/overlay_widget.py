from __future__ import annotations

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter

from editor.viewport.overlay import draw_stats_overlay, draw_delta_label
from editor.viewport.axis_gizmo import draw_axis_gizmo_labels
from editor.viewport.collaboration import draw_remote_cursors


class OverlayWidget(QWidget):
    def __init__(self, viewport, parent=None):
        super().__init__(parent)
        self._vp = viewport
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        vp = self._vp
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        qp.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if vp._stats_enabled:
            draw_stats_overlay(vp, qp)
        draw_delta_label(vp, qp)
        draw_axis_gizmo_labels(vp, qp)
        draw_remote_cursors(vp, qp)
        if vp._overlay_canvas and not vp._overlay_canvas.edit_mode:
            vp._overlay_canvas._render_overlay(qp)
        qp.end()
