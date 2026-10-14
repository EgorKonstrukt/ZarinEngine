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
class _P:
    def __getattr__(self, n):
        from .component import MODSong
        return getattr(MODSong, n)
MODSong = _P()

class MODSongHeaderMixin:
    ROWS = 64

    CHANNELS = 4

    SAMPLES = 31

    PAL_CLOCK = 7093789.2

    NTSC_SR = 8287

    PERIOD_TABLE = {
            3424: 'C-2', 3232: 'C#2', 3048: 'D-2', 2880: 'D#2', 2712: 'E-2', 2560: 'F-2', 2416: 'F#2', 2280: 'G-2',
            2152: 'G#2', 2032: 'A-2', 1920: 'A#2', 1812: 'B-2',
            1712: 'C-3', 1616: 'C#3', 1524: 'D-3', 1440: 'D#3', 1356: 'E-3', 1280: 'F-3', 1208: 'F#3', 1140: 'G-3',
            1076: 'G#3', 1016: 'A-3', 960: 'A#3', 906: 'B-3',
            856: 'C-4', 808: 'C#4', 762: 'D-4', 720: 'D#4', 678: 'E-4', 640: 'F-4', 604: 'F#4', 570: 'G-4', 538: 'G#4',
            508: 'A-4', 480: 'A#4', 453: 'B-4',
            428: 'C-5', 404: 'C#5', 381: 'D-5', 360: 'D#5', 339: 'E-5', 320: 'F-5', 302: 'F#5', 285: 'G-5', 269: 'G#5',
            254: 'A-5', 240: 'A#5', 226: 'B-5',
            214: 'C-6', 202: 'C#6', 190: 'D-6', 180: 'D#6', 170: 'E-6', 160: 'F-6', 151: 'F#6', 143: 'G-6', 135: 'G#6',
            127: 'A-6', 120: 'A#6', 113: 'B-6',
            107: 'C-7', 101: 'C#7', 95: 'D-7', 90: 'D#7', 85: 'E-7', 80: 'F-7', 75: 'F#7', 71: 'G-7', 67: 'G#7', 63: 'A-7',
            60: 'A#7', 56: 'B-7',
            53: 'C-8', 50: 'C#8', 47: 'D-8', 45: 'D#8', 42: 'E-8', 40: 'F-8', 37: 'F#8', 35: 'G-8', 33: 'G#8', 31: 'A-8',
            30: 'A#8', 28: 'B-8'
        }

    INV_PERIOD_TABLE = {value: key for key, value in PERIOD_TABLE.items()}

    @property
    def n_channels(self) -> int:
        return self.CHANNELS

    @property
    def file_extension(self) -> str:
        return 'mod'

    def __init__(self):
        super().__init__()
        self.patterns = [Pattern(n_rows=MODSong.ROWS, n_channels=MODSong.CHANNELS)]
        self.pattern_seq = [0]
        self.samples = [Sample() for _ in range(MODSong.SAMPLES)]
        self.n_actual_samples = 0
        self._restart_position_raw = 127
        self._resolution_version = 0
        self._resolved_sequence_cache_version = -1
        self._resolved_reachable_cache_version = -1
        self._resolved_sequence_cells: dict[tuple[int, int, int], int] = {}
        self._resolved_sequence_first_use: list[int] = []
        self._resolved_reachable_cells: dict[tuple[int, int], int] = {}
        self._resolved_reachable_first_use: list[int] = []
        self._resolved_reachable_rows: tuple[PlaybackRowView, ...] = ()

    def _update_n_actual_samples(self) -> None:
        self.n_actual_samples = sum(1 for sample in self.samples if len(sample.waveform) > 0)

    def _on_mutation(self) -> None:
        self._resolution_version += 1

    @staticmethod
    def _resolve_effective_sample(raw_sample: int, period: str, latched_sample: int) -> tuple[int, int]:
        if raw_sample > 0:
            latched_sample = raw_sample
        if period != '':
            if raw_sample > 0:
                return raw_sample, latched_sample
            return latched_sample, latched_sample
        return raw_sample, latched_sample

    def _ensure_sequence_resolution_cache(self) -> None:
        if self._resolved_sequence_cache_version == self._resolution_version:
            return
        latched = [0] * MODSong.CHANNELS
        cells: dict[tuple[int, int, int], int] = {}
        seen: set[int] = set()
        first_use: list[int] = []
        for sequence_idx, pattern_idx in enumerate(self.pattern_seq):
            if pattern_idx < 0 or pattern_idx >= len(self.patterns):
                continue
            pat = self.patterns[pattern_idx]
            n_channels = min(pat.n_channels, MODSong.CHANNELS)
            for row in range(pat.n_rows):
                for channel in range(n_channels):
                    note = pat.data[channel][row]
                    raw_sample = int(getattr(note, 'instrument_idx', 0))
                    period = getattr(note, 'period', '')
                    effective_sample, latched[channel] = self._resolve_effective_sample(
                        raw_sample,
                        period,
                        latched[channel],
                    )
                    cells[(sequence_idx, row, channel)] = effective_sample
                    used_sample = effective_sample if period != '' else raw_sample
                    if used_sample > 0 and used_sample not in seen:
                        seen.add(used_sample)
                        first_use.append(used_sample)
        self._resolved_sequence_cells = cells
        self._resolved_sequence_first_use = first_use
        self._resolved_sequence_cache_version = self._resolution_version

    def _ensure_reachable_resolution_cache(self) -> None:
        if self._resolved_reachable_cache_version == self._resolution_version:
            return
        played_rows = tuple(self.iter_playback_rows())
        latched = [0] * MODSong.CHANNELS
        cells: dict[tuple[int, int], int] = {}
        seen: set[int] = set()
        first_use: list[int] = []
        for played_row in played_rows:
            pattern_idx = played_row.pattern_idx
            if pattern_idx < 0 or pattern_idx >= len(self.patterns):
                continue
            pat = self.patterns[pattern_idx]
            row = played_row.row
            if row < 0 or row >= pat.n_rows:
                continue
            n_channels = min(pat.n_channels, MODSong.CHANNELS)
            for channel in range(n_channels):
                note = pat.data[channel][row]
                raw_sample = int(getattr(note, 'instrument_idx', 0))
                period = getattr(note, 'period', '')
                effective_sample, latched[channel] = self._resolve_effective_sample(
                    raw_sample,
                    period,
                    latched[channel],
                )
                cells[(played_row.visit_idx, channel)] = effective_sample
                used_sample = effective_sample if period != '' else raw_sample
                if used_sample > 0 and used_sample not in seen:
                    seen.add(used_sample)
                    first_use.append(used_sample)
        self._resolved_reachable_cells = cells
        self._resolved_reachable_first_use = first_use
        self._resolved_reachable_rows = played_rows
        self._resolved_reachable_cache_version = self._resolution_version

    @staticmethod
    def period_to_note(period_value: int) -> str:
        if period_value not in MODSong.PERIOD_TABLE:
            raise ValueError(f"Unknown period value {period_value}.")
        return MODSong.PERIOD_TABLE[period_value]

    @staticmethod
    def note_to_period(note_str: str) -> int:
        if note_str not in MODSong.INV_PERIOD_TABLE:
            raise ValueError(f"Unknown MOD note {note_str!r}.")
        return MODSong.INV_PERIOD_TABLE[note_str]

    def copy(self) -> MODSong:
        from .component import MODSong
        new_song = MODSong()
        new_song.artist = self.artist
        new_song.songname = self.songname
        new_song.patterns = copy.deepcopy(self.patterns)
        new_song.pattern_seq = copy.deepcopy(self.pattern_seq)
        new_song.samples = copy.deepcopy(self.samples)
        new_song.n_actual_samples = self.n_actual_samples
        new_song._restart_position_raw = self._restart_position_raw
        return new_song

    @property
    def restart_position(self) -> int | None:
        return self.get_restart_position(raw=False)

    def get_restart_position(self, raw: bool = False) -> int | None:
        value = self._restart_position_raw
        if raw:
            return value
        if value == 127:
            return None
        return value

    def set_restart_position(self, position: int | None, *, raw: bool = False) -> None:
        if position is None:
            self._restart_position_raw = 127
            return
        if not isinstance(position, int):
            raise TypeError(f"Invalid restart position type {type(position).__name__} (expected int or None).")
        if position < 0 or position > 255:
            raise ValueError(f"Invalid restart position {position} (expected 0-255).")
        if raw:
            self._restart_position_raw = position
            return
        self._restart_position_raw = position

    def load(self, fname: str, verbose: bool = True, *, metadata_from_filename: bool = False):
        if verbose:
            print(f'Loading {fname}... ', end='', flush=True)
        with (open(fname, 'rb') as mod_file):
            data = bytearray(mod_file.read())
            def _decode_header_bytes(raw: bytes) -> str:
                try:
                    return raw.decode('utf-8')
                except UnicodeDecodeError:
                    return raw.decode('latin-1')
            self.artist = "Unknown Artist"
            self.songname = _decode_header_bytes(bytes(data[:20])).rstrip('\x00')
            magic_string = _decode_header_bytes(data[1080:1080 + 4])
            accepted_magic = {"M.K.", "M!K!", "FLT4"}
            if magic_string not in accepted_magic:
                raise NotImplementedError(f"Unsupported MOD format {magic_string}. Supported: M.K., M!K!, FLT4.")
            song_length = data[950]
            self._restart_position_raw = data[951]
            self.pattern_seq = [0] * song_length
            n_unique_patterns = 0
            for p in range(song_length):
                x = data[952 + p]
                self.pattern_seq[p] = x
                if x > n_unique_patterns:
                    n_unique_patterns = x
            n_unique_patterns += 1
            self.patterns = []
            sample_lengths = [0] * MODSong.SAMPLES
            self.n_actual_samples = 0
            self.samples = [Sample() for _ in range(MODSong.SAMPLES)]
            waveform_idx = 1084 + n_unique_patterns * MODSong.ROWS * MODSong.CHANNELS * 4
            for i in range(MODSong.SAMPLES):
                idx = 20 + i * 30 + 22
                sample_lengths[i] = 2 * int.from_bytes(data[idx:idx + 2], byteorder='big', signed=False)
                assert sample_lengths[i] != 1
                if sample_lengths[i] > 0:
                    self.n_actual_samples += 1
                smp = Sample()
                smp.name = _decode_header_bytes(data[idx - 22:idx].rstrip(b'\x00'))
                smp.finetune = data[idx + 2]
                smp.finetune &= 0x0F
                smp.volume = data[idx + 3]
                smp.repeat_point = 2 * int.from_bytes(data[idx + 4:idx + 6], byteorder='big', signed=False)
                smp.repeat_len = 2 * int.from_bytes(data[idx + 6:idx + 8], byteorder='big', signed=False)
                if sample_lengths[i] == 0:
                    smp.waveform = array.array('b')
                else:
                    smp.waveform = data[waveform_idx:waveform_idx + sample_lengths[i]]
                    smp.waveform = array.array(
                        'b',
                        smp.waveform)
                    waveform_idx += sample_lengths[i]
                self.samples[i] = smp
            patterns_size = n_unique_patterns * MODSong.ROWS * MODSong.CHANNELS * 4
            samples_size = sum(sample_lengths)
            predicted_size = patterns_size + samples_size
            actual_size = len(data[1084:])
            if predicted_size != actual_size:
                n_extra_patterns = int((actual_size - predicted_size) / (MODSong.ROWS * MODSong.CHANNELS * 4))
                raise NotImplementedError(f"Unexpected extra patterns: {n_extra_patterns} (non-standard MOD).")
            for p in range(n_unique_patterns):
                pat = Pattern(MODSong.ROWS, MODSong.CHANNELS)
                for r in range(MODSong.ROWS):
                    for c in range(MODSong.CHANNELS):
                        idx = p * MODSong.ROWS * MODSong.CHANNELS * 4 + r * MODSong.CHANNELS * 4 + c * 4
                        note_raw = data[1084 + idx:1084 + idx + 4]
                        note = Note()
                        note.instrument_idx = MODSong.get_sample_from_note(note_raw)
                        note.period = MODSong.get_period_from_note(note_raw)
                        e_type, e_param = MODSong.get_effect_from_note(note_raw)
                        if e_type != 0 or e_param != 0:
                            note.effect = hex(e_type).lstrip("0x").upper()
                            note.effect += f"{e_param:02X}"
                            if e_type == 0:
                                note.effect = "0" + note.effect
                        pat.data[c][r] = note
                self.patterns.append(pat)
        if metadata_from_filename:
            self.artist, self.songname = Song.artist_songname_from_filename(fname)
        self._on_mutation()
        if verbose:
            print('done.')

    def save(self, fname: str, verbose: bool = True, *, validate_samples: bool = False):
        if verbose:
            print(f'Saving to {fname}... ', end='', flush=True)
        if validate_samples:
            self.validate_samples()
        if len(self.pattern_seq) == 0 or len(self.pattern_seq) > 128 or len(self.patterns) > 128:
            raise OverflowError(f"Too many patterns (sequence: {len(self.pattern_seq)}, unique: {len(self.patterns)}). MOD supports up to 128.")
        data = bytearray()
        def str_to_bytes_padded(s: str, max_len: int) -> bytes:
            r = bytes(s, 'utf-8')
            if len(r) > max_len:
                try:
                    r_latin1 = bytes(s, 'latin-1')
                    if len(r_latin1) <= max_len:
                        r = r_latin1
                except UnicodeEncodeError:
                    pass
            if len(r) > max_len:
                r = r[:max_len]
            else:
                r += bytes(max_len - len(r))
            return r
        data += str_to_bytes_padded(self.songname, 20)
        for s in range(MODSong.SAMPLES):
            smp = self.samples[s]
            data += str_to_bytes_padded(smp.name, 22)
            waveform = smp.waveform
            if len(waveform) % 2 != 0:
                waveform.append(0x0)
            if int(len(waveform) / 2) > 131072:
                raise ValueError(f"Sample length {int(len(waveform) / 2)} words exceeds MOD max 65536 words (128 KB).")
            data += int(len(waveform) / 2).to_bytes(2, byteorder='big', signed=False)
            data += ((smp.finetune << 4) >> 4).to_bytes(1, byteorder='big', signed=False)
            if smp.volume > 64:
                print(f"Warning: Truncating max sample volume from {smp.volume} to 64.")
            data += min(smp.volume, 64).to_bytes(1, byteorder='big', signed=False)
            data += int(smp.repeat_point / 2).to_bytes(2, byteorder='big', signed=False)
            data += int(smp.repeat_len / 2).to_bytes(2, byteorder='big', signed=False)
        data += len(self.pattern_seq).to_bytes(1, byteorder='big', signed=False)
        data += int(self._restart_position_raw).to_bytes(1, byteorder='big', signed=False)
        data += bytearray(self.pattern_seq) + bytearray(128 - len(self.pattern_seq))
        data += bytes("M.K.", 'utf-8')
        for p in range(len(self.patterns)):
            if p > max(self.pattern_seq):
                break
            pat = self.patterns[p]
            if len(pat.data) != MODSong.CHANNELS:
                raise NotImplementedError(f"Cannot save MOD with {len(pat.data)} channels (expected 4).")
            if len(pat.data[0]) != MODSong.ROWS:
                raise NotImplementedError(f"Cannot save MOD with {len(pat.data[0])} rows (expected 64).")
            for r in range(MODSong.ROWS):
                for c in range(MODSong.CHANNELS):
                    note = pat.data[c][r]
                    efx_type = 0x0
                    efx_param = 0x0
                    if note.effect != "":
                        efx_type = int(note.effect[0], 16)
                        efx_param = int(note.effect[1:], 16)
                    if note.period != '':
                        if note.period not in MODSong.INV_PERIOD_TABLE:
                            raise ValueError(f"Unknown note period '{note.period}' in pattern {p}, row {r}, channel {c}.")
                        pd = MODSong.INV_PERIOD_TABLE[note.period]
                    else:
                        pd = 0
                    note_raw = bytearray(4)
                    note_raw[0] = (note.instrument_idx & 0xF0) | ((pd & 0xF00) >> 8)
                    note_raw[1] = pd & 0xFF
                    note_raw[2] = ((note.instrument_idx & 0x0F) << 4) | efx_type
                    note_raw[3] = efx_param
                    data += note_raw
        for smp in self.samples:
            data += bytearray(smp.waveform)
        with open(fname, 'bw') as mod_file:
            mod_file.write(bytes(data))
        if verbose:
            print('done.')
