# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from plugins.qt_quick_plugin.runtime.qml import QImage, QPainter, QColor, QFont, QPen, QBrush, Qt, _view_key, _color_to_qcolor, _HAS_QT

class BridgeMixin:
    def _paint_fallback(self, comp, w: int, h: int):
        try:
            if not _HAS_QT or QImage is None:
                return None
            img = QImage(int(w), int(h), QImage.Format.Format_RGBA8888)
            try:
                img.fill(Qt.GlobalColor.transparent)
            except Exception:
                try:
                    img.fill(0)
                except Exception:
                    pass
            try:
                painter = QPainter(img)
            except Exception:
                return img
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                self._draw_fallback(painter, comp, int(w), int(h))
            except Exception:
                pass
            try:
                painter.end()
            except Exception:
                pass
            return img
        except Exception:
            return None

    def _draw_fallback(self, painter, comp, w: int, h: int):
        cname = type(comp).__name__
        try:
            painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 0))
        except Exception:
            pass
        if cname == "QuickButton":
            self._fallback_button(painter, comp, w, h)
        elif cname == "QuickLabel":
            self._fallback_label(painter, comp, w, h)
        elif cname == "QuickSlider":
            self._fallback_slider(painter, comp, w, h)
        elif cname == "QuickTextField":
            self._fallback_textfield(painter, comp, w, h)
        elif cname == "QuickCheckBox":
            self._fallback_checkbox(painter, comp, w, h)
        elif cname == "QuickProgressBar":
            self._fallback_progress(painter, comp, w, h)
        elif cname == "QuickSwitch":
            self._fallback_switch(painter, comp, w, h)
        elif cname == "QuickDial":
            self._fallback_dial(painter, comp, w, h)
        elif cname == "QuickComboBox":
            self._fallback_combo(painter, comp, w, h)
        elif cname == "QuickSpinBox":
            self._fallback_spin(painter, comp, w, h)
        elif cname == "QuickImageView":
            self._fallback_image(painter, comp, w, h)
        else:
            self._fallback_panel(painter, comp, w, h)

    def _round_bg(self, painter, w: int, h: int, fill, border, radius: int, border_w: int = 2):
        try:
            painter.setPen(QPen(QColor(border), border_w))
            painter.setBrush(QBrush(QColor(fill)))
            painter.drawRoundedRect(1, 1, max(2, w - 2), max(2, h - 2), radius, radius)
        except Exception:
            pass

    def _draw_text_center(self, painter, text: str, w: int, h: int, size: int, color):
        try:
            font = QFont("Segoe UI", max(8, int(size)))
            painter.setFont(font)
            painter.setPen(QPen(QColor(color)))
            painter.drawText(0, 0, w, h, int(Qt.AlignmentFlag.AlignCenter), str(text))
        except Exception:
            pass

    def _fallback_button(self, painter, comp, w: int, h: int):
        try:
            down = False
            try:
                down = bool(getattr(comp, "checked", False)) and bool(getattr(comp, "checkable", False))
            except Exception:
                down = False
            fill = QColor(58, 123, 213, 255) if not down else QColor(36, 90, 170, 255)
            self._round_bg(painter, w, h, fill, QColor(220, 230, 245, 255), 14, 2)
            try:
                label = str(getattr(comp, "text", "Button"))
            except Exception:
                label = "Button"
            try:
                size = int(getattr(comp, "font_size", 28) * h / 160) + 10
            except Exception:
                size = 16
            self._draw_text_center(painter, label, w, h, max(10, min(48, size)), QColor(255, 255, 255, 255))
        except Exception:
            pass

    def _fallback_label(self, painter, comp, w: int, h: int):
        try:
            label = str(getattr(comp, "text", "Label"))
        except Exception:
            label = "Label"
        try:
            size = int(getattr(comp, "font_size", 32))
        except Exception:
            size = 32
        try:
            col = _color_to_qcolor(getattr(comp, "text_color", [1, 1, 1, 1]))
        except Exception:
            col = QColor(255, 255, 255, 255)
        try:
            font = QFont("Segoe UI", max(8, size * h // 128 if h >= 64 else size))
            painter.setFont(font)
            painter.setPen(QPen(col))
            painter.drawText(4, 4, max(8, w - 8), max(8, h - 8), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
        except Exception:
            pass

    def _fallback_slider(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(30, 32, 38, 220), QColor(90, 100, 115, 255), 12, 1)
            try:
                lo = float(getattr(comp, "minimum", 0.0))
                hi = float(getattr(comp, "maximum", 1.0))
                vv = float(getattr(comp, "value", 0.5))
            except Exception:
                lo, hi, vv = 0.0, 1.0, 0.5
            span = hi - lo
            t = (vv - lo) / span if abs(span) > 1e-9 else 0.0
            t = max(0.0, min(1.0, t))
            gy = h // 2 - 4
            try:
                painter.setPen(QPen(QColor(0, 0, 0, 0)))
                painter.setBrush(QBrush(QColor(70, 78, 92, 255)))
                painter.drawRoundedRect(16, gy, max(4, w - 32), 8, 4, 4)
                painter.setBrush(QBrush(QColor(70, 160, 240, 255)))
                painter.drawRoundedRect(16, gy, max(4, int((w - 32) * t)), 8, 4, 4)
                hx = 16 + int((w - 32) * t)
                painter.setBrush(QBrush(QColor(240, 244, 250, 255)))
                painter.setPen(QPen(QColor(40, 50, 65, 255), 2))
                painter.drawEllipse(hx - 14, h // 2 - 14, 28, 28)
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_textfield(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(245, 246, 248, 255), QColor(120, 130, 145, 255), 10, 2)
            try:
                label = str(getattr(comp, "text", ""))
                ph = str(getattr(comp, "placeholder", ""))
            except Exception:
                label, ph = "", ""
            show = label if label else ph
            try:
                col = QColor(20, 22, 28, 255) if label else QColor(130, 138, 150, 255)
            except Exception:
                col = QColor(20, 22, 28, 255)
            try:
                painter.setFont(QFont("Segoe UI", max(10, h // 4)))
                painter.setPen(QPen(col))
                painter.drawText(12, 4, max(8, w - 24), max(8, h - 8), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), show)
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_checkbox(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(30, 32, 38, 220), QColor(90, 100, 115, 255), 12, 1)
            try:
                checked = bool(getattr(comp, "checked", False))
                label = str(getattr(comp, "text", "Check"))
            except Exception:
                checked, label = False, "Check"
            box = min(w, h) - 32
            if box < 16:
                box = 16
            bx, by = 16, (h - box) // 2
            try:
                painter.setPen(QPen(QColor(200, 210, 225, 255), 2))
                painter.setBrush(QBrush(QColor(245, 246, 248, 255)))
                painter.drawRoundedRect(bx, by, box, box, 6, 6)
                if checked:
                    painter.setPen(QPen(QColor(40, 140, 70, 255), 4))
                    painter.drawLine(bx + 6, by + box // 2, bx + box // 2, by + box - 6)
                    painter.drawLine(bx + box // 2, by + box - 6, bx + box - 6, by + 6)
                painter.setFont(QFont("Segoe UI", max(10, h // 4)))
                painter.setPen(QPen(QColor(240, 244, 250, 255)))
                painter.drawText(bx + box + 12, 0, max(8, w - bx - box - 16), h, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_progress(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(30, 32, 38, 220), QColor(90, 100, 115, 255), 12, 1)
            try:
                lo = float(getattr(comp, "minimum", 0.0))
                hi = float(getattr(comp, "maximum", 1.0))
                vv = float(getattr(comp, "value", 0.5))
            except Exception:
                lo, hi, vv = 0.0, 1.0, 0.5
            span = hi - lo
            t = (vv - lo) / span if abs(span) > 1e-9 else 0.0
            t = max(0.0, min(1.0, t))
            try:
                painter.setPen(QPen(QColor(0, 0, 0, 0)))
                painter.setBrush(QBrush(QColor(60, 180, 110, 255)))
                painter.drawRoundedRect(8, 8, max(4, int((w - 16) * t)), max(4, h - 16), 8, 8)
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_switch(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(30, 32, 38, 220), QColor(90, 100, 115, 255), 14, 1)
            try:
                checked = bool(getattr(comp, "checked", False))
                label = str(getattr(comp, "text", "Switch"))
            except Exception:
                checked, label = False, "Switch"
            tw = min(w - 24, 120)
            th = min(h - 24, 48)
            tx, ty = 16, (h - th) // 2
            try:
                painter.setPen(QPen(QColor(0, 0, 0, 0)))
                painter.setBrush(QBrush(QColor(70, 180, 110, 255) if checked else QColor(90, 98, 112, 255)))
                painter.drawRoundedRect(tx, ty, tw, th, th // 2, th // 2)
                knob = th - 8
                kx = tx + tw - knob - 4 if checked else tx + 4
                painter.setBrush(QBrush(QColor(245, 246, 248, 255)))
                painter.drawEllipse(kx, ty + 4, knob, knob)
                painter.setFont(QFont("Segoe UI", max(10, h // 4)))
                painter.setPen(QPen(QColor(240, 244, 250, 255)))
                painter.drawText(tx + tw + 12, 0, max(8, w - tx - tw - 16), h, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_dial(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(30, 32, 38, 220), QColor(90, 100, 115, 255), 16, 1)
            try:
                lo = float(getattr(comp, "minimum", 0.0))
                hi = float(getattr(comp, "maximum", 1.0))
                vv = float(getattr(comp, "value", 0.5))
            except Exception:
                lo, hi, vv = 0.0, 1.0, 0.5
            span = hi - lo
            t = (vv - lo) / span if abs(span) > 1e-9 else 0.0
            t = max(0.0, min(1.0, t))
            side = min(w, h) - 24
            cx, cy = w // 2, h // 2
            import math

            ang = math.pi * 0.75 + t * math.pi * 1.5
            nx = cx + math.cos(ang) * side * 0.32
            ny = cy + math.sin(ang) * side * 0.32
            try:
                painter.setPen(QPen(QColor(70, 160, 240, 255), 8))
                painter.drawEllipse(cx - side // 2, cy - side // 2, side, side)
                painter.setPen(QPen(QColor(245, 246, 248, 255), 6))
                painter.drawLine(cx, cy, int(nx), int(ny))
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_combo(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(245, 246, 248, 255), QColor(120, 130, 145, 255), 10, 2)
            try:
                items = comp.get_items() if hasattr(comp, "get_items") else []
                idx = int(getattr(comp, "current_index", 0))
            except Exception:
                items, idx = [], 0
            label = ""
            try:
                if items:
                    label = str(items[max(0, min(idx, len(items) - 1))])
            except Exception:
                label = ""
            try:
                painter.setFont(QFont("Segoe UI", max(10, h // 4)))
                painter.setPen(QPen(QColor(20, 22, 28, 255)))
                painter.drawText(12, 0, max(8, w - 60), h, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
                painter.drawText(max(8, w - 48), 0, 40, h, int(Qt.AlignmentFlag.AlignCenter), "v")
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_spin(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(245, 246, 248, 255), QColor(120, 130, 145, 255), 10, 2)
            try:
                label = str(int(getattr(comp, "value", 0)))
            except Exception:
                label = "0"
            try:
                painter.setFont(QFont("Segoe UI", max(10, h // 4)))
                painter.setPen(QPen(QColor(20, 22, 28, 255)))
                painter.drawText(0, 0, max(8, w - 64), h, int(Qt.AlignmentFlag.AlignCenter), label)
                painter.drawText(max(8, w - 64), 0, 30, h // 2, int(Qt.AlignmentFlag.AlignCenter), "^")
                painter.drawText(max(8, w - 64), h // 2, 30, h // 2, int(Qt.AlignmentFlag.AlignCenter), "v")
            except Exception:
                pass
        except Exception:
            pass

    def _fallback_image(self, painter, comp, w: int, h: int):
        try:
            self._round_bg(painter, w, h, QColor(24, 26, 32, 230), QColor(90, 100, 115, 255), 8, 1)
            src = ""
            try:
                src = str(getattr(comp, "image_source", "") or "")
            except Exception:
                src = ""
            loaded = False
            if src:
                try:
                    import os

                    path = src
                    if not os.path.isabs(path):
                        try:
                            from core.engine.eng import Engine

                            eng = Engine.instance()
                            base = getattr(eng, "_project_path", "") or ""
                            if base:
                                cand = os.path.join(base, path)
                                if os.path.isfile(cand):
                                    path = cand
                        except Exception:
                            pass
                    if os.path.isfile(path):
                        pm = QImage(path)
                        if not pm.isNull():
                            painter.drawImage(4, 4, pm.scaled(w - 8, h - 8, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                            loaded = True
                except Exception:
                    loaded = False
            if not loaded:
                try:
                    painter.setPen(QPen(QColor(120, 160, 200, 255), 3))
                    painter.drawLine(8, 8, w - 8, h - 8)
                    painter.drawLine(w - 8, 8, 8, h - 8)
                    painter.setFont(QFont("Segoe UI", 12))
                    painter.setPen(QPen(QColor(200, 210, 225, 255)))
                    painter.drawText(0, 0, w, h, int(Qt.AlignmentFlag.AlignCenter), "Image")
                except Exception:
                    pass
        except Exception:
            pass

    def _fallback_panel(self, painter, comp, w: int, h: int):
        try:
            fill = QColor(40, 45, 55, 235)
            try:
                fill = _color_to_qcolor(getattr(comp, "panel_color", [0.16, 0.18, 0.22, 0.92]))
            except Exception:
                pass
            try:
                radius = int(getattr(comp, "radius", 18))
            except Exception:
                radius = 18
            self._round_bg(painter, w, h, fill, QColor(150, 170, 195, 255), max(0, radius), 2)
            try:
                title = str(getattr(comp, "title", "Panel"))
            except Exception:
                title = "Panel"
            if title:
                self._draw_text_center(painter, title, w, h, max(12, h // 8), QColor(255, 255, 255, 255))
        except Exception:
            pass

    def set_focus(self, comp):
        try:
            self._focused_key = _view_key(comp) if comp is not None else ""
        except Exception:
            self._focused_key = ""

    def focused(self):
        try:
            rec = self._records.get(self._focused_key)
            if rec is not None:
                return rec.get("comp")
        except Exception:
            pass
        return None

