from __future__ import annotations
import time
import json
import os
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any, TYPE_CHECKING
from core.ecs import Scene, ComponentRegistry
from core.plugin_manager import PluginManager
from core.logger import Logger
from core.config import get_global_config
from core.constants import PATH_FIELDS as _PATH_FIELDS

if TYPE_CHECKING:
    from core.engine_worker import GameWorker

_ENGINE_POOL = ThreadPoolExecutor(max_workers=min(8, max(2, (os.cpu_count() or 4))), thread_name_prefix="engine")

_perf_counter = time.perf_counter

class ProfileSample:
    __slots__ = ('name', 'depth', 'start_ms', 'duration_ms', 'color')
    def __init__(self, name: str, depth: int, start_ms: float, duration_ms: float, color: str = "#aaaaaa"):
        self.name = name
        self.depth = depth
        self.start_ms = start_ms
        self.duration_ms = duration_ms
        self.color = color

class FrameProfile:
    __slots__ = ('samples', 'frame_time_ms', 'frame_number', 'flat_data')
    def __init__(self):
        self.samples: list[ProfileSample] = []
        self.frame_time_ms: float = 0.0
        self.frame_number: int = 0
        self.flat_data: dict[str, float] = {}

_PROFILER_COLORS = {
    "frame": "#aaaaaa", "tick": "#ff5252", "render_scene": "#ff5252",
    "fixed_update": "#448aff", "update": "#448aff",
    "scene_update": "#69f0ae", "scene_fixed_update": "#69f0ae",
    "animation_ms": "#ffd740", "audio_ms": "#e040fb",
    "ai_ms": "#40c4ff", "particle_ms": "#ff6e40",
    "ui_ms": "#b2ff59", "load_mesh": "#ff8a65",
    "load_obj": "#ff8a65", "scene_start": "#69f0ae",
    "scene_serialize": "#69f0ae", "scene_deserialize": "#69f0ae",
    "render_ms": "#ff5252", "physics_ms": "#448aff",
    "PhysicsPlugin": "#448aff",
    "physics_scan_bodies": "#64b5f6", "physics_drain_results": "#42a5f5",
    "physics_snapshot": "#1e88e5", "physics_worker_send": "#1565c0",
    "physics_scene_step": "#0d47a1",
    "phys_register": "#81c784", "phys_sync_to_solver": "#66bb6a",
    "phys_step_sim": "#4caf50", "phys_constrain_2d": "#43a047",
    "phys_sync_to_ecs": "#388e3c", "phys_collision_events": "#2e7d32",
    "input_handling": "#7e57c2", "logic_update": "#42a5f5",
    "render_widget": "#66bb6a", "frame_overhead": "#78909c",
    "editor_particles": "#ab47bc", "collab_camera": "#26c6da",
    "cam_update": "#29b6f6", "gl_setup": "#ff8a65",
    "gizmo_lines": "#ffd740", "gizmo_wireframes": "#ffaa00",
    "gizmo_icons": "#ffab40", "gizmo_collab": "#ff6e40",
    "overlay_draw": "#40c4ff",
}

class _Profiler:
    __slots__ = ('_frames', '_current_frame', '_stack', '_frame_start',
                 '_max_frames', '_flat_data', '_enabled', '_frame_number',
                 '_capture_frames', '_lock')
    def __init__(self, max_frames: int = 300):
        self._lock = threading.Lock()
        self._frames: deque[FrameProfile] = deque(maxlen=max_frames)
        self._current_frame: FrameProfile | None = None
        self._stack: list[tuple[str, float]] = []
        self._frame_start: float = 0.0
        self._max_frames = max_frames
        self._flat_data: dict[str, float] = {}
        self._enabled: bool = False
        self._frame_number: int = 0
        self._capture_frames: bool = False
    def start(self, key: str):
        if not self._enabled: return
        with self._lock:
            self._stack.append((key, _perf_counter()))
    def stop(self, key: str):
        if not self._enabled: return
        with self._lock:
            stack = self._stack
            if not stack: return
            if stack[-1][0] == key:
                name, t0 = stack.pop()
            else:
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == key:
                        name, t0 = stack.pop(i)
                        break
                else:
                    return
            now = _perf_counter()
            duration_ms = (now - t0) * 1000.0
            self._flat_data[name] = self._flat_data.get(name, 0.0) + duration_ms
            if self._capture_frames:
                cf = self._current_frame
                if cf is not None and self._frame_start > 0:
                    start_ms = (t0 - self._frame_start) * 1000.0
                    depth = len(stack)
                    c = _PROFILER_COLORS.get(name, "#aaaaaa")
                    cf.samples.append(ProfileSample(name, depth, start_ms, duration_ms, c))
                    cf.flat_data[name] = cf.flat_data.get(name, 0.0) + duration_ms
    def set_value(self, key: str, value_ms: float):
        if not self._enabled: return
        with self._lock:
            self._flat_data[key] = value_ms
            if self._capture_frames:
                cf = self._current_frame
                if cf is not None:
                    cf.flat_data[key] = value_ms
    def capture_frame(self):
        if not self._enabled: return
        with self._lock:
            now = _perf_counter()
            cf = self._current_frame
            frame_start = self._frame_start
            if self._stack:
                for name, t0 in self._stack:
                    duration_ms = (now - t0) * 1000.0
                    self._flat_data[name] = self._flat_data.get(name, 0.0) + duration_ms
                    if self._capture_frames and cf is not None and frame_start > 0:
                        start_ms = (t0 - frame_start) * 1000.0
                        c = _PROFILER_COLORS.get(name, "#aaaaaa")
                        depth = len(self._stack)
                        cf.samples.append(ProfileSample(name, depth, start_ms, duration_ms, c))
                        cf.flat_data[name] = cf.flat_data.get(name, 0.0) + duration_ms
                self._stack.clear()
            if cf is not None:
                cf.frame_time_ms = (now - frame_start) * 1000.0
                cf.frame_number = self._frame_number
                self._frames.append(cf)
                self._frame_number += 1
            self._current_frame = FrameProfile() if self._capture_frames else None
            self._frame_start = now
    def reset(self):
        if not self._enabled: return
        with self._lock:
            self._frames.clear()
            self._current_frame = None
            self._stack.clear()
            self._flat_data.clear()
            self._frame_start = 0.0
            self._frame_number = 0
    @property
    def data(self) -> dict[str, float]:
        return dict(self._flat_data)
    @property
    def frames(self) -> list[FrameProfile]:
        return list(self._frames)
    @property
    def enabled(self) -> bool:
        return self._enabled
    @enabled.setter
    def enabled(self, v: bool):
        self._enabled = v
        if v:
            self._capture_frames = True
    @property
    def capture_frames(self) -> bool:
        return self._capture_frames
    @capture_frames.setter
    def capture_frames(self, v: bool):
        self._capture_frames = v

class Engine:
    _instance: Optional[Engine] = None
    def __init__(self):
        Engine._instance = self
        self._plugin_manager: PluginManager = PluginManager()
        self._plugin_manager.set_engine(self)
        self._scene: Optional[Scene] = None
        self._running: bool = False
        self._play_mode: bool = False
        self._time_scale: float = 1.0
        self._fixed_dt: float = 0.02
        self._fixed_accum: float = 0.0
        self._last_time: float = 0.0
        self._frame_count: int = 0
        self._fps: float = 0.0
        self._fps_accum: float = 0.0
        self._fps_frames: int = 0
        self._tps: float = 0.0
        self._tps_accum: float = 0.0
        self._tps_frames: int = 0
        self._scene_lock = threading.RLock()
        self._profiler = _Profiler()
        self._event_listeners: dict[str, list] = {}
        self._component_registry = ComponentRegistry
        self._collab_manager: Optional[Any] = None
        self._game_worker: Optional[GameWorker] = None
        self._plugin_ui_registry: dict[str, list] = {
            "docks": [],
            "toolbar_actions": [],
            "menu_items": [],
        }
        self._project_path: Optional[str] = None
        self._project_settings_path: Optional[str] = None
    @classmethod
    def instance(cls) -> Optional[Engine]: return cls._instance
    @property
    def plugin_manager(self) -> PluginManager: return self._plugin_manager
    @property
    def scene(self) -> Optional[Scene]: return self._scene
    @property
    def play_mode(self) -> bool: return self._play_mode
    @property
    def fps(self) -> float: return self._fps
    @property
    def tps(self) -> float: return self._tps
    @property
    def frame_count(self) -> int: return self._frame_count
    @property
    def time_scale(self) -> float: return self._time_scale
    @time_scale.setter
    def time_scale(self, v: float): self._time_scale = max(0.0, v)
    @property
    def fixed_dt(self) -> float: return self._fixed_dt
    @fixed_dt.setter
    def fixed_dt(self, v: float): self._fixed_dt = max(0.001, v)
    @property
    def viewport(self):
        return getattr(self, '_viewport', None)
    @viewport.setter
    def viewport(self, v):
        self._viewport = v
        for p in self._plugin_manager.get_all():
            try: p.on_viewport_ready(v)
            except Exception as e: Logger.error(f"Plugin on_viewport_ready error: {e}", e)
    @property
    def profiler(self):
        return self._profiler
    @property
    def profiler_data(self) -> dict: return self._profiler.data
    def get_profiler_data(self, key: str, default: float = 0.0) -> float:
        return self._profiler.data.get(key, default)
    def reset_profiler(self):
        self._profiler.reset()
    @property
    def project_root(self) -> str:
        return getattr(self, '_project_path', os.getcwd())
    def resolve_scene_paths(self, data: dict):
        root = self.project_root
        entities = data.get("entities", {})
        for eid, edata in entities.items():
            for comp in edata.get("components", []):
                for key, val in comp.items():
                    if key in _PATH_FIELDS and val and isinstance(val, str):
                        comp[key] = self._resolve_path(val, root)
    def relativize_scene_paths(self, data: dict):
        """Convert absolute paths to project-relative in scene JSON data."""
        root = self.project_root
        entities = data.get("entities", {})
        for eid, edata in entities.items():
            for comp in edata.get("components", []):
                for key, val in comp.items():
                    if key in _PATH_FIELDS and val and isinstance(val, str):
                        comp[key] = self._relativize_path(val, root)
    @staticmethod
    def _resolve_path(val: str, root: str) -> str:
        if not val or os.path.exists(val):
            return val
        # Try resolving relative to project root
        candidate = os.path.normpath(os.path.join(root, val))
        if os.path.exists(candidate):
            return candidate.replace("\\", "/")
        # Windows absolute path (C:\...) on Linux — extract subpath after project name
        if len(val) > 1 and val[1] == ":":
            parts = val.replace("\\", "/").split("/")
            # Try each suffix from longest to shortest
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(c):
                        return c.replace("\\", "/")
        return val
    @staticmethod
    def _relativize_path(val: str, root: str) -> str:
        if not val:
            return ""
        try:
            rel = os.path.relpath(val, root)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:
            pass
        return val
    def initialize(self):
        import core.components

        cfg = get_global_config()
        self._time_scale = cfg.get("engine.time_scale", 1.0)
        self._fixed_dt = max(0.001, cfg.get("engine.fixed_update_dt", 0.02))

        try:
            from core.audio_system import AudioSystem
            audio_sys = AudioSystem()
            audio_sys.initialize()
        except Exception as e:
            Logger.error(f"Audio system init failed: {e}")

        # Initialize BuildSettings
        from core.build_settings import BuildSettings
        bs = BuildSettings()
        if self._project_path:
            bs.load(os.path.join(self._project_path, "BuildSettings.json"))

        Logger.info("Zarin Engine initialized.")
    def load_scene(self, path: str) -> Optional[Scene]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["_source"] = path
            self.resolve_scene_paths(data)
            if self._scene:
                self._plugin_manager.notify_scene_unloaded(self._scene)
            from core.components.rendering.graphics_effect import GraphicsEffect
            GraphicsEffect.cleanup_registry()
            self._scene = Scene.deserialize(data, self._component_registry)
            self._scene.path = path
            self._scene.mark_clean()
            self._plugin_manager.notify_scene_loaded(self._scene)
            Logger.info(f"Scene loaded: {path}")
            self._emit_event("scene_loaded", self._scene)
            return self._scene
        except Exception as e:
            Logger.error(f"Failed to load scene '{path}': {e}", e)
            return None
    def load_scene_from_data(self, data: dict) -> Optional[Scene]:
        try:
            if self._scene:
                self._plugin_manager.notify_scene_unloaded(self._scene)
            from core.components.rendering.graphics_effect import GraphicsEffect
            GraphicsEffect.cleanup_registry()
            self._scene = Scene.deserialize(data, self._component_registry)
            self._scene.mark_clean()
            self._plugin_manager.notify_scene_loaded(self._scene)
            Logger.info(f"Scene synced: {self._scene.name}")
            self._emit_event("scene_loaded", self._scene)
            return self._scene
        except Exception as e:
            Logger.error(f"Failed to load synced scene: {e}", e)
            return None
    def save_scene(self, path: Optional[str] = None):
        if not self._scene: return
        save_path = path or self._scene.path
        if not save_path:
            Logger.warning("No path for scene save.")
            return
        try:
            data = self._scene.serialize()
            self.relativize_scene_paths(data)
            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._scene.path = save_path
            self._scene.mark_clean()
            Logger.info(f"Scene saved: {save_path}")
            self._emit_event("scene_saved", self._scene)
        except Exception as e:
            Logger.error(f"Failed to save scene: {e}", e)
    def new_scene(self, name: str = "NewScene") -> Scene:
        if self._scene:
            self._plugin_manager.notify_scene_unloaded(self._scene)
        from core.components.rendering.graphics_effect import GraphicsEffect
        GraphicsEffect.cleanup_registry()
        self._scene = Scene(name)
        self._add_default_scene_objects(self._scene)
        self._plugin_manager.notify_scene_loaded(self._scene)
        self._emit_event("scene_loaded", self._scene)
        Logger.info(f"New scene created: {name}")
        return self._scene
    def _add_default_scene_objects(self, scene):
        pass
    def start_play(self):
        if self._play_mode: return
        self._play_mode = True
        self._fixed_accum = 0.0
        self._last_time = _perf_counter()
        if self._scene: self._scene.start()
        self._plugin_manager.notify_play_start()
        self._emit_event("play_start", None)
        Logger.info("Play mode started.")
        from core.engine_worker import GameWorker
        cfg = get_global_config()
        update_rate = cfg.get("rendering.tick_rate", 120.0)
        fixed_rate = cfg.get("rendering.fixed_tick_rate", 60.0)
        self._game_worker = GameWorker(self, update_rate, fixed_rate)
        self._game_worker.start()
    def stop_play(self):
        if not self._play_mode: return
        if self._game_worker:
            self._game_worker.stop()
            self._game_worker = None
        from core.audio_system import AudioSourceManager
        mgr = AudioSourceManager.instance()
        if mgr: mgr.stop_all()
        self._play_mode = False
        self._plugin_manager.notify_play_stop()
        self._emit_event("play_stop", None)
        Logger.info("Play mode stopped.")
    def tick(self):
        if not self._play_mode: return
        dt = self.tick_begin()
        MAX_FIXED_STEPS = 5
        for _ in range(MAX_FIXED_STEPS):
            if not self.tick_fixed_step():
                break
        self.tick_update(dt)

    def tick_begin(self) -> float:
        """Stage 1: flush transforms, calc dt. Returns frame dt."""
        if self._scene:
            self._scene.flush_transforms()
        now = _perf_counter()
        raw_dt = now - self._last_time
        self._last_time = now
        dt = raw_dt * self._time_scale
        self._profiler.start("tick")
        self._fixed_accum += dt
        return dt

    def tick_fixed_step(self) -> bool:
        """Stage 2: one fixed step. Returns True if step was consumed."""
        if self._fixed_accum < self._fixed_dt:
            return False
        self._profiler.start("fixed_update")
        sys_plugins = self._plugin_manager.get_system_plugins()
        for p in sys_plugins:
            self._profiler.start(p.NAME)
            try:
                p.pre_step(self._fixed_dt)
            except Exception as e:
                Logger.error(f"Plugin {p.NAME} pre_step exception: {e}")
            self._profiler.stop(p.NAME)
        if self._scene:
            try:
                self._scene.fixed_update(self._fixed_dt)
            except Exception as e:
                Logger.error(f"FixedUpdate exception: {e}", e)
        for p in sys_plugins:
            self._profiler.start(p.NAME)
            try:
                p.step(self._fixed_dt)
            except Exception as e:
                Logger.error(f"Plugin {p.NAME} exception: {e}")
            self._profiler.stop(p.NAME)
        self._fixed_accum -= self._fixed_dt
        if self._fixed_accum < 0:
            self._fixed_accum = 0.0
        self._profiler.stop("fixed_update")
        return True

    def tick_update(self, dt: float):
        """Stage 3: script update + frame bookkeeping."""
        self._profiler.start("update")
        if self._scene:
            try:
                self._scene.update(dt)
            except Exception as e:
                Logger.error(f"Update exception: {e}", e)
        self._profiler.stop("update")
        self._frame_count += 1
        self._fps_accum += dt / max(self._time_scale, 0.001)
        self._fps_frames += 1
        self._tps_accum += dt / max(self._time_scale, 0.001)
        self._tps_frames += 1
        if self._fps_accum >= 0.5:
            self._fps = self._fps_frames / self._fps_accum
            self._fps_accum = 0.0
            self._fps_frames = 0
            self._tps = self._tps_frames / self._tps_accum
            self._tps_accum = 0.0
            self._tps_frames = 0
        self._profiler.stop("tick")
    def set_profiler_data(self, key: str, value_ms: float):
        self._profiler.set_value(key, value_ms)
    def capture_profiler_frame(self):
        self._profiler.capture_frame()
    @property
    def profiler_enabled(self) -> bool: return self._profiler.enabled
    @profiler_enabled.setter
    def profiler_enabled(self, v: bool): self._profiler.enabled = v
    def on(self, event: str, callback):
        self._event_listeners.setdefault(event, []).append(callback)
    def off(self, event: str, callback):
        if event in self._event_listeners:
            try: self._event_listeners[event].remove(callback)
            except ValueError: pass
    def _emit_event(self, event: str, data: Any):
        cbs = self._event_listeners.get(event, [])
        if len(cbs) >= 10:
            futures = [_ENGINE_POOL.submit(cb, data) for cb in cbs]
            for f in as_completed(futures):
                try: f.result()
                except Exception as e: Logger.error(f"Event callback error '{event}': {e}")
        else:
            for cb in cbs:
                try: cb(data)
                except Exception as e: Logger.error(f"Event callback error '{event}': {e}", e)
    @property
    def collab_manager(self):
        return self._collab_manager
    @collab_manager.setter
    def collab_manager(self, v):
        self._collab_manager = v
    @property
    def plugin_ui_registry(self) -> dict:
        return self._plugin_ui_registry

    def shutdown(self):
        try:
            from core.audio_system import AudioSystem
            audio_sys = AudioSystem.instance()
            if audio_sys: audio_sys.shutdown()
        except Exception:
            pass
        self._plugin_manager.shutdown_all()
        Logger.info("Zarin Engine shutdown.")