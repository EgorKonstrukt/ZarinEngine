# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import threading, time
from typing import TYPE_CHECKING
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QApplication, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QSurfaceFormat
from core.foundation.logger import Logger
from core.engine.frame_pacer import FramePacer, needs_software_pacing, normalize_target_fps, timer_interval_ms
from editor.scene_camera import SceneCamera
from core.gizmo.gizmo import Gizmo
from core.gizmo.api import GizmosManager, set_gizmos
from core.input.input_manager import InputManager
from editor.viewport.overlay_widget import OverlayWidget
from editor.viewport.progress_toast import ProgressToast
from editor.viewport.perf import _BlockWatch
from editor.viewport.undo_filter import _UndoFilter
from editor.viewport.viewport_camera import ViewportCameraMixin
from editor.viewport.viewport_overlay import ViewportOverlayMixin
from editor.viewport.viewport_selection import ViewportSelectionMixin
from editor.viewport.viewport_render import ViewportRenderMixin
from editor.viewport.viewport_input import ViewportInputMixin

if TYPE_CHECKING:
    from core.renderer.renderer import Renderer


class SceneViewport(ViewportCameraMixin, ViewportOverlayMixin, ViewportSelectionMixin, ViewportRenderMixin, ViewportInputMixin, QOpenGLWidget):
    """OpenGL scene viewport composed from mixins."""

    entity_selected = pyqtSignal(object)
    entities_selected = pyqtSignal(list)
    entity_dropped = pyqtSignal(str, object, object)
    scene_modified = pyqtSignal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._mw = parent
        self._undo_filter = _UndoFilter(self._mw)
        app = QApplication.instance()
        if app:
            app.installEventFilter(self._undo_filter)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._engine = engine
        self._ctx = None
        self._renderer = None
        self._cam = SceneCamera()
        self._cam.set_viewport_size(self.width(), self.height())
        self._gizmo = Gizmo()
        self._gizmos_api = GizmosManager()
        set_gizmos(self._gizmos_api)
        self._selected_entities: list = []; self._selected_set: frozenset = frozenset()
        self._selected_set_key = (None, -1); self._selected_set_version: int = 0; self._gc_frame_counter: int = 0
        self._last_frame_time = time.perf_counter(); self._last_paint_time = time.perf_counter(); self._last_update_gap = time.perf_counter()
        self._last_dt = 0.016; self._paint_dt = 0.016; self._last_render_ms = 0.0; self._last_gizmo_ms = 0.0
        self._last_overlay_ms = 0.0; self._last_paint_full_ms = 0.0; self._fps = 0.0; self._fps_accum = 0.0; self._fps_frames = 0
        self._screen_fbo = None
        self._render_timer = QTimer(self)
        self._render_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._render_timer.timeout.connect(self._on_render_tick)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(40, 40)
        self.setContentsMargins(0, 0, 0, 0)
        self._area_selecting = False; self._area_start = (0, 0); self._area_end = (0, 0)
        self._rmb_press_pos = (0, 0); self._rmb_press_shift = False; self._physical_w = 800; self._physical_h = 600
        self._clear_color = [0.18, 0.18, 0.18]; self._no_scene_color = [0.12, 0.12, 0.12]
        self._update_interval = 16; self._grid_step = 10.0; self._vsync_enabled = True; self._target_fps = 60
        self._pacer = FramePacer(); self._init_format(); self._stats_enabled = True; self._audio_viz_enabled = False
        self._audio_analyzer = None; self._audio_viz = None
        self._audio_viz_opts = {"scope_gain": 0.82, "wave_gain": None, "hold_decay": 0.8}
        self._fps_history: list[float] = []; self._debug_lines = []; self._show_bvh_debug = False; self._show_rt_heatmap = False
        self._overlay_canvas = None
        try:
            self._im = InputManager.instance()
        except Exception:
            self._im = None
        self._focused = False; self._navigation_gizmo_enabled = True; self._navigation_gizmo_hover = -1
        self._navigation_gizmo_center = (0.0, 0.0); self._navigation_gizmo_interacting = False
        self._ng_mouse_pos = (0.0, 0.0); self._ng_mouse_down = False; self._ng_clicked = False; self._ng_released = False
        self._ng_mouse_delta = (0.0, 0.0); self._ng_last_mouse = (0.0, 0.0)
        from core.components.navigation_gizmo.navigation_gizmo import NavigationGizmo
        self._navigation_gizmo = NavigationGizmo(); self._navigation_gizmo_orbit = False
        self._gizmo_visible = True; self._gizmo_icons_visible = True
        self._overlay_widget = OverlayWidget(self, self); self._progress_toast = ProgressToast(self)
        try:
            from core.config.config import get_global_config
            get_global_config().on_changed(self._on_overlay_config_changed)
        except Exception:
            pass
        self._last_mouse_pos = (0, 0)
        self._entity_clipboard: list[dict] = []
        self._multi_entity_initial_transforms = {}
        self._collab_throttle_cursor = 0.0
        self._collab_throttle_camera = 0.0
        self._collab_cursor_interval = 1.0 / 30.0
        self._collab_camera_interval = 1.0 / 15.0
        self._collab_transform_interval = 1.0 / 20.0
        self._collab_gizmo_interval = 1.0 / 10.0
        self._collab_last_sent_transform = {}
        self._collab_throttle_transform = 0.0
        self._collab_throttle_gizmo = 0.0
        self._collab_last_gizmo_state = ("none", -1, False)
        self._collab_timer = QTimer(self)
        self._collab_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._collab_timer.setInterval(500)
        self._collab_timer.timeout.connect(self._collab_tick)
        self._pb_scale_gizmo = None
        self._pb_grab = None
        self._in_update = False
        self._last_status_update = 0.0
        self._cached_overlay_state = None
        self._last_overlay_update = 0.0
        self._frame_budget = 1.0 / 60.0
        self._cursor_label_cache = ("", "", "")
        self._throttle_mode = "editor"
        self._throttle_step = 2
        self._throttle_next_t = 0.0
        self._throttle_armed = False
        self._block_watch = _BlockWatch()
        self._last_block_log = 0.0
        from editor.viewport.toolbar import setup_toolbar
        setup_toolbar(self)
        self._refresh_no_qt_overlay()

    def _init_format(self):
        from core.config.config import get_global_config
        cfg = get_global_config()
        self._vsync_enabled = cfg.get("rendering.vsync", True)
        self._target_fps = cfg.get("rendering.target_fps", 60)
        self._frame_budget = 1.0 / max(1, int(self._target_fps)) if self._target_fps else 1.0 / 60.0
        self._throttle_mode = cfg.get("rendering.play_viewport_throttle", "editor")
        try:
            self._throttle_step = max(2, int(cfg.get("rendering.play_viewport_throttle_step", 2)))
        except Exception:
            self._throttle_step = 2
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setVersion(4, 6)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setSwapInterval(1 if self._vsync_enabled else 0)
        self.setFormat(fmt)
        self._apply_config()

    @property
    def _no_qt_overlay(self) -> bool:
        return self._engine._debug_no_qt_overlay if hasattr(self._engine, "_debug_no_qt_overlay") else False

    def _refresh_no_qt_overlay(self):
        no = self._no_qt_overlay
        want = not no
        if self._cached_overlay_state == want:
            return
        self._cached_overlay_state = want
        if hasattr(self, "_overlay_widget") and self._overlay_widget:
            self._overlay_widget.set_visible(want)
        if hasattr(self, "_toolbar") and self._toolbar:
            self._toolbar.setVisible(want)

    def _apply_config(self):
        if self._vsync_enabled:
            self._render_timer.stop()
            self._pacer.set_target(0)
        else:
            self._render_timer.setTimerType(Qt.TimerType.PreciseTimer)
            tgt = int(self._target_fps) if self._target_fps else 0
            if tgt <= 0 or tgt == 60:
                self._render_timer.setInterval(0)
                self._pacer.set_target(0)
            else:
                tgt = normalize_target_fps(tgt)
                self._render_timer.setInterval(timer_interval_ms(tgt))
                self._pacer.set_target(tgt if needs_software_pacing(tgt) else 0)
            if self.isVisible():
                self._render_timer.start()

    def _refresh_throttle_cache(self):
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            self._throttle_mode = cfg.get("rendering.play_viewport_throttle", "editor")
            try:
                self._throttle_step = max(2, int(cfg.get("rendering.play_viewport_throttle_step", 2)))
            except Exception:
                self._throttle_step = 2
        except Exception:
            pass

    def _on_overlay_config_changed(self, key: str, value):
        if key in ("rendering.vsync", "rendering.target_fps", "rendering.play_viewport_throttle", "rendering.play_viewport_throttle_step"):
            self._refresh_throttle_cache()
        if key in ("rendering.vsync", "rendering.target_fps"):
            try:
                from core.config.config import get_global_config
                cfg = get_global_config()
                self._vsync_enabled = cfg.get("rendering.vsync", True)
                self._target_fps = cfg.get("rendering.target_fps", 60)
                self._frame_budget = 1.0 / max(1, int(self._target_fps)) if self._target_fps else 1.0 / 60.0
                fmt = self.format()
                fmt.setSwapInterval(1 if self._vsync_enabled else 0)
                self.setFormat(fmt)
                self._apply_config()
                try:
                    import ctypes
                    opengl32 = ctypes.windll.opengl32
                    addr = opengl32.wglGetProcAddress(b"wglSwapIntervalEXT")
                    if addr:
                        func = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(addr)
                        func(0 if not self._vsync_enabled else 1)
                except Exception:
                    pass
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_config()
        self._collab_timer.start()
        try:
            self._block_watch.start(threading.get_ident())
        except Exception:
            pass
        self.update()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._render_timer.stop()
        self._collab_timer.stop()
        self._throttle_next_t = 0.0
        self._throttle_armed = False
        try:
            self._block_watch.stop()
        except Exception:
            pass

    def on_dock_top_level_changed(self, floating: bool):
        self._screen_fbo = None
        self._last_fbo_id = None
        self.update()
        if floating:
            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(100, self._retry_float_fbo)

    def load_config(self, config) -> None:
        clear = config.get("viewport.clear", self._clear_color)
        self._clear_color = [clear[0], clear[1], clear[2]]
        no_scene = config.get("viewport.no_scene", self._no_scene_color)
        self._no_scene_color = [no_scene[0], no_scene[1], no_scene[2]]
        self._vsync_enabled = config.get("rendering.vsync", self._vsync_enabled)
        self._target_fps = config.get("rendering.target_fps", self._target_fps)
        self._update_interval = config.get("viewport.update_interval", self._update_interval)
        self._grid_step = config.get("viewport.grid_step", self._grid_step)
        self._apply_config()

    @property
    def camera(self):
        return self._cam

    @property
    def gizmo(self):
        return self._gizmo

    @property
    def renderer(self):
        return self._renderer

    @property
    def selected_entities(self) -> list:
        return self._selected_entities

    def initializeGL(self):
        try:
            try:
                import gc as _gc
                _gc.freeze()
            except Exception:
                pass
            self._init_gl_resources()
        except Exception as e:
            import traceback
            print(f"[Zarin Engine] OpenGL init error: {e}\n{traceback.format_exc()}", flush=True)
            Logger.error(f"OpenGL init error: {e}", e)

    def resizeGL(self, w: int, h: int):
        dpr = self.devicePixelRatio()
        pw, ph = int(w * dpr), int(h * dpr)
        self._physical_w = pw
        self._physical_h = ph
        self._cam.set_viewport_size(w, h)
        if not self._no_qt_overlay:
            if hasattr(self, "_toolbar") and self._toolbar:
                self._toolbar.setGeometry(0, 0, w, self._toolbar.height())
            self._overlay_widget.resize(w, h)
        if self._ctx:
            self._screen_fbo = None
            self._last_fbo_id = None
            self._ctx.viewport = (0, 0, pw, ph)

    def paintGL(self):
        self._refresh_no_qt_overlay()
        _p0 = time.perf_counter()
        _paint_gap = _p0 - getattr(self, "_last_paint_enter", _p0)
        self._last_paint_enter = _p0
        _gap_raw = _paint_gap
        if _paint_gap > 0.05:
            _paint_gap = 0.05
        self._paint_dt = _paint_gap
        _ft = getattr(self, "_frame_times_ms", None)
        if _ft is None:
            self._frame_times_ms = _ft = []
        if _paint_gap > 0.0:
            _ft.append(_paint_gap * 1000.0)
            if len(_ft) > 300:
                _ft.pop(0)
        self._report_block(_gap_raw, _p0)
        eng = self._engine
        prof = eng._profiler
        prof.capture_frame()
        prof.start("frame")
        now = _p0
        self._fps_accum += now - self._last_paint_time
        self._last_paint_time = now
        self._fps_frames += 1
        if self._fps_accum >= 0.5:
            self._fps = self._fps_frames / self._fps_accum
            self._fps_accum = 0.0
            self._fps_frames = 0
        if not self._ctx or not self._renderer:
            prof.stop("frame")
            return
        if getattr(self._engine, "play_mode", False):
            if getattr(self, "_throttle_mode", "editor") == "editor":
                mw = getattr(self, "_mw", None)
                pd = getattr(mw, "_play_dock", None) if mw is not None else None
                if pd is not None and pd.isVisible():
                    step = getattr(self, "_throttle_step", 2)
                    try:
                        step = max(2, int(step))
                    except Exception:
                        step = 2
                    wait = self._play_throttle_wait(step)
                    if wait > 0.0:
                        if not self._throttle_armed and self.isVisible():
                            self._throttle_armed = True
                            QTimer.singleShot(max(1, int(wait * 1000.0)), self._throttle_resume)
                        prof.stop("frame")
                        return
                    self._throttle_armed = False
        self._paint_editor_update(now, prof)
        in_frame = prof is not None and len(prof._stack) > 0 and prof._stack[0][0] == "frame"
        try:
            if in_frame:
                prof.start("gl_setup")
            self._bind_screen_fbo()
            if self._screen_fbo is None:
                self.update()
                prof.stop("frame")
                return
            scene = eng.scene
            cam_cc = self._clear_color + [1.0] if scene else self._no_scene_color + [1.0]
            self._screen_fbo.clear(*cam_cc[:3], 1.0)
            self._renderer.clear_color = self._clear_color
            if in_frame:
                prof.stop("gl_setup")
            if scene:
                fw, fh = self._get_physical_dims()
                rw, rh = self._cam.compute_render_size(fw, fh)
                aspect = rw / max(1, rh)
                view = self._cam.get_view_matrix()
                proj = self._cam.get_projection_matrix(aspect)
                cam_pos = self._cam.position
                self._renderer.grid_2d_mode = self._cam.is_2d_mode
                self._renderer.grid_zoom_distance = self._cam._ortho_zoom_distance
                t0 = time.perf_counter()
                sel_set = self._get_selected_set()
                self._renderer.render_scene(scene, view, proj, cam_pos, rw, rh, self._screen_fbo, sel_set, self._cam.near, self._cam.far, self._cam.fov, display_w=fw, display_h=fh)
                self._last_render_ms = (time.perf_counter() - t0) * 1000.0
                eng.set_profiler_data("render_ms", self._last_render_ms)
                vp_mat = view * proj
                dpr = self.devicePixelRatio()
                self._renderer._line_width = max(1.0, float(dpr) * 1.0)
                t1 = time.perf_counter()
                if in_frame:
                    prof.start("gizmos")
                self._paint_gizmo_block(vp_mat, fw, fh, cam_pos)
                if in_frame:
                    prof.stop("gizmos")
                eng.set_profiler_data("gizmo_time", (time.perf_counter() - t1) * 1000.0)
                self._last_gizmo_ms = (time.perf_counter() - t1) * 1000.0
                t2 = time.perf_counter()
                if in_frame:
                    prof.start("overlay_draw")
                self._paint_overlay_tick()
                if in_frame:
                    prof.stop("overlay_draw")
                eng.set_profiler_data("overlay_time", (time.perf_counter() - t2) * 1000.0)
                self._last_overlay_ms = (time.perf_counter() - t2) * 1000.0
            if self._audio_viz_enabled:
                self._render_audio_osd(now)
            eng.set_profiler_data("paint_total_ms", (time.perf_counter() - _p0) * 1000.0)
        except Exception as e:
            import traceback as _tb
            _tb.print_exc()
            Logger.error(f"Render error: {e}", e)
        prof.stop("frame")
        _paint_dur = (time.perf_counter() - _p0) * 1000.0
        self._last_paint_full_ms = _paint_dur
        eng.set_profiler_data("paint_full_ms", _paint_dur)
        eng.set_profiler_data("paint_gap_ms", _paint_gap * 1000.0)
        if self.isVisible():
            if self._vsync_enabled:
                self.update()
            elif self._render_timer.isActive():
                pass
            else:
                self.update()

__all__ = ["SceneViewport"]
