# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations

from core.foundation.plugins import PluginBase
from core.foundation.logger import Logger
from plugins.qt_quick_plugin.components.quick_view import QuickView
from plugins.qt_quick_plugin.components import QUICK_ALL_TYPES, QUICK_BY_NAME, collect_quick_views
from plugins.qt_quick_plugin.runtime import QuickRuntime
from plugins.qt_quick_plugin.gl import QuickGLRenderer

from plugins.qt_quick_plugin.plug.plugin import QtQuickWorldPluginBase

class QtQuickWorldPlugin(QtQuickWorldPluginBase):
    def _render_quick_into(self, renderer_self, scene, view_mat, proj_mat, cam_pos):
        try:
            if scene is None:
                return 0
            if getattr(renderer_self, "_rendering_cubemap_face", False):
                return 0
            ctx = getattr(renderer_self, "_ctx", None)
            if ctx is None:
                return 0
            if not self._gl.ensure(ctx):
                if not self._gl_fail_logged:
                    self._gl_fail_logged = True
                    Logger.warning("[QtQuickWorld] GL program not ready, world UI hidden")
                return 0
            if not self._gl_ready_logged:
                self._gl_ready_logged = True
                Logger.info("[QtQuickWorld] GL renderer ready")
            views = collect_quick_views(scene)
            if not views:
                return 0
            keep = set()
            for comp in views:
                try:
                    ent = getattr(comp, "_entity", None)
                    key = str(ent.id) + "|" + str(getattr(comp, "_key", "")) if ent is not None else str(id(comp))
                    keep.add(key)
                    img = self._pending.get(key)
                    if img is None:
                        img = self._runtime.present_image(comp)
                    if img is None or img.isNull():
                        continue
                    self._gl.upload(key, img)
                except Exception:
                    continue
            try:
                self._gl.prune(keep)
            except Exception:
                pass
            try:
                fbo = getattr(renderer_self, "_scene_fbo", None)
                if fbo is not None:
                    try:
                        fbo.use()
                    except Exception:
                        pass
                    try:
                        size = getattr(renderer_self, "_scene_fbo_size", (0, 0))
                        if size and size[0] > 0 and size[1] > 0:
                            ctx.viewport = (0, 0, int(size[0]), int(size[1]))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                drawn = int(self._gl.render_into_scene(renderer_self, scene, views, self._pending, view_mat, proj_mat, cam_pos))
            except Exception:
                return 0
            if drawn != self._draw_logged:
                self._draw_logged = drawn
                Logger.info("[QtQuickWorld] drawing " + str(drawn) + " world views")
            return drawn
        except Exception:
            return 0

    def visible_views(self) -> list:
        try:
            scene = self._engine.scene if self._engine is not None else None
        except Exception:
            scene = None
        if scene is None:
            return []
        try:
            return collect_quick_views(scene)
        except Exception:
            return []

    def cached_views(self) -> list:
        try:
            scene = self._engine.scene if self._engine is not None else None
        except Exception:
            scene = None
        if scene is None:
            return []
        try:
            ver = int(getattr(scene, "_render_version", 0))
        except Exception:
            ver = 0
        try:
            if self._views_cache is None or ver != self._views_version:
                self._views_cache = collect_quick_views(scene)
                self._views_version = ver
        except Exception:
            return []
        out = []
        try:
            for comp in self._views_cache:
                try:
                    ent = getattr(comp, "_entity", None)
                    if ent is None or getattr(ent, "_scene", None) is not scene:
                        continue
                    if not getattr(ent, "active", True):
                        continue
                    if not getattr(comp, "enabled", True):
                        continue
                    out.append(comp)
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def is_interaction_enabled(self) -> bool:
        return bool(self._interaction_enabled)

    def set_interaction_enabled(self, value: bool):
        self._interaction_enabled = bool(value)

    def on_viewport_ready(self, viewport):
        try:
            if self._filter is not None and self._filter_vp is viewport:
                return
            if self._filter is not None and self._filter_vp is not None:
                try:
                    self._filter_vp.removeEventFilter(self._filter)
                except Exception:
                    pass
                self._filter = None
                self._filter_vp = None
        except Exception:
            pass
        self._viewport = viewport
        try:
            if self._filter is None:
                from plugins.qt_quick_plugin.interact import QuickEventFilter

                self._filter = QuickEventFilter(self)
            try:
                viewport.installEventFilter(self._filter)
                self._filter_vp = viewport
                Logger.info("[QtQuickWorld] viewport filter installed on " + type(viewport).__name__)
            except Exception:
                pass
            try:
                from PySide6.QtCore import Qt as _Qt

                viewport.setFocusPolicy(_Qt.FocusPolicy.StrongFocus)
            except Exception:
                pass
        except Exception:
            pass

    def on_scene_loaded(self, scene):
        try:
            self._runtime.clear_scene()
        except Exception:
            pass
        self._pending = {}
        self._views_cache = None
        self._views_version = -1

    def on_scene_unloaded(self, scene):
        try:
            self._runtime.clear_scene()
        except Exception:
            pass
        self._pending = {}
        self._views_cache = None
        self._views_version = -1

    def on_play_start(self):
        try:
            self._runtime.set_focus(None)
        except Exception:
            pass

    def on_play_stop(self):
        try:
            self._runtime.set_focus(None)
        except Exception:
            pass
        if self._filter is not None:
            try:
                self._filter._pressed_view = None
            except Exception:
                pass

    def step(self, dt: float):
        try:
            if self._filter is None and self._engine is not None:
                try:
                    vp = self._engine.viewport
                    if vp is not None:
                        self.on_viewport_ready(vp)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._kick()
        except Exception:
            pass

    def spawn_quick(self, class_name: str):
        try:
            cls = QUICK_BY_NAME.get(str(class_name))
        except Exception:
            cls = None
        if cls is None:
            return None
        try:
            scene = self._engine.scene if self._engine is not None else None
        except Exception:
            scene = None
        if scene is None:
            return None
        try:
            ent = scene.create_entity(str(class_name))
        except Exception:
            return None
        try:
            from core.components.transform.tr import Transform

            if ent.transform is None:
                ent.add_component(Transform())
        except Exception:
            pass
        try:
            comp = cls()
            ent.add_component(comp)
        except Exception as e:
            Logger.error("[QtQuickWorld] spawn failed: " + str(e))
            return None
        try:
            self._place_in_front(ent)
        except Exception:
            pass
        try:
            comp._dirty = True
        except Exception:
            pass
        try:
            self._runtime.ensure_view(comp)
        except Exception:
            pass
        try:
            self._kick()
        except Exception:
            pass
        return ent

    def _place_in_front(self, ent):
        try:
            from plugins.qt_quick_plugin.interact import resolve_camera

            cam = resolve_camera(self._engine, self._viewport)
            if cam is None:
                return
            try:
                pos = cam.position
                fwd = cam.forward
            except Exception:
                return
            try:
                tr = ent.transform
                if tr is None:
                    return
                from core.maths.math3d import Vec3

                tr.position = Vec3(float(pos.x) + float(fwd.x) * 2.0, float(pos.y) + float(fwd.y) * 2.0, float(pos.z) + float(fwd.z) * 2.0)
            except Exception:
                pass
        except Exception:
            pass

    def focus_view(self, comp):
        try:
            vp = self._viewport or (self._engine.viewport if self._engine is not None else None)
            if vp is None:
                return
            cam = getattr(vp, "_cam", None)
            if cam is None:
                return
            tr = comp.transform
            if tr is None:
                return
            try:
                from editor.entframe import compute_entity_frame
                ent = getattr(comp, "_entity", None)
                target = comp
                try:
                    if ent is not None and hasattr(ent, "transform") and hasattr(ent, "children"):
                        target = ent
                    elif hasattr(comp, "transform") and hasattr(comp, "children") and hasattr(comp, "_components"):
                        target = comp
                    else:
                        e = getattr(comp, "entity", None)
                        if e is not None and hasattr(e, "transform"):
                            target = e
                except Exception:
                    target = comp
                renderer = getattr(vp, "_renderer", None)
                if renderer is None:
                    try:
                        renderer = vp.renderer
                    except Exception:
                        renderer = None
                center, radius = compute_entity_frame(target, renderer)
                cam.frame_bounds(center, radius)
                return
            except Exception:
                pass
            try:
                cam.frame_bounds(tr.position)
                return
            except Exception:
                pass
            try:
                from core.maths.math3d import Vec3

                p = tr.position
                cam.position = Vec3(float(p.x) + 1.5, float(p.y) + 1.0, float(p.z) + 1.5)
            except Exception:
                pass
        except Exception:
            pass

    def shutdown(self):
        try:
            if self._viewport is not None and self._filter is not None:
                try:
                    self._viewport.removeEventFilter(self._filter)
                except Exception:
                    pass
        except Exception:
            pass
        self._filter = None
        self._filter_vp = None
        self._viewport = None
        try:
            if self._timer is not None:
                try:
                    self._timer.stop()
                except Exception:
                    pass
                try:
                    self._timer.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        self._timer = None
        try:
            if self._orig_render_scene is not None:
                try:
                    from core.renderer.renderer import Renderer

                    Renderer.render_scene = self._orig_render_scene
                except Exception:
                    pass
                self._orig_render_scene = None
        except Exception:
            pass
        try:
            self._gl.release()
        except Exception:
            pass
        try:
            self._runtime.shutdown()
        except Exception:
            pass
        self._pending = {}
        super().shutdown()

def get_plugin():
    return QtQuickWorldPlugin()
QtQuickWorldPlugin = QtQuickWorldPlugin
