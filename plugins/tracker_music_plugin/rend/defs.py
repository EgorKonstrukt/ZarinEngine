# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import functools


try:
    from .. import fastmix as _fastmix_prefetched
except Exception:
    _fastmix_prefetched = None


def _load_fastmix():
    if _fastmix_prefetched is not None:
        return _fastmix_prefetched
    try:
        import os as _os
        from core.foundation.plugin_cython import import_extension as _import_extension
        return _import_extension(
            (__package__ or "").rsplit(".", 1)[0],
            "fastmix",
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        )
    except Exception:
        return None


def _build_fastmix_once():
    try:
        import os as _os
        from core.foundation.plugin_cython import ensure_extensions as _ensure_extensions
        _ensure_extensions(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), background=False)
    except Exception:
        pass
    return None


_NTSC_SR = 8287.0
_AMIGA_CLOCK = 3546894.6
_RENDER_VERSION = 3

_MOD_PERIODS = {
    856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
    428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
    214, 202, 190, 180, 169, 160, 151, 143, 135, 127, 120, 113,
}

_NOTE_NAMES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]


def _note_to_midi(note_str: str) -> int | None:
    s = str(note_str).strip().upper()
    if not s or s == "OFF":
        return None
    if len(s) < 3:
        return None
    try:
        name = s[:2]
        octave = int(s[2:])
        idx = _NOTE_NAMES.index(name)
    except (ValueError, IndexError):
        return None
    return (octave + 1) * 12 + idx


@functools.lru_cache(maxsize=2048)
def _parse_effect(effect: str) -> tuple[str, int] | None:
    if not effect:
        return None
    cmd = effect[0]
    try:
        arg = int(effect[1:], 16)
    except ValueError:
        return None
    return cmd, arg
