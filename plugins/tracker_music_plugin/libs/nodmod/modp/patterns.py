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

class MODSongPatternsMixin:
    def iter_playback_rows(
        self,
        *,
        profile: str | None = None,
        exact: bool = True,
        max_steps: int = 250_000,
    ):
        if max_steps <= 0:
            raise ValueError(f"Invalid max_steps {max_steps} (expected > 0).")
        bpm = 125
        speed = 6
        d = Song.get_tick_duration(bpm)
        jump_to_position = -1
        jump_to_pattern = -1
        stop_song = False
        self_jump_count = 0
        self_jump_limit = 5
        start_row = 0
        elapsed = 0.0
        visit_idx = 0
        seq_idx = 0
        while seq_idx < len(self.pattern_seq):
            p = self.pattern_seq[seq_idx]
            loop_start_row = [0] * MODSong.CHANNELS
            loop_count = [0] * MODSong.CHANNELS
            r = start_row
            while r < MODSong.ROWS:
                if visit_idx >= max_steps:
                    raise RuntimeError(
                        f"iter_playback_rows exceeded max_steps={max_steps}; possible runaway playback loop."
                    )
                if jump_to_position != -1:
                    jump_to_position = -1
                    start_row = 0
                row_delay = 0
                loop_jump_row = None
                pending_jump_row = None
                pending_jump_pattern = None
                saw_self_jump = False
                for c in range(MODSong.CHANNELS):
                    efx = self.patterns[p].data[c][r].effect
                    if efx == "":
                        continue
                    if efx[0] == "F":
                        v = int(efx[1:], 16)
                        if v <= 31:
                            if v != 0:
                                speed = v
                        else:
                            bpm = v
                        d = Song.get_tick_duration(bpm)
                    elif efx[0] == "D":
                        if len(efx) >= 3:
                            hi = int(efx[1], 16)
                            lo = int(efx[2], 16)
                            if len(self.pattern_seq) > 1:
                                pending_jump_row = hi * 10 + lo
                    elif efx[0] == "B":
                        dest = int(efx[1:], 16)
                        if dest < len(self.pattern_seq):
                            if dest > seq_idx:
                                pending_jump_pattern = dest
                            elif dest == seq_idx:
                                saw_self_jump = True
                            else:
                                stop_song = True
                    elif efx[0] == "E" and len(efx) >= 3:
                        cmd = efx[1].upper()
                        val = int(efx[2], 16)
                        if cmd == "6":
                            if val == 0:
                                old_loop_start = loop_start_row[c]
                                loop_start_row[c] = r
                                if loop_count[c] == -1 and r > old_loop_start:
                                    loop_count[c] = 0
                            else:
                                if loop_count[c] == 0:
                                    loop_count[c] = val
                                if loop_count[c] > 0 and loop_start_row[c] < r:
                                    loop_count[c] -= 1
                                    loop_jump_row = loop_start_row[c]
                                    if loop_count[c] == 0:
                                        loop_count[c] = -1
                        elif cmd == "E":
                            row_delay = val
                row_duration = d * speed
                if row_delay > 0:
                    row_duration *= (row_delay + 1)
                start_sec = elapsed
                elapsed += row_duration
                yield PlaybackRowView(
                    visit_idx=visit_idx,
                    sequence_idx=seq_idx,
                    pattern_idx=p,
                    row=r,
                    start_sec=start_sec,
                    end_sec=elapsed,
                    speed=speed,
                    tempo=bpm,
                )
                visit_idx += 1
                if stop_song:
                    break
                if saw_self_jump and pending_jump_row is not None and self_jump_count < self_jump_limit:
                    pending_jump_pattern = seq_idx
                    self_jump_count += 1
                if loop_jump_row is not None:
                    r = loop_jump_row
                    continue
                if pending_jump_pattern is not None:
                    jump_to_pattern = pending_jump_pattern
                    if pending_jump_row is not None:
                        start_row = pending_jump_row
                    else:
                        start_row = 0
                    break
                if pending_jump_row is not None:
                    jump_to_position = pending_jump_row
                    start_row = jump_to_position
                    break
                r += 1
            if stop_song:
                break
            if jump_to_pattern != -1:
                seq_idx = jump_to_pattern
                jump_to_pattern = -1
                start_row = 0
                continue
            seq_idx += 1

    def iter_cells(self, *, sequence_only: bool = True, resolved: bool = True):
        if not resolved or not sequence_only:
            yield from super().iter_cells(sequence_only=sequence_only)
            return
        self._ensure_sequence_resolution_cache()
        for sequence_idx, pattern_idx in self._iter_pattern_entries(sequence_only=True):
            pat = self.patterns[pattern_idx]
            for row in range(pat.n_rows):
                for channel in range(pat.n_channels):
                    raw_note = pat.data[channel][row]
                    raw_sample = int(getattr(raw_note, 'instrument_idx', 0))
                    effective_sample = self._resolved_sequence_cells.get((sequence_idx, row, channel), raw_sample)
                    view_note = raw_note
                    if effective_sample != raw_sample:
                        view_note = Note(effective_sample, raw_note.period, raw_note.effect)
                    yield self._make_cell_view(
                        sequence_idx=sequence_idx,
                        pattern_idx=pattern_idx,
                        row=row,
                        channel=channel,
                        note=view_note,
                    )

    def iter_rows(
        self,
        *,
        sequence_only: bool = True,
        reachable_only: bool = False,
        resolved: bool = True,
    ):
        if not resolved:
            yield from super().iter_rows(sequence_only=sequence_only, reachable_only=reachable_only)
            return
        if reachable_only:
            self._ensure_reachable_resolution_cache()
            for played_row in self._resolved_reachable_rows:
                if played_row.pattern_idx < 0 or played_row.pattern_idx >= len(self.patterns):
                    continue
                pat = self.patterns[played_row.pattern_idx]
                if played_row.row < 0 or played_row.row >= pat.n_rows:
                    continue
                cells: list[CellView] = []
                for channel in range(pat.n_channels):
                    raw_note = pat.data[channel][played_row.row]
                    raw_sample = int(getattr(raw_note, 'instrument_idx', 0))
                    effective_sample = self._resolved_reachable_cells.get((played_row.visit_idx, channel), raw_sample)
                    view_note = raw_note
                    if effective_sample != raw_sample:
                        view_note = Note(effective_sample, raw_note.period, raw_note.effect)
                    cells.append(
                        self._make_cell_view(
                            sequence_idx=played_row.sequence_idx,
                            pattern_idx=played_row.pattern_idx,
                            row=played_row.row,
                            channel=channel,
                            note=view_note,
                        )
                    )
                yield RowView(
                    sequence_idx=played_row.sequence_idx,
                    pattern_idx=played_row.pattern_idx,
                    row=played_row.row,
                    cells=tuple(cells),
                )
            return
        if not sequence_only:
            yield from super().iter_rows(sequence_only=False, reachable_only=False)
            return
        self._ensure_sequence_resolution_cache()
        for sequence_idx, pattern_idx in self._iter_pattern_entries(sequence_only=True):
            pat = self.patterns[pattern_idx]
            for row in range(pat.n_rows):
                cells: list[CellView] = []
                for channel in range(pat.n_channels):
                    raw_note = pat.data[channel][row]
                    raw_sample = int(getattr(raw_note, 'instrument_idx', 0))
                    effective_sample = self._resolved_sequence_cells.get((sequence_idx, row, channel), raw_sample)
                    view_note = raw_note
                    if effective_sample != raw_sample:
                        view_note = Note(effective_sample, raw_note.period, raw_note.effect)
                    cells.append(
                        self._make_cell_view(
                            sequence_idx=sequence_idx,
                            pattern_idx=pattern_idx,
                            row=row,
                            channel=channel,
                            note=view_note,
                        )
                    )
                yield RowView(
                    sequence_idx=sequence_idx,
                    pattern_idx=pattern_idx,
                    row=row,
                    cells=tuple(cells),
                )

    def get_effective_row_count(self, sequence_idx: int, include_loops: bool = True) -> int:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        loop_start_row = 0
        data = copy.deepcopy(self.patterns[self.pattern_seq[sequence_idx]].data)
        unrolled_data = [[] for _ in range(MODSong.CHANNELS)]
        for r in range(MODSong.ROWS):
            interrupt = False
            for c in range(MODSong.CHANNELS):
                unrolled_data[c].append(data[c][r])
                efx = data[c][r].effect
                if efx != "":
                    if efx[0] == "B" or efx[0] == "D":
                        interrupt = True
                    if include_loops and efx[:2] == "E6":
                        if int(efx[2], 16) == 0:
                            loop_start_row = r
                        loop_end_row = r
                        loop_count = int(efx[2], 16)
                        for loop in range(loop_count):
                            unrolled_data[c] += unrolled_data[c][loop_start_row:loop_end_row + 1]
            if interrupt:
                break
        return max([len(unrolled_data[c]) for c in range(MODSong.CHANNELS)])

    @staticmethod
    def get_sample_from_note(note: bytearray) -> int:
        u4 = note[0] & 0xF0
        l4 = note[2] & 0xF0
        return u4 | (l4 >> 4)

    @staticmethod
    def get_effect_from_note(note: bytearray) -> tuple[int, int]:
        return note[2] & 0x0F, note[3]

    @staticmethod
    def get_period_from_note(note: bytearray) -> str:
        period_raw = ((note[0] & 0x0F) << 8) | note[1]
        if period_raw != 0:
            if period_raw not in MODSong.PERIOD_TABLE:
                raise ValueError(f"Unknown period value {period_raw} in MOD note data.")
            return MODSong.PERIOD_TABLE[period_raw]
        else:
            return ""

    def get_note_raw(self, sequence_idx: int, row: int, channel: int) -> Note:
        if row < 0 or row >= MODSong.ROWS:
            raise IndexError(f"Invalid row index {row} (expected 0-63).")
        if channel < 0 or channel >= MODSong.CHANNELS:
            raise IndexError(f"Invalid channel index {channel} (expected 0-3).")
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        return self.patterns[self.pattern_seq[sequence_idx]].data[channel][row]

    def get_note(self, sequence_idx: int, row: int, channel: int, *, resolved: bool = True) -> Note:
        raw_note = self.get_note_raw(sequence_idx, row, channel)
        if not resolved:
            return raw_note
        self._ensure_sequence_resolution_cache()
        raw_sample = int(getattr(raw_note, 'instrument_idx', 0))
        effective_sample = self._resolved_sequence_cells.get((sequence_idx, row, channel), raw_sample)
        if effective_sample == raw_sample:
            return raw_note
        return Note(effective_sample, raw_note.period, raw_note.effect)
