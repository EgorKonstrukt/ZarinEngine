# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import hashlib

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QUrl, QObject, QCoreApplication, QPointF, Qt
    from PyQt6.QtGui import QImage, QPainter, QColor, QFont, QPen, QBrush, QMouseEvent, QWheelEvent, QKeyEvent
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QApplication = None
    QUrl = None
    QObject = object
    QCoreApplication = None
    QPointF = None
    Qt = None
    QImage = None
    QPainter = None
    QColor = None
    QFont = None
    QPen = None
    QBrush = None
    QMouseEvent = None
    QWheelEvent = None
    QKeyEvent = None

try:
    from PyQt6.QtQml import QQmlEngine, QQmlComponent
    from PyQt6.QtQuick import QQuickWindow
    _HAS_QUICK = _HAS_QT
except Exception:
    QQmlEngine = None
    QQmlComponent = None
    QQuickWindow = None
    _HAS_QUICK = False


def _app_available() -> bool:
    if not _HAS_QT:
        return False
    try:
        return QApplication.instance() is not None
    except Exception:
        return False


def _view_key(comp) -> str:
    try:
        ent = getattr(comp, "_entity", None)
        key = getattr(comp, "_key", "")
        if ent is not None and getattr(ent, "id", ""):
            return str(ent.id) + "|" + str(key)
    except Exception:
        pass
    return "addr|" + str(id(comp))


def _align_to_int(value) -> int:
    s = str(value).lower()
    if s == "center":
        return 4
    if s == "right":
        return 2
    return 1


def _fill_to_int(value) -> int:
    order = ["Stretch", "Fit", "Crop", "Tile", "Pad"]
    try:
        return order.index(str(value))
    except Exception:
        return 1


def _color_to_qcolor(value):
    try:
        if isinstance(value, str):
            return QColor(str(value))
        seq = list(value)
        if len(seq) >= 4:
            return QColor.fromRgbF(float(seq[0]), float(seq[1]), float(seq[2]), float(seq[3]))
        if len(seq) == 3:
            return QColor.fromRgbF(float(seq[0]), float(seq[1]), float(seq[2]), 1.0)
    except Exception:
        pass
    try:
        return QColor(255, 255, 255, 255)
    except Exception:
        return None


class QuickRuntime:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = QuickRuntime()
        return cls._instance

    def __init__(self):
        self._engine = None
        self._qml_engine = None
        self._records: dict = {}
        self._focused_key: str = ""
        self._hover_key: str = ""
        self._qml_ok: bool = _HAS_QUICK

    def attach(self, engine):
        self._engine = engine

    def clear_scene(self):
        drop = []
        try:
            scene = getattr(self._engine, "scene", None) if self._engine is not None else None
            alive = set()
            if scene is not None:
                for ent in scene.get_all_entities():
                    alive.add(ent.id)
            for key, rec in self._records.items():
                comp = rec.get("comp")
                try:
                    ent = getattr(comp, "_entity", None)
                    eid = getattr(ent, "id", None) if ent is not None else None
                    if eid is None or eid not in alive:
                        drop.append(key)
                except Exception:
                    drop.append(key)
        except Exception:
            drop = []
        for key in drop:
            self._destroy_record(key)
        self._focused_key = ""
        self._hover_key = ""

    def _destroy_record(self, key: str):
        rec = self._records.pop(key, None)
        if rec is None:
            return
        try:
            window = rec.get("window")
            if window is not None:
                try:
                    window.hide()
                except Exception:
                    pass
                try:
                    window.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            root = rec.get("root")
            if root is not None:
                try:
                    root.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass

    def shutdown(self):
        for key in list(self._records.keys()):
            self._destroy_record(key)
        try:
            if self._qml_engine is not None:
                try:
                    self._qml_engine.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        self._qml_engine = None
        self._focused_key = ""
        self._hover_key = ""

    def _shared_engine(self):
        if not self._qml_ok or not _app_available():
            return None
        if self._qml_engine is not None:
            return self._qml_engine
        try:
            eng = QQmlEngine()
            try:
                from PyQt6.QtQuickControls2 import QQuickStyle

                try:
                    QQuickStyle.setStyle("Fusion")
                except Exception:
                    pass
            except Exception:
                pass
            self._qml_engine = eng
            return eng
        except Exception:
            self._qml_ok = False
            return None

    def _record(self, comp) -> dict:
        key = _view_key(comp)
        rec = self._records.get(key)
        if rec is None:
            rec = {"comp": comp, "key": key, "qml_hash": 0, "size": (0, 0), "window": None, "root": None, "image": None, "use_qml": False, "pushed": {}, "fails": 0, "exposed": False}
            self._records[key] = rec
        else:
            rec["comp"] = comp
        return rec

    def update(self, views: list, for_render: bool = False):
        seen = set()
        for comp in views:
            try:
                key = _view_key(comp)
                seen.add(key)
                self.ensure_view(comp, for_render=for_render)
            except Exception:
                continue
        for key in list(self._records.keys()):
            if key not in seen:
                ent_alive = False
                try:
                    rec = self._records.get(key)
                    comp = rec.get("comp") if rec else None
                    ent = getattr(comp, "_entity", None) if comp is not None else None
                    ent_alive = ent is not None and getattr(ent, "_scene", None) is not None
                except Exception:
                    ent_alive = False
                if not ent_alive:
                    self._destroy_record(key)

    def ensure_view(self, comp, for_render: bool = False) -> bool:
        try:
            rec = self._record(comp)
            qml = comp.effective_qml()
            w, h = comp.effective_px()
            digest = hashlib.sha256((qml + "|" + str(w) + "x" + str(h)).encode("utf-8", errors="ignore")).hexdigest()
            if digest != rec.get("qml_hash") or rec.get("root") is None and self._qml_ok:
                if for_render:
                    rec["needs_build"] = True
                    if rec.get("image") is None:
                        rec["image"] = self._paint_fallback(comp, w, h)
                        try:
                            comp._dirty = False
                        except Exception:
                            pass
                    return True
                if qml.strip():
                    ok = self._build_qml(rec, comp, qml, w, h)
                    if ok:
                        rec["qml_hash"] = digest
                        rec["size"] = (w, h)
                        rec["pushed"] = {}
                        rec["needs_build"] = False
                        self.sync_to_qml(rec, comp, force=True)
                        self.poll_from_qml(rec, comp)
                        self.render_image(comp)
                        return True
                rec["qml_hash"] = digest
                rec["size"] = (w, h)
                rec["use_qml"] = False
            else:
                if rec.get("size") != (w, h):
                    rec["size"] = (w, h)
                    rec["exposed"] = False
                    if for_render:
                        comp._dirty = True
                    else:
                        try:
                            window = rec.get("window")
                            if window is not None:
                                window.setWidth(int(w))
                                window.setHeight(int(h))
                            try:
                                root = rec.get("root")
                                if root is not None:
                                    try:
                                        root.setWidth(int(w))
                                    except Exception:
                                        pass
                                    try:
                                        root.setHeight(int(h))
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        except Exception:
                            pass
                    comp._dirty = True
            changed = self.sync_to_qml(rec, comp, force=False)
            self.poll_from_qml(rec, comp)
            if for_render:
                self._refresh_present_image(rec, comp, w, h)
                return True
            if changed or getattr(comp, "_dirty", False):
                self.render_image(comp)
            elif rec.get("image") is None:
                self.render_image(comp)
            return True
        except Exception:
            return False

    def _build_qml(self, rec: dict, comp, qml: str, w: int, h: int) -> bool:
        self._destroy_qml_objects(rec)
        eng = self._shared_engine()
        if eng is None:
            rec["use_qml"] = False
            return False
        try:
            component = QQmlComponent(eng)
            try:
                component.setData(qml.encode("utf-8"), QUrl())
            except Exception:
                return False
            if component.isError():
                try:
                    errs = component.errors()
                    if errs:
                        rec["fails"] = int(rec.get("fails", 0)) + 1
                        if int(rec.get("fails", 0)) > 4:
                            self._qml_ok = False
                except Exception:
                    pass
                return False
            try:
                window = QQuickWindow()
            except Exception:
                return False
            try:
                window.setWidth(int(w))
                window.setHeight(int(h))
            except Exception:
                pass
            try:
                window.setPosition(-20000, -20000)
            except Exception:
                pass
            try:
                window.setFlags(window.flags() | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
            except Exception:
                pass
            try:
                root = component.create()
            except Exception:
                try:
                    window.deleteLater()
                except Exception:
                    pass
                return False
            if root is None:
                try:
                    window.deleteLater()
                except Exception:
                    pass
                return False
            try:
                root.setParentItem(window.contentItem())
            except Exception:
                try:
                    root.deleteLater()
                except Exception:
                    pass
                try:
                    window.deleteLater()
                except Exception:
                    pass
                return False
            try:
                root.setWidth(int(w))
            except Exception:
                pass
            try:
                root.setHeight(int(h))
            except Exception:
                pass
            try:
                window.show()
            except Exception:
                pass
            try:
                QCoreApplication.processEvents()
            except Exception:
                pass
            rec["window"] = window
            rec["root"] = root
            rec["use_qml"] = True
            rec["fails"] = 0
            rec["exposed"] = False
            return True
        except Exception:
            rec["use_qml"] = False
            return False

    def _destroy_qml_objects(self, rec: dict):
        try:
            window = rec.get("window")
            if window is not None:
                try:
                    window.hide()
                except Exception:
                    pass
                try:
                    window.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            root = rec.get("root")
            if root is not None:
                try:
                    root.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        rec["window"] = None
        rec["root"] = None
        rec["use_qml"] = False

    def _to_qml_value(self, prop: str, value):
        try:
            if prop in ("textColor", "panelColor"):
                return _color_to_qcolor(value)
            if prop == "hAlign":
                if isinstance(value, int):
                    return int(value)
                return _align_to_int(value)
            if prop == "imageFill":
                if isinstance(value, int):
                    return int(value)
                return _fill_to_int(value)
            if isinstance(value, (list, tuple)):
                try:
                    seq = list(value)
                    if len(seq) in (3, 4) and all(isinstance(x, (int, float)) for x in seq):
                        return _color_to_qcolor(seq)
                except Exception:
                    pass
                return value
            return value
        except Exception:
            return value

    def sync_to_qml(self, rec: dict, comp, force: bool = False) -> bool:
        try:
            root = rec.get("root")
            if root is None or not rec.get("use_qml"):
                return False
            mapping = getattr(type(comp), "TO_QML", {}) or {}
            pushed = rec.get("pushed", {})
            changed = False
            for attr, prop in mapping.items():
                try:
                    value = getattr(comp, attr, None)
                except Exception:
                    continue
                qv = self._to_qml_value(prop, value)
                old = pushed.get(prop, None)
                same = False
                try:
                    if isinstance(qv, QObject):
                        same = False
                    else:
                        same = old == qv or (old is not None and str(old) == str(qv) and not isinstance(value, (list, tuple)))
                except Exception:
                    same = False
                if same and not force:
                    continue
                try:
                    root.setProperty(prop, qv)
                    pushed[prop] = qv
                    changed = True
                except Exception:
                    continue
            rec["pushed"] = pushed
            if changed:
                comp._dirty = True
            return changed
        except Exception:
            return False

    def poll_from_qml(self, rec: dict, comp):
        try:
            root = rec.get("root")
            if root is None or not rec.get("use_qml"):
                return
            mapping = getattr(type(comp), "FROM_QML", {}) or {}
            for prop, attr in mapping.items():
                try:
                    qv = root.property(prop)
                except Exception:
                    continue
                if qv is None:
                    continue
                try:
                    cur = getattr(comp, attr, None)
                except Exception:
                    cur = None
                nv = self._from_qml_value(attr, qv, cur)
                if nv is None:
                    continue
                if cur == nv:
                    continue
                try:
                    setattr(comp, attr, nv)
                except Exception:
                    continue
                try:
                    comp._dirty = True
                except Exception:
                    pass
                try:
                    if attr == "click_count":
                        try:
                            old_n = int(cur) if cur is not None else 0
                        except Exception:
                            old_n = 0
                        if int(nv) > old_n and hasattr(comp, "_notify_clicked"):
                            comp._notify_clicked()
                    elif hasattr(comp, "_notify_changed"):
                        try:
                            comp._notify_changed()
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def _from_qml_value(self, attr: str, qv, cur):
        try:
            if isinstance(cur, bool):
                return bool(qv)
            if isinstance(cur, int):
                return int(float(qv))
            if isinstance(cur, float):
                return float(qv)
            if isinstance(cur, str):
                return str(qv)
            if isinstance(qv, bool):
                return bool(qv)
            if isinstance(qv, int):
                return int(qv)
            if isinstance(qv, float):
                return float(qv)
            return qv
        except Exception:
            return None

    def _refresh_present_image(self, rec: dict, comp, w: int, h: int):
        try:
            img = rec.get("image")
            if img is not None and not getattr(comp, "_dirty", False):
                return img
            if rec.get("use_qml") and img is not None:
                return img
            fresh = self._paint_fallback(comp, w, h)
            rec["image"] = fresh
            try:
                comp._dirty = False
            except Exception:
                pass
            return fresh
        except Exception:
            return rec.get("image")

    def render_image(self, comp):
        try:
            rec = self._record(comp)
            w, h = comp.effective_px()
            if rec.get("use_qml") and rec.get("window") is not None:
                img = self._grab_qml(rec, w, h)
                if img is not None and not img.isNull():
                    rec["image"] = img
                    try:
                        comp._dirty = False
                    except Exception:
                        pass
                    return img
            img = self._paint_fallback(comp, w, h)
            rec["image"] = img
            try:
                comp._dirty = False
            except Exception:
                pass
            return img
        except Exception:
            return None

    def get_image(self, comp):
        try:
            rec = self._record(comp)
            img = rec.get("image")
            if img is not None and not getattr(comp, "_dirty", False):
                return img
            return self.render_image(comp)
        except Exception:
            return None

    def present_image(self, comp):
        try:
            rec = self._record(comp)
            img = rec.get("image")
            if img is not None:
                return img
            w, h = comp.effective_px()
            return self._refresh_present_image(rec, comp, w, h)
        except Exception:
            return None

    def _grab_qml(self, rec: dict, w: int, h: int):
        try:
            window = rec.get("window")
            if window is None:
                return None
            try:
                if int(window.width()) != int(w) or int(window.height()) != int(h):
                    window.setWidth(int(w))
                    window.setHeight(int(h))
                    rec["exposed"] = False
                    try:
                        root = rec.get("root")
                        if root is not None:
                            try:
                                root.setWidth(int(w))
                            except Exception:
                                pass
                            try:
                                root.setHeight(int(h))
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                window.update()
            except Exception:
                pass
            if not rec.get("exposed"):
                try:
                    QCoreApplication.processEvents()
                except Exception:
                    pass
            try:
                img = window.grabWindow()
            except Exception:
                return None
            if img is None or img.isNull():
                return None
            rec["exposed"] = True
            if img.width() != w or img.height() != h:
                try:
                    img = img.scaled(w, h)
                except Exception:
                    pass
            return img
        except Exception:
            return None

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
                            from core.engine.engine import Engine

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

    def inject_mouse(self, comp, px: float, py: float, kind: str, button: int = 1) -> bool:
        try:
            rec = self._record(comp)
            if rec.get("use_qml") and rec.get("window") is not None:
                handled = self._inject_qml_mouse(rec, float(px), float(py), kind, button)
                if handled or kind not in ("press", "drag"):
                    return handled
                return self._inject_fallback_mouse(comp, float(px), float(py), kind)
            return self._inject_fallback_mouse(comp, float(px), float(py), kind)
        except Exception:
            return False

    def _inject_qml_mouse(self, rec: dict, px: float, py: float, kind: str, button: int) -> bool:
        try:
            window = rec.get("window")
            if window is None or QMouseEvent is None:
                return False
            pos = QPointF(float(px), float(py))
            gpos = QPointF(float(px), float(py))
            if kind == "press":
                try:
                    from PyQt6.QtCore import QEvent

                    ev = QMouseEvent(QEvent.Type.MouseButtonPress, pos, gpos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                except Exception:
                    return False
                try:
                    handled = bool(QCoreApplication.sendEvent(window, ev))
                    try:
                        window.requestUpdate()
                    except Exception:
                        pass
                    return handled
                except Exception:
                    return False
            if kind == "release":
                try:
                    from PyQt6.QtCore import QEvent

                    ev = QMouseEvent(QEvent.Type.MouseButtonRelease, pos, gpos, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
                except Exception:
                    return False
                try:
                    handled = bool(QCoreApplication.sendEvent(window, ev))
                    try:
                        window.requestUpdate()
                    except Exception:
                        pass
                    return handled
                except Exception:
                    return False
            try:
                from PyQt6.QtCore import QEvent

                ev = QMouseEvent(QEvent.Type.MouseMove, pos, gpos, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton if button else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
            except Exception:
                return False
            try:
                return bool(QCoreApplication.sendEvent(window, ev))
            except Exception:
                return False
        except Exception:
            return False

    def _inject_fallback_mouse(self, comp, px: float, py: float, kind: str) -> bool:
        try:
            if kind not in ("press", "drag"):
                return False
            w, h = comp.effective_px()
            cname = type(comp).__name__
            if cname == "QuickButton":
                if kind == "press":
                    try:
                        comp.click()
                        return True
                    except Exception:
                        return False
            elif cname == "QuickSlider":
                try:
                    t = (float(px) - 16.0) / max(1.0, float(w) - 32.0)
                    comp.set_normalized(t)
                    return True
                except Exception:
                    return False
            elif cname == "QuickDial":
                try:
                    comp.set_value(float(comp.minimum) + (float(px) / max(1.0, float(w))) * (float(comp.maximum) - float(comp.minimum)))
                    return True
                except Exception:
                    return False
            elif cname in ("QuickCheckBox", "QuickSwitch"):
                if kind == "press":
                    try:
                        comp.toggle()
                        return True
                    except Exception:
                        return False
            elif cname == "QuickComboBox":
                if kind == "press":
                    try:
                        items = comp.get_items()
                        if items:
                            comp.current_index = (int(comp.current_index) + 1) % len(items)
                            comp._dirty = True
                            comp._notify_changed()
                            return True
                    except Exception:
                        return False
            elif cname == "QuickSpinBox":
                if kind == "press":
                    try:
                        if float(px) > float(w) - 64.0:
                            if float(py) < float(h) * 0.5:
                                comp.set_value(int(comp.value) + 1)
                            else:
                                comp.set_value(int(comp.value) - 1)
                            return True
                    except Exception:
                        return False
            elif cname == "QuickTextField":
                if kind == "press":
                    self.set_focus(comp)
                    return True
            return False
        except Exception:
            return False

    def inject_wheel(self, comp, px: float, py: float, delta: int) -> bool:
        try:
            rec = self._record(comp)
            if rec.get("use_qml") and rec.get("window") is not None and QWheelEvent is not None:
                try:
                    from PyQt6.QtCore import QEvent

                    pos = QPointF(float(px), float(py))
                    gpos = QPointF(float(px), float(py))
                    ev = QWheelEvent(pos, gpos, QPointF(0, float(delta)), QPointF(0, float(delta)), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
                    return bool(QCoreApplication.sendEvent(rec.get("window"), ev))
                except Exception:
                    pass
            cname = type(comp).__name__
            if cname in ("QuickSlider", "QuickDial", "QuickSpinBox"):
                try:
                    step = float(getattr(comp, "step", 1.0)) if cname != "QuickSpinBox" else 1.0
                    direction = 1.0 if int(delta) > 0 else -1.0
                    comp.set_value(float(getattr(comp, "value", 0.0)) + direction * step)
                    return True
                except Exception:
                    return False
            return False
        except Exception:
            return False

    def inject_key(self, comp, key: int, text: str, kind: str) -> bool:
        try:
            rec = self._record(comp)
            if rec.get("use_qml") and rec.get("window") is not None and QKeyEvent is not None:
                try:
                    from PyQt6.QtCore import QEvent

                    et = QEvent.Type.KeyPress if kind == "press" else QEvent.Type.KeyRelease
                    ev = QKeyEvent(et, int(key), Qt.KeyboardModifier.NoModifier, str(text or ""))
                    return bool(QCoreApplication.sendEvent(rec.get("window"), ev))
                except Exception:
                    pass
            if type(comp).__name__ == "QuickTextField" and kind == "press":
                try:
                    cur = str(getattr(comp, "text", ""))
                    if int(key) in (16777219, 8):
                        comp.set_text(cur[:-1])
                        return True
                    if text and len(str(text)) == 1 and str(text).isprintable():
                        comp.set_text((cur + str(text))[: int(getattr(comp, "max_length", 256))])
                        return True
                except Exception:
                    return False
            return False
        except Exception:
            return False
