# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.foundation.plugin_manager import PluginBase
from core.foundation.logger import Logger
from plugins.qt_quick_plugin.components.quick_view import QuickView
from plugins.qt_quick_plugin.components import QUICK_ALL_TYPES, QUICK_BY_NAME, collect_quick_views
from plugins.qt_quick_plugin.quick_runtime import QuickRuntime
from plugins.qt_quick_plugin.quick_gl import QuickGLRenderer


class QtQuickWorldPlugin(PluginBase):
    NAME = "QtQuickWorldPlugin"
    VERSION = "1.0.0"
    DESCRIPTION = "Qt Quick world-space UI widgets rendered into 3D world as ECS components"
    SYSTEM = True

    def __init__(self):
        super().__init__()
        self._runtime = QuickRuntime.instance()
        self._gl = QuickGLRenderer()
        self._viewport = None
        self._filter = None
        self._filter_vp = None
        self._orig_render_scene = None
        self._interaction_enabled = True
        self._pending: dict = {}
        self._in_render = False
        self._views_cache = None
        self._views_version = -1
        self._timer = None
        self._pumping = False
        self._kick_pending = False
        self._pump_count = 0
        self._gl_ready_logged = False
        self._gl_fail_logged = False
        self._draw_logged = 0

    def initialize(self, engine):
        super().initialize(engine)
        try:
            self._runtime.attach(engine)
        except Exception:
            pass
        for cls in [QuickView] + list(QUICK_ALL_TYPES):
            try:
                self.register_component(cls)
            except Exception:
                pass
        try:
            self._install_render_hook()
        except Exception as e:
            Logger.error("[QtQuickWorld] render hook failed: " + str(e))
        try:
            self.add_toolbar_button("QuickUI", self._on_refresh_all, tooltip="Refresh Quick world UI")
        except Exception:
            pass
        try:
            for label, cname in [("Button", "QuickButton"), ("Label", "QuickLabel"), ("Slider", "QuickSlider"), ("Field", "QuickTextField"), ("Check", "QuickCheckBox"), ("Bar", "QuickProgressBar"), ("Switch", "QuickSwitch"), ("Dial", "QuickDial"), ("Combo", "QuickComboBox"), ("Spin", "QuickSpinBox"), ("Panel", "QuickPanel"), ("Image", "QuickImageView")]:
                self.add_menu_item("QtQuick", "Create " + label, lambda checked=False, n=cname: self.spawn_quick(n))
            self.add_menu_item("QtQuick", "Refresh All", lambda checked=False: self._on_refresh_all())
            self.add_menu_item("QtQuick", "Diagnose", lambda checked=False: self._diagnose())
        except Exception:
            pass
        Logger.info("[QtQuickWorld] initialized with " + str(len(QUICK_ALL_TYPES)) + " world-space widgets")
        try:
            self._ensure_timer()
        except Exception:
            pass

    def _ensure_timer(self):
        if self._timer is not None:
            return
        try:
            from PyQt6.QtCore import QTimer as _QTimer

            timer = _QTimer()
            try:
                timer.setSingleShot(False)
            except Exception:
                pass
            try:
                timer.timeout.connect(self._on_pump)
            except Exception:
                return
            self._timer = timer
            try:
                timer.start(300)
            except Exception:
                pass
        except Exception:
            self._timer = None

    def _kick(self):
        try:
            if self._pumping or self._kick_pending:
                return
            self._kick_pending = True
            from PyQt6.QtCore import QTimer as _QTimer

            _QTimer.singleShot(0, self._on_kick)
        except Exception:
            self._kick_pending = False

    def _on_kick(self):
        self._kick_pending = False
        self._on_pump()

    def _on_pump(self):
        if self._pumping:
            return
        self._pumping = True
        try:
            views = self.cached_views()
            if views:
                try:
                    self._runtime.update(views)
                except Exception:
                    pass
                self._pump_count += 1
            busy = False
            try:
                for comp in views:
                    if getattr(comp, "_dirty", False) or getattr(comp, "animated", False):
                        busy = True
                        break
                    try:
                        from plugins.qt_quick_plugin.quick_runtime import _view_key as _vk

                        rec = self._runtime._records.get(_vk(comp))
                        if rec is not None and (rec.get("needs_build") or rec.get("image") is None):
                            busy = True
                            break
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if self._timer is not None:
                    self._timer.start(40 if busy else 300)
            except Exception:
                pass
        except Exception:
            pass
        self._pumping = False

    def _diagnose(self):
        try:
            lines = []
            lines.append("engine: " + ("ok" if self._engine is not None else "NONE"))
            try:
                scene = self._engine.scene if self._engine is not None else None
            except Exception:
                scene = None
            lines.append("scene: " + (getattr(scene, "name", "?") if scene is not None else "NONE"))
            try:
                views = collect_quick_views(scene) if scene is not None else []
            except Exception:
                views = []
            lines.append("quick views: " + str(len(views)))
            for comp in views[:12]:
                try:
                    ent = getattr(comp, "_entity", None)
                    lines.append("view " + type(comp).__name__ + " entity=" + (getattr(ent, "name", "?") if ent is not None else "?"))
                except Exception:
                    pass
            vp = self._viewport
            if vp is None:
                try:
                    vp = self._engine.viewport if self._engine is not None else None
                except Exception:
                    vp = None
            lines.append("viewport: " + (type(vp).__name__ if vp is not None else "NONE"))
            lines.append("filter: " + ("installed" if self._filter is not None else "NONE"))
            try:
                cands = []
                if vp is not None:
                    fn = getattr(vp, "screen_to_ray", None)
                    cands.append("vp.screen_to_ray=" + ("ok" if callable(fn) else "missing"))
                    try:
                        o, d = vp.screen_to_ray(400, 300)
                        cands.append("ray=" + ("ok" if o is not None and d is not None else "NONE"))
                    except Exception as e:
                        cands.append("ray=ERR " + str(e)[:120])
                lines.append("pick: " + " ".join(cands) if cands else "pick: no viewport")
            except Exception as e:
                lines.append("pick: ERR " + str(e)[:120])
            try:
                states = getattr(self._gl, "_states", {})
                lines.append("gl contexts: " + str(len(states)) + " ready=" + str(self._gl_ready_logged))
            except Exception:
                pass
            try:
                lines.append("qml engine: " + ("ok" if self._runtime._qml_engine is not None else "none") + " records=" + str(len(self._runtime._records)))
            except Exception:
                pass
            try:
                lines.append("timer: " + ("on" if self._timer is not None else "NONE") + " pumps=" + str(self._pump_count) + " pending_img=" + str(len(self._pending)))
            except Exception:
                pass
            try:
                shown = 0
                for key, rec in list(self._runtime._records.items())[:12]:
                    try:
                        img = rec.get("image")
                        lines.append("rec use_qml=" + str(bool(rec.get("use_qml"))) + " exposed=" + str(bool(rec.get("exposed"))) + " img=" + (str(img.width()) + "x" + str(img.height()) if img is not None else "NONE"))
                        shown += 1
                    except Exception:
                        pass
                if shown == 0:
                    lines.append("rec: none")
            except Exception:
                pass
            for line in lines:
                Logger.info("[QtQuickWorld] " + line)
        except Exception as e:
            Logger.error("[QtQuickWorld] diagnose failed: " + str(e))

    def _on_refresh_all(self):
        try:
            views = self.visible_views()
            for comp in views:
                try:
                    comp._dirty = True
                except Exception:
                    pass
            self._runtime.update(views)
        except Exception:
            pass
        try:
            self._kick()
        except Exception:
            pass

    def _install_render_hook(self):
        try:
            from core.renderer.renderer import Renderer
        except Exception:
            return
        if self._orig_render_scene is not None:
            return
        try:
            self._orig_render_scene = Renderer.render_scene
        except Exception:
            return
        plugin = self

        def _wrapped(self_renderer, scene, view_mat, proj_mat, cam_pos, viewport_w, viewport_h, fbo=None, selected_entities=None, cam_near=0.01, cam_far=1000.0, cam_fov=60.0, display_w=None, display_h=None, shared_cache=None):
            if plugin._in_render:
                return plugin._orig_render_scene(self_renderer, scene, view_mat, proj_mat, cam_pos, viewport_w, viewport_h, fbo, selected_entities, cam_near, cam_far, cam_fov, display_w, display_h, shared_cache)
            plugin._in_render = True
            try:
                if not getattr(self_renderer, "_rendering_cubemap_face", False):
                    plugin._prepare_views(scene)
            except Exception:
                pass
            orig_present = None
            patched = False
            try:
                if not getattr(self_renderer, "_rendering_cubemap_face", False):
                    orig_present = Renderer._present_composite

                    def _injecting_present(self_inner, tex, fbo_arg, dw, dh):
                        try:
                            plugin._render_quick_into(self_inner, scene, view_mat, proj_mat, cam_pos)
                        except Exception as e:
                            Logger.error("[QtQuickWorld] draw failed: " + str(e))
                        return orig_present(self_inner, tex, fbo_arg, dw, dh)

                    Renderer._present_composite = _injecting_present
                    patched = True
            except Exception:
                patched = False
            try:
                return plugin._orig_render_scene(self_renderer, scene, view_mat, proj_mat, cam_pos, viewport_w, viewport_h, fbo, selected_entities, cam_near, cam_far, cam_fov, display_w, display_h, shared_cache)
            finally:
                try:
                    if patched and orig_present is not None:
                        Renderer._present_composite = orig_present
                except Exception:
                    pass
                plugin._in_render = False

        Renderer.render_scene = _wrapped

    def _prepare_views(self, scene):
        try:
            views = self.cached_views()
        except Exception:
            views = []
        if not views:
            self._pending = {}
            return
        try:
            self._runtime.update(views, for_render=True)
        except Exception:
            pass
        pending = {}
        for comp in views:
            try:
                img = self._runtime.present_image(comp)
                if img is None or img.isNull():
                    continue
                try:
                    ent = getattr(comp, "_entity", None)
                    key = str(ent.id) + "|" + str(getattr(comp, "_key", "")) if ent is not None else str(id(comp))
                except Exception:
                    key = str(id(comp))
                pending[key] = img
            except Exception:
                continue
        self._pending = pending

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
                from plugins.qt_quick_plugin.quick_interaction import QuickEventFilter

                self._filter = QuickEventFilter(self)
            try:
                viewport.installEventFilter(self._filter)
                self._filter_vp = viewport
                Logger.info("[QtQuickWorld] viewport filter installed on " + type(viewport).__name__)
            except Exception:
                pass
            try:
                from PyQt6.QtCore import Qt as _Qt

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
            from core.components.transform.transform import Transform

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
            from plugins.qt_quick_plugin.quick_interaction import resolve_camera

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
