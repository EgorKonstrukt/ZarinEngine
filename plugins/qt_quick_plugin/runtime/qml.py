# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QUrl, QObject, QCoreApplication, QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPen, QBrush, QMouseEvent, QWheelEvent, QKeyEvent
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
    from PySide6.QtQml import QQmlEngine, QQmlComponent
    from PySide6.QtQuick import QQuickWindow
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




class QmlMixin:
    def _shared_engine(self):
        if not self._qml_ok or not _app_available():
            return None
        if self._qml_engine is not None:
            return self._qml_engine
        try:
            eng = QQmlEngine()
            try:
                from PySide6.QtQuickControls2 import QQuickStyle

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

