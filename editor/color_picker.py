from __future__ import annotations
import re
from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QSpinBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import QColor, QPixmap, QPainter, QLinearGradient, QBrush, QPen, QImage
from math import floor, sqrt


def _hsv_to_rgb(h, s, v):
    h = h % 360
    s = max(0, min(1, s))
    v = max(0, min(1, v))
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (r + m, g + m, b + m)


def _rgb_to_hsv(r, g, b):
    mx = max(r, g, b)
    mn = min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0
    elif mx == r:
        h = 60 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60 * (((b - r) / d) + 2)
    else:
        h = 60 * (((r - g) / d) + 4)
    s = 0 if mx == 0 else d / mx
    v = mx
    return (h % 360, s, v)


class _TriangleWidget(QWidget):
    colorChanged = pyqtSignal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 220)
        self._hue = 0.0
        self._sat = 1.0
        self._val = 1.0
        self._image = None
        self._dragging = False

    def set_hue(self, h):
        self._hue = h
        self._image = None
        self.update()

    def set_sv(self, s, v):
        self._sat = max(0, min(1, s))
        self._val = max(0, min(1, v))
        self.update()

    def _vert_coords(self):
        w, h = self.width(), self.height()
        return (w / 2, 5), (5, h - 5), (w - 5, h - 5)

    def _barycentric(self, px, py):
        (ax, ay), (bx, by), (cx, cy) = self._vert_coords()
        area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area2 == 0:
            return None
        u = ((bx - px) * (cy - py) - (cx - px) * (by - py)) / area2
        v = ((cx - px) * (ay - py) - (ax - px) * (cy - py)) / area2
        w = ((ax - px) * (by - py) - (bx - px) * (ay - py)) / area2
        return u, v, w

    def _xy_to_sv(self, px, py):
        bc = self._barycentric(px, py)
        if bc is None:
            return (0, 0)
        u, v, w = bc
        s = max(0, min(1, w))
        val = max(0, min(1, u + w))
        return (s, val)

    def _sv_to_xy(self, s, v):
        (ax, ay), (bx, by), (cx, cy) = self._vert_coords()
        w_coord = max(0, min(1, s))
        v_coord = max(0, min(1, 1 - v))
        u_coord = max(0, min(1, 1 - v_coord - w_coord))
        total = u_coord + v_coord + w_coord
        if total > 0:
            u_coord /= total
            v_coord /= total
            w_coord /= total
        px = u_coord * ax + v_coord * bx + w_coord * cx
        py = u_coord * ay + v_coord * by + w_coord * cy
        return (px, py)

    def paintEvent(self, event):
        if self._image is None or self._image.size() != self.size():
            self._render_image()
        p = QPainter(self)
        p.drawImage(0, 0, self._image)
        ix, iy = self._sv_to_xy(self._sat, self._val)
        lum = self._val * 0.299 + self._sat * 0.587 + (1 - self._val) * 0.114
        pen = QPen(Qt.GlobalColor.black if lum > 0.5 else Qt.GlobalColor.white)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(ix) - 5, int(iy) - 5, 10, 10)
        p.setPen(QPen(Qt.GlobalColor.black if lum > 0.5 else Qt.GlobalColor.white, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(ix) - 4, int(iy) - 4, 8, 8)

    def _render_image(self):
        w, h = self.width(), self.height()
        if w < 1 or h < 1:
            return
        self._image = QImage(w, h, QImage.Format.Format_RGB32)
        (ax, ay), (bx, by), (cx, cy) = self._vert_coords()
        area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area2 == 0:
            self._image.fill(0xFF333333)
            return
        for py in range(h):
            for px in range(w):
                u = ((bx - px) * (cy - py) - (cx - px) * (by - py)) / area2
                vv = ((cx - px) * (ay - py) - (ax - px) * (cy - py)) / area2
                wv = ((ax - px) * (by - py) - (bx - px) * (ay - py)) / area2
                if u >= 0 and vv >= 0 and wv >= 0:
                    s = wv
                    val = u + wv
                    r, g, b = _hsv_to_rgb(self._hue, s, val)
                    self._image.setPixel(px, py, (0xFF << 24) | (int(r * 255) << 16) | (int(g * 255) << 8) | int(b * 255))
                else:
                    self._image.setPixel(px, py, 0xFF333333)

    def _clamp_to_triangle(self, px, py):
        (ax, ay), (bx, by), (cx, cy) = self._vert_coords()
        area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area2 == 0:
            return (ax, ay)
        u = ((bx - px) * (cy - py) - (cx - px) * (by - py)) / area2
        vv = ((cx - px) * (ay - py) - (ax - px) * (cy - py)) / area2
        wv = ((ax - px) * (by - py) - (bx - px) * (ay - py)) / area2
        if u >= 0 and vv >= 0 and wv >= 0:
            return (px, py)
        if u < 0:
            d = vv + wv
            if d > 0:
                vv /= d
                wv /= d
            vv = max(0, min(1, vv))
            wv = max(0, min(1, 1 - vv))
            u = 0
        elif vv < 0:
            d = u + wv
            if d > 0:
                u /= d
                wv /= d
            u = max(0, min(1, u))
            wv = max(0, min(1, 1 - u))
            vv = 0
        elif wv < 0:
            d = u + vv
            if d > 0:
                u /= d
                vv /= d
            u = max(0, min(1, u))
            vv = max(0, min(1, 1 - u))
            wv = 0
        px = u * ax + vv * bx + wv * cx
        py = u * ay + vv * by + wv * cy
        return (px, py)

    def mousePressEvent(self, event):
        self._dragging = True
        self._update_sv(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_sv(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._update_sv(event)

    def _update_sv(self, event):
        px, py = self._clamp_to_triangle(event.position().x(), event.position().y())
        s, val = self._xy_to_sv(px, py)
        if s != self._sat or val != self._val:
            self._sat = s
            self._val = val
            self.update()
            self.colorChanged.emit(self._hue, self._sat, self._val, -1.0)


class _HueSlider(QWidget):
    hueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 20)
        self._hue = 0.0
        self._dragging = False

    def set_hue(self, h):
        self._hue = h % 360
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        grad = QLinearGradient(0, 0, w, 0)
        for i in range(0, 360, 30):
            c = QColor.fromHsvF(i / 360, 1, 1)
            grad.setColorAt(i / 360, c)
        grad.setColorAt(1, QColor.fromHsvF(1, 1, 1))
        p.fillRect(0, 0, w, h, grad)
        x = int(self._hue / 360 * (w - 1))
        p.setPen(QPen(Qt.GlobalColor.black, 2))
        p.drawLine(x, 0, x, h)
        p.setPen(QPen(Qt.GlobalColor.white, 1))
        p.drawLine(x + 1, 0, x + 1, h)

    def mousePressEvent(self, event):
        self._dragging = True
        self._update_hue(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_hue(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._update_hue(event)

    def _update_hue(self, event):
        w = self.width()
        if w < 1:
            return
        x = max(0, min(w - 1, event.position().x()))
        self._hue = x / (w - 1) * 360
        self.update()
        self.hueChanged.emit(self._hue)


class _AlphaWidget(QWidget):
    alphaChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 20)
        self._alpha = 1.0
        self._color = QColor.fromRgbF(1, 1, 1)
        self._dragging = False

    def set_alpha(self, a):
        self._alpha = max(0, min(1, a))
        self.update()

    def set_color(self, c: QColor):
        self._color = c
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        for x in range(0, w, 8):
            for y in range(0, h, 8):
                even = (x // 8 + y // 8) % 2 == 0
                p.fillRect(x, y, 8, 8, Qt.GlobalColor.white if even else Qt.GlobalColor.lightGray)
        r, g, b = self._color.redF(), self._color.greenF(), self._color.blueF()
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0, QColor.fromRgbF(r, g, b, 0))
        grad.setColorAt(1, QColor.fromRgbF(r, g, b, 1))
        p.fillRect(0, 0, w, h, grad)
        x = int(self._alpha * (w - 1))
        p.setPen(QPen(Qt.GlobalColor.black, 2))
        p.drawLine(x, 0, x, h)

    def mousePressEvent(self, event):
        self._dragging = True
        self._update_alpha(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_alpha(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._update_alpha(event)

    def _update_alpha(self, event):
        w = self.width()
        if w < 1:
            return
        self._alpha = max(0, min(1, event.position().x() / (w - 1)))
        self.update()
        self.alphaChanged.emit(self._alpha)


class ColorDialog(QDialog):
    colorChanged = pyqtSignal(object)

    def __init__(self, initial: QColor = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Color")
        self.setMinimumWidth(300)

        self._color = initial.toRgb() if initial and initial.isValid() else QColor.fromRgbF(1, 1, 1)
        h, s, v, a = self._color.hueF(), self._color.saturationF(), self._color.valueF(), self._color.alphaF()
        if h < 0:
            h = 0

        layout = QVBoxLayout(self)

        self._triangle = _TriangleWidget()
        self._triangle.set_hue(h * 360)
        self._triangle.set_sv(s, v)
        layout.addWidget(self._triangle, alignment=Qt.AlignmentFlag.AlignCenter)

        self._hue_slider = _HueSlider()
        self._hue_slider.set_hue(h * 360)
        layout.addWidget(self._hue_slider)

        self._alpha_slider = _AlphaWidget()
        self._alpha_slider.set_alpha(a)
        self._alpha_slider.set_color(self._color)
        layout.addWidget(self._alpha_slider)

        rgb_layout = QHBoxLayout()
        self._r_spin = QSpinBox()
        self._r_spin.setRange(0, 255)
        self._r_spin.setValue(int(self._color.redF() * 255))
        self._g_spin = QSpinBox()
        self._g_spin.setRange(0, 255)
        self._g_spin.setValue(int(self._color.greenF() * 255))
        self._b_spin = QSpinBox()
        self._b_spin.setRange(0, 255)
        self._b_spin.setValue(int(self._color.blueF() * 255))
        self._a_spin = QSpinBox()
        self._a_spin.setRange(0, 255)
        self._a_spin.setValue(int(a * 255))
        rgb_layout.addWidget(QLabel("R:"))
        rgb_layout.addWidget(self._r_spin)
        rgb_layout.addWidget(QLabel("G:"))
        rgb_layout.addWidget(self._g_spin)
        rgb_layout.addWidget(QLabel("B:"))
        rgb_layout.addWidget(self._b_spin)
        rgb_layout.addWidget(QLabel("A:"))
        rgb_layout.addWidget(self._a_spin)
        layout.addLayout(rgb_layout)

        hex_layout = QHBoxLayout()
        hex_layout.addWidget(QLabel("Hex:"))
        self._hex_edit = QLineEdit()
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        hex_layout.addWidget(self._hex_edit)
        layout.addLayout(hex_layout)

        self._preview = QLabel()
        self._preview.setFixedHeight(30)
        self._update_preview()
        layout.addWidget(self._preview)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._triangle.colorChanged.connect(self._on_triangle_changed)
        self._hue_slider.hueChanged.connect(self._on_hue_changed)
        self._alpha_slider.alphaChanged.connect(self._on_alpha_changed)
        self._r_spin.valueChanged.connect(self._on_rgb_spin)
        self._g_spin.valueChanged.connect(self._on_rgb_spin)
        self._b_spin.valueChanged.connect(self._on_rgb_spin)
        self._a_spin.valueChanged.connect(self._on_a_spin)
        self._hex_edit.editingFinished.connect(self._on_hex_edited)

    def _on_triangle_changed(self, hue, s, v, _alpha_unused):
        a = self._color.alphaF()
        self._color.setHsvF(hue / 360.0, s, v, a)
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_hue_changed(self, h):
        self._triangle.set_hue(h)
        s = self._triangle._sat
        v = self._triangle._val
        a = self._color.alphaF()
        self._color.setHsvF(h / 360.0, s, v, a)
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_alpha_changed(self, a):
        self._color.setAlphaF(a)
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_rgb_spin(self):
        self._color.setRgb(self._r_spin.value(), self._g_spin.value(), self._b_spin.value(), self._a_spin.value())
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_a_spin(self, v):
        self._color.setAlpha(v)
        self._sync_from_color()
        self.colorChanged.emit(self._color)

    def _on_hex_edited(self):
        text = self._hex_edit.text().strip()
        c = QColor(text)
        if c.isValid():
            self._color = c.toRgb()
            self._sync_from_color()
            self.colorChanged.emit(self._color)

    def _sync_from_color(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        h, s, v = self._color.hueF(), self._color.saturationF(), self._color.valueF()
        if h < 0:
            h = 0
        self._r_spin.blockSignals(True)
        self._g_spin.blockSignals(True)
        self._b_spin.blockSignals(True)
        self._a_spin.blockSignals(True)
        self._r_spin.setValue(r)
        self._g_spin.setValue(g)
        self._b_spin.setValue(b)
        self._a_spin.setValue(a)
        self._r_spin.blockSignals(False)
        self._g_spin.blockSignals(False)
        self._b_spin.blockSignals(False)
        self._a_spin.blockSignals(False)
        af = self._color.alphaF()
        self._alpha_slider.set_alpha(af)
        self._alpha_slider.set_color(self._color)
        self._hue_slider.set_hue(h * 360)
        self._triangle.set_hue(h * 360)
        self._triangle.set_sv(s, v)
        self._hex_edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._update_preview()

    def _update_preview(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        self._preview.setStyleSheet(f"background: rgba({r},{g},{b},{a/255});")

    def get_color(self) -> QColor:
        return self._color


class ColorLineEdit(QWidget):
    colorChanged = pyqtSignal(object)

    def __init__(self, color=None, parent=None):
        super().__init__(parent)
        self._color = self._parse_color(color) if color is not None else QColor.fromRgbF(1, 1, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._preview = QPushButton()
        self._preview.setFixedSize(28, 22)
        self._update_swatch()
        self._preview.clicked.connect(self._open_dialog)
        layout.addWidget(self._preview)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("#rrggbb or rgb(r,g,b)")
        self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit, 1)

    @staticmethod
    def _parse_color(color):
        if isinstance(color, QColor):
            return color.toRgb()
        if isinstance(color, (list, tuple)):
            r, g, b, a = (float(v) for v in (color + [1.0, 1.0, 1.0, 1.0])[:4])
            return QColor.fromRgbF(r, g, b, a).toRgb()
        if isinstance(color, str):
            c = QColor(color.strip())
            if c.isValid():
                return c.toRgb()
        return QColor.fromRgbF(1, 1, 1)

    def _update_swatch(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        self._preview.setStyleSheet(
            f"background: rgba({r},{g},{b},{a/255}); border: 1px solid #555; border-radius: 3px;"
        )

    def _open_dialog(self):
        dlg = ColorDialog(self._color, self)

        def _on_dialog_color(c):
            self._color = c.toRgb()
            self._update_swatch()
            self._edit.blockSignals(True)
            self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
            self._edit.blockSignals(False)
            self.colorChanged.emit(self._color)

        dlg.colorChanged.connect(_on_dialog_color)
        dlg.exec()
        dlg.colorChanged.disconnect(_on_dialog_color)
        self._color = dlg.get_color().toRgb()
        self._update_swatch()
        self._edit.blockSignals(True)
        self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._edit.blockSignals(False)
        self.colorChanged.emit(self._color)

    def _on_text_changed(self, text):
        c = QColor(text.strip())
        if c.isValid():
            self._color = c.toRgb()
            self._update_swatch()
            self.colorChanged.emit(self._color)

    def set_color(self, color):
        if isinstance(color, (list, tuple)):
            fmt = tuple(float(v) for v in color)
            if len(fmt) >= 3:
                r, g, b = fmt[0], fmt[1], fmt[2]
                a = fmt[3] if len(fmt) > 3 else 1.0
                self._color = QColor.fromRgbF(r, g, b, a)
            else:
                self._color = QColor.fromRgbF(1, 1, 1)
        elif isinstance(color, QColor):
            self._color = color.toRgb()
        else:
            c = QColor(str(color))
            self._color = c.toRgb() if c.isValid() else QColor.fromRgbF(1, 1, 1)
        self._update_swatch()
        self._edit.blockSignals(True)
        self._edit.setText(self._color.name(QColor.NameFormat.HexArgb))
        self._edit.blockSignals(False)

    def get_color(self) -> QColor:
        return self._color

    def get_color_rgba(self) -> list[float]:
        return [self._color.redF(), self._color.greenF(), self._color.blueF(), self._color.alphaF()]
