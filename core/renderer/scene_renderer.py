# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Main scene rendering orchestration."""

from __future__ import annotations
import time
import traceback
import numpy as np
import moderngl
from typing import Optional, Any, Callable
from core.components.lighting import Light, Projector
from core.engine.engine import Engine
from core.foundation.logger import Logger
from core.components.rendering.particles.particle_force_field import ParticleForceField, FORCE_FIELD_DTYPE, MAX_FORCE_FIELDS
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.maths.math3d import Mat4, Vec3
from core.renderer.types import RenderMode
from core.renderer.mesh_data import MeshData, read_shader
from core.renderer.batcher import RenderBatcher, resolve_normal_matrix
from core.renderer.culling import cpu_frustum_cull
from core.renderer.render_items import _TAAU_JITTER
from core.renderer.render_snapshot import _RenderSnapshot


class SceneRendererMixin:
    """Main scene rendering orchestration."""


    def render_scene(self, scene, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3,
                     viewport_w: int, viewport_h: int, fbo=None,
                     selected_entities: Optional[set] = None,
                     cam_near: float = 0.01, cam_far: float = 1000.0, cam_fov: float = 60.0,
                      display_w: int = None, display_h: int = None,
                      shared_cache: dict = None):
        if not self._initialized:
            return
        _scale = self._render_scale
        rw = max(1, int(round(viewport_w * _scale)))
        rh = max(1, int(round(viewport_h * _scale)))
        _render_t0 = time.perf_counter()
        eng = Engine.instance()
        prof = eng._profiler if eng and hasattr(eng, '_profiler') else None
        if self._gizmo:
            self._gizmo._stat_lines = 0
            self._gizmo._stat_instances = 0
            self._gizmo._stat_mesh_verts = 0
            self._gizmo._stat_draws = 0
            self._gizmo._stat_upload_bytes = 0
            self._gizmo._stat_upload_full = 0
            self._gizmo._stat_upload_partial = 0
        if prof:
            prof.start("render_scene")
        if shared_cache is not None and 'snap' in shared_cache:
            snap = shared_cache['snap']
        else:
            snap = getattr(self, '_snap_cache_reuse', None)
            if snap is None:
                snap = _RenderSnapshot()
            if scene:
                if eng._scene_lock.acquire(blocking=False):
                    try:
                        snap = self._collect_snapshot(scene, cam_near, cam_far, cam_fov, view_mat, proj_mat, cam_pos)
                        self._snap_cache_reuse = snap
                    finally:
                        eng._scene_lock.release()
                elif self._snap_cache_reuse is not None:
                    snap = self._snap_cache_reuse
                else:
                    snap = _RenderSnapshot()
            if shared_cache is not None:
                shared_cache['snap'] = snap
        lights = snap.lights
        dir_light = snap.dir_light
        sky_component = snap.sky_component
        sky_entity = snap.sky_entity
        cloud_components = snap.cloud_components
        water_components = snap.water_components
        dynamic_cubemaps = snap.dynamic_cubemaps
        renderable = snap.renderable
        try:
            self._refresh_soft_snapshot_meshes(scene, snap)
            renderable = snap.renderable
        except Exception:
            pass
        if prof:
            prof.start("gl_state_setup")
        if fbo is not None:
            fbo.use()
            fbo.viewport = (0, 0, viewport_w, viewport_h)
        self._ctx.viewport = (0, 0, rw, rh)
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._ctx.enable(moderngl.CULL_FACE)
        self._ctx.cull_face = 'back'
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        if self._render_mode == RenderMode.SHADED:
            prog = self._default_prog
            fill_mode = moderngl.TRIANGLES
            use_polygon_mode = False
        elif self._render_mode == RenderMode.SHADED_WIREFRAME:
            prog = self._default_prog
            fill_mode = moderngl.TRIANGLES
            use_polygon_mode = True
        else:
            prog = self._default_prog
            fill_mode = moderngl.TRIANGLES
            use_polygon_mode = False
        unjit_proj = proj_mat
        jitter_active = (not self._effects_disabled) and (display_w and display_h) and any(
            getattr(e, '_is_upscaler', False) and e.enabled and e.entity and e.entity.active
            for e in GraphicsEffect._registry
        )
        if jitter_active:
            self._jitter_index = (getattr(self, '_jitter_index', 0) + 1) % len(_TAAU_JITTER)
            hx, hy = _TAAU_JITTER[self._jitter_index]
            jx = hx * 2.0 / max(1, viewport_w)
            jy = hy * 2.0 / max(1, viewport_h)
            jd = proj_mat._d.copy()
            jd[:, 0] += jx * jd[:, 3]
            jd[:, 1] += jy * jd[:, 3]
            proj_mat = Mat4(jd)
        view_f32 = view_mat.to_f32()
        proj_f32 = proj_mat.to_f32()
        if prof:
            prof.stop("gl_state_setup")
        self._ensure_scene_fbo(rw, rh)
        self._ctx.disable(moderngl.BLEND)
        self._scene_fbo.use()
        self._scene_fbo.clear(0.0, 0.0, 0.0, 1.0, 1.0)
        aspect = rw / max(1, rh)
        if prof:
            prof.start("mesh_async_load")
        self._mesh_loader.process_pending()
        if self._gaussians is not None:
            self._gaussians.process_pending()
        if prof:
            prof.stop("mesh_async_load")
        self._skinning_cache.clear()
        if shared_cache is not None:
            shared_cache['skinning'] = self._skinning_cache
        if prof:
            prof.start("render_shadow_pass")
        shadow_groups = {}
        self._apply_shadow_system_state(update=True)
        if not self._shadow_enabled:
            try:
                self._shadows.reset_shadow_state()
            except Exception:
                pass
        elif shared_cache is not None and 'shadow_groups' in shared_cache:
            shadow_groups = shared_cache['shadow_groups']
        else:
            needs_shadow = (bool(snap.shadow_renderables) or bool(snap.skinned_shadow_renderables)
                            or any(getattr(l, "cast_shadows", False) for l, _ in snap.lights))
            if needs_shadow:
                try:
                    shadow_groups = self._shadows.render_shadow_pass(snap.shadow_renderables, snap.lights, cam_near, cam_far, cam_fov, aspect, view_mat, {}, skinned_entries=snap.skinned_shadow_renderables, scene=scene, skinning_cache=self._skinning_cache)
                    if snap.projectors:
                        self._shadows.render_projector_shadows(snap.projectors, snap.shadow_renderables, shadow_groups)
                except Exception as _sh_err:
                    import traceback as _tb
                    _tb.print_exc()
            else:
                self._shadows.reset_shadow_state()
            if shared_cache is not None:
                shared_cache['shadow_groups'] = shadow_groups
        if prof:
            prof.stop("render_shadow_pass")
        self._scene_fbo.use()
        self._ctx.viewport = (0, 0, rw, rh)
        if sky_component and sky_component.enabled and self._skybox_cube and self._skybox_enabled:
            if prof:
                prof.start("render_skybox")
            sky_component.render_sky(self._ctx, self._shaders, view_mat, proj_mat, dir_light, self._skybox_cube)
            if prof:
                prof.stop("render_skybox")
        if dynamic_cubemaps is not None and not self._rendering_cubemap_face:
            if not (shared_cache is not None and shared_cache.get('_cubemaps_done')):
                if prof:
                    prof.start("update_dynamic_cubemaps")
                probe_pos = snap.dynamic_cubemaps_pos if (snap.dynamic_cubemaps_pos is not None and not getattr(dynamic_cubemaps, 'follow_camera', True)) else cam_pos
                dynamic_cubemaps.update(self._ctx, view_mat, proj_mat, probe_pos, scene, self,
                                        main_snap=snap, skip_entity=snap.dynamic_cubemaps_entity)
                self._scene_fbo.use()
                if prof:
                    prof.stop("update_dynamic_cubemaps")
                if shared_cache is not None:
                    shared_cache['_cubemaps_done'] = True
        self._ctx.viewport = (0, 0, rw, rh)
        if use_polygon_mode:
            self._ctx.wireframe = True
        if prof:
            prof.start("process_pending_textures")
        self._materials.process_texture_pending()
        if prof:
            prof.stop("process_pending_textures")


        self._culled_total = len(renderable) if renderable else 0
        self._culled_visible = self._culled_total
        if renderable:
            try:
                from core._render_utils import build_frustum_cull_inputs as _bfci
                from itertools import chain as _chain
                vp = proj_mat._d.T @ view_mat._d.T
                cull_entries = snap.cull_entries
                n_ent = len(cull_entries)
                if n_ent:
                    _cc = getattr(self, "_cull_cache", None)
                    try:
                        _tvg = scene._transform_version
                    except Exception:
                        _tvg = -1
                    try:
                        _mg = self._mesh_loader._loaded_generation if self._mesh_loader else 0
                    except Exception:
                        _mg = 0
                    _ck = (id(snap), _tvg, _mg, n_ent)
                    if _cc is not None and _cc[0] == _ck:
                        centers, radii = _cc[1], _cc[2]
                    else:
                        centers, radii = _bfci(cull_entries)
                        self._cull_cache = (_ck, centers, radii)
                    visible = cpu_frustum_cull(centers, radii, vp)
                    offsets = snap.cull_offsets
                    counts = snap.cull_counts
                    n_vis = len(visible)
                    if n_vis == n_ent:
                        self._culled_visible = self._culled_total
                    else:
                        self._culled_visible = sum(counts[i] for i in visible) if n_vis else 0
                    if n_vis < n_ent:
                        if n_vis == 0:
                            renderable = []
                        elif n_vis == 1:
                            i = int(visible[0])
                            renderable = renderable[offsets[i]:offsets[i] + counts[i]]
                        else:
                            parts = [renderable[offsets[i]:offsets[i] + counts[i]] for i in visible]
                            renderable = list(_chain.from_iterable(parts))
                else:
                    n = len(renderable)
                    centers, radii = _bfci(renderable)
                    visible = cpu_frustum_cull(centers, radii, vp)
                    self._culled_visible = len(visible)
                    if len(visible) < n:
                        renderable = [renderable[idx] for idx in visible]
            except Exception:
                import traceback; traceback.print_exc()

        if prof:
            prof.start("render_meshes")
        outline_queue: list[tuple[MeshData, Mat4]] = []
        try:
            if selected_entities is not None and len(selected_entities) > 256:
                selected_entities = frozenset()
        except Exception:
            pass
        opaque_entries = None
        transparent_entries = []
        use_fast_groups = False
        fast_groups = getattr(self, "_fast_groups", None)
        if fast_groups is not None and renderable is snap.renderable and len(renderable) > 0:
            try:
                _fc = getattr(self, "_fast_count", 0) + 1
                self._fast_count = _fc
                if _fc < 600 and scene._render_version == getattr(self, "_fast_rv", None) and scene._transform_version == getattr(self, "_fast_tv", None) and len(renderable) == getattr(self, "_fast_len", -1) and id(snap) == getattr(self, "_fast_snap", -1) and getattr(self, "_triangles_drawn", 0) < 500000 and not getattr(self, "_fast_has_fx", True) and not getattr(self, "_fast_has_sprite", True) and not getattr(self, "_fast_trans", True):
                    _funiq = getattr(self, "_fast_uniq", None)
                    _fmats = getattr(self, "_fast_mats", None)
                    if _funiq is not None and _fmats is not None:
                        _ok = True
                        for _p in _funiq:
                            _m = self._materials.load_material(_p)
                            _sp = self._shaders.get_or_compile(_m.shader_path) if _m is not None and getattr(_m, "shader_path", "") else None
                            if _sp is None:
                                _sp = self._default_prog
                            _cid = _fmats.get(_p)
                            if _cid is None or _cid[0] != (id(_m) if _m is not None else 0) or _cid[1] != id(_sp):
                                _ok = False
                                break
                            if self._materials.mesh_transparency(None, _m):
                                _ok = False
                                break
                        if _ok:
                            use_fast_groups = True
            except Exception:
                use_fast_groups = False
        if use_fast_groups:
            groups = fast_groups
            if self._batcher:
                self._batcher.render_groups(
                    groups, view_f32, proj_f32, cam_pos, lights, False,
                    self._set_scene_uniforms, self._materials.apply_material,
                    self._normal_cache,
                    selected_entities or set(), outline_queue,
                    gpu_storage=self._gpu_storage,
                    dynamic_cubemaps=dynamic_cubemaps,
                    sky_ibl=getattr(sky_component, '_sky_ibl', None) if sky_component else None, skip_cull=True)
            opaque_entries = []
            transparent_entries = []
        else:
            opaque_entries, transparent_entries = self._partition_transparent(renderable)
            self._sort_transparent_far_first(transparent_entries, cam_pos)
            if len(opaque_entries) > 64 and getattr(self, "_triangles_drawn", 0) > 500000:
                self._sort_opaque_front_first(opaque_entries, cam_pos)
        for _is_trans_phase, _phase_entries in ((False, opaque_entries), (True, transparent_entries)):
            if not _phase_entries:
                continue
            if _is_trans_phase:
                self._scene_fbo.use()
                self._ctx.viewport = (0, 0, rw, rh)
                self._ctx.enable(moderngl.BLEND)
                self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                self._ctx.depth_mask = False
            fx_renderable = [e for e in _phase_entries if len(e) > 6 and e[6]]
            if fx_renderable:
                self._render_object_effects(fx_renderable, view_f32, proj_f32, cam_pos, lights, selected_entities, outline_queue)
                _phase_entries = [e for e in _phase_entries if not (len(e) > 6 and e[6])]
            if self._batcher:
                groups = self._batcher.collect_groups(
                    _phase_entries, self._materials, self._shaders)
                try:
                    _all_vis = self._culled_visible == self._culled_total
                except Exception:
                    _all_vis = False
                self._batcher.render_groups(
                    groups, view_f32, proj_f32, cam_pos, lights, False,
                    self._set_scene_uniforms, self._materials.apply_material,
                    self._normal_cache,
                    selected_entities or set(), outline_queue,
                    gpu_storage=self._gpu_storage,
                    dynamic_cubemaps=dynamic_cubemaps,
                    sky_ibl=getattr(sky_component, '_sky_ibl', None) if sky_component else None, skip_cull=_all_vis)
                try:
                    if not _is_trans_phase and not transparent_entries and renderable is snap.renderable and not fx_renderable:
                        _lu = getattr(self, "_last_uniq", None)
                        _lt = getattr(self, "_last_trans", None)
                        _lhs = getattr(self, "_last_has_sprite", True)
                        if _lu is not None and _lt is not None and not _lhs and len(_lt) == 0:
                            _fm = {}
                            for _pp in _lu:
                                _mm = self._materials.load_material(_pp)
                                _psp = self._shaders.get_or_compile(_mm.shader_path) if _mm is not None and getattr(_mm, "shader_path", "") else None
                                if _psp is None:
                                    _psp = self._default_prog
                                _fm[_pp] = ((id(_mm) if _mm is not None else 0), id(_psp))
                            self._fast_groups = groups
                            self._fast_rv = scene._render_version
                            self._fast_tv = scene._transform_version
                            self._fast_len = len(renderable)
                            self._fast_snap = id(snap)
                            self._fast_uniq = _lu
                            self._fast_trans = _lt
                            self._fast_mats = _fm
                            self._fast_has_sprite = False
                            self._fast_has_fx = False
                            self._fast_count = 0
                except Exception:
                    pass
            else:
                for entry in _phase_entries:
                    ent, tr, mesh, mr = entry[:4]
                    wm = entry[4]
                    try:
                        mat = self._materials.load_material(mr.get_material_path(0))
                        shader_path = mat.shader_path if mat else ""
                        prog = self._shaders.get_or_compile(shader_path if shader_path else "") or self._default_prog
                        self._set_scene_uniforms(prog, view_f32, proj_f32, cam_pos, lights, disable_shadows=not mr.receive_shadows)
                        names = self._uniform_names(prog)
                        if getattr(mr, 'dynamic_reflections', False) and dynamic_cubemaps is not None:
                            dynamic_cubemaps.bind_ibl(prog)
                        elif getattr(sky_component, '_sky_ibl', None) is not None and sky_component._sky_ibl.ready:
                            sky_component._sky_ibl.bind(prog)
                        elif not getattr(mr, 'dynamic_reflections', False):
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
                        model = wm
                        model_f32 = model.to_f32()
                        if "u_model" in names:
                            prog["u_model"].write(model_f32.tobytes())
                        nm = resolve_normal_matrix(self._normal_cache, ent._id, model._d)
                        if "u_normal_matrix" in names:
                            prog["u_normal_matrix"].write(nm.tobytes())
                        self._materials.apply_material(mat, prog, mr)
                        ds = self._mat_double_sided(mat)
                        self._render_mesh_double_sided(prog, mesh, ds)
                        if selected_entities and ent in selected_entities:
                            outline_queue.append((mesh, wm))
                    except Exception:
                        prog = self._default_prog
                        self._set_scene_uniforms(prog, view_f32, proj_f32, cam_pos, lights, disable_shadows=not mr.receive_shadows)
                        names = self._uniform_names(prog)
                        model = wm
                        model_f32 = model.to_f32()
                        if "u_model" in names:
                            prog["u_model"].write(model_f32.tobytes())
                        if "u_normal_matrix" in names:
                            prog["u_normal_matrix"].write(np.eye(3, dtype=np.float32).tobytes())
                        self._materials.apply_material(None, prog, mr)
                        mesh.render(prog)
                        if selected_entities and ent in selected_entities:
                            outline_queue.append((mesh, wm))
        if transparent_entries:
            self._ctx.depth_mask = True
            self._ctx.disable(moderngl.BLEND)
        if prof:
            prof.stop("render_meshes")
        if use_polygon_mode:
            self._ctx.wireframe = False
        if snap.skinned_renderables:
            if prof:
                prof.start("render_skinned")
            self._render_skinned_meshes(snap, view_f32, proj_f32, cam_pos, lights)
            if prof:
                prof.stop("render_skinned")
        if snap.projectors:
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
                suf = f"u_pj_{i}_"
                proj[f"{suf}vp"].write(px.vp_matrix.tobytes())
                proj[f"{suf}pos"].value = tuple(float(v) for v in px.position)
                proj[f"{suf}dir"].value = tuple(float(v) for v in px.direction)
                proj[f"{suf}color"].value = tuple(float(v) for v in px.color)
                proj[f"{suf}intensity"].value = float(px.intensity)
                proj[f"{suf}range"].value = float(px.range)
                proj[f"{suf}spot_angle"].value = float(px.spot_angle)
                tex_loaded = False
                if px.texture_path and self._materials:
                    tex = self._materials.load_texture(px.texture_path)
                    if tex:
                        tex_unit = 20 + i
                        tex.use(tex_unit)
                        proj[f"{suf}tex"].value = tex_unit
                        tex_loaded = True
                proj[f"{suf}has_tex"].value = 1.0 if tex_loaded else 0.0
                proj[f"{suf}flip_y"].value = 1.0 if px.flip_y else 0.0
                proj[f"{suf}flip_x"].value = 1.0 if px.flip_x else 0.0
            self._projector_vao.render()
            self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self._ctx.enable(moderngl.DEPTH_TEST)
        if prof:
            prof.start("render_text_world")
        if self._text and scene:
            with eng._scene_lock:
                self._text.render(scene, view_mat, proj_mat, rw, rh, world_space_only=True)
        if prof:
            prof.stop("render_text_world")
        if prof:
            prof.start("render_sprites")
        self._sprites.render_snapshot(snap.sprite_items, view_mat, proj_mat)
        if prof:
            prof.stop("render_sprites")
        if prof:
            prof.start("render_videos")
        self._videos.render_snapshot(snap.video_items, view_mat, proj_mat)
        if prof:
            prof.stop("render_videos")
        if self._grid and self._grid.show:
            if prof:
                prof.start("render_grid")
            if "u_scene_color" in self._grid_prog:
                self._grid_prog["u_scene_color"] = 12
                self._scene_color_tex.use(12)
            if "u_viewport_size" in self._grid_prog:
                self._grid_prog["u_viewport_size"].value = (float(viewport_w), float(viewport_h))
            self._grid.render(view_f32, proj_f32, cam_pos, self._clear_color, viewport_h, cam_fov)
            if prof:
                prof.stop("render_grid")
        if water_components and self._water_plane:
            if prof:
                prof.start("render_water")
            self._ensure_water_fbo(rw, rh)
            self._ctx.copy_framebuffer(self._water_fbo, self._scene_fbo)
            self._water_fbo.use()
            self._water_fbo.viewport = (0, 0, rw, rh)
            self._ctx.viewport = (0, 0, rw, rh)
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.enable(moderngl.CULL_FACE)
            self._ctx.cull_face = 'back'
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
                    if shared_cache is not None and id(water_component) in shared_cache.get('_water_sims', {}):
                        sim_tex = shared_cache['_water_sims'][id(water_component)]
                    else:
                        sim_tex = self._step_water_sim(water_component, grid_center, grid_size, water_y, sim_dt)
                        if shared_cache is not None:
                            shared_cache.setdefault('_water_sims', {})[id(water_component)] = sim_tex
                    water_component.render_water(self._ctx, self._shaders, view_mat, proj_mat,
                                                 dir_light, cam_pos, mesh,
                                                 self._scene_color_tex, self._scene_depth_tex,
                                                 (rw, rh), cam_near, cam_far,
                                                 snap.wind_zones, snap.lights, chunk_models,
                                                 sim_tex=sim_tex, sim_grid_center=grid_center,
                                                 sim_grid_size=grid_size,
                                                 sim_disp_scale=getattr(water_component, "sim_disp_scale", 1.0),
                                                 sim_normal_scale=getattr(water_component, "sim_normal_scale", 1.0))
                elif water_component.surface_type == "Pond":
                    res = int(getattr(water_component, "mesh_resolution", 128.0))
                    mesh = self._get_water_box_mesh(res)
                    grid_center = tr.position if tr else cam_pos
                    grid_size = float(getattr(water_component, "pond_size", 20.0))
                    if shared_cache is not None and id(water_component) in shared_cache.get('_water_sims', {}):
                        sim_tex = shared_cache['_water_sims'][id(water_component)]
                    else:
                        sim_tex = self._step_water_sim(water_component, grid_center, grid_size, water_y, sim_dt)
                        if shared_cache is not None:
                            shared_cache.setdefault('_water_sims', {})[id(water_component)] = sim_tex
                    water_component.render_water(self._ctx, self._shaders, view_mat, proj_mat,
                                                 dir_light, cam_pos, mesh,
                                                 self._scene_color_tex, self._scene_depth_tex,
                                                 (rw, rh), cam_near, cam_far,
                                                 snap.wind_zones, snap.lights, None, is_box=True,
                                                 sim_tex=sim_tex, sim_grid_center=grid_center,
                                                 sim_grid_size=grid_size,
                                                 sim_disp_scale=getattr(water_component, "sim_disp_scale", 1.0),
                                                 sim_normal_scale=getattr(water_component, "sim_normal_scale", 1.0))
                else:
                    res = int(getattr(water_component, "mesh_resolution", 200.0))
                    mesh = self._get_water_plane_mesh(res)
                    grid_center = tr.position if tr else cam_pos
                    grid_size = float(getattr(water_component, "pond_size", 200.0))
                    if shared_cache is not None and id(water_component) in shared_cache.get('_water_sims', {}):
                        sim_tex = shared_cache['_water_sims'][id(water_component)]
                    else:
                        sim_tex = self._step_water_sim(water_component, grid_center, grid_size, water_y, sim_dt)
                        if shared_cache is not None:
                            shared_cache.setdefault('_water_sims', {})[id(water_component)] = sim_tex
                    water_component.render_water(self._ctx, self._shaders, view_mat, proj_mat,
                                                 dir_light, cam_pos, mesh,
                                                 self._scene_color_tex, self._scene_depth_tex,
                                                 (rw, rh), cam_near, cam_far,
                                                 snap.wind_zones, snap.lights, None,
                                                 sim_tex=sim_tex, sim_grid_center=grid_center,
                                                 sim_grid_size=grid_size,
                                                 sim_disp_scale=getattr(water_component, "sim_disp_scale", 1.0),
                                                 sim_normal_scale=getattr(water_component, "sim_normal_scale", 1.0))
            self._scene_fbo.use()
            self._scene_fbo.viewport = (0, 0, rw, rh)
            self._ctx.viewport = (0, 0, rw, rh)
            self._ctx.disable(moderngl.DEPTH_TEST)
            self._pp_copy_prog["u_input_tex"] = 0
            self._water_color_tex.use(0)
            self._pp_copy_vao.render()
            self._ctx.enable(moderngl.DEPTH_TEST)
            if prof:
                prof.stop("render_water")





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
            c_surface_y = caustic_best_y
            try:
                c_inv_vp = (view_mat @ proj_mat).inverted().to_f32()
            except Exception:
                c_inv_vp = None
            self._render_caustics_pass(
                rw, rh, view_f32, proj_f32, cam_pos,
                csun_dir, csun_color, csun_intensity,
                c_tint, c_strength, c_surface_y,
                caustic_water, c_inv_vp, cam_near, cam_far
            )
            if prof:
                prof.stop("render_caustics")
        if cloud_components and self._cloud_plane and self._skybox_enabled:
            if prof:
                prof.start("render_cloud_layer")
            for cloud_component in cloud_components:
                cloud_component.render_cloud_layer(self._ctx, self._shaders, view_mat, proj_mat, dir_light, cam_pos, self._cloud_plane)
            if prof:
                prof.stop("render_cloud_layer")
        if cloud_components and self._cloud_quad and self._skybox_enabled:
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
            self._render_underwater_pass(
                rw, rh, view_f32, proj_f32, cam_pos,
                sun_dir, sun_color, sun_intensity, fog_color, caustic_color,
                best_depth, cam_near, cam_far,
                water_component=underwater_water, inv_view_proj_f32=inv_vp_f32
            )
            if prof:
                prof.stop("render_underwater")
        if self._gaussians and snap.gaussian_splats:
            if prof:
                prof.start("render_gaussians")
            self._scene_fbo.use()
            self._scene_fbo.viewport = (0, 0, rw, rh)
            self._ctx.viewport = (0, 0, rw, rh)
            self._ctx.enable(moderngl.DEPTH_TEST)
            for ent, gs in snap.gaussian_splats:
                tr = ent.transform
                if tr:
                    model = tr.world_matrix
                else:
                    model = Mat4.identity()
                try:
                    m, _ = self._gaussians.prepare(
                        self._gaussian_ply_path(gs, eng), model, view_mat, proj_mat,
                        cam_pos, viewport_w, viewport_h,
                        gs.opacity_threshold, gs.sh_degree,
                    )
                    if m > 0:
                        self._gaussians.draw_color(m)
                except Exception as e:
                    Logger.error(f"Gaussian Splat render error: {e}")
            self._ctx.disable(moderngl.BLEND)
            if prof:
                prof.stop("render_gaussians")
        if prof:
            prof.start("render_overlay")
        dw = display_w if display_w else viewport_w
        dh = display_h if display_h else viewport_h
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._present_composite(self._scene_color_tex, fbo, dw, dh)
        self._ctx.enable(moderngl.DEPTH_TEST)
        if prof:
            prof.stop("render_overlay")

        if scene:
            from core.components.rendering.renderers.raytracing_renderer import RaytracingRenderer
            for ent in scene.get_entities_with_component(RaytracingRenderer):
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
                self._rt_rays_per_frame = 0

        if scene:
            from core.components.rendering.environment.radiance_cascades_gi import RadianceCascadesGI
            for ent in scene.get_entities_with_component(RadianceCascadesGI):
                if not ent.active:
                    continue
                gi = ent.get_component(RadianceCascadesGI)
                if gi and gi.enabled:
                    if gi._dispatch(self._ctx, viewport_w, viewport_h, view_mat, proj_mat, cam_pos, scene, self):
                        gi._blit_to_fbo(self._ctx, self._scene_fbo, viewport_w, viewport_h)
                        gi.blit_to_screen(self._ctx, viewport_w, viewport_h)
                    break

        if prof:
            prof.start("render_stats")
        skybox_call = 1 if (self._skybox_enabled and self._skybox_cube) else 0
        if self._batcher:
            self._draw_calls = self._batcher.draw_calls + skybox_call
        else:
            self._draw_calls = len(renderable) + skybox_call
        self._triangles_drawn = 0
        self._vertices_drawn = 0
        counted_mesh_ids: set[int] = set()
        tri_cache = getattr(self, "_tri_cache", None)
        vert_cache = getattr(self, "_vert_cache", None)
        tri_gen = getattr(self, "_tri_cache_gen", -1)
        cur_gen = self._mesh_loader._loaded_generation if self._mesh_loader else 0
        if tri_cache is None or vert_cache is None or tri_gen != cur_gen:
            tri_cache = {}
            vert_cache = {}
            self._tri_cache = tri_cache
            self._vert_cache = vert_cache
            self._tri_cache_gen = cur_gen
        tri_get = tri_cache.get
        vert_get = vert_cache.get
        for entry in renderable:
            mesh = entry[2]
            sub_idx = entry[5]
            mkey = (id(mesh), sub_idx)
            tri = tri_get(mkey)
            if tri is None:
                ranges = mesh.sub_mesh_ranges
                if ranges and sub_idx >= 0 and sub_idx < len(ranges):
                    tri = ranges[sub_idx][1] // 3
                else:
                    idx = mesh.indices
                    tri = len(idx) // 3 if idx is not None and len(idx) > 0 else 0
                tri_cache[mkey] = tri
            self._triangles_drawn += tri
            mid = id(mesh)
            if mid not in counted_mesh_ids:
                counted_mesh_ids.add(mid)
                vert = vert_get(mid)
                if vert is None:
                    v = mesh.vertices
                    vert = len(v) // 3 if v is not None and len(v) > 0 else 0
                    vert_cache[mid] = vert
                self._vertices_drawn += vert
        if hasattr(snap, 'skinned_renderables'):
            for entry in snap.skinned_renderables:
                mesh = entry[2]
                sub_idx = entry[7] if len(entry) > 7 else -1
                ranges = getattr(mesh, 'sub_mesh_ranges', None)
                if ranges and sub_idx >= 0 and sub_idx < len(ranges):
                    _, count = ranges[sub_idx]
                    self._triangles_drawn += count // 3
                else:
                    if hasattr(mesh, 'indices') and mesh.indices is not None and len(mesh.indices) > 0:
                        self._triangles_drawn += len(mesh.indices) // 3
                mid = id(mesh)
                if mid not in counted_mesh_ids:
                    counted_mesh_ids.add(mid)
                    if hasattr(mesh, 'vertices') and mesh.vertices is not None and len(mesh.vertices) > 0:
                        self._vertices_drawn += len(mesh.vertices) // 3
        if prof:
            prof.stop("render_stats")
        _pv_key = id(fbo) if fbo is not None else 0
        prev_view_proj = self._prev_view_proj_by_target.get(_pv_key)
        self._prev_view_proj_by_target[_pv_key] = unjit_proj @ view_mat
        if GraphicsEffect._registry and not self._effects_disabled:
            if shared_cache is None or not shared_cache.get('_fx_done'):
                GraphicsEffect.increment_frame()
                if shared_cache is not None:
                    shared_cache['_fx_done'] = True
            if prof:
                prof.start("render_graphics_effects")
            self._ctx.disable(moderngl.DEPTH_TEST)

            has_velocity_effects = any(
                getattr(e, '_use_velocity', False) for e in GraphicsEffect._registry
                if e.enabled and e.entity and e.entity.active
            )
            velocity_tex = None
            if has_velocity_effects and renderable and prev_view_proj is not None and self._velocity_geom_prog:
                try:
                    self._ensure_velocity_fbo(rw, rh)
                    self._velocity_fbo.use()
                    self._velocity_fbo.viewport = (0, 0, rw, rh)
                    self._velocity_fbo.clear(red=0.0, green=0.0, depth=1.0)
                    self._ctx.enable(moderngl.DEPTH_TEST)
                    self._ctx.enable(moderngl.CULL_FACE)
                    self._ctx.cull_face = 'back'
                    cur_vp = unjit_proj @ view_mat
                    prog = self._velocity_geom_prog
                    prog["u_view_proj"].write(cur_vp.to_f32().tobytes())
                    prog["u_prev_view_proj"].write(prev_view_proj.to_f32().tobytes())
                    for entry in renderable:
                        ent = entry[0]
                        wm = entry[4]
                        mesh = entry[2]
                        prev_model = self._prev_model_by_entity.get(id(ent))
                        if prev_model is None:
                            continue
                        prog["u_model"].write(wm.to_f32().tobytes())
                        prog["u_prev_model"].write(prev_model.to_f32().tobytes())
                        mesh.render(prog)
                    for entry in renderable:
                        ent = entry[0]
                        wm = entry[4]
                        self._prev_model_by_entity[id(ent)] = wm
                    velocity_tex = self._velocity_tex
                    self._scene_fbo.use()
                    self._scene_fbo.viewport = (0, 0, rw, rh)
                    self._ctx.disable(moderngl.DEPTH_TEST)
                except Exception as e:
                    Logger.error(f"Velocity geometry pass error: {e}")
                    import traceback; traceback.print_exc()
                    velocity_tex = None

            additive_effects = []
            screen_effects = []
            for e in list(GraphicsEffect._registry):
                if not e.enabled or not e.entity or not e.entity.active:
                    continue
                if e.should_skip():
                    continue
                if getattr(e, 'render_type', 'additive') == 'screen':
                    screen_effects.append(e)
                else:
                    additive_effects.append(e)
            if additive_effects:
                self._scene_fbo.use()
                self._scene_fbo.viewport = (0, 0, rw, rh)
                self._ctx.viewport = (0, 0, rw, rh)
            for effect in additive_effects:
                try:
                    extra = {}
                    if getattr(effect, '_use_velocity', False):
                        extra['velocity_tex'] = velocity_tex
                        extra['prev_view_proj'] = prev_view_proj
                    effect.render(self._ctx, self._scene_color_tex, self._scene_depth_tex,
                                  view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
                                  **extra)
                except Exception as e:
                    Logger.error(f"GraphicsEffect.render error: {e}")
            disp_w = display_w if display_w else viewport_w
            disp_h = display_h if display_h else viewport_h
            composite_src = self._scene_color_tex
            if screen_effects:
                has_upscaler = any(getattr(e, '_is_upscaler', False) for e in screen_effects)
                pipe_w = disp_w if has_upscaler else viewport_w
                pipe_h = disp_h if has_upscaler else viewport_h
                self._ensure_se_fbo(pipe_w, pipe_h)
                self._ctx.disable(moderngl.BLEND)
                self._se_fbo_a.use()
                self._se_fbo_a.viewport = (0, 0, pipe_w, pipe_h)
                self._se_fbo_a.clear(0.0, 0.0, 0.0, 0.0, 1.0)
                self._se_fbo_b.use()
                self._se_fbo_b.viewport = (0, 0, pipe_w, pipe_h)
                self._se_fbo_b.clear(0.0, 0.0, 0.0, 0.0, 1.0)
                self._se_fbo_a.use()
                self._se_fbo_a.viewport = (0, 0, pipe_w, pipe_h)
                self._pp_copy_prog["u_input_tex"] = 0
                self._scene_color_tex.use(0)
                self._pp_copy_vao.render()
                src_fbo = self._se_fbo_a
                dst_fbo = self._se_fbo_b
                src_tex = self._se_color_tex_a
                for effect in screen_effects:
                    dst_fbo.use()
                    dst_fbo.viewport = (0, 0, pipe_w, pipe_h)
                    try:
                        if prof:
                            prof.start(f"effect_{effect.__class__.__name__}")
                        extra = {}
                        if getattr(effect, '_use_velocity', False):
                            extra['velocity_tex'] = velocity_tex
                            extra['prev_view_proj'] = prev_view_proj
                        effect.render(self._ctx, self._scene_color_tex, self._scene_depth_tex,
                                      view_mat, proj_mat, cam_pos, pipe_w, pipe_h,
                                      input_tex=src_tex, output_fbo=dst_fbo,
                                      render_w=viewport_w, render_h=viewport_h,
                                      **extra)
                        if prof:
                            time_elapsed = prof.stop(f"effect_{effect.__class__.__name__}")
                            if time_elapsed is not None and time_elapsed > 0.01:
                                Logger.warning(f"{effect.__class__.__name__} took {time_elapsed*1000:.1f}ms")
                    except Exception as e:
                        Logger.error(f"GraphicsEffect.render error: {e}")
                    src_fbo, dst_fbo = dst_fbo, src_fbo
                    src_tex = src_fbo.color_attachments[0]
                composite_src = src_tex
            self._ctx.disable(moderngl.BLEND)
            self._present_composite(composite_src, fbo, disp_w, disp_h)
            self._ctx.enable(moderngl.BLEND)
            self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            if prof:
                prof.stop("render_graphics_effects")

        if prof:
            prof.start("render_text")
        if self._text and scene:
            with eng._scene_lock:
                self._text.render(scene, view_mat, proj_mat, rw, rh, world_space_only=False)
        if prof:
            prof.stop("render_text")
        if prof:
            prof.start("render_svgs")
        self._svgs.render_snapshot(snap.svg_items, view_mat, proj_mat)
        if prof:
            prof.stop("render_svgs")
        if prof:
            prof.start("render_particles")
        if self._particles and snap.particle_systems:
            ff_list = snap.force_fields
            num_ff = min(len(ff_list), MAX_FORCE_FIELDS)
            if num_ff > 0:
                ff_data_arr = np.zeros(num_ff, dtype=FORCE_FIELD_DTYPE)
                for i in range(num_ff):
                    ff_data_arr[i] = ff_list[i].to_gpu_data()
                self._particles.upload_force_fields(ff_data_arr)
            frame = eng.frame_count if eng else 0
            if frame != self._particles._last_frame:
                now = time.perf_counter()
                self._particles._render_dt = min(now - self._particles._last_particle_time, 0.05)
                self._particles._last_particle_time = now
                self._particles._last_frame = frame
            self._particles.begin_frame(view_mat, proj_mat)
            for ps in snap.particle_systems:
                params = ps.get_compute_params(eng.fixed_dt if eng else 0.02, ps._last_delta_pos)
                params['num_force_fields'] = num_ff
                n = len(ps._particles) if ps._particles is not None else 0
                self._particles._ensure_buffers(n)
                self._particles.upload_all(ps._particles)
                self._particles.dispatch(params)
                self._particles.readback_all(ps._particles)
                dead = self._particles.read_dead_list()
                ps.replenish_free_list(dead)
                self._particles.render_single(ps)
            self._particles.end_frame()
            self._particle_count = sum(ps._alive_count for ps in snap.particle_systems)
        else:
            self._particle_count = 0
        if prof:
            prof.stop("render_particles")
        if outline_queue and self._outline_prog and len(outline_queue) <= 512:
            if prof:
                prof.start("render_outlines")
            old_depth_mask = self._ctx.depth_mask
            old_wireframe = self._ctx.wireframe
            self._ctx.depth_mask = False
            self._ctx.wireframe = True
            for mesh, model_mat in outline_queue:
                mvp = model_mat * view_mat * proj_mat
                if "u_mvp" in self._outline_prog:
                    self._outline_prog["u_mvp"].write(mvp.to_f32().tobytes())
                if "u_outline_color" in self._outline_prog:
                    self._outline_prog["u_outline_color"].write(np.array(self._selection_outline_color, dtype=np.float32).tobytes())
                mesh.render_outline()
            self._ctx.depth_mask = old_depth_mask
            self._ctx.wireframe = old_wireframe
            if prof:
                prof.stop("render_outlines")
        if prof:
            prof.stop("render_scene")
