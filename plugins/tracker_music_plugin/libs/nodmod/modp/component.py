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
from .header import MODSongHeaderMixin
from .patterns import MODSongPatternsMixin
from .samples import MODSongSamplesMixin

class MODSong(MODSongHeaderMixin, MODSongPatternsMixin, MODSongSamplesMixin, Song):
    def timestamp(self) -> list[list[tuple[float, int, int]]]:
        bpm = 125
        speed = 6
        d = Song.get_tick_duration(bpm)
        timestamps = []
        speeds = []
        bpms = []
        jump_to_position = -1
        jump_to_pattern = -1
        stop_song = False
        self_jump_count = 0
        self_jump_limit = 5
        start_row = 0
        seq_idx = 0
        while seq_idx < len(self.pattern_seq):
            p = self.pattern_seq[seq_idx]
            pattern_timestamps = []
            pattern_speeds = []
            pattern_bpms = []
            loop_start_row = [0] * MODSong.CHANNELS
            loop_count = [0] * MODSong.CHANNELS
            r = start_row
            while r < MODSong.ROWS:
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
                    if efx != "":
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
                pattern_timestamps.append(row_duration)
                pattern_speeds.append(speed)
                pattern_bpms.append(bpm)
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
            timestamps.append(pattern_timestamps)
            speeds.append(pattern_speeds)
            bpms.append(pattern_bpms)
            if stop_song:
                break
            if jump_to_pattern != -1:
                seq_idx = jump_to_pattern
                jump_to_pattern = -1
                start_row = 0
                continue
            seq_idx += 1
        cum = 0
        for p in range(len(timestamps)):
            for r in range(len(timestamps[p])):
                cum += timestamps[p][r]
                timestamps[p][r] = (cum, speeds[p][r], bpms[p][r])
        return timestamps

    def resize_pattern(self, pattern: int, n_rows: int) -> None:
        if n_rows != MODSong.ROWS:
            raise ValueError(f"MOD patterns have fixed 64 rows (got {n_rows}).")

    def add_to_sequence(self, pattern_idx: int, sequence_position: int | None = None) -> None:
        if len(self.pattern_seq) + 1 > 128:
            raise ValueError(f"Pattern sequence too long ({len(self.pattern_seq) + 1}). MOD supports up to 128.")
        super().add_to_sequence(pattern_idx, sequence_position)

    def set_sequence(self, seq: list[int]) -> None:
        if len(seq) > 128:
            raise ValueError(f"Pattern sequence too long ({len(seq)}). MOD supports up to 128.")
        super().set_sequence(seq)

    def clear_pattern(self, sequence_idx: int):
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        p = self.pattern_seq[sequence_idx]
        for r in range(MODSong.ROWS):
            for c in range(MODSong.CHANNELS):
                self.patterns[p].data[c][r] = Note()
        self._on_mutation()

    def add_pattern(self) -> int:
        self.patterns.append(Pattern(MODSong.ROWS, MODSong.CHANNELS))
        n = len(self.patterns) - 1
        self.pattern_seq.append(n)
        self._on_mutation()
        return n

    def add_channel(self, count: int = 1) -> None:
        if count <= 0:
            raise ValueError(f"Invalid channel count {count} (expected >=1).")
        raise NotImplementedError("MOD format has fixed 4 channels; cannot add channels.")

    def remove_channel(self, channel: int) -> None:
        raise NotImplementedError("MOD format has fixed 4 channels; cannot remove channels.")

    def clear_channel(self, channel: int):
        if channel < 0 or channel >= MODSong.CHANNELS:
            raise IndexError(f"Invalid channel index {channel} (expected 0-3).")
        for p in range(len(self.patterns)):
            for r in range(MODSong.ROWS):
                self.patterns[p].data[channel][r] = Note()
        self._on_mutation()

    def mute_channel(self, channel: int):
        if channel < 0 or channel >= MODSong.CHANNELS:
            raise IndexError(f"Invalid channel index {channel} (expected 0-3).")
        for p in range(len(self.patterns)):
            for r in range(MODSong.ROWS):
                note = self.patterns[p].data[channel][r]
                global_effect = ""
                if note.effect != "":
                    effect_type = note.effect[0]
                    if effect_type in ['F', 'B', 'D', 'C', 'E']:
                        global_effect = note.effect
                new_note = Note()
                if global_effect:
                    new_note.effect = global_effect
                self.patterns[p].data[channel][r] = new_note
        self._on_mutation()

    def set_bpm(self, pattern: int, channel: int, row: int, bpm: int):
        if bpm < 32 or bpm > 255:
            raise ValueError(f"Invalid tempo {bpm} (expected 32-255).")
        self.set_effect(pattern, channel, row, f"F{bpm:02X}")

    def set_ticks_per_row(self, pattern: int, channel: int, row: int, ticks: int):
        if ticks < 1 or ticks > 31:
            raise ValueError(f"Invalid ticks per row {ticks} (expected 1-31).")
        self.set_effect(pattern, channel, row, f"F{ticks:02X}")

    def set_portamento(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -255 or slide > 255:
            raise ValueError(f"Invalid portamento slide {slide} (expected 0-255).")
        if slide > 0:
            self.set_effect(pattern, channel, row, f"1{slide:02X}")
        elif slide < 0:
            self.set_effect(pattern, channel, row, f"2{(-slide):02X}")

    def set_tone_portamento(self, pattern: int, channel: int, row: int, speed: int):
        if speed < 0 or speed > 255:
            raise ValueError(f"Invalid tone portamento speed {speed} (expected 0-255).")
        self.set_effect(pattern, channel, row, f"3{speed:02X}")

    def set_tone_portamento_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid tone portamento slide {slide} (expected 0-255).")
        efx = 0
        if slide > 0:
            efx = slide << 4
        elif slide < 0:
            efx = -slide
        self.set_effect(pattern, channel, row, f"5{efx:02X}")

    def set_volume(self, pattern: int, channel: int, row: int, volume: int):
        if volume < 0 or volume > 64:
            raise ValueError(f"Invalid volume {volume} (expected 0-64).")
        self.set_effect(pattern, channel, row, f"C{volume:02X}")

    def set_volume_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid volume slide {slide} (expected 0-255).")
        efx = 0
        if slide > 0:
            efx = slide << 4
        elif slide < 0:
            efx = -slide
        self.set_effect(pattern, channel, row, f"A{efx:02X}")

    def set_vibrato(self, pattern: int, channel: int, row: int, speed: int, depth: int):
        if speed < 0 or speed > 15:
            raise ValueError(f"Invalid vibrato speed {speed} (expected 0-15).")
        if depth < 0 or depth > 15:
            raise ValueError(f"Invalid vibrato depth {depth} (expected 0-15).")
        efx = 16 * speed + depth
        self.set_effect(pattern, channel, row, f"4{efx:02X}")

    def set_vibrato_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid vibrato slide {slide} (expected 0-255).")
        efx = 0
        if slide > 0:
            efx = slide << 4
        elif slide < 0:
            efx = -slide
        self.set_effect(pattern, channel, row, f"6{efx:02X}")

    def set_tremolo(self, pattern: int, channel: int, row: int, speed: int, depth: int):
        if speed < 0 or speed > 15:
            raise ValueError(f"Invalid tremolo speed {speed} (expected 0-15).")
        if depth < 0 or depth > 15:
            raise ValueError(f"Invalid tremolo depth {depth} (expected 0-15).")
        efx = 16 * speed + depth
        self.set_effect(pattern, channel, row, f"7{efx:02X}")
