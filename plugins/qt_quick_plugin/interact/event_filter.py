# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations

try:
    from PyQt6.QtCore import QObject, QEvent

    _HAS_QT = True
except Exception:
    QObject = object
    QEvent = None
    _HAS_QT = False
from plugins.qt_quick_plugin.interact.picking import pick_view, resolve_camera, screen_ray


class QuickEventFilter(QObject):
    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin
        self._pressed_view = None
        self._swallowed = False
        self._last_hover = None
        self._last_uv = (0.5, 0.5)

    def _viewport_size(self, obj):
        try:
            return (float(obj.width()), float(obj.height()))
        except Exception:
            return (1.0, 1.0)

    def _views(self):
        try:
            return self._plugin.cached_views()
        except Exception:
            return []

    def _cam_for(self, obj):
        try:
            cam = resolve_camera(self._plugin._engine, obj)
            if cam is None:
                cam = resolve_camera(self._plugin._engine, getattr(self._plugin, "_viewport", None))
            return cam
        except Exception:
            return None

    def _ray_for(self, obj, px, py):
        try:
            fn = getattr(obj, "screen_to_ray", None)
            if callable(fn):
                origin, direction = fn(int(px), int(py))
                if origin is not None and direction is not None:
                    return (origin, direction)
        except Exception:
            pass
        try:
            vp = getattr(self._plugin, "_viewport", None)
            if vp is not None and vp is not obj:
                fn = getattr(vp, "screen_to_ray", None)
                if callable(fn):
                    origin, direction = fn(int(px), int(py))
                    if origin is not None and direction is not None:
                        return (origin, direction)
        except Exception:
            pass
        try:
            cam = self._cam_for(obj)
            if cam is None:
                return (None, None)
            w, h = self._viewport_size(obj)
            return screen_ray(cam, float(px), float(py), w, h)
        except Exception:
            return (None, None)

    def _pick_at(self, obj, px, py):
        try:
            views = self._views()
            if not views:
                return (None, 0.0, 0.0)
            origin, direction = self._ray_for(obj, px, py)
            comp, u, v, _t = pick_view(views, origin, direction)
            return (comp, float(u), float(v))
        except Exception:
            return (None, 0.0, 0.0)

    def _mouse_pos(self, event):
        try:
            pos = event.position()
            return (float(pos.x()), float(pos.y()))
        except Exception:
            pass
        try:
            return (float(event.x()), float(event.y()))
        except Exception:
            return None

    def _view_id(self, comp):
        try:
            from plugins.qt_quick_plugin.runtime import _view_key

            return _view_key(comp)
        except Exception:
            return str(id(comp))

    def _clear_gesture(self):
        self._pressed_view = None
        self._swallowed = False

    def _btn_value(self, v) -> int:
        try:
            u = getattr(v, "value", None)
            if u is not None:
                return int(u)
            return int(v)
        except Exception:
            return 0

    def _hold_left(self, event) -> bool:
        try:
            return bool(self._btn_value(event.buttons()) & 1)
        except Exception:
            return False

    def _to_px(self, comp, u, v):
        try:
            w, h = comp.effective_px()
            px = float(u) * float(w)
            py = (1.0 - float(v)) * float(h)
            return (px, py)
        except Exception:
            return (0.0, 0.0)

    def eventFilter(self, obj, event):
        try:
            plugin = self._plugin
            if plugin is None or not plugin.is_interaction_enabled():
                return False
            try:
                et = event.type()
            except Exception:
                return False
            if QEvent is None:
                return False
            if et == QEvent.Type.MouseMove:
                pos = self._mouse_pos(event)
                if pos is None:
                    return False
                px, py = pos
                if self._swallowed and self._pressed_view is not None:
                    if not self._hold_left(event):
                        self._clear_gesture()
                    else:
                        comp = self._pressed_view
                        try:
                            u, v = self._last_uv
                            origin, direction = self._ray_for(obj, px, py)
                            if origin is not None and direction is not None:
                                try:
                                    ok, nu, nv, _t = comp.intersect_ray(origin, direction)
                                    if ok:
                                        u, v = float(nu), float(nv)
                                except Exception:
                                    pass
                            self._last_uv = (float(u), float(v))
                            qx, qy = self._to_px(comp, float(u), float(v))
                            try:
                                plugin._runtime.inject_mouse(comp, qx, qy, "drag", 1)
                            except Exception:
                                pass
                            try:
                                plugin._kick()
                            except Exception:
                                pass
                        except Exception:
                            pass
                        return True
                comp, u, v = self._pick_at(obj, px, py)
                if comp is not None:
                    qx, qy = self._to_px(comp, u, v)
                    sig = (self._view_id(comp), int(qx), int(qy))
                    if sig == self._last_hover:
                        return False
                    self._last_hover = sig
                    try:
                        plugin._runtime.inject_mouse(comp, qx, qy, "move", 0)
                    except Exception:
                        pass
                else:
                    self._last_hover = None
                return False
            if et == QEvent.Type.MouseButtonPress:
                btn = self._btn_value(event.button())
                if btn != 1:
                    return False
                pos = self._mouse_pos(event)
                if pos is None:
                    return False
                px, py = pos
                comp, u, v = self._pick_at(obj, px, py)
                if comp is None:
                    try:
                        plugin._runtime.set_focus(None)
                    except Exception:
                        pass
                    self._last_hover = None
                    return False
                qx, qy = self._to_px(comp, u, v)
                try:
                    plugin._runtime.set_focus(comp)
                except Exception:
                    pass
                try:
                    plugin._runtime.inject_mouse(comp, qx, qy, "press", 1)
                except Exception:
                    pass
                try:
                    plugin._kick()
                except Exception:
                    pass
                self._pressed_view = comp
                self._swallowed = True
                self._last_uv = (float(u), float(v))
                return True
            if et == QEvent.Type.MouseButtonRelease:
                if not self._swallowed or self._pressed_view is None:
                    return False
                comp = self._pressed_view
                self._clear_gesture()
                pos = self._mouse_pos(event)
                if pos is not None:
                    try:
                        origin, direction = self._ray_for(obj, pos[0], pos[1])
                        if origin is not None and direction is not None:
                            try:
                                ok, u, v, _t = comp.intersect_ray(origin, direction)
                                if ok:
                                    self._last_uv = (float(u), float(v))
                            except Exception:
                                pass
                    except Exception:
                        pass
                qx, qy = self._to_px(comp, self._last_uv[0], self._last_uv[1])
                try:
                    plugin._runtime.inject_mouse(comp, qx, qy, "release", 1)
                except Exception:
                    pass
                try:
                    plugin._kick()
                except Exception:
                    pass
                return True
            if et == QEvent.Type.Wheel:
                pos = self._mouse_pos(event)
                if pos is None:
                    return False
                comp, u, v = self._pick_at(obj, pos[0], pos[1])
                if comp is None:
                    return False
                qx, qy = self._to_px(comp, u, v)
                try:
                    delta = int(event.angleDelta().y())
                except Exception:
                    delta = 120
                try:
                    handled = bool(plugin._runtime.inject_wheel(comp, qx, qy, delta))
                    if handled:
                        try:
                            plugin._kick()
                        except Exception:
                            pass
                    return handled
                except Exception:
                    return False
            if et == QEvent.Type.KeyPress or et == QEvent.Type.KeyRelease:
                try:
                    focused = plugin._runtime.focused()
                except Exception:
                    focused = None
                if focused is None:
                    return False
                key = self._btn_value(event.key())
                if key == 0:
                    return False
                try:
                    text = str(event.text())
                except Exception:
                    text = ""
                kind = "press" if et == QEvent.Type.KeyPress else "release"
                try:
                    return bool(plugin._runtime.inject_key(focused, key, text, kind))
                except Exception:
                    return False
            if et == QEvent.Type.Leave:
                self._clear_gesture()
                self._last_hover = None
                return False
            if et == QEvent.Type.FocusOut or et == QEvent.Type.WindowDeactivate:
                self._clear_gesture()
                self._last_hover = None
                try:
                    plugin._runtime.set_focus(None)
                except Exception:
                    pass
                return False
            return False
        except Exception:
            return False
