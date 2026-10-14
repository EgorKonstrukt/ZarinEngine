# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from .shader import _project_root
from .shader import _SHADER_PROP_RE
from .shader import ShaderProperty
from .shader import _parse_shader_properties_block
from .shader import _parse_shader_default
from .shader import _extract_all_subshaders
from .shader import _extract_glsl_from_shader
from .shader import _parse_shader_file
from .shader import ShaderSource
from .materials import Material
from .materials import _PROP_MIGRATION
from .materials import MaterialLibrary
__all__ = [
    "_project_root",
    "_SHADER_PROP_RE",
    "ShaderProperty",
    "_parse_shader_properties_block",
    "_parse_shader_default",
    "_extract_all_subshaders",
    "_extract_glsl_from_shader",
    "_parse_shader_file",
    "ShaderSource",
    "Material",
    "_PROP_MIGRATION",
    "MaterialLibrary",
]
