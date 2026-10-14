# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import re

from PyQt6.QtGui import QBrush, QColor

_HIGHLIGHT_BRUSH = QBrush(QColor(255, 190, 30, 100))
_BASE_BRUSH = QBrush(QColor(0, 0, 0, 0))

_NOTE_RE = re.compile(r"^([A-Ga-g])([-\x23])([0-9])$")
_EFFECT_RE = re.compile(r"^([0-9A-Fa-f]{3})$")
_VOLUME_RE = re.compile(r"^([a-z])([0-9]{1,2})$")

_NOTE_NAMES = ["C-", "C\x23", "D-", "D\x23", "E-", "F-", "F\x23", "G-", "G\x23", "A-", "A\x23", "B-"]

COLUMNS_PER_CHANNEL = 4
COL_NOTE = 0
COL_INS = 1
COL_VOL = 2
COL_EFF = 3

_COL_LABELS = ["Note", "Ins", "Vol", "Eff"]


def _note_text(note) -> str:
    p = getattr(note, "period", "") or ""
    return p if p else "---"


def _inst_text(note) -> str:
    i = int(getattr(note, "instrument_idx", 0) or 0)
    return f"{i:02d}" if i else "--"


def _vol_text(note) -> str:
    if hasattr(note, "vol_cmd"):
        cmd = str(getattr(note, "vol_cmd", "") or "")
        if cmd:
            v = int(getattr(note, "vol_val", -1) or -1)
            return f"{cmd}{v:02d}" if v >= 0 else f"{cmd}--"
        return "--"
    if hasattr(note, "volume"):
        v = int(getattr(note, "volume", -1) or -1)
        return f"v{v:02d}" if v >= 0 else "--"
    return "--"


def _eff_text(note) -> str:
    e = str(getattr(note, "effect", "") or "")
    return e if e else "---"


def _transpose_note(note_str: str, semis: int) -> str:
    m = _NOTE_RE.match(note_str)
    if not m:
        return note_str
    pitch = (m.group(1) + m.group(2)).upper()
    octave = int(m.group(3))
    idx = (octave - 1) * 12 + _NOTE_NAMES.index(pitch)
    idx += semis
    idx = max(0, min(95, idx))
    return f"{_NOTE_NAMES[idx % 12]}{idx // 12 + 1}"


def _parse_note(text: str):
    s = text.strip()
    if not s or s in ("---", "--"):
        return ""
    if s.lower() == "off":
        return "off"
    m = _NOTE_RE.match(s)
    if not m:
        return None
    return (m.group(1) + m.group(2)).upper() + m.group(3)


def _parse_inst(text: str):
    s = text.strip()
    if not s or s in ("---", "--"):
        return 0
    if not s.isdigit():
        return None
    v = int(s)
    if v > 255:
        return None
    return v


def _parse_effect(text: str):
    s = text.strip()
    if not s or s in ("---", "--"):
        return ""
    m = _EFFECT_RE.match(s)
    if not m:
        return None
    return m.group(1).upper()


def _parse_vol(text: str):
    s = text.strip()
    if not s or s in ("---", "--"):
        return ("", -1)
    m = _VOLUME_RE.match(s)
    if m:
        v = int(m.group(2))
        if v <= 64:
            return (m.group(1).lower(), v)
        return None
    if s.isdigit():
        v = int(s)
        if v <= 64:
            return ("v", v)
    return None
