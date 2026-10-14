# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import numpy as np
from typing import Optional, Any
from core.audio.miniaudio_decoder import decode_audio, decode_audio_stereo, decode_audio_channels, miniaudio_available, AUDIO_EXTENSIONS, _detect_openal_format
try:
    import openal as al
    from openal import alc
    _openal_available = True
except Exception:
    _openal_available = False
    al = None
    alc = None
class AudioClip:
    def __init__(self):
        self._sample_rate: int = 0
        self._channels: int = 0
        self._data: memoryview | None = None
        self._format: int = 0
        self._buffer: Optional[al.Buffer] = None
        self._source: Optional[Any] = None
        self._path: str = ""
        self._pcm_mono: Any = None
        self._pcm_stereo: Any = None
        self._vis_rate: int = 0
    @property
    def sample_rate(self) -> int: return self._sample_rate
    @property
    def channels(self) -> int: return self._channels
    @property
    def data(self): return self._data
    @property
    def buffer(self): return self._buffer
    def ensure_pcm(self):
        if self._pcm_mono is not None:
            return self._pcm_mono
        if self._data is not None:
            raw = np.frombuffer(self._data, dtype=np.int16)
            pcm = raw.astype(np.float32) / 32768.0
            if self._channels == 2:
                if pcm.size % 2:
                    pcm = pcm[:pcm.size - pcm.size % 2]
                pcm = pcm.reshape(-1, 2).mean(axis=1)
            self._pcm_mono = np.ascontiguousarray(pcm, dtype=np.float32)
            self._vis_rate = self._sample_rate
            return self._pcm_mono
        if self._path:
            ext = os.path.splitext(self._path)[1].lower()
            if ext in (".wav", ".wave"):
                try:
                    import wave
                    with wave.open(self._path, "rb") as wf:
                        nch = wf.getnchannels()
                        sw = wf.getsampwidth()
                        sr = wf.getframerate()
                        raw = wf.readframes(wf.getnframes())
                    if sw == 2:
                        d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    elif sw == 4:
                        d = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
                    else:
                        return None
                    if nch > 1:
                        d = d.reshape(-1, nch).mean(axis=1)
                    self._sample_rate = sr
                    self._channels = nch
                    self._pcm_mono = np.ascontiguousarray(d, dtype=np.float32)
                    self._vis_rate = sr
                    return self._pcm_mono
                except Exception:
                    return None
            if miniaudio_available():
                decoded = decode_audio(self._path)
                if decoded is not None:
                    raw = np.frombuffer(decoded.pcm_int16, dtype=np.int16)
                    pcm = raw.astype(np.float32) / 32768.0
                    self._sample_rate = decoded.sample_rate
                    self._channels = decoded.channels
                    self._pcm_mono = np.ascontiguousarray(pcm, dtype=np.float32)
                    self._vis_rate = decoded.sample_rate
                    return self._pcm_mono
        return None
    def ensure_stereo_pcm(self):
        if self._pcm_stereo is not None:
            return self._pcm_stereo
        if self._data is not None:
            raw = np.frombuffer(self._data, dtype=np.int16)
            pcm = raw.astype(np.float32) / 32768.0
            if self._channels == 2:
                if pcm.size % 2:
                    pcm = pcm[:pcm.size - pcm.size % 2]
                pcm = pcm.reshape(-1, 2)
            else:
                pcm = np.column_stack([pcm, pcm])
            self._pcm_stereo = np.ascontiguousarray(pcm, dtype=np.float32)
            self._vis_rate = self._sample_rate
            return self._pcm_stereo
        if self._path:
            ext = os.path.splitext(self._path)[1].lower()
            if ext in (".wav", ".wave"):
                try:
                    import wave
                    with wave.open(self._path, "rb") as wf:
                        nch = wf.getnchannels()
                        sw = wf.getsampwidth()
                        sr = wf.getframerate()
                        raw = wf.readframes(wf.getnframes())
                    if sw == 2:
                        d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    elif sw == 4:
                        d = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
                    else:
                        return None
                    if nch >= 2:
                        d = d.reshape(-1, nch)[:, :2]
                    else:
                        d = np.column_stack([d, d])
                    self._sample_rate = sr
                    self._channels = nch
                    self._pcm_stereo = np.ascontiguousarray(d, dtype=np.float32)
                    self._vis_rate = sr
                    return self._pcm_stereo
                except Exception:
                    return None
            if miniaudio_available():
                decoded = decode_audio_stereo(self._path)
                if decoded is not None:
                    raw = np.frombuffer(decoded.pcm_int16, dtype=np.int16)
                    pcm = raw.astype(np.float32) / 32768.0
                    if decoded.channels == 2:
                        if pcm.size % 2:
                            pcm = pcm[:pcm.size - pcm.size % 2]
                        pcm = pcm.reshape(-1, 2)
                    else:
                        pcm = np.column_stack([pcm, pcm])
                    self._sample_rate = decoded.sample_rate
                    self._channels = decoded.channels
                    self._pcm_stereo = np.ascontiguousarray(pcm, dtype=np.float32)
                    self._vis_rate = decoded.sample_rate
                    return self._pcm_stereo
        return None
    def load_from_file(self, path: str):
        import json
        quality = None
        self._path = path
        import_path = path + ".import"
        if os.path.exists(import_path):
            try:
                with open(import_path) as f:
                    settings = json.load(f)
                quality = settings.get("quality")
            except Exception:
                pass
        ext = os.path.splitext(path)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio format: {ext}")
        if ext in (".wav", ".wave"):
            self._load_wav(path)
        elif miniaudio_available():
            self._load_with_miniaudio(path)
        else:
            raise RuntimeError(f"miniaudio not available; cannot load '{ext}' files. Install miniaudio: pip install miniaudio")
        if quality is not None:
            self._resample(quality)
    def _load_wav(self, path: str):
        import wave
        with wave.open(path, "rb") as wf:
            num_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            raw_data = wf.readframes(frames)
        self._sample_rate = sample_rate
        self._channels = num_channels
        self._format = _detect_openal_format(num_channels, sample_width)
        self._data = memoryview(bytearray(raw_data))
    def _load_with_miniaudio(self, path: str):
        decoded = decode_audio_channels(path, 1)
        if decoded is None:
            raise RuntimeError(f"Failed to decode audio file '{path}' with miniaudio")
        self._sample_rate = decoded.sample_rate
        self._channels = decoded.channels
        self._format = _detect_openal_format(decoded.channels, 2)
        self._data = memoryview(bytearray(decoded.pcm_int16))
    def _resample(self, quality: int):
        if quality >= 100 or self._data is None:
            return
        old_rate = self._sample_rate
        new_rate = max(8000, int(old_rate * quality / 100))
        if new_rate >= old_rate:
            return
        ratio = old_rate / new_rate
        raw = np.frombuffer(self._data, dtype=np.int16)
        if self._channels == 2:
            raw = raw.reshape(-1, 2)
        n = len(raw)
        new_n = max(1, int(n / ratio))
        indices = np.linspace(0, n - 1, new_n)
        if self._channels == 2:
            resampled = np.column_stack([np.interp(indices, np.arange(n), raw[:, 0]), np.interp(indices, np.arange(n), raw[:, 1])]).astype(np.int16)
        else:
            resampled = np.interp(indices, np.arange(n), raw).astype(np.int16)
        self._data = memoryview(resampled.tobytes())
        self._sample_rate = new_rate
    def create_buffer(self):
        if not self._data: return
        al.oalInit()
        self._buffer = al.Buffer(self._format, self._data.tobytes(), len(self._data), self._sample_rate)
    def destroy_buffer(self):
        if self._source:
            try:
                self._source.destroy()
            except Exception:
                pass
            self._source = None
        elif self._buffer:
            try:
                self._buffer.destroy()
            except Exception:
                pass
            self._buffer = None
