# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Renderer configuration and cache state."""

from __future__ import annotations
from core.components.lighting import Light, Projector
from core.engine.engine import Engine
from core.renderer.types import RenderMode
from core.renderer.mesh_data import MeshData, read_shader
from core.components.rendering.environment.sky import Sky, release_env_cache


class RendererConfigMixin:
    """Renderer configuration and cache state."""


    _effects_disabled: bool = False


    def load_config(self, config) -> None:
        ambient = config.get("rendering.ambient", self._ambient)
        self._ambient = [ambient[0], ambient[1], ambient[2]]
        sel = config.get("rendering.selection_outline", self._selection_outline_color)
        self._selection_outline_color = [sel[0], sel[1], sel[2], sel[3]]
        self._selection_outline_thickness = config.get("rendering.selection_outline_thickness", self._selection_outline_thickness)
        from core.renderer.mesh_data import MeshData
        MeshData.outline_max_triangles = int(config.get("rendering.selection_outline_max_tris", MeshData.outline_max_triangles))
        self._max_lights = config.get("rendering.max_lights", self._max_lights)
        self._shadow_resolution = config.get("rendering.shadow_resolution", self._shadow_resolution)
        self._shadow_distance = config.get("rendering.shadow_distance", self._shadow_distance)
        self._cascade_count = config.get("rendering.cascade_count", self._cascade_count)
        self._cascade_splits_norm = config.get("rendering.cascade_splits", []) or None
        self._apply_shadow_system_state(update=True)
        self._render_scale = config.get("rendering.render_scale", self._render_scale)
        self._exposure = config.get("rendering.exposure", self._exposure)
        Light.set_light_scale(config.get("rendering.light_scale", 1.0))
        self._line_width = config.get("gizmo.line_width", self._line_width)


    def _apply_shadow_system_state(self, update: bool = True) -> bool:
        from core.components.rendering.environment.directional_shadow import DirectionalShadow
        from core.components.rendering.environment.point_shadow import PointShadow
        from core.components.rendering.environment.spot_shadow import SpotShadow
        from core.components.rendering.environment.area_shadow import AreaShadow
        d = DirectionalShadow.find_active()
        p = PointShadow.find_active()
        s = SpotShadow.find_active()
        a = AreaShadow.find_active()
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


    def _load_grid_config(self):
        eng = Engine.instance()
        config = eng.config if eng and hasattr(eng, 'config') else None
        if not config:
            return
        if self._grid:
            self._grid.show = config.get("rendering.show_grid", self._grid.show)
            self._grid.grid_size = config.get("rendering.grid_size", self._grid.grid_size)
            self._grid.grid_2d_mode = config.get("rendering.grid_2d_mode", self._grid.grid_2d_mode)
            self._grid.grid_zoom_distance = config.get("rendering.grid_zoom_distance", self._grid.grid_zoom_distance)
        self._skybox_enabled = config.get("rendering.show_skybox", self._skybox_enabled)


    @property
    def show_grid(self) -> bool:
        return self._grid.show if self._grid else False


    @show_grid.setter
    def show_grid(self, v: bool):
        if self._grid:
            self._grid.show = v


    @property
    def grid_2d_mode(self) -> bool:
        return self._grid.grid_2d_mode if self._grid else False


    @grid_2d_mode.setter
    def grid_2d_mode(self, v: bool):
        if self._grid:
            self._grid.grid_2d_mode = v


    @property
    def grid_zoom_distance(self) -> float:
        return self._grid.grid_zoom_distance if self._grid else 0.0


    @grid_zoom_distance.setter
    def grid_zoom_distance(self, v: float):
        if self._grid:
            self._grid.grid_zoom_distance = v


    @property
    def grid_size(self) -> float:
        return self._grid.grid_size if self._grid else 10.0


    @grid_size.setter
    def grid_size(self, v: float):
        if self._grid:
            self._grid.grid_size = v


    @property
    def clear_color(self) -> list:
        return self._clear_color


    @clear_color.setter
    def clear_color(self, v: list):
        self._clear_color = list(v[:3]) if v else [0.18, 0.18, 0.18]


    @property
    def ambient(self) -> list[float]:
        return self._ambient


    @ambient.setter
    def ambient(self, v: list[float]):
        self._ambient = v


    @property
    def render_mode(self) -> RenderMode:
        return self._render_mode


    @render_mode.setter
    def render_mode(self, v: RenderMode):
        self._render_mode = v


    @property
    def skybox_enabled(self) -> bool:
        return self._skybox_enabled


    @skybox_enabled.setter
    def skybox_enabled(self, v: bool):
        self._skybox_enabled = v


    def clear_scene_caches(self):
        """Clear per-frame caches on scene reload. Does NOT clear mesh/material
        caches to avoid reloading all 3D models after play mode toggle."""
        self._normal_cache.clear()
        self._prog_member_cache.clear()
        self._import_meta_cache.clear()
        self._import_meta_mtime.clear()
        self._snap_cache = None
        self._snap_version = -1
        self._snap_scene = None
        self._release_morph_cache()
        self._snap_morph_sig = ()


    def release_all_caches(self):
        """Clear mesh, material and texture caches. Called when loading a
        completely different scene (not on play mode toggle)."""
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
