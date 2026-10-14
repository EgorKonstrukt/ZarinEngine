# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from .capture import register_capture as _register_capture
from .camera import register_camera as _register_camera


def register(registry, engine):
    _register_capture(registry, engine)
    _register_camera(registry, engine)


__all__ = ["register"]
