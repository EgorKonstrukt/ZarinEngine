# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from collections import OrderedDict
import os


_SENTINEL = object()


class _LRU:
    def __init__(self, maxsize: int = 512):
        self._data: OrderedDict = OrderedDict()
        self._maxsize = maxsize
    def get(self, key):
        if key not in self._data:
            return _SENTINEL
        self._data.move_to_end(key)
        return self._data[key]
    def set(self, key, value):
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)


_mesh_data = _LRU(256)
_decimated_hull_cache_np = _LRU(128)
_convex_hull_cache_np = _LRU(128)
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
