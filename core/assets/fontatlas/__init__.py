# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.assets.fontatlas.atlas import FontAtlas
from core.assets.fontatlas.atlas import get_default_font_path
from core.assets.fontatlas.cache import request_font_atlas
from core.assets.fontatlas.cache import drop_font_atlas
from core.assets.fontatlas.cache import get_cached_font_atlas
from core.assets.fontatlas.cache import shutdown_font_atlas_loader
__all__ = [
    "FontAtlas",
    "get_default_font_path",
    "request_font_atlas",
    "drop_font_atlas",
    "get_cached_font_atlas",
    "shutdown_font_atlas_loader",
]
