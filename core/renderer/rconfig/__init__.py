# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.renderer.rconfig.config_state import ConfigStateMixin
from core.renderer.rconfig.cache_precision import CachePrecisionMixin


class RendererConfigMixin(ConfigStateMixin, CachePrecisionMixin):
    pass


__all__ = ["RendererConfigMixin", "ConfigStateMixin", "CachePrecisionMixin"]
