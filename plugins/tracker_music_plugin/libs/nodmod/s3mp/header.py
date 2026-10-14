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

class S3MSongHeaderMixin:
    ROWS = 64

    MAX_CHANNELS = 32

    MAX_SAMPLES = 99

    PRESERVED_EFFECT_PREFIXES = frozenset({'A', 'B', 'C', 'T'})

    @property
    def file_extension(self) -> str:
        return 's3m'

    @property
    def n_channels(self) -> int:
        return self._n_channels

    @n_channels.setter
    def n_channels(self, n: int) -> None:
        if n < 1 or n > self.MAX_CHANNELS:
            raise ValueError(f"Invalid channel count {n} (expected 1-{self.MAX_CHANNELS}).")
        self._n_channels = n
        self.channel_settings = self._default_channel_settings(n)
        self._rebuild_channel_mappings()
        for pat in self.patterns:
            self._resize_pattern_channels(pat, n)

    def __init__(self):
        super().__init__()
        self.sig1 = 0x1A
        self.song_type = 0x10
        self.tracker_version = 0x1320
        self.flags = 0
        self.global_volume = 64
        self.initial_speed = 6
        self.initial_tempo = 125
        self.master_volume = 0xB0
        self.ultra_click_removal = 0
        self.sample_type = 2
        self.default_pan_flag = 0
        self.special = 0
        self.reserved1 = 0
        self.reserved2 = b'\x00' * 8
        self.default_panning: list[int] = []
        self.order_count = 0
        self.instrument_count = 0
        self.pattern_count = 0
        self.order_list_raw: list[int] = []
        self.instrument_parapointers: list[int] = []
        self.pattern_parapointers: list[int] = []
        self.instrument_offsets: list[int] = []
        self.pattern_offsets: list[int] = []
        self.samples: list[S3MSample] = [S3MSample() for _ in range(self.MAX_SAMPLES)]
        self.n_actual_samples = 0
        self._n_channels = 0
        self.channel_settings: list[int] = []
        self.raw_channel_slots: list[int] = []
        self.compact_to_raw_channel: list[int] = []
        self.raw_to_compact_channel: dict[int, int] = {}
        self.n_channels = 16
        self.add_pattern()

    def _default_channel_settings(self, n_channels: int) -> list[int]:
        default_active = [0, 8, 1, 9, 2, 10, 3, 11, 4, 12, 5, 13, 6, 14, 7, 15]
        settings = default_active[:n_channels]
        while len(settings) < n_channels:
            settings.append(len(settings) & 0x0F)
        return settings + [255] * (self.MAX_CHANNELS - n_channels)

    def _default_channel_setting_for_index(self, compact_index: int) -> int:
        return self._default_channel_settings(compact_index + 1)[compact_index]

    def _rebuild_channel_mappings(self) -> None:
        self.raw_channel_slots = [idx for idx, value in enumerate(self.channel_settings) if value != 255]
        self.compact_to_raw_channel = list(self.raw_channel_slots)
        self.raw_to_compact_channel = {raw: compact for compact, raw in enumerate(self.compact_to_raw_channel)}
        self._n_channels = len(self.compact_to_raw_channel)

    def _new_pattern(self) -> Pattern:
        pat = Pattern(self.ROWS, self.n_channels)
        pat.data = [[S3MNote() for _ in range(pat.n_rows)] for _ in range(pat.n_channels)]
        return pat

    def _resize_pattern_channels(self, pat: Pattern, n_channels: int) -> None:
        if pat.n_channels < n_channels:
            for _ in range(n_channels - pat.n_channels):
                pat.data.append([S3MNote() for _ in range(pat.n_rows)])
        elif pat.n_channels > n_channels:
            pat.data = pat.data[:n_channels]
        pat.n_channels = n_channels

    def _update_n_actual_samples(self) -> None:
        self.n_actual_samples = sum(1 for sample in self.samples if len(sample.waveform) > 0)

    def copy(self) -> 'S3MSong':
        from .component import S3MSong
        new_song = S3MSong()
        new_song.artist = self.artist
        new_song.songname = self.songname
        new_song.patterns = copy.deepcopy(self.patterns)
        new_song.pattern_seq = copy.deepcopy(self.pattern_seq)
        new_song.samples = copy.deepcopy(self.samples)
        new_song.n_actual_samples = self.n_actual_samples
        new_song.sig1 = self.sig1
        new_song.song_type = self.song_type
        new_song.tracker_version = self.tracker_version
        new_song.flags = self.flags
        new_song.global_volume = self.global_volume
        new_song.initial_speed = self.initial_speed
        new_song.initial_tempo = self.initial_tempo
        new_song.master_volume = self.master_volume
        new_song.ultra_click_removal = self.ultra_click_removal
        new_song.sample_type = self.sample_type
        new_song.default_pan_flag = self.default_pan_flag
        new_song.special = self.special
        new_song.reserved1 = self.reserved1
        new_song.reserved2 = self.reserved2
        new_song.default_panning = copy.deepcopy(self.default_panning)
        new_song.order_count = self.order_count
        new_song.instrument_count = self.instrument_count
        new_song.pattern_count = self.pattern_count
        new_song.order_list_raw = list(self.order_list_raw)
        new_song.instrument_parapointers = list(self.instrument_parapointers)
        new_song.pattern_parapointers = list(self.pattern_parapointers)
        new_song.instrument_offsets = list(self.instrument_offsets)
        new_song.pattern_offsets = list(self.pattern_offsets)
        new_song.channel_settings = list(self.channel_settings)
        new_song._rebuild_channel_mappings()
        return new_song

    def save(self, fname: str, verbose: bool = True):
        if verbose:
            print(f'Saving to {fname}... ', end='', flush=True)
        order_list = self._build_order_list_for_save()
        instrument_count = self._instrument_count_for_save()
        pattern_count = len(self.patterns)
        has_panning = len(self.default_panning) == 32 and self.default_pan_flag == 252
        default_pan_flag = 252 if has_panning else 0
        header_size = 96 + len(order_list) + 2 * instrument_count + 2 * pattern_count + (32 if has_panning else 0)
        payload = bytearray(header_size)
        order_offset = 96
        instrument_ptr_offset = order_offset + len(order_list)
        pattern_ptr_offset = instrument_ptr_offset + 2 * instrument_count
        panning_offset = pattern_ptr_offset + 2 * pattern_count
        payload[order_offset:order_offset + len(order_list)] = bytes(order_list)
        if has_panning:
            payload[panning_offset:panning_offset + 32] = bytes(self.default_panning)
        self._align16(payload)
        instrument_parapointers: list[int] = []
        pattern_parapointers: list[int] = []
        instrument_header_positions: list[int] = []
        for sample_idx in range(1, instrument_count + 1):
            instrument_parapointers.append(len(payload) >> 4)
            instrument_header_positions.append(len(payload))
            payload.extend(b'\x00' * 80)
        for pat in self.patterns:
            self._align16(payload)
            pattern_parapointers.append(len(payload) >> 4)
            payload.extend(self._encode_pattern_block(pat))
        sample_paragraphs: dict[int, int] = {}
        for sample_idx in range(1, instrument_count + 1):
            sample = self.samples[sample_idx - 1]
            self._validate_sample_for_save(sample, sample_idx)
            sample_bytes = self._encode_sample_data(sample)
            if sample_bytes:
                self._align16(payload)
                sample_paragraphs[sample_idx] = len(payload) >> 4
                payload.extend(sample_bytes)
            else:
                sample_paragraphs[sample_idx] = 0
        for sample_idx in range(1, instrument_count + 1):
            sample = self.samples[sample_idx - 1]
            header = self._build_instrument_header(sample, sample_paragraphs[sample_idx])
            pos = instrument_header_positions[sample_idx - 1]
            payload[pos:pos + 80] = header
        payload[0:28] = self._encode_text(self.songname, 28)
        payload[28] = self.sig1
        payload[29] = self.song_type
        struct.pack_into('<H', payload, 30, self.reserved1)
        struct.pack_into(
            '<6H',
            payload,
            32,
            len(order_list),
            instrument_count,
            pattern_count,
            self.flags,
            self.tracker_version,
            self.sample_type,
        )
        payload[44:48] = b'SCRM'
        payload[48] = self.global_volume
        payload[49] = self.initial_speed
        payload[50] = self.initial_tempo
        payload[51] = self.master_volume
        payload[52] = self.ultra_click_removal
        payload[53] = default_pan_flag
        payload[54:62] = self.reserved2[:8].ljust(8, b'\x00')
        struct.pack_into('<H', payload, 62, self.special)
        payload[64:96] = bytes(self.channel_settings[:32])
        if instrument_count:
            struct.pack_into(
                '<' + 'H' * instrument_count,
                payload,
                instrument_ptr_offset,
                *instrument_parapointers,
            )
        if pattern_count:
            struct.pack_into(
                '<' + 'H' * pattern_count,
                payload,
                pattern_ptr_offset,
                *pattern_parapointers,
            )
        with open(fname, 'wb') as s3m_file:
            s3m_file.write(payload)
        self.order_count = len(order_list)
        self.instrument_count = instrument_count
        self.pattern_count = pattern_count
        self.order_list_raw = list(order_list)
        self.instrument_parapointers = instrument_parapointers
        self.pattern_parapointers = pattern_parapointers
        self.instrument_offsets = [ptr << 4 for ptr in instrument_parapointers]
        self.pattern_offsets = [ptr << 4 for ptr in pattern_parapointers]
        self.default_pan_flag = default_pan_flag
        if verbose:
            print('done.')

    def load(self, fname: str, verbose: bool = True):
        if verbose:
            print(f'Loading {fname}... ', end='', flush=True)
        with open(fname, 'rb') as s3m_file:
            data = s3m_file.read()
        if len(data) < 96:
            raise NotImplementedError("Invalid S3M file format (header too short).")
        self.artist = "Unknown Artist"
        self.songname = self._decode_text(data[:28])
        self.sig1 = data[28]
        self.song_type = data[29]
        if self.sig1 != 0x1A or self.song_type != 0x10:
            raise NotImplementedError(
                f"Not an S3M module. Signature/type mismatch: sig1={self.sig1:#04x}, type={self.song_type:#04x}."
            )
        self.reserved1 = struct.unpack_from('<H', data, 30)[0]
        (
            self.order_count,
            self.instrument_count,
            self.pattern_count,
            self.flags,
            self.tracker_version,
            self.sample_type,
        ) = struct.unpack_from('<6H', data, 32)
        if data[44:48] != b'SCRM':
            raise NotImplementedError(f"Not an S3M module. Missing SCRM signature: {data[44:48]!r}.")
        if self.sample_type not in (1, 2):
            raise NotImplementedError(f"Unsupported S3M sample type {self.sample_type}.")
        if self.instrument_count > self.MAX_SAMPLES:
            raise NotImplementedError(
                f"Too many instruments: {self.instrument_count} (S3M support currently expects <= {self.MAX_SAMPLES})."
            )
        self.global_volume = data[48]
        self.initial_speed = data[49] or self.initial_speed
        tempo = data[50]
        if tempo >= 33:
            self.initial_tempo = tempo
        self.master_volume = data[51]
        self.ultra_click_removal = data[52]
        self.default_pan_flag = data[53]
        self.reserved2 = bytes(data[54:62])
        self.special = struct.unpack_from('<H', data, 62)[0]
        self.channel_settings = list(data[64:96])
        self._rebuild_channel_mappings()
        offset = 96
        tables_size = self.order_count + 2 * self.instrument_count + 2 * self.pattern_count
        if len(data) < offset + tables_size:
            raise NotImplementedError("Invalid S3M file format (truncated order/parapointer tables).")
        self.order_list_raw = list(data[offset:offset + self.order_count])
        offset += self.order_count
        if self.instrument_count:
            fmt = '<' + 'H' * self.instrument_count
            self.instrument_parapointers = list(struct.unpack_from(fmt, data, offset))
        else:
            self.instrument_parapointers = []
        offset += 2 * self.instrument_count
        if self.pattern_count:
            fmt = '<' + 'H' * self.pattern_count
            self.pattern_parapointers = list(struct.unpack_from(fmt, data, offset))
        else:
            self.pattern_parapointers = []
        offset += 2 * self.pattern_count
        self.instrument_offsets = [ptr << 4 for ptr in self.instrument_parapointers]
        self.pattern_offsets = [ptr << 4 for ptr in self.pattern_parapointers]
        highest_order = max((order for order in self.order_list_raw if order not in {0xFE, 0xFF}), default=-1)
        if highest_order >= self.pattern_count:
            missing = highest_order + 1 - self.pattern_count
            self.pattern_parapointers.extend([0] * missing)
            self.pattern_offsets.extend([0] * missing)
            self.pattern_count = highest_order + 1
        self.default_panning = []
        if self.default_pan_flag == 252:
            if len(data) < offset + 32:
                raise NotImplementedError("Invalid S3M file format (missing default panning table).")
            self.default_panning = list(data[offset:offset + 32])
        self.patterns = [self._new_pattern() for _ in range(self.pattern_count)]
        self.pattern_seq = []
        for order in self.order_list_raw:
            if order == 0xFF:
                break
            if order == 0xFE:
                continue
            self.pattern_seq.append(order)
        self.samples = [S3MSample() for _ in range(self.MAX_SAMPLES)]
        self._load_pcm_instruments(data, fname)
        self._load_patterns(data, fname)
        if verbose:
            print('done.')
