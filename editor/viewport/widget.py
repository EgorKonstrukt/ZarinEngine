from __future__ import annotations

import copy
import math
import os
import time
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
from editor.gizmo.gizmo import Gizmo, GizmoMode
from core.input_system import Input, KeyCode
from editor.input_manager import InputManager
from editor.constants import (KEY_Q, KEY_W, KEY_E, KEY_R, KEY_F, KEY_DELETE, KEY_SHIFT, KEY_CTRL, KEY_ALT,
                              KEY_SPACE, KEY_S, KEY_D, KEY_A, MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE,
                              MOUSE_L, MOUSE_R, MOUSE_M)
from editor.viewport.overlay_widget import OverlayWidget
from editor.viewport.axis_gizmo import get_axis_gizmo_lines
from editor.viewport.rendering import (
    render_collider_wireframes,
    render_particle_emitter_wireframes,
    render_camera_frustums,
    render_audio_source_gizmos,
    render_reverb_zone_gizmos,
    render_script_gizmos,
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
    entity_dropped = pyqtSignal(str, object)
    scene_modified = pyqtSignal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._ctx: Optional[moderngl.Context] = None
        self._renderer: Optional[Renderer] = None
        self._cam: SceneCamera = SceneCamera()
        self._cam.set_viewport_size(self.width(), self.height())
        self._gizmo: Gizmo = Gizmo()
        self._selected_entities: list = []
        self._last_frame_time: float = time.perf_counter()
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
        self._init_format()
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
        self._AXIS_GIZMO_SIZE = 100
        self._AXIS_GIZMO_MARGIN = 8
        self._AXIS_ARROW_LEN = 32
        self._AXIS_ARROW_HEAD = 6
        from editor.viewport.toolbar import setup_toolbar
        setup_toolbar(self)

    def _init_format(self):
        from core.config import get_global_config
        cfg = get_global_config()
        self._vsync_enabled = cfg.get("rendering.vsync", True)
        self._target_fps = cfg.get("rendering.target_fps", 60)
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setVersion(3, 3)
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
            self._update_timer.setInterval(1)
            self._update_timer.start()
            self.update()
        elif self._target_fps > 0:
            self._update_timer.setInterval(max(1, int(1000.0 / self._target_fps)))
            self._update_timer.start()
        else:
            self._update_timer.setInterval(16)
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
        fmt.setVersion(3, 3)
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

    def set_selected_entity(self, entity: Optional[Entity]):
        self._selected_entities = [entity] if entity else []
        self._gizmo.entity = entity
        from editor.viewport.collaboration import send_collab_selection
        send_collab_selection(self)

    def set_selected_entities(self, entities: list):
        self._selected_entities = list(entities)
        self._gizmo.entity = entities[0] if entities else None
        from editor.viewport.collaboration import send_collab_selection
        send_collab_selection(self)

    def _bind_screen_fbo(self):
        fbo_id = self.defaultFramebufferObject()
        self._screen_fbo = self._ctx.detect_framebuffer(fbo_id)
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
            self._engine.on("scene_loaded", self._on_scene_loaded)
        except Exception as e:
            import traceback
            print(f"[Zarin Engine] OpenGL init error: {e}\n{traceback.format_exc()}", flush=True)
            Logger.error(f"OpenGL init error: {e}", e)

    def _on_scene_loaded(self, scene):
        pass

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
                self._renderer.render_scene(scene, view, proj, cam_pos, fw, fh, self._screen_fbo,
                                            set(self._selected_entities), self._cam.near, self._cam.far, self._cam.fov)
                render_ms = (time.perf_counter() - t0) * 1000.0
                eng.set_profiler_data("render_ms", render_ms)
                vp_mat = view * proj
                dpr = self.devicePixelRatio()
                self._renderer._line_width = max(2.5, float(dpr) * 2.5)
                if in_frame:
                    prof.start("gizmo_lines")
                t1 = time.perf_counter()
                gizmo_lines = self._gizmo.get_gizmo_lines(self._cam, fw, fh)
                if gizmo_lines:
                    self._renderer.render_gizmo_lines(gizmo_lines, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.0)
                if self._gizmo_visible:
                    axis_lines = get_axis_gizmo_lines(self)
                    if axis_lines:
                        self._renderer.render_gizmo_lines(axis_lines, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.0)
                if in_frame:
                    prof.stop("gizmo_lines")
                if in_frame:
                    prof.start("gizmo_wireframes")
                if self._gizmo_visible:
                    render_collider_wireframes(self, vp_mat)
                    render_particle_emitter_wireframes(self, vp_mat)
                    render_camera_frustums(self, vp_mat)
                    render_audio_source_gizmos(self, vp_mat)
                    render_reverb_zone_gizmos(self, vp_mat)
                    render_script_gizmos(self, vp_mat)
                if in_frame:
                    prof.stop("gizmo_wireframes")
                if in_frame:
                    prof.start("gizmo_icons")
                try:
                    render_component_icons_gl(self)
                except Exception:
                    pass
                if self._debug_lines:
                    self._renderer.render_gizmo_lines(self._debug_lines, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.0)
                    self._debug_lines.clear()
                if in_frame:
                    prof.stop("gizmo_icons")
                if in_frame:
                    prof.start("gizmo_collab")
                try:
                    render_remote_collaborator_gizmos(self, vp_mat, cam_pos, fw, fh)
                except Exception:
                    pass
                if in_frame:
                    prof.stop("gizmo_collab")
                eng.set_profiler_data("gizmo_time", (time.perf_counter() - t1) * 1000.0)
                t2 = time.perf_counter()
                if in_frame:
                    prof.start("overlay_draw")
                self._overlay_widget.resize(self.width(), self.height())
                self._overlay_widget.update()
                if in_frame:
                    prof.stop("overlay_draw")
                eng.set_profiler_data("overlay_time", (time.perf_counter() - t2) * 1000.0)
            if not self._vsync_enabled and self.isVisible():
                self.update()
        except Exception as e:
            Logger.error(f"Render error: {e}", e)

    def update_scene(self):
        eng = self._engine
        prof = eng._profiler
        prof.capture_frame()
        prof.start("frame")
        now = time.perf_counter()
        dt = now - self._last_frame_time
        self._last_frame_time = now
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
                        self._gizmo.entity = None
                        self.entity_selected.emit(None)
        prof.stop("input_handling")
        prof.start("logic_update")
        if eng.play_mode:
            eng.tick()
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
        prof.stop("logic_update")
        prof.start("render_widget")
        if self.isVisible():
            if self._vsync_enabled:
                self.update()
        prof.stop("render_widget")
        prof.start("frame_overhead")
        self._fps_accum += dt
        self._fps_frames += 1
        if self._fps_accum >= 0.5:
            self._fps = self._fps_frames / self._fps_accum
            self._fps_accum = 0.0
            self._fps_frames = 0
        self._update_status_labels()
        prof.stop("frame_overhead")
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
            picked = pick_entity(self, x, y)
            if shift:
                if picked:
                    if picked in self._selected_entities:
                        self._selected_entities.remove(picked)
                    else:
                        self._selected_entities.append(picked)
                    self._gizmo.entity = self._selected_entities[0] if self._selected_entities else None
                    self.entities_selected.emit(self._selected_entities)
                else:
                    self._selected_entities = []
                    self._gizmo.entity = None
                    self.entity_selected.emit(None)
                return
            if ctrl:
                if picked:
                    if picked in self._selected_entities:
                        self._selected_entities.remove(picked)
                    else:
                        self._selected_entities.append(picked)
                    self._gizmo.entity = self._selected_entities[0] if self._selected_entities else None
                    self.entities_selected.emit(self._selected_entities)
                else:
                    self._selected_entities = []
                    self._gizmo.entity = None
                    self.entity_selected.emit(None)
                return
            self._area_selecting = True
            self._area_start = (lx, ly)
            self._area_end = (lx, ly)
            self.update()
            if picked != (self._selected_entities[0] if self._selected_entities else None):
                self._selected_entities = [picked] if picked else []
                self._gizmo.entity = picked
                self.entity_selected.emit(picked)

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
                    pos_delta = pt.position - pre_pos
                    rot_rel = (pre_rot.conjugate() * pt.local_rotation).normalized()
                    scale_rel = Vec3(
                        pt.local_scale.x / max(0.001, pre_scale.x),
                        pt.local_scale.y / max(0.001, pre_scale.y),
                        pt.local_scale.z / max(0.001, pre_scale.z),
                    )
                    for ent in self._selected_entities:
                        if ent is primary:
                            continue
                        et = ent.get_component_by_name("Transform")
                        if et:
                            et.position = et.position + pos_delta
                            et.local_rotation = (et.local_rotation * rot_rel).normalized()
                            et.local_scale = Vec3(
                                max(0.001, et.local_scale.x * scale_rel.x),
                                max(0.001, et.local_scale.y * scale_rel.y),
                                max(0.001, et.local_scale.z * scale_rel.z),
                            )

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
                    self._gizmo.entity = self._selected_entities[0] if self._selected_entities else None
                    self.entities_selected.emit(self._selected_entities)
            self.update()
        self._gizmo.on_mouse_release()
        if self._multi_entity_initial_transforms:
            from core.commands import SetComponentCommand, get_history
            from core.components import Transform as TransformComponent
            for ent in self._selected_entities:
                if ent is self._gizmo._entity:
                    continue
                init = self._multi_entity_initial_transforms.get(ent.id)
                if not init:
                    continue
                et = ent.get_component_by_name("Transform")
                if not et:
                    continue
                if self._gizmo._mode == GizmoMode.TRANSLATE:
                    new_pos = et.position
                    if (new_pos - init["position"]).length() > 1e-8:
                        get_history().execute(SetComponentCommand(ent, TransformComponent, "position", init["position"], new_pos))
                elif self._gizmo._mode == GizmoMode.ROTATE:
                    new_rot = et.local_rotation
                    get_history().execute(SetComponentCommand(ent, TransformComponent, "local_rotation", init["local_rotation"], new_rot))
                elif self._gizmo._mode == GizmoMode.SCALE:
                    new_scale = et.local_scale
                    get_history().execute(SetComponentCommand(ent, TransformComponent, "local_scale", init["local_scale"], new_scale))
            self._multi_entity_initial_transforms = {}
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
        from PyQt6.QtCore import Qt as QtCore
        mapping = {
            QtCore.Key.Key_W: KEY_W, QtCore.Key.Key_A: KEY_A,
            QtCore.Key.Key_S: KEY_S, QtCore.Key.Key_D: KEY_D,
            QtCore.Key.Key_Q: KEY_Q, QtCore.Key.Key_E: KEY_E,
            QtCore.Key.Key_R: KEY_R, QtCore.Key.Key_F: KEY_F,
            QtCore.Key.Key_Shift: KEY_SHIFT,
            QtCore.Key.Key_Control: KEY_CTRL,
            QtCore.Key.Key_Alt: KEY_ALT,
            QtCore.Key.Key_Delete: KEY_DELETE,
            QtCore.Key.Key_Space: KEY_SPACE,
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
            self._gizmo.entity = e
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
        self._gizmo.entity = None
        self.entity_selected.emit(None)

    def _copy_selected_entities(self):
        if not self._selected_entities:
            return
        self._entity_clipboard = [copy.deepcopy(e.serialize()) for e in self._selected_entities]
        for data in self._entity_clipboard:
            data["parent"] = None

    def _paste_entities(self):
        from core.engine import Engine
        registry = Engine.instance()._component_registry
        if not self._entity_clipboard or not self._engine.scene:
            return
        new_entities = []
        for data in self._entity_clipboard:
            d = copy.deepcopy(data)
            d["id"] = str(uuid.uuid4())
            d["parent"] = None
            from core.ecs import Entity
            e = Entity.deserialize(d, registry)
            self._engine.scene.add_entity(e)
            from editor.viewport.collaboration import send_collab_entity_create
            send_collab_entity_create(self, e.serialize())
            new_entities.append(e)
        self._selected_entities = new_entities
        self._gizmo.entity = new_entities[0] if new_entities else None
        self.entities_selected.emit(self._selected_entities)
        self.scene_modified.emit()

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

    def dropEvent(self, event):
        pos = event.position()
        if event.mimeData().hasFormat("application/x-zpep"):
            path = bytes(event.mimeData().data("application/x-zpep")).decode()
            from editor.viewport.projection import screen_to_world
            world_pos = screen_to_world(self, int(pos.x()), int(pos.y()))
            self.entity_dropped.emit(path, world_pos)
        elif event.mimeData().hasText():
            text = event.mimeData().text()
            from editor.viewport.projection import screen_to_world
            world_pos = screen_to_world(self, int(pos.x()), int(pos.y()))
            self.entity_dropped.emit(text, world_pos)
        event.acceptProposedAction()

    def screen_to_ray(self, sx: int, sy: int) -> tuple[Vec3, Vec3]:
        from editor.viewport.projection import screen_to_ray as _screen_to_ray
        return _screen_to_ray(self, sx, sy)

    def screen_to_plane(self, sx: int, sy: int, plane_point: Vec3) -> Vec3:
        from editor.viewport.projection import screen_to_plane as _screen_to_plane
        return _screen_to_plane(self, sx, sy, plane_point)

    def add_debug_line(self, start: Vec3, end: Vec3, color: list[float]):
        self._debug_lines.append((start, end, color))
