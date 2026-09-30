# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def transform_pos(pos: int, against_pos: int, against_removed: int, against_added_len: int) -> int:
    if pos > against_pos:
        if against_removed > 0 and pos <= against_pos + against_removed:
            return against_pos
        pos += against_added_len - against_removed
    return pos


def transform_op(op: tuple, against: tuple) -> tuple:
    pos, removed, added = op
    apos, aremoved, aadded = against
    new_pos = transform_pos(pos, apos, aremoved or 0, len(aadded or ""))
    return (new_pos, removed, added)
