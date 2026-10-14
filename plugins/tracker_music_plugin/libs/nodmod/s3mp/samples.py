# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import copy
import array
import os
import struct
import sys
from nodmod import Pattern
from nodmod import S3MNote
from nodmod import S3MSample
from nodmod import Song
from nodmod.views import PlaybackRowView

class S3MSongSamplesMixin:
    def copy_sample_from(self, src: 'S3MSong', src_sample_idx: int, dst_sample_idx: int | None = None) -> int:
        if src_sample_idx <= 0 or src_sample_idx > src.MAX_SAMPLES:
            raise IndexError(f"Invalid source sample index {src_sample_idx} (expected 1-{src.MAX_SAMPLES}).")
        if dst_sample_idx is not None and (dst_sample_idx <= 0 or dst_sample_idx > self.MAX_SAMPLES):
            raise IndexError(f"Invalid destination sample index {dst_sample_idx} (expected 1-{self.MAX_SAMPLES}).")
        if dst_sample_idx is None:
            for idx, sample in enumerate(self.samples, start=1):
                if len(sample.waveform) == 0:
                    dst_sample_idx = idx
                    break
            if dst_sample_idx is None:
                raise ValueError("Couldn't find an empty slot for the new sample.")
        self.samples[dst_sample_idx - 1] = copy.deepcopy(src.get_sample(src_sample_idx))
        self._update_n_actual_samples()
        return dst_sample_idx

    def set_n_channels(self, n: int) -> None:
        self.n_channels = n

    def get_sample(self, sample_idx: int) -> S3MSample:
        if sample_idx <= 0 or sample_idx > self.MAX_SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-{self.MAX_SAMPLES}).")
        return self.samples[sample_idx - 1]

    def list_samples(self) -> list[S3MSample]:
        return self.samples

    def set_sample(self, sample_idx: int, sample: S3MSample) -> None:
        if sample_idx <= 0 or sample_idx > self.MAX_SAMPLES:
            raise IndexError(f"Invalid sample index {sample_idx} (expected 1-{self.MAX_SAMPLES}).")
        self.samples[sample_idx - 1] = sample
        self._update_n_actual_samples()

    def _load_pcm_instruments(self, data: bytes, fname: str) -> None:
        self.samples = [S3MSample() for _ in range(self.MAX_SAMPLES)]
        for inst_idx, inst_offset in enumerate(self.instrument_offsets, start=1):
            if inst_offset + 80 > len(data):
                raise NotImplementedError(
                    f"Invalid S3M instrument pointer for instrument {inst_idx} in {os.path.basename(fname)}."
                )
            inst = data[inst_offset:inst_offset + 80]
            inst_type = inst[0]
            sample = S3MSample()
            sample.instrument_type = inst_type
            sample.filename = self._decode_text(inst[1:13])
            sample.name = self._decode_text(inst[48:76])
            sample._signature = inst[76:80].decode('latin-1', errors='replace')
            if inst_type == 0:
                self.samples[inst_idx - 1] = sample
                continue
            if 2 <= inst_type <= 7:
                raise NotImplementedError(
                    f"Adlib S3M instruments are not supported yet (instrument {inst_idx} in {os.path.basename(fname)})."
                )
            if inst_type != 1:
                raise NotImplementedError(
                    f"Unsupported S3M instrument type {inst_type} at instrument {inst_idx}."
                )
            para = (inst[13] << 16) | struct.unpack_from('<H', inst, 14)[0]
            sample.sample_offset = para << 4
            length_units = struct.unpack_from('<I', inst, 16)[0]
            loop_start = struct.unpack_from('<I', inst, 20)[0]
            loop_end = struct.unpack_from('<I', inst, 24)[0]
            sample.volume = inst[28]
            sample._reserved_byte = inst[29]
            sample.pack = inst[30]
            sample.flags = inst[31]
            sample.is_stereo = bool(sample.flags & 0x02)
            sample.is_16bit = bool(sample.flags & 0x04)
            sample.c2spd = struct.unpack_from('<I', inst, 32)[0]
            sample._internal = bytes(inst[36:48])
            if sample.pack != 0:
                raise NotImplementedError(
                    f"Packed S3M samples are not supported yet (instrument {inst_idx} in {os.path.basename(fname)})."
                )
            if sample.is_stereo:
                raise NotImplementedError(
                    f"Stereo S3M samples are not supported yet (instrument {inst_idx} in {os.path.basename(fname)})."
                )
            byte_length = length_units * (2 if sample.is_16bit else 1)
            sample.waveform = self._decode_sample_waveform(data, sample.sample_offset, byte_length, sample.is_16bit)
            sample.repeat_point = loop_start
            if sample.flags & 0x01 and loop_end > loop_start:
                sample.repeat_len = loop_end - loop_start
            else:
                sample.repeat_len = 0
            self.samples[inst_idx - 1] = sample
        self._update_n_actual_samples()

    def _decode_sample_waveform(self, data: bytes, offset: int, byte_length: int, is_16bit: bool):
        if offset == 0 or byte_length == 0:
            return array.array('h' if is_16bit else 'b')
        if offset + byte_length > len(data):
            raise NotImplementedError("Invalid S3M sample data pointer (truncated sample data).")
        raw = data[offset:offset + byte_length]
        if is_16bit:
            if byte_length % 2 != 0:
                raise NotImplementedError("Invalid S3M 16-bit sample length.")
            if self.sample_type == 1:
                waveform = array.array('h')
                waveform.frombytes(raw)
                if sys.byteorder != 'little':
                    waveform.byteswap()
                return waveform
            unsigned_waveform = array.array('H')
            unsigned_waveform.frombytes(raw)
            if sys.byteorder != 'little':
                unsigned_waveform.byteswap()
            return array.array('h', (value - 32768 for value in unsigned_waveform))
        if self.sample_type == 1:
            waveform = array.array('b')
            waveform.frombytes(raw)
            return waveform
        unsigned_waveform = array.array('B')
        unsigned_waveform.frombytes(raw)
        return array.array('b', (value - 128 for value in unsigned_waveform))

    def _load_patterns(self, data: bytes, fname: str) -> None:
        self.patterns = [self._new_pattern() for _ in range(self.pattern_count)]
        for pat_idx, pat_offset in enumerate(self.pattern_offsets):
            if pat_offset == 0:
                continue
            if pat_offset + 2 > len(data):
                raise NotImplementedError(
                    f"Invalid S3M pattern pointer for pattern {pat_idx} in {os.path.basename(fname)}."
                )
            packed_len = struct.unpack_from('<H', data, pat_offset)[0]
            if packed_len < 2 or pat_offset + packed_len > len(data):
                raise NotImplementedError(
                    f"Invalid S3M packed pattern length for pattern {pat_idx} in {os.path.basename(fname)}."
                )
            packed_data = data[pat_offset + 2:pat_offset + packed_len]
            self._decode_pattern_data(self.patterns[pat_idx], packed_data)

    def _decode_pattern_data(self, pat: Pattern, packed_data: bytes) -> None:
        row = 0
        pos = 0
        while row < self.ROWS and pos < len(packed_data):
            what = packed_data[pos]
            pos += 1
            if what == 0:
                row += 1
                continue
            raw_channel = what & 0x1F
            note_value = None
            instrument_idx = 0
            volume = -1
            effect = ''
            if what & 0x20:
                if pos + 2 > len(packed_data):
                    return
                note_value = packed_data[pos]
                instrument_idx = packed_data[pos + 1]
                pos += 2
            if what & 0x40:
                if pos >= len(packed_data):
                    return
                raw_volume = packed_data[pos]
                volume = raw_volume if raw_volume <= 64 else -1
                pos += 1
            if what & 0x80:
                if pos + 2 > len(packed_data):
                    return
                command = packed_data[pos]
                info = packed_data[pos + 1]
                pos += 2
                if command != 0:
                    effect = f"{chr(ord('A') + command - 1)}{info:02X}"
            compact_channel = self.raw_to_compact_channel.get(raw_channel)
            if compact_channel is None:
                continue
            note = S3MNote()
            note.instrument_idx = instrument_idx
            note.volume = volume
            note.effect = effect
            if note_value is not None:
                note.period = self._decode_note_value(note_value)
            pat.data[compact_channel][row] = note

    @staticmethod
    def _align16(payload: bytearray) -> None:
        remainder = len(payload) % 16
        if remainder:
            payload.extend(b'\x00' * (16 - remainder))

    def _build_order_list_for_save(self) -> list[int]:
        raw = list(self.order_list_raw)
        if raw and self._normalized_order_list(raw) == self.pattern_seq:
            return raw
        order_list = list(self.pattern_seq)
        if not order_list or order_list[-1] != 0xFF:
            order_list.append(0xFF)
        if len(order_list) > 256:
            raise ValueError(f"Pattern sequence too long ({len(order_list)}). S3M supports up to 256 orders.")
        return order_list

    def _instrument_count_for_save(self) -> int:
        highest_non_empty = 0
        for idx, sample in enumerate(self.samples, start=1):
            if self._sample_slot_used(sample):
                highest_non_empty = idx
        return max(self.instrument_count, highest_non_empty)

    @staticmethod
    def _normalized_order_list(order_list: list[int]) -> list[int]:
        normalized: list[int] = []
        for order in order_list:
            if order == 0xFF:
                break
            if order == 0xFE:
                continue
            normalized.append(order)
        return normalized

    @staticmethod
    def _encode_text(text: str, length: int) -> bytes:
        raw = text.encode('latin-1', errors='replace')[:length]
        return raw.ljust(length, b'\x00')

    def _sample_slot_used(self, sample: S3MSample) -> bool:
        return (
            sample.instrument_type != 0
            or len(sample.waveform) > 0
            or sample.name != ''
            or sample.filename != ''
        )

    def _validate_sample_for_save(self, sample: S3MSample, sample_idx: int) -> None:
        if getattr(sample, 'instrument_type', 0) in {2, 3, 4, 5, 6, 7}:
            raise NotImplementedError(f"Adlib S3M instruments are not supported yet (sample {sample_idx}).")
        if sample.pack != 0:
            raise NotImplementedError(f"Packed S3M samples are not supported yet (sample {sample_idx}).")
        if sample.is_stereo:
            raise NotImplementedError(f"Stereo S3M samples are not supported yet (sample {sample_idx}).")

    def _build_instrument_header(self, sample: S3MSample, sample_paragraph: int) -> bytes:
        header = bytearray(80)
        instrument_type = 1 if self._sample_slot_used(sample) and (sample.instrument_type == 1 or len(sample.waveform) > 0) else 0
        if sample.instrument_type in {2, 3, 4, 5, 6, 7}:
            instrument_type = sample.instrument_type
        header[0] = instrument_type
        header[1:13] = self._encode_text(sample.filename, 12)
        if instrument_type == 1:
            header[13] = (sample_paragraph >> 16) & 0xFF
            struct.pack_into('<H', header, 14, sample_paragraph & 0xFFFF)
            struct.pack_into('<I', header, 16, len(sample.waveform))
            loop_start = sample.repeat_point
            loop_end = sample.repeat_point + sample.repeat_len
            struct.pack_into('<I', header, 20, loop_start)
            struct.pack_into('<I', header, 24, loop_end)
            header[28] = max(0, min(64, sample.volume))
            header[29] = getattr(sample, '_reserved_byte', 0)
            header[30] = sample.pack
            flags = sample.flags & ~0x07
            if sample.repeat_len > 0:
                flags |= 0x01
            if sample.is_stereo:
                flags |= 0x02
            if sample.is_16bit:
                flags |= 0x04
            header[31] = flags
            struct.pack_into('<I', header, 32, sample.c2spd or 8363)
            header[36:48] = getattr(sample, '_internal', b'\x00' * 12)[:12].ljust(12, b'\x00')
            header[76:80] = getattr(sample, '_signature', 'SCRS').encode('latin-1', errors='replace')[:4].ljust(4, b'\x00')
        else:
            header[76:80] = getattr(sample, '_signature', 'SCRS').encode('latin-1', errors='replace')[:4].ljust(4, b'\x00')
        header[48:76] = self._encode_text(sample.name, 28)
        return bytes(header)

    def _sample_byte_length(self, sample: S3MSample) -> int:
        unit_size = 2 if sample.is_16bit else 1
        return len(sample.waveform) * unit_size

    def _encode_sample_data(self, sample: S3MSample) -> bytes:
        if len(sample.waveform) == 0:
            return b''
        if sample.is_16bit:
            if self.sample_type == 1:
                waveform = array.array('h', (int(value) for value in sample.waveform))
                if sys.byteorder != 'little':
                    waveform.byteswap()
                return waveform.tobytes()
            unsigned_waveform = array.array('H', (max(0, min(65535, int(value) + 32768)) for value in sample.waveform))
            if sys.byteorder != 'little':
                unsigned_waveform.byteswap()
            return unsigned_waveform.tobytes()
        if self.sample_type == 1:
            waveform = array.array('b', (max(-128, min(127, int(value))) for value in sample.waveform))
            return waveform.tobytes()
        unsigned_waveform = array.array('B', (max(0, min(255, int(value) + 128)) for value in sample.waveform))
        return unsigned_waveform.tobytes()

    def _encode_pattern_block(self, pat: Pattern) -> bytes:
        packed_data = bytearray()
        for row in range(pat.n_rows):
            for channel in range(pat.n_channels):
                note = pat.data[channel][row]
                raw_channel = self.compact_to_raw_channel[channel]
                have_note_inst = note.period != '' or note.instrument_idx != 0
                have_volume = 0 <= getattr(note, 'volume', -1) <= 64
                have_effect = self._effect_text(note.effect) != ''
                if not have_note_inst and not have_volume and not have_effect:
                    continue
                what = raw_channel
                if have_note_inst:
                    what |= 0x20
                if have_volume:
                    what |= 0x40
                if have_effect:
                    what |= 0x80
                packed_data.append(what)
                if have_note_inst:
                    packed_data.append(self._encode_note_value(note.period))
                    packed_data.append(note.instrument_idx)
                if have_volume:
                    packed_data.append(note.volume)
                if have_effect:
                    command, info = self._encode_effect(note.effect)
                    packed_data.append(command)
                    packed_data.append(info)
            packed_data.append(0)
        return struct.pack('<H', len(packed_data) + 2) + packed_data

    @staticmethod
    def _encode_note_value(period: str) -> int:
        period = period.strip().upper()
        if period == '':
            return 255
        if period == 'OFF':
            return 254
        if len(period) != 3 or period[1] not in {'-', '#'}:
            raise ValueError(f"Invalid S3M note format {period!r}.")
        pitch = period[:2]
        octave = int(period[2])
        if octave < 0 or octave > 15:
            raise ValueError(f"Invalid S3M note octave {period!r}.")
        semitone = Song.PERIOD_SEQ.index(pitch)
        return (octave << 4) | semitone

    @staticmethod
    def _encode_effect(effect: str) -> tuple[int, int]:
        effect = effect.strip().upper()
        if effect == '':
            return 0, 0
        if len(effect) != 3:
            raise ValueError(f"Invalid S3M effect format {effect!r}.")
        command = ord(effect[0]) - ord('A') + 1
        if command < 1 or command > 26:
            raise ValueError(f"Invalid S3M effect command {effect!r}.")
        return command, int(effect[1:], 16)

    @staticmethod
    def _decode_note_value(note_value: int) -> str:
        if note_value == 255:
            return ''
        if note_value == 254:
            return 'off'
        semitone = note_value & 0x0F
        octave = (note_value >> 4) & 0x0F
        if semitone > 11:
            raise NotImplementedError(f"Unsupported S3M note value {note_value}.")
        return f"{Song.PERIOD_SEQ[semitone]}{octave}"

    @staticmethod
    def _decode_text(raw: bytes) -> str:
        return raw.split(b'\x00', 1)[0].decode('latin-1', errors='replace').rstrip(' ')

    def _preserved_effect(self, effect: str) -> str:
        effect = self._effect_text(effect)
        if effect == '':
            return ''
        if effect[0] in {'A', 'B', 'C', 'T'}:
            return effect
        if effect.startswith('SB') or effect.startswith('SE'):
            return effect
        return ''
