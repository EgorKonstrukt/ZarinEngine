# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
import numpy as np
import moderngl
from typing import Optional, Any
from core.engine.eng import Engine
from core.components.lighting import Light
from core.maths.math3d import Mat4, Vec3
from core.renderer.batch import resolve_normal_matrix
from core.renderer.origin import origin_for, relativize_model_f32


class ScenevForwardMixin:
    def _scenev_render_forward_phases(self, opaque_entries, transparent_entries, view_f32, proj_f32, cam_pos, lights, dynamic_cubemaps, sky_component, selected_entities, outline_queue, rw, rh, snap=None):
        try:
            self._materials._transmission_bg = None
        except Exception:
            pass
        self._opaque_draws = 0
        self._trans_draws = 0
        try:
            sky_ibl = getattr(sky_component, "_sky_ibl", None) if sky_component else None
        except Exception:
            sky_ibl = None
        try:
            sel = selected_entities or set()
        except Exception:
            sel = set()
        try:
            _tv = snap.transform_version if snap is not None else None
        except Exception:
            _tv = None
        try:
            _org = origin_for(cam_pos)
            _orgkey = None if _org is None else (float(_org[0]), float(_org[1]), float(_org[2]))
        except Exception:
            _orgkey = None
        _seen = getattr(self, "_fwd_seen_frames", None)
        if not isinstance(_seen, set):
            _seen = set()
            self._fwd_seen_frames = _seen
        if _tv != getattr(self, "_fwd_seen_tv", None):
            _seen.clear()
            self._fwd_seen_tv = _tv
        _fkey = (_tv, _orgkey)
        _static_frame = bool(_tv is not None and _fkey in _seen)
        _seen.add(_fkey)
        if len(_seen) > 32:
            _seen.clear()
            _seen.add(_fkey)
        try:
            _has_fx = bool(snap.has_fx) if snap is not None else True
        except Exception:
            _has_fx = True
        try:
            self._fwd_stats_groups = []
        except Exception:
            pass
        phases = ((False, opaque_entries), (True, transparent_entries))
        for is_trans, phase_entries in phases:
            if not phase_entries:
                continue
            refresh_hook = None
            if is_trans:
                try:
                    self._scene_fbo.use()
                    self._ctx.viewport = (0, 0, rw, rh)
                    self._ctx.enable(moderngl.BLEND)
                    self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                    self._ctx.depth_mask = False
                except Exception:
                    pass
                try:
                    sr_self = self
                    def _hook(_m=None, _s=sr_self, _w=rw, _h=rh):
                        try:
                            _s._recapture_transmission_bg(_w, _h)
                        except Exception:
                            pass
                    refresh_hook = _hook
                except Exception:
                    refresh_hook = None
                try:
                    need_bg = False
                    seen = set()
                    for te in transparent_entries:
                        try:
                            tmr = te[3]
                            mats = tmr.materials if tmr is not None else None
                        except Exception:
                            mats = None
                        if mats:
                            try:
                                sub = te[5]
                                mp = mats[sub].get("path", "") if sub < len(mats) else mats[-1].get("path", "")
                            except Exception:
                                mp = ""
                        else:
                            mp = ""
                        if mp in seen:
                            continue
                        seen.add(mp)
                        try:
                            mt = self._materials.load_material(mp)
                            pr = mt.properties if mt is not None else {}
                            if float(pr.get("_Transmission", pr.get("transmission", 0.0))) > 0.001:
                                need_bg = True
                                break
                        except Exception:
                            pass
                    if need_bg:
                        try:
                            self._recapture_transmission_bg(rw, rh)
                        except Exception:
                            pass
                except Exception:
                    pass
            if _has_fx:
                fx_list = [e for e in phase_entries if len(e) > 6 and e[6]]
            else:
                fx_list = []
            if fx_list:
                try:
                    self._render_object_effects(fx_list, view_f32, proj_f32, cam_pos, lights, selected_entities, outline_queue)
                except Exception:
                    pass
                phase_entries = [e for e in phase_entries if not (len(e) > 6 and e[6])]
                if not phase_entries:
                    continue
            if self._batcher is not None:
                try:
                    groups = self._scenev_collect_groups(phase_entries)
                except Exception:
                    groups = {}
                try:
                    self._fwd_stats_groups.append(groups)
                except Exception:
                    pass
                try:
                    all_vis = self._culled_visible == self._culled_total
                except Exception:
                    all_vis = False
                try:
                    if _static_frame and all_vis and not is_trans and groups:
                        _gskip = set(groups.keys())
                    else:
                        _gskip = None
                except Exception:
                    _gskip = None
                try:
                    self._batcher.render_groups(groups, view_f32, proj_f32, cam_pos, lights, False, self._set_scene_uniforms, self._materials.apply_material, self._normal_cache, sel, outline_queue, gpu_storage=self._gpu_storage, dynamic_cubemaps=dynamic_cubemaps, sky_ibl=sky_ibl, skip_cull=bool(all_vis), sort_groups=not is_trans, transparent_pass=bool(is_trans), transmission_hook=refresh_hook, group_skip=_gskip)
                except Exception:
                    pass
                try:
                    if is_trans:
                        self._trans_draws = self._batcher.draw_calls if self._batcher else 0
                    else:
                        self._opaque_draws = self._batcher.draw_calls if self._batcher else 0
                except Exception:
                    pass
            else:
                for entry in phase_entries:
                    try:
                        self._scenev_render_fallback_entry(entry, is_trans, view_f32, proj_f32, cam_pos, lights, dynamic_cubemaps, sky_component, selected_entities, outline_queue, rw, rh)
                    except Exception:
                        pass
        try:
            self._materials._transmission_bg = None
        except Exception:
            pass
        try:
            if transparent_entries:
                self._ctx.depth_mask = True
                self._ctx.disable(moderngl.BLEND)
        except Exception:
            pass
        return outline_queue

    def _scenev_render_fallback_entry(self, entry, is_trans, view_f32, proj_f32, cam_pos, lights, dynamic_cubemaps, sky_component, selected_entities, outline_queue, rw, rh):
        ent, tr, mesh, mr = entry[:4]
        wm = entry[4]
        try:
            if is_trans and mr is not None:
                try:
                    mp0 = mr.get_material_path(0)
                except Exception:
                    mp0 = ""
                try:
                    mm0 = self._materials.load_material(mp0)
                    pp0 = mm0.properties if mm0 is not None else {}
                    tt0 = float(pp0.get("_Transmission", pp0.get("transmission", 0.0)))
                except Exception:
                    tt0 = 0.0
                if tt0 > 0.001:
                    try:
                        self._recapture_transmission_bg(rw, rh)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            mat = self._materials.load_material(mr.get_material_path(0))
            shader_path = mat.shader_path if mat else ""
            prog = self._shaders.get_or_compile(shader_path if shader_path else "") or self._default_prog
            self._set_scene_uniforms(prog, view_f32, proj_f32, cam_pos, lights, disable_shadows=not mr.receive_shadows)
            names = self._uniform_names(prog)
            self._scenev_bind_scene_ibl(prog, mr, dynamic_cubemaps, sky_component)
            model_f32 = relativize_model_f32(wm, origin_for(cam_pos))
            if "u_model" in names:
                prog["u_model"].write(model_f32.tobytes())
            nm = resolve_normal_matrix(self._normal_cache, ent._id, wm._d)
            if "u_normal_matrix" in names:
                prog["u_normal_matrix"].write(nm.tobytes())
            self._materials.apply_material(mat, prog, mr)
            ds = self._mat_double_sided(mat)
            try:
                tp = bool(is_trans)
            except Exception:
                tp = False
            self._render_mesh_double_sided(prog, mesh, ds, two_pass=bool(tp and ds))
            if selected_entities and ent in selected_entities:
                outline_queue.append((mesh, wm))
        except Exception:
            try:
                prog = self._default_prog
                self._set_scene_uniforms(prog, view_f32, proj_f32, cam_pos, lights, disable_shadows=not mr.receive_shadows)
                names = self._uniform_names(prog)
                model_f32 = relativize_model_f32(wm, origin_for(cam_pos))
                if "u_model" in names:
                    prog["u_model"].write(model_f32.tobytes())
                if "u_normal_matrix" in names:
                    prog["u_normal_matrix"].write(np.eye(3, dtype=np.float32).tobytes())
                self._materials.apply_material(None, prog, mr)
                mesh.render(prog)
                if selected_entities and ent in selected_entities:
                    outline_queue.append((mesh, wm))
            except Exception:
                pass

    def _scenev_render_water(self, snap, water_components, view_mat, proj_mat, cam_pos, dir_light, rw, rh, cam_near, cam_far, shared_cache=None):
        if not water_components or not self._water_plane:
            return
        try:
            try:
                eng0 = Engine.instance()
                prof0 = eng0._profiler if eng0 and hasattr(eng0, "_profiler") else None
            except Exception:
                prof0 = None
            if prof0:
                prof0.start("render_water")
            self._ensure_water_fbo(rw, rh)
            self._ctx.copy_framebuffer(self._water_fbo, self._scene_fbo)
            self._water_fbo.use()
            self._water_fbo.viewport = (0, 0, rw, rh)
            self._ctx.viewport = (0, 0, rw, rh)
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.enable(moderngl.CULL_FACE)
            self._ctx.cull_face = "back"
            self._last_interactors = snap.interactors
            now_t = time.time()
            sim_dt = max(0.001, min(now_t - getattr(self, "_last_water_sim_time", now_t - 0.016), 0.05))
            self._last_water_sim_time = now_t
            for water_component in water_components:
                tr = water_component.transform
                water_y = tr.position.y if tr else 0.0
                if water_component.infinite_ocean and water_component.surface_type == "Ocean":
                    chunk_models = self._compute_water_chunk_models(cam_pos, water_y, water_component.ocean_size)
                    res = int(getattr(water_component, "mesh_resolution", 32.0))
                    mesh = self._get_water_plane_mesh(max(2, res))
                    grid_center = cam_pos
                    grid_size = float(getattr(water_component, "ocean_size", 2000.0))
                    if shared_cache is not None and id(water_component) in shared_cache.get("_water_sims", {}):
                        sim_tex = shared_cache["_water_sims"][id(water_component)]
                    else:
                        sim_tex = self._step_water_sim(water_component, grid_center, grid_size, water_y, sim_dt)
                        if shared_cache is not None:
                            shared_cache.setdefault("_water_sims", {})[id(water_component)] = sim_tex
                    water_component.render_water(self._ctx, self._shaders, view_mat, proj_mat, dir_light, cam_pos, mesh, self._scene_color_tex, self._scene_depth_tex, (rw, rh), cam_near, cam_far, snap.wind_zones, snap.lights, chunk_models, sim_tex=sim_tex, sim_grid_center=grid_center, sim_grid_size=grid_size, sim_disp_scale=getattr(water_component, "sim_disp_scale", 1.0), sim_normal_scale=getattr(water_component, "sim_normal_scale", 1.0))
                elif water_component.surface_type == "Pond":
                    res = int(getattr(water_component, "mesh_resolution", 128.0))
                    mesh = self._get_water_box_mesh(res)
                    grid_center = tr.position if tr else cam_pos
                    grid_size = float(getattr(water_component, "pond_size", 20.0))
                    if shared_cache is not None and id(water_component) in shared_cache.get("_water_sims", {}):
                        sim_tex = shared_cache["_water_sims"][id(water_component)]
                    else:
                        sim_tex = self._step_water_sim(water_component, grid_center, grid_size, water_y, sim_dt)
                        if shared_cache is not None:
                            shared_cache.setdefault("_water_sims", {})[id(water_component)] = sim_tex
                    water_component.render_water(self._ctx, self._shaders, view_mat, proj_mat, dir_light, cam_pos, mesh, self._scene_color_tex, self._scene_depth_tex, (rw, rh), cam_near, cam_far, snap.wind_zones, snap.lights, None, is_box=True, sim_tex=sim_tex, sim_grid_center=grid_center, sim_grid_size=grid_size, sim_disp_scale=getattr(water_component, "sim_disp_scale", 1.0), sim_normal_scale=getattr(water_component, "sim_normal_scale", 1.0))
                else:
                    res = int(getattr(water_component, "mesh_resolution", 200.0))
                    mesh = self._get_water_plane_mesh(res)
                    grid_center = tr.position if tr else cam_pos
                    grid_size = float(getattr(water_component, "pond_size", 200.0))
                    if shared_cache is not None and id(water_component) in shared_cache.get("_water_sims", {}):
                        sim_tex = shared_cache["_water_sims"][id(water_component)]
                    else:
                        sim_tex = self._step_water_sim(water_component, grid_center, grid_size, water_y, sim_dt)
                        if shared_cache is not None:
                            shared_cache.setdefault("_water_sims", {})[id(water_component)] = sim_tex
                    water_component.render_water(self._ctx, self._shaders, view_mat, proj_mat, dir_light, cam_pos, mesh, self._scene_color_tex, self._scene_depth_tex, (rw, rh), cam_near, cam_far, snap.wind_zones, snap.lights, None, sim_tex=sim_tex, sim_grid_center=grid_center, sim_grid_size=grid_size, sim_disp_scale=getattr(water_component, "sim_disp_scale", 1.0), sim_normal_scale=getattr(water_component, "sim_normal_scale", 1.0))
            self._scene_fbo.use()
            self._scene_fbo.viewport = (0, 0, rw, rh)
            self._ctx.viewport = (0, 0, rw, rh)
            self._ctx.disable(moderngl.DEPTH_TEST)
            self._pp_copy_prog["u_input_tex"] = 0
            self._water_color_tex.use(0)
            self._pp_copy_vao.render()
            self._ctx.enable(moderngl.DEPTH_TEST)
            if prof0:
                prof0.stop("render_water")
        except Exception:
            try:
                self._scene_fbo.use()
                self._ctx.enable(moderngl.DEPTH_TEST)
            except Exception:
                pass

    def _scenev_render_water_volumes(self, snap, water_components, view_mat, proj_mat, view_f32, proj_f32, cam_pos, dir_light, rw, rh, cam_near, cam_far):
        try:
            eng = Engine.instance()
            prof = eng._profiler if eng and hasattr(eng, "_profiler") else None
        except Exception:
            prof = None
        caustic_water = None
        caustic_best_y = float("-inf")
        for wc in water_components:
            if getattr(wc, "caustics", 0.0) <= 0.0:
                continue
            tr = wc.transform
            sy = tr.position.y if tr else 0.0
            if sy > caustic_best_y:
                caustic_best_y = sy
                caustic_water = wc
        if caustic_water is not None and self._scene_depth_tex is not None:
            try:
                if prof:
                    prof.start("render_caustics")
                csun_dir = Vec3(0.0, 1.0, 0.0)
                csun_color = [1.0, 1.0, 1.0]
                csun_intensity = 1.0
                if dir_light:
                    dl, dt = dir_light
                    csun_dir = -dt.forward
                    csun_color, csun_intensity = Light.shader_radiance(dl, dt)
                c_tint = getattr(caustic_water, "sss_color", [0.0, 0.55, 0.45])
                c_strength = float(getattr(caustic_water, "caustics", 0.0))
                try:
                    c_inv_vp = (view_mat @ proj_mat).inverted().to_f32()
                except Exception:
                    c_inv_vp = None
                self._render_caustics_pass(rw, rh, view_f32, proj_f32, cam_pos, csun_dir, csun_color, csun_intensity, c_tint, c_strength, caustic_best_y, caustic_water, c_inv_vp, cam_near, cam_far)
                if prof:
                    prof.stop("render_caustics")
            except Exception:
                pass
        underwater_water = None
        best_depth = float("inf")
        for wc in water_components:
            tr = wc.transform
            surface_y = tr.position.y if tr else 0.0
            if cam_pos.y < surface_y:
                depth_below = surface_y - cam_pos.y
                if depth_below < best_depth:
                    best_depth = depth_below
                    underwater_water = wc
        if underwater_water is not None and self._scene_depth_tex is not None:
            try:
                if prof:
                    prof.start("render_underwater")
                sun_dir = Vec3(0.0, 1.0, 0.0)
                sun_color = [1.0, 1.0, 1.0]
                sun_intensity = 1.0
                if dir_light:
                    dl, dt = dir_light
                    sun_dir = -dt.forward
                    sun_color, sun_intensity = Light.shader_radiance(dl, dt)
                fog_color = getattr(underwater_water, "deep_color", [0.02, 0.18, 0.28])
                caustic_color = getattr(underwater_water, "sss_color", [0.0, 0.55, 0.45])
                try:
                    inv_vp_f32 = (view_mat @ proj_mat).inverted().to_f32()
                except Exception:
                    inv_vp_f32 = None
                self._render_underwater_pass(rw, rh, view_f32, proj_f32, cam_pos, sun_dir, sun_color, sun_intensity, fog_color, caustic_color, best_depth, cam_near, cam_far, water_component=underwater_water, inv_view_proj_f32=inv_vp_f32)
                if prof:
                    prof.stop("render_underwater")
            except Exception:
                pass

    def _scenev_render_clouds(self, snap, cloud_components, view_mat, proj_mat, dir_light, cam_pos, rw, rh):
        try:
            eng = Engine.instance()
            prof = eng._profiler if eng and hasattr(eng, "_profiler") else None
        except Exception:
            prof = None
        if cloud_components and self._cloud_plane and self._skybox_enabled:
            try:
                if prof:
                    prof.start("render_cloud_layer")
                for cloud_component in cloud_components:
                    cloud_component.render_cloud_layer(self._ctx, self._shaders, view_mat, proj_mat, dir_light, cam_pos, self._cloud_plane)
                if prof:
                    prof.stop("render_cloud_layer")
            except Exception:
                pass
        if cloud_components and self._cloud_quad and self._skybox_enabled:
            try:
                if prof:
                    prof.start("render_clouds")
                self._ensure_pp_fbo(rw, rh)
                self._ctx.copy_framebuffer(self._pp_fbo_a, self._scene_fbo)
                self._pp_fbo_a.use()
                self._pp_fbo_a.viewport = (0, 0, rw, rh)
                self._ctx.viewport = (0, 0, rw, rh)
                self._ctx.disable(moderngl.DEPTH_TEST)
                for cloud_component in cloud_components:
                    cloud_component.render_clouds(self._ctx, self._shaders, view_mat, proj_mat, dir_light, cam_pos, self._cloud_quad, self._shadows, self._scene_depth_tex, (rw, rh))
                self._scene_fbo.use()
                self._scene_fbo.viewport = (0, 0, rw, rh)
                self._ctx.viewport = (0, 0, rw, rh)
                self._ctx.disable(moderngl.DEPTH_TEST)
                self._pp_copy_prog["u_input_tex"] = 0
                self._pp_color_tex_a.use(0)
                self._pp_copy_vao.render()
                self._ctx.enable(moderngl.DEPTH_TEST)
                if prof:
                    prof.stop("render_clouds")
            except Exception:
                pass
