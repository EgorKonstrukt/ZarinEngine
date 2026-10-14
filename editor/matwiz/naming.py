# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import re
from typing import Optional
from .keywords import _CHANNEL_HINTS, _PRIORITY_ORDER


def _normalize_name(name: str) -> str:
    name = os.path.splitext(name)[0].lower()
    name = re.sub(r'[\s\-_.]+', '_', name)
    return name


def _guess_map_type(filename: str) -> Optional[str]:
    base = _normalize_name(filename)
    for keywords, prop in _PRIORITY_ORDER:
        for kw in keywords:
            if kw in base:
                return prop
    for hint_key, prop in _CHANNEL_HINTS.items():
        if hint_key in base:
            return prop
    return None
