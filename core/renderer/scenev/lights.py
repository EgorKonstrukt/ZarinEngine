# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
from typing import Optional, Any


class ScenevLightsMixin:
    def _scenev_render_shadow_pass(self, snap, scene, view_mat, cam_near, cam_far, cam_fov, aspect, shared_cache=None):
        shadow_groups = {}
        try:
            self._apply_shadow_system_state(update=True)
        except Exception:
            pass
        warm = False
        try:
            if self._shadow_warmup > 0:
                warm = True
                if not self._rendering_cubemap_face:
                    self._shadow_warmup -= 1
        except Exception:
            warm = False
        try:
            if not self._shadow_enabled:
                try:
                    self._shadows.reset_shadow_state()
                except Exception:
                    pass
            elif shared_cache is not None and "shadow_groups" in shared_cache and not warm:
                shadow_groups = shared_cache["shadow_groups"]
            else:
                need = False if warm else (bool(snap.shadow_renderables) or bool(snap.skinned_shadow_renderables) or any(getattr(l, "cast_shadows", False) for l, _ in snap.lights))
                if need:
                    try:
                        try:
                            tint_casters = snap.transparent_shadow_casters
                        except Exception:
                            tint_casters = None
                        shadow_groups = self._shadows.render_shadow_pass(snap.shadow_renderables, snap.lights, cam_near, cam_far, cam_fov, aspect, view_mat, {}, skinned_entries=snap.skinned_shadow_renderables, scene=scene, skinning_cache=self._skinning_cache, tint_casters=tint_casters, material_manager=self._materials)
                        if snap.projectors:
                            self._shadows.render_projector_shadows(snap.projectors, snap.shadow_renderables, shadow_groups)
                    except Exception:
                        import traceback as _tb
                        _tb.print_exc()
                else:
                    try:
                        self._shadows.reset_shadow_state()
                    except Exception:
                        pass
                if shared_cache is not None:
                    shared_cache["shadow_groups"] = shadow_groups
        except Exception:
            pass
        return shadow_groups

    def _scenev_bind_scene_ibl(self, prog, mr, dynamic_cubemaps, sky_component):
        try:
            names = self._uniform_names(prog)
        except Exception:
            return
        try:
            if getattr(mr, "dynamic_reflections", False) and dynamic_cubemaps is not None:
                dynamic_cubemaps.bind_ibl(prog)
            elif getattr(sky_component, "_sky_ibl", None) is not None and sky_component._sky_ibl.ready:
                sky_component._sky_ibl.bind(prog)
            elif not getattr(mr, "dynamic_reflections", False):
                try:
                    if "u_irradiance_map_Active" in names:
                        prog["u_irradiance_map_Active"].value = 0
                    if "u_prefilter_map_Active" in names:
                        prog["u_prefilter_map_Active"].value = 0
                    if "u_brdf_lut_Active" in names:
                        prog["u_brdf_lut_Active"].value = 0
                    if "u_irradiance_map" in names:
                        prog["u_irradiance_map"].value = 14
                    if "u_prefilter_map" in names:
                        prog["u_prefilter_map"].value = 15
                    if "u_brdf_lut" in names:
                        prog["u_brdf_lut"].value = 16
                except Exception:
                    pass
        except Exception:
            pass

    def _scenev_render_projectors(self, snap, view_mat, proj_mat, rw, rh):
        if not snap.projectors:
            return
        try:
            self._scene_fbo.use()
            self._scene_fbo.viewport = (0, 0, rw, rh)
            self._ctx.viewport = (0, 0, rw, rh)
            self._ctx.disable(moderngl.DEPTH_TEST)
            self._ctx.enable(moderngl.BLEND)
            self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
            proj = self._projector_prog
            combined = view_mat @ proj_mat
            inv_vp = combined.inverted().to_f32()
            proj["u_inv_vp"].write(inv_vp.tobytes())
            proj["u_depth_tex"] = 14
            self._scene_depth_tex.use(14)
            self._shadows.set_uniforms(proj)
            count = min(len(snap.projectors), 2)
            proj["u_projector_count"].value = count
            for i in range(count):
                px = snap.projectors[i]
                suf = "u_pj_" + str(i) + "_"
                proj[suf + "vp"].write(px.vp_matrix.tobytes())
                proj[suf + "pos"].value = tuple(float(v) for v in px.position)
                proj[suf + "dir"].value = tuple(float(v) for v in px.direction)
                proj[suf + "color"].value = tuple(float(v) for v in px.color)
                proj[suf + "intensity"].value = float(px.intensity)
                proj[suf + "range"].value = float(px.range)
                proj[suf + "spot_angle"].value = float(px.spot_angle)
                tex_loaded = False
                if px.texture_path and self._materials:
                    tex = self._materials.load_texture(px.texture_path)
                    if tex:
                        tex_unit = 20 + i
                        tex.use(tex_unit)
                        proj[suf + "tex"].value = tex_unit
                        tex_loaded = True
                proj[suf + "has_tex"].value = 1.0 if tex_loaded else 0.0
                proj[suf + "flip_y"].value = 1.0 if px.flip_y else 0.0
                proj[suf + "flip_x"].value = 1.0 if px.flip_x else 0.0
            self._projector_vao.render()
            self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self._ctx.enable(moderngl.DEPTH_TEST)
        except Exception:
            try:
                self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                self._ctx.enable(moderngl.DEPTH_TEST)
            except Exception:
                pass

    def _scenev_dispatch_raytracing(self, scene, view_mat, proj_mat, cam_pos, viewport_w, viewport_h):
        if not scene:
            return
        try:
            idx = scene._component_indices.get("RaytracingRenderer")
        except Exception:
            idx = True
        ents = []
        if idx:
            try:
                from core.components.rendering.renderers.raytrace import RaytracingRenderer
                try:
                    ents = scene.get_entities_with_component(RaytracingRenderer)
                except Exception:
                    ents = []
            except Exception:
                return
        for ent in ents:
            if not ent.active:
                continue
            rtr = ent.get_component(RaytracingRenderer)
            if rtr and rtr.enabled:
                if rtr._dispatch(self._ctx, viewport_w, viewport_h, view_mat, proj_mat, cam_pos, scene, self):
                    rtr.blit_to_screen(self._ctx, viewport_w, viewport_h)
                    rtr._blit_to_fbo(self._ctx, self._scene_fbo, viewport_w, viewport_h)
                    self._rt_rays_per_frame = rtr._rays_per_frame
                break
        else:
            try:
                self._rt_rays_per_frame = 0
            except Exception:
                pass

    def _scenev_dispatch_gi(self, scene, view_mat, proj_mat, cam_pos, viewport_w, viewport_h, cam_near, cam_far):
        if not scene:
            return
        try:
            idx = scene._component_indices.get("RadianceCascadesGI")
        except Exception:
            idx = True
        ents = []
        if idx:
            try:
                from core.components.rendering.environment.radiance import RadianceCascadesGI
                try:
                    ents = scene.get_entities_with_component(RadianceCascadesGI)
                except Exception:
                    ents = []
            except Exception:
                return
        for ent in ents:
            if not ent.active:
                continue
            gi = ent.get_component(RadianceCascadesGI)
            if gi and gi.enabled:
                if gi._dispatch(self._ctx, viewport_w, viewport_h, view_mat, proj_mat, cam_pos, scene, self, cam_near, cam_far):
                    gi._blit_to_fbo(self._ctx, self._scene_fbo, viewport_w, viewport_h)
                    gi.blit_to_screen(self._ctx, viewport_w, viewport_h)
                break
