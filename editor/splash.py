from __future__ import annotations

import os
import random
import sys
from PyQt6.QtWidgets import QSplashScreen, QApplication
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QRadialGradient, QPen, QPainterPath
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF
from PyQt6.QtSvg import QSvgRenderer

from core.constants import (
    APP_VERSION_DISPLAY,
    SPLASH_WIDTH, SPLASH_HEIGHT, SPLASH_RADIUS, SPLASH_OPACITY, SPLASH_WINDOW_FLAGS,
    LOGO_TARGET_WIDTH, LOGO_VIEWBOX, LOGO_Y,
    PROGRESS_BAR_WIDTH, PROGRESS_BAR_HEIGHT, PROGRESS_BAR_Y_OFFSET,
    PROGRESS_BAR_RADIUS, PROGRESS_FILL_RADIUS,
    STATUS_TEXT_Y_OFFSET, STATUS_TEXT_MARGIN,
    VERSION_Y, ACCENT_BAR_Y, DID_YOU_KNOW_Y, DID_YOU_KNOW_WIDTH_MAX,
    TIPS, BG_GRADIENT, GLOW_SPOTS, LOGO_GLOW, CENTER_GLOW,
    TEXT_VERSION, TEXT_STATUS, TEXT_TIP, ACCENT_BAR_COLORS,
    PB_TRACK, PB_TRACK_FILL, PB_FILL_COLORS,
)


def _render_logo(target_width: int) -> QPixmap | None:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "zarin_logo.svg")
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    renderer.setViewBox(LOGO_VIEWBOX)
    target_height = round(target_width * LOGO_VIEWBOX.height() / LOGO_VIEWBOX.width())
    pm = QPixmap(target_width, target_height)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, target_width, target_height))
    p.end()
    return pm


def _build_base_pixmap(tip: str = ""):
    pixmap = QPixmap(SPLASH_WIDTH, SPLASH_HEIGHT)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    path = QPainterPath()
    path.addRoundedRect(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT, SPLASH_RADIUS, SPLASH_RADIUS)
    p.setClipPath(path)

    bg = QLinearGradient(0, 0, 0, SPLASH_HEIGHT)
    for stop, r, g, b, a in BG_GRADIENT:
        bg.setColorAt(stop, QColor(r, g, b, a))
    p.setBrush(bg)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT)

    for i, (r, g, b, a) in enumerate(GLOW_SPOTS):
        cx = SPLASH_WIDTH * (0.15 + i * 0.23)
        cy = SPLASH_HEIGHT * (0.3 + (i % 2) * 0.25)
        rg = QRadialGradient(cx, cy, 200)
        rg.setColorAt(0.0, QColor(r, g, b, a))
        rg.setColorAt(0.5, QColor(r, g, b, a // 2))
        rg.setColorAt(1.0, QColor(r, g, b, 0))
        p.setBrush(rg)
        p.drawEllipse(QPointF(cx, cy), 200, 150)

    cgr, cgg, cgb, cga = CENTER_GLOW
    glow = QRadialGradient(SPLASH_WIDTH * 0.5, SPLASH_HEIGHT * 0.3, 280)
    glow.setColorAt(0.0, QColor(cgr, cgg, cgb, cga))
    glow.setColorAt(1.0, QColor(cgr, cgg, cgb, 0))
    p.setBrush(glow)
    p.drawEllipse(QPointF(SPLASH_WIDTH * 0.5, SPLASH_HEIGHT * 0.3), 280, 200)

    lgr, lgg, lgb, lga = LOGO_GLOW
    logo_glow = QRadialGradient(SPLASH_WIDTH * 0.5, LOGO_Y + 100, 320)
    logo_glow.setColorAt(0.0, QColor(lgr, lgg, lgb, lga))
    logo_glow.setColorAt(0.3, QColor(lgr, lgg, lgb, lga // 2))
    logo_glow.setColorAt(1.0, QColor(lgr, lgg, lgb, 0))
    p.setBrush(logo_glow)
    p.drawEllipse(QPointF(SPLASH_WIDTH * 0.5, LOGO_Y + 100), 320, 200)

    logo = _render_logo(LOGO_TARGET_WIDTH)
    if logo is not None:
        p.drawPixmap((SPLASH_WIDTH - logo.width()) // 2, LOGO_Y, logo)

    vr, vg, vb, va = TEXT_VERSION
    vf = QFont("Segoe UI Semibold", 13)
    p.setFont(vf)
    p.setPen(QColor(vr, vg, vb, va))
    p.drawText(QRect(0, VERSION_Y, SPLASH_WIDTH, 20), Qt.AlignmentFlag.AlignCenter, APP_VERSION_DISPLAY)

    ab = QRectF(SPLASH_WIDTH * 0.25, ACCENT_BAR_Y, SPLASH_WIDTH * 0.5, 1)
    ag = QLinearGradient(ab.left(), 0, ab.right(), 0)
    for stop, r, g, b, a in ACCENT_BAR_COLORS:
        ag.setColorAt(stop, QColor(r, g, b, a))
    p.setBrush(ag)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(ab)

    if tip:
        tr, tg, tb, ta = TEXT_TIP
        tf = QFont("Segoe UI", 12)
        tf.setItalic(True)
        p.setFont(tf)
        p.setPen(QColor(tr, tg, tb, ta))
        tip_rect = QRect((SPLASH_WIDTH - DID_YOU_KNOW_WIDTH_MAX) // 2, DID_YOU_KNOW_Y,
                         DID_YOU_KNOW_WIDTH_MAX, 20)
        p.drawText(tip_rect, Qt.AlignmentFlag.AlignCenter, tip)

    p.setClipping(False)
    p.end()
    return pixmap


class SplashScreen(QSplashScreen):
    _instance: SplashScreen | None = None

    def __init__(self, tip: str = ""):
        if not tip:
            tip = random.choice(TIPS)
        self._base = _build_base_pixmap(tip)
        super().__init__(self._base)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # self.setWindowOpacity removed — only the background has alpha
        self.setWindowFlags(SPLASH_WINDOW_FLAGS)
        self._progress = 0
        self._message = ""
        self._total_steps = 0
        self._current_step = 0
        pb_x = (SPLASH_WIDTH - PROGRESS_BAR_WIDTH) // 2
        pb_y = SPLASH_HEIGHT - PROGRESS_BAR_Y_OFFSET
        self._pb_rect = QRect(pb_x, pb_y, PROGRESS_BAR_WIDTH, PROGRESS_BAR_HEIGHT)
        SplashScreen._instance = self

    @classmethod
    def instance(cls):
        return cls._instance

    def set_total_steps(self, total: int):
        self._total_steps = total
        self._current_step = 0

    def advance(self, message: str = ""):
        self._current_step += 1
        if self._total_steps > 0:
            value = int(self._current_step * 100 / self._total_steps)
        else:
            value = 0
        self.set_progress(min(100, value), message)

    def set_progress(self, value: int, message: str = ""):
        self._progress = max(0, min(100, value))
        if message:
            self._message = message
        pix = self._base.copy()
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._pb_rect

        p.setPen(QPen(QColor(*PB_TRACK), 1))
        p.setBrush(QColor(*PB_TRACK_FILL))
        p.drawRoundedRect(r, PROGRESS_BAR_RADIUS, PROGRESS_BAR_RADIUS)

        if self._progress > 0:
            fw = int((r.width() - 2) * self._progress / 100)
            fill = QRect(r.x() + 1, r.y() + 1, fw, r.height() - 2)
            grad = QLinearGradient(fill.left(), 0, fill.right(), 0)
            for stop, r_, g_, b_, a_ in PB_FILL_COLORS:
                grad.setColorAt(stop, QColor(r_, g_, b_, a_))
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(fill, PROGRESS_FILL_RADIUS, PROGRESS_FILL_RADIUS)

        sr, sg, sb, sa = TEXT_STATUS
        mf = QFont("Segoe UI", 9)
        p.setFont(mf)
        p.setPen(QColor(sr, sg, sb, sa))
        msg_rect = QRect(STATUS_TEXT_MARGIN, SPLASH_HEIGHT - STATUS_TEXT_Y_OFFSET,
                         SPLASH_WIDTH - STATUS_TEXT_MARGIN * 2, 16)
        p.drawText(msg_rect, Qt.AlignmentFlag.AlignLeft, self._message)

        p.end()
        self.setPixmap(pix)

    @classmethod
    def show_message(cls, message: str):
        inst = cls._instance
        if inst is not None:
            inst.set_progress(inst._progress, message)
            inst.show()
            inst.raise_()
            QApplication.processEvents()

    @classmethod
    def hide_splash(cls):
        inst = cls._instance
        if inst is not None:
            inst.setVisible(False)


def _enable_acrylic(hwnd: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import c_long, POINTER, Structure, windll

        class ACCENTPOLICY(Structure):
            _fields_ = [
                ("AccentState", c_long),
                ("AccentFlags", c_long),
                ("GradientColor", c_long),
                ("AnimationId", c_long),
            ]

        class WINCOMPATTRDATA(Structure):
            _fields_ = [
                ("Attribute", c_long),
                ("Data", POINTER(ACCENTPOLICY)),
                ("SizeOfData", c_long),
            ]

        accent = ACCENTPOLICY()
        accent.AccentState = 4  # ACCENT_ENABLE_ACRYLIC_BLURBEHIND
        accent.AccentFlags = 2  # Allow layered window
        accent.GradientColor = 0x22101030  # ARGB dark tint
        accent.AnimationId = 0

        data = WINCOMPATTRDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)

        result = windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.pointer(data))
        return result != 0
    except Exception:
        return False


def show_splash():
    splash = SplashScreen()
    splash.show()
    _enable_acrylic(int(splash.winId()))
    return splash
