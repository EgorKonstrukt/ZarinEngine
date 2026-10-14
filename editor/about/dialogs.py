# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import platform
import random
import sys
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QTextEdit, QApplication
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QKeyEvent
from PyQt6.QtCore import Qt, QTimer
from core.config.constants import APP_VERSION_DISPLAY
from editor.about.system_info import _read_engine_optimization, _render_logo, _render_icon, _collect_system_info
MPL_URL = "https://mozilla.org/MPL/2.0/"
LOGO_W = 256
_EASTER_CLICKS_NEEDED = 10
_COLS = 20
_ROWS = 15
_CELL = 22
_TICK_MS = 110
_DIR = {
    Qt.Key.Key_Up: (0, -1),
    Qt.Key.Key_Down: (0, 1),
    Qt.Key.Key_Left: (-1, 0),
    Qt.Key.Key_Right: (1, 0),
}
_OPPOSITE = {
    Qt.Key.Key_Up: Qt.Key.Key_Down,
    Qt.Key.Key_Down: Qt.Key.Key_Up,
    Qt.Key.Key_Left: Qt.Key.Key_Right,
    Qt.Key.Key_Right: Qt.Key.Key_Left,
}
_BG = QColor(24, 24, 28)
_GRID = QColor(30, 30, 36)
_SNAKE_HEAD = QColor(70, 180, 100)
_SNAKE_BODY = QColor(50, 140, 75)
_FOOD = QColor(220, 60, 60)
_TEXT = QColor(200, 200, 210)


class _SnakeGame(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zarin Snake")
        self.setFixedSize(_COLS * _CELL + 2, _ROWS * _CELL + 2)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._head_pm = _render_icon(_CELL)
        self._reset()

    def _reset(self):
        mid_x, mid_y = _COLS // 2, _ROWS // 2
        self._snake = [(mid_x - i, mid_y) for i in range(4)]
        self._dir = (1, 0)
        self._next_dir = (1, 0)
        self._alive = True
        self._score = 0
        self._spawn_food()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_TICK_MS)

    def _spawn_food(self):
        while True:
            pos = (random.randint(0, _COLS - 1), random.randint(0, _ROWS - 1))
            if pos not in self._snake:
                self._food = pos
                return

    def keyPressEvent(self, e: QKeyEvent):
        nd = _DIR.get(e.key())
        if nd is None:
            return
        dx, dy = self._dir
        if nd != (-dx, -dy):
            self._next_dir = nd

    def _tick(self):
        if not self._alive:
            return
        self._dir = self._next_dir
        hx, hy = self._snake[0]
        dx, dy = self._dir
        nx, ny = hx + dx, hy + dy
        if nx < 0 or nx >= _COLS or ny < 0 or ny >= _ROWS:
            return self._die()
        if (nx, ny) in self._snake:
            return self._die()
        self._snake.insert(0, (nx, ny))
        if (nx, ny) == self._food:
            self._score += 1
            self._spawn_food()
        else:
            self._snake.pop()
        self.update()

    def _die(self):
        self._alive = False
        self._timer.stop()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0, 0, self.width(), self.height(), _BG)
        for x in range(_COLS + 1):
            p.setPen(_GRID)
            p.drawLine(x * _CELL, 0, x * _CELL, _ROWS * _CELL)
        for y in range(_ROWS + 1):
            p.setPen(_GRID)
            p.drawLine(0, y * _CELL, _COLS * _CELL, y * _CELL)
        fx, fy = self._food
        p.setBrush(_FOOD)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(fx * _CELL + 2, fy * _CELL + 2, _CELL - 4, _CELL - 4)
        for i, (sx, sy) in enumerate(self._snake):
            if i == 0 and self._head_pm is not None:
                p.drawPixmap(sx * _CELL, sy * _CELL, self._head_pm)
            else:
                c = _SNAKE_BODY
                p.setBrush(c)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(sx * _CELL + 1, sy * _CELL + 1, _CELL - 2, _CELL - 2, 4, 4)
        if not self._alive:
            p.setPen(QPen(_TEXT, 1))
            p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       f"Game Over!\nScore: {self._score}\n\nPress Space to restart")
        p.end()

    def keyReleaseEvent(self, e: QKeyEvent):
        if not self._alive and e.key() == Qt.Key.Key_Space:
            self._reset()

    def closeEvent(self, e):
        self._timer.stop()
        super().closeEvent(e)


class _SystemInfoDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Info")
        self.setFixedSize(640, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        lbl = QLabel("Full system information for debugging:")
        root.addWidget(lbl)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        te.setFont(QFont("Consolas", 9))
        te.setStyleSheet("QTextEdit { background: rgb(30, 30, 30); color: rgb(212, 212, 212); border: 1px solid rgb(85, 85, 85); }")
        te.setTabStopDistance(te.fontMetrics().horizontalAdvance(" ") * 4)
        root.addWidget(te)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setFixedWidth(150)
        copy_btn.clicked.connect(lambda: (QApplication.clipboard().setText(text), copy_btn.setText("Copied!"),
                                          QTimer.singleShot(1500, lambda: copy_btn.setText("Copy to Clipboard"))))
        btn_row.addWidget(copy_btn)
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Zarin Engine")
        self.setFixedWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._logo_clicks = 0
        self._gpu_name = self._detect_gpu(parent)
        self._setup_ui()

    @staticmethod
    def _detect_gpu(parent) -> str:
        try:
            vp = getattr(parent, '_viewport', None)
            if vp is not None:
                info = getattr(vp, '_gl_info_cache', None)
                if info:
                    return info.get("GL_RENDERER", "Unknown")
        except Exception:
            pass
        return "Unknown"

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(20, 20, 20, 16)
        logo_pm = _render_logo(LOGO_W)
        if logo_pm is not None:
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_pm)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            logo_lbl.mousePressEvent = self._on_logo_click
            root.addWidget(logo_lbl)
        ver = QLabel(APP_VERSION_DISPLAY)
        ver.setFont(QFont("Segoe UI", 9))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(ver)
        root.addWidget(self._hline())
        desc = QLabel(
            "A high-performance 64-bit ECS 3D engine with\n"
            "plugin-based architecture, real-time rendering,\n"
            "and a full-featured editor."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(desc)
        root.addWidget(self._hline())
        gil_enabled = getattr(sys, '_is_gil_enabled', lambda: True)()
        gil_status = "No (nogil)" if not gil_enabled else "Yes"
        jit_enabled = getattr(sys, '_jit_enabled', False)
        jit_status = "Active" if jit_enabled else "Off"
        flags = sys.flags
        debug_flag = "on" if flags.debug else "off"
        optimize_flag = flags.optimize
        dev_mode = getattr(flags, 'dev_mode', False)
        isolated = getattr(flags, 'isolated', False)
        utf8 = getattr(flags, 'utf8_mode', False)
        eng_cfg = _read_engine_optimization()
        jit_cfg = bool(eng_cfg.get("python_jit", False))
        opt_cfg = int(eng_cfg.get("python_optimize", 0))
        unbuf_cfg = bool(eng_cfg.get("python_unbuffered", False))
        nobc_cfg = bool(eng_cfg.get("python_no_bytecode", False))
        info = QLabel(
            f"<b>Plugins:</b> {self._count_plugins()} loaded<br>"
            f"<b>System:</b> {platform.system()} {platform.machine()}<br>"
            f"<b>Python:</b> {sys.version.split()[0]}<br>"
            f"<b>JIT:</b> {jit_status} (cfg: {'on' if jit_cfg else 'off'})<br>"
            f"<b>GIL:</b> {gil_status}<br>"
            f"<b>Debug:</b> {debug_flag} &nbsp; <b>Optimize:</b> {optimize_flag} (cfg: {opt_cfg})<br>"
            f"<b>Unbuffered:</b> {'on' if unbuf_cfg else 'off'} &nbsp; "
            f"<b>No-Bytecode:</b> {'on' if nobc_cfg else 'off'}<br>"
            f"<b>Dev:</b> {dev_mode} &nbsp; <b>Isolated:</b> {isolated} &nbsp; <b>UTF-8:</b> {utf8}<br>"
            f"<b>Interpreter:</b> {os.path.basename(sys.executable)}<br>"
            f"<b>Renderer:</b> OpenGL 4.6 Core Profile<br>"
            f"<b>GPU:</b> {self._gpu_name}"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(info)
        root.addWidget(self._hline())
        copy_lbl = QLabel("Copyright © 2026 Zarrakun")
        copy_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(copy_lbl)
        lic_lbl = QLabel(
            f'Licensed under the <a href="{MPL_URL}">Mozilla Public License 2.0</a>'
        )
        lic_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lic_lbl.setOpenExternalLinks(True)
        root.addWidget(lic_lbl)
        root.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        info_btn = QPushButton("System Info")
        info_btn.setFixedWidth(110)
        info_btn.clicked.connect(self._open_system_info)
        btn_row.addWidget(info_btn)
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _on_logo_click(self, _event):
        self._logo_clicks += 1
        if self._logo_clicks >= _EASTER_CLICKS_NEEDED:
            self._logo_clicks = 0
            dlg = _SnakeGame(self)
            dlg.exec()

    def _open_system_info(self):
        text = _collect_system_info(self.parent())
        dlg = _SystemInfoDialog(text, self)
        dlg.exec()

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    @staticmethod
    def _count_plugins() -> int:
        plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "plugins")
        try:
            return len([d for d in os.listdir(plugins_dir)
                        if os.path.isdir(os.path.join(plugins_dir, d)) and not d.startswith("_")])
        except FileNotFoundError:
            return 0
