from __future__ import annotations

import copy
import math
import os
import time
import traceback
import uuid
from typing import Any, Optional, TYPE_CHECKING

import moderngl
import numpy as np
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QMenu, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QSurfaceFormat

from core.math3d import Vec3, Mat4, Quat
from core.logger import Logger
from editor.scene_camera import SceneCamera
from editor.gizmo.gizmo import Gizmo, GizmoMode, GizmoSpace
from editor.gizmo.api import GizmosManager, set_gizmos, _GIZMO_LINE_BUILDERS, _apply_line_style
from editor.gizmo.pb_scale_gizmo import PbScaleGizmo
from core.input_system import Input, KeyCode
from core.input.input_manager import InputManager
from core.input.constants import (KEY_Q, KEY_W, KEY_E, KEY_R, KEY_F, KEY_DELETE, KEY_SHIFT, KEY_CTRL, KEY_ALT,
                              KEY_SPACE, KEY_S, KEY_D, KEY_A, MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE,
                              MOUSE_L, MOUSE_R, MOUSE_M)
from editor.viewport.overlay_widget import OverlayWidget
from editor.viewport.axis_gizmo import draw_axis_gizmo_api

from editor.viewport.rendering import (
    render_collider_wireframes,
    render_particle_emitter_wireframes,
    render_camera_frustums,
    render_audio_source_gizmos,
    render_reverb_zone_gizmos,
    render_script_gizmos,
    render_selection_bounds,
)
from editor.viewport.component_icons import render_component_icons_gl
from editor.viewport.collaboration import (
    render_remote_collaborator_gizmos,
    send_collab_gizmo_state,
    send_collab_camera,
)

if TYPE_CHECKING:
    from core.ecs import Entity
    from editor.renderer import Renderer


class SceneViewport(QOpenGLWidget):
    entity_selected = pyqtSignal(object)
    entities_selected = pyqtSignal(list)
    entity_dropped = pyqtSignal(str, object, object)
    scene_modified = pyqtSignal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._ctx: Optional[moderngl.Context] = None
        self._renderer: Optional[Renderer] = None
        self._cam: SceneCamera = SceneCamera()
        self._cam.set_viewport_size(self.width(), self.height())
        self._gizmo: Gizmo = Gizmo()
        self._gizmos_api: GizmosManager = GizmosManager()
        set_gizmos(self._gizmos_api)
        self._selected_entities: list = []
        self._last_frame_time: float = time.perf_counter()
        self._last_paint_time: float = time.perf_counter()
        self._last_update_gap: float = time.perf_counter()
        self._last_dt: float = 0.016
        self._fps: float = 0.0
        self._fps_accum: float = 0.0
        self._fps_frames: int = 0
        self._screen_fbo: Optional[moderngl.Framebuffer] = None
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self.update_scene)
        self._update_timer.start(16)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 100)
        self.setContentsMargins(0, 0, 0, 0)
        self._area_selecting = False
        self._area_start = (0, 0)
        self._area_end = (0, 0)
        self._physical_w: int = 800
        self._physical_h: int = 600
        self._clear_color: list[float] = [0.18, 0.18, 0.18]
        self._no_scene_color: list[float] = [0.12, 0.12, 0.12]
        self._update_interval: int = 16
        self._grid_step: float = 10.0
        self._vsync_enabled: bool = True
        self._target_fps: int = 60
        self._init_format()
        self._stats_enabled: bool = False
        self._fps_history: list[float] = []
        self._debug_lines: list[tuple[Vec3, Vec3, list[float]]] = []
        self._overlay_canvas = None
        try:
            self._im = InputManager.instance()
            self._im.start()
        except Exception:
            self._im = None
        self._focused: bool = False
        self._axis_gizmo_enabled = True
        self._axis_gizmo_hover = -1
        self._gizmo_visible = True
        self._gizmo_icons_visible = True
        self._overlay_widget = OverlayWidget(self, self)
        self._last_mouse_pos: tuple[int, int] = (0, 0)
        self._entity_clipboard: list[dict] = []
        self._multi_entity_initial_transforms: dict[str, dict] = {}
        self._collab_throttle_cursor: float = 0.0
        self._collab_throttle_camera: float = 0.0
        self._collab_cursor_interval: float = 1.0 / 30.0
        self._collab_camera_interval: float = 1.0 / 15.0
        self._collab_transform_interval: float = 1.0 / 20.0
        self._collab_gizmo_interval: float = 1.0 / 10.0
        self._collab_last_sent_transform: dict[str, dict] = {}
        self._collab_throttle_transform: float = 0.0
        self._collab_throttle_gizmo: float = 0.0
        self._collab_last_gizmo_state: tuple[str, int, bool] = ("none", -1, False)
        self._pb_scale_gizmo: "PbScaleGizmo | None" = None
        from editor.viewport.toolbar import setup_toolbar
        setup_toolbar(self)

    def _init_format(self):
        from core.config import get_global_config
        cfg = get_global_config()
        self._vsync_enabled = cfg.get("rendering.vsync", True)
        self._target_fps = cfg.get("rendering.target_fps", 60)
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setVersion(4, 6)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setSwapInterval(1 if self._vsync_enabled else 0)
        self.setFormat(fmt)
        self._update_timer.setInterval(16)
        if not self._vsync_enabled:
            try:
                import ctypes
                result = ctypes.windll.winmm.timeBeginPeriod(1)
                if result != 0:
                    ctypes.windll.winmm.timeBeginPeriod(2)
            except Exception:
                pass
        self._apply_config()

    def _apply_config(self):
        if not self._vsync_enabled:
            self._update_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._update_timer.setInterval(4)
        else:
            fps = self._target_fps
            if fps <= 0 or fps > 240:
                fps = 240
            interval = max(1, int(1000.0 / fps))
            self._update_timer.setInterval(interval)
        self._update_timer.start()

    def _toggle_stats(self, checked: bool):
        self._stats_enabled = checked
        if checked:
            self._fps_history.clear()
        self.update()

    def _on_fov_changed(self, value: float):
        self._cam._fov = value

    def _on_near_changed(self, value: float):
        self._cam._near = value

    def _on_far_changed(self, value: float):
        self._cam._far = value

    def _on_move_speed_changed(self, value: float):
        self._cam._move_speed = value

    def _on_rotate_speed_changed(self, value: float):
        self._cam._rotate_speed = value

    def _on_depth_changed(self, value: int):
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(value)
        fmt.setVersion(4, 6)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        self.setFormat(fmt)

    def showEvent(self, event):
        super().showEvent(event)
        self.update()

    def load_config(self, config) -> None:
        self._clear_color = [
            config.get("viewport.clear_r", self._clear_color[0]),
            config.get("viewport.clear_g", self._clear_color[1]),
            config.get("viewport.clear_b", self._clear_color[2]),
        ]
        self._no_scene_color = [
            config.get("viewport.no_scene_r", self._no_scene_color[0]),
            config.get("viewport.no_scene_g", self._no_scene_color[1]),
            config.get("viewport.no_scene_b", self._no_scene_color[2]),
        ]
        self._vsync_enabled = config.get("rendering.vsync", self._vsync_enabled)
        self._target_fps = config.get("rendering.target_fps", self._target_fps)
        self._update_interval = config.get("viewport.update_interval", self._update_interval)
        self._grid_step = config.get("viewport.grid_step", self._grid_step)
        self._apply_config()

    def set_grid_step(self, step: float):
        self._grid_step = max(0.01, step)

    def snap_to_grid(self, value: float) -> float:
        if self._grid_step <= 0:
            return value
        return round(value / self._grid_step) * self._grid_step

    def snap_vec3_to_grid(self, v: Vec3) -> Vec3:
        if self._grid_step <= 0:
            return v
        return Vec3(round(v.x / self._grid_step) * self._grid_step,
                    round(v.y / self._grid_step) * self._grid_step,
                    round(v.z / self._grid_step) * self._grid_step)

    @property
    def camera(self) -> SceneCamera:
        return self._cam

    @property
    def gizmo(self) -> Gizmo:
        return self._gizmo

    @property
    def renderer(self) -> Optional[Renderer]:
        return self._renderer

    @property
    def selected_entities(self) -> list:
        return self._selected_entities

    def _set_gizmo_entity(self, entity):
        self._gizmo.entity = entity
        self._update_gizmo_pivot()

    def _update_gizmo_pivot(self):
        if len(self._selected_entities) > 1:
            center = Vec3.zero()
            count = 0
            for ent in self._selected_entities:
                t = ent.get_component_by_name("Transform")
                if t:
                    center += t.position
                    count += 1
            if count > 0:
                center /= count
            pt = self._gizmo.entity.get_component_by_name("Transform") if self._gizmo.entity else None
            self._gizmo._pivot_offset = center - (pt.position if pt else Vec3.zero())
            self._gizmo._visual_center = None
        else:
            self._gizmo._pivot_offset = Vec3.zero()
            self._gizmo._visual_center = None

    def set_selected_entity(self, entity: Optional[Entity]):
        self._selected_entities = [entity] if entity else []
        self._set_gizmo_entity(entity)
        self._update_gizmo_pivot()
        from editor.viewport.collaboration import send_collab_selection
        send_collab_selection(self)

    def set_selected_entities(self, entities: list):
        self._selected_entities = list(entities)
        self._set_gizmo_entity(entities[0] if entities else None)
        self._update_gizmo_pivot()
        from editor.viewport.collaboration import send_collab_selection
        send_collab_selection(self)

    def _bind_screen_fbo(self):
        fbo_id = self.defaultFramebufferObject()
        if self._screen_fbo is None or not hasattr(self, '_last_fbo_id') or self._last_fbo_id != fbo_id:
            self._screen_fbo = self._ctx.detect_framebuffer(fbo_id)
            self._last_fbo_id = fbo_id
        self._screen_fbo.use()

    def _get_physical_dims(self):
        if self._physical_w > 0 and self._physical_h > 0:
            return self._physical_w, self._physical_h
        dpr = self.devicePixelRatio()
        return int(self.width() * dpr), int(self.height() * dpr)

    def _disable_dwm_throttle(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_NOREDIRECTIONBITMAP = 0x00200000
            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            hwnds = set()
            hwnds.add(int(self.winId()))
            child = user32.FindWindowExW(hwnd, None, None, None)
            while child:
                hwnds.add(child)
                child = user32.FindWindowExW(hwnd, child, None, None)
            for h in hwnds:
                current = user32.GetWindowLongW(h, GWL_EXSTYLE)
                user32.SetWindowLongW(h, GWL_EXSTYLE, current | WS_EX_NOREDIRECTIONBITMAP)
                user32.SetWindowPos(h, 0, 0, 0, 0, 0,
                                    SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            pass

    def initializeGL(self):
        try:
            self._ctx = moderngl.create_context(standalone=False)
            try:
                self._ctx.gc_mode = "context_gc"
            except Exception:
                pass
            self._bind_screen_fbo()
            if not self._vsync_enabled:
                self._disable_dwm_throttle()
                try:
                    import ctypes
                    opengl32 = ctypes.windll.opengl32
                    addr = opengl32.wglGetProcAddress(b"wglSwapIntervalEXT")
                    if addr:
                        func = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(addr)
                        func(0)
                except Exception:
                    pass
            from editor.renderer import Renderer
            self._renderer = Renderer(self._ctx)
            self._renderer.initialize()
            self._renderer.request_render(lambda: self.update())
            self._pb_scale_gizmo = PbScaleGizmo(self)
            self._engine.on("scene_loaded", self._on_scene_loaded)
            self._engine.on("play_stop", self._on_play_stop)
            self._engine.on("play_start", self._on_play_stop)
        except Exception as e:
            import traceback
            print(f"[Zarin Engine] OpenGL init error: {e}\n{traceback.format_exc()}", flush=True)
            Logger.error(f"OpenGL init error: {e}", e)

    def _on_scene_loaded(self, scene):
        self._gizmos_api.clear()
        Logger.info(f"_on_scene_loaded: selected={len(self._selected_entities)} scene_entities={len(scene._entities)}")
        old_ids = [e.id for e in self._selected_entities]
        resolved = [scene.get_entity(eid) for eid in old_ids if scene.get_entity(eid)]
        Logger.info(f"_on_scene_loaded: resolved {len(old_ids)} -> {len(resolved)}")
        self._selected_entities = resolved
        self._set_gizmo_entity(self._selected_entities[0] if self._selected_entities else None)
        if hasattr(self, '_sel_bounds_state'):
            self._sel_bounds_state = [None, None]
        if hasattr(self, '_sel_bounds_peers'):
            self._sel_bounds_peers.clear()
        self.entities_selected.emit(self._selected_entities)
        from editor.viewport.collaboration import send_collab_selection; send_collab_selection(self)

    def _on_play_stop(self, data=None):
        self._gizmos_api.clear()

    def resizeGL(self, w: int, h: int):
        dpr = self.devicePixelRatio()
        pw, ph = int(w * dpr), int(h * dpr)
        self._physical_w = pw
        self._physical_h = ph
        self._cam.set_viewport_size(w, h)
        if hasattr(self, '_toolbar') and self._toolbar:
            self._toolbar.setGeometry(0, 0, w, self._toolbar.height())
        self._overlay_widget.resize(w, h)
        if self._ctx:
            self._bind_screen_fbo()
            self._ctx.viewport = (0, 0, pw, ph)

    def paintGL(self):
        _p0 = time.perf_counter()
        bu = getattr(self, '_before_update', 0)
        if bu:
            self._engine.set_profiler_data("update_to_paint_ms", (_p0 - bu) * 1000.0)
            self._before_update = 0
        now = _p0
        self._fps_accum += now - self._last_paint_time
        self._last_paint_time = now
        self._fps_frames += 1
        if self._fps_accum >= 0.5:
            self._fps = self._fps_frames / self._fps_accum
            self._fps_accum = 0.0
            self._fps_frames = 0
        if not self._ctx or not self._renderer:
            return
        eng = self._engine
        prof = eng._profiler if hasattr(eng, '_profiler') else None
        in_frame = prof is not None and len(prof._stack) > 0 and prof._stack[0][0] == "frame"
        try:
            if in_frame:
                prof.start("gl_setup")
            self._bind_screen_fbo()
            scene = eng.scene
            cam_cc = self._clear_color + [1.0] if scene else self._no_scene_color + [1.0]
            self._screen_fbo.clear(*cam_cc[:3], 1.0)
            self._renderer.clear_color = self._clear_color
            if in_frame:
                prof.stop("gl_setup")
            if scene:
                fw, fh = self._get_physical_dims()
                aspect = fw / max(1, fh)
                view = self._cam.get_view_matrix()
                proj = self._cam.get_projection_matrix(aspect)
                cam_pos = self._cam.position
                self._renderer.grid_2d_mode = self._cam.is_2d_mode
                self._renderer.grid_zoom_distance = self._cam._ortho_zoom_distance
                t0 = time.perf_counter()
                with eng._scene_lock:
                    self._renderer.render_scene(scene, view, proj, cam_pos, fw, fh, self._screen_fbo,
                                                set(self._selected_entities), self._cam.near, self._cam.far, self._cam.fov)
                render_ms = (time.perf_counter() - t0) * 1000.0
                eng.set_profiler_data("render_ms", render_ms)
                vp_mat = view * proj
                dpr = self.devicePixelRatio()
                self._renderer._line_width = max(1.0, float(dpr) * 1.0)
                t1 = time.perf_counter()
                if in_frame:
                    prof.start("gizmo_wireframes")
                if self._gizmo_visible:
                    with eng._scene_lock:
                        render_collider_wireframes(self, vp_mat)
                        render_particle_emitter_wireframes(self, vp_mat)
                        render_camera_frustums(self, vp_mat)
                        render_audio_source_gizmos(self, vp_mat)
                        render_reverb_zone_gizmos(self, vp_mat)
                        render_script_gizmos(self, vp_mat)
                if in_frame:
                    prof.stop("gizmo_wireframes")
                with eng._scene_lock:
                    render_selection_bounds(self, vp_mat, time.perf_counter(), self._last_dt)
                if in_frame:
                    prof.start("gizmo_icons")
                try:
                    with eng._scene_lock:
                        render_component_icons_gl(self)
                except Exception:
                    pass
                if self._debug_lines:
                    self._renderer.render_gizmo_lines(self._debug_lines, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.0)
                    self._debug_lines.clear()
                draw_axis_gizmo_api(self)
                self._render_api_gizmos()
                if self._pb_scale_gizmo and self._pb_scale_gizmo.active:
                    self._pb_scale_gizmo.render()
                if in_frame:
                    prof.stop("gizmo_icons")
                if in_frame:
                    prof.start("gizmo_collab")
                try:
                    with eng._scene_lock:
                        render_remote_collaborator_gizmos(self, vp_mat, cam_pos, fw, fh)
                except Exception:
                    pass
                if in_frame:
                    prof.stop("gizmo_collab")
                if self._gizmo_visible:
                    gizmo_result = self._gizmo.get_gizmo_arrays(self._cam, fw, fh)
                    if gizmo_result is not None:
                        gs, ge, gc = gizmo_result
                        self._renderer.render_gizmo_arrays(gs, ge, gc, vp_mat, fw, fh, thickness_multiplier=1.0)
                    else:
                        gizmo_lines = self._gizmo.get_gizmo_lines(self._cam, fw, fh)
                        if gizmo_lines:
                            self._renderer.render_gizmo_lines(gizmo_lines, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.0)
                eng.set_profiler_data("gizmo_time", (time.perf_counter() - t1) * 1000.0)
                t2 = time.perf_counter()
                if in_frame:
                    prof.start("overlay_draw")
                self._overlay_widget.resize(self.width(), self.height())
                if in_frame:
                    prof.stop("overlay_draw")
                eng.set_profiler_data("overlay_time", (time.perf_counter() - t2) * 1000.0)
            eng.set_profiler_data("paint_total_ms", (time.perf_counter() - _p0) * 1000.0)
        except Exception as e:
            traceback.print_exc()
            Logger.error(f"Render error: {e}", e)
        eng.set_profiler_data("paint_full_ms", (time.perf_counter() - _p0) * 1000.0)
        if not self._vsync_enabled and self.isVisible():
            self.update()

    def update_scene(self):
        _u0 = time.perf_counter()
        eng = self._engine
        eng.set_profiler_data("timer_interval_ms", float(self._update_timer.interval()))
        eng.set_profiler_data("target_fps", float(self._target_fps))
        prof = eng._profiler
        prof.capture_frame()
        prof.start("frame")
        now = time.perf_counter()
        dt = now - self._last_frame_time
        self._last_frame_time = now
        self._last_dt = dt
        prof.start("input_handling")
        if self._im:
            self._im.new_frame()
        if self._focused and self.isActiveWindow():
            if self._im and self._im.key_just_pressed(KEY_Q):
                self._gizmo.mode = GizmoMode.NONE
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_W):
                self._gizmo.mode = GizmoMode.TRANSLATE
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_E):
                self._gizmo.mode = GizmoMode.ROTATE
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_R):
                self._gizmo.mode = GizmoMode.SCALE
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_F):
                if self._selected_entities:
                    t = self._selected_entities[0].get_component_by_name("Transform")
                    if t:
                        self._cam.frame_bounds(t.position)
            elif self._im and self._im.key_just_pressed(KEY_DELETE):
                if self._selected_entities and eng.scene:
                    from editor.viewport.collaboration import is_collab_locked
                    if not is_collab_locked(self):
                        from core.commands import DeleteEntityCommand, get_history
                        for ent in list(self._selected_entities):
                            cmd = DeleteEntityCommand(eng.scene, ent.id)
                            get_history().execute(cmd)
                        self._selected_entities.clear()
                        self._set_gizmo_entity(None)
                        self.entity_selected.emit(None)
                        from editor.viewport.collaboration import send_collab_selection; send_collab_selection(self)
        prof.stop("input_handling")
        prof.start("logic_update")
        if eng.play_mode:
            pass
        else:
            prof.start("editor_particles")
            self._update_editor_particles(dt, self._selected_entities)
            prof.stop("editor_particles")
        prof.start("collab_camera")
        send_collab_camera(self)
        prof.stop("collab_camera")
        prof.start("cam_update")
        self._cam.update(dt)
        prof.stop("cam_update")
        self._gizmos_api.update(dt)
        prof.stop("logic_update")
        prof.start("render_widget")
        if self.isVisible():
            _u1 = time.perf_counter()
            eng.set_profiler_data("full_frame_ms", (_u1 - self._last_update_gap) * 1000.0)
            self._last_update_gap = _u1
            self._before_update = _u1
            if self._vsync_enabled:
                self.update()
        prof.stop("render_widget")
        self._update_status_labels()
        eng.set_profiler_data("logic_total_ms", (time.perf_counter() - _u0) * 1000.0)
        prof.stop("frame")

    def _update_editor_particles(self, dt: float, selected: list = None):
        from core.components import ParticleSystem
        scene = self._engine.scene
        if not scene:
            return
        selected_ids = {e.id for e in (selected or [])}
        for ent in scene.get_entities_with_component(ParticleSystem):
            if not ent.active:
                continue
            ps = ent.get_component(ParticleSystem)
            if not ps or not ps.enabled:
                continue
            if ent.id not in selected_ids:
                continue
            try:
                ps.on_update(dt)
            except Exception:
                pass

    def _update_status_labels(self):
        pos = self._cam.position
        self._cam_pos_label.setText(f"Cam: {pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f}")

    def _forward_to_overlay(self, event):
        if self._overlay_canvas and not self._overlay_canvas.edit_mode:
            return True
        return False

    def mousePressEvent(self, event: QMouseEvent):
        if self._overlay_canvas:
            if self._overlay_canvas.edit_mode:
                self._overlay_canvas.mousePressEvent(event)
                return
            hit = self._overlay_canvas.hit_test_widget(event.position().x(), event.position().y())
            if hit:
                self._overlay_canvas.mousePressEvent(event)
                return
        self._focused = True
        self.setFocus()
        dpr = self.devicePixelRatio()
        lx, ly = int(event.position().x()), int(event.position().y())
        x, y = int(lx * dpr), int(ly * dpr)
        qt_btn = event.button()
        alt = self._im.is_key_pressed(KEY_ALT) if self._im else False
        shift = self._im.is_key_pressed(KEY_SHIFT) if self._im else False
        ctrl = self._im.is_key_pressed(KEY_CTRL) if self._im else False
        self._gizmo.ctrl_down = ctrl
        btn = MOUSE_L if qt_btn == Qt.MouseButton.LeftButton else (MOUSE_R if qt_btn == Qt.MouseButton.RightButton else MOUSE_M)
        if self._im:
            self._im.feed_mouse_button(btn, True)
        self._cam.on_mouse_press(btn, lx, ly, alt)
        from editor.viewport.collaboration import send_collab_cursor
        send_collab_cursor(self, lx, ly)
        if btn == MOUSE_L and not alt:
            from editor.viewport.axis_gizmo import hit_test_axis_gizmo, snap_camera_to_axis
            axis_hit = hit_test_axis_gizmo(self, lx, ly)
            if axis_hit >= 0:
                snap_camera_to_axis(self, axis_hit)
                return
            if self._pb_scale_gizmo and self._pb_scale_gizmo.active and self._pb_scale_gizmo.on_mouse_press(lx, ly):
                return
            if self._gizmo.on_mouse_press(x, y, self._cam, *self._get_physical_dims()):
                self._multi_entity_initial_transforms = {}
                for ent in self._selected_entities:
                    et = ent.get_component_by_name("Transform")
                    if et:
                        self._multi_entity_initial_transforms[ent.id] = {
                            "position": Vec3(et.position.x, et.position.y, et.position.z),
                            "local_rotation": Quat(et.local_rotation.x, et.local_rotation.y, et.local_rotation.z, et.local_rotation.w),
                            "local_scale": Vec3(et.local_scale.x, et.local_scale.y, et.local_scale.z),
                        }
                return
            from editor.viewport.picking import pick_entity
            picked = pick_entity(self, lx, ly)
            if shift:
                if picked:
                    if picked in self._selected_entities:
                        self._selected_entities.remove(picked)
                    else:
                        self._selected_entities.append(picked)
                    self._set_gizmo_entity(self._selected_entities[0] if self._selected_entities else None)
                    self.entities_selected.emit(self._selected_entities)
                else:
                    self._selected_entities = []
                    self._set_gizmo_entity(None)
                    self.entity_selected.emit(None)
                from editor.viewport.collaboration import send_collab_selection; send_collab_selection(self)
                return
            if ctrl:
                if picked:
                    if picked in self._selected_entities:
                        self._selected_entities.remove(picked)
                    else:
                        self._selected_entities.append(picked)
                    self._set_gizmo_entity(self._selected_entities[0] if self._selected_entities else None)
                    self.entities_selected.emit(self._selected_entities)
                else:
                    self._selected_entities = []
                    self._set_gizmo_entity(None)
                    self.entity_selected.emit(None)
                from editor.viewport.collaboration import send_collab_selection; send_collab_selection(self)
                return
            self._area_selecting = True
            self._area_start = (lx, ly)
            self._area_end = (lx, ly)
            self.update()
            if picked != (self._selected_entities[0] if self._selected_entities else None):
                self._selected_entities = [picked] if picked else []
                self._set_gizmo_entity(picked)
                self.entity_selected.emit(picked)
                from editor.viewport.collaboration import send_collab_selection; send_collab_selection(self)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._overlay_canvas and self._overlay_canvas.edit_mode:
            self._overlay_canvas.mouseMoveEvent(event)
            return
        dpr = self.devicePixelRatio()
        lx, ly = int(event.position().x()), int(event.position().y())
        self._last_mouse_pos = (lx, ly)
        px, py = int(lx * dpr), int(ly * dpr)
        ctrl = self._im.is_key_pressed(KEY_CTRL) if self._im else False
        self._gizmo.ctrl_down = ctrl
        self._cam.on_mouse_move(lx, ly)
        from editor.viewport.axis_gizmo import hit_test_axis_gizmo
        new_hover = hit_test_axis_gizmo(self, lx, ly)
        if new_hover != self._axis_gizmo_hover:
            self._axis_gizmo_hover = new_hover
            self.update()
        from editor.viewport.collaboration import send_collab_cursor
        send_collab_cursor(self, lx, ly)
        from editor.viewport.projection import screen_to_world
        world_pos = screen_to_world(self, lx, ly)
        self._cursor_x_label.setText(f"X: {world_pos.x:.2f}")
        self._cursor_y_label.setText(f"Y: {world_pos.y:.2f}")
        self._cursor_z_label.setText(f"Z: {world_pos.z:.2f}")
        if self._area_selecting:
            self._area_end = (lx, ly)
            self.update()
        else:
            if self._pb_scale_gizmo and self._pb_scale_gizmo._dragging:
                self._pb_scale_gizmo.on_mouse_move(lx, ly)
                self.update()
                return
            primary = self._gizmo._entity
            multi = len(self._selected_entities) > 1 and primary is not None and self._gizmo._dragging
            pre_pos = None
            pre_rot = None
            pre_scale = None
            if multi:
                pt = primary.get_component_by_name("Transform")
                if pt:
                    pre_pos = Vec3(pt.position.x, pt.position.y, pt.position.z)
                    pre_rot = Quat(pt.local_rotation.x, pt.local_rotation.y, pt.local_rotation.z, pt.local_rotation.w)
                    pre_scale = Vec3(pt.local_scale.x, pt.local_scale.y, pt.local_scale.z)
            self._gizmo.on_mouse_move(px, py, self._cam, *self._get_physical_dims())
            from editor.viewport.collaboration import send_collab_gizmo_state, send_collab_transforms
            send_collab_gizmo_state(self)
            if self._gizmo._dragging:
                send_collab_transforms(self)
            if multi and pre_pos is not None:
                pt = primary.get_component_by_name("Transform")
                if pt:
                    center = Vec3.zero()
                    count = 0
                    for init in self._multi_entity_initial_transforms.values():
                        center += init["position"]
                        count += 1
                    if count > 0:
                        center /= count
                    if self._gizmo._mode == GizmoMode.ROTATE:
                        primary_init = self._multi_entity_initial_transforms.get(primary.id)
                        if primary_init:
                            world_rot_rel = (pt.local_rotation * primary_init["local_rotation"].conjugate()).normalized()
                            for eid, init in self._multi_entity_initial_transforms.items():
                                ent = self._engine.scene.get_entity(eid)
                                if not ent:
                                    continue
                                et = ent.get_component_by_name("Transform")
                                if et:
                                    offset = init["position"] - center
                                    rotated = world_rot_rel.rotate_vec3(offset)
                                    et.position = center + rotated
                                    et.local_rotation = (world_rot_rel * init["local_rotation"]).normalized()
                    elif self._gizmo._mode == GizmoMode.SCALE:
                        primary_init = self._multi_entity_initial_transforms.get(primary.id)
                        if primary_init:
                            dS_current = Vec3(
                                pt.local_scale.x / max(0.001, primary_init["local_scale"].x),
                                pt.local_scale.y / max(0.001, primary_init["local_scale"].y),
                                pt.local_scale.z / max(0.001, primary_init["local_scale"].z),
                            )
                        else:
                            dS_current = Vec3(1, 1, 1)
                        world_rot_rel = (pt.local_rotation * pre_rot.conjugate()).normalized()
                        for eid, init in self._multi_entity_initial_transforms.items():
                            ent = self._engine.scene.get_entity(eid)
                            if not ent:
                                continue
                            et = ent.get_component_by_name("Transform")
                            if et:
                                offset = init["position"] - center
                                et.position = center + Vec3(
                                    offset.x * dS_current.x,
                                    offset.y * dS_current.y,
                                    offset.z * dS_current.z,
                                )
                                et.local_rotation = (world_rot_rel * init["local_rotation"]).normalized()
                                if eid != primary.id:
                                    et.local_scale = Vec3(
                                        max(0.001, init["local_scale"].x * dS_current.x),
                                        max(0.001, init["local_scale"].y * dS_current.y),
                                        max(0.001, init["local_scale"].z * dS_current.z),
                                    )
                    else:
                        pos_delta = pt.position - pre_pos
                        world_rot_rel = (pt.local_rotation * pre_rot.conjugate()).normalized()
                        for ent in self._selected_entities:
                            if ent is primary:
                                continue
                            et = ent.get_component_by_name("Transform")
                            if et:
                                et.position = et.position + pos_delta
                                et.local_rotation = (world_rot_rel * et.local_rotation).normalized()
                    new_center = Vec3.zero()
                    cnt = 0
                    for ent in self._selected_entities:
                        et = ent.get_component_by_name("Transform")
                        if et:
                            new_center += et.position
                            cnt += 1
                    if cnt > 0:
                        new_center /= cnt
                    self._gizmo._visual_center = new_center

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._overlay_canvas:
            if self._overlay_canvas.edit_mode:
                self._overlay_canvas.mouseReleaseEvent(event)
                return
            hit = self._overlay_canvas.hit_test_widget(event.position().x(), event.position().y())
            if hit:
                self._overlay_canvas.mouseReleaseEvent(event)
                return
        qt_btn = event.button()
        btn = MOUSE_L if qt_btn == Qt.MouseButton.LeftButton else (MOUSE_R if qt_btn == Qt.MouseButton.RightButton else MOUSE_M)
        if self._im:
            self._im.feed_mouse_button(btn, False)
        self._cam.on_mouse_release(btn)
        if btn == MOUSE_L and self._area_selecting:
            self._area_selecting = False
            x1, y1 = self._area_start
            x2, y2 = self._area_end
            if abs(x2 - x1) > 3 or abs(y2 - y1) > 3:
                from editor.viewport.picking import pick_entities_in_rect
                selected = pick_entities_in_rect(self, min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                if selected:
                    self._selected_entities = selected
                    self._set_gizmo_entity(self._selected_entities[0] if self._selected_entities else None)
                    self.entities_selected.emit(self._selected_entities)
                    from editor.viewport.collaboration import send_collab_selection; send_collab_selection(self)
            self.update()
        multi = bool(self._multi_entity_initial_transforms and len(self._selected_entities) > 1)
        self._gizmo._multi_undo_active = multi
        self._gizmo.on_mouse_release()
        self._gizmo._multi_undo_active = False
        if self._pb_scale_gizmo and self._pb_scale_gizmo._dragging:
            self._pb_scale_gizmo.on_mouse_release()
            self.update()
        if self._multi_entity_initial_transforms:
            from core.commands import SetComponentCommand, CompoundCommand, get_history
            from core.components import Transform as TransformComponent
            cmds = []
            for ent in self._selected_entities:
                init = self._multi_entity_initial_transforms.get(ent.id)
                if not init:
                    continue
                et = ent.get_component_by_name("Transform")
                if not et:
                    continue
                if self._gizmo._mode == GizmoMode.TRANSLATE:
                    new_pos = et.position
                    if (new_pos - init["position"]).length() > 1e-8:
                        cmds.append(SetComponentCommand(ent, TransformComponent, "position", init["position"], new_pos))
                elif self._gizmo._mode in (GizmoMode.ROTATE, GizmoMode.SCALE):
                    new_pos = et.position
                    if (new_pos - init["position"]).length() > 1e-8:
                        cmds.append(SetComponentCommand(ent, TransformComponent, "position", init["position"], new_pos))
                    if self._gizmo._mode == GizmoMode.ROTATE:
                        new_rot = et.local_rotation
                        cmds.append(SetComponentCommand(ent, TransformComponent, "local_rotation", init["local_rotation"], new_rot))
                    else:
                        new_scale = et.local_scale
                        if (new_scale - init["local_scale"]).length() > 1e-8:
                            cmds.append(SetComponentCommand(ent, TransformComponent, "local_scale", init["local_scale"], new_scale))
            if cmds:
                get_history().set_current_selection(list(self._selected_entities))
                get_history().execute(CompoundCommand(cmds, "Multi-Entity Transform"))
            self._multi_entity_initial_transforms = {}
            self._update_gizmo_pivot()
        from editor.viewport.collaboration import send_collab_transforms
        send_collab_transforms(self)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y() / 120.0
        cx, cy = int(event.position().x()), int(event.position().y())
        self._cam.on_scroll(delta, cx, cy)
        if self._im:
            self._im.feed_scroll(0.0, delta)

    def keyPressEvent(self, event: QKeyEvent):
        self._focused = True
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C:
                self._copy_selected_entities()
                event.accept()
                return
            if event.key() == Qt.Key.Key_V:
                self._paste_entities()
                event.accept()
                return
        if self._im:
            vk = self._qt_key_to_vk(event.key())
            if vk is None:
                nvk = event.nativeVirtualKey()
                if 65 <= nvk <= 90:
                    vk = nvk
            if vk is not None:
                self._im.feed_key(vk, True)
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self._im.feed_key(KeyCode.LEFT_SHIFT, True)
            if mods & Qt.KeyboardModifier.ControlModifier:
                self._im.feed_key(KeyCode.LEFT_CONTROL, True)
            if mods & Qt.KeyboardModifier.AltModifier:
                self._im.feed_key(KeyCode.LEFT_ALT, True)
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        if self._im:
            mods = event.modifiers()
            vk = self._qt_key_to_vk(event.key())
            if vk is None:
                nvk = event.nativeVirtualKey()
                if 65 <= nvk <= 90:
                    vk = nvk
            if vk is not None:
                self._im.feed_key(vk, False)
            if not (mods & Qt.KeyboardModifier.ShiftModifier):
                self._im.feed_key(KeyCode.LEFT_SHIFT, False)
            if not (mods & Qt.KeyboardModifier.ControlModifier):
                self._im.feed_key(KeyCode.LEFT_CONTROL, False)
            if not (mods & Qt.KeyboardModifier.AltModifier):
                self._im.feed_key(KeyCode.LEFT_ALT, False)
        event.accept()

    @staticmethod
    def _qt_key_to_vk(qt_key: int) -> Optional[int]:
        mapping = {
            Qt.Key.Key_W: KEY_W, Qt.Key.Key_A: KEY_A,
            Qt.Key.Key_S: KEY_S, Qt.Key.Key_D: KEY_D,
            Qt.Key.Key_Q: KEY_Q, Qt.Key.Key_E: KEY_E,
            Qt.Key.Key_R: KEY_R, Qt.Key.Key_F: KEY_F,
            Qt.Key.Key_Shift: KEY_SHIFT,
            Qt.Key.Key_Control: KEY_CTRL,
            Qt.Key.Key_Alt: KEY_ALT,
            Qt.Key.Key_Delete: KEY_DELETE,
            Qt.Key.Key_Space: KEY_SPACE,
        }
        return mapping.get(qt_key)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        create_menu = menu.addMenu("Create")
        create_empty = create_menu.addAction("Empty")
        create_empty.triggered.connect(lambda: self._emit_create_request())
        primitives_menu = create_menu.addMenu("3D Object")
        for name in ["Cube", "Sphere", "Plane"]:
            act = primitives_menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name.lower(): self._emit_create_request(n))
        lights_menu = create_menu.addMenu("Light")
        for ltype in ["Directional", "Point", "Spot"]:
            act = lights_menu.addAction(ltype)
            act.triggered.connect(lambda checked=False, lt=ltype.lower(): self._emit_create_request("light", lt))
        cam_act = create_menu.addAction("Camera")
        cam_act.triggered.connect(lambda: self._emit_create_request("camera"))
        effects_menu = create_menu.addMenu("Effects")
        ps_act = effects_menu.addAction("Particle System")
        ps_act.triggered.connect(lambda: self._emit_create_request("particle_system"))
        if self._selected_entities:
            menu.addSeparator()
            delete_act = menu.addAction("Delete")
            from editor.viewport.collaboration import is_collab_locked
            delete_act.setEnabled(not is_collab_locked(self))
            delete_act.triggered.connect(self._delete_selected)
        if is_collab_locked(self):
            create_menu.setEnabled(False)
        menu.exec(event.globalPos())

    def _emit_create_request(self, obj_type="empty", subtype=None):
        from core.commands import CreateEntityCommand, get_history
        from core.components import Transform, MeshFilter, MeshRenderer, Light, LightType, Camera, ParticleSystem
        scene = self._engine.scene
        from editor.viewport.collaboration import is_collab_locked
        if not scene or is_collab_locked(self):
            return
        if obj_type == "particle_system":
            cmd = CreateEntityCommand(scene, "Particle System")
            get_history().execute(cmd)
            e = scene.get_entity(cmd._entity_id)
            if e:
                e.add_component(Transform())
                e.add_component(ParticleSystem())
        elif obj_type == "empty":
            cmd = CreateEntityCommand(scene, "GameObject")
            get_history().execute(cmd)
            e = scene.get_entity(cmd._entity_id)
            if e:
                e.add_component(Transform())
        elif obj_type == "cube":
            cmd = CreateEntityCommand(scene, "Cube")
            get_history().execute(cmd)
            e = scene.get_entity(cmd._entity_id)
            if e:
                e.add_component(Transform())
                mf = MeshFilter(); mf.mesh_name = "cube"; e.add_component(mf)
                e.add_component(MeshRenderer())
        elif obj_type == "sphere":
            cmd = CreateEntityCommand(scene, "Sphere")
            get_history().execute(cmd)
            e = scene.get_entity(cmd._entity_id)
            if e:
                e.add_component(Transform())
                mf = MeshFilter(); mf.mesh_name = "sphere"; e.add_component(mf)
                e.add_component(MeshRenderer())
        elif obj_type == "plane":
            cmd = CreateEntityCommand(scene, "Plane")
            get_history().execute(cmd)
            e = scene.get_entity(cmd._entity_id)
            if e:
                e.add_component(Transform())
                mf = MeshFilter(); mf.mesh_name = "plane"; e.add_component(mf)
                e.add_component(MeshRenderer())
        elif obj_type == "light" and subtype:
            name_map = {"directional": "Directional Light", "point": "Point Light", "spot": "Spot Light"}
            type_map = {"directional": LightType.DIRECTIONAL, "point": LightType.POINT, "spot": LightType.SPOT}
            cmd = CreateEntityCommand(scene, name_map.get(subtype, "Light"))
            get_history().execute(cmd)
            e = scene.get_entity(cmd._entity_id)
            if e:
                e.add_component(Transform())
                l = Light(); l.light_type = type_map[subtype]; e.add_component(l)
        elif obj_type == "camera":
            cmd = CreateEntityCommand(scene, "Camera")
            get_history().execute(cmd)
            e = scene.get_entity(cmd._entity_id)
            if e:
                e.add_component(Transform())
                e.add_component(Camera())
        else:
            return
        if e:
            self._selected_entities = [e]
            self._set_gizmo_entity(e)
            self.entity_selected.emit(e)
            from editor.viewport.collaboration import send_collab_entity_create
            send_collab_entity_create(self, e.serialize())

    def _delete_selected(self):
        if not self._selected_entities or not self._engine.scene:
            return
        from editor.viewport.collaboration import is_collab_locked
        if is_collab_locked(self):
            return
        from core.commands import DeleteEntityCommand, get_history
        for ent in list(self._selected_entities):
            from editor.viewport.collaboration import send_collab_entity_delete
            send_collab_entity_delete(self, ent.id)
            cmd = DeleteEntityCommand(self._engine.scene, ent.id)
            get_history().execute(cmd)
        self._selected_entities.clear()
        self._set_gizmo_entity(None)
        self.entity_selected.emit(None)

    def _copy_selected_entities(self):
        if not self._selected_entities:
            return
        seen = set()
        to_serialize = []
        for e in self._selected_entities:
            if e.id in seen:
                continue
            stack = [(e, True)]
            while stack:
                current, is_top = stack.pop()
                if current.id in seen:
                    continue
                seen.add(current.id)
                to_serialize.append((current, is_top))
                for child in current.children:
                    stack.append((child, False))
        self._entity_clipboard = []
        for e, is_top in to_serialize:
            data = copy.deepcopy(e.serialize())
            if is_top:
                data["parent"] = None
            t = e.get_component_by_name("Transform")
            if t:
                world_pos, world_rot, world_scale = t.world_matrix.decompose()
                for comp_data in data.get("components", []):
                    if comp_data.get("_key") == "Transform":
                        comp_data["local_position"] = world_pos.to_list()
                        comp_data["local_rotation"] = world_rot.to_list()
                        comp_data["local_scale"] = world_scale.to_list()
                        break
            self._entity_clipboard.append(data)

    def _paste_entities(self):
        from core.engine import Engine
        from core.commands import PasteEntitiesCommand, get_history
        registry = Engine.instance()._component_registry
        if not self._entity_clipboard or not self._engine.scene:
            return
        cmd = PasteEntitiesCommand(self._engine.scene, self._entity_clipboard, registry)
        get_history().execute(cmd)
        top_entities = []
        for eid in cmd.spawned_ids:
            e = self._engine.scene.get_entity(eid)
            if e and e.parent is None:
                top_entities.append(e)
        self._selected_entities = top_entities
        self._set_gizmo_entity(top_entities[0] if top_entities else None)
        from editor.viewport.collaboration import send_collab_entity_create, send_collab_selection
        for eid in cmd.spawned_ids:
            e = self._engine.scene.get_entity(eid)
            if e:
                send_collab_entity_create(self, e.serialize())
        send_collab_selection(self)
        self.scene_modified.emit()
        self.entities_selected.emit(self._selected_entities)
        if top_entities:
            self.entity_selected.emit(top_entities[0])

    def enterEvent(self, event):
        self._focused = True

    def focusInEvent(self, event):
        self._focused = True
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._focused = False
        super().focusOutEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-zpep"):
            event.acceptProposedAction()

    def _drop_world_pos(self, sx: int, sy: int):
        from editor.viewport.projection import screen_to_ray
        from core.math3d import Vec3
        ray_origin, ray_dir = screen_to_ray(self, sx, sy)
        from editor.viewport.picking import pick_entity
        hit_entity = pick_entity(self, sx, sy)
        if hit_entity is not None:
            from editor.viewport.picking import _world_aabb_of, _ray_aabb_min
            box = _world_aabb_of(hit_entity)
            if box is not None:
                d = _ray_aabb_min(ray_origin.x, ray_origin.y, ray_origin.z,
                                  ray_dir.x, ray_dir.y, ray_dir.z,
                                  box[0][0], box[0][1], box[0][2],
                                  box[1][0], box[1][1], box[1][2])
                if d > 0 and d < 1e6:
                    return ray_origin + ray_dir * d, hit_entity
            return ray_origin + ray_dir * 50.0, hit_entity
        if abs(ray_dir.y) > 0.0001:
            t = -ray_origin.y / ray_dir.y
            if t > 0:
                return ray_origin + ray_dir * t, None
        return ray_origin + ray_dir * 10.0, None

    def dropEvent(self, event):
        pos = event.position()
        sx, sy = int(pos.x()), int(pos.y())
        world_pos, hit_entity = self._drop_world_pos(sx, sy)
        if event.mimeData().hasFormat("application/x-zpep"):
            path = bytes(event.mimeData().data("application/x-zpep")).decode()
            self.entity_dropped.emit(path, world_pos, hit_entity)
        elif event.mimeData().hasText():
            text = event.mimeData().text()
            self.entity_dropped.emit(text, world_pos, hit_entity)
        event.acceptProposedAction()

    def screen_to_ray(self, sx: int, sy: int) -> tuple[Vec3, Vec3]:
        from editor.viewport.projection import screen_to_ray as _screen_to_ray
        return _screen_to_ray(self, sx, sy)

    def screen_to_plane(self, sx: int, sy: int, plane_point: Vec3) -> Vec3:
        from editor.viewport.projection import screen_to_plane as _screen_to_plane
        return _screen_to_plane(self, sx, sy, plane_point)

    def add_debug_line(self, start: Vec3, end: Vec3, color: list[float]):
        self._debug_lines.append((start, end, color))

    def _render_api_gizmos(self):
        gm = self._gizmos_api
        if not gm or not gm.enabled:
            return
        fw, fh = self._get_physical_dims()
        view = self._cam.get_view_matrix()
        proj = self._cam.get_projection_matrix(fw / max(1, fh))
        vp_mat = view * proj
        np_data = gm._get_render_data()
        gm._batches.clear()
        if np_data is not None:
            gs, ge, gc = np_data
            self._renderer.render_gizmo_arrays(gs, ge, gc, vp_mat, fw, fh, thickness_multiplier=1.0)
        all_g = list(gm.unique_draws.values()) + gm.draws + gm.persistent_draws
        if not all_g:
            gm.draws.clear()
            return
        s_list: list[np.ndarray] = []
        e_list: list[np.ndarray] = []
        c_list: list[np.ndarray] = []
        for g in all_g:
            builder = _GIZMO_LINE_BUILDERS.get(g.gizmo_type)
            if builder is not None:
                result = builder(g)
                if result is not None:
                    s, e, c = result
                    s, e, c = _apply_line_style(s, e, c, g.line_style, g.dash_length, g.gap_length)
                    if s.shape[0] > 0:
                        s_list.append(s)
                        e_list.append(e)
                        c_list.append(c)
        if s_list:
            self._renderer.render_gizmo_arrays(
                np.concatenate(s_list), np.concatenate(e_list), np.concatenate(c_list),
                vp_mat, fw, fh, thickness_multiplier=1.0)
        gm.draws.clear()
