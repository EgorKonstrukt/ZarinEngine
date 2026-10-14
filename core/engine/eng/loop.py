# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import gc
import time
from core.foundation.logger import Logger


class EngineLoopMixin:
    @staticmethod
    def _settle_scene_heap():
        try:
            gc.freeze()
        except Exception:
            pass
    @property
    def fps(self) -> float:
        return self._fps
    @property
    def tps(self) -> float:
        return self._tps
    @property
    def frame_count(self) -> int:
        return self._frame_count
    @property
    def time_scale(self) -> float:
        return self._time_scale
    @time_scale.setter
    def time_scale(self, v: float):
        self._time_scale = max(0.0, v)
    @property
    def fixed_dt(self) -> float:
        return self._fixed_dt
    @fixed_dt.setter
    def fixed_dt(self, v: float):
        self._fixed_dt = max(0.001, v)
    @property
    def profiler(self):
        return self._profiler
    @property
    def profiler_data(self) -> dict:
        return self._profiler.data
    def get_profiler_data(self, key: str, default: float = 0.0) -> float:
        return self._profiler.data.get(key, default)
    def reset_profiler(self):
        self._profiler.reset()
    def set_profiler_data(self, key: str, value_ms: float):
        self._profiler.set_value(key, value_ms)
    def capture_profiler_frame(self):
        self._profiler.capture_frame()
    @property
    def profiler_enabled(self) -> bool:
        return self._profiler.enabled
    @profiler_enabled.setter
    def profiler_enabled(self, v: bool):
        self._profiler.enabled = v
    def tick(self):
        if not self._play_mode:
            return
        dt = self.tick_begin()
        MAX_FIXED_STEPS = 5
        _steps = 0
        for _ in range(MAX_FIXED_STEPS):
            if not self.tick_fixed_step():
                break
            _steps += 1
        self._fixed_steps_last = _steps
        self.tick_update(dt)
    def tick_begin(self) -> float:
        sc = self._scene
        if sc is not None:
            try:
                sc._last_flushed = []
                try:
                    sc._last_flushed_set.clear()
                except Exception:
                    pass
                try:
                    sc._flushed_overflow = False
                except Exception:
                    pass
            except Exception:
                pass
            sc.flush_transforms()
        now = time.perf_counter()
        raw_dt = now - self._last_time
        self._last_time = now
        dt = raw_dt * self._time_scale
        self._profiler.start("tick")
        self._fixed_accum += dt
        try:
            _cap = float(self._fixed_dt) * 5.0
            if self._fixed_accum > _cap:
                self._fixed_accum = _cap
        except Exception:
            pass
        return dt
    def tick_fixed_step(self) -> bool:
        fd = self._fixed_dt
        if self._fixed_accum < fd:
            return False
        prof = self._profiler
        prof.start("fixed_update")
        sys_plugins = self._plugin_manager.get_system_plugins()
        for p in sys_plugins:
            prof.start(p.NAME)
            try:
                p.pre_step(fd)
            except Exception as e:
                Logger.error(f"Plugin {p.NAME} pre_step exception: {e}")
            prof.stop(p.NAME)
        sc = self._scene
        if sc is not None:
            try:
                sc.fixed_update(fd)
            except Exception as e:
                Logger.error(f"FixedUpdate exception: {e}", e)
        for p in sys_plugins:
            prof.start(p.NAME)
            try:
                p.step(fd)
            except Exception as e:
                Logger.error(f"Plugin {p.NAME} exception: {e}")
            prof.stop(p.NAME)
        self._fixed_accum -= fd
        if self._fixed_accum < 0:
            self._fixed_accum = 0.0
        prof.stop("fixed_update")
        return True
    def tick_update(self, dt: float):
        prof = self._profiler
        prof.start("update")
        sc = self._scene
        if sc is not None:
            try:
                sc.update(dt)
            except Exception as e:
                Logger.error(f"Update exception: {e}", e)
        prof.stop("update")
        self._frame_count += 1
        ts = self._time_scale if self._time_scale > 0.001 else 0.001
        inv = dt / ts
        try:
            self._tick_dts.append(inv)
        except Exception:
            pass
        self._fps_accum += inv
        self._fps_frames += 1
        self._tps_accum += inv
        self._tps_frames += 1
        if self._fps_accum >= 0.5:
            self._fps = self._fps_frames / self._fps_accum
            self._fps_accum = 0.0
            self._fps_frames = 0
            self._tps = self._tps_frames / self._tps_accum
            self._tps_accum = 0.0
            self._tps_frames = 0
        prof.stop("tick")
        rec = self._time_travel_recorder
        if rec is not None and rec.is_recording:
            rec.capture(sc)
    def shutdown(self):
        try:
            if self._game_worker:
                try:
                    self._game_worker.stop()
                except Exception:
                    pass
                self._game_worker = None
        except Exception:
            pass
        try:
            cm = self._collab_manager
            if cm is not None:
                active = True
                try:
                    active = bool(getattr(cm, "_server", None) is not None or getattr(cm, "_mode", "none") != "none")
                except Exception:
                    active = True
                if active:
                    try:
                        if hasattr(cm, "shutdown"):
                            cm.shutdown()
                        elif hasattr(cm, "stop"):
                            cm.stop()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            from core.terrain.terrain_worker import stop_all as _terrain_stop_all
            _terrain_stop_all()
        except Exception:
            pass
        try:
            from core.navigation import stop_nav_worker as _nav_stop
            _nav_stop()
        except Exception:
            pass
        try:
            from core.audio.sys import AudioSystem
            audio_sys = AudioSystem.instance()
            if audio_sys:
                audio_sys.shutdown()
        except Exception:
            pass
        self._plugin_manager.shutdown_all()
        try:
            from core.ecs.pool import shutdown_all as _pools_shutdown
            _pools_shutdown()
        except Exception:
            pass
        Logger.info("Zarin Engine shutdown.")
