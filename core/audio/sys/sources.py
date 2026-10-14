# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
from contextlib import suppress
from typing import Optional, Tuple, Any
from core.audio.sys.curve import AudioRolloffCurve, _normalize_audio_zone_shape, _normalize_audio_box_halves, _box_zone_t
from core.audio.sys.system import al, _openal_available, _read_audio_value, _get_aux_send_filter
from core.audio.sys.clip import AudioClip
class AudioSourceManager:
    _instance: Optional[AudioSourceManager] = None
    def __init__(self):
        AudioSourceManager._instance = self
        self._active_sources: dict[int, int] = {}; self._source_info: dict[int, dict] = {}; self._source_positions: dict[int, tuple[float, float, float]] = {}; self._source_aux_slot: dict[int, int] = {}
        self._source_aux_filter: dict[int, int] = {}; self._source_aux_gain: dict[int, float] = {}; self._source_direct_filter: dict[int, int] = {}; self._source_clips: dict[int, AudioClip] = {}
        self._source_gains: dict[int, float] = {}; self._listener_pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    @classmethod
    def instance(cls) -> Optional[AudioSourceManager]: return cls._instance
    def _distance_to_listener(self, position: Tuple[float, float, float]) -> float:
        dx = position[0] - self._listener_pos[0]; dy = position[1] - self._listener_pos[1]; dz = position[2] - self._listener_pos[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    @staticmethod
    def _clear_al_errors():
        if not al:
            return
        with suppress(Exception):
            while al.alGetError() != al.AL_NO_ERROR:
                pass
    @staticmethod
    def _delete_al_source(src_val: int):
        if not al or not src_val:
            return
        with suppress(Exception):
            al.alDeleteSources(1, al.ctypes.pointer(al.ctypes.c_uint(src_val)))
    def _max_sources_limit(self) -> int:
        try:
            value = _read_audio_value("audio.max_sources", 32)
            return max(1, min(256, int(value)))
        except Exception:
            return 32
    def _priority_threshold(self) -> float:
        try:
            value = _read_audio_value("audio.priority_threshold", 0.1)
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.1
    def _spatialization_on(self) -> bool:
        try:
            value = _read_audio_value("audio.enable_spatialization", True)
            return bool(value)
        except Exception:
            return True
    def _enforce_source_limit(self):
        try:
            limit = self._max_sources_limit()
            if len(self._active_sources) < limit:
                return True
            scored = []
            for src in list(self._active_sources.keys()):
                pos = self._source_positions.get(src, self._listener_pos)
                dist = self._distance_to_listener(pos) if pos is not None else 0.0
                info = self._source_info.get(src, {})
                looping = bool(info.get("looping", False)); gain = float(self._source_gains.get(src, 1.0))
                scored.append((looping, gain, -dist, src))
            scored.sort(key=lambda item: (item[0], item[1], item[2]))
            victim = scored[0][3] if scored else None
            if victim is not None:
                with suppress(Exception):
                    self.stop(int(victim))
            return len(self._active_sources) < limit
        except Exception:
            return True
    def play(self, clip_path: str, loop: bool = False, volume: float = 1.0, pitch: float = 1.0, spatial_blend: float = 1.0, min_distance: float = 1.0, max_distance: float = 50.0, volume_rolloff: list[list[float]] = None, offset: float = 0.0, velocity: tuple[float, float, float] = (0.0, 0.0, 0.0), zone_shape: str = "sphere", box_inner_size=None, box_outer_size=None) -> int | None:
        if not al.oalGetInit(): return None
        from core.audio.sys.system import AudioSystem
        audio_sys = AudioSystem.instance()
        if not audio_sys: return None
        if not self._enforce_source_limit():
            return None
        clip = audio_sys.load_clip(clip_path)
        if not clip or not clip.buffer: return None
        if not self._spatialization_on():
            spatial_blend = 0.0
        src_val = 0
        try:
            self._clear_al_errors()
            source_id = al.ctypes.c_uint()
            al.alGenSources(1, al.ctypes.pointer(source_id))
            src_val = source_id.value
            al.alSourcei(src_val, al.AL_BUFFER, clip.buffer._geti())
            al.alSourcef(src_val, al.AL_PITCH, pitch); al.alSourcef(src_val, al.AL_GAIN, volume); al.alSourcei(src_val, al.AL_LOOPING, 1 if loop else 0)
            with suppress(Exception):
                al.alSourcei(src_val, 0x1214, 0x0001)
            al.alSource3f(src_val, al.AL_POSITION, 0.0, 0.0, 0.0); al.alSource3f(src_val, al.AL_VELOCITY, *velocity)
            zs = _normalize_audio_zone_shape(zone_shape)
            inner_half = _normalize_audio_box_halves(box_inner_size, 2.0); outer_half = _normalize_audio_box_halves(box_outer_size, 10.0)
            outer_half = (max(outer_half[0], inner_half[0]), max(outer_half[1], inner_half[1]), max(outer_half[2], inner_half[2]))
            if zs == "box":
                ref_d = min(inner_half[0], inner_half[1], inner_half[2]); max_d = math.sqrt(outer_half[0] * outer_half[0] + outer_half[1] * outer_half[1] + outer_half[2] * outer_half[2])
            else:
                ref_d = min_distance; max_d = max_distance
            al.alSourcef(src_val, al.AL_REFERENCE_DISTANCE, ref_d); al.alSourcef(src_val, al.AL_MAX_DISTANCE, max_d); al.alSourcef(src_val, al.AL_ROLLOFF_FACTOR, 0.0)
            al.alSourcei(src_val, al.AL_SOURCE_RELATIVE, 0 if spatial_blend > 0 else 1)
            if offset > 0.0:
                al.alSourcef(src_val, 0x1024, offset)
            al.alSourcePlay(src_val)
        except Exception:
            self._delete_al_source(src_val); self._clear_al_errors()
            return None
        self._active_sources[src_val] = src_val; self._source_clips[src_val] = clip; self._source_gains[src_val] = volume
        self._source_info[src_val] = {"min_distance": min_distance, "max_distance": max_distance, "spatial_blend": spatial_blend, "volume_rolloff": volume_rolloff or [[0, 1], [1, 0]], "offset": offset, "velocity": velocity, "looping": loop, "zone_shape": zs, "box_inner": inner_half, "box_outer": outer_half}
        self._source_positions[src_val] = (0.0, 0.0, 0.0); self._source_aux_slot[src_val] = 0
        if not hasattr(self, "_source_aux_filter"):
            self._source_aux_filter = {}
        if not hasattr(self, "_source_aux_gain"):
            self._source_aux_gain = {}
        if not hasattr(self, "_source_direct_filter"):
            self._source_direct_filter = {}
        self._source_aux_filter.pop(src_val, None); self._source_aux_gain[src_val] = 0.0; self._source_direct_filter.pop(src_val, None)
        return src_val
    def update_source(self, source: int, volume: float, pitch: float, position: tuple[float, float, float], spatial_blend: float | None = None, velocity: tuple[float, float, float] | None = None, min_distance: float | None = None, max_distance: float | None = None, zone_shape=None, box_inner_size=None, box_outer_size=None):
        if not source or not al.oalGetInit(): return
        try:
            state = al.ctypes.c_int()
            al.alGetSourcei(source, al.AL_SOURCE_STATE, state)
            if state.value in (al.AL_PLAYING, al.AL_PAUSED):
                al.alSourcef(source, al.AL_PITCH, pitch)
                if velocity is not None:
                    al.alSource3f(source, al.AL_VELOCITY, *velocity)
                    info = self._source_info.get(source)
                    if info:
                        info["velocity"] = velocity
                if not self._spatialization_on():
                    spatial_blend = 0.0
                info = self._source_info.get(source)
                if spatial_blend is not None and info:
                    if min_distance is not None:
                        with suppress(Exception):
                            info["min_distance"] = float(min_distance)
                    if max_distance is not None:
                        with suppress(Exception):
                            info["max_distance"] = float(max_distance)
                    if zone_shape is not None:
                        info["zone_shape"] = _normalize_audio_zone_shape(zone_shape)
                    if box_inner_size is not None:
                        with suppress(Exception):
                            cur = info.get("box_inner", (1.0, 1.0, 1.0))
                            info["box_inner"] = _normalize_audio_box_halves(box_inner_size, cur[0] * 2.0)
                    if box_outer_size is not None:
                        with suppress(Exception):
                            cur = info.get("box_outer", (5.0, 5.0, 5.0))
                            info["box_outer"] = _normalize_audio_box_halves(box_outer_size, cur[0] * 2.0)
                    with suppress(Exception):
                        inner_half = info.get("box_inner", (1.0, 1.0, 1.0)); outer_half = info.get("box_outer", (5.0, 5.0, 5.0))
                        info["box_outer"] = (max(float(outer_half[0]), float(inner_half[0])), max(float(outer_half[1]), float(inner_half[1])), max(float(outer_half[2]), float(inner_half[2])))
                    info["spatial_blend"] = spatial_blend
                    if spatial_blend > 0:
                        al.alSource3f(source, al.AL_POSITION, *position); al.alSourcei(source, al.AL_SOURCE_RELATIVE, 0)
                        self._source_positions[source] = position
                        if info.get("zone_shape", "sphere") == "box":
                            t = _box_zone_t(self._listener_pos, position, info.get("box_inner", (1.0, 1.0, 1.0)), info.get("box_outer", (5.0, 5.0, 5.0)))
                            atten = AudioRolloffCurve.evaluate_normalized(t, info.get("volume_rolloff", [[0, 1], [1, 0]]))
                        else:
                            dist = self._distance_to_listener(position)
                            atten = AudioRolloffCurve.evaluate(dist, info["min_distance"], info["max_distance"], info.get("volume_rolloff", [[0, 1], [1, 0]]))
                        final_volume = volume * atten
                        al.alSourcef(source, al.AL_GAIN, final_volume)
                    else:
                        al.alSource3f(source, al.AL_POSITION, 0.0, 0.0, 0.0); al.alSourcei(source, al.AL_SOURCE_RELATIVE, 1); al.alSourcef(source, al.AL_GAIN, volume)
                else:
                    if self._spatialization_on():
                        al.alSource3f(source, al.AL_POSITION, *position)
                    else:
                        al.alSource3f(source, al.AL_POSITION, 0.0, 0.0, 0.0)
                        with suppress(Exception):
                            al.alSourcei(source, al.AL_SOURCE_RELATIVE, 1)
                    al.alSourcef(source, al.AL_GAIN, volume)
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"update_source error: {e}")
    def update_listener_position(self, pos: Tuple[float, float, float]): self._listener_pos = pos
    def get_active_source_ids(self) -> list[int]: return list(self._active_sources.keys())
    def get_active_sound_count(self) -> int:
        if not _openal_available or not al.oalGetInit():
            return 0
        count = 0
        for src in list(self._active_sources.keys()):
            with suppress(Exception):
                state = al.ctypes.c_int(); al.alGetSourcei(src, al.AL_SOURCE_STATE, state)
                if state.value == al.AL_PLAYING:
                    count += 1
        return count
    def get_total_sound_count(self) -> int: return len(self._active_sources)
    def get_dsp_load(self) -> float: return 0.0
    def get_source_position(self, source_id: int) -> Optional[tuple[float, float, float]]: return self._source_positions.get(source_id)
    def get_source_aux_slot(self, source_id: int) -> int: return self._source_aux_slot.get(source_id, 0)
    def get_source_aux_filter(self, source_id: int) -> int:
        if not hasattr(self, "_source_aux_filter"):
            self._source_aux_filter = {}
        return self._source_aux_filter.get(source_id, 0)
    def get_source_aux_gain(self, source_id: int) -> float:
        if not hasattr(self, "_source_aux_gain"):
            self._source_aux_gain = {}
        return float(self._source_aux_gain.get(source_id, 0.0))
    def _ensure_aux_filter(self, source_id: int) -> int:
        if not hasattr(self, "_source_aux_filter"):
            self._source_aux_filter = {}
        existing = self._source_aux_filter.get(source_id, 0)
        if existing:
            with suppress(Exception):
                from core.audio.efx import is_filter
                if is_filter(int(existing)):
                    return int(existing)
            self._source_aux_filter.pop(source_id, None)
        try:
            from core.audio.efx import create_filter, set_filter_type, AL_FILTER_LOWPASS
            fid = int(create_filter()); set_filter_type(int(fid), int(AL_FILTER_LOWPASS))
            self._source_aux_filter[int(source_id)] = int(fid)
            return int(fid)
        except Exception:
            return 0
    def _delete_aux_filter(self, source_id: int):
        if not hasattr(self, "_source_aux_filter"):
            return
        fid = self._source_aux_filter.pop(int(source_id), 0)
        if fid:
            with suppress(Exception):
                from core.audio.efx import delete_filter
                delete_filter(int(fid))
        if hasattr(self, "_source_aux_gain"):
            self._source_aux_gain.pop(int(source_id), None)
    def _delete_direct_filter(self, source_id: int):
        if not hasattr(self, "_source_direct_filter"):
            return
        fid = self._source_direct_filter.pop(int(source_id), 0)
        if fid:
            with suppress(Exception):
                from core.audio.efx import delete_filter, set_source_direct_filter
                with suppress(Exception):
                    set_source_direct_filter(int(source_id), 0)
                delete_filter(int(fid))
    def set_source_aux_send(self, source_id: int, slot_id: int, filter_id: int = 0, send_index: int = 0):
        if not source_id or not al.oalGetInit():
            return
        if int(slot_id) != 0:
            with suppress(Exception):
                from core.audio.efx import reverb_enabled
                if not bool(reverb_enabled()):
                    slot_id = 0; filter_id = 0
        current = self._source_aux_slot.get(int(source_id), 0)
        if hasattr(self, "_source_aux_filter"):
            tracked = self._source_aux_filter.get(int(source_id), 0)
            if int(filter_id) == 0 and int(tracked) != 0:
                filter_id = int(tracked)
        else:
            self._source_aux_filter = {}
        if int(current) == int(slot_id) and int(filter_id) == int(self._source_aux_filter.get(int(source_id), 0)):
            if int(slot_id) == 0:
                return
            try:
                if float(self._source_aux_gain.get(int(source_id), 1.0)) > 0.999 and int(filter_id) != 0:
                    pass
                else:
                    raise ValueError("gain")
            except ValueError:
                pass
            except Exception:
                return
        try:
            from core.audio.efx import set_source_aux_send as _efx_send
            ok = bool(_efx_send(int(source_id), int(slot_id), int(filter_id), int(send_index)))
            if ok:
                self._source_aux_slot[int(source_id)] = int(slot_id)
                if int(filter_id) != 0:
                    self._source_aux_filter[int(source_id)] = int(filter_id)
                if int(slot_id) == 0 and int(filter_id) == 0:
                    if hasattr(self, "_source_aux_gain"):
                        self._source_aux_gain[int(source_id)] = 0.0
            else:
                if int(slot_id) == 0:
                    self._source_aux_slot[int(source_id)] = 0
        except Exception:
            pass
    def set_source_aux_send_weighted(self, source_id: int, slot_id: int, weight: float, send_index: int = 0):
        if not source_id or not al.oalGetInit():
            return
        try:
            w = max(0.0, min(1.0, float(weight)))
        except Exception:
            w = 0.0
        if w <= 0.001 or int(slot_id) == 0:
            try:
                current = int(self._source_aux_slot.get(int(source_id), 0))
            except Exception:
                current = 0
            if current == 0:
                if hasattr(self, "_source_aux_gain"):
                    self._source_aux_gain[int(source_id)] = 0.0
                return
            self.set_source_aux_send(int(source_id), 0, 0, int(send_index))
            if hasattr(self, "_source_aux_gain"):
                self._source_aux_gain[int(source_id)] = 0.0
            return
        fid = 0
        try:
            from core.audio.efx import efx_available, set_filter_param_f, AL_LOWPASS_GAIN, AL_LOWPASS_GAINHF
            if bool(efx_available()):
                fid = int(self._ensure_aux_filter(int(source_id)))
                if fid:
                    set_filter_param_f(int(fid), int(AL_LOWPASS_GAIN), float(w)); set_filter_param_f(int(fid), int(AL_LOWPASS_GAINHF), 1.0)
                else:
                    fid = 0
        except Exception:
            fid = 0
        try:
            prev_slot = int(self._source_aux_slot.get(int(source_id), 0)); prev_gain = float(self._source_aux_gain.get(int(source_id), -1.0)) if hasattr(self, "_source_aux_gain") else -1.0
            if prev_slot == int(slot_id) and abs(prev_gain - float(w)) < 0.01:
                return
        except Exception:
            pass
        self.set_source_aux_send(int(source_id), int(slot_id), int(fid), int(send_index))
        if hasattr(self, "_source_aux_gain"):
            self._source_aux_gain[int(source_id)] = float(w)
    def set_source_occlusion(self, source_id: int, occlusion: float):
        if not source_id or not al.oalGetInit():
            return
        try:
            occ = max(0.0, min(1.0, float(occlusion)))
        except Exception:
            occ = 0.0
        try:
            from core.audio.efx import occlusion_enabled
            if not bool(occlusion_enabled()):
                occ = 0.0
        except Exception:
            pass
        if occ <= 0.001:
            if hasattr(self, "_source_direct_filter"):
                existing = int(self._source_direct_filter.get(int(source_id), 0))
                if existing:
                    self._delete_direct_filter(int(source_id))
            return
        try:
            from core.audio.efx import efx_available, create_filter, set_filter_type, set_filter_param_f, set_source_direct_filter, AL_FILTER_LOWPASS, AL_LOWPASS_GAIN, AL_LOWPASS_GAINHF
            if not bool(efx_available()):
                return
            if not hasattr(self, "_source_direct_filter"):
                self._source_direct_filter = {}
            fid = int(self._source_direct_filter.get(int(source_id), 0)); valid = False
            if fid:
                with suppress(Exception):
                    from core.audio.efx import is_filter as _is_f
                    valid = bool(_is_f(int(fid)))
            if not valid:
                fid = int(create_filter()); set_filter_type(int(fid), int(AL_FILTER_LOWPASS)); self._source_direct_filter[int(source_id)] = int(fid)
            gain = max(0.05, 1.0 - float(occ) * 0.85); gain_hf = max(0.05, 1.0 - float(occ) * 0.9)
            set_filter_param_f(int(fid), int(AL_LOWPASS_GAIN), float(gain)); set_filter_param_f(int(fid), int(AL_LOWPASS_GAINHF), float(gain_hf)); set_source_direct_filter(int(source_id), int(fid))
        except Exception:
            pass
    def pause(self, source: int):
        if not source or not al.oalGetInit(): return
        with suppress(Exception):
            state = al.ctypes.c_int(); al.alGetSourcei(source, al.AL_SOURCE_STATE, state)
            if state.value == al.AL_PLAYING:
                al.alSourcePause(source)
    def resume(self, source: int):
        if not source or not al.oalGetInit(): return
        with suppress(Exception):
            state = al.ctypes.c_int(); al.alGetSourcei(source, al.AL_SOURCE_STATE, state)
            if state.value == al.AL_PAUSED:
                al.alSourcePlay(source)
    def stop(self, source: int):
        if not source:
            return
        with suppress(Exception):
            if al.oalGetInit():
                with suppress(Exception):
                    from core.audio.efx import set_source_aux_send as _efx_clear, set_source_direct_filter as _efx_clear_direct
                    with suppress(Exception):
                        _efx_clear(int(source), 0, 0, 0)
                    with suppress(Exception):
                        _efx_clear_direct(int(source), 0)
                with suppress(Exception):
                    state = al.ctypes.c_int(); al.alGetSourcei(source, al.AL_SOURCE_STATE, state)
                    if state.value in (al.AL_PLAYING, al.AL_PAUSED):
                        al.alSourceStop(source)
                    al.alDeleteSources(1, al.ctypes.pointer(al.ctypes.c_uint(source)))
        with suppress(Exception):
            self._delete_aux_filter(int(source))
        with suppress(Exception):
            self._delete_direct_filter(int(source))
        self._active_sources.pop(source, None); self._source_info.pop(source, None); self._source_positions.pop(source, None); self._source_aux_slot.pop(source, None); self._source_clips.pop(source, None); self._source_gains.pop(source, None)
        if hasattr(self, "_source_aux_gain"):
            self._source_aux_gain.pop(source, None)
    def stop_all(self):
        if not al.oalGetInit():
            with suppress(Exception):
                self._active_sources.clear(); self._source_info.clear(); self._source_positions.clear(); self._source_aux_slot.clear(); self._source_clips.clear(); self._source_gains.clear()
                if hasattr(self, "_source_aux_filter"):
                    self._source_aux_filter.clear()
                if hasattr(self, "_source_aux_gain"):
                    self._source_aux_gain.clear()
                if hasattr(self, "_source_direct_filter"):
                    self._source_direct_filter.clear()
            return
        for src in list(self._active_sources.keys()):
            with suppress(Exception):
                with suppress(Exception):
                    from core.audio.efx import set_source_aux_send as _efx_c, set_source_direct_filter as _efx_cd
                    with suppress(Exception):
                        _efx_c(int(src), 0, 0, 0)
                    with suppress(Exception):
                        _efx_cd(int(src), 0)
                state = al.ctypes.c_int(); al.alGetSourcei(src, al.AL_SOURCE_STATE, state)
                if state.value in (al.AL_PLAYING, al.AL_PAUSED):
                    al.alSourceStop(src)
                al.alDeleteSources(1, al.ctypes.pointer(al.ctypes.c_uint(src)))
            with suppress(Exception):
                self._delete_aux_filter(int(src))
            with suppress(Exception):
                self._delete_direct_filter(int(src))
        self._active_sources.clear(); self._source_info.clear(); self._source_positions.clear(); self._source_aux_slot.clear(); self._source_clips.clear(); self._source_gains.clear()
        if hasattr(self, "_source_aux_filter"):
            with suppress(Exception):
                from core.audio.efx import delete_filter as _df
                for _fid in list(self._source_aux_filter.values()):
                    with suppress(Exception):
                        _df(int(_fid))
            self._source_aux_filter.clear()
        if hasattr(self, "_source_aux_gain"):
            self._source_aux_gain.clear()
        if hasattr(self, "_source_direct_filter"):
            with suppress(Exception):
                from core.audio.efx import delete_filter as _df2
                for _fid in list(self._source_direct_filter.values()):
                    with suppress(Exception):
                        _df2(int(_fid))
            self._source_direct_filter.clear()
