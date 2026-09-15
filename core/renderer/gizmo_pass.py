# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Gizmo debug rendering."""

from __future__ import annotations
import numpy as np
from typing import Optional, Any, Callable
from core.maths.math3d import Mat4, Vec3


class GizmoPassMixin:
    """Gizmo debug rendering."""


    def render_gizmo_lines(self, lines, vp_mat: Mat4, cam_pos: Optional[Vec3] = None,
                           fw: int = 1920, fh: int = 1080, thickness_multiplier: float = 1.0):
        if self._gizmo:
            self._gizmo.render_lines(lines, vp_mat, fw, fh, thickness_multiplier)


    def render_gizmo_arrays(self, starts: np.ndarray, ends: np.ndarray, colors: np.ndarray,
                             vp_mat: Mat4, fw: int = 1920, fh: int = 1080, thickness_multiplier: float = 1.0,
                             dash_opts: Optional[dict] = None, dirty: bool = True):
        if self._gizmo:
            desired_pixels = max(1.0, float(self._line_width) * 1.5 * thickness_multiplier)
            self._gizmo.render_raw_lines(starts, ends, colors, vp_mat, fw, fh, desired_pixels, dash_opts, dirty)


    def render_instanced_gizmo(self, mesh_type: str, instance_data: np.ndarray, vp_mat: Mat4, num_instances: int):
        if not self._gizmo:
            return
        mesh_map = {
            'cone': self._gizmo._cone_mesh,
            'cylinder': self._gizmo._cylinder_mesh,
            'cube': self._gizmo._cube_mesh,
            'quad': self._gizmo._quad_mesh,
            'circle': self._gizmo._circle_mesh,
        }
        mesh = mesh_map.get(mesh_type)
        if mesh is not None:
            self._gizmo.render_instanced(mesh, instance_data, vp_mat, num_instances)


    def render_gizmo_meshes(self, meshes: list[tuple], vp_mat: Mat4):
        if self._gizmo:
            self._gizmo.render_meshes(meshes, vp_mat)


    def render_gizmo_mesh_np(self, v_data: np.ndarray, idx_arr: np.ndarray, vp_mat: Mat4):
        if self._gizmo:
            self._gizmo.render_mesh_np(v_data, idx_arr, vp_mat)


    def render_instanced_gizmo_lines(self, shape_type: str, instance_data: np.ndarray,
                                      num_instances: int, vp_mat: Mat4,
                                      fw: int = 1920, fh: int = 1080,
                                      thickness_multiplier: float = 1.0,
                                      cam_pos: Vec3 = Vec3(0, 0, 0)):
        if self._gizmo:
            self._gizmo.render_instanced_lines(shape_type, instance_data, num_instances,
                                                vp_mat, fw, fh, thickness_multiplier, cam_pos)


    def render_wireframe_box(self, center: Vec3, size: Vec3, color: list[float], vp_mat: Mat4):
        if self._gizmo:
            self._gizmo.render_wireframe_box(center, size, color, vp_mat)
