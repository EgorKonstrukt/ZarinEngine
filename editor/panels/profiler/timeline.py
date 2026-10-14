# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import hashlib
from collections import deque
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QFontMetrics, QPalette
from core.config.editor_scale import scale


def _name_to_color(name: str) -> QColor:
    key = name.replace("_ms", "").replace("_", "").replace(" ", "").strip().lower()
    known = {
        "frame": (128, 128, 128),
        "tick": (66, 116, 200),
        "update": (66, 116, 200),
        "fixedupdate": (66, 116, 200),
        "game_tick": (66, 116, 200),
        "game_input": (126, 87, 194),
        "game_render": (230, 126, 34),
        "inputhandling": (126, 87, 194),
        "input_handling": (126, 87, 194),
        "editorupdate": (41, 182, 246),
        "editor_update": (41, 182, 246),
        "camupdate": (41, 182, 246),
        "cam_update": (41, 182, 246),
        "gizmoupdate": (255, 183, 77),
        "gizmo_update": (255, 183, 77),
        "editorparticles": (171, 71, 188),
        "editor_particles": (171, 71, 188),
        "sceneupdate": (56, 142, 60),
        "scene_update": (56, 142, 60),
        "scenefixedupdate": (56, 142, 60),
        "scene_fixed_update": (56, 142, 60),
        "constraints": (56, 142, 60),
        "components": (66, 165, 245),
        "ik": (38, 198, 218),
        "render": (230, 126, 34),
        "renderscene": (230, 126, 34),
        "rendermeshes": (230, 126, 34),
        "renderskybox": (230, 126, 34),
        "rendershadowpass": (200, 100, 30),
        "renderoverlay": (200, 150, 40),
        "rendergrid": (120, 144, 156),
        "renderstats": (120, 144, 156),
        "rendergraphicseffects": (142, 80, 180),
        "glsetup": (200, 120, 80),
        "glstatesetup": (200, 120, 80),
        "gizmos": (200, 150, 40),
        "overlaydraw": (40, 150, 200),
        "overlay_draw": (40, 150, 200),
        "physics": (70, 130, 200),
        "physicsstep": (70, 130, 200),
        "physics_step": (70, 130, 200),
        "meshasyncload": (130, 110, 200),
        "processpendingtextures": (130, 110, 200),
        "rendertextworld": (80, 150, 90),
        "rendersprites": (80, 150, 90),
        "rendervideos": (80, 150, 90),
        "playviewport": (70, 130, 200),
        "play_viewport": (70, 130, 200),
        "playcameras": (41, 182, 246),
        "play_cameras": (41, 182, 246),
        "playguisync": (38, 198, 218),
        "play_gui_sync": (38, 198, 218),
        "unaccounted": (130, 130, 130),
    }
    if key in known:
        r, g, b = known[key]
        return QColor(r, g, b)
    if not key:
        return QColor(140, 140, 140)
    h = int(hashlib.md5(key.encode()).hexdigest()[:6], 16)
    return QColor.fromHsl(h % 360, 45, 55)

def _name_to_hex(name: str) -> str:
    return _name_to_color(name).name()

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)
_FONT_TINY = QFont("Segoe UI", 7)
_FONT_LARGE = QFont("Segoe UI", 13, QFont.Weight.Bold)
_FONT_MED = QFont("Segoe UI", 10, QFont.Weight.DemiBold)


class TimelineOverview(QWidget):
    HEIGHT = 64
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames_data: deque[dict] = deque(maxlen=300)
        self._selected_index = -1
        self._hover_index = -1
        self._budget_ms = 16.67
        self.setMouseTracking(True)
        self.setFixedHeight(scale(self.HEIGHT))
        self.setMinimumWidth(100)
    def add_frame(self, flat_data: dict, frame_time_ms: float):
        self._frames_data.append({"flat": dict(flat_data), "total": frame_time_ms})
        self.update()
    def clear_data(self):
        self._frames_data.clear()
        self._selected_index = -1
        self._hover_index = -1
        self.update()
    def _bar_color(self, total: float) -> QColor:
        if total <= self._budget_ms:
            return QColor(76, 175, 80)
        if total <= self._budget_ms * 2.0:
            return QColor(245, 150, 30)
        return QColor(211, 80, 80)
    def paintEvent(self, event):
        p = QPainter(self)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        txt = pal.color(QPalette.ColorRole.Text)
        mut = pal.color(QPalette.ColorRole.PlaceholderText)
        hl = pal.color(QPalette.ColorRole.Highlight)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, base)
        n = len(self._frames_data)
        if n == 0:
            p.setPen(mut)
            p.setFont(_FONT_SMALL)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No frame data")
            p.end()
            return
        for frac in (0.25, 0.5, 0.75):
            y = int(h * (1.0 - frac))
            p.setPen(QPen(mid, 1))
            p.drawLine(0, y, w, y)
        y_max = self._budget_ms * 1.4
        for d in self._frames_data:
            if d["total"] > y_max:
                y_max = d["total"]
        if y_max < 8.0:
            y_max = 8.0
        bar_w = w // max(n, 1)
        if bar_w > 9:
            bar_w = 9
        if bar_w < 2:
            bar_w = 2
        gap = 1 if bar_w > 3 else 0
        step = bar_w + gap
        self._bar_w = step
        total_w = n * step
        offset = max(0, total_w - w)
        budget_y = int(h - (h * min(self._budget_ms / y_max, 1.0)))
        hlc = QColor(hl.red(), hl.green(), hl.blue(), 150)
        p.setPen(QPen(hlc, 1, Qt.PenStyle.DashLine))
        p.drawLine(0, budget_y, w, budget_y)
        lbl = str(round(self._budget_ms, 1)) + "ms"
        p.setPen(mut)
        p.setFont(_FONT_TINY)
        p.drawText(w - 52, max(2, budget_y - 15), 48, 13, Qt.AlignmentFlag.AlignRight, lbl)
        for i, d in enumerate(self._frames_data):
            x = i * step - offset
            if x < -step or x > w:
                continue
            total = d["total"]
            bar_h = max(2, int((total / y_max) * (h - 6)))
            y0 = h - bar_h - 2
            base_c = self._bar_color(total)
            if i == self._selected_index:
                c = base_c.lighter(118)
            elif i == self._hover_index:
                c = base_c.lighter(108)
            else:
                c = base_c
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.fillRect(x, y0, bar_w, bar_h, c)
            if i == self._selected_index:
                p.setPen(QPen(txt, 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(x, y0, bar_w, bar_h)
        if self._hover_index >= 0 and self._hover_index < n:
            d = self._frames_data[self._hover_index]
            ms = d["total"]
            fps = 1000.0 / ms if ms > 0.001 else 0.0
            info = "Frame " + str(self._hover_index) + "  " + format(ms, ".2f") + "ms  " + format(fps, ".0f") + " FPS"
            fm = QFontMetrics(_FONT_SMALL)
            tw = fm.horizontalAdvance(info) + 16
            tx = self._hover_index * step - offset - tw // 2
            if tx < 4:
                tx = 4
            if tx + tw > w - 4:
                tx = w - tw - 4
            p.setPen(QPen(mid, 1))
            tip = QColor(base)
            tip.setAlpha(235)
            p.setBrush(QBrush(tip))
            p.drawRoundedRect(tx, 4, tw, 19, 4, 4)
            p.setPen(txt)
            p.setFont(_FONT_SMALL)
            p.drawText(tx, 4, tw, 19, Qt.AlignmentFlag.AlignCenter, info)
        p.end()
    def mouseMoveEvent(self, event):
        x = event.position().x()
        n = len(self._frames_data)
        step = getattr(self, "_bar_w", 4)
        if step <= 0:
            step = 4
        w = self.width()
        total_w = n * step
        offset = max(0, total_w - w)
        idx = (int(x) + offset) // step if step > 0 else -1
        if 0 <= idx < n:
            self._hover_index = idx
        else:
            self._hover_index = -1
        self.update()
    def mousePressEvent(self, event):
        x = event.position().x()
        n = len(self._frames_data)
        step = getattr(self, "_bar_w", 4)
        if step <= 0:
            step = 4
        w = self.width()
        total_w = n * step
        offset = max(0, total_w - w)
        idx = (int(x) + offset) // step if step > 0 else -1
        if 0 <= idx < n:
            self._selected_index = idx
            parent_panel = self.parent()
            while parent_panel and not hasattr(parent_panel, "_select_frame"):
                parent_panel = parent_panel.parent()
            if parent_panel:
                parent_panel._select_frame(idx)
        self.update()
    def leaveEvent(self, event):
        self._hover_index = -1
        self.update()


class TimelineWidget(QWidget):
    MAX_SAMPLES = 300
    def __init__(self, parent=None):
        super().__init__(parent)
        self._series: dict[str, deque] = {}
        self._colors: dict[str, QColor] = {}
        self._total_frames = 0
        self.setMinimumHeight(120)
    def add_frame(self, flat_data: dict[str, float]):
        self._total_frames += 1
        if not flat_data:
            self.update()
            return
        for key, val in flat_data.items():
            if key not in self._series:
                self._colors[key] = _name_to_color(key)
                self._series[key] = deque(maxlen=self.MAX_SAMPLES)
            self._series[key].append(val)
        for key in list(self._series.keys()):
            if key not in flat_data:
                self._series[key].append(0.0)
        self.update()
    def clear_data(self):
        self._series.clear()
        self._colors.clear()
        self._total_frames = 0
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        mut = pal.color(QPalette.ColorRole.PlaceholderText)
        hl = pal.color(QPalette.ColorRole.Highlight)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, base)
        margin = 46
        plot_w = w - margin * 2
        plot_h = h - margin * 2
        if plot_w < 10 or plot_h < 10:
            p.end()
            return
        if not self._series:
            p.setPen(mut)
            p.setFont(_FONT)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No timeline data")
            p.end()
            return
        p.setPen(QPen(mid, 1))
        for i in range(5):
            y = margin + plot_h * (1.0 - i * 0.25)
            p.drawLine(margin, int(y), w - margin, int(y))
        p.setPen(mut)
        p.setFont(_FONT_SMALL)
        for i in range(5):
            val = i * 0.25 * 33.33
            p.drawText(4, int(margin + plot_h * (1.0 - i * 0.25) + 3), format(val, ".0f") + "ms")
        budget_y = margin + plot_h * (1.0 - 16.67 / 33.33)
        hlc = QColor(hl.red(), hl.green(), hl.blue(), 130)
        p.setPen(QPen(hlc, 1, Qt.PenStyle.DashLine))
        p.drawLine(margin, int(budget_y), w - margin, int(budget_y))
        p.setPen(hl)
        p.setFont(_FONT_TINY)
        p.drawText(w - margin - 44, int(budget_y) - 4, "16.67ms")
        global_max = 0.1
        for key, data in self._series.items():
            if data:
                m = max(data)
                if m > global_max:
                    global_max = m
        y_max = global_max * 1.2
        if y_max < 16.67:
            y_max = 16.67
        keys = sorted(self._series.keys(), key=lambda k: max(self._series[k]) if self._series[k] else 0.0, reverse=True)[:8]
        for key in keys:
            data = self._series.get(key)
            if data is None or len(data) < 2:
                continue
            color = self._colors.get(key, pal.color(QPalette.ColorRole.Text))
            n = len(data)
            pts = []
            for i, val in enumerate(data):
                px = margin + (plot_w * i / max(n - 1, 1))
                py = margin + plot_h * (1.0 - val / y_max)
                pts.append(QPointF(px, py))
            pen = QPen(color, 1.6)
            p.setPen(pen)
            for i in range(1, len(pts)):
                p.drawLine(pts[i-1], pts[i])
        legend_x = margin
        legend_y = h - margin + 6
        p.setFont(_FONT_SMALL)
        for key in keys:
            if legend_x + 130 < w:
                color = self._colors.get(key, pal.color(QPalette.ColorRole.Text))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(color))
                p.drawRoundedRect(legend_x, legend_y, 8, 8, 2, 2)
                p.setPen(mut)
                label = key.replace("_ms", "").replace("_", " ").title()
                p.drawText(legend_x + 11, legend_y - 2, 120, 12, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
                fm = QFontMetrics(_FONT_SMALL)
                legend_x += fm.horizontalAdvance(label) + 30
        p.end()
