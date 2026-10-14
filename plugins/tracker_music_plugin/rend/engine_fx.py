# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import math

import numpy as np

from .defs import _AMIGA_CLOCK
from .defs import _note_to_midi
from .voice import _Voice


class _FxMixin:
    def _sample_for_instrument(self, song, inst_idx: int):
        fmt = self._song_format(song)
        try:
            if fmt == "mod":
                if 1 <= inst_idx <= len(song.samples):
                    return song.samples[inst_idx - 1]
            elif fmt == "s3m":
                if 1 <= inst_idx <= len(song.samples):
                    return song.samples[inst_idx - 1]
            elif fmt == "xm":
                if 1 <= inst_idx <= len(song.instruments):
                    inst = song.instruments[inst_idx - 1]
                    if inst.samples:
                        return inst.samples[0]
        except Exception:
            return None
        return None

    def _sample_volume(self, smp) -> int:
        return int(getattr(smp, "volume", 64) or 64)

    def _sample_wave(self, smp) -> np.ndarray:
        key = id(smp)
        hit = self._wave_cache.get(key)
        if hit is not None:
            return hit
        try:
            raw = smp.waveform
            if getattr(smp, "is_16bit", False):
                arr = np.asarray(raw, dtype=np.float32) / 32768.0
            else:
                arr = np.asarray(raw, dtype=np.float32) / 128.0
        except Exception:
            arr = np.zeros(1, dtype=np.float32)
        arr = np.ascontiguousarray(arr, dtype=np.float32)
        if arr.size == 0:
            arr = np.zeros(1, dtype=np.float32)
        self._wave_cache[key] = arr
        return arr

    def _sample_loop(self, smp) -> tuple[int, int, int]:
        key = id(smp)
        hit = self._loop_cache.get(key)
        if hit is not None:
            return hit
        start = int(getattr(smp, "repeat_point", 0) or 0)
        length = int(getattr(smp, "repeat_len", 0) or 0)
        mode = 1
        loop_type = getattr(smp, "loop_type", None)
        if loop_type is not None:
            mode = int(loop_type)
        n = int(getattr(smp, "length", 0) or len(getattr(smp, "waveform", [])))
        end = min(start + length, n) if length > 1 else n
        if length <= 1 or start >= n:
            start = n
            end = n
            mode = 0
        out = (start, end, mode)
        self._loop_cache[key] = out
        return out

    def _start_voice(self, song, v: _Voice, period: str, inst: int, ch: int, retrig: bool = False):
        smp = self._sample_for_instrument(song, inst)
        if smp is None:
            if period:
                try:
                    fl = self._finetune_for_note(song, inst, period)
                    v.base_period = self._period_for_str(song, period)
                    v.finetune = fl
                    v.porta_target = v.base_period
                    v.freq = self._freq_for_base(v)
                except Exception:
                    pass
            return
        v.sample = smp
        v.wave = self._sample_wave(smp)
        v.loop_start, v.loop_end, v.loop_mode = self._sample_loop(smp)
        pos = float(v.offset)
        if pos >= len(v.wave):
            pos = float(len(v.wave) - 1)
        v.pos = max(0.0, pos)
        v.vol = max(0.0, min(1.0, self._sample_volume(smp) / 64.0))
        v.pan = self._pan_for_sample(smp)
        v.active = True
        v.offset = 0
        fmt = self._song_format(song)
        if fmt == "mod":
            try:
                v.base_period = song.note_to_period(period)
            except Exception:
                v.base_period = 428
            v.pitch_mode = "mod"
            v.finetune = int(getattr(smp, "finetune", 0) or 0)
            v.porta_target = v.base_period
            v.freq = self._freq_for_base(v)
        else:
            midi = _note_to_midi(period)
            v.base_freq = self._base_freq_from_song(song, fmt, inst, midi)
            v.pitch_mode = "xm" if fmt == "xm" else "s3m"
            v.base_period = 0
            v.freq = v.base_freq

    def _period_for_str(self, song, period: str) -> int:
        try:
            return song.note_to_period(period)
        except Exception:
            return 428

    def _finetune_for_note(self, song, inst, period) -> int:
        smp = self._sample_for_instrument(song, inst)
        if smp is not None:
            return int(getattr(smp, "finetune", 0) or 0)
        return 0

    def _freq_for_base(self, v: _Voice) -> float:
        p = v.base_period
        p = max(40.0, min(856.0, p))
        base = _AMIGA_CLOCK / p
        ft = v.finetune
        if ft:
            base *= 2.0 ** (ft / 96.0)
        return base

    def _pan_for_sample(self, smp) -> int:
        pan = getattr(smp, "panning", None)
        if pan is not None:
            return max(0, min(255, int(pan)))
        return 128

    def _apply_row_effect(self, song, v: _Voice, ch: int, efx, inst: int):
        if not efx:
            return
        cmd, arg = efx
        if self._song_format(song) == "s3m" and cmd in ("A", "C", "E"):
            return
        if cmd == "0":
            v.arp_base = v.base_period or 0
        elif cmd == "1":
            v.porta_speed = arg
        elif cmd == "2":
            v.porta_speed = arg
        elif cmd == "3":
            v.porta_speed = arg
        elif cmd == "4":
            v.vib_speed = (arg >> 4) or 1
            v.vib_depth = arg & 0x0F
        elif cmd == "5":
            v.porta_speed = arg >> 4
            v.vol_down = arg & 0x0F
            v.vol_up = arg >> 4
        elif cmd == "6":
            v.vib_speed = (arg >> 4) or 1
            v.vib_depth = arg & 0x0F
            v.vol_down = arg & 0x0F
            v.vol_up = arg >> 4
        elif cmd == "8":
            v.pan = max(0, min(255, arg * 17))
        elif cmd == "9":
            v.offset = arg * 256
            if arg == 0:
                v.offset = 0
        elif cmd == "A":
            v.vol_up = arg >> 4
            v.vol_down = arg & 0x0F
            v.last_volslide = arg
        elif cmd == "C":
            v.vol = max(0.0, min(1.0, arg / 64.0))
        elif cmd == "E":
            sub = arg >> 4
            x = arg & 0x0F
            if sub == 0x1:
                p = v.base_period if v.pitch_mode == "mod" else 0
                if p:
                    v.base_period = max(40, p - x)
                    v.freq = self._freq_for_base(v)
                    v.porta_target = max(40, p - x)
            elif sub == 0x2:
                p = v.base_period if v.pitch_mode == "mod" else 0
                if p:
                    v.base_period = min(856, p + x)
                    v.freq = self._freq_for_base(v)
                    v.porta_target = min(856, p + x)
            elif sub == 0x9:
                v.retrig_every = x
                v.retrig_count = 0
            elif sub == 0xA:
                pass

    def _apply_volume_column(self, cell, v: _Voice):
        vol = getattr(cell, "volume", None)
        if vol is not None and vol >= 0:
            v.vol = max(0.0, min(1.0, vol / 64.0))
        cmd = getattr(cell, "vol_cmd", "") or ""
        if not cmd:
            return
        try:
            val = int(getattr(cell, "vol_val", -1))
        except (TypeError, ValueError):
            return
        if val < 0:
            return
        if cmd == "v":
            v.vol = max(0.0, min(1.0, val / 64.0))
        elif cmd == "p":
            v.pan = max(0, min(255, int(val * 4.25)))
        elif cmd == "d":
            v.vol_down = val
            v.vol_up = 0
        elif cmd == "c":
            v.vol_up = val
            v.vol_down = 0

    def _tick_effect(self, song, v: _Voice, efx, tick: int, ch: int):
        if not v.active:
            return
        if not efx:
            return
        cmd, arg = efx
        if self._song_format(song) == "s3m" and cmd in ("A", "C", "E"):
            return
        if cmd == "0":
            x = (arg >> 4) or 0
            y = arg & 0x0F
            cycle = tick % 3
            if cycle == 1 and x:
                self._apply_semi_shift(v, x)
            elif cycle == 2 and y:
                self._apply_semi_shift(v, y)
            else:
                if v.pitch_mode == "mod":
                    v.freq = self._freq_for_base(v)
                else:
                    v.freq = v.base_freq
        elif cmd == "1":
            if v.base_period:
                v.base_period = max(40, v.base_period - arg)
                v.freq = self._freq_for_base(v)
        elif cmd == "2":
            if v.base_period:
                v.base_period = min(856, v.base_period + arg)
                v.freq = self._freq_for_base(v)
        elif cmd == "3":
            if v.base_period and v.porta_target:
                diff = v.porta_target - v.base_period
                step = v.porta_speed or arg
                if diff > 0:
                    v.base_period = min(v.base_period + step, v.porta_target)
                else:
                    v.base_period = max(v.base_period - step, v.porta_target)
                v.freq = self._freq_for_base(v)
        elif cmd == "4":
            if v.base_period:
                vib = self._vibrato(tick, v)
                v.freq = self._freq_for_base(v)
                if vib:
                    p = v.base_period + vib * (v.vib_depth or 0)
                    p = max(40, min(856, p))
                    v.freq = _AMIGA_CLOCK / p
        elif cmd == "A":
            if v.vol_up:
                v.vol = min(1.0, v.vol + v.vol_up * (1.0 / 64.0))
            if v.vol_down:
                v.vol = max(0.0, v.vol - v.vol_down * (1.0 / 64.0))
        elif cmd == "E":
            sub = arg >> 4
            x = arg & 0x0F
            if sub == 0x9 and x:
                v.retrig_count += 1
                if v.retrig_count >= x:
                    v.retrig_count = 0
                    v.pos = 0.0

    def _apply_semi_shift(self, v: _Voice, semis: int):
        if v.pitch_mode == "mod" and v.base_period:
            p = v.base_period / (2.0 ** (semis / 12.0))
            v.freq = _AMIGA_CLOCK / max(40, min(856, p))
        else:
            v.freq = v.base_freq * (2.0 ** (semis / 12.0))

    def _vibrato(self, tick: int, v: _Voice) -> float:
        phase = (tick * v.vib_speed) * (math.pi * 2.0 / 64.0)
        return math.sin(phase)
