# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Billboard icon rendering."""

from __future__ import annotations



class IconPassMixin:
    """Billboard icon rendering."""

    def create_icon_texture_from_data(self, rgba_data: bytes, w: int, h: int, key: str):
        if self._icons:
            return self._icons.create_texture_from_data(rgba_data, w, h, key)
        return None


    def create_icon_texture_from_png(self, path: str):
        if self._icons:
            return self._icons.create_texture_from_png(path)
        return None


    def render_icon(self, texture, sx: float, sy: float, size: float, alpha: float,
                    viewport_w: int, viewport_h: int):
        if self._icons:
            self._icons.render(texture, sx, sy, size, alpha, viewport_w, viewport_h)


    def render_icons_batched(self, batches: list, viewport_w: int, viewport_h: int):
        if self._icons:
            self._icons.render_batched(batches, viewport_w, viewport_h)

    _render_icon = render_icon


    _render_icons_batched = render_icons_batched
