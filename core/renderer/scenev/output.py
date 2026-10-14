# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
import numpy as np
import moderngl
from core.engine.eng import Engine
from core.foundation.logger import Logger
from core.maths.math3d import Mat4
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.components.rendering.particles.particle_force_field import FORCE_FIELD_DTYPE, MAX_FORCE_FIELDS


class ScenevOutputMixin:
    def _recapture_transmission_bg(self, w: int, h: int):
        try:
            self._ensure_transmission_fbo(w, h)
        except Exception:
            return
        try:
            self._ctx.copy_framebuffer(self._transmission_fbo, self._scene_fbo)
        except Exception:
            return
        try:
            self._transmission_tex.build_mipmaps()
        except Exception:
            pass
        try:
            self._materials._transmission_bg = (self._transmission_tex, w, h)
        except Exception:
            pass

    def _scenev_present_composite(self, snap, scene, renderable, transparent_entries, view_mat, proj_mat, cam_pos, rw, rh, viewport_w, viewport_h, display_w, display_h, fbo, outline_queue, unjit_proj, stats_groups=None):
        try:
            eng = Engine.instance()
            prof = eng._profiler if eng and hasattr(eng, "_profiler") else None
        except Exception:
            eng = None
            prof = None
        try:
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
                        m, _, indirect = self._gaussians.prepare(self._gaussian_ply_path(gs, eng), model, view_mat, proj_mat, cam_pos, viewport_w, viewport_h, gs.opacity_threshold, gs.sh_degree)
                        if indirect:
                            self._gaussians.draw_indirect(self._gaussian_ply_path(gs, eng))
                        elif m > 0:
                            self._gaussians.draw_color(m)
                    except Exception as e:
                        Logger.error("Gaussian Splat render error: " + str(e))
                self._ctx.disable(moderngl.BLEND)
                if prof:
                    prof.stop("render_gaussians")
        except Exception:
            pass
        try:
            if prof:
                prof.start("render_overlay")
            dw = display_w if display_w else viewport_w
            dh = display_h if display_h else viewport_h
            self._ctx.disable(moderngl.DEPTH_TEST)
            self._present_composite(self._scene_color_tex, fbo, dw, dh)
            self._ctx.enable(moderngl.DEPTH_TEST)
            if prof:
                prof.stop("render_overlay")
        except Exception:
            pass
        try:
            self._scenev_dispatch_raytracing(scene, view_mat, proj_mat, cam_pos, viewport_w, viewport_h)
        except Exception:
            pass
        try:
            self._scenev_dispatch_gi(scene, view_mat, proj_mat, cam_pos, viewport_w, viewport_h, 0.01, 1000.0)
        except Exception:
            pass
        try:
            self._scenev_update_stats(snap, renderable, transparent_entries, stats_groups, fbo)
        except Exception:
            pass
        try:
            self._scenev_render_effects(snap, scene, renderable, view_mat, proj_mat, cam_pos, rw, rh, viewport_w, viewport_h, display_w, display_h, fbo, unjit_proj, prof)
        except Exception:
            pass
        try:
            self._scenev_render_final_overlays(snap, scene, view_mat, proj_mat, rw, rh, outline_queue, prof)
        except Exception:
            pass

    def _scenev_update_stats(self, snap, renderable, transparent_entries, stats_groups, fbo):
        try:
            skybox_call = 1 if (self._skybox_enabled and self._skybox_cube) else 0
        except Exception:
            skybox_call = 0
        try:
            if self._batcher:
                self._draw_calls = self._opaque_draws + self._trans_draws + skybox_call
            else:
                self._draw_calls = len(renderable) + skybox_call
                try:
                    nt = len(transparent_entries) if transparent_entries else 0
                except Exception:
                    nt = 0
                self._trans_draws = nt
                self._opaque_draws = len(renderable) - nt
        except Exception:
            pass
        try:
            self._triangles_drawn = 0
            self._vertices_drawn = 0
            counted = set()
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
            if self._batcher is not None and stats_groups:
                for sg in stats_groups:
                    for gk, grp in sg.items():
                        if not grp:
                            continue
                        gm = grp[0][2]
                        gs = grp[0][7]
                        mk = (id(gm), gs)
                        tri = tri_get(mk)
                        if tri is None:
                            ranges = gm.sub_mesh_ranges
                            if ranges and gs >= 0 and gs < len(ranges):
                                tri = ranges[gs][1] // 3
                            else:
                                idx = gm.indices
                                tri = len(idx) // 3 if idx is not None and len(idx) > 0 else 0
                            tri_cache[mk] = tri
                        self._triangles_drawn += len(grp) * tri
                        mid = id(gm)
                        if mid not in counted:
                            counted.add(mid)
                            vert = vert_get(mid)
                            if vert is None:
                                vv = gm.vertices
                                vert = len(vv) // 3 if vv is not None and len(vv) > 0 else 0
                                vert_cache[mid] = vert
                            self._vertices_drawn += vert
            else:
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
                    if mid not in counted:
                        counted.add(mid)
                        vert = vert_get(mid)
                        if vert is None:
                            vv = mesh.vertices
                            vert = len(vv) // 3 if vv is not None and len(vv) > 0 else 0
                            vert_cache[mid] = vert
                        self._vertices_drawn += vert
            if hasattr(snap, "skinned_renderables"):
                for entry in snap.skinned_renderables:
                    mesh = entry[2]
                    sub_idx = entry[7] if len(entry) > 7 else -1
                    ranges = getattr(mesh, "sub_mesh_ranges", None)
                    if ranges and sub_idx >= 0 and sub_idx < len(ranges):
                        _, count = ranges[sub_idx]
                        self._triangles_drawn += count // 3
                    else:
                        if hasattr(mesh, "indices") and mesh.indices is not None and len(mesh.indices) > 0:
                            self._triangles_drawn += len(mesh.indices) // 3
                    mid = id(mesh)
                    if mid not in counted:
                        counted.add(mid)
                        if hasattr(mesh, "vertices") and mesh.vertices is not None and len(mesh.vertices) > 0:
                            self._vertices_drawn += len(mesh.vertices) // 3
        except Exception:
            pass

    def _scenev_render_effects(self, snap, scene, renderable, view_mat, proj_mat, cam_pos, rw, rh, viewport_w, viewport_h, display_w, display_h, fbo, unjit_proj, prof=None):
        try:
            key = id(fbo) if fbo is not None else 0
            prev_vp = self._prev_view_proj_by_target.get(key)
            self._prev_view_proj_by_target[key] = unjit_proj @ view_mat
        except Exception:
            prev_vp = None
        if not GraphicsEffect._registry or self._effects_disabled:
            return
        try:
            has_velocity = any(getattr(e, "_use_velocity", False) for e in GraphicsEffect._registry if e.enabled and e.entity and e.entity.active)
        except Exception:
            has_velocity = False
        velocity_tex = None
        if has_velocity and renderable and prev_vp is not None and self._velocity_geom_prog:
            try:
                self._ensure_velocity_fbo(rw, rh)
                self._velocity_fbo.use()
                self._velocity_fbo.viewport = (0, 0, rw, rh)
                self._velocity_fbo.clear(red=0.0, green=0.0, depth=1.0)
                self._ctx.enable(moderngl.DEPTH_TEST)
                self._ctx.enable(moderngl.CULL_FACE)
                self._ctx.cull_face = "back"
                cur_vp = unjit_proj @ view_mat
                prog = self._velocity_geom_prog
                prog["u_view_proj"].write(cur_vp.to_f32().tobytes())
                prog["u_prev_view_proj"].write(prev_vp.to_f32().tobytes())
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
                Logger.error("Velocity geometry pass error: " + str(e))
                import traceback
                traceback.print_exc()
                velocity_tex = None
        try:
            additive_effects = []
            screen_effects = []
            for e in list(GraphicsEffect._registry):
                if not e.enabled or not e.entity or not e.entity.active:
                    continue
                if e.should_skip():
                    continue
                if getattr(e, "render_type", "additive") == "screen":
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
                    if getattr(effect, "_use_velocity", False):
                        extra["velocity_tex"] = velocity_tex
                        extra["prev_view_proj"] = prev_vp
                    effect.render(self._ctx, self._scene_color_tex, self._scene_depth_tex, view_mat, proj_mat, cam_pos, viewport_w, viewport_h, **extra)
                except Exception as e:
                    Logger.error("GraphicsEffect.render error: " + str(e))
            disp_w = display_w if display_w else viewport_w
            disp_h = display_h if display_h else viewport_h
            composite_src = self._scene_color_tex
            if screen_effects:
                has_upscaler = any(getattr(e, "_is_upscaler", False) for e in screen_effects)
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
                            prof.start("effect_" + effect.__class__.__name__)
                        extra = {}
                        if getattr(effect, "_use_velocity", False):
                            extra["velocity_tex"] = velocity_tex
                            extra["prev_view_proj"] = prev_vp
                        effect.render(self._ctx, self._scene_color_tex, self._scene_depth_tex, view_mat, proj_mat, cam_pos, pipe_w, pipe_h, input_tex=src_tex, output_fbo=dst_fbo, render_w=viewport_w, render_h=viewport_h, **extra)
                        if prof:
                            elapsed = prof.stop("effect_" + effect.__class__.__name__)
                            if elapsed is not None and elapsed > 10.0:
                                Logger.warning(effect.__class__.__name__ + " took " + str(round(elapsed, 1)) + "ms")
                    except Exception as e:
                        Logger.error("GraphicsEffect.render error: " + str(e))
                    src_fbo, dst_fbo = dst_fbo, src_fbo
                    src_tex = src_fbo.color_attachments[0]
                composite_src = src_tex
            self._ctx.disable(moderngl.BLEND)
            self._present_composite(composite_src, fbo, disp_w, disp_h)
            self._ctx.enable(moderngl.BLEND)
            self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        except Exception:
            pass

    def _scenev_render_final_overlays(self, snap, scene, view_mat, proj_mat, rw, rh, outline_queue, prof=None):
        try:
            eng = Engine.instance()
        except Exception:
            eng = None
        try:
            if prof:
                prof.start("render_text")
            if self._text and scene and eng:
                with eng._scene_lock:
                    self._text.render(scene, view_mat, proj_mat, rw, rh, world_space_only=False)
            if prof:
                prof.stop("render_text")
        except Exception:
            pass
        try:
            if prof:
                prof.start("render_svgs")
            try:
                svg_key = (id(scene), scene._render_version, scene._transform_version) if scene is not None else None
            except Exception:
                svg_key = None
            self._svgs.render_snapshot(snap.svg_items, view_mat, proj_mat, svg_key)
            if prof:
                prof.stop("render_svgs")
        except Exception:
            pass
        try:
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
                    params["num_force_fields"] = num_ff
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
        except Exception:
            pass
        try:
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
        except Exception:
            pass
