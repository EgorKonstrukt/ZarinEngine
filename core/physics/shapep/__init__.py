# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from .materials import (
    default_physics_material_dict,
    resolve_physics_material,
    capsule_part_quat,
    capsule_section_height,
    capsule_volume,
    part_volume,
    part_center,
    PRIMITIVE_SHAPE_TYPES,
    _HALF_SQRT2,
    _CAPSULE_PART_QUAT,
    _PYBULLET_CAPSULE_EULER,
)
from .shapes import (
    _PROJECT_ROOT,
    SHAPE_TYPE_MAP,
    SHAPE_INFO_CACHE_KEYS,
    read_import_scale,
    _shape_info_for,
    find_shapes_info,
    find_shape_info,
    make_shape_key,
    _key_part,
    make_shapes_key,
    downgrade_mesh_to_box,
    partition_compound_shapes,
)

__all__ = [
    "default_physics_material_dict",
    "resolve_physics_material",
    "capsule_part_quat",
    "capsule_section_height",
    "capsule_volume",
    "part_volume",
    "part_center",
    "PRIMITIVE_SHAPE_TYPES",
    "_HALF_SQRT2",
    "_CAPSULE_PART_QUAT",
    "_PYBULLET_CAPSULE_EULER",
    "_PROJECT_ROOT",
    "SHAPE_TYPE_MAP",
    "SHAPE_INFO_CACHE_KEYS",
    "read_import_scale",
    "_shape_info_for",
    "find_shapes_info",
    "find_shape_info",
    "make_shape_key",
    "_key_part",
    "make_shapes_key",
    "downgrade_mesh_to_box",
    "partition_compound_shapes",
]
