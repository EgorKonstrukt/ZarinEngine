# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

#!/usr/bin/python
from PyQt6 import (QtGui, QtCore, QtWidgets)

from editor.NodeGraphQt.constants import ViewerEnum


class NodeScene(QtWidgets.QGraphicsScene):

    def __init__(self, parent=None):
        super(NodeScene, self).__init__(parent)
        self._grid_mode = ViewerEnum.GRID_DISPLAY_LINES.value
        self._grid_color = ViewerEnum.GRID_COLOR.value
        self._bg_color = ViewerEnum.BACKGROUND_COLOR.value
        self.setBackgroundBrush(QtGui.QColor(*self._bg_color))
        self.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        self._grid_pen_minor = QtGui.QPen(QtGui.QColor(*self._grid_color), 0.65)
        self._grid_pen_major = QtGui.QPen(QtGui.QColor(*self._bg_color).darker(200), 0.65)
        self._dot_pen = QtGui.QPen(QtGui.QColor(*self._grid_color), 0.65)

    def __repr__(self):
        cls_name = str(self.__class__.__name__)
        return '<{}("{}") object at {}>'.format(
            cls_name, self.viewer(), hex(id(self)))

    # def _draw_text(self, painter, pen):
    #     font = QtGui.QFont()
    #     font.setPixelSize(48)
    #     painter.setFont(font)
    #     parent = self.viewer()
    #     pos = QtCore.QPoint(20, parent.height() - 20)
    #     painter.setPen(pen)
    #     painter.drawText(parent.mapToScene(pos), 'Not Editable')

    def _draw_grid(self, painter, rect, pen, grid_size):
        left = int(rect.left())
        right = int(rect.right())
        top = int(rect.top())
        bottom = int(rect.bottom())
        if grid_size <= 0:
            return
        span_x = (right - left) // grid_size
        span_y = (bottom - top) // grid_size
        if span_x * span_y > 4000:
            return
        first_left = left - (left % grid_size)
        first_top = top - (top % grid_size)
        lines = []
        append = lines.append
        for x in range(first_left, right, grid_size):
            append(QtCore.QLineF(x, top, x, bottom))
            if len(lines) > 2000:
                break
        for y in range(first_top, bottom, grid_size):
            append(QtCore.QLineF(left, y, right, y))
            if len(lines) > 2000:
                break
        if lines:
            painter.setPen(pen)
            painter.drawLines(lines)

    def _draw_dots(self, painter, rect, pen, grid_size):
        zoom = self.viewer().get_zoom()
        if zoom < 0:
            grid_size = int(abs(zoom) / 0.3 + 1) * grid_size
        left = int(rect.left())
        right = int(rect.right())
        top = int(rect.top())
        bottom = int(rect.bottom())
        if grid_size <= 0:
            return
        span_x = (right - left) // grid_size
        span_y = (bottom - top) // grid_size
        if span_x * span_y > 6000:
            step = max(2, int(((span_x * span_y) / 6000) ** 0.5) + 1)
            grid_size = grid_size * step
        first_left = left - (left % grid_size)
        first_top = top - (top % grid_size)
        pen.setWidth(max(1, grid_size // 10))
        painter.setPen(pen)
        pts = []
        append = pts.append
        for x in range(first_left, right, grid_size):
            for y in range(first_top, bottom, grid_size):
                append(QtCore.QPointF(x, y))
                if len(pts) > 6000:
                    break
            if len(pts) > 6000:
                break
        if pts:
            painter.drawPoints(pts)

    def drawBackground(self, painter, rect):
        super(NodeScene, self).drawBackground(painter, rect)

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setBrush(self.backgroundBrush())

        if self._grid_mode is ViewerEnum.GRID_DISPLAY_DOTS.value:
            self._draw_dots(painter, rect, self._dot_pen, ViewerEnum.GRID_SIZE.value)

        elif self._grid_mode is ViewerEnum.GRID_DISPLAY_LINES.value:
            try:
                zoom = self.viewer().get_zoom()
            except Exception:
                zoom = 0.0
            if zoom > -0.5:
                self._draw_grid(
                    painter, rect, self._grid_pen_minor, ViewerEnum.GRID_SIZE.value
                )
            self._draw_grid(
                painter, rect, self._grid_pen_major, ViewerEnum.GRID_SIZE.value * 8
            )

        painter.restore()

    def mousePressEvent(self, event):
        selected_nodes = self.viewer().selected_nodes()
        if self.viewer():
            self.viewer().sceneMousePressEvent(event)
        super(NodeScene, self).mousePressEvent(event)
        keep_selection = any([
            event.button() == QtCore.Qt.MouseButton.MiddleButton,
            event.button() == QtCore.Qt.MouseButton.RightButton,
            event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier
        ])
        if keep_selection:
            for node in selected_nodes:
                node.setSelected(True)

    def mouseMoveEvent(self, event):
        if self.viewer():
            self.viewer().sceneMouseMoveEvent(event)
        super(NodeScene, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.viewer():
            self.viewer().sceneMouseReleaseEvent(event)
        super(NodeScene, self).mouseReleaseEvent(event)

    def viewer(self):
        return self.views()[0] if self.views() else None

    @property
    def grid_mode(self):
        return self._grid_mode

    @grid_mode.setter
    def grid_mode(self, mode=None):
        if mode is None:
            mode = ViewerEnum.GRID_DISPLAY_LINES.value
        self._grid_mode = mode

    @property
    def grid_color(self):
        return self._grid_color

    @grid_color.setter
    def grid_color(self, color=(0, 0, 0)):
        self._grid_color = color
        try:
            self._grid_pen_minor = QtGui.QPen(QtGui.QColor(*self._grid_color), 0.65)
            self._dot_pen = QtGui.QPen(QtGui.QColor(*self._grid_color), 0.65)
        except Exception:
            pass

    @property
    def background_color(self):
        return self._bg_color

    @background_color.setter
    def background_color(self, color=(0, 0, 0)):
        self._bg_color = color
        self.setBackgroundBrush(QtGui.QColor(*self._bg_color))
        try:
            self._grid_pen_major = QtGui.QPen(QtGui.QColor(*self._bg_color).darker(200), 0.65)
        except Exception:
            pass
