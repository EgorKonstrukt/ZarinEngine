# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import shutil

import numpy as np

from .engine import _RENDER_VERSION
from .engine import TrackerSoftwareRenderer


def _sample_for_instrument_mode(song, inst_idx: int):
    fmt = getattr(song, "file_extension", "mod")
    try:
        if fmt == "xm":
            if 1 <= inst_idx <= len(song.instruments):
                inst = song.instruments[inst_idx - 1]
                if inst.samples:
                    return inst.samples[0]
        elif 1 <= inst_idx <= len(song.samples):
            return song.samples[inst_idx - 1]
    except Exception:
        return None
    return None


def render_to_wav_file(pcm: np.ndarray, path: str, sample_rate: int = 44100):
    import wave
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        interleaved = np.zeros(pcm.shape[0] * 2, dtype=np.int16)
        interleaved[0::2] = pcm[:, 0]
        interleaved[1::2] = pcm[:, 1]
        wf.writeframes(interleaved.tobytes())


def find_external_renderer() -> str | None:
    for tool in ("openmpt123", "ffmpeg"):
        if shutil.which(tool):
            return tool
    return None


class TrackerRenderService:
    def __init__(self, cache_dir: str, sample_rate: int = 44100):
        self.cache_dir = cache_dir
        self.sample_rate = sample_rate
        os.makedirs(cache_dir, exist_ok=True)

    def _file_key(self, path: str) -> str:
        import hashlib
        try:
            with open(path, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()[:16]
        except Exception:
            h = os.path.basename(path)
        return f"{h}_{self.sample_rate}_v{_RENDER_VERSION}"

    def render_wav(self, module_path: str, quality: str = "software") -> str | None:
        cache_path = os.path.join(self.cache_dir, self._file_key(module_path) + ".wav")
        if os.path.isfile(cache_path):
            return cache_path
        song = load_module(module_path)
        if song is None:
            return None
        pcm = None
        try:
            from nodmod.song import Song
        except Exception:
            pass
        if quality == "external":
            tool = find_external_renderer()
            if tool is not None:
                try:
                    tmp_wav = cache_path + ".tmp.wav"
                    try:
                        song.render(tmp_wav, verbose=False, channels=2)
                        if os.path.isfile(tmp_wav):
                            shutil.move(tmp_wav, cache_path)
                            return cache_path
                    except Exception:
                        pass
                except Exception:
                    pass
        try:
            pcm = TrackerSoftwareRenderer(self.sample_rate).render(song)
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"Tracker render failed: {e}", e)
            return None
        if pcm is None or len(pcm) == 0:
            return None
        render_to_wav_file(pcm, cache_path, self.sample_rate)
        return cache_path


def load_module(path: str):
    if not path or not os.path.isfile(path):
        return None
    try:
        from nodmod.loader import load_song
        return load_song(path, verbose=False)
    except Exception as e:
        from core.foundation.logger import Logger
        Logger.error(f"Failed to load tracker module '{path}': {e}", e)
        return None
