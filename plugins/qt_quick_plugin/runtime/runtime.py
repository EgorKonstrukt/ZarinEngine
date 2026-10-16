# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import hashlib

from plugins.qt_quick_plugin.runtime.qml import QmlMixin, _view_key, _HAS_QUICK, QPointF, QMouseEvent, QWheelEvent, QKeyEvent, QCoreApplication, Qt
from plugins.qt_quick_plugin.runtime.bridge import BridgeMixin

class QuickRuntime(QmlMixin, BridgeMixin):
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
                    from PySide6.QtCore import QEvent

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
                    from PySide6.QtCore import QEvent

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
                from PySide6.QtCore import QEvent

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
                    from PySide6.QtCore import QEvent

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
                    from PySide6.QtCore import QEvent

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
