# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from .compress import _CACHE_SUBDIR
from .compress import _MATERIAL_EXTS
from .compress import _PATH_SUFFIX
from .compress import _abs_path
from .compress import _cache_dir
from .compress import _cache_path_for
from .compress import _compress
from .compress import _decompress
from .compress import _entry_cache_basename
from .compress import _entry_raw_bytes
from .compress import _flagged_entity_ids
from .compress import _is_material_file
from .compress import _iter_component_path_entries
from .compress import _key_candidates
from .compress import _norm
from .compress import _resolve_alias
from .compress import _sanitize_name
from .compress import _set_nested
from .compress import _storage_key
from .embed import _EMBED_STAT_CACHE
from .embed import _material_textures
from .embed import _read_raw_digest
from .embed import embed_scene_resources
from .extract import _decode_entry_raw
from .extract import _rewrite_material_textures
from .extract import _target_for_key
from .extract import extract_embedded_resources
__all__ = ["_CACHE_SUBDIR", "_EMBED_STAT_CACHE", "_MATERIAL_EXTS", "_PATH_SUFFIX", "_abs_path", "_cache_dir", "_cache_path_for", "_compress", "_decode_entry_raw", "_decompress", "_entry_cache_basename", "_entry_raw_bytes", "_flagged_entity_ids", "_is_material_file", "_iter_component_path_entries", "_key_candidates", "_material_textures", "_norm", "_read_raw_digest", "_resolve_alias", "_rewrite_material_textures", "_sanitize_name", "_set_nested", "_storage_key", "_target_for_key", "embed_scene_resources", "extract_embedded_resources"]
