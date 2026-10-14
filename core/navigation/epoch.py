# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import threading
_GRID_EPOCH = 0
_EPOCH_LOCK = threading.Lock()
_GRID_LOCK = threading.RLock()


def _bump_epoch():
    global _GRID_EPOCH
    with _EPOCH_LOCK:
        _GRID_EPOCH += 1
        return _GRID_EPOCH

def _current_epoch():
    return _GRID_EPOCH

def _grid_snapshot(grid):
    with _GRID_LOCK:
        return grid._grid, _GRID_EPOCH