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

class SongHeaderMixin(ABC):
    PERIOD_SEQ = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']

    PRESERVED_EFFECT_PREFIXES = frozenset({'B', 'C', 'D', 'E', 'F'})
    def __init__(self):
        self.artist = ""
        self.songname = "new song"
        self.patterns = []
        self.pattern_seq = []

    def __repr__(self) -> str:
        n_channels = getattr(self, 'n_channels', self.patterns[0].n_channels if self.patterns else 0)
        return (
            f"{self.__class__.__name__}(songname={self.songname!r}, "
            f"patterns={len(self.patterns)}, sequence={len(self.pattern_seq)}, channels={n_channels})"
        )
    __str__ = __repr__
    def set_artist(self, artist_name: str):
        self.artist = artist_name

    def set_songname(self, song_name: str):
        self.songname = song_name

    def view(self) -> SongView:
        n_channels = getattr(self, 'n_channels', self.patterns[0].n_channels if self.patterns else 0)
        return SongView(
            format=self.file_extension,
            songname=self.songname,
            artist=self.artist,
            sequence=tuple(self.pattern_seq),
            n_patterns=len(self.patterns),
            n_channels=n_channels,
        )

    def _on_mutation(self) -> None:
        return

    @staticmethod
    def artist_songname_from_filename(filename: str):
        filename = os.path.basename(filename)
        parts = filename.split(' - ', maxsplit=1)
        if len(parts) == 1:
            artist_name = "Unknown Artist"
            song_name = parts[0].strip()
        else:
            artist_name = parts[0].strip()
            song_name = parts[1].strip()
        song_name = os.path.splitext(song_name)[0]
        return artist_name, song_name

    @property
    @abstractmethod
    def file_extension(self) -> str:
        pass

    @abstractmethod
    def save(self, fname: str, verbose: bool = True):
        pass

    def render(self, fname: str, verbose: bool = True, cleanup: bool = True, channels: int = 1):
        if channels <= 0:
            raise ValueError(f"Invalid channel count {channels} (expected >=1).")
        if verbose:
            print("Rendering as wav... ", end='', flush=True)
        if os.path.isfile(fname):
            os.remove(fname)
        noext = os.path.splitext(fname)[0]
        ext = self.file_extension
        temp_file = f"{noext}.{ext}"
        temp_wav = f"{temp_file}.wav"
        if os.path.isfile(temp_file):
            os.remove(temp_file)
        self.save(temp_file, verbose=False)
        if os.path.isfile(temp_wav):
            os.remove(temp_wav)
        try:
            subprocess.run(
                ["openmpt123", temp_file, "-q", "--channels", str(channels), "--samplerate", "44100", "--render"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            try:
                subprocess.run(
                    ["ffmpeg", "-ar", "44100", "-i", temp_file, temp_wav],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError as e:
                raise FileNotFoundError(
                    "Neither openmpt123 nor ffmpeg found. Install one of them to render WAV files."
                ) from e
        shutil.move(temp_wav, fname)
        if cleanup:
            os.remove(temp_file)
        if verbose:
            print("done.")

    def get_song_duration(self) -> float:
        timestamps = self.timestamp()
        if not timestamps or not timestamps[-1]:
            return 0.0
        return timestamps[-1][-1][0]

    def get_song_info(self) -> dict:
        timestamps = []
        try:
            timestamps = self.timestamp()
        except Exception:
            timestamps = []
        first_row = timestamps[0][0] if timestamps and timestamps[0] else None
        n_channels = getattr(self, 'n_channels', self.patterns[0].n_channels if self.patterns else 0)
        info = {
            'format': self.file_extension,
            'songname': self.songname,
            'artist': self.artist,
            'n_patterns': len(self.patterns),
            'sequence_length': len(self.pattern_seq),
            'n_channels': n_channels,
            'sequence': list(self.pattern_seq),
            'speed': first_row[1] if first_row else None,
            'bpm': first_row[2] if first_row else None,
            'duration_seconds': self.get_song_duration() if timestamps else 0.0,
        }
        if hasattr(self, 'restart_position'):
            info['restart_position'] = getattr(self, 'restart_position')
        return info
