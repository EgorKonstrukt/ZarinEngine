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

class SongSamplesMixin(ABC):
    def iter_samples(self, *, include_empty: bool = True):
        if not hasattr(self, 'samples'):
            return
        sample_slots = getattr(self, 'samples')
        if not isinstance(sample_slots, list):
            return
        for sample_idx, sample in enumerate(sample_slots, start=1):
            length = len(getattr(sample, 'waveform', []))
            if not include_empty and length == 0:
                continue
            yield SampleView(
                sample_idx=sample_idx,
                name=getattr(sample, 'name', ''),
                length=length,
                finetune=getattr(sample, 'finetune', 0),
                volume=getattr(sample, 'volume', 0),
                loop_start=getattr(sample, 'repeat_point', 0),
                loop_length=getattr(sample, 'repeat_len', 0),
            )

    @staticmethod
    def _validate_used_resource_args(scope: str, order: str) -> None:
        if scope not in {"sequence", "reachable"}:
            raise ValueError(f"Invalid scope {scope!r} (expected 'sequence' or 'reachable').")
        if order not in {"sorted", "first_use"}:
            raise ValueError(f"Invalid order {order!r} (expected 'sorted' or 'first_use').")

    @staticmethod
    def _finalize_used_values(first_use_values: list[int], order: str) -> list[int]:
        if order == "first_use":
            return first_use_values
        return sorted(first_use_values)

    def _iter_notes_by_scope(self, scope: str):
        if scope == "sequence":
            for _, pattern_idx in self._iter_pattern_entries(sequence_only=True):
                if pattern_idx < 0 or pattern_idx >= len(self.patterns):
                    continue
                pat = self.patterns[pattern_idx]
                for row in range(pat.n_rows):
                    for channel in range(pat.n_channels):
                        yield pat.data[channel][row]
            return
        for played_row in self.iter_playback_rows():
            pattern_idx = played_row.pattern_idx
            if pattern_idx < 0 or pattern_idx >= len(self.patterns):
                continue
            pat = self.patterns[pattern_idx]
            row = played_row.row
            if row < 0 or row >= pat.n_rows:
                continue
            for channel in range(pat.n_channels):
                yield pat.data[channel][row]

    @staticmethod
    def _effect_text(note_or_effect) -> str:
        if hasattr(note_or_effect, 'effect'):
            effect = note_or_effect.effect
        elif note_or_effect is None:
            effect = ''
        else:
            effect = str(note_or_effect)
        return effect.strip().upper()

    @staticmethod
    def parse_effect(effect_str) -> tuple[str, int | None]:
        effect = Song._effect_text(effect_str)
        if effect == '':
            return '', None
        if len(effect) < 2:
            raise ValueError(f"Invalid effect string {effect!r}.")
        if effect[0] in {'E', 'X'}:
            if len(effect) != 3:
                raise ValueError(f"Invalid extended effect string {effect!r}.")
            return effect[:2], int(effect[2], 16)
        return effect[0], int(effect[1:], 16)

    @staticmethod
    def get_bpm(note_or_effect) -> int | None:
        effect_name, value = Song.parse_effect(note_or_effect)
        if effect_name == 'F' and value is not None and value >= 32:
            return value
        return None

    @staticmethod
    def get_ticks_per_row(note_or_effect) -> int | None:
        effect_name, value = Song.parse_effect(note_or_effect)
        if effect_name == 'F' and value is not None and 1 <= value <= 31:
            return value
        return None

    @staticmethod
    def get_tick_duration(bpm: int) -> float:
        return 2.5 / bpm

    @staticmethod
    def note_to_index(note: str | int) -> int:
        if isinstance(note, int):
            return note
        s = note.strip().upper()
        if len(s) != 3 or s[1] not in ("-", "#"):
            raise ValueError(f"Invalid note format {note}. Expected like C-4 or F#3.")
        pitch = s[:2]
        try:
            octave = int(s[2])
        except ValueError as exc:
            raise ValueError(f"Invalid note octave {note}. Expected a single digit octave.") from exc
        if octave < 1 or octave > 8:
            raise ValueError(f"Invalid note octave {note}. Octave must be 1-8 (maps to note index 0-95).")
        if pitch not in Song.PERIOD_SEQ:
            raise ValueError(f"Invalid note name {note}. Expected C-, C#, D-, D#, E-, F-, F#, G-, G#, A-, A#, B-.")
        note_idx = Song.PERIOD_SEQ.index(pitch)
        return (octave - 1) * 12 + note_idx

    @staticmethod
    def index_to_note(idx: int) -> str:
        if idx < 0 or idx >= 96:
            raise IndexError(f"Invalid note index {idx} (expected 0-95).")
        octave = idx // 12 + 1
        pitch = Song.PERIOD_SEQ[idx % 12]
        return f"{pitch}{octave}"

    @abstractmethod
    def timestamp(self) -> list[list[tuple[float, int, int]]]:
        pass

    def iter_playback_rows(
        self,
        *,
        profile: str | None = None,
        exact: bool = True,
        max_steps: int = 250_000,
    ):
        raise NotImplementedError("iter_playback_rows() is not implemented for this song format.")

    @staticmethod
    def note_in_range(note_str: str, lo: str | int, hi: str | int) -> bool:
        note_idx = Song.note_to_index(note_str)
        lo_idx = Song.note_to_index(lo)
        hi_idx = Song.note_to_index(hi)
        return lo_idx <= note_idx <= hi_idx

    @staticmethod
    def transpose_note(note_str: str, semitones: int) -> str:
        if note_str == '':
            return ''
        if note_str == 'off':
            return 'off'
        new_index = Song.note_to_index(note_str) + semitones
        return Song.index_to_note(new_index)

    def set_bpm(self, pattern: int, channel: int, row: int, bpm: int):
        if bpm < 32 or bpm > 255:
            raise ValueError(f"Invalid tempo {bpm} (expected 32-255).")
        self.set_effect(pattern, channel, row, f"F{bpm:02X}")

    def set_ticks_per_row(self, pattern: int, channel: int, row: int, ticks: int):
        if ticks < 1 or ticks > 31:
            raise ValueError(f"Invalid ticks per row {ticks} (expected 1-31).")
        self.set_effect(pattern, channel, row, f"F{ticks:02X}")

    def set_arpeggio(self, pattern: int, channel: int, row: int, note1: int, note2: int):
        if note1 < 0 or note1 > 15 or note2 < 0 or note2 > 15:
            raise ValueError("Arpeggio offsets must be in the range 0-15.")
        self.set_effect(pattern, channel, row, f"0{note1:X}{note2:X}")

    def set_panning(self, pattern: int, channel: int, row: int, panning: int):
        if panning < 0 or panning > 255:
            raise ValueError(f"Invalid panning {panning} (expected 0-255).")
        self.set_effect(pattern, channel, row, f"8{panning:02X}")

    def set_sample_offset(self, pattern: int, channel: int, row: int, offset: int):
        if offset < 0 or offset > 255:
            raise ValueError(f"Invalid sample offset {offset} (expected 0-255).")
        self.set_effect(pattern, channel, row, f"9{offset:02X}")

    def set_position_jump(self, pattern: int, channel: int, row: int, pos: int):
        if pos < 0 or pos > 255:
            raise ValueError(f"Invalid position jump {pos} (expected 0-255).")
        self.set_effect(pattern, channel, row, f"B{pos:02X}")

    def set_pattern_break(self, pattern: int, channel: int, row: int, row_target: int):
        if row_target < 0 or row_target > 99:
            raise ValueError(f"Invalid pattern break row {row_target} (expected 0-99).")
        tens, ones = divmod(row_target, 10)
        self.set_effect(pattern, channel, row, f"D{tens:X}{ones:X}")

    def set_portamento(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -255 or slide > 255:
            raise ValueError(f"Invalid portamento slide {slide} (expected -255 to 255).")
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
            raise ValueError(f"Invalid tone portamento slide {slide} (expected -15 to 15).")
        effect_value = 0
        if slide > 0:
            effect_value = slide << 4
        elif slide < 0:
            effect_value = -slide
        self.set_effect(pattern, channel, row, f"5{effect_value:02X}")

    def set_volume(self, pattern: int, channel: int, row: int, volume: int):
        if volume < 0 or volume > 64:
            raise ValueError(f"Invalid volume {volume} (expected 0-64).")
        self.set_effect(pattern, channel, row, f"C{volume:02X}")

    def set_volume_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid volume slide {slide} (expected -15 to 15).")
        effect_value = 0
        if slide > 0:
            effect_value = slide << 4
        elif slide < 0:
            effect_value = -slide
        self.set_effect(pattern, channel, row, f"A{effect_value:02X}")

    def set_vibrato(self, pattern: int, channel: int, row: int, speed: int, depth: int):
        if speed < 0 or speed > 15:
            raise ValueError(f"Invalid vibrato speed {speed} (expected 0-15).")
        if depth < 0 or depth > 15:
            raise ValueError(f"Invalid vibrato depth {depth} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"4{(speed << 4) | depth:02X}")

    def set_vibrato_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid vibrato slide {slide} (expected -15 to 15).")
        effect_value = 0
        if slide > 0:
            effect_value = slide << 4
        elif slide < 0:
            effect_value = -slide
        self.set_effect(pattern, channel, row, f"6{effect_value:02X}")

    def set_tremolo(self, pattern: int, channel: int, row: int, speed: int, depth: int):
        if speed < 0 or speed > 15:
            raise ValueError(f"Invalid tremolo speed {speed} (expected 0-15).")
        if depth < 0 or depth > 15:
            raise ValueError(f"Invalid tremolo depth {depth} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"7{(speed << 4) | depth:02X}")

    def set_fine_portamento(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid fine portamento {slide} (expected -15 to 15).")
        if slide > 0:
            self.set_effect(pattern, channel, row, f"E1{slide:X}")
        elif slide < 0:
            self.set_effect(pattern, channel, row, f"E2{-slide:X}")
        else:
            self.set_effect(pattern, channel, row, "E10")

    def set_glissando(self, pattern: int, channel: int, row: int, on: bool):
        self.set_effect(pattern, channel, row, f"E3{1 if on else 0}")

    def set_vibrato_waveform(self, pattern: int, channel: int, row: int, wave: int):
        if wave < 0 or wave > 7:
            raise ValueError(f"Invalid vibrato waveform {wave} (expected 0-7).")
        self.set_effect(pattern, channel, row, f"E4{wave:X}")

    def set_finetune(self, pattern: int, channel: int, row: int, finetune: int):
        if finetune < 0 or finetune > 15:
            raise ValueError(f"Invalid finetune {finetune} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"E5{finetune:X}")

    def set_pattern_loop(self, pattern: int, channel: int, row: int, count: int):
        if count < 0 or count > 15:
            raise ValueError(f"Invalid pattern loop count {count} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"E6{count:X}")

    def set_tremolo_waveform(self, pattern: int, channel: int, row: int, wave: int):
        if wave < 0 or wave > 7:
            raise ValueError(f"Invalid tremolo waveform {wave} (expected 0-7).")
        self.set_effect(pattern, channel, row, f"E7{wave:X}")

    def set_retrigger(self, pattern: int, channel: int, row: int, interval: int):
        if interval < 0 or interval > 15:
            raise ValueError(f"Invalid retrigger interval {interval} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"E9{interval:X}")

    def set_fine_volume_slide(self, pattern: int, channel: int, row: int, slide: int):
        if slide < -15 or slide > 15:
            raise ValueError(f"Invalid fine volume slide {slide} (expected -15 to 15).")
        if slide > 0:
            self.set_effect(pattern, channel, row, f"EA{slide:X}")
        elif slide < 0:
            self.set_effect(pattern, channel, row, f"EB{-slide:X}")
        else:
            self.set_effect(pattern, channel, row, "EA0")

    def set_note_cut(self, pattern: int, channel: int, row: int, tick: int):
        if tick < 0 or tick > 15:
            raise ValueError(f"Invalid note cut tick {tick} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"EC{tick:X}")

    def set_note_delay(self, pattern: int, channel: int, row: int, tick: int):
        if tick < 0 or tick > 15:
            raise ValueError(f"Invalid note delay tick {tick} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"ED{tick:X}")

    def set_pattern_delay(self, pattern: int, channel: int, row: int, rows: int):
        if rows < 0 or rows > 15:
            raise ValueError(f"Invalid pattern delay {rows} (expected 0-15).")
        self.set_effect(pattern, channel, row, f"EE{rows:X}")
