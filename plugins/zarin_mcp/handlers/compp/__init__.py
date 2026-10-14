# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from .crud import register_crud as _register_crud
from .transform import register_transform as _register_transform


def register(registry, engine):
    _register_crud(registry, engine)
    _register_transform(registry, engine)


__all__ = ["register"]
