# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import copy
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from nodmod.effects import decode_mod_effect
from nodmod.types import Note
from nodmod.views import CellView, EffectView, RowView, SampleView, SongView
from nodmod.song import Song

class SongPatternsMixin(ABC):
    def _iter_pattern_entries(self, sequence_only: bool) -> list[tuple[int, int]]:
        if sequence_only:
            entries: list[tuple[int, int]] = []
            for seq_idx, pat_idx in enumerate(self.pattern_seq):
                if 0 <= pat_idx < len(self.patterns):
                    entries.append((seq_idx, pat_idx))
            return entries
        return [(-1, pat_idx) for pat_idx in range(len(self.patterns))]

    @staticmethod
    def _make_cell_view(
        *,
        sequence_idx: int,
        pattern_idx: int,
        row: int,
        channel: int,
        note,
    ) -> CellView:
        vol_cmd = getattr(note, 'vol_cmd', None)
        if vol_cmd == '':
            vol_cmd = None
        vol_val = getattr(note, 'vol_val', None)
        if not isinstance(vol_val, int) or vol_val < 0:
            vol_val = None
        volume = getattr(note, 'volume', None)
        if not isinstance(volume, int) or volume < 0:
            volume = None
        return CellView(
            sequence_idx=sequence_idx,
            pattern_idx=pattern_idx,
            row=row,
            channel=channel,
            instrument_idx=getattr(note, 'instrument_idx', 0),
            period=getattr(note, 'period', ''),
            effect=getattr(note, 'effect', ''),
            vol_cmd=vol_cmd,
            vol_val=vol_val,
            volume=volume,
        )

    def iter_cells(self, *, sequence_only: bool = True):
        for sequence_idx, pattern_idx in self._iter_pattern_entries(sequence_only):
            pat = self.patterns[pattern_idx]
            for row in range(pat.n_rows):
                for channel in range(pat.n_channels):
                    note = pat.data[channel][row]
                    yield self._make_cell_view(
                        sequence_idx=sequence_idx,
                        pattern_idx=pattern_idx,
                        row=row,
                        channel=channel,
                        note=note,
                    )

    def iter_rows(self, *, sequence_only: bool = True, reachable_only: bool = False):
        if reachable_only:
            try:
                for played_row in self.iter_playback_rows():
                    pat = self.patterns[played_row.pattern_idx]
                    cells = tuple(
                        self._make_cell_view(
                            sequence_idx=played_row.sequence_idx,
                            pattern_idx=played_row.pattern_idx,
                            row=played_row.row,
                            channel=channel,
                            note=pat.data[channel][played_row.row],
                        )
                        for channel in range(pat.n_channels)
                    )
                    yield RowView(
                        sequence_idx=played_row.sequence_idx,
                        pattern_idx=played_row.pattern_idx,
                        row=played_row.row,
                        cells=cells,
                    )
            except NotImplementedError as exc:
                raise NotImplementedError(
                    "iter_rows(reachable_only=True) requires iter_playback_rows() support for this song format."
                ) from exc
            return
        for sequence_idx, pattern_idx in self._iter_pattern_entries(sequence_only):
            pat = self.patterns[pattern_idx]
            for row in range(pat.n_rows):
                cells = tuple(
                    self._make_cell_view(
                        sequence_idx=sequence_idx,
                        pattern_idx=pattern_idx,
                        row=row,
                        channel=channel,
                        note=pat.data[channel][row],
                    )
                    for channel in range(pat.n_channels)
                )
                yield RowView(
                    sequence_idx=sequence_idx,
                    pattern_idx=pattern_idx,
                    row=row,
                    cells=cells,
                )

    def iter_effects(
        self,
        *,
        sequence_only: bool = True,
        include_empty: bool = False,
        decoded: bool = True,
    ):
        for cell in self.iter_cells(sequence_only=sequence_only):
            raw = cell.effect
            if not include_empty and raw == '':
                continue
            command = None
            arg = None
            x = None
            y = None
            extended_cmd = None
            if decoded and raw != '':
                try:
                    info = decode_mod_effect(raw)
                except (TypeError, ValueError):
                    info = None
                if info is not None:
                    command = info.command
                    arg = info.arg
                    x = info.x
                    y = info.y
                    extended_cmd = info.extended_cmd
            yield EffectView(
                sequence_idx=cell.sequence_idx,
                pattern_idx=cell.pattern_idx,
                row=cell.row,
                channel=cell.channel,
                raw=raw,
                command=command,
                arg=arg,
                x=x,
                y=y,
                extended_cmd=extended_cmd,
            )

    def _ascii_pattern_entries(self, sequence_only: bool) -> list[tuple[int | None, int]]:
        if sequence_only:
            return [(seq_idx, pat_idx) for seq_idx, pat_idx in enumerate(self.pattern_seq)]
        return [(None, pat_idx) for pat_idx in range(len(self.patterns))]

    def to_ascii(self, *, sequence_only: bool = True, include_headers: bool = False) -> str:
        lines: list[str] = []
        entries = self._ascii_pattern_entries(sequence_only)
        for sequence_idx, pattern_idx in entries:
            pat = self.patterns[pattern_idx]
            if include_headers:
                if sequence_idx is None:
                    lines.append(
                        f"# Pattern pool {pattern_idx}: {pat.n_rows} rows, {pat.n_channels} channels"
                    )
                else:
                    lines.append(
                        f"# Pattern {sequence_idx} (unique pattern {pattern_idx}): "
                        f"{pat.n_rows} rows, {pat.n_channels} channels"
                    )
            for row in range(pat.n_rows):
                row_text = ""
                for channel in range(pat.n_channels):
                    row_text += f"| {pat.data[channel][row]} "
                lines.append(f"{row_text}|")
            lines.append("")
        return "\n".join(lines)

    def save_ascii(self, fname: str, verbose: bool = True):
        if verbose:
            print(f'Saving to {fname}... ', end='', flush=True)
        with open(fname, 'w', encoding='ascii') as file:
            file.write(self.to_ascii())
        if verbose:
            print('done.')

    @abstractmethod
    def get_effective_row_count(self, sequence_idx: int) -> int:
        pass

    def add_to_sequence(self, pattern_idx: int, sequence_position: int | None = None) -> None:
        if pattern_idx < 0 or pattern_idx >= len(self.patterns):
            raise IndexError(f"Invalid pattern index {pattern_idx} (expected 0-{len(self.patterns)-1}).")
        if sequence_position is None:
            self.pattern_seq.append(pattern_idx)
            self._on_mutation()
            return
        if sequence_position < 0 or sequence_position > len(self.pattern_seq):
            raise IndexError(f"Invalid sequence position {sequence_position} (expected 0-{len(self.pattern_seq)}).")
        self.pattern_seq = self.pattern_seq[:sequence_position] + [pattern_idx] + self.pattern_seq[sequence_position:]
        self._on_mutation()

    def set_sequence(self, seq: list[int]) -> None:
        if not isinstance(seq, list):
            raise ValueError("Pattern sequence must be a list of integers.")
        for idx in seq:
            if not isinstance(idx, int):
                raise ValueError(f"Invalid pattern index {idx} (expected int).")
            if idx < 0 or idx >= len(self.patterns):
                raise IndexError(f"Invalid pattern index {idx} (expected 0-{len(self.patterns)-1}).")
        self.pattern_seq = list(seq)
        self._on_mutation()

    def remove_patterns_after(self, sequence_idx: int):
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        self.pattern_seq = self.pattern_seq[:sequence_idx + 1]
        self._on_mutation()

    def remove_pattern(self, sequence_idx: int) -> None:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        self.pattern_seq = self.pattern_seq[:sequence_idx] + self.pattern_seq[sequence_idx + 1:]
        self._on_mutation()

    def remove_all_patterns(self, sequence_only: bool) -> None:
        self.pattern_seq = []
        if not sequence_only:
            self.patterns = []
        self._on_mutation()

    def keep_pattern(self, sequence_idx: int) -> None:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        self.pattern_seq = [self.pattern_seq[sequence_idx]]
        self._on_mutation()

    def insert_pattern(self, sequence_idx: int, after: bool = True) -> int:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        self.patterns.append(copy.deepcopy(self.patterns[self.pattern_seq[sequence_idx]]))
        new_idx = len(self.patterns) - 1
        seq_pos = sequence_idx + 1 if after else sequence_idx
        self.pattern_seq = self.pattern_seq[:seq_pos] + [new_idx] + self.pattern_seq[seq_pos:]
        self._on_mutation()
        return new_idx

    def duplicate_pattern(self, sequence_idx: int) -> int:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        self.patterns.append(copy.deepcopy(self.patterns[self.pattern_seq[sequence_idx]]))
        n = len(self.patterns) - 1
        self.pattern_seq.append(n)
        self._on_mutation()
        return n

    def copy_pattern_from(self, src_song: 'Song', src_pattern_idx: int) -> int:
        if src_pattern_idx < 0 or src_pattern_idx >= len(src_song.patterns):
            raise IndexError(f"Invalid source pattern index {src_pattern_idx} (expected 0-{len(src_song.patterns)-1}).")
        self.patterns.append(copy.deepcopy(src_song.patterns[src_pattern_idx]))
        new_idx = len(self.patterns) - 1
        self.pattern_seq.append(new_idx)
        self._on_mutation()
        return new_idx

    def is_pattern_empty(self, pattern: int) -> bool:
        pat = self._get_sequence_pattern(pattern)
        for channel in pat.data:
            for note in channel:
                if not note.is_empty():
                    return False
        return True

    def get_used_patterns(self) -> list[int]:
        used = []
        seen = set()
        for pattern_idx in self.pattern_seq:
            if pattern_idx not in seen:
                seen.add(pattern_idx)
                used.append(pattern_idx)
        return used

    def get_note_rc(self, sequence_idx: int, row: int, channel: int):
        return self.get_note(sequence_idx, row, channel)

    def set_note_rc(
        self,
        sequence_idx: int,
        row: int,
        channel: int,
        sample_idx: int,
        period: str,
        effect: str = "",
    ):
        self.set_note(sequence_idx, channel, row, sample_idx, period, effect)

    def clear_note_rc(self, sequence_idx: int, row: int, channel: int):
        self.clear_note(sequence_idx, channel, row)

    def set_note(self, sequence_idx:int, channel: int, row: int, sample_idx: int, period: str, effect: str = ""):
        pat = self._get_sequence_pattern(sequence_idx)
        if channel < 0 or channel >= pat.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{pat.n_channels-1}).")
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        cur_note = pat.data[channel][row]
        if effect == '':
            effect = self._preserved_effect(cur_note.effect)
        pat.data[channel][row] = Note(sample_idx, period, effect)
        self._on_mutation()

    def clear_note(self, sequence_idx: int, channel: int, row: int):
        pat = self._get_sequence_pattern(sequence_idx)
        if channel < 0 or channel >= pat.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{pat.n_channels-1}).")
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        pat.data[channel][row] = type(pat.data[channel][row])()
        self._on_mutation()

    def clear_row(self, sequence_idx: int, row: int):
        pat = self._get_sequence_pattern(sequence_idx)
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        for channel in range(pat.n_channels):
            pat.data[channel][row] = type(pat.data[channel][row])()
        self._on_mutation()

    def copy_row(self, src_sequence_idx: int, src_row: int, dst_sequence_idx: int, dst_row: int):
        src_pat = self._get_sequence_pattern(src_sequence_idx)
        dst_pat = self._get_sequence_pattern(dst_sequence_idx)
        if src_row < 0 or src_row >= src_pat.n_rows:
            raise IndexError(f"Invalid source row index {src_row} (expected 0-{src_pat.n_rows-1}).")
        if dst_row < 0 or dst_row >= dst_pat.n_rows:
            raise IndexError(f"Invalid destination row index {dst_row} (expected 0-{dst_pat.n_rows-1}).")
        for channel in range(dst_pat.n_channels):
            dst_pat.data[channel][dst_row] = type(dst_pat.data[channel][dst_row])()
        for channel in range(min(src_pat.n_channels, dst_pat.n_channels)):
            dst_pat.data[channel][dst_row] = copy.deepcopy(src_pat.data[channel][src_row])
        self._on_mutation()

    def shift_pattern(self, sequence_idx: int, delta_rows: int):
        pat = self._get_sequence_pattern(sequence_idx)
        for channel in range(pat.n_channels):
            old_rows = pat.data[channel]
            new_rows = [type(old_rows[row])() for row in range(pat.n_rows)]
            for row, note in enumerate(old_rows):
                new_row = row + delta_rows
                if 0 <= new_row < pat.n_rows:
                    new_rows[new_row] = copy.deepcopy(note)
            pat.data[channel] = new_rows
        self._on_mutation()

    def copy_channel_data(self, src_sequence_idx: int, src_channel: int, dst_sequence_idx: int, dst_channel: int):
        src_pat = self._get_sequence_pattern(src_sequence_idx)
        dst_pat = self._get_sequence_pattern(dst_sequence_idx)
        if src_channel < 0 or src_channel >= src_pat.n_channels:
            raise IndexError(f"Invalid source channel index {src_channel} (expected 0-{src_pat.n_channels-1}).")
        if dst_channel < 0 or dst_channel >= dst_pat.n_channels:
            raise IndexError(f"Invalid destination channel index {dst_channel} (expected 0-{dst_pat.n_channels-1}).")
        dst_pat.data[dst_channel] = [type(dst_pat.data[dst_channel][row])() for row in range(dst_pat.n_rows)]
        for row in range(min(src_pat.n_rows, dst_pat.n_rows)):
            dst_pat.data[dst_channel][row] = copy.deepcopy(src_pat.data[src_channel][row])
        self._on_mutation()

    def swap_channels(self, ch1: int, ch2: int):
        if ch1 == ch2:
            return
        for pat in self.patterns:
            if ch1 < 0 or ch1 >= pat.n_channels or ch2 < 0 or ch2 >= pat.n_channels:
                raise IndexError(f"Invalid channel indices {ch1}, {ch2} for pattern with {pat.n_channels} channels.")
            pat.data[ch1], pat.data[ch2] = pat.data[ch2], pat.data[ch1]
        self._on_mutation()

    def set_effect_rc(self, sequence_idx: int, row: int, channel: int, effect: str = ""):
        self.set_effect(sequence_idx, channel, row, effect)

    def set_effect(self, sequence_idx: int, channel: int, row: int, effect: str = ""):
        pat = self._get_sequence_pattern(sequence_idx)
        if channel < 0 or channel >= pat.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{pat.n_channels-1}).")
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        pat.data[channel][row].effect = effect
        self._on_mutation()

    def _get_sequence_pattern(self, sequence_idx: int):
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        return self.patterns[self.pattern_seq[sequence_idx]]

    def _preserved_effect(self, effect: str) -> str:
        effect = self._effect_text(effect)
        if effect and effect[0] in self.PRESERVED_EFFECT_PREFIXES:
            return effect
        return ''
