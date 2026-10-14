# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import sys

_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_SHADER_CANDIDATES = [
    os.path.join(_ENGINE_ROOT, "core", "shaders"),
    os.path.join(os.path.dirname(sys.executable), "core", "shaders"),
]
_SHADER_SUBDIRS = ("", "materials", "internal", "compute", "include", "legacy")
_find_cache: dict[str, str | None] = {}


def _find_in_shaders(filename: str) -> str | None:
    if filename in _find_cache:
        return _find_cache[filename]
    for base in _SHADER_CANDIDATES:
        for sub in _SHADER_SUBDIRS:
            full = os.path.join(base, sub, filename) if sub else os.path.join(base, filename)
            if os.path.exists(full):
                _find_cache[filename] = full
                return full
    _find_cache[filename] = None
    return None


SHADER_DIR = next((p for p in _SHADER_CANDIDATES if os.path.isdir(p)), _SHADER_CANDIDATES[0])


def _resolve_shader_file(name: str) -> str:
    if os.path.isabs(name) and os.path.exists(name):
        return name
    if os.path.exists(name):
        return name
    if "/" in name or "\\" in name:
        found = _find_in_shaders(os.path.basename(name))
        if found is not None:
            return found
        for base in _SHADER_CANDIDATES:
            candidate = os.path.join(base, name)
            if os.path.exists(candidate):
                return candidate
    else:
        found = _find_in_shaders(name)
        if found is not None:
            return found
    return os.path.join(SHADER_DIR, name)
