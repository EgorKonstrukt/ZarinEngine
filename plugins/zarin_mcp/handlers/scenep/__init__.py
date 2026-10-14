# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from .query import register_query as _register_query
from .modify import register_modify as _register_modify
from .modify import _get_project_scenes


def register(registry, engine):
    _register_query(registry, engine)
    _register_modify(registry, engine)


__all__ = ["register", "_get_project_scenes"]
