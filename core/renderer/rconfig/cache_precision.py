# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.components.rendering.environment.skyp import release_env_cache


class CachePrecisionMixin:
    _effects_disabled: bool = False

    def _apply_shadow_system_state(self, update: bool = True) -> bool:
        cls_cache = getattr(self, "_shadow_cls", None)
        if cls_cache is None:
            from core.components.rendering.environment.directional_shadow import DirectionalShadow as _D
            from core.components.rendering.environment.point_shadow import PointShadow as _P
            from core.components.rendering.environment.spot_shadow import SpotShadow as _S
            from core.components.rendering.environment.area_shadow import AreaShadow as _A
            cls_cache = (_D, _P, _S, _A)
            self._shadow_cls = cls_cache
            self._shadow_state_sig = False
            self._shadow_splits_cache = None
        _D, _P, _S, _A = cls_cache
        d = _D.find_active()
        p = _P.find_active()
        s = _S.find_active()
        a = _A.find_active()
        if d is not None:
            try:
                _ds = d._cascade_splits
            except Exception:
                _ds = []
            try:
                sig = (d, p, s, a, d._shadow_resolution, d._shadow_distance, d._cascade_count,
                       _ds == getattr(self, "_shadow_splits_cache", None),
                       getattr(p, "_shadow_resolution", 0) if p is not None else 0,
                       getattr(s, "_shadow_resolution", 0) if s is not None else 0,
                       getattr(a, "_shadow_resolution", 0) if a is not None else 0)
            except Exception:
                sig = None
        else:
            try:
                sig = (None, p, s, a,
                       getattr(p, "_shadow_resolution", 0) if p is not None else 0,
                       getattr(s, "_shadow_resolution", 0) if s is not None else 0,
                       getattr(a, "_shadow_resolution", 0) if a is not None else 0)
            except Exception:
                sig = None
        if sig is not None and sig == getattr(self, "_shadow_state_sig", None):
            return self._shadow_enabled
        self._shadow_state_sig = sig
        try:
            self._shadow_splits_cache = list(_ds) if d is not None else None
        except Exception:
            pass
        directional = d is not None
        point = p is not None
        spot = s is not None
        area = a is not None
        if d is not None:
            self._shadow_resolution = int(d._shadow_resolution)
            self._shadow_distance = float(d._shadow_distance)
            self._cascade_count = int(d._cascade_count)
            self._cascade_splits_norm = list(d._cascade_splits) or None
        if p is not None:
            self._point_shadow_resolution = int(p._shadow_resolution)
        if s is not None:
            self._spot_shadow_resolution = int(s._shadow_resolution)
        if a is not None:
            self._area_shadow_resolution = int(a._shadow_resolution)
        self._shadow_type_flags = {
            'directional': directional,
            'point': point,
            'spot': spot,
            'area': area,
        }
        self._shadow_enabled = bool(directional or point or spot or area)
        if update and self._shadows:
            try:
                self._shadows.update_settings(
                    shadow_resolution=self._shadow_resolution,
                    shadow_distance=self._shadow_distance,
                    cascade_count=self._cascade_count,
                    cascade_splits=self._cascade_splits_norm,
                    area_shadow_resolution=self._area_shadow_resolution,
                    point_shadow_resolution=self._point_shadow_resolution,
                    spot_shadow_resolution=self._spot_shadow_resolution,
                    type_flags=self._shadow_type_flags,
                )
            except Exception:
                pass
        return self._shadow_enabled

    def clear_scene_caches(self):
        self._normal_cache.clear()
        self._prog_member_cache.clear()
        self._import_meta_cache.clear()
        self._import_meta_mtime.clear()
        self._snap_cache = None
        self._snap_version = -1
        self._snap_scene = None
        self._release_morph_cache()
        self._snap_morph_sig = ()
        try:
            self._shadow_warmup = 2
        except Exception:
            pass

    def release_all_caches(self):
        self._normal_cache.clear()
        self._prog_member_cache.clear()
        self._import_meta_cache.clear()
        self._import_meta_mtime.clear()
        self._snap_cache = None
        self._snap_version = -1
        self._snap_scene = None
        if self._materials:
            self._materials.clear_caches()
        release_env_cache()
        if self._mesh_loader:
            self._mesh_loader.clear_scene_data()
        self._release_morph_cache()
        self._snap_morph_sig = ()

    def set_effects_enabled(self, enabled: bool):
        self._effects_disabled = not enabled

    @property
    def effects_enabled(self) -> bool:
        return not self._effects_disabled

    @property
    def rtc_enabled(self) -> bool:
        return bool(getattr(self, "_rtc_enabled", False))

    @rtc_enabled.setter
    def rtc_enabled(self, v: bool):
        self.set_rtc_enabled(v)

    @property
    def gpu_double_enabled(self) -> bool:
        return bool(getattr(self, "_gpu_double_enabled", False))

    @gpu_double_enabled.setter
    def gpu_double_enabled(self, v: bool):
        self.set_gpu_double_enabled(v)

    def set_rtc_enabled(self, enabled: bool):
        flag = bool(enabled)
        if bool(getattr(self, "_rtc_enabled", False)) == flag:
            return
        self._rtc_enabled = flag
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            if cfg is not None:
                cfg.set("rendering.high_precision_rtc", flag, notify=False)
                try:
                    cfg.save()
                except Exception:
                    pass
        except Exception:
            pass
        self._rebuild_precision_programs()

    def set_gpu_double_enabled(self, enabled: bool):
        flag = bool(enabled)
        if bool(getattr(self, "_gpu_double_enabled", False)) == flag:
            return
        self._gpu_double_enabled = flag
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            if cfg is not None:
                cfg.set("rendering.high_precision_gpu", flag, notify=False)
                try:
                    cfg.save()
                except Exception:
                    pass
        except Exception:
            pass
        self._rebuild_precision_programs()

    def _rebuild_precision_programs(self):
        try:
            if getattr(self, "_shaders", None) is not None:
                try:
                    self._shaders.release()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._prog_member_cache.clear()
        except Exception:
            pass
        try:
            fx_cache = getattr(self, "_fx_prog_cache", None)
            if fx_cache is not None:
                fx_cache.clear()
        except Exception:
            pass
        try:
            from core.components.rendering.postfx.graphics_effect import GraphicsEffect
            GraphicsEffect.clear_res_caches()
        except Exception:
            pass
        if bool(getattr(self, "_initialized", False)):
            try:
                self.release()
            except Exception:
                pass
            try:
                self.initialize()
            except Exception:
                pass
