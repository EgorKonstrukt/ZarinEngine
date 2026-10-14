# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from .keywords import (
    _ALBEDO_KEYWORDS,
    _NORMAL_KEYWORDS,
    _METALLIC_KEYWORDS,
    _ROUGHNESS_KEYWORDS,
    _SMOOTHNESS_KEYWORDS,
    _AO_KEYWORDS,
    _EMISSION_KEYWORDS,
    _HEIGHT_KEYWORDS,
    _DETAIL_ALBEDO_KEYWORDS,
    _DETAIL_NORMAL_KEYWORDS,
    _CLEARCOAT_KEYWORDS,
    _SUBSURFACE_KEYWORDS,
    _THIN_FILM_KEYWORDS,
    _CHANNEL_HINTS,
    _PRIORITY_ORDER,
)
from .naming import _normalize_name, _guess_map_type
from .shaders import _collect_shaders, _extract_shader_name
from .drop_list import _TextureDropList
from .dialog import MaterialWizardDialog

__all__ = [
    "_ALBEDO_KEYWORDS",
    "_NORMAL_KEYWORDS",
    "_METALLIC_KEYWORDS",
    "_ROUGHNESS_KEYWORDS",
    "_SMOOTHNESS_KEYWORDS",
    "_AO_KEYWORDS",
    "_EMISSION_KEYWORDS",
    "_HEIGHT_KEYWORDS",
    "_DETAIL_ALBEDO_KEYWORDS",
    "_DETAIL_NORMAL_KEYWORDS",
    "_CLEARCOAT_KEYWORDS",
    "_SUBSURFACE_KEYWORDS",
    "_THIN_FILM_KEYWORDS",
    "_CHANNEL_HINTS",
    "_PRIORITY_ORDER",
    "_normalize_name",
    "_guess_map_type",
    "_collect_shaders",
    "_extract_shader_name",
    "_TextureDropList",
    "MaterialWizardDialog",
]
