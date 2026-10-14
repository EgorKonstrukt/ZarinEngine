# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from typing import Optional, Dict, Tuple, Any
from core.ecs.pool import audio as _get_audio_pool
from core.foundation.progress import task_complete, task_start
from core.audio.sys.clip import AudioClip
try:
    import openal as al
    from openal import alc
    _openal_available = True
except Exception:
    _openal_available = False
    al = None
    alc = None
_DISTANCE_MODEL_MAP = {"none": al.AL_NONE if al else 0, "inverse_distance": al.AL_INVERSE_DISTANCE if al else 0xD001, "inverse_distance_clamped": al.AL_INVERSE_DISTANCE_CLAMPED if al else 0xD002, "linear_distance": al.AL_LINEAR_DISTANCE if al else 0xD003, "linear_distance_clamped": al.AL_LINEAR_DISTANCE_CLAMPED if al else 0xD004, "exponent_distance": al.AL_EXPONENT_DISTANCE if al else 0xD005, "exponent_distance_clamped": al.AL_EXPONENT_DISTANCE_CLAMPED if al else 0xD006}
_AUDIO_CATEGORIES = ("master", "sfx", "music", "voice", "ambient")
_AL_AUX_SEND_FILTER = None
def _get_aux_send_filter() -> int:
    global _AL_AUX_SEND_FILTER
    if _AL_AUX_SEND_FILTER is None:
        try:
            from core.audio.efx import get_aux_send_enum
            _AL_AUX_SEND_FILTER = int(get_aux_send_enum())
        except Exception:
            _AL_AUX_SEND_FILTER = al.alGetEnumValue(b"AL_AUXILIARY_SEND_FILTER") if al else 0x20006
    return int(_AL_AUX_SEND_FILTER)
def _read_audio_value(key: str, default):
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng is not None and getattr(eng, "_project_path", None):
            try:
                from core.config.config import get_project_config
                pcfg = get_project_config(eng._project_path)
                value = pcfg.get(key, None)
                if value is not None:
                    return value
            except Exception:
                pass
    except Exception:
        pass
    try:
        from core.config.config import get_global_config
        cfg = get_global_config()
        return cfg.get(key, default)
    except Exception:
        return default
class AudioSystem:
    _instance: Optional[AudioSystem] = None
    def __init__(self):
        AudioSystem._instance = self
        self._clips: Dict[str, AudioClip] = {}
        self._initialized: bool = False
        self._listener_pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._device_name: str = ""
    @classmethod
    def instance(cls) -> Optional[AudioSystem]: return cls._instance
    def initialize(self):
        if not _openal_available:
            from core.foundation.logger import Logger
            Logger.warning("OpenAL not available, audio disabled.")
            self._initialized = False
            return
        try:
            al.oalInit()
            if not al.oalGetInit():
                raise RuntimeError("OpenAL oalInit returned not initialized")
            try:
                from core.audio.efx import invalidate_efx_cache, ensure_efx
                invalidate_efx_cache()
                ensure_efx()
            except Exception:
                pass
            try:
                default_name = alc.alcGetString(None, alc.ALC_DEFAULT_DEVICE_SPECIFIER)
                if default_name:
                    self._device_name = default_name.decode("utf-8", errors="replace") if isinstance(default_name, bytes) else str(default_name)
                else:
                    self._device_name = "System Default"
            except Exception:
                self._device_name = "System Default"
            from core.foundation.logger import Logger
            Logger.info(f"Audio device: {self._device_name}")
            al.alDistanceModel(al.AL_INVERSE_DISTANCE_CLAMPED)
            al.alDopplerFactor(1.0)
            al.alSpeedOfSound(343.3)
            from core.audio.sys.sources import AudioSourceManager
            AudioSourceManager()
            self._initialized = True
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"OpenAL initialization failed: {e}")
            self._initialized = False
    def shutdown(self):
        if not _openal_available or not al.oalGetInit():
            try:
                from core.audio.efx import invalidate_efx_cache
                invalidate_efx_cache()
            except Exception:
                pass
            self._initialized = False
            return
        from core.audio.sys.sources import AudioSourceManager
        mgr = AudioSourceManager.instance()
        if mgr:
            try:
                mgr.stop_all()
            except Exception:
                pass
            try:
                mgr._active_sources.clear()
                mgr._source_info.clear()
                mgr._source_positions.clear()
                mgr._source_clips.clear()
                mgr._source_gains.clear()
                if hasattr(mgr, "_source_aux_slot"):
                    mgr._source_aux_slot.clear()
                if hasattr(mgr, "_source_aux_filter"):
                    try:
                        from core.audio.efx import delete_filter
                        for _fid in list(mgr._source_aux_filter.values()):
                            try:
                                delete_filter(int(_fid))
                            except Exception:
                                pass
                    except Exception:
                        pass
                    mgr._source_aux_filter.clear()
                if hasattr(mgr, "_source_aux_gain"):
                    mgr._source_aux_gain.clear()
                if hasattr(mgr, "_source_direct_filter"):
                    try:
                        from core.audio.efx import delete_filter as _del_f
                        for _fid in list(mgr._source_direct_filter.values()):
                            try:
                                _del_f(int(_fid))
                            except Exception:
                                pass
                    except Exception:
                        pass
                    mgr._source_direct_filter.clear()
            except Exception:
                pass
        for _, clip in list(self._clips.values()):
            if clip.buffer:
                try:
                    clip.buffer.destroy()
                except Exception:
                    pass
        self._clips.clear()
        try:
            al._buffers.clear()
            al.oalQuit()
        except Exception:
            pass
        try:
            from core.audio.efx import invalidate_efx_cache as _inv2
            _inv2()
        except Exception:
            pass
        self._initialized = False
    @property
    def device_name(self) -> str:
        return self._device_name
    def _import_mtime(self, path: str) -> float:
        import_path = path + ".import"
        try:
            return os.path.getmtime(import_path)
        except OSError:
            return 0.0
    def load_clip(self, path: str) -> AudioClip:
        abs_path = os.path.abspath(path)
        imtime = self._import_mtime(abs_path)
        cached = self._clips.get(abs_path)
        if cached is not None:
            c_mtime, clip = cached
            if abs(imtime - c_mtime) < 0.001:
                return clip
            try:
                clip.destroy_buffer()
            except Exception:
                pass
            self._clips.pop(abs_path, None)
        task_id = "audio_load:" + abs_path
        try:
            file_size = os.path.getsize(abs_path)
        except OSError:
            file_size = 0
        task_start(task_id, f"Loading audio {os.path.basename(abs_path)}...", total=float(file_size) if file_size else None, units="bytes")
        try:
            clip = AudioClip()
            try:
                clip.load_from_file(abs_path)
                clip.create_buffer()
                self._clips[abs_path] = (imtime, clip)
            except Exception as e:
                from core.foundation.logger import Logger
                Logger.error(f"Failed to load audio clip '{path}': {e}")
            return clip
        finally:
            task_complete(task_id)
    def load_clip_async(self, path: str, callback):
        abs_path = os.path.abspath(path)
        imtime = self._import_mtime(abs_path)
        cached = self._clips.get(abs_path)
        if cached is not None:
            c_mtime, clip = cached
            if abs(imtime - c_mtime) < 0.001:
                callback(clip)
                return
            try:
                clip.destroy_buffer()
            except Exception:
                pass
            self._clips.pop(abs_path, None)
        task_id = "audio_load:" + abs_path
        try:
            file_size = os.path.getsize(abs_path)
        except OSError:
            file_size = 0
        task_start(task_id, f"Loading audio {os.path.basename(abs_path)}...", total=float(file_size) if file_size else None, units="bytes")
        def _load():
            clip = AudioClip()
            try:
                clip.load_from_file(abs_path)
                clip.create_buffer()
                self._clips[abs_path] = (imtime, clip)
            except Exception as e:
                from core.foundation.logger import Logger
                Logger.error(f"Failed to load audio clip '{path}': {e}")
                clip = None
                self._clips.pop(abs_path, None)
            task_complete(task_id)
            callback(clip)
        _get_audio_pool().submit(_load)
    def get_clip(self, path: str) -> Optional[AudioClip]:
        abs_path = os.path.abspath(path)
        cached = self._clips.get(abs_path)
        if cached is not None:
            return cached[1]
        return None
    def set_listener_position(self, pos: tuple[float, float, float]):
        self._listener_pos = pos
        from core.audio.sys.sources import AudioSourceManager
        mgr = AudioSourceManager.instance()
        if mgr:
            mgr.update_listener_position(pos)
        if not self._initialized: return
        al.alListener3f(al.AL_POSITION, *pos)
    def set_listener_velocity(self, vel: tuple[float, float, float]):
        if not self._initialized: return
        al.alListener3f(al.AL_VELOCITY, *vel)
    def set_listener_orientation(self, at: tuple[float, float, float], up: tuple[float, float, float]):
        if not self._initialized: return
        arr = (al.ALfloat * 6)(at[0], at[1], at[2], up[0], up[1], up[2])
        al.alListenerfv(al.AL_ORIENTATION, arr)
    def set_master_volume(self, volume: float):
        if not self._initialized: return
        al.alListenerf(al.AL_GAIN, max(0.0, min(1.0, volume)))
    def set_doppler_factor(self, factor: float):
        if not self._initialized: return
        al.alDopplerFactor(factor)
    def set_speed_of_sound(self, speed: float):
        if not self._initialized: return
        al.alSpeedOfSound(speed)
    def set_distance_model(self, model: str):
        if not self._initialized: return
        al.alDistanceModel(_DISTANCE_MODEL_MAP.get(model, al.AL_INVERSE_DISTANCE_CLAMPED))
    def set_category_volume(self, category: str, volume: float):
        if category not in _AUDIO_CATEGORIES:
            return
        from core.config.config import get_global_config
        cfg = get_global_config()
        cfg.set(f"audio.{category}_volume", max(0.0, min(1.0, volume)), notify=False)
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            if eng and eng._project_path:
                from core.config.config import get_project_config
                pcfg = get_project_config(eng._project_path)
                pcfg.set(f"audio.{category}_volume", max(0.0, min(1.0, volume)), notify=False)
        except Exception:
            pass
    def get_category_volume(self, category: str) -> float:
        if category not in _AUDIO_CATEGORIES:
            return 1.0
        from core.config.config import get_global_config
        cfg = get_global_config()
        global_val = cfg.get(f"audio.{category}_volume", 1.0)
        if category == "master":
            return global_val
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            if eng and eng._project_path:
                from core.config.config import get_project_config
                pcfg = get_project_config(eng._project_path)
                proj_val = pcfg.get(f"audio.{category}_volume", 1.0)
                return global_val * proj_val
        except Exception:
            pass
        return global_val
    def get_effective_volume(self, category: str, base_volume: float) -> float:
        return base_volume * self.get_category_volume(category) * self.get_category_volume("master")
    def apply_project_audio_config(self):
        if not self._initialized:
            return
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            if not eng or not eng._project_path:
                return
            from core.config.config import get_project_config
            pcfg = get_project_config(eng._project_path)
        except Exception:
            return
        distance_model = pcfg.get("audio.distance_model", "inverse_distance_clamped")
        al.alDistanceModel(_DISTANCE_MODEL_MAP.get(distance_model, al.AL_INVERSE_DISTANCE_CLAMPED))
        al.alDopplerFactor(pcfg.get("audio.doppler_factor", 1.0))
        al.alSpeedOfSound(pcfg.get("audio.speed_of_sound", 343.3))
    @staticmethod
    def get_available_devices() -> list[str]:
        if not alc:
            return []
        devices = []
        try:
            raw = alc.alcGetString(None, alc.ALC_DEVICE_SPECIFIER)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                for dev in raw.split("\x00"):
                    if dev.strip():
                        devices.append(dev.strip())
        except Exception:
            pass
        return devices
    @staticmethod
    def get_default_device_name() -> str:
        if not alc:
            return ""
        try:
            raw = alc.alcGetString(None, alc.ALC_DEFAULT_DEVICE_SPECIFIER)
            if raw:
                return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        except Exception:
            pass
        return ""
