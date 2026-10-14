# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from nodmod import Song
from nodmod import Sample
from nodmod import Pattern
from nodmod import Note
import array
import copy
import struct
from nodmod.views import CellView, PlaybackRowView, RowView
from .header import _require_pydub
from .header import MODSong
NTSC_SR = 8287

class MODSongSamplesMixin:
    def load_sample(self, fname: str, sample_idx: int | None = None) -> tuple[int, Sample]:
        if sample_idx is not None and (sample_idx <= 0 or sample_idx > MODSong.SAMPLES):
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        if sample_idx is None:
            for i in range(MODSong.SAMPLES):
                if len(self.samples[i].waveform) == 0:
                    sample_idx = i + 1
                    break
            if sample_idx is None:
                raise ValueError("No empty sample slots available (1-31 are full).")
        self.samples[sample_idx - 1] = Sample()
        pydub = _require_pydub()
        audio = pydub.AudioSegment.from_wav(fname).set_channels(1)
        if audio.sample_width != 1:
            audio = audio.set_sample_width(1)
        self.samples[sample_idx - 1].waveform = audio.get_array_of_samples()
        self._update_n_actual_samples()
        return sample_idx, self.samples[sample_idx - 1]

    def load_sample_from_raw(self, raw_samples: list[float], sample_idx: int | None = None, input_sr: int = NTSC_SR) -> tuple[int, Sample]:
        if sample_idx is not None and (sample_idx <= 0 or sample_idx > MODSong.SAMPLES):
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        if sample_idx is None:
            for i in range(MODSong.SAMPLES):
                if len(self.samples[i].waveform) == 0:
                    sample_idx = i + 1
                    break
            if sample_idx is None:
                raise ValueError("No empty sample slots available (1-31 are full).")
        self.samples[sample_idx - 1] = Sample()
        pcm_bytes = bytearray()
        for s in raw_samples:
            if s > 1.0:
                s = 1.0
            elif s < -1.0:
                s = -1.0
            pcm_bytes.append(struct.pack('b', int(s * 127))[0])
        pydub = _require_pydub()
        audio = pydub.AudioSegment(
            data=bytes(pcm_bytes),
            sample_width=1,
            frame_rate=input_sr,
            channels=1
        )
        audio = audio.set_frame_rate(self.NTSC_SR)
        self.samples[sample_idx - 1].waveform = audio.get_array_of_samples()
        self._update_n_actual_samples()
        return sample_idx, self.samples[sample_idx - 1]

    def _get_effective_sample_rate(self, smp: Sample, period: str = "C-5") -> int:
        base_freq = MODSong.PAL_CLOCK / (MODSong.INV_PERIOD_TABLE[period] * 2)
        finetune = smp.finetune
        if finetune > 7:
            finetune = finetune - 16
        finetune_multiplier = 2 ** (finetune / 96.0)
        effective_sample_rate = int(base_freq * finetune_multiplier)
        return effective_sample_rate

    def set_sample_name(self, sample_idx: int, name: str) -> None:
        smp = self.get_sample(sample_idx)
        smp.name = name

    def set_sample_volume(self, sample_idx: int, volume: int) -> None:
        if volume < 0 or volume > 64:
            raise ValueError(f"Invalid volume {volume} (expected 0-64).")
        smp = self.get_sample(sample_idx)
        smp.volume = volume

    def set_sample_finetune(self, sample_idx: int, finetune: int) -> None:
        if finetune < 0 or finetune > 15:
            raise ValueError(f"Invalid finetune {finetune} (expected 0-15).")
        smp = self.get_sample(sample_idx)
        smp.finetune = finetune

    def set_sample_loop(self, sample_idx: int, start: int, length: int) -> None:
        smp = self.get_sample(sample_idx)
        smp.repeat_point = max(0, start)
        smp.repeat_len = max(0, length)

    def get_sample_pcm_i8(self, sample_idx: int) -> bytes:
        smp = self.get_sample(sample_idx)
        return smp.waveform.tobytes()

    def set_sample_pcm_i8(
        self,
        sample_idx: int,
        pcm_i8: bytes | bytearray | memoryview | array.array,
        *,
        reset_meta: bool = False,
    ) -> None:
        smp = self.get_sample(sample_idx)
        raw: bytes
        if isinstance(pcm_i8, array.array):
            if pcm_i8.typecode not in {'b', 'B'}:
                raise TypeError(f"Invalid PCM array typecode {pcm_i8.typecode!r} (expected 'b' or 'B').")
            raw = pcm_i8.tobytes()
        elif isinstance(pcm_i8, (bytes, bytearray, memoryview)):
            raw = bytes(pcm_i8)
        else:
            raise TypeError(
                f"Invalid pcm_i8 type {type(pcm_i8).__name__} "
                "(expected bytes, bytearray, memoryview, or array.array)."
            )
        smp.waveform = array.array('b')
        smp.waveform.frombytes(raw)
        if reset_meta:
            smp.name = ""
            smp.finetune = 0
            smp.volume = 64
            smp.repeat_point = 0
            smp.repeat_len = 0
            smp.tune = ''
        self._update_n_actual_samples()

    def set_sample_loop_bytes(self, sample_idx: int, start_byte: int, length_byte: int) -> None:
        if start_byte < 0:
            raise ValueError(f"Invalid loop start {start_byte} (expected >= 0).")
        if length_byte < 0:
            raise ValueError(f"Invalid loop length {length_byte} (expected >= 0).")
        smp = self.get_sample(sample_idx)
        smp.repeat_point = start_byte
        smp.repeat_len = length_byte

    def sanitize_samples(self, *, mode: str = "coerce") -> None:
        for smp in self.samples:
            smp.sanitize_loop(mode=mode)

    def validate_samples(self) -> None:
        for sample_idx, smp in enumerate(self.samples, start=1):
            try:
                smp.validate_loop()
            except ValueError as exc:
                raise ValueError(f"Sample {sample_idx}: {exc}") from exc

    def validate_sample_loop(self, sample_idx: int) -> None:
        smp = self.get_sample(sample_idx)
        smp.validate_loop()

    def get_sample_duration(self, sample_idx: int, period: str = "C-5") -> float:
        if sample_idx <= 0 or sample_idx > MODSong.SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        smp = self.samples[sample_idx - 1]
        if len(smp.waveform) == 0:
            raise ValueError(f"Sample {sample_idx} has no waveform data")
        effective_sample_rate = self._get_effective_sample_rate(smp, period)
        duration = len(smp.waveform) / effective_sample_rate
        return duration

    def save_sample(self, sample_idx: int, fname: str, period: str = "C-5", force_sample_rate: int = None):
        if sample_idx <= 0 or sample_idx > MODSong.SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        smp = self.samples[sample_idx - 1]
        if len(smp.waveform) == 0:
            raise ValueError(f"Sample {sample_idx} has no waveform data")
        effective_sample_rate = self._get_effective_sample_rate(smp, period)
        pydub = _require_pydub()
        audio = pydub.AudioSegment(
            data=smp.waveform.tobytes(),
            sample_width=1,
            frame_rate=effective_sample_rate,
            channels=1
        )
        if force_sample_rate is not None and force_sample_rate != effective_sample_rate:
            audio = audio.set_frame_rate(force_sample_rate)
        audio.export(fname, format="wav")

    def get_sample(self, sample_idx: int) -> Sample:
        if sample_idx <= 0 or sample_idx > MODSong.SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        return self.samples[sample_idx - 1]

    def list_samples(self) -> list[Sample]:
        return self.samples

    def set_sample(self, sample_idx: int, sample: Sample) -> None:
        if sample_idx <= 0 or sample_idx > MODSong.SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        self.samples[sample_idx - 1] = sample
        self._update_n_actual_samples()

    def copy_sample_from(self, src: 'MODSong', src_sample_idx: int, dst_sample_idx: int | None = None) -> int:
        if src_sample_idx <= 0 or src_sample_idx > MODSong.SAMPLES:
            raise IndexError(f"Invalid source sample index {src_sample_idx} (expected 1-31).")
        if dst_sample_idx is not None and (dst_sample_idx <= 0 or dst_sample_idx > MODSong.SAMPLES):
            raise IndexError(f"Invalid destination sample index {dst_sample_idx} (expected 1-31).")
        src_smp = src.samples[src_sample_idx - 1]
        new_smp = Sample()
        new_smp.name = src_smp.name
        new_smp.finetune = src_smp.finetune
        new_smp.volume = src_smp.volume
        new_smp.repeat_point = src_smp.repeat_point
        new_smp.repeat_len = src_smp.repeat_len
        new_smp.waveform = src_smp.waveform.__class__(src_smp.waveform.typecode, src_smp.waveform)
        new_smp.tune = src_smp.tune
        if dst_sample_idx is None:
            for i in range(MODSong.SAMPLES):
                if len(self.samples[i].waveform) == 0:
                    dst_sample_idx = i + 1
                    break
            if dst_sample_idx is None:
                raise ValueError("Couldn't find an empty slot for the new sample.")
        self.samples[dst_sample_idx - 1] = new_smp
        self._update_n_actual_samples()
        return dst_sample_idx

    def copy_samples_from(self, src: 'MODSong', src_sample_indices: list[int]) -> list[int]:
        new_indices: list[int] = []
        for idx in src_sample_indices:
            new_indices.append(self.copy_sample_from(src, idx, None))
        return new_indices

    def remove_sample(self, sample_idx: int):
        if sample_idx <= 0 or sample_idx > MODSong.SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        self.samples[sample_idx - 1] = Sample()
        self._update_n_actual_samples()

    def keep_sample(self, sample_idx: int):
        if sample_idx <= 0 or sample_idx > MODSong.SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-31).")
        for s in range(MODSong.SAMPLES):
            if s + 1 != sample_idx:
                self.samples[s] = Sample()
        self._update_n_actual_samples()

    def get_used_samples(
        self,
        *,
        scope: str = "sequence",
        order: str = "sorted",
        resolved: bool = True,
    ) -> list[int]:
        self._validate_used_resource_args(scope, order)
        if resolved:
            if scope == "sequence":
                self._ensure_sequence_resolution_cache()
                first_use = list(self._resolved_sequence_first_use)
            else:
                self._ensure_reachable_resolution_cache()
                first_use = list(self._resolved_reachable_first_use)
            return self._finalize_used_values(first_use, order)
        seen: set[int] = set()
        first_use: list[int] = []
        for note in self._iter_notes_by_scope(scope):
            sample_idx = getattr(note, 'instrument_idx', 0)
            if sample_idx > 0 and sample_idx not in seen:
                seen.add(sample_idx)
                first_use.append(sample_idx)
        return self._finalize_used_values(first_use, order)
