# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Any
import numpy as np; import moderngl
from core.renderer.origin import shift_vp_bytes, shift_pos_bytes
class UniformsMixin:
    def _uniform_names(self, prog: moderngl.Program) -> frozenset:
        key = id(prog)
        cached = self._prog_member_cache.get(key)
        if cached is not None:
            return cached
        names = frozenset(prog); self._prog_member_cache[key] = names
        return names
    def _ensure_context(self):
        try:
            from core.engine.engine import Engine
            eng = Engine.instance(); vp = getattr(eng, "viewport", None) if eng else None
            if vp is not None and hasattr(vp, "makeCurrent"):
                try:
                    vp.makeCurrent()
                except Exception:
                    pass
        except Exception:
            pass
    def update_settings(self, shadow_resolution: int = None, shadow_distance: float = None, cascade_count: int = None, area_shadow_resolution: int = None, cascade_splits: list = None, point_shadow_resolution: int = None, spot_shadow_resolution: int = None, type_flags: dict = None, small_caster_texels: float = None):
        changed = False
        if shadow_resolution is not None and shadow_resolution != self._shadow_resolution:
            self._shadow_resolution = shadow_resolution; base = shadow_resolution
            self._cascade_resolutions = [base, max(512, base//2), max(512, base//2), max(256, base//4)]; changed = True
        if shadow_distance is not None and shadow_distance != self._shadow_distance:
            self._shadow_distance = shadow_distance
        if cascade_splits is not None:
            self._cascade_splits_norm = list(cascade_splits) if cascade_splits else None
        if cascade_count is not None:
            cc = max(1, min(cascade_count, 4))
            if cc != self._cascade_count:
                self._cascade_count = cc; changed = True
        if area_shadow_resolution is not None and area_shadow_resolution != self._area_shadow_resolution:
            self._area_shadow_resolution = area_shadow_resolution; changed = True
        if point_shadow_resolution is not None and point_shadow_resolution != self._point_shadow_resolution:
            self._point_shadow_resolution = point_shadow_resolution; changed = True
        if spot_shadow_resolution is not None and spot_shadow_resolution != self._spot_shadow_resolution:
            self._spot_shadow_resolution = spot_shadow_resolution; changed = True
        if type_flags is not None:
            self._type_flags = dict(type_flags)
        if small_caster_texels is not None:
            try:
                self._small_caster_texels = max(0.0, float(small_caster_texels))
            except Exception:
                pass
        if changed:
            self._cascade_valid = [False, False, False, False]; self._cascade_stale = [False, False, False, False]; self._cascade_raw_key = [None, None, None, None]
            try:
                self._cascade_vp_key = None
            except Exception:
                pass
            try:
                self._last_static_frame_key = None; self._point_static_key = None; self._spot_static_key = None; self._area_static_key = None
            except Exception:
                pass
            try:
                self._create_csm_resources()
            except Exception:
                pass
            try:
                self._create_point_shadow_resources()
            except Exception:
                pass
            try:
                self._create_spot_shadow_resources()
            except Exception:
                pass
    def _cache_uniform_bytes(self):
        try:
            cm = self._cascade_matrices_buf
            for ci in range(self._cascade_count):
                np.copyto(cm[ci], self._light_space_matrices[ci])
            self._cascade_matrices_bytes = cm.tobytes()
        except Exception:
            pass
        try:
            cs = self._cascade_splits_buf
            cs[0] = self._cascade_splits[0]; cs[1] = self._cascade_splits[1]; cs[2] = self._cascade_splits[2]; cs[3] = self._cascade_splits[3]
            self._cascade_splits_bytes = cs.tobytes()
        except Exception:
            pass
        try:
            pv = self._point_vps_buf
            for slot in range(self._point_shadow_count):
                base = slot * 6
                for fi in range(6):
                    np.copyto(pv[base + fi], self._point_light_vps[base + fi])
            self._point_vps_bytes = pv.tobytes()
        except Exception:
            pass
        try:
            for slot in range(self._point_shadow_count):
                try:
                    pa = self._point_shadow_light_positions[slot]
                    self._point_pos_buf[slot][0] = float(pa.x); self._point_pos_buf[slot][1] = float(pa.y); self._point_pos_buf[slot][2] = float(pa.z)
                except Exception:
                    pass
                try:
                    self._point_range_buf[slot] = float(self._point_shadow_light_ranges[slot])
                except Exception:
                    pass
                try:
                    self._point_idx_buf[slot] = int(self._point_shadow_light_indices[slot])
                except Exception:
                    pass
            self._point_pos_bytes = self._point_pos_buf.tobytes(); self._point_range_bytes = self._point_range_buf.tobytes(); self._point_idx_bytes = self._point_idx_buf.tobytes()
        except Exception:
            pass
        try:
            sv = self._spot_vps_buf
            for slot in range(self._spot_shadow_count):
                np.copyto(sv[slot], self._spot_shadow_vps[slot])
            self._spot_vps_bytes = sv.tobytes()
        except Exception:
            pass
        try:
            for slot in range(self._spot_shadow_count):
                try:
                    self._spot_idx_buf[slot] = int(self._spot_shadow_light_indices[slot])
                except Exception:
                    pass
            self._spot_idx_bytes = self._spot_idx_buf.tobytes()
        except Exception:
            pass
        try:
            self._area_vp_bytes = np.ascontiguousarray(self._area_light_vp, dtype=np.float32).tobytes()
        except Exception:
            pass
        try:
            self._area_vp_back_bytes = np.ascontiguousarray(self._area_light_vp_back, dtype=np.float32).tobytes()
        except Exception:
            pass
        try:
            af = self._area_nearfar_buf; af[0] = float(self._area_light_near); af[1] = float(self._area_light_far); self._area_nearfar_bytes = af.tobytes()
        except Exception:
            pass
    def set_uniforms(self, prog, origin=None):
        names = self._uniform_names(prog); has_csm = self._cascade_splits[self._cascade_count - 1] > 0.0
        if has_csm and "u_cascade_count" in names and len(self._shadow_maps) >= 1:
            prog["u_cascade_count"].value = self._cascade_count
            if "u_light_space_matrices" in names:
                try:
                    if not self._cascade_matrices_bytes: self._cache_uniform_bytes()
                    prog["u_light_space_matrices"].write(shift_vp_bytes(self._cascade_matrices_bytes, origin))
                except Exception:
                    pass
            if "u_cascade_splits" in names:
                try:
                    if not self._cascade_splits_bytes: self._cache_uniform_bytes()
                    prog["u_cascade_splits"].write(self._cascade_splits_bytes)
                except Exception:
                    pass
            try:
                self._shadow_maps[0].use(28)
            except Exception:
                pass
            if "u_cascade_atlas" in names:
                prog["u_cascade_atlas"].value = 28
            if "u_cascade_rects" in names:
                try:
                    _W = float(getattr(self, '_cascade_atlas_w', 1) or 1); _H = float(getattr(self, '_cascade_atlas_h', 1) or 1)
                    _tx = getattr(self, '_cascade_tile_x', [0, 0, 0, 0]); _tr = getattr(self, '_cascade_tile_res', [0, 0, 0, 0])
                    _rects = np.zeros(16, dtype=np.float32)
                    for _i in range(4):
                        _rx = float(_tx[_i]) if _i < len(_tx) else 0.0; _rr = float(_tr[_i]) if _i < len(_tr) else 0.0
                        _rects[_i * 4:(_i + 1) * 4] = (_rx / _W, 0.0, _rr / _W, _rr / _H)
                    prog["u_cascade_rects"].write(_rects.tobytes())
                except Exception:
                    pass
        else:
            if "u_cascade_count" in names: prog["u_cascade_count"].value = 0
        try:
            _stained_on = bool(self._stained_valid) and self._stained_tex is not None
        except Exception:
            _stained_on = False
        if "u_stained_tex" in names:
            try:
                if _stained_on: self._stained_tex.use(27)
            except Exception:
                pass
            try:
                prog["u_stained_tex"].value = 27
            except Exception:
                pass
        if "u_stained_vp" in names:
            try:
                if _stained_on and self._stained_vp_bytes: prog["u_stained_vp"].write(shift_vp_bytes(self._stained_vp_bytes, origin))
            except Exception:
                pass
        if "u_stained_depth" in names:
            try:
                if _stained_on and self._stained_depth_tex is not None: self._stained_depth_tex.use(26)
            except Exception:
                pass
            try:
                prog["u_stained_depth"].value = 26
            except Exception:
                pass
        if "u_stained_active" in names:
            try:
                prog["u_stained_active"].value = 1.0 if _stained_on else 0.0
            except Exception:
                pass
        if "u_shadow_bias" in names: prog["u_shadow_bias"].value = 0.0015
        if "u_shadow_normal_bias" in names: prog["u_shadow_normal_bias"].value = 0.02
        if "u_shadow_slope_scale" in names: prog["u_shadow_slope_scale"].value = 0.008
        if self._has_point_shadow and "u_point_shadow_count" in names:
            prog["u_point_shadow_count"].value = self._point_shadow_count
            if "u_point_shadow_vps" in names:
                try:
                    if not self._point_vps_bytes: self._cache_uniform_bytes()
                    prog["u_point_shadow_vps"].write(shift_vp_bytes(self._point_vps_bytes, origin))
                except Exception:
                    pass
            if "u_point_shadow_atlas" in names:
                try:
                    self._point_shadow_maps[0].use(29)
                except Exception:
                    pass
                prog["u_point_shadow_atlas"].value = 29
            if "u_point_shadow_light_positions" in names:
                try:
                    if not self._point_pos_bytes: self._cache_uniform_bytes()
                    prog["u_point_shadow_light_positions"].write(shift_pos_bytes(self._point_pos_bytes, origin))
                except Exception:
                    pass
            if "u_point_shadow_light_ranges" in names:
                try:
                    if not self._point_range_bytes: self._cache_uniform_bytes()
                    prog["u_point_shadow_light_ranges"].write(self._point_range_bytes)
                except Exception:
                    pass
            if "u_point_shadow_light_indices" in names:
                try:
                    if not self._point_idx_bytes: self._cache_uniform_bytes()
                    prog["u_point_shadow_light_indices"].write(self._point_idx_bytes)
                except Exception:
                    pass
        else:
            if "u_point_shadow_count" in names: prog["u_point_shadow_count"].value = 0
        if self._has_spot_shadow and "u_spot_shadow_count" in names:
            prog["u_spot_shadow_count"].value = self._spot_shadow_count
            if "u_spot_shadow_vps" in names:
                try:
                    if not self._spot_vps_bytes: self._cache_uniform_bytes()
                    prog["u_spot_shadow_vps"].write(shift_vp_bytes(self._spot_vps_bytes, origin))
                except Exception:
                    pass
            if "u_spot_shadow_atlas" in names:
                try:
                    self._spot_shadow_maps[0].use(30)
                except Exception:
                    pass
                prog["u_spot_shadow_atlas"].value = 30
            if "u_spot_shadow_light_indices" in names:
                try:
                    if not self._spot_idx_bytes: self._cache_uniform_bytes()
                    prog["u_spot_shadow_light_indices"].write(self._spot_idx_bytes)
                except Exception:
                    pass
        else:
            if "u_spot_shadow_count" in names: prog["u_spot_shadow_count"].value = 0
        if self._has_area_shadow and "u_area_shadow_light_index" in names:
            tex_unit = 35
            try:
                self._area_shadow_map.use(tex_unit)
            except Exception:
                pass
            if "u_area_shadow_map" in names: prog["u_area_shadow_map"].value = tex_unit
            if "u_area_light_vp" in names:
                try:
                    if not self._area_vp_bytes: self._cache_uniform_bytes()
                    prog["u_area_light_vp"].write(shift_vp_bytes(self._area_vp_bytes, origin))
                except Exception:
                    pass
            if "u_area_light_size" in names: prog["u_area_light_size"].value = float(self._area_light_size)
            if "u_area_light_fov_scale" in names: prog["u_area_light_fov_scale"].value = float(self._area_light_fov_scale)
            if "u_area_light_near_far" in names:
                try:
                    if not self._area_nearfar_bytes: self._cache_uniform_bytes()
                    prog["u_area_light_near_far"].write(self._area_nearfar_bytes)
                except Exception:
                    pass
            if "u_area_shadow_light_index" in names: prog["u_area_shadow_light_index"].value = self._area_light_idx if self._area_light_idx >= 0 else -1
            if "u_area_shadow_bias" in names: prog["u_area_shadow_bias"].value = float(self._area_shadow_bias)
            back_ok = bool(self._has_area_shadow_back and self._area_shadow_map_back is not None and self._area_shadow_two_sided > 0.5)
            if "u_area_shadow_map_back" in names:
                try:
                    if back_ok: self._area_shadow_map_back.use(38)
                except Exception:
                    pass
                prog["u_area_shadow_map_back"].value = 38
            if "u_area_light_vp_back" in names:
                try:
                    if not self._area_vp_back_bytes: self._cache_uniform_bytes()
                    prog["u_area_light_vp_back"].write(shift_vp_bytes(self._area_vp_back_bytes, origin))
                except Exception:
                    pass
            if "u_area_shadow_back" in names: prog["u_area_shadow_back"].value = 1.0 if back_ok else 0.0
        else:
            if "u_area_shadow_light_index" in names: prog["u_area_shadow_light_index"].value = -1
            if "u_area_shadow_back" in names: prog["u_area_shadow_back"].value = 0.0
        for i in range(2):
            suf = f"u_pj_{i}_shadow_map"
            if self._has_projector_shadow[i] and suf in names:
                tex_unit = 36 + i
                if i < len(self._projector_shadow_maps):
                    try:
                        self._projector_shadow_maps[i].use(tex_unit)
                    except Exception:
                        pass
                    prog[suf].value = tex_unit
                vpn = f"u_pj_{i}_shadow_vp"
                if vpn in names:
                    try:
                        prog[vpn].write(self._projector_light_vps[i].tobytes())
                    except Exception:
                        pass
            elif suf in names:
                prog[suf].value = 0
    def release(self):
        for sm in self._shadow_maps:
            try: sm.release()
            except Exception: pass
        for fbo in self._shadow_fbos:
            try: fbo.release()
            except Exception: pass
        for sm in self._point_shadow_maps:
            try: sm.release()
            except Exception: pass
        for fbo in self._point_shadow_fbos:
            try: fbo.release()
            except Exception: pass
        for sm in self._spot_shadow_maps:
            try: sm.release()
            except Exception: pass
        for fbo in self._spot_shadow_fbos:
            try: fbo.release()
            except Exception: pass
        if self._area_shadow_map:
            try: self._area_shadow_map.release()
            except Exception: pass
        if self._area_shadow_fbo:
            try: self._area_shadow_fbo.release()
            except Exception: pass
        if self._area_shadow_map_back:
            try: self._area_shadow_map_back.release()
            except Exception: pass
        if self._area_shadow_fbo_back:
            try: self._area_shadow_fbo_back.release()
            except Exception: pass
        for sm in self._projector_shadow_maps:
            try: sm.release()
            except Exception: pass
        for fbo in self._projector_shadow_fbos:
            try: fbo.release()
            except Exception: pass
        for vbo in self._shadow_inst_vbo.values():
            try: vbo.release()
            except Exception: pass
        self._shadow_inst_vbo.clear(); self._shadow_inst_vbo_fp.clear(); self._shadow_inst_sel.clear()
        self._shadow_vao_cache.clear(); self._prog_member_cache.clear()
        self._shadow_frame_key = None; self._flat_moved_key = None; self._flat_rebuilt_frame = False; self._flat_rebuilt_frame = False
        if self._skinned_bone_ssbo is not None:
            try: self._skinned_bone_ssbo.release()
            except Exception: pass
            self._skinned_bone_ssbo = None
