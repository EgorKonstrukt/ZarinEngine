# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.components.lighting import Light
from core.renderer.types import RenderMode


class ConfigStateMixin:
    def load_config(self, config) -> None:
        ambient = config.get("rendering.ambient", self._ambient)
        self._ambient = [ambient[0], ambient[1], ambient[2]]
        sel = config.get("rendering.selection_outline", self._selection_outline_color)
        self._selection_outline_color = [sel[0], sel[1], sel[2], sel[3]]
        self._selection_outline_thickness = config.get("rendering.selection_outline_thickness", self._selection_outline_thickness)
        from core.renderer.meshd import MeshData
        MeshData.outline_max_triangles = int(config.get("rendering.selection_outline_max_tris", MeshData.outline_max_triangles))
        max_lights = int(config.get("rendering.max_lights", self._max_lights))
        if max_lights != self._max_lights:
            self._max_lights = max(1, max_lights)
            self._light_uniforms = [
                {
                    "type": f"u_lights[{i}].type",
                    "position": f"u_lights[{i}].position",
                    "direction": f"u_lights[{i}].direction",
                    "color": f"u_lights[{i}].color",
                    "intensity": f"u_lights[{i}].intensity",
                    "range": f"u_lights[{i}].range",
                    "spot_angle": f"u_lights[{i}].spot_angle",
                    "spot_inner_angle": f"u_lights[{i}].spot_inner_angle",
                    "right": f"u_lights[{i}].right",
                    "up": f"u_lights[{i}].up",
                    "area_width": f"u_lights[{i}].area_width",
                    "area_height": f"u_lights[{i}].area_height",
                    "area_type": f"u_lights[{i}].area_type",
                    "area_samples": f"u_lights[{i}].area_samples",
                    "area_double_sided": f"u_lights[{i}].area_double_sided",
                }
                for i in range(self._max_lights)
            ]
        self._shadow_resolution = config.get("rendering.shadow_resolution", self._shadow_resolution)
        self._shadow_distance = config.get("rendering.shadow_distance", self._shadow_distance)
        self._cascade_count = config.get("rendering.cascade_count", self._cascade_count)
        self._cascade_splits_norm = config.get("rendering.cascade_splits", []) or None
        self._apply_shadow_system_state(update=True)
        self._render_scale = config.get("rendering.render_scale", self._render_scale)
        self._exposure = config.get("rendering.exposure", self._exposure)
        Light.set_light_scale(config.get("rendering.light_scale", 1.0))
        self._line_width = config.get("gizmo.line_width", self._line_width)
        try:
            if getattr(self, "_gizmo", None) is not None:
                self._gizmo._line_width = self._line_width
        except Exception:
            pass
        try:
            if getattr(self, "_grid", None) is not None:
                self._grid.show = config.get("rendering.show_grid", self._grid.show)
                self._grid.grid_size = config.get("rendering.grid_size", self._grid.grid_size)
                try:
                    self._grid._grid_world_size = float(config.get("rendering.grid_world_size", self._grid._grid_world_size))
                except Exception:
                    pass
                self._grid.grid_2d_mode = config.get("rendering.grid_2d_mode", self._grid.grid_2d_mode)
                self._grid.grid_zoom_distance = config.get("rendering.grid_zoom_distance", self._grid.grid_zoom_distance)
        except Exception:
            pass
        try:
            self._skybox_enabled = config.get("rendering.show_skybox", self._skybox_enabled)
        except Exception:
            pass
        try:
            new_rtc = bool(config.get("rendering.high_precision_rtc", getattr(self, "_rtc_enabled", False)))
        except Exception:
            new_rtc = bool(getattr(self, "_rtc_enabled", False))
        try:
            new_gpu = bool(config.get("rendering.high_precision_gpu", getattr(self, "_gpu_double_enabled", False)))
        except Exception:
            new_gpu = bool(getattr(self, "_gpu_double_enabled", False))
        old_rtc = bool(getattr(self, "_rtc_enabled", False))
        old_gpu = bool(getattr(self, "_gpu_double_enabled", False))
        self._rtc_enabled = new_rtc
        self._gpu_double_enabled = new_gpu
        if new_rtc != old_rtc or new_gpu != old_gpu:
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
                return

    def _load_grid_config(self):
        try:
            from core.config.config import get_global_config
            config = get_global_config()
        except Exception:
            return
        if config is None:
            return
        if getattr(self, "_grid", None) is not None:
            try:
                self._grid.show = config.get("rendering.show_grid", self._grid.show)
            except Exception:
                pass
            try:
                self._grid.grid_size = config.get("rendering.grid_size", self._grid.grid_size)
            except Exception:
                pass
            try:
                self._grid._grid_world_size = float(config.get("rendering.grid_world_size", self._grid._grid_world_size))
            except Exception:
                pass
            try:
                self._grid.grid_2d_mode = config.get("rendering.grid_2d_mode", self._grid.grid_2d_mode)
            except Exception:
                pass
            try:
                self._grid.grid_zoom_distance = config.get("rendering.grid_zoom_distance", self._grid.grid_zoom_distance)
            except Exception:
                pass
        try:
            self._skybox_enabled = config.get("rendering.show_skybox", self._skybox_enabled)
        except Exception:
            pass

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
