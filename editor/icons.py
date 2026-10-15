# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
_cache: dict = {}


def _key(color):
    try:
        hash(color)
        return color
    except Exception:
        pass
    try:
        return color.name()
    except Exception:
        return str(color)


def icon(name: str, color=None):
    key = (name, _key(color))
    ic = _cache.get(key)
    if ic is None:
        import qtawesome as _qta
        ic = _qta.icon(name, color=color) if color is not None else _qta.icon(name)
        _cache[key] = ic
    return ic


def clear_cache():
    _cache.clear()
