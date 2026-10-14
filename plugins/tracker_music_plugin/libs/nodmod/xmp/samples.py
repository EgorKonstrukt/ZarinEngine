# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import array
import copy
import warnings
from nodmod import Song
from nodmod import XMSample
from nodmod import Sample
from nodmod import Instrument
from nodmod import EnvelopePoint
from nodmod import Pattern
from nodmod import XMNote
from nodmod.views import PlaybackRowView, SampleView
from .header import _require_pydub

class XMSongSamplesMixin:
    def iter_samples(self, *, include_empty: bool = True):
        sample_idx = 1
        for inst in self.instruments:
            for sample in inst.samples:
                length = len(sample.waveform)
                if not include_empty and length == 0:
                    sample_idx += 1
                    continue
                yield SampleView(
                    sample_idx=sample_idx,
                    name=sample.name,
                    length=length,
                    finetune=sample.finetune,
                    volume=sample.volume,
                    loop_start=sample.repeat_point,
                    loop_length=sample.repeat_len,
                )
                sample_idx += 1
    def new_instrument(self, name: str = "") -> int:
        inst = Instrument()
        inst.name = name
        self.instruments.append(inst)
        self.n_instruments = len(self.instruments)
        return self.n_instruments
    def list_instruments(self) -> list[Instrument]:
        return self.instruments
    def get_instrument(self, inst_idx: int) -> Instrument:
        if inst_idx <= 0 or inst_idx > len(self.instruments):
            raise IndexError(f"Invalid instrument index {inst_idx} (expected 1-{len(self.instruments)}).")
        return self.instruments[inst_idx - 1]
    def set_volume_envelope(
        self,
        inst_idx: int,
        points: list[EnvelopePoint | tuple[int, int]],
        sustain: int | None = None,
        loop: tuple[int, int] | None = None,
        enabled: bool = True,
        sustain_enabled: bool | None = None,
        loop_enabled: bool | None = None,
        raw_type: int | None = None,
    ) -> None:
        inst = self.get_instrument(inst_idx)
        inst.set_volume_envelope(
            points,
            sustain=sustain,
            loop=loop,
            enabled=enabled,
            sustain_enabled=sustain_enabled,
            loop_enabled=loop_enabled,
            raw_type=raw_type,
        )
    def set_panning_envelope(
        self,
        inst_idx: int,
        points: list[EnvelopePoint | tuple[int, int]],
        sustain: int | None = None,
        loop: tuple[int, int] | None = None,
        enabled: bool = True,
        sustain_enabled: bool | None = None,
        loop_enabled: bool | None = None,
        raw_type: int | None = None,
    ) -> None:
        inst = self.get_instrument(inst_idx)
        inst.set_panning_envelope(
            points,
            sustain=sustain,
            loop=loop,
            enabled=enabled,
            sustain_enabled=sustain_enabled,
            loop_enabled=loop_enabled,
            raw_type=raw_type,
        )
    def clear_volume_envelope(self, inst_idx: int) -> None:
        inst = self.get_instrument(inst_idx)
        inst.set_volume_envelope([], enabled=False, sustain_enabled=False, loop_enabled=False)
    def clear_panning_envelope(self, inst_idx: int) -> None:
        inst = self.get_instrument(inst_idx)
        inst.set_panning_envelope([], enabled=False, sustain_enabled=False, loop_enabled=False)
    def set_sample_for_note(self, inst_idx: int, note: str | int, sample_idx: int) -> None:
        inst = self.get_instrument(inst_idx)
        inst.set_sample_for_note(note, sample_idx)
    def duplicate_instrument(self, inst_idx: int) -> int:
        return self.copy_instrument_from(self, inst_idx)
    def duplicate_sample(self, inst_idx: int, sample_idx: int) -> int:
        return self.copy_sample_from(self, inst_idx, sample_idx, inst_idx)
    def set_sample_name(self, inst_idx: int, sample_idx: int, name: str) -> None:
        smp = self.get_sample(inst_idx, sample_idx)
        smp.name = name
    def set_sample_volume(self, inst_idx: int, sample_idx: int, volume: int) -> None:
        if volume < 0 or volume > 64:
            raise ValueError(f"Invalid volume {volume} (expected 0-64).")
        smp = self.get_sample(inst_idx, sample_idx)
        smp.volume = volume
    def set_sample_finetune(self, inst_idx: int, sample_idx: int, finetune: int) -> None:
        if finetune < -128 or finetune > 127:
            raise ValueError(f"Invalid finetune {finetune} (expected -128 to 127).")
        smp = self.get_sample(inst_idx, sample_idx)
        smp.finetune = finetune
    def set_sample_panning(self, inst_idx: int, sample_idx: int, panning: int) -> None:
        if panning < 0 or panning > 255:
            raise ValueError(f"Invalid panning {panning} (expected 0-255).")
        smp = self.get_sample(inst_idx, sample_idx)
        smp.panning = panning
    def set_sample_relative_note(self, inst_idx: int, sample_idx: int, rel: int) -> None:
        if rel < -96 or rel > 95:
            raise ValueError(f"Invalid relative note {rel} (expected -96 to 95).")
        smp = self.get_sample(inst_idx, sample_idx)
        smp.relative_note = rel
    def set_instrument_name(self, inst_idx: int, name: str) -> None:
        inst = self.get_instrument(inst_idx)
        inst.name = name
    def set_instrument_fadeout(self, inst_idx: int, fadeout: int) -> None:
        if fadeout < 0 or fadeout > 65535:
            raise ValueError(f"Invalid fadeout {fadeout} (expected 0-65535).")
        inst = self.get_instrument(inst_idx)
        inst.volume_fadeout = fadeout
    def set_instrument_vibrato(self, inst_idx: int, vib_type: int, sweep: int, depth: int, rate: int) -> None:
        if vib_type < 0 or vib_type > 3:
            raise ValueError(f"Invalid vibrato type {vib_type} (expected 0-3).")
        if sweep < 0 or sweep > 255 or depth < 0 or depth > 255 or rate < 0 or rate > 255:
            raise ValueError("Invalid vibrato parameters (expected 0-255).")
        inst = self.get_instrument(inst_idx)
        inst.vibrato_type = vib_type
        inst.vibrato_sweep = sweep
        inst.vibrato_depth = depth
        inst.vibrato_rate = rate
    def set_sample_loop(
        self,
        inst_idx: int,
        sample_idx: int,
        start: int,
        length: int,
        loop_type: int,
    ) -> None:
        if loop_type not in (0, 1, 2):
            raise ValueError(f"Invalid loop_type {loop_type}. Expected 0, 1, or 2.")
        smp = self.get_sample(inst_idx, sample_idx)
        smp.repeat_point = max(0, start)
        smp.repeat_len = max(0, length)
        smp.loop_type = loop_type
    def validate_sample_loop(self, inst_idx: int, sample_idx: int) -> None:
        smp = self.get_sample(inst_idx, sample_idx)
        n = len(smp.waveform)
        if smp.loop_type == Sample.LOOP_NONE:
            return
        if smp.repeat_len <= 0:
            raise ValueError("Loop length must be >0 when loop_type is enabled.")
        if smp.repeat_point < 0:
            raise ValueError("Loop start cannot be negative.")
        if smp.repeat_point + smp.repeat_len > n:
            raise ValueError(f"Loop end {smp.repeat_point + smp.repeat_len} exceeds sample length {n}.")
    def validate_instrument(self, inst_idx: int) -> None:
        inst = self.get_instrument(inst_idx)
        inst.validate_envelopes()
        for sidx in range(1, len(inst.samples) + 1):
            self.validate_sample_loop(inst_idx, sidx)
    def remove_instrument(self, inst_idx: int) -> None:
        if inst_idx <= 0 or inst_idx > len(self.instruments):
            raise IndexError(f"Invalid instrument index {inst_idx} (expected 1-{len(self.instruments)}).")
        self.instruments[inst_idx - 1] = Instrument()
    def add_sample(self, inst_idx: int, sample: XMSample) -> int:
        inst = self.get_instrument(inst_idx)
        inst.samples.append(sample)
        if not inst.sample_map:
            inst.sample_map = [0] * 96
        return len(inst.samples)
    def get_sample(self, inst_idx: int, sample_idx: int) -> XMSample:
        inst = self.get_instrument(inst_idx)
        if sample_idx <= 0 or sample_idx > len(inst.samples):
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-{len(inst.samples)}).")
        return inst.samples[sample_idx - 1]
    def remove_sample(self, inst_idx: int, sample_idx: int) -> None:
        inst = self.get_instrument(inst_idx)
        if sample_idx <= 0 or sample_idx > len(inst.samples):
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-{len(inst.samples)}).")
        removed_idx = sample_idx - 1
        inst.samples.pop(removed_idx)
        if inst.sample_map:
            new_map: list[int] = []
            for v in inst.sample_map:
                if v == removed_idx:
                    new_map.append(0)
                elif v > removed_idx:
                    new_map.append(v - 1)
                else:
                    new_map.append(v)
            inst.sample_map = new_map
    def set_instrument_sample(self, inst_idx: int, sample: XMSample) -> None:
        inst = self.get_instrument(inst_idx)
        inst.samples = [sample]
        inst.sample_map = [0] * 96
    def get_instrument_sample(self, inst_idx: int) -> XMSample | None:
        inst = self.get_instrument(inst_idx)
        if len(inst.samples) != 1:
            return None
        return inst.samples[0]
    def load_sample(self, inst_idx: int, fname: str) -> int:
        inst = self.get_instrument(inst_idx)
        pydub = _require_pydub()
        audio = pydub.AudioSegment.from_wav(fname).set_channels(1)
        sample = XMSample()
        sample.waveform = audio.get_array_of_samples()
        sample.is_16bit = audio.sample_width == 2
        inst.samples.append(sample)
        if not inst.sample_map:
            inst.sample_map = [0] * 96
        return len(inst.samples)
    def load_sample_from_raw(
        self,
        inst_idx: int,
        raw_bytes: bytes | bytearray | list[float] | tuple[float, ...],
        sample_width: int,
    ) -> int:
        if sample_width not in (1, 2):
            raise ValueError(f"Invalid sample_width {sample_width}. XM supports 1 (8-bit) or 2 (16-bit).")
        inst = self.get_instrument(inst_idx)
        sample = XMSample()
        if isinstance(raw_bytes, (list, tuple)):
            if sample_width == 1:
                sample.waveform = array.array('b')
                for s in raw_bytes:
                    if s > 1.0:
                        s = 1.0
                    elif s < -1.0:
                        s = -1.0
                    sample.waveform.append(int(s * 127))
                sample.is_16bit = False
            else:
                sample.waveform = array.array('h')
                for s in raw_bytes:
                    if s > 1.0:
                        s = 1.0
                    elif s < -1.0:
                        s = -1.0
                    sample.waveform.append(int(s * 32767))
                sample.is_16bit = True
        else:
            if sample_width == 1:
                sample.waveform = array.array('b')
                sample.waveform.frombytes(raw_bytes)
                sample.is_16bit = False
            else:
                sample.waveform = array.array('h')
                sample.waveform.frombytes(raw_bytes)
                sample.is_16bit = True
        inst.samples.append(sample)
        if not inst.sample_map:
            inst.sample_map = [0] * 96
        return len(inst.samples)
    def set_sample_map_range(
        self,
        inst_idx: int,
        sample_idx: int,
        note_low: str | int,
        note_high: str | int,
    ) -> None:
        low_idx = self._note_str_to_idx(note_low)
        high_idx = self._note_str_to_idx(note_high)
        if low_idx < 0 or high_idx > 95 or low_idx > high_idx:
            raise ValueError(f"Invalid note range {note_low}-{note_high} (expected 0-95 and low<=high).")
        inst = self.get_instrument(inst_idx)
        if sample_idx < 1 or sample_idx > len(inst.samples):
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-{len(inst.samples)}).")
        if not inst.sample_map or len(inst.sample_map) != 96:
            inst.sample_map = [0] * 96
        for note in range(low_idx, high_idx + 1):
            inst.sample_map[note] = sample_idx - 1
    def set_sample_map_all(self, inst_idx: int, sample_idx: int) -> None:
        self.set_sample_map_range(inst_idx, sample_idx, 0, 95)
    def copy_sample_from(
        self,
        src: 'XMSong',
        src_inst_idx: int,
        src_sample_idx: int,
        dst_inst_idx: int,
    ) -> int:
        src_inst = src.get_instrument(src_inst_idx)
        if src_sample_idx < 1 or src_sample_idx > len(src_inst.samples):
            raise IndexError(f"Invalid sample index {src_sample_idx} (expected 1-{len(src_inst.samples)}).")
        smp = src_inst.samples[src_sample_idx - 1]
        new_smp = XMSample()
        new_smp.name = smp.name
        new_smp.volume = smp.volume
        new_smp.finetune = smp.finetune
        new_smp.panning = smp.panning
        new_smp.relative_note = smp.relative_note
        new_smp._reserved = smp._reserved
        new_smp.loop_type = smp.loop_type
        new_smp.is_16bit = smp.is_16bit
        new_smp.repeat_point = smp.repeat_point
        new_smp.repeat_len = smp.repeat_len
        new_smp.waveform = smp.waveform.__class__(smp.waveform.typecode, smp.waveform)
        return self.add_sample(dst_inst_idx, new_smp)
    def copy_samples_from(
        self,
        src: 'XMSong',
        src_inst_idx: int,
        src_sample_indices: list[int],
        dst_inst_idx: int,
    ) -> list[int]:
        new_indices: list[int] = []
        for s_idx in src_sample_indices:
            new_indices.append(self.copy_sample_from(src, src_inst_idx, s_idx, dst_inst_idx))
        return new_indices
    def copy_instrument_from(self, src: 'XMSong', inst_idx: int) -> int:
        inst = src.get_instrument(inst_idx)
        new_idx = self.new_instrument(inst.name)
        new_inst = self.get_instrument(new_idx)
        new_inst._type = inst._type
        new_inst._header_size = inst._header_size
        new_inst.set_volume_envelope(
            [(p.frame, p.value) for p in inst.volume_envelope],
            sustain=inst.volume_sustain_point,
            loop=(inst.volume_loop_start, inst.volume_loop_end),
            enabled=(inst.volume_type & 0x01) != 0,
            sustain_enabled=(inst.volume_type & 0x02) != 0,
            loop_enabled=(inst.volume_type & 0x04) != 0,
            raw_type=inst.volume_type,
        )
        new_inst.set_panning_envelope(
            [(p.frame, p.value) for p in inst.panning_envelope],
            sustain=inst.panning_sustain_point,
            loop=(inst.panning_loop_start, inst.panning_loop_end),
            enabled=(inst.panning_type & 0x01) != 0,
            sustain_enabled=(inst.panning_type & 0x02) != 0,
            loop_enabled=(inst.panning_type & 0x04) != 0,
            raw_type=inst.panning_type,
        )
        new_inst.vibrato_type = inst.vibrato_type
        new_inst.vibrato_sweep = inst.vibrato_sweep
        new_inst.vibrato_depth = inst.vibrato_depth
        new_inst.vibrato_rate = inst.vibrato_rate
        new_inst.volume_fadeout = inst.volume_fadeout
        for smp in inst.samples:
            new_smp = XMSample()
            new_smp.name = smp.name
            new_smp.volume = smp.volume
            new_smp.finetune = smp.finetune
            new_smp.panning = smp.panning
            new_smp.relative_note = smp.relative_note
            new_smp._reserved = smp._reserved
            new_smp.loop_type = smp.loop_type
            new_smp.is_16bit = smp.is_16bit
            new_smp.repeat_point = smp.repeat_point
            new_smp.repeat_len = smp.repeat_len
            new_smp.waveform = smp.waveform.__class__(smp.waveform.typecode, smp.waveform)
            self.add_sample(new_idx, new_smp)
        if inst.samples:
            map_1based = [v + 1 for v in inst.sample_map[:96]]
            new_inst.set_sample_map(map_1based)
        return new_idx
    def copy_instruments_from(self, src: 'XMSong', inst_indices: list[int]) -> dict[int, int]:
        mapping: dict[int, int] = {}
        for idx in inst_indices:
            mapping[idx] = self.copy_instrument_from(src, idx)
        return mapping
    def get_used_instruments(
        self,
        *,
        scope: str = "sequence",
        order: str = "sorted",
    ) -> list[int]:
        self._validate_used_resource_args(scope, order)
        seen: set[int] = set()
        first_use: list[int] = []
        for note in self._iter_notes_by_scope(scope):
            inst_idx = getattr(note, 'instrument_idx', 0)
            if inst_idx > 0 and inst_idx not in seen:
                seen.add(inst_idx)
                first_use.append(inst_idx)
        return self._finalize_used_values(first_use, order)
    def get_used_samples(
        self,
        *,
        scope: str = "sequence",
        order: str = "sorted",
    ) -> list[int]:
        self._validate_used_resource_args(scope, order)
        flat_by_instrument: dict[int, list[int]] = {}
        flat_idx = 1
        for inst_idx, inst in enumerate(self.instruments, start=1):
            inst_flat = list(range(flat_idx, flat_idx + len(inst.samples)))
            flat_by_instrument[inst_idx] = inst_flat
            flat_idx += len(inst.samples)
        seen: set[int] = set()
        first_use: list[int] = []
        def _record(flat_sample_idx: int) -> None:
            if flat_sample_idx not in seen:
                seen.add(flat_sample_idx)
                first_use.append(flat_sample_idx)
        for note in self._iter_notes_by_scope(scope):
            inst_idx = getattr(note, 'instrument_idx', 0)
            if inst_idx <= 0 or inst_idx > len(self.instruments):
                continue
            inst = self.instruments[inst_idx - 1]
            inst_flat = flat_by_instrument.get(inst_idx, [])
            if not inst_flat:
                continue
            if len(inst_flat) == 1:
                _record(inst_flat[0])
                continue
            mapped_flat = None
            period = getattr(note, 'period', '')
            if period not in {'', 'off'} and len(inst.sample_map) == 96:
                try:
                    note_idx = Song.note_to_index(period)
                except (TypeError, ValueError):
                    note_idx = None
                if note_idx is not None:
                    mapped_local = inst.sample_map[note_idx]
                    if 0 <= mapped_local < len(inst_flat):
                        mapped_flat = inst_flat[mapped_local]
            if mapped_flat is not None:
                _record(mapped_flat)
                continue
            for candidate in inst_flat:
                _record(candidate)
        return self._finalize_used_values(first_use, order)
