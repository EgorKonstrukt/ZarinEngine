# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from .mode import CollisionMode
from .cache import _SENTINEL, _LRU, _mesh_data, _decimated_hull_cache_np, _convex_hull_cache_np, _PROJECT_ROOT
from .geometry import _resolve_mesh_path, _load_mesh_data, _decimate_verts, _compute_hull_edges_np, _import_sig_of, load_collision_geometry, _get_convex_hull_edges_np, _get_decimated_hull_edges_np, _triangle_edges_np, _box_edges_np, _sphere_edges_np, _edge_pairs_np
from .collider import MeshCollider


__all__ = [
    "CollisionMode",
    "MeshCollider",
    "load_collision_geometry",
    "_SENTINEL",
    "_LRU",
    "_mesh_data",
    "_decimated_hull_cache_np",
    "_convex_hull_cache_np",
    "_PROJECT_ROOT",
    "_resolve_mesh_path",
    "_load_mesh_data",
    "_decimate_verts",
    "_compute_hull_edges_np",
    "_import_sig_of",
    "_get_convex_hull_edges_np",
    "_get_decimated_hull_edges_np",
    "_triangle_edges_np",
    "_box_edges_np",
    "_sphere_edges_np",
    "_edge_pairs_np",
]
