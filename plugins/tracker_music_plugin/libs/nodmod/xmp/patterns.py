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

class XMSongPatternsMixin:
    def copy(self) -> 'XMSong':
        from .component import XMSong
        new_song = XMSong()
        new_song.artist = self.artist
        new_song.songname = self.songname
        new_song.patterns = copy.deepcopy(self.patterns)
        new_song.pattern_seq = copy.deepcopy(self.pattern_seq)
        new_song.instruments = copy.deepcopy(self.instruments)
        new_song.n_instruments = self.n_instruments
        new_song.tracker_name = self.tracker_name
        new_song.song_restart = self.song_restart
        new_song.flags = self.flags
        new_song.default_speed = self.default_speed
        new_song.default_tempo = self.default_tempo
        new_song.n_channels = self.n_channels
        return new_song
    def iter_playback_rows(
        self,
        *,
        profile: str | None = None,
        exact: bool = True,
        max_steps: int = 250_000,
    ):
        if max_steps <= 0:
            raise ValueError(f"Invalid max_steps {max_steps} (expected > 0).")
        bpm = self.default_tempo
        speed = self.default_speed
        d = Song.get_tick_duration(bpm)
        jump_to_position = -1
        jump_to_pattern = -1
        stop_song = False
        self_jump_count = 0
        self_jump_limit = 5
        start_row = 0
        elapsed = 0.0
        visit_idx = 0
        loop_start_row = [0] * self.n_channels
        seq_idx = 0
        while seq_idx < len(self.pattern_seq):
            p = self.pattern_seq[seq_idx]
            if p < 0 or p >= len(self.patterns):
                seq_idx += 1
                continue
            pat = self.patterns[p]
            n_rows = pat.n_rows
            n_channels = pat.n_channels
            if n_channels != len(loop_start_row):
                loop_start_row = [0] * n_channels
            loop_count = [0] * n_channels
            r = start_row
            while r < n_rows:
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
                for c in range(n_channels):
                    efx = pat.data[c][r].effect
                    if efx == "":
                        continue
                    if efx[0] == "F":
                        if len(efx) < 2:
                            continue
                        try:
                            v = int(efx[1:], 16)
                        except ValueError:
                            continue
                        if v <= 31:
                            if v != 0:
                                speed = v
                        else:
                            bpm = v
                        d = Song.get_tick_duration(bpm)
                    elif efx[0] == "D":
                        if len(self.pattern_seq) <= 1:
                            continue
                        if len(efx) == 1:
                            pending_jump_row = 0
                            continue
                        param = efx[1:]
                        if len(param) == 1:
                            param = f"0{param}"
                        try:
                            hi = int(param[0], 16)
                            lo = int(param[1], 16)
                        except ValueError:
                            continue
                        pending_jump_row = hi * 10 + lo
                    elif efx[0] == "B":
                        param = efx[1:] if len(efx) > 1 else "00"
                        try:
                            dest = int(param, 16)
                        except ValueError:
                            continue
                        if dest < len(self.pattern_seq):
                            if dest > seq_idx:
                                pending_jump_pattern = dest
                            elif dest == seq_idx:
                                saw_self_jump = True
                            else:
                                stop_song = True
                    elif efx[0] == "E" and len(efx) >= 3:
                        cmd = efx[1].upper()
                        try:
                            val = int(efx[2], 16)
                        except ValueError:
                            continue
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
    def timestamp(self) -> list[list[tuple[float, int, int]]]:
        bpm = self.default_tempo
        speed = self.default_speed
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
        loop_start_row = [0] * self.n_channels
        seq_idx = 0
        while seq_idx < len(self.pattern_seq):
            p = self.pattern_seq[seq_idx]
            if p < 0 or p >= len(self.patterns):
                seq_idx += 1
                continue
            pat = self.patterns[p]
            n_rows = pat.n_rows
            n_channels = pat.n_channels
            if n_channels != len(loop_start_row):
                loop_start_row = [0] * n_channels
            pattern_timestamps = []
            pattern_speeds = []
            pattern_bpms = []
            loop_count = [0] * n_channels
            r = start_row
            while r < n_rows:
                if jump_to_position != -1:
                    jump_to_position = -1
                    start_row = 0
                row_delay = 0
                loop_jump_row = None
                pending_jump_row = None
                pending_jump_pattern = None
                saw_self_jump = False
                for c in range(n_channels):
                    efx = pat.data[c][r].effect
                    if efx != "":
                        if efx[0] == "F":
                            if len(efx) < 2:
                                continue
                            try:
                                v = int(efx[1:], 16)
                            except ValueError:
                                continue
                            if v <= 31:
                                if v != 0:
                                    speed = v
                            else:
                                bpm = v
                            d = Song.get_tick_duration(bpm)
                        elif efx[0] == "D":
                            if len(self.pattern_seq) <= 1:
                                continue
                            if len(efx) == 1:
                                pending_jump_row = 0
                                continue
                            param = efx[1:]
                            if len(param) == 1:
                                param = f"0{param}"
                            try:
                                hi = int(param[0], 16)
                                lo = int(param[1], 16)
                            except ValueError:
                                continue
                            pending_jump_row = hi * 10 + lo
                        elif efx[0] == "B":
                            param = efx[1:] if len(efx) > 1 else "00"
                            try:
                                dest = int(param, 16)
                            except ValueError:
                                continue
                            if dest < len(self.pattern_seq):
                                if dest > seq_idx:
                                    pending_jump_pattern = dest
                                elif dest == seq_idx:
                                    saw_self_jump = True
                                else:
                                    stop_song = True
                        elif efx[0] == "E" and len(efx) >= 3:
                            cmd = efx[1].upper()
                            try:
                                val = int(efx[2], 16)
                            except ValueError:
                                continue
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
    def set_note(
        self,
        sequence_idx: int,
        channel: int,
        row: int,
        instrument_idx: int,
        period: str,
        effect: str = "",
        vol_cmd: str | None = None,
        vol_val: int | None = None,
    ):
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        pat = self.patterns[self.pattern_seq[sequence_idx]]
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        if channel < 0 or channel >= pat.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        cur_note = pat.data[channel][row]
        cur_efx = cur_note.effect
        if effect == '':
            effect = self._preserved_effect(cur_efx)
        new_note = XMNote()
        new_note.instrument_idx = instrument_idx
        new_note.period = period
        new_note.effect = effect
        if vol_cmd is None and vol_val is None:
            new_note.vol_cmd = getattr(cur_note, 'vol_cmd', '')
            new_note.vol_val = getattr(cur_note, 'vol_val', -1)
        else:
            new_note.vol_cmd = vol_cmd if vol_cmd is not None else ''
            new_note.vol_val = vol_val if vol_val is not None else -1
        pat.data[channel][row] = new_note
    def set_note_rc(
        self,
        sequence_idx: int,
        row: int,
        channel: int,
        instrument_idx: int,
        period: str,
        effect: str = "",
        vol_cmd: str | None = None,
        vol_val: int | None = None,
    ):
        self.set_note(sequence_idx, channel, row, instrument_idx, period, effect, vol_cmd, vol_val)
    def add_channel(self, count: int = 1) -> None:
        if count <= 0:
            raise ValueError(f"Invalid channel count {count} (expected >=1).")
        if self.n_channels + count > 32:
            raise ValueError(f"Too many channels: {self.n_channels + count} (XM supports 1-32).")
        for pat in self.patterns:
            for _ in range(count):
                pat.data.append([XMNote() for _ in range(pat.n_rows)])
            pat.n_channels += count
        self._n_channels += count
    def remove_channel(self, channel: int) -> None:
        if self.n_channels <= 1:
            raise ValueError("Cannot remove last channel (XM requires at least 1).")
        if channel < 0 or channel >= self.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        for pat in self.patterns:
            pat.data.pop(channel)
            pat.n_channels -= 1
        self._n_channels -= 1
    def mute_channel(self, channel: int) -> None:
        if channel < 0 or channel >= self.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        for pat in self.patterns:
            for r in range(pat.n_rows):
                note = pat.data[channel][r]
                global_effect = self._preserved_effect(note.effect)
                new_note = XMNote()
                if global_effect:
                    new_note.effect = global_effect
                pat.data[channel][r] = new_note
    def clear_channel(self, channel: int) -> None:
        if channel < 0 or channel >= self.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        for pat in self.patterns:
            for r in range(pat.n_rows):
                pat.data[channel][r] = XMNote()
    def get_note(self, sequence_idx: int, row: int, channel: int) -> XMNote:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        pat = self.patterns[self.pattern_seq[sequence_idx]]
        if row < 0 or row >= pat.n_rows:
            raise IndexError(f"Invalid row index {row} (expected 0-{pat.n_rows-1}).")
        if channel < 0 or channel >= pat.n_channels:
            raise IndexError(f"Invalid channel index {channel} (expected 0-{self.n_channels-1}).")
        return pat.data[channel][row]
