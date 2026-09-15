# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Render snapshot."""

from __future__ import annotations


class _RenderSnapshot:
    __slots__ = (
        'lights', 'dir_light', 'sky_component', 'sky_entity', 'cloud_components',
        'water_components', 'wind_zones', 'renderable', 'shadow_renderables',         'sprite_items', 'video_items',
        'svg_items', 'text_items', 'particle_systems', 'force_fields',
        'projectors', 'skinned_renderables', 'skinned_shadow_renderables',
        'interactors', 'gaussian_splats', 'dynamic_cubemaps',
        'dynamic_cubemaps_pos', 'dynamic_cubemaps_entity',
        'cull_entries', 'cull_offsets', 'cull_counts',
    )
    def __init__(self):
        self.lights: list = []
        self.dir_light = None
        self.sky_component = None
        self.sky_entity = None
        self.cloud_components: list = []
        self.water_components: list = []
        self.wind_zones: list = []
        self.renderable: list = []
        self.shadow_renderables: list = []
        self.skinned_renderables: list = []
        self.skinned_shadow_renderables: list = []
        self.sprite_items: list = []
        self.video_items: list = []
        self.svg_items: list = []
        self.text_items: list = []
        self.particle_systems: list = []
        self.force_fields: list = []
        self.projectors: list = []
        self.interactors: list = []
        self.gaussian_splats: list = []
        self.dynamic_cubemaps = None
        self.dynamic_cubemaps_pos = None
        self.dynamic_cubemaps_entity = None
        self.cull_entries: list = []
        self.cull_offsets: list = []
        self.cull_counts: list = []
