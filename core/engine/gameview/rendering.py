# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
import time
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QFont
from core.input.inpsys import Input
from core.foundation.logger import Logger
from core.engine.frame_pacer import needs_software_pacing, normalize_target_fps, timer_interval_ms
from core.renderer.stats import _SPIKE_LOG, build_stats_rows, collect_render_stats, compute_frame_metrics, draw_stats_panel, log_spike


class GameViewportRenderMixin:

    def _on_play_stop(self, _=None):
        if self._mouse_captured or self._cursor_blank:
            Input.set_cursor_visible(True)
            Input.set_cursor_locked(False)
            self._release_mouse()

    def _bind_screen_fbo(self):
        fbo_id = self.defaultFramebufferObject()
        self._screen_fbo = self._ctx.detect_framebuffer(fbo_id)
        self._screen_fbo.use()

    def showEvent(self, event):
        super().showEvent(event)
        self.update()

    def _apply_config(self):
        if not self._vsync_enabled:
            self._timer.setTimerType(Qt.TimerType.PreciseTimer)
            tgt = int(self._target_fps) if self._target_fps else 0
            if tgt <= 0 or tgt == 60:
                self._timer.setInterval(0)
                self._pacer.set_target(0)
            else:
                tgt = normalize_target_fps(tgt)
                self._timer.setInterval(timer_interval_ms(tgt))
                self._pacer.set_target(tgt if needs_software_pacing(tgt) else 0)
        else:
            self._timer.setTimerType(Qt.TimerType.CoarseTimer)
            tgt = int(self._target_fps) if self._target_fps else 60
            tgt = normalize_target_fps(tgt) or 60
            self._timer.setInterval(timer_interval_ms(tgt))
            self._pacer.set_target(0)
        if self.isVisible() or not self._vsync_enabled:
            self._timer.start()

    def initializeGL(self):
        try:
            self._ctx = moderngl.create_context(standalone=False)
            self._bind_screen_fbo()
            if not self._vsync_enabled:
                try:
                    import ctypes
                    opengl32 = ctypes.windll.opengl32
                    addr = opengl32.wglGetProcAddress(b"wglSwapIntervalEXT")
                    if addr:
                        func = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(addr)
                        func(0)
                except Exception:
                    pass
            from core.renderer import Renderer
            self._renderer = Renderer(self._ctx)
            self._renderer.initialize()
            try:
                from core.config.config import get_global_config
                self._renderer.load_config(get_global_config())
            except Exception:
                pass
        except Exception as e:
            Logger.error(f"GameViewport GL init error: {e}", e)

    def resizeGL(self, w: int, h: int):
        dpr = self.devicePixelRatio()
        pw, ph = int(w * dpr), int(h * dpr)
        self._physical_w, self._physical_h = pw, ph
        if self._ctx:
            self._ctx.viewport = (0, 0, pw, ph)
            self._bind_screen_fbo()

    def paintGL(self):
        if not self._ctx or not self._renderer:
            return
        now = time.perf_counter()
        if self._last_paint_time > 0:
            self._paint_dt = now - self._last_paint_time
            if self._paint_dt > 0.05:
                self._paint_dt = 0.05
            elif self._paint_dt < 0.0:
                self._paint_dt = 0.0
            self._fps_accum += self._paint_dt
            self._fps_frames += 1
            if self._fps_accum >= 0.5:
                self._fps = self._fps_frames / self._fps_accum
                self._fps_accum = 0.0
                self._fps_frames = 0
        self._last_paint_time = now
        prof = getattr(self._engine, "_profiler", None)
        if prof is None:
            self._paint_uncaptured(now)
            self._last_paint_full_ms = (time.perf_counter() - now) * 1000.0
            return
        with prof.scope("frame"):
            with prof.scope("game_render"):
                self._paint_uncaptured(now)
        self._last_paint_full_ms = (time.perf_counter() - now) * 1000.0

    def _paint_uncaptured(self, now: float):
        try:
            self._bind_screen_fbo()
            scene = self._engine.scene
            if not scene:
                self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                return
            from core.components import Camera
            cam_entity = None
            for e in scene.get_entities_with_component(Camera):
                if e.active:
                    cam_entity = e
                    break
            if not cam_entity:
                self._ctx.clear(0.1, 0.1, 0.1, 1.0)
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
            _t0 = time.perf_counter()
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
            self._last_render_ms = (time.perf_counter() - _t0) * 1000.0
            if self._stats_enabled:
                self._draw_stats_overlay()
        except Exception as e:
            import traceback as _tb
            _tb.print_exc()
            Logger.error(f"GameViewport render error: {e}", e)

    def _tick(self):
        if self._engine.play_mode and self.isVisible():
            if not self._pacer.should_run():
                return
            prof = self._engine._profiler
            if prof:
                prof.capture_frame()
            with prof.scope("game_tick"):
                with prof.scope("game_input"):
                    self._input_manager.new_frame()
                if self._engine._game_worker is None:
                    with self._engine._scene_lock:
                        self._engine.tick()
            self._tick_editor_cameras()
            self._sync_cursor()
            self.update()

    def _tick_editor_cameras(self):
        try:
            from core.components.rendering.cameras.editor_camera import EditorCamera
            scene = self._engine.scene
            if not scene:
                return
            dt = self._paint_dt if self._paint_dt > 0 else 0.016
            for e in scene.get_entities_with_component(EditorCamera):
                if e.active:
                    comp = e.get_component(EditorCamera)
                    if comp.enabled:
                        comp.on_update(dt)
        except Exception as e:
            Logger.warning(f"_tick_editor_cameras error: {e}")

    def _get_physical_dims(self):
        if self._physical_w > 0 and self._physical_h > 0:
            return self._physical_w, self._physical_h
        dpr = self.devicePixelRatio()
        return int(self.width() * dpr), int(self.height() * dpr)

    def _draw_stats_overlay(self):
        painter = QPainter(self)
        try:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            font = QFont("Consolas", 9)
            font.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
            painter.setFont(font)
            paint_dt = self._paint_dt if self._paint_dt > 0 else 0.016
            if paint_dt > 0:
                self._frame_times_ms.append(paint_dt * 1000.0)
                if len(self._frame_times_ms) > 300:
                    self._frame_times_ms.pop(0)
            if self._frame_times_ms and self._frame_times_ms[-1] > 33.0:
                prof = getattr(self._engine, "_profiler", None)
                if prof is not None and getattr(prof, "enabled", False):
                    log_spike(self._frame_times_ms[-1], prof)
            m = compute_frame_metrics(self._frame_times_ms)
            live_fps = self._fps if self._fps > 0 else 0.0
            if live_fps > 0:
                m["fps"] = live_fps
                m["avg_fps"] = live_fps
            st = collect_render_stats(self._engine, self._renderer)
            fw, fh = self._get_physical_dims()
            timings = {
                "cpu_ms": paint_dt * 1000.0,
                "render_ms": self._last_render_ms or 0.0,
                "gizmo_ms": 0.0,
                "overlay_ms": 0.0,
                "paint_ms": self._last_paint_full_ms or 0.0,
                "res": f"{fw}x{fh}",
                "dpr": float(self.devicePixelRatio() or 1.0),
            }
            rows = build_stats_rows(m, st, timings)
            try:
                tick_ms = [float(d) * 1000.0 for d in (st.get("tick_dts") or [])]
            except Exception:
                tick_ms = None
            draw_stats_panel(painter, rows, self._frame_times_ms, _SPIKE_LOG, tick_ms)
            painter.restore()
        except Exception as e:
            Logger.error(f"GameViewport stats overlay error: {e}", e)
        finally:
            painter.end()
