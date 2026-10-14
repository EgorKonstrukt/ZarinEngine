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
ROWS = 64

class S3MSongPatternsMixin:
    def iter_playback_rows(
        self,
        *,
        profile: str | None = None,
        exact: bool = True,
        max_steps: int = 250_000,
    ):
        if max_steps <= 0:
            raise ValueError(f"Invalid max_steps {max_steps} (expected > 0).")
        speed = self.initial_speed
        bpm = self.initial_tempo
        elapsed = 0.0
        seq_idx = 0
        start_row = 0
        self_jump_count = 0
        self_jump_limit = 5
        visit_idx = 0
        while seq_idx < len(self.pattern_seq):
            pat_idx = self.pattern_seq[seq_idx]
            if pat_idx < 0 or pat_idx >= len(self.patterns):
                seq_idx += 1
                start_row = 0
                continue
            pat = self.patterns[pat_idx]
            r = start_row
            start_row = 0
            while r < pat.n_rows:
                if visit_idx >= max_steps:
                    raise RuntimeError(
                        f"iter_playback_rows exceeded max_steps={max_steps}; possible runaway playback loop."
                    )
                pending_jump_seq = None
                pending_break_row = None
                row_delay = 0
                for channel in range(pat.n_channels):
                    effect = self._effect_text(pat.data[channel][r].effect)
                    if effect == '':
                        continue
                    if effect.startswith('A') and len(effect) == 3:
                        value = int(effect[1:], 16)
                        if value != 0:
                            speed = value
                    elif effect.startswith('T') and len(effect) == 3:
                        value = int(effect[1:], 16)
                        if value >= 33:
                            bpm = value
                    elif effect.startswith('B') and len(effect) == 3:
                        value = int(effect[1:], 16)
                        if value < len(self.pattern_seq):
                            pending_jump_seq = value
                    elif effect.startswith('C') and len(effect) == 3:
                        hi = int(effect[1], 16)
                        lo = int(effect[2], 16)
                        row_target = hi * 10 + lo
                        if row_target < pat.n_rows:
                            pending_break_row = row_target
                    elif effect.startswith('SE') and len(effect) == 3:
                        row_delay = max(row_delay, int(effect[2], 16))
                start_sec = elapsed
                row_duration = (1 + row_delay) * self.get_tick_duration(bpm) * speed
                elapsed += row_duration
                yield PlaybackRowView(
                    visit_idx=visit_idx,
                    sequence_idx=seq_idx,
                    pattern_idx=pat_idx,
                    row=r,
                    start_sec=start_sec,
                    end_sec=elapsed,
                    speed=speed,
                    tempo=bpm,
                )
                visit_idx += 1
                if pending_jump_seq is not None or pending_break_row is not None:
                    if pending_jump_seq is not None:
                        if pending_jump_seq == seq_idx:
                            self_jump_count += 1
                            if self_jump_count > self_jump_limit:
                                return
                        else:
                            self_jump_count = 0
                    if pending_break_row is not None:
                        start_row = pending_break_row
                        seq_idx = pending_jump_seq if pending_jump_seq is not None else seq_idx + 1
                    else:
                        start_row = 0
                        seq_idx = pending_jump_seq
                    break
                r += 1
            else:
                seq_idx += 1

    def timestamp(self) -> list[list[tuple[float, int, int]]]:
        timestamps: list[list[tuple[float, int, int]]] = []
        speed = self.initial_speed
        bpm = self.initial_tempo
        elapsed = 0.0
        seq_idx = 0
        start_row = 0
        self_jump_count = 0
        self_jump_limit = 5
        while seq_idx < len(self.pattern_seq):
            pat_idx = self.pattern_seq[seq_idx]
            if pat_idx < 0 or pat_idx >= len(self.patterns):
                seq_idx += 1
                start_row = 0
                continue
            pat = self.patterns[pat_idx]
            pat_rows: list[tuple[float, int, int]] = []
            r = start_row
            start_row = 0
            while r < pat.n_rows:
                pending_jump_seq = None
                pending_break_row = None
                row_delay = 0
                for channel in range(pat.n_channels):
                    effect = self._effect_text(pat.data[channel][r].effect)
                    if effect == '':
                        continue
                    if effect.startswith('A') and len(effect) == 3:
                        value = int(effect[1:], 16)
                        if value != 0:
                            speed = value
                    elif effect.startswith('T') and len(effect) == 3:
                        value = int(effect[1:], 16)
                        if value >= 33:
                            bpm = value
                    elif effect.startswith('B') and len(effect) == 3:
                        value = int(effect[1:], 16)
                        if value < len(self.pattern_seq):
                            pending_jump_seq = value
                    elif effect.startswith('C') and len(effect) == 3:
                        hi = int(effect[1], 16)
                        lo = int(effect[2], 16)
                        row_target = hi * 10 + lo
                        if row_target < pat.n_rows:
                            pending_break_row = row_target
                    elif effect.startswith('SE') and len(effect) == 3:
                        row_delay = max(row_delay, int(effect[2], 16))
                pat_rows.append((elapsed, speed, bpm))
                elapsed += (1 + row_delay) * self.get_tick_duration(bpm) * speed
                if pending_jump_seq is not None or pending_break_row is not None:
                    timestamps.append(pat_rows)
                    if pending_jump_seq is not None:
                        if pending_jump_seq == seq_idx:
                            self_jump_count += 1
                            if self_jump_count > self_jump_limit:
                                return timestamps
                        else:
                            self_jump_count = 0
                    if pending_break_row is not None:
                        start_row = pending_break_row
                        seq_idx = pending_jump_seq if pending_jump_seq is not None else seq_idx + 1
                    else:
                        start_row = 0
                        seq_idx = pending_jump_seq
                    break
                r += 1
            else:
                timestamps.append(pat_rows)
                seq_idx += 1
        return timestamps

    def get_effective_row_count(self, sequence_idx: int) -> int:
        pat = self._get_sequence_pattern(sequence_idx)
        played_rows = 0
        for row in range(pat.n_rows):
            row_delay = 0
            interrupt = False
            for channel in range(pat.n_channels):
                effect = self._effect_text(pat.data[channel][row].effect)
                if effect == '':
                    continue
                if effect.startswith('SE') and len(effect) == 3:
                    row_delay = max(row_delay, int(effect[2], 16))
                if effect.startswith('B') and len(effect) == 3:
                    interrupt = True
                if effect.startswith('C') and len(effect) == 3:
                    hi = int(effect[1], 16)
                    lo = int(effect[2], 16)
                    if hi * 10 + lo < pat.n_rows:
                        interrupt = True
            played_rows += 1 + row_delay
            if interrupt:
                break
        return played_rows

    def get_used_samples(
        self,
        *,
        scope: str = "sequence",
        order: str = "sorted",
    ) -> list[int]:
        self._validate_used_resource_args(scope, order)
        seen: set[int] = set()
        first_use: list[int] = []
        for note in self._iter_notes_by_scope(scope):
            sample_idx = getattr(note, 'instrument_idx', 0)
            if sample_idx > 0 and sample_idx not in seen:
                seen.add(sample_idx)
                first_use.append(sample_idx)
        return self._finalize_used_values(first_use, order)

    def add_pattern(self, n_rows: int = ROWS) -> int:
        if n_rows != self.ROWS:
            raise ValueError(f"S3M patterns have fixed 64 rows (got {n_rows}).")
        if len(self.pattern_seq) + 1 > 256:
            raise ValueError(f"Pattern sequence too long ({len(self.pattern_seq) + 1}). S3M supports up to 256 orders.")
        self.patterns.append(self._new_pattern())
        pat_idx = len(self.patterns) - 1
        self.pattern_seq.append(pat_idx)
        return pat_idx

    def add_to_sequence(self, pattern_idx: int, sequence_position: int | None = None) -> None:
        if len(self.pattern_seq) + 1 > 256:
            raise ValueError(f"Pattern sequence too long ({len(self.pattern_seq) + 1}). S3M supports up to 256 orders.")
        super().add_to_sequence(pattern_idx, sequence_position)

    def set_sequence(self, seq: list[int]) -> None:
        if len(seq) > 256:
            raise ValueError(f"Pattern sequence too long ({len(seq)}). S3M supports up to 256 orders.")
        super().set_sequence(seq)

    def clear_pattern(self, sequence_idx: int) -> None:
        pat = self._get_sequence_pattern(sequence_idx)
        for channel in range(pat.n_channels):
            for row in range(pat.n_rows):
                pat.data[channel][row] = S3MNote()

    def resize_pattern(self, sequence_idx: int, n_rows: int) -> None:
        if n_rows != self.ROWS:
            raise ValueError(f"S3M patterns have fixed 64 rows (got {n_rows}).")
        self._get_sequence_pattern(sequence_idx)

    def get_note(self, sequence_idx: int, row: int, channel: int) -> S3MNote:
        pat = self._get_sequence_pattern(sequence_idx)
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        if channel < 0 or channel >= pat.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{pat.n_channels-1}).")
        return pat.data[channel][row]

    def set_note(
        self,
        sequence_idx: int,
        channel: int,
        row: int,
        instrument_idx: int,
        period: str,
        effect: str = "",
        volume: int | None = None,
    ) -> None:
        pat = self._get_sequence_pattern(sequence_idx)
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        if channel < 0 or channel >= pat.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{pat.n_channels-1}).")
        if instrument_idx < 0 or instrument_idx > self.MAX_SAMPLES:
            raise IndexError(f"Invalid sample index {instrument_idx} (expected 0-{self.MAX_SAMPLES}).")
        cur_note = pat.data[channel][row]
        if effect == '':
            effect = self._preserved_effect(cur_note.effect)
        new_note = S3MNote(
            instrument_idx=instrument_idx,
            period=period,
            effect=effect,
            volume=cur_note.volume if volume is None else volume,
        )
        pat.data[channel][row] = new_note

    def set_note_rc(
        self,
        sequence_idx: int,
        row: int,
        channel: int,
        instrument_idx: int,
        period: str,
        effect: str = "",
        volume: int | None = None,
    ) -> None:
        self.set_note(sequence_idx, channel, row, instrument_idx, period, effect, volume)

    def set_bpm(self, pattern: int, channel: int, row: int, bpm: int):
        if bpm < 32 or bpm > 255:
            raise ValueError(f"Invalid tempo {bpm} (expected 32-255).")
        self.set_effect(pattern, channel, row, f"T{bpm:02X}")

    def set_ticks_per_row(self, pattern: int, channel: int, row: int, ticks: int):
        if ticks < 1 or ticks > 31:
            raise ValueError(f"Invalid ticks per row {ticks} (expected 1-31).")
        self.set_effect(pattern, channel, row, f"A{ticks:02X}")

    def add_channel(self, count: int = 1) -> None:
        if count <= 0:
            raise ValueError(f"Invalid channel count {count} (expected >=1).")
        if self.n_channels + count > self.MAX_CHANNELS:
            raise ValueError(f"Too many channels: {self.n_channels + count} (S3M supports 1-{self.MAX_CHANNELS}).")
        for _ in range(count):
            try:
                raw_slot = self.channel_settings.index(255)
            except ValueError as exc:
                raise ValueError("No unused S3M channel slots are available.") from exc
            self.channel_settings[raw_slot] = self._default_channel_setting_for_index(self.n_channels)
            for pat in self.patterns:
                pat.data.append([S3MNote() for _ in range(pat.n_rows)])
                pat.n_channels += 1
            self._rebuild_channel_mappings()

    def remove_channel(self, channel: int) -> None:
        if self.n_channels <= 1:
            raise ValueError("Cannot remove last channel (S3M requires at least 1).")
        if channel < 0 or channel >= self.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        raw_slot = self.compact_to_raw_channel[channel]
        for pat in self.patterns:
            pat.data.pop(channel)
            pat.n_channels -= 1
        self.channel_settings[raw_slot] = 255
        self._rebuild_channel_mappings()

    def clear_channel(self, channel: int) -> None:
        if channel < 0 or channel >= self.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        for pat in self.patterns:
            for row in range(pat.n_rows):
                pat.data[channel][row] = S3MNote()

    def mute_channel(self, channel: int) -> None:
        if channel < 0 or channel >= self.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        for pat in self.patterns:
            for row in range(pat.n_rows):
                note = pat.data[channel][row]
                preserved = self._preserved_effect(note.effect)
                new_note = S3MNote()
                if preserved:
                    new_note.effect = preserved
                pat.data[channel][row] = new_note
