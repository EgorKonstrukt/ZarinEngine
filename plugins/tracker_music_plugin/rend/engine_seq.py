# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

from .defs import _AMIGA_CLOCK
from .defs import _build_fastmix_once
from .defs import _load_fastmix
from .defs import _parse_effect
from .voice import _Voice


class _SeqMixin:
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.voices: list[_Voice] = []
        self.n_channels = 0
        self.channel_gains: list[float] = []
        self.master_gain: float = 1.0
        self._arange_cache: dict[int, np.ndarray] = {}
        self._idx_cache: dict[int, np.ndarray] = {}
        self._tmp_cache: dict[int, np.ndarray] = {}
        self._xp_cache: dict[int, np.ndarray] = {}
        self._wave_cache: dict[int, np.ndarray] = {}
        self._loop_cache: dict[int, tuple[int, int, int]] = {}
        self._fastmix = None
        self._fastmix_tried = False
        self.playback_map: list[tuple] = []
        self.meter_peaks: list[list[float]] = []
        self.meter_block_sec: float = self.METER_BLOCK_SEC
        self._meter_block: list[float] = []
        self._meter_blocks: list[list[float]] = []
        self._meter_cursor: int = 0

    def _fastmix_mod(self):
        if self._fastmix is not None:
            return self._fastmix
        mod = _load_fastmix()
        if mod is not None:
            self._fastmix = mod
            return mod
        if self._fastmix_tried:
            return None
        self._fastmix_tried = True
        _build_fastmix_once()
        mod = _load_fastmix()
        if mod is not None:
            self._fastmix = mod
            return mod
        return None

    @staticmethod
    def db_to_gain(db: float) -> float:
        if db <= -60.0:
            return 0.0
        return 10.0 ** (db / 20.0)

    def set_channel_db(self, ch: int, db: float):
        while len(self.channel_gains) <= ch:
            self.channel_gains.append(1.0)
        self.channel_gains[ch] = self.db_to_gain(db)

    def get_meter_data(self) -> tuple[float, list[list[float]]]:
        return self.meter_block_sec, self.meter_peaks

    def _voice_frequency(self, v: _Voice, arp_semi: int, tick_cycle: int) -> float:
        if v.pitch_mode == "mod":
            period = v.base_period
            period = max(40.0, min(856.0, period))
            f = _AMIGA_CLOCK / period
            if tick_cycle == 1 and arp_semi:
                f *= 2.0 ** (arp_semi / 12.0)
            elif tick_cycle == 2 and arp_semi:
                f *= 2.0 ** (arp_semi / 12.0)
            return f
        base = v.base_freq
        if tick_cycle == 1 and arp_semi:
            base *= 2.0 ** (arp_semi / 12.0)
        elif tick_cycle == 2 and arp_semi:
            base *= 2.0 ** (arp_semi / 12.0)
        return base

    def _base_freq_from_song(self, song, fmt: str, instrument_idx: int, midi: int) -> float:
        if midi is None:
            midi = 60
        if fmt == "s3m":
            c2spd = 8363.0
            try:
                if instrument_idx > 0 and instrument_idx <= len(song.samples):
                    c2spd = float(getattr(song.samples[instrument_idx - 1], "c2spd", 8363) or 8363)
            except Exception:
                pass
            return c2spd * 2.0 ** ((midi - 60) / 12.0)
        rel = 0
        fine = 0
        try:
            inst = song.instruments[instrument_idx - 1] if instrument_idx >= 1 and instrument_idx <= len(
                song.instruments) else None
            if inst is not None and inst.samples:
                smp = inst.samples[0]
                rel = int(getattr(smp, "relative_note", 0) or 0)
                fine = int(getattr(inst, "vibrato_depth", 0) or 0)
                if hasattr(smp, "finetune"):
                    fine = int(getattr(smp, "finetune", 0) or 0)
        except Exception:
            pass
        ft2_midi = midi - 12
        return 8363.0 * 2.0 ** ((ft2_midi - 60 + rel) / 12.0 + fine / (128.0 * 12.0))

    def _song_format(self, song) -> str:
        return getattr(song, "file_extension", "mod")

    def _reset(self, song):
        fmt = self._song_format(song)
        try:
            self.n_channels = int(song.n_channels)
        except Exception:
            self.n_channels = getattr(song, "patterns", None) and song.patterns and song.patterns[0].n_channels or 4
        while len(self.voices) < self.n_channels:
            self.voices.append(_Voice())
        for v in self.voices:
            v.active = False
        self._meter_block = [0.0] * self.n_channels
        self._meter_blocks = []
        self._meter_cursor = 0
        self.meter_peaks = []
        self.meter_block_sec = self.METER_BLOCK_SEC
        self.playback_map = []
        self._wave_cache.clear()
        self._loop_cache.clear()

    def get_playback_map(self) -> list[tuple]:
        return list(self.playback_map)

    def render(self, song, max_seconds: float | None = None,
               progress=None, should_cancel=None) -> np.ndarray | None:
        try:
            initial_bpm = int(getattr(song, "initial_bpm", None) or getattr(song, "bpm", 125) or 125)
        except Exception:
            initial_bpm = 125
        try:
            speed = int(getattr(song, "initial_speed", None) or getattr(song, "speed", 6) or 6)
        except Exception:
            speed = 6
        if speed < 1:
            speed = 6
        if initial_bpm < 32:
            initial_bpm = 125
        self._reset(song)
        sequence = list(getattr(song, "pattern_seq", []))
        patterns = list(getattr(song, "patterns", []))
        sr = self.sample_rate
        total = int(max_seconds * sr) if max_seconds else None
        total_sec = float(max_seconds) if max_seconds else None
        if total_sec is None:
            try:
                info = (getattr(song, "get_song_info", lambda: {})() or {})
                total_sec = float(info.get("duration_seconds") or 0) or None
            except Exception:
                total_sec = None
        left = []
        right = []
        elapsed_frames = 0
        bpm = initial_bpm
        next_bpm = bpm
        seq_idx = 0
        pattern_loop_start_row = None
        pattern_loop_counts: dict[int, int] = {}
        back_jumps = 0
        song_end = False
        while seq_idx < len(sequence) and not song_end:
            pat_uniq = sequence[seq_idx]
            if pat_uniq < 0 or pat_uniq >= len(patterns):
                seq_idx += 1
                continue
            pat = patterns[pat_uniq]
            n_rows = int(pat.n_rows)
            row = 0
            row_speed = speed
            while row < n_rows:
                block, row_speed = self._render_row(
                    song, pat, row, seq_idx, speed, bpm, elapsed_frames, total)
                if block is not None and len(block[0]) > 0:
                    left.append(block[0])
                    right.append(block[1])
                    elapsed_frames += len(block[0])
                    self.playback_map.append((elapsed_frames / sr, seq_idx, row))
                    if progress is not None:
                        progress(elapsed_frames / sr, total_sec)
                    if total is not None and elapsed_frames >= total:
                        return self._assemble(left, right)
                if should_cancel is not None and should_cancel():
                    return None
                new_speed = self._row_speed_change(song, pat, row)
                if new_speed:
                    speed = new_speed
                if self._bpm_change(song, pat, row):
                    nb = self._bpm_change(song, pat, row)
                    if 32 <= nb <= 255:
                        next_bpm = nb
                bpm = next_bpm
                continue_row = self._loop_directive(song, pat, row, pattern_loop_start_row, pattern_loop_counts)
                if continue_row is not None:
                    pattern_loop_start_row, row = continue_row
                    continue
                if self._jump_directive(song, pat, row, is_jump=True):
                    target = self._jump_target(song, pat, row, seq_idx, sequence)
                    row = self._pattern_break_row(song, pat, row)
                    if target <= seq_idx:
                        back_jumps += 1
                        if back_jumps > 2:
                            song_end = True
                            break
                    seq_idx = min(max(int(target), 0), len(sequence))
                    pattern_loop_start_row = None
                    pattern_loop_counts = {}
                    break
                if self._break_directive(song, pat, row):
                    seq_idx += 1
                    row = self._pattern_break_row(song, pat, row)
                    pattern_loop_start_row = None
                    pattern_loop_counts = {}
                    break
                row += 1
            else:
                pattern_loop_start_row = None
                pattern_loop_counts = {}
                seq_idx += 1
            if total is not None and elapsed_frames >= total:
                break
        return self._assemble(left, right)

    def _row_speed_change(self, song, pat, row) -> int:
        fmt = self._song_format(song)
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row]
            efx = _parse_effect(getattr(cell, "effect", ""))
            if not efx:
                continue
            if fmt == "s3m":
                if efx[0] == "A" and 1 <= efx[1] <= 255:
                    return efx[1]
            elif efx[0] == "F" and 1 <= efx[1] <= 31:
                return efx[1]
        return 0

    def _bpm_change(self, song, pat, row) -> int:
        fmt = self._song_format(song)
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row]
            efx = _parse_effect(getattr(cell, "effect", ""))
            if not efx:
                continue
            if fmt == "s3m":
                if efx[0] == "T" and efx[1] >= 32:
                    return efx[1]
            elif efx[0] == "F" and efx[1] >= 32:
                return efx[1]
        return 0

    def _loop_directive(self, song, pat, row, loop_start, loop_counts) -> tuple | None:
        fmt = self._song_format(song)
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row]
            efx = _parse_effect(getattr(cell, "effect", ""))
            if not efx:
                continue
            if fmt == "s3m":
                if efx[0] != "S" or (efx[1] >> 4) != 0xB:
                    continue
            elif efx[0] != "E" or (efx[1] >> 4) != 0xE:
                continue
            x = efx[1] & 0x0F
            if x == 0:
                return (row, row + 1)
            if loop_start is not None:
                counts = loop_counts.get(ch, 0) + 1
                if counts < x:
                    loop_counts[ch] = counts
                    return (loop_start, loop_start)
                loop_counts[ch] = 0
        return None

    def _jump_directive(self, song, pat, row, is_jump: bool) -> bool:
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row]
            efx = _parse_effect(getattr(cell, "effect", ""))
            if efx and efx[0] == "B":
                return True
        return False

    def _jump_target(self, song, pat, row, seq_idx, sequence) -> int:
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row]
            efx = _parse_effect(getattr(cell, "effect", ""))
            if efx and efx[0] == "B":
                return efx[1]
        return seq_idx + 1

    def _break_directive(self, song, pat, row) -> bool:
        fmt = self._song_format(song)
        want = "C" if fmt == "s3m" else "D"
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row]
            efx = _parse_effect(getattr(cell, "effect", ""))
            if efx and efx[0] == want:
                return True
        return False

    def _pattern_break_row(self, song, pat, row) -> int:
        fmt = self._song_format(song)
        want = "C" if fmt == "s3m" else "D"
        n_rows = int(getattr(pat, "n_rows", 64) or 64)
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row]
            efx = _parse_effect(getattr(cell, "effect", ""))
            if efx and efx[0] == want:
                arg = efx[1]
                target = (arg >> 4) * 10 + (arg & 0x0F)
                return max(0, min(int(target), n_rows))
        return 0

    def _render_row(self, song, pat, row_idx, seq_idx, speed, bpm, elapsed_frames, total) -> tuple:
        efxs = []
        fmt = self._song_format(song)
        for ch in range(pat.n_channels):
            cell = pat.data[ch][row_idx]
            period = getattr(cell, "period", "") or ""
            inst = int(getattr(cell, "instrument_idx", 0) or 0)
            effect = getattr(cell, "effect", "") or ""
            v = self.voices[ch]
            efx = _parse_effect(effect)
            efxs.append((ch, efx))
            delay = -1
            cut = -1
            if fmt != "s3m" and efx and efx[0] == "E":
                sub = efx[1] >> 4
                x = efx[1] & 0x0F
                if sub == 0xC:
                    cut = x
                elif sub == 0xD:
                    delay = x
            v.cut_tick = cut
            v.delay_tick = delay
            porta = False
            if fmt != "s3m" and efx and efx[0] in ("3", "5"):
                porta = True
            if period and period.upper() != "OFF" and not porta:
                self._start_voice(song, v, period, inst, ch)
            elif period and period.upper() == "OFF":
                v.active = False
            elif inst and not period:
                smp = self._sample_for_instrument(song, inst)
                if smp is not None:
                    v.vol = self._sample_volume(smp) / 64.0
            self._apply_volume_column(cell, v)
            self._apply_row_effect(song, v, ch, efx, inst)
        tick_frames = int(round(self.sample_rate * 2.5 / bpm))
        if tick_frames < 1:
            tick_frames = 1
        row_frames = tick_frames * max(1, int(speed))
        l_all = np.zeros(row_frames, dtype=np.float32)
        r_all = np.zeros(row_frames, dtype=np.float32)
        for tick in range(speed):
            for ch in range(pat.n_channels):
                v = self.voices[ch]
                _, efx = efxs[ch]
                self._tick_effect(song, v, efx, tick, ch)
                if v.delay_tick == tick:
                    cell = pat.data[ch][row_idx]
                    period = getattr(cell, "period", "") or ""
                    inst = int(getattr(cell, "instrument_idx", 0) or 0)
                    if period and period.upper() != "OFF":
                        self._start_voice(song, v, period, inst, ch)
                if v.cut_tick == tick:
                    v.vol = 0.0
            off = tick * tick_frames
            self._mix_tick_into(l_all[off:off + tick_frames],
                                r_all[off:off + tick_frames])
        return ((l_all, r_all), speed)
