# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import ctypes
from . import efx as _core


def _filter_type_enum() -> int:
    cached = _core._enum_cache.get(b"AL_FILTER_TYPE")
    if cached is not None:
        return int(cached)
    return int(_core.AL_FILTER_TYPE)


def _lowpass_enum() -> int:
    cached = _core._enum_cache.get(b"AL_FILTER_LOWPASS")
    if cached is not None:
        return int(cached)
    return int(_core.AL_FILTER_LOWPASS)


def create_filter() -> int:
    if not _core.efx_available():
        raise _core.EFXError("EFX not available")
    filter_id = ctypes.c_uint()
    _core._alGenFilters(1, ctypes.pointer(filter_id))
    if filter_id.value == 0:
        raise _core.EFXError("Failed to create filter")
    return filter_id.value


def delete_filter(filter_id: int):
    if filter_id == 0:
        return
    if not _core._efx_available or _core._alDeleteFilters is None:
        return
    try:
        val = ctypes.c_uint(int(filter_id))
        _core._alDeleteFilters(1, ctypes.pointer(val))
    except Exception:
        pass


def is_filter(filter_id: int) -> bool:
    if filter_id == 0 or not _core._efx_available or _core._alIsFilter is None:
        return False
    try:
        return bool(_core._alIsFilter(int(filter_id)))
    except Exception:
        return False


def set_filter_type(filter_id: int, ftype: int):
    if not _core._efx_available or _core._alFilteri is None:
        return
    try:
        _core._alFilteri(int(filter_id), int(_filter_type_enum()), int(ftype))
    except Exception:
        pass


def set_filter_param_i(filter_id: int, param: int, value: int):
    if not _core._efx_available or _core._alFilteri is None:
        return
    try:
        _core._alFilteri(int(filter_id), int(param), int(value))
    except Exception:
        pass


def set_filter_param_f(filter_id: int, param: int, value: float):
    if not _core._efx_available or _core._alFilterf is None:
        return
    try:
        _core._alFilterf(int(filter_id), int(param), float(value))
    except Exception:
        pass
