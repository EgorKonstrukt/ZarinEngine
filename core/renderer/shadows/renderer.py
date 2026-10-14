# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional, Any
import numpy as np; import moderngl
from core.maths.math3d import Vec3, Mat4
from .mathx import MAX_POINT_SHADOWS, MAX_SPOT_SHADOWS
from .groups import GroupsMixin
from .flat import FlatMixin
from .instancing import InstancingMixin
from .csm import CsmMixin
from .point_spot import PointSpotMixin
from .area import AreaMixin
from .projector import ProjectorMixin
from .stained import StainedMixin
from .passes import PassesMixin
from .uniforms import UniformsMixin
class ShadowRenderer(GroupsMixin, FlatMixin, InstancingMixin, CsmMixin, PointSpotMixin, AreaMixin, ProjectorMixin, StainedMixin, PassesMixin, UniformsMixin):
    """Thin orchestrator composing shadow mixins."""
    def __init__(self, ctx: moderngl.Context, shadow_prog: moderngl.Program, shadow_resolution: int = 512, shadow_distance: float = 50.0, area_shadow_resolution: int = 512, cascade_count: int = 2, cascade_splits: list = None, point_shadow_resolution: int = None, spot_shadow_resolution: int = None):
        self._ctx = ctx; self._prog = shadow_prog; self._shadow_resolution = shadow_resolution; self._area_shadow_resolution = area_shadow_resolution
        self._shadow_distance = shadow_distance; self._cascade_count = max(1, min(cascade_count, 4)); self._cascade_splits_norm: list[float] | None = cascade_splits
        self._shadow_maps: list[Any] = []; self._shadow_fbos: list[Any] = []
        self._cascade_splits: list[float] = [0.0] * 4
        self._light_space_matrices: list[np.ndarray] = [np.eye(4, dtype=np.float32) for _ in range(4)]
        self._point_shadow_resolution: int = point_shadow_resolution or shadow_resolution
        self._spot_shadow_resolution: int = spot_shadow_resolution or shadow_resolution
        self._point_shadow_maps: list[Any] = []; self._point_shadow_fbos: list[Any] = []
        self._point_light_vps: list[np.ndarray] = [np.eye(4, dtype=np.float32) for _ in range(MAX_POINT_SHADOWS * 6)]
        self._has_point_shadow: bool = False
        self._point_shadow_light_positions: list[Vec3] = [Vec3.zero() for _ in range(MAX_POINT_SHADOWS)]
        self._point_shadow_light_ranges: list[float] = [10.0] * MAX_POINT_SHADOWS
        self._point_shadow_light_indices: list[int] = [-1] * MAX_POINT_SHADOWS; self._point_shadow_count: int = 0
        self._spot_shadow_maps: list[Any] = []; self._spot_shadow_fbos: list[Any] = []
        self._spot_shadow_vps: list[np.ndarray] = [np.eye(4, dtype=np.float32) for _ in range(MAX_SPOT_SHADOWS)]
        self._has_spot_shadow: bool = False; self._spot_shadow_light_indices: list[int] = [-1] * MAX_SPOT_SHADOWS; self._spot_shadow_count: int = 0
        self._area_shadow_map: Optional[Any] = None; self._area_shadow_fbo: Optional[Any] = None
        self._area_light_vp: np.ndarray = np.eye(4, dtype=np.float32)
        self._area_shadow_map_back: Optional[Any] = None; self._area_shadow_fbo_back: Optional[Any] = None
        self._area_light_vp_back: np.ndarray = np.eye(4, dtype=np.float32); self._has_area_shadow_back: bool = False
        self._area_shadow_two_sided: float = 0.0; self._has_area_shadow: bool = False; self._area_light_idx: int = -1
        self._area_light_size: float = 1.0; self._area_light_pos: Vec3 = Vec3.zero(); self._area_light_range: float = 10.0
        self._area_light_near: float = 0.1; self._area_light_far: float = 10.0; self._area_light_fov_scale: float = 1.0; self._area_shadow_bias: float = 0.005
        self._projector_shadow_maps: list[Any] = []; self._projector_shadow_fbos: list[Any] = []
        self._projector_light_vps: list[np.ndarray] = [np.eye(4, dtype=np.float32) for _ in range(2)]
        self._has_projector_shadow: list[bool] = [False, False]
        self._shadow_vao_cache: dict[tuple[int, int], moderngl.VertexArray] = {}; self._prog_member_cache: dict[int, frozenset] = {}
        self._shadow_inst_vbo: dict[tuple[int, int], moderngl.Buffer] = {}; self._shadow_inst_vbo_fp: dict[tuple[int, int], tuple] = {}
        self._skinned_bone_ssbo: Optional[Any] = None; self._skinned_bone_ssbo_cap: int = 0
        self._pending_skinned: list = []; self._pending_scene: Any = None; self._skinning_cache: dict = None
        self._shadow_groups_cache: Optional[dict] = None
        self._cascade_matrices_buf = np.zeros((4, 4, 4), dtype=np.float32); self._cascade_splits_buf = np.zeros(4, dtype=np.float32)
        self._point_vps_buf = np.zeros((MAX_POINT_SHADOWS * 6, 4, 4), dtype=np.float32)
        self._point_pos_buf = np.zeros((MAX_POINT_SHADOWS, 3), dtype=np.float32); self._point_range_buf = np.zeros(MAX_POINT_SHADOWS, dtype=np.float32)
        self._point_idx_buf = np.zeros(MAX_POINT_SHADOWS, dtype=np.int32)
        self._spot_vps_buf = np.zeros((MAX_SPOT_SHADOWS, 4, 4), dtype=np.float32); self._spot_idx_buf = np.zeros(MAX_SPOT_SHADOWS, dtype=np.int32)
        self._area_nearfar_buf = np.zeros(2, dtype=np.float32); self._vp_f32_buf = np.zeros((4, 4), dtype=np.float32)
        self._shadow_groups_key: int = 0; self._shadow_groups_ref: Any = None
        self._inv_view_buf = np.zeros((4, 4), dtype=np.float64); self._frustum_corners_buf = np.zeros((8, 3), dtype=np.float64)
        self._cascade_vps_raw = np.zeros((4, 4, 4), dtype=np.float64)
        self._model_pack_buf: Optional[np.ndarray] = None; self._model_pack_buf_cap: int = 0
        self._temporal_frame: int = 0; self._temporal_skip_idx: int = -1
        self._cascade_valid = [False, False, False, False]; self._cascade_stale = [False, False, False, False]; self._cascade_raw_key = [None, None, None, None]
        self._cascade_vp_key = None
        self._prev_flat_centers = np.zeros((0, 3), dtype=np.float64); self._prev_flat_radii = np.zeros(0, dtype=np.float64); self._prev_flat_n: int = 0
        self._shadow_frame_key = None; self._shadow_inst_sel: dict = {}; self._flat_moved_key = None; self._flat_rebuilt_frame = False
        self._cascade_resolutions: list[int] = [2048, 1024, 1024, 512]
        self._last_light_dir: Optional[Vec3] = None; self._last_cam_view_hash: int = 0
        self._import_cache: dict[str, tuple] = {}; self._import_cache_mtime: dict[str, float] = {}
        self._shadow_cache_valid: bool = False; self._type_flags: dict = {'directional': True, 'point': True, 'spot': True, 'area': True}
        self._flat_cap: int = 0; self._flat_n: int = 0; self._flat_sig: Any = None; self._flat_src_list: Any = None
        self._flat_centers = np.zeros((0, 3), dtype=np.float64); self._flat_radii = np.zeros(0, dtype=np.float64)
        self._flat_mats = np.zeros((0, 16), dtype=np.float32); self._flat_mats_f64 = np.zeros((0, 4, 4), dtype=np.float64)
        self._flat_mesh_ids = np.zeros(0, dtype=np.uint64); self._flat_out = np.zeros(0, dtype=np.intp); self._flat_mesh_map: dict = {}
        self._flat_row_base = np.zeros((0,), dtype=np.float64); self._flat_row_tids = np.zeros(0, dtype=np.uint64)
        self._partial_rows = np.zeros(0, dtype=np.intp); self._partial_which = np.zeros(0, dtype=np.intp)
        self._flat_index_src = None; self._flat_index_n: int = 0; self._flat_order = None; self._flat_order_n: int = 0
        self._flat_prep_ver: int = 0; self._flat_order_ver: int = -1; self._flat_max_radius: float = 0.0; self._small_caster_texels: float = 0.5
        self._last_cam_pos = None; self._last_cam_fwd = None
        self._flat_out_multi = np.zeros((0, 0), dtype=np.intp); self._flat_multi_counts = np.zeros(0, dtype=np.intp)
        self._cull_cen_buf = np.zeros((0, 3), dtype=np.float64); self._mesh_radius_cache: dict = {}; self._instancing_cache: dict[int, bool] = {}
        self._point_proj_cache: dict = {}; self._spot_proj_cache: dict = {}
        self._last_view = np.zeros((4, 4), dtype=np.float64); self._last_view_valid: bool = False; self._last_light_dir_xyz: tuple = (0.0, 0.0, 0.0)
        self._cascade_matrices_bytes: bytes = b""; self._cascade_splits_bytes: bytes = b""; self._point_vps_bytes: bytes = b""
        self._point_pos_bytes: bytes = b""; self._point_range_bytes: bytes = b""; self._point_idx_bytes: bytes = b""
        self._spot_vps_bytes: bytes = b""; self._spot_idx_bytes: bytes = b""
        self._area_vp_bytes: bytes = b""; self._area_vp_back_bytes: bytes = b""; self._area_nearfar_bytes: bytes = b""
        self._shadow_origin = None; self._last_static_frame_key = None
        self._point_static_key = None; self._spot_static_key = None; self._area_static_key = None
        self._stained_tex = None; self._stained_fbo = None; self._stained_prog = None
        self._stained_depth_tex = None; self._stained_depth_fbo = None; self._stained_depth_prog = None
        self._stained_vp_bytes: bytes = b""; self._stained_valid: bool = False
        self._create_csm_resources()
