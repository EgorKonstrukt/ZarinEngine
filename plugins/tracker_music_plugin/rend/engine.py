# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from .defs import _AMIGA_CLOCK
from .defs import _MOD_PERIODS
from .defs import _NOTE_NAMES
from .defs import _NTSC_SR
from .defs import _RENDER_VERSION
from .defs import _build_fastmix_once
from .defs import _fastmix_prefetched
from .defs import _load_fastmix
from .defs import _note_to_midi
from .defs import _parse_effect
from .engine_fx import _FxMixin
from .engine_mix import _MixMixin
from .engine_seq import _SeqMixin
from .voice import _Voice


class TrackerSoftwareRenderer(_SeqMixin, _FxMixin, _MixMixin):
    METER_BLOCK_SEC = 0.1


__all__ = [
    "TrackerSoftwareRenderer",
]
