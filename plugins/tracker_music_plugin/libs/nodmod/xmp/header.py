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

def _require_pydub():
    try:
        import pydub
    except ImportError as exc:
        missing = getattr(exc, "name", "")
        if missing in {"audioop", "pyaudioop"}:
            raise ImportError(
                "WAV sample I/O requires audioop compatibility on this Python. "
                "Install `audioop-lts`."
            ) from exc
        raise ImportError("WAV sample I/O requires `pydub`.") from exc
    return pydub

class XMSongHeaderMixin:
    PRESERVED_EFFECT_PREFIXES = Song.PRESERVED_EFFECT_PREFIXES | frozenset({'G', 'H'})
    @property
    def file_extension(self) -> str:
        return 'xm'
    @property
    def uses_linear_frequency(self) -> bool:
        return (self.flags & 0x01) == 1
    @property
    def n_channels(self) -> int:
        return self._n_channels
    @n_channels.setter
    def n_channels(self, n: int) -> None:
        if n < 1 or n > 32:
            raise ValueError(f"Invalid channel count {n} (expected 1-32).")
        self._n_channels = n
        for pat in self.patterns:
            if pat.n_channels < n:
                for _ in range(n - pat.n_channels):
                    pat.data.append([XMNote() for _ in range(pat.n_rows)])
            elif pat.n_channels > n:
                pat.data = pat.data[:n]
            pat.n_channels = n
    def _note_str_to_idx(self, note: str | int) -> int:
        return Song.note_to_index(note)
    def __init__(self):
        super().__init__()
        self.instruments: list[Instrument] = []
        self.n_instruments = 0
        self.tracker_name = ""
        self.song_restart = 0
        self.flags = 0
        self.default_speed = 6
        self.default_tempo = 125
        self.n_channels = 8
        self.add_pattern()
    def set_default_speed(self, speed: int) -> None:
        if speed < 1 or speed > 31:
            raise ValueError(f"Invalid default speed {speed} (expected 1-31).")
        self.default_speed = speed
    def set_default_tempo(self, bpm: int) -> None:
        if bpm < 32 or bpm > 255:
            raise ValueError(f"Invalid default tempo {bpm} (expected 32-255).")
        self.default_tempo = bpm
    def set_song_restart(self, song_restart_position: int) -> None:
        if song_restart_position < 0 or song_restart_position >= len(self.pattern_seq):
            raise IndexError(
                f"Invalid song restart position {song_restart_position} (expected 0-{len(self.pattern_seq)-1})."
            )
        self.song_restart = song_restart_position
    def set_linear_frequency(self, on: bool) -> None:
        if on:
            self.flags |= 0x01
        else:
            self.flags &= ~0x01
    def set_n_channels(self, n: int) -> None:
        self.n_channels = n
    def save_ascii(self, fname: str, verbose: bool = True):
        if verbose:
            print(f'Saving to {fname}... ', end='', flush=True)
        with open(fname, 'w', encoding='ascii') as file:
            file.write(self.to_ascii(sequence_only=True, include_headers=True))
        if verbose:
            print('done.')
    def load(self, fname: str, verbose: bool = True):
        if verbose:
            print(f'Loading {fname}... ', end='', flush=True)
        with (open(fname, 'rb') as xm_file):
            data = bytearray(xm_file.read())
            header = data[:60]
            magic_string = header[:17].decode('ascii')
            if magic_string != "Extended Module: ":
                raise NotImplementedError(f"Not an XM module. Magic string: {magic_string}.")
            self.songname = header[17:37].decode('latin-1').rstrip(' \x00')
            if header[37] != 0x1A:
                raise NotImplementedError("Invalid XM file format (header mismatch).")
            self.tracker_name = header[38:58].decode('latin-1').rstrip(' \x00')
            version = int.from_bytes(header[58:60], byteorder='little', signed=False)
            if version < 0x0104:
                raise NotImplementedError(f"Unsupported XM version {version} (expected 0x0104).")
            header_size = int.from_bytes(data[60:64], byteorder='little', signed=False)
            self.song_restart = int.from_bytes(data[66:68], byteorder='little', signed=False)
            self.n_channels = int.from_bytes(data[68:70], byteorder='little', signed=False)
            if self.n_channels > 32:
                raise NotImplementedError(f"Too many channels: {self.n_channels} (XM supports 1-32).")
            self.n_instruments = int.from_bytes(data[72:74], byteorder='little', signed=False)
            if self.n_instruments > 256:
                raise NotImplementedError(f"Too many instruments: {self.n_instruments} (expected 1-256).")
            self.instruments = [Instrument() for _ in range(self.n_instruments)]
            self.flags = int.from_bytes(data[74:76], byteorder='little', signed=False)
            self.default_speed = int.from_bytes(data[76:78], byteorder='little', signed=False)
            self.default_tempo = int.from_bytes(data[78:80], byteorder='little', signed=False)
            song_length = int.from_bytes(data[64:66], byteorder='little', signed=False)
            self.pattern_seq = [0] * song_length
            for p in range(song_length):
                self.pattern_seq[p] = data[80 + p]
            n_unique_patterns = int.from_bytes(data[70:72], byteorder='little', signed=False)
            if n_unique_patterns > 256:
                raise NotImplementedError(f"Too many patterns: {n_unique_patterns} (XM supports 1-256).")
            def get_period(note_byte, pat_num, row, chan) -> str:
                note_val = note_byte & 0x7F
                if note_val == 0:
                    period_ = ''
                elif note_val <= 96:
                    note_idx = (note_val - 1) % 12
                    octave = (note_val - 1) // 12 + 1
                    period_ = f"{self.PERIOD_SEQ[note_idx]}{octave}"
                elif note_val == 97:
                    period_ = 'off'
                else:
                    if verbose:
                        warnings.warn(f"Non-standard note value {note_val} at pattern {pat_num}, row {row}, channel {chan}. Ignoring.")
                    period_ = ''
                return period_
            def get_instrument(instrument_byte, pat_num, row, chan) -> int:
                if instrument_byte > 256:
                    return 0
                return instrument_byte
            def get_volume(volume_byte) -> tuple[str, int]:
                volume_cmd = ''
                volume_val = 0
                cmd_nibble = volume_byte & 0xF0
                val_nibble = volume_byte & 0x0F
                if volume_byte == 0:
                    pass
                elif volume_byte < 0x10:
                    pass
                elif cmd_nibble >= 0x10 and cmd_nibble <= 0x40:
                    volume_cmd = 'v'
                    volume_val = volume_byte - 0x10
                elif volume_byte == 0x50:
                    volume_cmd = 'v'
                    volume_val = 64
                elif volume_byte > 0x50 and volume_byte < 0x60:
                    pass
                elif cmd_nibble == 0x60:
                    volume_cmd = 'd'
                    volume_val = val_nibble
                elif cmd_nibble == 0x70:
                    volume_cmd = 'c'
                    volume_val = val_nibble
                elif cmd_nibble == 0x80:
                    volume_cmd = 'b'
                    volume_val = val_nibble
                elif cmd_nibble == 0x90:
                    volume_cmd = 'a'
                    volume_val = val_nibble
                elif cmd_nibble == 0xA0:
                    volume_cmd = 'u'
                    volume_val = val_nibble
                elif cmd_nibble == 0xB0:
                    volume_cmd = 'h'
                    volume_val = val_nibble
                elif cmd_nibble == 0xC0:
                    volume_cmd = 'p'
                    volume_val = val_nibble * 4
                elif cmd_nibble == 0xD0:
                    volume_cmd = 'l'
                    volume_val = val_nibble
                elif cmd_nibble == 0xE0:
                    volume_cmd = 'r'
                    volume_val = val_nibble
                elif cmd_nibble == 0xF0:
                    volume_cmd = 'g'
                    volume_val = val_nibble
                return volume_cmd, volume_val
            def get_efx_type(effect_byte, pat_num, row, chan) -> str:
                if effect_byte <= 0x0D or effect_byte == 0x0F:
                    efx = f"{effect_byte:01X}"
                elif effect_byte == 0x0E:
                    efx = "E"
                elif effect_byte == 0x10:
                    efx = "G"
                elif effect_byte == 0x11:
                    efx = "H"
                elif effect_byte == 0x15:
                    efx = "L"
                elif effect_byte == 0x19:
                    efx = "P"
                elif effect_byte == 0x1B:
                    efx = "R"
                elif effect_byte == 0x14:
                    efx = "K"
                elif effect_byte == 0x1D:
                    efx = "T"
                elif effect_byte == 0x21:
                    efx = "X"
                else:
                    if verbose:
                        warnings.warn(f"Non-standard effect type {effect_byte:02X} at pattern {pat_num}, row {row}, channel {chan}. Ignoring.")
                    efx = ""
                return efx
            def get_efx_param(effect_type, effect_param_byte):
                if effect_type == "E" or effect_type == "X":
                    sub_effect = (effect_param_byte >> 4) & 0x0F
                    param = effect_param_byte & 0x0F
                    return f"{sub_effect:01X}{param:01X}"
                else:
                    return f"{effect_param_byte:02X}"
            self.patterns = []
            pattern_data = data[60 + header_size:]
            cur_pat_idx = 0
            for p in range(n_unique_patterns):
                if pattern_data[cur_pat_idx:cur_pat_idx + 4][0] != 9:
                    raise NotImplementedError(f"Unsupported pattern header length {pattern_data[cur_pat_idx:cur_pat_idx + 4][0]} (expected 9).")
                if pattern_data[cur_pat_idx+4] != 0:
                    raise NotImplementedError("Unsupported packing type (expected 0).")
                n_rows = int.from_bytes(pattern_data[cur_pat_idx+5:cur_pat_idx+7], byteorder='little', signed=False)
                pattern_data_size = int.from_bytes(pattern_data[cur_pat_idx+7:cur_pat_idx+9], byteorder='little', signed=False)
                pat = Pattern(n_rows, self.n_channels)
                if pattern_data_size == 0:
                    for c in range(self.n_channels):
                        for r in range(n_rows):
                            pat.data[c][r] = XMNote()
                    self.patterns.append(pat)
                    cur_pat_idx += 9
                    continue
                c = 0
                r = 0
                byte_idx = cur_pat_idx + 9
                while True:
                    packed_byte = pattern_data[byte_idx]
                    instrument = 0
                    effect = ''
                    period = ''
                    volume_cmd = ''
                    volume_val = -1
                    is_packed = packed_byte & 0x80
                    if is_packed:
                        if packed_byte & 0x01:
                            byte_idx += 1
                            period = get_period(pattern_data[byte_idx], p, r, c)
                    elif not is_packed:
                        period = get_period(packed_byte, p, r, c)
                    if not is_packed or (is_packed and packed_byte & 0x02):
                        byte_idx += 1
                        instrument = get_instrument(pattern_data[byte_idx], p, r, c)
                    if not is_packed or (is_packed and packed_byte & 0x04):
                        byte_idx += 1
                        volume_cmd, volume_val = get_volume(pattern_data[byte_idx])
                    has_effect_byte = not is_packed or (is_packed and packed_byte & 0x08)
                    if has_effect_byte:
                        byte_idx += 1
                        effect = get_efx_type(pattern_data[byte_idx], p, r, c)
                    if not is_packed or (is_packed and packed_byte & 0x10):
                        byte_idx += 1
                        if effect == '' and not has_effect_byte:
                            effect = '0'
                        if effect != '':
                            effect = f"{effect}{get_efx_param(effect, pattern_data[byte_idx])}"
                    note = XMNote()
                    note.instrument_idx = instrument
                    note.period = period
                    note.effect = effect
                    note.vol_cmd = volume_cmd
                    note.vol_val = volume_val
                    pat.data[c][r] = note
                    byte_idx += 1
                    c += 1
                    if c == self.n_channels:
                        c = 0
                        r += 1
                    if byte_idx == cur_pat_idx + 9 + pattern_data_size:
                        break
                self.patterns.append(pat)
                cur_pat_idx += 9 + pattern_data_size
            instrument_data = pattern_data[cur_pat_idx:]
            cur_inst_idx = 0
            for i in range(self.n_instruments):
                inst_header_size = int.from_bytes(
                    instrument_data[cur_inst_idx:cur_inst_idx + 4],
                    byteorder='little', signed=False
                )
                self.instruments[i]._header_size = inst_header_size
                name_bytes = instrument_data[cur_inst_idx + 4:cur_inst_idx + 26]
                self.instruments[i].name = name_bytes.decode('latin-1').rstrip('\x00')
                self.instruments[i]._type = instrument_data[cur_inst_idx + 26]
                n_samples = int.from_bytes(
                    instrument_data[cur_inst_idx + 27:cur_inst_idx + 29],
                    byteorder='little', signed=False
                )
                if verbose:
                    print(f"Instrument {i + 1}: '{self.instruments[i].name}' ({n_samples} samples)")
                total_inst_size = inst_header_size
                if n_samples > 0:
                    ext_offset = cur_inst_idx + 29
                    sample_header_size = int.from_bytes(
                        instrument_data[ext_offset:ext_offset + 4],
                        byteorder='little', signed=False
                    )
                    sample_map_bytes = instrument_data[ext_offset + 4:ext_offset + 100]
                    self.instruments[i].sample_map = list(sample_map_bytes)
                    vol_env_bytes = instrument_data[ext_offset + 100:ext_offset + 148]
                    pan_env_bytes = instrument_data[ext_offset + 148:ext_offset + 196]
                    n_vol_points = instrument_data[ext_offset + 196]
                    n_pan_points = instrument_data[ext_offset + 197]
                    for p in range(n_vol_points):
                        frame = int.from_bytes(vol_env_bytes[p * 4:p * 4 + 2], byteorder='little', signed=False)
                        value = int.from_bytes(vol_env_bytes[p * 4 + 2:p * 4 + 4], byteorder='little', signed=False)
                        self.instruments[i].volume_envelope.append(EnvelopePoint(frame, value))
                    for p in range(n_pan_points):
                        frame = int.from_bytes(pan_env_bytes[p * 4:p * 4 + 2], byteorder='little', signed=False)
                        value = int.from_bytes(pan_env_bytes[p * 4 + 2:p * 4 + 4], byteorder='little', signed=False)
                        self.instruments[i].panning_envelope.append(EnvelopePoint(frame, value))
                    self.instruments[i].volume_sustain_point = instrument_data[ext_offset + 198]
                    self.instruments[i].volume_loop_start = instrument_data[ext_offset + 199]
                    self.instruments[i].volume_loop_end = instrument_data[ext_offset + 200]
                    self.instruments[i].panning_sustain_point = instrument_data[ext_offset + 201]
                    self.instruments[i].panning_loop_start = instrument_data[ext_offset + 202]
                    self.instruments[i].panning_loop_end = instrument_data[ext_offset + 203]
                    self.instruments[i].volume_type = instrument_data[ext_offset + 204]
                    self.instruments[i].panning_type = instrument_data[ext_offset + 205]
                    self.instruments[i].vibrato_type = instrument_data[ext_offset + 206]
                    self.instruments[i].vibrato_sweep = instrument_data[ext_offset + 207]
                    self.instruments[i].vibrato_depth = instrument_data[ext_offset + 208]
                    self.instruments[i].vibrato_rate = instrument_data[ext_offset + 209]
                    self.instruments[i].volume_fadeout = int.from_bytes(
                        instrument_data[ext_offset + 210:ext_offset + 212],
                        byteorder='little', signed=False
                    )
                    self.instruments[i].samples = [XMSample() for _ in range(n_samples)]
                    sample_headers_start = cur_inst_idx + inst_header_size
                    total_sample_data_size = 0
                    sample_lengths = []
                    sample_is_16bit = []
                    for s in range(n_samples):
                        sample_hdr_offset = sample_headers_start + s * sample_header_size
                        sample_length = int.from_bytes(
                            instrument_data[sample_hdr_offset:sample_hdr_offset + 4],
                            byteorder='little', signed=False
                        )
                        loop_start = int.from_bytes(
                            instrument_data[sample_hdr_offset + 4:sample_hdr_offset + 8],
                            byteorder='little', signed=False
                        )
                        loop_length = int.from_bytes(
                            instrument_data[sample_hdr_offset + 8:sample_hdr_offset + 12],
                            byteorder='little', signed=False
                        )
                        volume = instrument_data[sample_hdr_offset + 12]
                        finetune = instrument_data[sample_hdr_offset + 13]
                        if finetune > 127:
                            finetune -= 256
                        sample_type = instrument_data[sample_hdr_offset + 14]
                        loop_type = sample_type & 0x03
                        is_16bit = bool(sample_type & 0x10)
                        panning = instrument_data[sample_hdr_offset + 15]
                        relative_note = instrument_data[sample_hdr_offset + 16]
                        if relative_note > 127:
                            relative_note -= 256
                        reserved = instrument_data[sample_hdr_offset + 17]
                        sample_name = instrument_data[sample_hdr_offset + 18:sample_hdr_offset + 40]
                        sample = self.instruments[i].samples[s]
                        sample.name = sample_name.decode('latin-1').rstrip('\x00')
                        sample.volume = volume
                        sample.finetune = finetune
                        sample.panning = panning
                        sample.relative_note = relative_note
                        sample._reserved = reserved
                        sample.loop_type = loop_type
                        sample.is_16bit = is_16bit
                        if is_16bit:
                            sample.repeat_point = loop_start // 2
                            sample.repeat_len = loop_length // 2
                        else:
                            sample.repeat_point = loop_start
                            sample.repeat_len = loop_length
                        sample_lengths.append(sample_length)
                        sample_is_16bit.append(is_16bit)
                        total_sample_data_size += sample_length
                    sample_data_start = sample_headers_start + n_samples * sample_header_size
                    sample_data_offset = 0
                    for s in range(n_samples):
                        sample = self.instruments[i].samples[s]
                        sample_length = sample_lengths[s]
                        is_16bit = sample_is_16bit[s]
                        if sample_length == 0:
                            continue
                        raw_data = instrument_data[
                            sample_data_start + sample_data_offset:
                            sample_data_start + sample_data_offset + sample_length
                        ]
                        if is_16bit:
                            n_samples_count = sample_length // 2
                            sample.waveform = array.array('h')
                            old = 0
                            for j in range(n_samples_count):
                                delta = int.from_bytes(
                                    raw_data[j * 2:j * 2 + 2],
                                    byteorder='little', signed=True
                                )
                                new_val = (old + delta) & 0xFFFF
                                if new_val > 32767:
                                    new_val -= 65536
                                sample.waveform.append(new_val)
                                old = new_val
                        else:
                            sample.waveform = array.array('b')
                            old = 0
                            for j in range(sample_length):
                                delta = raw_data[j]
                                if delta > 127:
                                    delta -= 256
                                new_val = (old + delta) & 0xFF
                                if new_val > 127:
                                    new_val -= 256
                                sample.waveform.append(new_val)
                                old = new_val & 0xFF
                        sample_data_offset += sample_length
                    total_inst_size = inst_header_size + n_samples * sample_header_size + total_sample_data_size
                cur_inst_idx += total_inst_size
        if verbose:
            print('done.')
