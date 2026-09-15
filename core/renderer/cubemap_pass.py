# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Dynamic cubemap face rendering."""

from __future__ import annotations
import traceback
import numpy as np
import moderngl
from core.engine.engine import Engine
from core.foundation.logger import Logger
from core.maths.math3d import Mat4, Vec3


class CubemapPassMixin:
    """Dynamic cubemap face rendering."""


    def render_cubemap_face(self, snap, face_fbo, res, view_f32, proj_f32, cam_pos, lights, skip_entity=None, face_index=None):
        try:
            face_fbo.use()
            face_fbo.viewport = (0, 0, res, res)
            self._ctx.viewport = (0, 0, res, res)
            self._ctx.clear(0.0, 0.0, 0.0, 1.0, 1.0)
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.enable(moderngl.CULL_FACE)
            self._ctx.cull_face = 'back'
            self._ctx.disable(moderngl.BLEND)


            sky_component = getattr(snap, 'sky_component', None)
            if (sky_component and getattr(sky_component, 'enabled', False)
                    and self._skybox_cube and self._skybox_enabled):
                try:


                    face_view = Mat4(np.asarray(view_f32, dtype=np.float64).reshape(4, 4))
                    face_proj = Mat4(np.asarray(proj_f32, dtype=np.float64).reshape(4, 4))
                    sky_component.render_sky(self._ctx, self._shaders, face_view, face_proj,
                                             snap.dir_light, self._skybox_cube)
                except Exception:
                    import traceback
                    traceback.print_exc()
            renderable = snap.renderable
            if skip_entity is not None and renderable:
                renderable = [e for e in renderable if e[0] is not skip_entity]
            if renderable:
                if self._batcher:
                    groups = self._batcher.collect_groups(renderable, self._materials, self._shaders)
                    self._batcher.render_groups(
                        groups, view_f32, proj_f32, cam_pos, lights, True,
                        self._set_scene_uniforms, self._materials.apply_material,
                        self._normal_cache, set(), [],
                        gpu_storage=self._gpu_storage)
                else:
                    prog = self._default_prog
                    for entry in renderable:
                        ent, tr, mesh, mr = entry[:4]
                        wm = entry[4]
                        try:
                            mat = self._materials.load_material(mr.get_material_path(0))
                            shader_path = mat.shader_path if mat else ""
                            p = self._shaders.get_or_compile(shader_path if shader_path else "") or prog
                            self._set_scene_uniforms(p, view_f32, proj_f32, cam_pos, lights, disable_shadows=True)
                            names = self._uniform_names(p)
                            model_f32 = wm.to_f32()
                            if "u_model" in names:
                                p["u_model"].write(model_f32.tobytes())
                            nm = np.eye(3, dtype=np.float32).T
                            if "u_normal_matrix" in names:
                                p["u_normal_matrix"].write(nm.tobytes())
                            self._materials.apply_material(mat, p, mr)
                            ds = self._mat_double_sided(mat)
                            self._render_mesh_double_sided(p, mesh, ds)
                        except Exception:
                            pass
            if snap.skinned_renderables:
                if skip_entity is not None:
                    original_skinned = snap.skinned_renderables
                    filtered_skinned = [e for e in original_skinned if e[0] is not skip_entity]
                    if len(filtered_skinned) != len(original_skinned):
                        snap.skinned_renderables = filtered_skinned
                        try:
                            self._render_skinned_meshes(snap, view_f32, proj_f32, cam_pos, lights)
                        finally:
                            snap.skinned_renderables = original_skinned
                    else:
                        self._render_skinned_meshes(snap, view_f32, proj_f32, cam_pos, lights)
                else:
                    self._render_skinned_meshes(snap, view_f32, proj_f32, cam_pos, lights)
            gauss_items = getattr(snap, 'gaussian_splats', None)
            if self._gaussians is not None and gauss_items:
                try:
                    face_view_m = Mat4(np.asarray(view_f32, dtype=np.float64).reshape(4, 4))
                    face_proj_m = Mat4(np.asarray(proj_f32, dtype=np.float64).reshape(4, 4))
                except Exception:
                    face_view_m = None
                    face_proj_m = None
                if face_view_m is not None and face_proj_m is not None:
                    try:
                        eng = Engine.instance()
                    except Exception:
                        eng = None
                    self._ctx.enable(moderngl.DEPTH_TEST)
                    for ent, gs in gauss_items:
                        if skip_entity is not None and ent is skip_entity:
                            continue
                        tr = ent.transform
                        if tr:
                            model = tr.world_matrix
                        else:
                            model = Mat4.identity()
                        try:
                            self._gaussians.render(
                                self._gaussian_ply_path(gs, eng), model, face_view_m, face_proj_m,
                                cam_pos, res, res,
                                gs.opacity_threshold, gs.sh_degree, face_index,
                            )
                        except Exception as e:
                            Logger.error(f"Gaussian Splat cubemap error: {e}")
        except Exception:
            import traceback
            traceback.print_exc()
