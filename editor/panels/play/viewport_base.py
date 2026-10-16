# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import moderngl
from typing import Optional, TYPE_CHECKING
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QSurfaceFormat
from core.input.inpsys import Input
from core.foundation.logger import Logger
from core.engine.frame_pacer import FramePacer, needs_software_pacing, normalize_target_fps, timer_interval_ms
from .fallback_view import _fallback_game_view
if TYPE_CHECKING:
    from core.engine.eng import Engine
    from core.gui.canvasp import GuiCanvas


class _PlayViewportBase(QOpenGLWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._ctx: Optional[moderngl.Context] = None
        self._renderer = None
        self._screen_fbo = None
        self._overlay_canvas: Optional[GuiCanvas] = None
        self._overlay_container: Optional[QWidget] = None
        self._mouse_captured: bool = False
        self._cursor_blank: bool = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._pacer = FramePacer()
        self._throttle_mode = "editor"
        self._throttle_step = 2
        try:
            from core.config.config import get_global_config
            _cfg = get_global_config()
            self._throttle_mode = _cfg.get("rendering.play_viewport_throttle", "editor")
            self._throttle_step = max(2, int(_cfg.get("rendering.play_viewport_throttle_step", 2)))
        except Exception:
            pass
        self._apply_timer_config()
        try:
            from core.config.config import get_global_config
            get_global_config().on_changed(self._on_config_changed)
        except Exception:
            pass
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
        engine.on("play_stop", self._on_play_stop)
        engine.on("play_start", self._on_play_start)
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        self.setFormat(fmt)

    def _wants_fast(self):
        try:
            return bool(getattr(self._engine, "play_mode", False)) and self.isVisible()
        except Exception:
            return False

    def _apply_timer_config(self):
        try:
            if not self._wants_fast():
                self._timer.setTimerType(Qt.TimerType.CoarseTimer)
                self._timer.setInterval(250)
                if not self._timer.isActive():
                    self._timer.start()
                return
            from core.config.config import get_global_config
            cfg = get_global_config()
            vsync = cfg.get("rendering.vsync", True)
            tgt = cfg.get("rendering.target_fps", 60)
            tgt = int(tgt) if tgt else 0
            if not vsync and (tgt <= 0 or tgt == 60):
                self._timer.setTimerType(Qt.TimerType.PreciseTimer)
                self._timer.setInterval(0)
                self._pacer.set_target(0)
            else:
                if tgt <= 0:
                    tgt = 60
                tgt = normalize_target_fps(tgt)
                self._timer.setTimerType(Qt.TimerType.PreciseTimer if not vsync else Qt.TimerType.CoarseTimer)
                self._timer.setInterval(timer_interval_ms(tgt))
                self._pacer.set_target(tgt if needs_software_pacing(tgt) else 0)
            if not self._timer.isActive():
                self._timer.start()
            else:
                self._timer.start()
        except Exception:
            try:
                if not self._timer.isActive():
                    self._timer.start(16)
            except Exception:
                pass

    def _on_config_changed(self, key: str, value):
        if key in ("rendering.vsync", "rendering.target_fps"):
            self._apply_timer_config()
        if key in ("rendering.play_viewport_throttle", "rendering.play_viewport_throttle_step"):
            try:
                from core.config.config import get_global_config
                cfg = get_global_config()
                self._throttle_mode = cfg.get("rendering.play_viewport_throttle", "editor")
                self._throttle_step = max(2, int(cfg.get("rendering.play_viewport_throttle_step", 2)))
            except Exception:
                pass

    def _on_play_start(self, _=None):
        self._apply_timer_config()

    def _on_play_stop(self, _=None):
        if self._mouse_captured or self._cursor_blank:
            Input.set_cursor_visible(True)
            Input.set_cursor_locked(False)
            self._release_mouse()
        self._apply_timer_config()

    def _bind_screen_fbo(self):
        fbo_id = self.defaultFramebufferObject()
        self._screen_fbo = self._ctx.detect_framebuffer(fbo_id)
        self._screen_fbo.use()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_timer_config()
        self.update()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._apply_timer_config()

    def initializeGL(self):
        try:
            self._ctx = moderngl.create_context(standalone=False)
            self._bind_screen_fbo()
            from core.renderer.renderer import Renderer
            self._renderer = Renderer(self._ctx)
            self._renderer.initialize()
            try:
                from core.config.config import get_global_config
                self._renderer.load_config(get_global_config())
            except Exception:
                pass
        except Exception as e:
            Logger.error(f"PlayViewport GL init error: {e}", e)

    def resizeGL(self, w: int, h: int):
        dpr = self.devicePixelRatio()
        pw, ph = int(w * dpr), int(h * dpr)
        if self._ctx:
            self._ctx.viewport = (0, 0, pw, ph)
            self._bind_screen_fbo()

    def paintGL(self):
        if not self._ctx or not self._renderer:
            return
        try:
            if getattr(self, "_throttle_mode", "editor") == "game":
                step = getattr(self, "_throttle_step", 2)
                self._throttle_count = getattr(self, "_throttle_count", 0) + 1
                if self._throttle_count % step:
                    return
            self._bind_screen_fbo()
            scene = self._engine.scene
            if not scene:
                self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                return
            from core.components import Camera, Transform
            cam_entity = None
            for e in scene.get_entities_with_component(Camera):
                if e.active:
                    cam_entity = e
                    break
            if not cam_entity:
                fb = None
                try:
                    dpr = self.devicePixelRatio()
                    pw, ph = int(self.width() * dpr), int(self.height() * dpr)
                    fb_aspect = float(pw) / max(1.0, float(ph))
                    fb = _fallback_game_view(scene, fb_aspect)
                except Exception:
                    fb = None
                if fb is None:
                    self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                    return
                try:
                    fb_view, fb_proj, fb_pos, fb_near, fb_far = fb
                except Exception:
                    self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                    return
                self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                try:
                    self._renderer.show_grid = False
                except Exception:
                    pass
                self._renderer.render_scene(scene, fb_view, fb_proj, fb_pos, pw, ph, self._screen_fbo, None, fb_near, fb_far, 60.0, display_w=pw, display_h=ph)
                return
            cam = cam_entity.get_component(Camera)
            tr = cam_entity.transform
            if not cam or not tr:
                self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                return
            cc = cam.clear_color
            self._ctx.clear(*cc[:3], 1.0)
            dpr = self.devicePixelRatio()
            pw, ph = int(self.width() * dpr), int(self.height() * dpr)
            rw, rh = cam.compute_render_size(pw, ph)
            aspect = rw / max(1, rh)
            view = cam.get_view_matrix()
            proj = cam.get_projection_matrix(aspect)
            self._renderer.show_grid = False
            try:
                _cn = float(cam.near)
            except Exception:
                _cn = 0.01
            try:
                _cf = float(cam.far)
            except Exception:
                _cf = 1000.0
            try:
                _cv = float(cam.fov)
            except Exception:
                _cv = 60.0
            self._renderer.render_scene(scene, view, proj, tr.position, rw, rh, self._screen_fbo, None, _cn, _cf, _cv, display_w=pw, display_h=ph)
            if self._overlay_canvas and self._overlay_canvas.edit_mode:
                from PySide6.QtGui import QPainter
                qp = QPainter(self)
                qp.setRenderHint(QPainter.RenderHint.Antialiasing)
                self._overlay_canvas._render_overlay(qp)
                qp.end()
        except Exception as e:
            import traceback as _tb
            _tb.print_exc()
            Logger.error(f"PlayViewport render error: {e}", e)

    def _tick(self):
        if self._engine.play_mode and self.isVisible():
            if not self._pacer.should_run():
                return
            prof = getattr(self._engine, "_profiler", None)
            if prof is not None:
                prof.start("play_viewport")
            try:
                from core.input.input_manager import InputManager
                im = InputManager.instance()
                im.set_surface_size(self.width(), self.height())
                im.new_frame()
                if prof is not None:
                    prof.start("play_cameras")
                try:
                    self._tick_editor_cameras()
                finally:
                    if prof is not None:
                        prof.stop("play_cameras")
                self._sync_cursor()
                self.update()
                canvas = self._overlay_canvas
                if canvas is not None:
                    try:
                        from core.gui.system import GuiCanvasSystem
                        if prof is not None:
                            prof.start("play_gui_sync")
                        try:
                            GuiCanvasSystem.instance().sync_all(self._engine.scene, canvas)
                        finally:
                            if prof is not None:
                                prof.stop("play_gui_sync")
                    except Exception:
                        pass
            finally:
                if prof is not None:
                    prof.stop("play_viewport")

    def _tick_editor_cameras(self):
        try:
            from core.components.rendering.cameras.editor_camera import EditorCamera
            scene = self._engine.scene
            if not scene:
                return
            dt = 1.0 / 60.0
            for e in scene.get_entities_with_component(EditorCamera):
                if e.active:
                    comp = e.get_component(EditorCamera)
                    if comp.enabled:
                        comp.on_update(dt)
        except Exception as e:
            Logger.warning(f"PlayViewport _tick_editor_cameras error: {e}")
