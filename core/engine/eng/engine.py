# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import time
import threading
from collections import deque as _deque
from typing import Optional, Any, TYPE_CHECKING
from core.ecs import Scene, ComponentRegistry
from core.foundation.plugins import PluginManager
from core.foundation.logger import Logger
from core.config.config import get_global_config
from core.config.constants import PATH_FIELDS as _PATH_FIELDS
from core.foundation.profiler import Profiler as _Profiler
from core.engine.eng.scenes import EngineScenesMixin
from core.engine.eng.loop import EngineLoopMixin
from core.engine.eng.events import EngineEventsMixin
if TYPE_CHECKING:
    from core.engine.engine_worker import GameWorker


class Engine(EngineScenesMixin, EngineLoopMixin, EngineEventsMixin):
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
        self._fixed_steps_last: int = 0
        self._last_time: float = 0.0
        self._frame_count: int = 0
        self._fps: float = 0.0
        self._fps_accum: float = 0.0
        self._fps_frames: int = 0
        self._tps: float = 0.0
        self._tps_accum: float = 0.0
        self._tps_frames: int = 0
        self._tick_dts = _deque(maxlen=600)
        self._scene_lock = threading.RLock()
        self._profiler = _Profiler()
        self._time_travel_recorder: Optional[Any] = None
        self._event_listeners: dict[str, list] = {}
        self._component_registry = ComponentRegistry
        self._collab_manager: Optional[Any] = None
        self._game_worker: Optional[GameWorker] = None
        self._plugin_ui_registry: dict[str, list] = {
            "docks": [],
            "toolbar_actions": [],
            "menu_items": [],
            "file_openers": [],
        }
        self._main_window: Optional[Any] = None
        self._project_path: Optional[str] = None
        self._project_settings_path: Optional[str] = None
    @classmethod
    def instance(cls) -> Optional[Engine]:
        return cls._instance
    _debug_no_qt_overlay: bool = False
    @property
    def debug_no_qt_overlay(self) -> bool:
        return self._debug_no_qt_overlay
    @debug_no_qt_overlay.setter
    def debug_no_qt_overlay(self, value: bool):
        self._debug_no_qt_overlay = value
    @property
    def plugin_manager(self) -> PluginManager:
        return self._plugin_manager
    def set_main_window(self, window) -> None:
        self._main_window = window
        try:
            self._plugin_manager.notify_main_window_ready(window)
        except Exception as e:
            Logger.error(f"Plugin on_main_window_ready error: {e}", e)
    def get_main_window(self):
        return self._main_window
    @property
    def scene(self) -> Optional[Scene]:
        return self._scene
    @property
    def play_mode(self) -> bool:
        return self._play_mode
    @property
    def viewport(self):
        return getattr(self, "_viewport", None)
    @viewport.setter
    def viewport(self, v):
        self._viewport = v
        for p in self._plugin_manager.get_all():
            try:
                p.on_viewport_ready(v)
            except Exception as e:
                Logger.error(f"Plugin on_viewport_ready error: {e}", e)
    @property
    def project_root(self) -> str:
        return getattr(self, "_project_path", os.getcwd())
    @project_root.setter
    def project_root(self, path: str):
        self._project_path = path
        try:
            from core.audio.sys import AudioSystem
            audio = AudioSystem.instance()
            if audio:
                audio.apply_project_audio_config()
        except Exception:
            pass
    def _embedded_cache_mode(self) -> str:
        try:
            from core.config.config import get_global_config
            return get_global_config().get("engine.embedded_cache_mode", "project")
        except Exception:
            return "project"
    def _compress_level(self) -> int:
        try:
            scene_level = getattr(self._scene, "compress_level", None)
            if scene_level is not None:
                return self._resolve_compress_level(scene_level)
            return self._resolve_compress_level(
                get_global_config().get("engine.embedded_compression_level", "balanced"))
        except Exception:
            return 6
    @staticmethod
    def _resolve_compress_level(val) -> int:
        if isinstance(val, bool) or not isinstance(val, int):
            return {"fast": 1, "balanced": 6, "max": 9}.get(str(val).lower(), 6)
        return max(0, min(9, val))
    def resolve_scene_paths(self, data: dict):
        root = self.project_root
        entities = data.get("entities", {})
        comps: list[dict] = []
        for edata in entities.values():
            try:
                cl = edata.get("components", [])
            except Exception:
                continue
            for comp in cl:
                comps.append(comp)
        if not comps:
            return
        uniq: set[str] = set()
        for comp in comps:
            for key, val in comp.items():
                if key in _PATH_FIELDS and val and isinstance(val, str):
                    uniq.add(val)
            mats = comp.get("materials")
            if isinstance(mats, list):
                for entry in mats:
                    if isinstance(entry, dict):
                        pv = entry.get("path")
                        if pv and isinstance(pv, str):
                            uniq.add(pv)
            elif isinstance(mats, dict):
                for entry in mats.values():
                    if isinstance(entry, dict):
                        pv = entry.get("path")
                        if pv and isinstance(pv, str):
                            uniq.add(pv)
        if not uniq:
            return
        root_norm = os.path.normpath(root) if root else ""
        resolved: dict[str, str] = {}
        def _resolve_one(val: str) -> str:
            try:
                if os.path.exists(val):
                    return val
                candidate = os.path.normpath(os.path.join(root_norm, val)) if root_norm else os.path.normpath(val)
                if os.path.exists(candidate):
                    return candidate.replace("\\", "/")
                if len(val) > 1 and val[1] == ":":
                    parts = val.replace("\\", "/").split("/")
                    for i in range(len(parts)):
                        sub = "/".join(parts[i:])
                        if sub:
                            c = os.path.normpath(os.path.join(root_norm, sub)) if root_norm else os.path.normpath(sub)
                            if os.path.exists(c):
                                return c.replace("\\", "/")
                return val
            except Exception:
                return val
        uniq_list = list(uniq)
        if len(uniq_list) > 64:
            import concurrent.futures as _cf
            import os as _os
            workers = min(8, max(2, (_os.cpu_count() or 4)))
            chunk = (len(uniq_list) + workers - 1) // workers
            def _chunk_task(part):
                out = []
                for v in part:
                    out.append((v, _resolve_one(v)))
                return out
            with _cf.ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(_chunk_task, uniq_list[i:i + chunk]) for i in range(0, len(uniq_list), chunk)]
                for fu in _cf.as_completed(futs):
                    try:
                        for v, r in fu.result():
                            resolved[v] = r
                    except Exception:
                        pass
        else:
            for val in uniq_list:
                resolved[val] = _resolve_one(val)
        for comp in comps:
            for key, val in list(comp.items()):
                if key in _PATH_FIELDS and val and isinstance(val, str):
                    nv = resolved.get(val)
                    if nv is not None and nv != val:
                        comp[key] = nv
            mats = comp.get("materials")
            if isinstance(mats, list):
                dirty = False
                rebuilt = []
                for entry in mats:
                    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
                        nv = resolved.get(entry["path"])
                        if nv is not None and nv != entry["path"]:
                            entry = dict(entry)
                            entry["path"] = nv
                            dirty = True
                    rebuilt.append(entry)
                if dirty:
                    comp["materials"] = rebuilt
            elif isinstance(mats, dict):
                dirty = False
                rebuilt_d = {}
                for k, entry in mats.items():
                    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
                        nv = resolved.get(entry["path"])
                        if nv is not None and nv != entry["path"]:
                            entry = dict(entry)
                            entry["path"] = nv
                            dirty = True
                    rebuilt_d[k] = entry
                if dirty:
                    comp["materials"] = rebuilt_d
    def relativize_scene_paths(self, data: dict):
        root = self.project_root
        entities = data.get("entities", {})
        comps: list[dict] = []
        for edata in entities.values():
            try:
                cl = edata.get("components", [])
            except Exception:
                continue
            for comp in cl:
                comps.append(comp)
        if not comps:
            return
        uniq: set[str] = set()
        for comp in comps:
            for key, val in comp.items():
                if key in _PATH_FIELDS and val and isinstance(val, str):
                    uniq.add(val)
            mats = comp.get("materials")
            if isinstance(mats, list):
                for entry in mats:
                    if isinstance(entry, dict):
                        pv = entry.get("path")
                        if pv and isinstance(pv, str):
                            uniq.add(pv)
            elif isinstance(mats, dict):
                for entry in mats.values():
                    if isinstance(entry, dict):
                        pv = entry.get("path")
                        if pv and isinstance(pv, str):
                            uniq.add(pv)
        if not uniq:
            return
        root_norm = os.path.normpath(root) if root else ""
        mapped: dict[str, str] = {}
        for val in uniq:
            if not val:
                mapped[val] = ""
            elif not os.path.isabs(val):
                mapped[val] = val.replace("\\", "/")
            else:
                try:
                    mapped[val] = os.path.relpath(val, root_norm if root_norm else ".").replace("\\", "/")
                except ValueError:
                    mapped[val] = val
        for comp in comps:
            for key, val in list(comp.items()):
                if key in _PATH_FIELDS and val and isinstance(val, str):
                    nv = mapped.get(val)
                    if nv is not None and nv != val:
                        comp[key] = nv
            mats = comp.get("materials")
            if isinstance(mats, list):
                dirty = False
                rebuilt = []
                for entry in mats:
                    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
                        nv = mapped.get(entry["path"])
                        if nv is not None and nv != entry["path"]:
                            entry = dict(entry)
                            entry["path"] = nv
                            dirty = True
                    rebuilt.append(entry)
                if dirty:
                    comp["materials"] = rebuilt
            elif isinstance(mats, dict):
                dirty = False
                rebuilt_d = {}
                for k, entry in mats.items():
                    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
                        nv = mapped.get(entry["path"])
                        if nv is not None and nv != entry["path"]:
                            entry = dict(entry)
                            entry["path"] = nv
                            dirty = True
                    rebuilt_d[k] = entry
                if dirty:
                    comp["materials"] = rebuilt_d
    def initialize(self):
        import core.components
        cfg = get_global_config()
        self._time_scale = cfg.get("engine.time_scale", 1.0)
        self._fixed_dt = max(0.001, cfg.get("engine.fixed_update_dt", 0.02))
        try:
            self._profiler.enabled = bool(cfg.get("profiler.enabled", False))
        except Exception:
            pass
        try:
            from core.audio.sys import AudioSystem
            audio_sys = AudioSystem()
            audio_sys.initialize()
            if self._project_path:
                audio_sys.apply_project_audio_config()
        except Exception as e:
            Logger.error(f"Audio system init failed: {e}")
        from core.config.build_settings import BuildSettings
        bs = BuildSettings()
        if self._project_path:
            bs.load(os.path.join(self._project_path, "BuildSettings.json"))
        Logger.info("Zarin Engine initialized.")
    def new_scene(self, name: str = "NewScene") -> Scene:
        if self._scene:
            self._plugin_manager.notify_scene_unloaded(self._scene)
        from core.components.rendering.postfx.graphics_effect import GraphicsEffect
        GraphicsEffect.cleanup_registry()
        self._scene = Scene(name)
        self._add_default_scene_objects(self._scene)
        self._plugin_manager.notify_scene_loaded(self._scene)
        self._emit_event("scene_loaded", self._scene)
        Logger.info(f"New scene created: {name}")
        Engine._settle_scene_heap()
        return self._scene
    def _ensure_shadow_system(self, scene):
        try:
            from core.components.transform.tr import Transform
            from core.components.rendering.environment.directional_shadow import DirectionalShadow
            from core.components.rendering.environment.point_shadow import PointShadow
            from core.components.rendering.environment.spot_shadow import SpotShadow
            from core.components.rendering.environment.area_shadow import AreaShadow
            try:
                for ent in scene.get_entities_with_component(DirectionalShadow):
                    try:
                        if ent._scene is scene:
                            return
                    except Exception:
                        return
            except Exception:
                pass
            e = scene.create_entity("Shadow System")
            e.add_component(Transform())
            e.add_component(DirectionalShadow())
            e.add_component(PointShadow())
            e.add_component(SpotShadow())
            e.add_component(AreaShadow())
            e.system = True
            e.locked = True
        except Exception:
            pass
    def _add_default_scene_objects(self, scene):
        self._ensure_shadow_system(scene)
    def start_play(self):
        if self._play_mode:
            return
        self._play_mode = True
        self._fixed_accum = 0.0
        self._last_time = time.perf_counter()
        from core.input.inpsys import Input
        Input.LoadProjectBindings(self.project_root)
        if self._scene:
            self._scene.start()
        self._plugin_manager.notify_play_start()
        self._emit_event("play_start", None)
        Logger.info("Play mode started.")
        from core.engine.engine_worker import GameWorker
        cfg = get_global_config()
        update_rate = cfg.get("rendering.tick_rate", 120.0)
        fixed_rate = cfg.get("rendering.fixed_tick_rate", 60.0)
        self._game_worker = GameWorker(self, update_rate, fixed_rate)
        self._game_worker.start()
    def stop_play(self):
        if not self._play_mode:
            return
        if self._game_worker:
            self._game_worker.stop()
            self._game_worker = None
        from core.audio.sys import AudioSourceManager
        mgr = AudioSourceManager.instance()
        if mgr:
            mgr.stop_all()
        self._play_mode = False
        self._plugin_manager.notify_play_stop()
        self._emit_event("play_stop", None)
        Logger.info("Play mode stopped.")
