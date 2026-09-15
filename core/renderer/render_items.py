# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Render items."""

from __future__ import annotations

import numpy as np
from core.maths.math3d import Mat4


def _halton(index: int, base: int) -> float:
    f = 1.0
    r = 0.0
    i = index
    while i > 0:
        f /= base
        r += f * (i % base)
        i //= base
    return r


_TAAU_JITTER = [(_halton(i, 2) - 0.5, _halton(i, 3) - 0.5) for i in range(1, 9)]


class _SpriteItem:
    __slots__ = ('world_matrix', 'color', 'flip_x', 'flip_y', 'texture_path', '_tr')
    def __init__(self, world_matrix, color, flip_x, flip_y, texture_path, tr=None):
        self.world_matrix = world_matrix
        self._tr = tr
        self.color = list(color) if color else [1, 1, 1, 1]
        self.flip_x = flip_x
        self.flip_y = flip_y
        self.texture_path = texture_path


class _SvgItem:
    __slots__ = ('world_matrix', 'color', 'flip_x', 'flip_y', 'abs_path', 'pixels_per_unit', '_tr')
    def __init__(self, world_matrix, color, flip_x, flip_y, abs_path, pixels_per_unit, tr=None):
        self.world_matrix = world_matrix
        self._tr = tr
        self.color = list(color) if color else [1, 1, 1, 1]
        self.flip_x = flip_x
        self.flip_y = flip_y
        self.abs_path = abs_path
        self.pixels_per_unit = pixels_per_unit


class _VideoItem:
    __slots__ = ('world_matrix', 'color', 'flip_x', 'flip_y', 'video_path', 'entity_id', 'loop', 'volume', 'offset', 'audio_source_entity_id', '_tr')
    def __init__(self, world_matrix, color, flip_x, flip_y, video_path, entity_id, loop, volume, offset=0.0, audio_source_entity_id="", tr=None):
        self.world_matrix = world_matrix
        self._tr = tr
        self.color = list(color) if color else [1, 1, 1, 1]
        self.flip_x = flip_x
        self.flip_y = flip_y
        self.video_path = video_path
        self.entity_id = entity_id
        self.loop = loop
        self.volume = volume
        self.offset = offset
        self.audio_source_entity_id = audio_source_entity_id


class _ProjectorItem:
    __slots__ = ('texture_path', 'color', 'intensity', 'range', 'spot_angle',
                 'aspect_ratio', 'near_plane', 'far_plane', 'vp_matrix',
                 'position', 'direction', 'up', 'flip_y', 'flip_x', 'cast_shadows', '_tr')
    def __init__(self, texture_path, color, intensity, range, spot_angle,
                 aspect_ratio, near_plane, far_plane, vp_matrix, position, direction, up,
                 flip_y=True, flip_x=False, cast_shadows=True, tr=None):
        self.texture_path = texture_path
        c = list(color) if color else [1, 1, 1]
        self.color = c[:3]
        self.intensity = intensity
        self.range = range
        self.spot_angle = spot_angle
        self.aspect_ratio = aspect_ratio
        self.near_plane = near_plane
        self.far_plane = far_plane
        self.vp_matrix = vp_matrix
        self.position = np.array(position.to_array(), dtype=np.float32)
        self.direction = np.array(direction.to_array(), dtype=np.float32)
        self.up = np.array(up.to_array(), dtype=np.float32)
        self.flip_y = flip_y
        self.flip_x = flip_x
        self.cast_shadows = cast_shadows
        self._tr = tr

    def refresh_vp(self):
        tr = self._tr
        if tr is None:
            return
        pos = tr.position
        fwd = tr.forward
        up = tr.up
        view = Mat4.look_at(pos, pos + fwd, up)
        proj = Mat4.perspective(self.spot_angle, self.aspect_ratio, self.near_plane, self.far_plane)
        self.vp_matrix = (view @ proj).to_f32()
        self.position = np.array(pos.to_array(), dtype=np.float32)
        self.direction = np.array(fwd.to_array(), dtype=np.float32)
        self.up = np.array(up.to_array(), dtype=np.float32)
