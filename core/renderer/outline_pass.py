# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Selection outline rendering."""

from __future__ import annotations
import numpy as np
from core.foundation.logger import Logger
from core.components.rendering.renderers.mesh_filter import MeshFilter
from core.components.rendering.renderers.mesh_renderer import MeshRenderer
from core.maths.math3d import Mat4, Vec3
from core.renderer.mesh_data import MeshData, read_shader


class OutlinePassMixin:
    """Selection outline rendering."""


    def _render_single_outline(self, mesh: MeshData, model_mat: Mat4, view_mat: Mat4, proj_mat: Mat4):
        if not self._outline_prog or not mesh:
            return
        outline_color = self._selection_outline_color
        old_wireframe = self._ctx.wireframe
        old_depth_mask = self._ctx.depth_mask
        try:
            mvp = model_mat * view_mat * proj_mat
            if "u_mvp" in self._outline_prog:
                self._outline_prog["u_mvp"].write(mvp.to_f32().tobytes())
            if "u_outline_color" in self._outline_prog:
                self._outline_prog["u_outline_color"].write(np.array(outline_color, dtype=np.float32).tobytes())
            self._ctx.depth_mask = False
            self._ctx.wireframe = True
            mesh.render_outline()
        except Exception as e:
            Logger.error("Outline render failed in _render_single_outline", e)
        finally:
            self._ctx.wireframe = old_wireframe
            self._ctx.depth_mask = old_depth_mask


    def render_entity_outline(self, entity, model_mat: Mat4, view_mat: Mat4, proj_mat: Mat4, color: list[float]):
        if not self._outline_prog:
            return
        from core.components.rendering.renderers.mesh_filter import MeshFilter
        from core.components.rendering.renderers.mesh_renderer import MeshRenderer
        mf = entity.get_component(MeshFilter)
        mr = entity.get_component(MeshRenderer)
        if not mf or not mr or not mr.enabled:
            return
        mesh = None
        try:
            from core.components.physics.soft_body import SoftBody
            soft = entity.get_component(SoftBody)
            if soft is not None and getattr(soft, "enabled", True):
                ov = getattr(soft, "_render_mesh", None)
                if ov is not None and getattr(ov, "_soft_n", 0) > 0:
                    self._soft_upload_if_dirty(ov)
                    mesh = ov
        except Exception:
            mesh = None
        if mesh is None:
            mesh = self._lookup_outline_mesh(mf)
        if not mesh:
            return
        old_wireframe = self._ctx.wireframe
        old_depth_mask = self._ctx.depth_mask
        try:
            mvp = model_mat * view_mat * proj_mat
            if "u_mvp" in self._outline_prog:
                self._outline_prog["u_mvp"].write(mvp.to_f32().tobytes())
            if "u_outline_color" in self._outline_prog:
                self._outline_prog["u_outline_color"].write(np.array(color, dtype=np.float32).tobytes())
            self._ctx.depth_mask = False
            self._ctx.wireframe = True
            mesh.render_outline()
        except Exception as e:
            Logger.error("render_entity_outline failed", e)
        finally:
            self._ctx.wireframe = old_wireframe
            self._ctx.depth_mask = old_depth_mask
