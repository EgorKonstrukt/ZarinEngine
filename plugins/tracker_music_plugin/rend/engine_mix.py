# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import math

import numpy as np

from .voice import _Voice


class _MixMixin:
    def _mix_one(self, v: _Voice, n: int) -> np.ndarray:
        if not v.active or len(v.wave) == 0 or v.vol <= 0.0:
            return np.zeros(n, dtype=np.float32)
        freq = v.freq
        if freq <= 0:
            return np.zeros(n, dtype=np.float32)
        ar = self._arange(n)
        idx_buf = self._idx_buf(n)
        return self._render_voice_numpy(v, n, ar, idx_buf)

    def _arange(self, n: int) -> np.ndarray:
        ar = self._arange_cache.get(n)
        if ar is None:
            ar = np.arange(n, dtype=np.float64)
            self._arange_cache[n] = ar
        return ar

    def _idx_buf(self, n: int) -> np.ndarray:
        buf = self._idx_cache.get(n)
        if buf is None:
            buf = np.empty(n, dtype=np.float64)
            self._idx_cache[n] = buf
        return buf

    def _tmp_buf(self, n: int) -> np.ndarray:
        buf = self._tmp_cache.get(n)
        if buf is None:
            buf = np.empty(n, dtype=np.float32)
            self._tmp_cache[n] = buf
        return buf

    def _xp_for(self, wlen: int) -> np.ndarray:
        xp = self._xp_cache.get(wlen)
        if xp is None:
            xp = np.arange(wlen, dtype=np.float64)
            self._xp_cache[wlen] = xp
        return xp

    def _render_voice_numpy(self, v: _Voice, n: int, ar: np.ndarray,
                            idx_buf: np.ndarray) -> np.ndarray:
        wave = v.wave
        wlen = int(len(wave))
        step = float(v.freq) / float(self.sample_rate)
        pos = float(v.pos)
        vol = float(v.vol)
        ls = int(v.loop_start)
        le = int(v.loop_end)
        mode = int(v.loop_mode)
        if wlen == 0:
            return np.zeros(n, dtype=np.float32)
        if mode == 0 or le <= ls:
            np.multiply(ar, step, out=idx_buf)
            idx_buf += pos
            mono = np.interp(idx_buf, self._xp_for(wlen), wave).astype(
                np.float32, copy=False)
            if vol != 1.0:
                mono *= vol
            return mono
        span = le - ls
        if span <= 1:
            np.multiply(ar, step, out=idx_buf)
            idx_buf += pos
            mono = np.interp(idx_buf, self._xp_for(wlen), wave).astype(
                np.float32, copy=False)
            if vol != 1.0:
                mono *= vol
            return mono
        if pos >= ls:
            np.multiply(ar, step, out=idx_buf)
            idx_buf += pos
            idx_buf -= ls
            np.mod(idx_buf, span, out=idx_buf)
            if mode == 2:
                tri = np.minimum(idx_buf, span - idx_buf)
                idx_buf = ls + tri
            else:
                idx_buf += ls
            mono = np.interp(idx_buf, self._xp_for(wlen), wave).astype(
                np.float32, copy=False)
            if vol != 1.0:
                mono *= vol
            return mono
        t = pos + step * ar
        rel = np.mod(t - ls, span)
        tmod = ls + rel
        head = np.clip(t, 0, ls)
        idx = np.where(t < ls, head, tmod)
        if mode == 2:
            tri = np.minimum(rel, span - rel)
            idx = np.where(t < ls, head, ls + tri)
        idx = np.clip(idx, 0, wlen - 1.0)
        i0 = np.floor(idx).astype(np.int64)
        frac = idx - i0
        i1 = np.minimum(i0 + 1, wlen - 1)
        return (wave[i0] * (1.0 - frac) + wave[i1] * frac).astype(
            np.float32) * vol

    def _mix_tick(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        n = max(1, n)
        left = np.zeros(n, dtype=np.float32)
        right = np.zeros(n, dtype=np.float32)
        self._mix_tick_into(left, right)
        return left, right

    def _mix_tick_into(self, left: np.ndarray, right: np.ndarray) -> None:
        n = int(len(left))
        if n == 0:
            return
        gains = self.channel_gains
        fm = self._fastmix_mod()
        if fm is not None:
            try:
                for ch, v in enumerate(self.voices):
                    if not v.active:
                        continue
                    wlen = int(len(v.wave))
                    freq = float(v.freq)
                    if wlen == 0 or freq <= 0.0:
                        continue
                    vol = float(v.vol)
                    g = gains[ch] if ch < len(gains) else 1.0
                    vol_gain = vol * float(g)
                    if vol_gain <= 0.0:
                        v.pos += freq * n / self.sample_rate
                        if v.pos >= wlen:
                            if v.loop_mode != 0 and v.loop_start < v.loop_end:
                                span = v.loop_end - v.loop_start
                                if span > 0:
                                    v.pos = v.loop_start + (
                                        (v.pos - v.loop_start) % span)
                                else:
                                    v.active = False
                            else:
                                v.active = False
                        continue
                    pan = int(v.pan)
                    lg = math.sqrt(max(0.0, (255.0 - pan) / 255.0))
                    rg = math.sqrt(max(0.0, pan / 255.0))
                    try:
                        peak = float(fm.mix_add_voice(
                            v.wave, float(v.pos), freq / float(self.sample_rate),
                            float(vol_gain), int(v.loop_start), int(v.loop_end),
                            int(v.loop_mode), float(lg), float(rg),
                            left, right))
                    except Exception:
                        peak = self._mix_voice_numpy_into(
                            v, n, left, right, vol_gain, lg, rg)
                    if len(self._meter_block) <= ch:
                        self._meter_block.extend(
                            [0.0] * (ch + 1 - len(self._meter_block)))
                    if peak > self._meter_block[ch]:
                        self._meter_block[ch] = peak
                    v.pos += freq * n / self.sample_rate
                    if v.pos >= wlen:
                        if v.loop_mode != 0 and v.loop_start < v.loop_end:
                            span = v.loop_end - v.loop_start
                            if span > 0:
                                v.pos = v.loop_start + (
                                    (v.pos - v.loop_start) % span)
                            else:
                                v.active = False
                        else:
                            v.active = False
                self._meter_advance(n)
                return
            except Exception:
                pass
        ar = self._arange(n)
        idx_buf = self._idx_buf(n)
        tmp = self._tmp_buf(n)
        abs_buf = tmp
        for ch, v in enumerate(self.voices):
            if not v.active:
                continue
            wlen = int(len(v.wave))
            freq = float(v.freq)
            if wlen == 0 or freq <= 0.0 or float(v.vol) <= 0.0:
                v.pos += freq * n / self.sample_rate if freq > 0 else 0.0
                if v.pos >= wlen and wlen > 0:
                    if v.loop_mode != 0 and v.loop_start < v.loop_end:
                        span = v.loop_end - v.loop_start
                        if span > 0:
                            v.pos = v.loop_start + (
                                (v.pos - v.loop_start) % span)
                        else:
                            v.active = False
                    else:
                        v.active = False
                continue
            mono = self._render_voice_numpy(v, n, ar, idx_buf)
            g = gains[ch] if ch < len(gains) else 1.0
            if g != 1.0:
                mono = mono * float(g)
            try:
                np.abs(mono, out=abs_buf)
                peak = float(abs_buf.max()) if n else 0.0
            except Exception:
                peak = 0.0
            if len(self._meter_block) <= ch:
                self._meter_block.extend(
                    [0.0] * (ch + 1 - len(self._meter_block)))
            if peak > self._meter_block[ch]:
                self._meter_block[ch] = peak
            pan = int(v.pan)
            lg = math.sqrt(max(0.0, (255.0 - pan) / 255.0))
            rg = math.sqrt(max(0.0, pan / 255.0))
            np.multiply(mono, np.float32(lg), out=tmp)
            left += tmp
            np.multiply(mono, np.float32(rg), out=tmp)
            right += tmp
            v.pos += freq * n / self.sample_rate
            if v.pos >= wlen:
                if v.loop_mode != 0 and v.loop_start < v.loop_end:
                    span = v.loop_end - v.loop_start
                    if span > 0:
                        v.pos = v.loop_start + ((v.pos - v.loop_start) % span)
                    else:
                        v.active = False
                else:
                    v.active = False
        self._meter_advance(n)

    def _mix_voice_numpy_into(self, v: _Voice, n: int, left: np.ndarray,
                              right: np.ndarray, vol_gain: float,
                              lg: float, rg: float) -> float:
        ar = self._arange(n)
        idx_buf = self._idx_buf(n)
        tmp = self._tmp_buf(n)
        mono = self._render_voice_numpy(v, n, ar, idx_buf)
        if vol_gain != float(v.vol):
            try:
                base_vol = float(v.vol)
            except Exception:
                base_vol = 1.0
            if base_vol != 0.0:
                mono = mono * (vol_gain / base_vol)
            else:
                mono = mono * 0.0
        try:
            np.abs(mono, out=tmp)
            peak = float(tmp.max()) if n else 0.0
        except Exception:
            peak = 0.0
        np.multiply(mono, np.float32(lg), out=tmp)
        left += tmp
        np.multiply(mono, np.float32(rg), out=tmp)
        right += tmp
        return peak

    def _meter_advance(self, n: int):
        block_frames = max(1, int(self.sample_rate * self.METER_BLOCK_SEC))
        self._meter_cursor += n
        while self._meter_cursor >= block_frames:
            self._meter_cursor -= block_frames
            self._meter_blocks.append(list(self._meter_block))
            self._meter_block = [0.0] * max(1, self.n_channels)

    def _flush_meter(self):
        if any(self._meter_block):
            self._meter_blocks.append(list(self._meter_block))
        self._meter_block = [0.0] * max(1, self.n_channels)
        self._meter_cursor = 0
        self.meter_peaks = self._meter_blocks
        self.meter_block_sec = self.METER_BLOCK_SEC

    def _assemble(self, left: list, right: list) -> np.ndarray:
        self._flush_meter()
        if not left:
            return np.zeros((0, 2), dtype=np.int16)
        l_all = np.concatenate(left)
        r_all = np.concatenate(right)
        n = min(len(l_all), len(r_all))
        if self.master_gain != 1.0:
            l_all = l_all * self.master_gain
            r_all = r_all * self.master_gain
        peak = float(max(np.abs(l_all[:n]).max(), np.abs(r_all[:n]).max()))
        if peak > 1.0:
            l_all = l_all / peak
            r_all = r_all / peak
        l16 = np.clip(l_all[:n], -1.0, 1.0)
        r16 = np.clip(r_all[:n], -1.0, 1.0)
        stereo = np.empty((n, 2), dtype=np.float32)
        stereo[:, 0] = l16
        stereo[:, 1] = r16
        return (stereo * 32767.0).astype(np.int16)
