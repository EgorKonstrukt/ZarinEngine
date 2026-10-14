# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
try:
    from core import _shadow_batch as _shadow_batch_mod
except ImportError:
    _shadow_batch_mod = None
def _cy(name):
    try:
        return getattr(_shadow_batch_mod, name)
    except Exception:
        return None
compute_frustum_corners_out = _cy('compute_frustum_corners_out')
build_directional_cascade_fast = _cy('build_directional_cascade_fast')
pack_model_matrices_f32 = _cy('pack_model_matrices_f32')
frustum_cull_shadow_groups = _cy('frustum_cull_shadow_groups')
pack_cascade_vps_transposed = _cy('pack_cascade_vps_transposed')
compute_frustum_corners = _cy('compute_frustum_corners')
build_directional_cascade = _cy('build_directional_cascade')
compute_cascade_distances = _cy('compute_cascade_distances')
pack_cascade_matrices_f32 = _cy('pack_cascade_matrices_f32')
pack_cascade_splits_f32 = _cy('pack_cascade_splits_f32')
pack_point_vps_f32 = _cy('pack_point_vps_f32')
cy_build_shadow_groups = _cy('build_shadow_groups')
face_cull_point_shadow = _cy('face_cull_point_shadow')
prepare_shadow_flat = _cy('prepare_shadow_flat')
cull_flat = _cy('cull_flat')
cull_flat_min = _cy('cull_flat_min')
cull_flat_range_min = _cy('cull_flat_range_min')
cull_flat_multi = _cy('cull_flat_multi')
collect_row_tr_ids = _cy('collect_row_tr_ids')
match_flushed_rows = _cy('match_flushed_rows')
_HAS_CYTHON = _shadow_batch_mod is not None
try:
    from core.math_helpers import mat4_inv_fast as _mat4_inv_fast
except ImportError:
    _mat4_inv_fast = None
