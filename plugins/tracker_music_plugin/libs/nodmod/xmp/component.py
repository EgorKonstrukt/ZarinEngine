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
from .header import XMSongHeaderMixin, _require_pydub
from .patterns import XMSongPatternsMixin
from .samples import XMSongSamplesMixin

class XMSong(XMSongHeaderMixin, XMSongPatternsMixin, XMSongSamplesMixin, Song):
    def save(self, fname: str, verbose: bool = True):
        if verbose:
            print(f'Saving to {fname}... ', end='', flush=True)
        data = bytearray()
        def str_to_bytes_padded(s: str, max_len: int, encoding: str = 'latin-1', pad: int = 0x00) -> bytes:
            r = bytes(s, encoding)
            if len(r) > max_len:
                r = r[:max_len]
            else:
                r += bytes([pad] * (max_len - len(r)))
            return r
        def period_to_note_byte(period: str) -> int:
            if period == '':
                return 0
            if period == 'off':
                return 97
            note_name = period[:2]
            octave = int(period[2:])
            note_idx = self.PERIOD_SEQ.index(note_name)
            return note_idx + (octave - 1) * 12 + 1
        def volume_to_byte(vol_cmd: str, vol_val: int) -> int:
            if vol_cmd == '':
                return 0
            if vol_cmd == 'v':
                return 0x10 + max(0, min(vol_val, 64))
            elif vol_cmd == 'd':
                return 0x60 + vol_val
            elif vol_cmd == 'c':
                return 0x70 + vol_val
            elif vol_cmd == 'b':
                return 0x80 + vol_val
            elif vol_cmd == 'a':
                return 0x90 + vol_val
            elif vol_cmd == 'u':
                return 0xA0 + vol_val
            elif vol_cmd == 'h':
                return 0xB0 + vol_val
            elif vol_cmd == 'p':
                return 0xC0 + (vol_val // 4)
            elif vol_cmd == 'l':
                return 0xD0 + vol_val
            elif vol_cmd == 'r':
                return 0xE0 + vol_val
            elif vol_cmd == 'g':
                return 0xF0 + vol_val
            return 0
        def effect_to_bytes(effect: str) -> tuple[int, int]:
            if effect == '':
                return 0, 0
            effect_char = effect[0]
            param_str = effect[1:] if len(effect) > 1 else '00'
            if effect_char.isdigit() or effect_char in 'ABCDF':
                effect_type = int(effect_char, 16)
            elif effect_char == 'E':
                effect_type = 0x0E
            elif effect_char == 'G':
                effect_type = 0x10
            elif effect_char == 'H':
                effect_type = 0x11
            elif effect_char == 'L':
                effect_type = 0x15
            elif effect_char == 'P':
                effect_type = 0x19
            elif effect_char == 'R':
                effect_type = 0x1B
            elif effect_char == 'K':
                effect_type = 0x14
            elif effect_char == 'T':
                effect_type = 0x1D
            elif effect_char == 'X':
                effect_type = 0x21
            else:
                effect_type = 0
            effect_param = int(param_str, 16) if param_str else 0
            return effect_type, effect_param
        data += b'Extended Module: '
        data += str_to_bytes_padded(self.songname, 20, pad=0x20)
        data += bytes([0x1A])
        data += str_to_bytes_padded(self.tracker_name, 20, pad=0x20)
        data += bytes([0x04, 0x01])
        header_size = 276
        data += header_size.to_bytes(4, byteorder='little')
        data += len(self.pattern_seq).to_bytes(2, byteorder='little')
        data += self.song_restart.to_bytes(2, byteorder='little')
        data += self.n_channels.to_bytes(2, byteorder='little')
        data += len(self.patterns).to_bytes(2, byteorder='little')
        data += len(self.instruments).to_bytes(2, byteorder='little')
        data += self.flags.to_bytes(2, byteorder='little')
        data += self.default_speed.to_bytes(2, byteorder='little')
        data += self.default_tempo.to_bytes(2, byteorder='little')
        pattern_order = bytearray(256)
        for i, p in enumerate(self.pattern_seq):
            if i < 256:
                pattern_order[i] = p
        data += pattern_order
        for pat in self.patterns:
            packed_pattern = bytearray()
            for r in range(pat.n_rows):
                for c in range(pat.n_channels):
                    note = pat.data[c][r]
                    note_byte = period_to_note_byte(note.period)
                    inst_byte = note.instrument_idx
                    vol_cmd = getattr(note, 'vol_cmd', '')
                    vol_val = getattr(note, 'vol_val', -1)
                    vol_byte = volume_to_byte(vol_cmd, vol_val)
                    efx_type, efx_param = effect_to_bytes(note.effect)
                    has_note = note_byte != 0
                    has_inst = inst_byte != 0
                    has_vol = vol_byte != 0
                    has_efx = efx_type != 0
                    has_param = efx_param != 0
                    all_fields_present = has_note and has_inst and has_vol and has_efx and has_param
                    can_use_unpacked = note_byte > 0 and note_byte < 0x80
                    if all_fields_present and can_use_unpacked:
                        packed_pattern.append(note_byte)
                        packed_pattern.append(inst_byte)
                        packed_pattern.append(vol_byte)
                        packed_pattern.append(efx_type)
                        packed_pattern.append(efx_param)
                    else:
                        pack_byte = 0x80
                        if has_note:
                            pack_byte |= 0x01
                        if has_inst:
                            pack_byte |= 0x02
                        if has_vol:
                            pack_byte |= 0x04
                        if has_efx:
                            pack_byte |= 0x08
                        if has_param:
                            pack_byte |= 0x10
                        packed_pattern.append(pack_byte)
                        if has_note:
                            packed_pattern.append(note_byte)
                        if has_inst:
                            packed_pattern.append(inst_byte)
                        if has_vol:
                            packed_pattern.append(vol_byte)
                        if has_efx:
                            packed_pattern.append(efx_type)
                        if has_param:
                            packed_pattern.append(efx_param)
            data += (9).to_bytes(4, byteorder='little')
            data += bytes([0])
            data += pat.n_rows.to_bytes(2, byteorder='little')
            data += len(packed_pattern).to_bytes(2, byteorder='little')
            data += packed_pattern
        for inst in self.instruments:
            n_samples = len(inst.samples)
            if n_samples == 0:
                inst_header_size = inst._header_size if inst._header_size > 0 else 29
                data += inst_header_size.to_bytes(4, byteorder='little')
                data += str_to_bytes_padded(inst.name, 22)
                data += bytes([inst._type])
                data += (0).to_bytes(2, byteorder='little')
                extra_bytes = inst_header_size - 29
                if extra_bytes > 0:
                    data += (40).to_bytes(4, byteorder='little')
                    extra_bytes -= 4
                    if extra_bytes > 0:
                        data += bytes(extra_bytes)
            else:
                inst_header_size = 263
                data += inst_header_size.to_bytes(4, byteorder='little')
                data += str_to_bytes_padded(inst.name, 22)
                data += bytes([inst._type])
                data += n_samples.to_bytes(2, byteorder='little')
                sample_header_size = 40
                data += sample_header_size.to_bytes(4, byteorder='little')
                sample_map = bytearray(96)
                for i, s in enumerate(inst.sample_map[:96]):
                    sample_map[i] = s
                data += sample_map
                vol_env_data = bytearray(48)
                for i, point in enumerate(inst.volume_envelope[:12]):
                    vol_env_data[i * 4:i * 4 + 2] = point.frame.to_bytes(2, byteorder='little')
                    vol_env_data[i * 4 + 2:i * 4 + 4] = point.value.to_bytes(2, byteorder='little')
                data += vol_env_data
                pan_env_data = bytearray(48)
                for i, point in enumerate(inst.panning_envelope[:12]):
                    pan_env_data[i * 4:i * 4 + 2] = point.frame.to_bytes(2, byteorder='little')
                    pan_env_data[i * 4 + 2:i * 4 + 4] = point.value.to_bytes(2, byteorder='little')
                data += pan_env_data
                data += bytes([len(inst.volume_envelope)])
                data += bytes([len(inst.panning_envelope)])
                data += bytes([inst.volume_sustain_point])
                data += bytes([inst.volume_loop_start])
                data += bytes([inst.volume_loop_end])
                data += bytes([inst.panning_sustain_point])
                data += bytes([inst.panning_loop_start])
                data += bytes([inst.panning_loop_end])
                data += bytes([inst.volume_type])
                data += bytes([inst.panning_type])
                data += bytes([inst.vibrato_type])
                data += bytes([inst.vibrato_sweep])
                data += bytes([inst.vibrato_depth])
                data += bytes([inst.vibrato_rate])
                data += inst.volume_fadeout.to_bytes(2, byteorder='little')
                data += bytes(22)
                for sample in inst.samples:
                    sample_len_bytes = len(sample.waveform) * (2 if sample.is_16bit else 1)
                    if sample.is_16bit:
                        loop_start_bytes = sample.repeat_point * 2
                        loop_len_bytes = sample.repeat_len * 2
                    else:
                        loop_start_bytes = sample.repeat_point
                        loop_len_bytes = sample.repeat_len
                    data += sample_len_bytes.to_bytes(4, byteorder='little')
                    data += loop_start_bytes.to_bytes(4, byteorder='little')
                    data += loop_len_bytes.to_bytes(4, byteorder='little')
                    data += bytes([sample.volume])
                    finetune = sample.finetune
                    if finetune < 0:
                        finetune += 256
                    data += bytes([finetune])
                    sample_type = sample.loop_type & 0x03
                    if sample.is_16bit:
                        sample_type |= 0x10
                    data += bytes([sample_type])
                    data += bytes([sample.panning])
                    rel_note = sample.relative_note
                    if rel_note < 0:
                        rel_note += 256
                    data += bytes([rel_note])
                    data += bytes([sample._reserved])
                    data += str_to_bytes_padded(sample.name, 22)
                for sample in inst.samples:
                    if len(sample.waveform) == 0:
                        continue
                    if sample.is_16bit:
                        old = 0
                        for val in sample.waveform:
                            delta = (val - old) & 0xFFFF
                            if delta > 32767:
                                delta -= 65536
                            data += delta.to_bytes(2, byteorder='little', signed=True)
                            old = val
                    else:
                        old = 0
                        for val in sample.waveform:
                            delta = (val - old) & 0xFF
                            data += bytes([delta])
                            old = val
        with open(fname, 'wb') as f:
            f.write(data)
        if verbose:
            print('done.')
    def set_bpm(self, pattern: int, channel: int, row: int, bpm: int):
        if bpm < 32 or bpm > 255:
            raise ValueError(f"Invalid tempo {bpm} (expected 32-255).")
        self.set_effect(pattern, channel, row, f"F{bpm:02X}")
    def set_ticks_per_row(self, pattern: int, channel: int, row: int, ticks: int):
        if ticks < 1 or ticks > 31:
            raise ValueError(f"Invalid ticks per row {ticks} (expected 1-31).")
        self.set_effect(pattern, channel, row, f"F{ticks:02X}")
    def set_global_volume(self, pattern: int, channel: int, row: int, volume: int):
        if volume < 0 or volume > 64:
            raise ValueError(f"Invalid global volume {volume} (expected 0-64).")
        self.set_effect(pattern, channel, row, f"G{volume:02X}")
    def set_global_volume_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid global volume slide {slide} (expected -15 to 15).")
        effect_value = 0
        if slide > 0:
            effect_value = slide << 4
        elif slide < 0:
            effect_value = -slide
        self.set_effect(pattern, channel, row, f"H{effect_value:02X}")
    def set_key_off(self, pattern: int, channel: int, row: int, ticks: int):
        if ticks < 0 or ticks > 255:
            raise ValueError(f"Invalid key-off tick {ticks} (expected 0-255).")
        self.set_effect(pattern, channel, row, f"K{ticks:02X}")
    def set_envelope_position(self, pattern: int, channel: int, row: int, pos: int):
        if pos < 0 or pos > 255:
            raise ValueError(f"Invalid envelope position {pos} (expected 0-255).")
        self.set_effect(pattern, channel, row, f"L{pos:02X}")
    def set_panning_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid panning slide {slide} (expected -15 to 15).")
        if slide > 0:
            effect = f"P{slide:X}0"
        elif slide < 0:
            effect = f"P0{-slide:X}"
        else:
            effect = "P00"
        self.set_effect(pattern, channel, row, effect)
    def set_retrigger_volume_slide(self, pattern: int, channel: int, row: int, volume_slide: int, interval: int):
        if volume_slide < 0 or volume_slide > 15:
            raise ValueError(f"Invalid retrigger volume slide {volume_slide} (expected 0-15).")
        if interval < 0 or interval > 15:
            raise ValueError(f"Invalid retrigger interval {interval} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"R{volume_slide:X}{interval:X}")
    def set_tremor(self, pattern: int, channel: int, row: int, on_ticks: int, off_ticks: int):
        if on_ticks < 0 or on_ticks > 15 or off_ticks < 0 or off_ticks > 15:
            raise ValueError("Tremor values must be in the range 0-15.")
        self.set_effect(pattern, channel, row, f"T{on_ticks:X}{off_ticks:X}")
    def set_extra_fine_portamento(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid extra-fine portamento {slide} (expected -15 to 15).")
        if slide > 0:
            self.set_effect(pattern, channel, row, f"X1{slide:X}")
        elif slide < 0:
            self.set_effect(pattern, channel, row, f"X2{-slide:X}")
        else:
            self.set_effect(pattern, channel, row, "X10")
    def save_sample(
        self,
        inst_idx: int,
        sample_idx: int,
        fname: str,
        sample_rate: int | None = None,
        force_sample_rate: int | None = None,
    ):
        smp = self.get_sample(inst_idx, sample_idx)
        if sample_rate is None:
            sample_rate = 8363
        if len(smp.waveform) == 0:
            raise ValueError(f"Sample {sample_idx} has no waveform data")
        sample_width = 2 if smp.is_16bit else 1
        pydub = _require_pydub()
        audio = pydub.AudioSegment(
            data=smp.waveform.tobytes(),
            sample_width=sample_width,
            frame_rate=sample_rate,
            channels=1,
        )
        if force_sample_rate is not None and force_sample_rate != sample_rate:
            audio = audio.set_frame_rate(force_sample_rate)
        audio.export(fname, format="wav")
    def add_to_sequence(self, pattern_idx: int, sequence_position: int | None = None) -> None:
        if len(self.pattern_seq) + 1 > 256:
            raise ValueError(f"Pattern sequence too long ({len(self.pattern_seq) + 1}). XM supports up to 256.")
        super().add_to_sequence(pattern_idx, sequence_position)
    def set_sequence(self, seq: list[int]) -> None:
        if len(seq) > 256:
            raise ValueError(f"Pattern sequence too long ({len(seq)}). XM supports up to 256.")
        super().set_sequence(seq)
    def resize_pattern(self, sequence_idx: int, n_rows: int) -> None:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        if n_rows < 1 or n_rows > 256:
            raise ValueError(f"Invalid row count {n_rows} (expected 1-256).")
        p = self.pattern_seq[sequence_idx]
        pat = self.patterns[p]
        if n_rows == pat.n_rows:
            return
        if n_rows < pat.n_rows:
            for c in range(pat.n_channels):
                pat.data[c] = pat.data[c][:n_rows]
        else:
            for c in range(pat.n_channels):
                pat.data[c].extend([XMNote() for _ in range(n_rows - pat.n_rows)])
        pat.n_rows = n_rows
    def clear_pattern(self, sequence_idx: int):
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        p = self.pattern_seq[sequence_idx]
        pat = self.patterns[p]
        for r in range(pat.n_rows):
            for c in range(pat.n_channels):
                pat.data[c][r] = XMNote()
    def add_pattern(self, n_rows: int = 64) -> int:
        if n_rows < 1 or n_rows > 256:
            raise ValueError(f"Invalid row count {n_rows}. XM supports 1-256 rows.")
        pat = Pattern(n_rows, self.n_channels)
        for c in range(self.n_channels):
            for r in range(n_rows):
                pat.data[c][r] = XMNote()
        self.patterns.append(pat)
        n = len(self.patterns) - 1
        self.pattern_seq.append(n)
        return n
    def get_effective_row_count(self, sequence_idx: int, include_loops: bool = True) -> int:
        if sequence_idx < 0 or sequence_idx >= len(self.pattern_seq):
            raise IndexError(f"Invalid sequence index {sequence_idx} (expected 0-{len(self.pattern_seq)-1}).")
        loop_start_row = 0
        data = copy.deepcopy(self.patterns[self.pattern_seq[sequence_idx]].data)
        n_channels = len(data)
        n_rows = len(data[0]) if data else 0
        unrolled_data = [[] for _ in range(n_channels)]
        for r in range(n_rows):
            interrupt = False
            for c in range(n_channels):
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
                        for _ in range(loop_count):
                            unrolled_data[c] += unrolled_data[c][loop_start_row:loop_end_row + 1]
            if interrupt:
                break
        return max([len(unrolled_data[c]) for c in range(n_channels)]) if n_channels > 0 else 0
    def get_pattern_duration(self, pattern: int) -> float:
        raise NotImplementedError("XMSong.get_pattern_duration() is not implemented.")
