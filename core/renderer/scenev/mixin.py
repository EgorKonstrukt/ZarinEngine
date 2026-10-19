# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
import moderngl
from typing import Optional, Any
from core.engine.eng import Engine
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.maths.math3d import Mat4, Vec3
from core.renderer.types import RenderMode
from core.renderer.render_items import _TAAU_JITTER
from core.renderer.render_snapshot import _RenderSnapshot
from core.renderer.scenev.collect import ScenevCollectMixin
from core.renderer.scenev.lights import ScenevLightsMixin
from core.renderer.scenev.forward import ScenevForwardMixin
from core.renderer.scenev.skinned import ScenevSkinnedMixin
from core.renderer.scenev.output import ScenevOutputMixin


class SceneRendererMixin(ScenevCollectMixin, ScenevLightsMixin, ScenevForwardMixin, ScenevSkinnedMixin, ScenevOutputMixin):
    def render_scene(self, scene, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3, viewport_w: int, viewport_h: int, fbo=None, selected_entities: Optional[set] = None, cam_near: float = 0.01, cam_far: float = 1000.0, cam_fov: float = 60.0, display_w: int = None, display_h: int = None, shared_cache: dict = None):
        if not self._initialized:
            return
        scale = self._render_scale
        rw = max(1, int(round(viewport_w * scale)))
        rh = max(1, int(round(viewport_h * scale)))
        eng = Engine.instance()
        prof = eng._profiler if eng and hasattr(eng, "_profiler") else None
        if prof:
            prof.start("render_scene")
        try:
            if self._gizmo:
                self._gizmo._stat_lines = 0
                self._gizmo._stat_instances = 0
                self._gizmo._stat_mesh_verts = 0
                self._gizmo._stat_draws = 0
                self._gizmo._stat_upload_bytes = 0
                self._gizmo._stat_upload_full = 0
                self._gizmo._stat_upload_partial = 0
        except Exception:
            pass
        if shared_cache is not None and "snap" in shared_cache:
            snap = shared_cache["snap"]
        else:
            snap = getattr(self, "_snap_cache_reuse", None)
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
                shared_cache["snap"] = snap
        lights = snap.lights
        dir_light = snap.dir_light
        sky_component = snap.sky_component
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
        self._ctx.cull_face = "back"
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        if self._render_mode == RenderMode.SHADED:
            use_polygon_mode = False
        elif self._render_mode == RenderMode.SHADED_WIREFRAME:
            use_polygon_mode = True
        else:
            use_polygon_mode = False
        unjit_proj = proj_mat
        try:
            jitter_active = (not self._effects_disabled) and (display_w and display_h) and any(getattr(e, "_is_upscaler", False) and e.enabled and e.entity and e.entity.active for e in GraphicsEffect._registry)
        except Exception:
            jitter_active = False
        if jitter_active:
            try:
                self._jitter_index = (getattr(self, "_jitter_index", 0) + 1) % len(_TAAU_JITTER)
                hx, hy = _TAAU_JITTER[self._jitter_index]
                jx = hx * 2.0 / max(1, viewport_w)
                jy = hy * 2.0 / max(1, viewport_h)
                jd = proj_mat._d.copy()
                jd[:, 0] += jx * jd[:, 3]
                jd[:, 1] += jy * jd[:, 3]
                proj_mat = Mat4(jd)
            except Exception:
                pass
        view_f32 = view_mat.to_f32()
        proj_f32 = proj_mat.to_f32()
        if prof:
            prof.stop("gl_state_setup")
        try:
            self._ensure_scene_fbo(rw, rh)
        except Exception:
            pass
        try:
            self._ctx.disable(moderngl.BLEND)
            self._scene_fbo.use()
            self._scene_fbo.clear(0.0, 0.0, 0.0, 1.0, 1.0)
        except Exception:
            pass
        aspect = rw / max(1, rh)
        try:
            if prof:
                prof.start("mesh_async_load")
            self._mesh_loader.process_pending()
            if self._gaussians is not None:
                self._gaussians.process_pending()
            if prof:
                prof.stop("mesh_async_load")
        except Exception:
            pass
        try:
            self._skinning_cache.clear()
            if shared_cache is not None:
                shared_cache["skinning"] = self._skinning_cache
        except Exception:
            pass
        if prof:
            prof.start("render_shadow_pass")
        try:
            shadow_groups = self._scenev_render_shadow_pass(snap, scene, view_mat, cam_near, cam_far, cam_fov, aspect, shared_cache)
        except Exception:
            shadow_groups = {}
        if prof:
            prof.stop("render_shadow_pass")
        try:
            self._scene_fbo.use()
            self._ctx.viewport = (0, 0, rw, rh)
        except Exception:
            pass
        try:
            if sky_component and sky_component.enabled and self._skybox_cube and self._skybox_enabled:
                if prof:
                    prof.start("render_skybox")
                sky_component.render_sky(self._ctx, self._shaders, view_mat, proj_mat, dir_light, self._skybox_cube)
                if prof:
                    prof.stop("render_skybox")
        except Exception:
            pass
        try:
            if dynamic_cubemaps is not None and not self._rendering_cubemap_face:
                if not (shared_cache is not None and shared_cache.get("_cubemaps_done")):
                    if prof:
                        prof.start("update_dynamic_cubemaps")
                    probe_pos = snap.dynamic_cubemaps_pos if (snap.dynamic_cubemaps_pos is not None and not getattr(dynamic_cubemaps, "follow_camera", True)) else cam_pos
                    dynamic_cubemaps.update(self._ctx, view_mat, proj_mat, probe_pos, scene, self, main_snap=snap, skip_entity=snap.dynamic_cubemaps_entity)
                    self._scene_fbo.use()
                    if prof:
                        prof.stop("update_dynamic_cubemaps")
                    if shared_cache is not None:
                        shared_cache["_cubemaps_done"] = True
        except Exception:
            pass
        try:
            self._ctx.viewport = (0, 0, rw, rh)
            if use_polygon_mode:
                self._ctx.wireframe = True
        except Exception:
            pass
        try:
            if prof:
                prof.start("process_pending_textures")
            self._materials.process_texture_pending()
            if prof:
                prof.stop("process_pending_textures")
        except Exception:
            pass
        if prof:
            prof.start("render_meshes")
        try:
            renderable, _vis = self._scenev_cull_renderable(snap, renderable, view_mat, proj_mat)
        except Exception:
            pass
        outline_queue = []
        try:
            if selected_entities is not None and len(selected_entities) > 256:
                selected_entities = frozenset()
        except Exception:
            pass
        try:
            opaque_entries, transparent_entries = self._scenev_partition_and_sort(renderable, cam_pos, scene)
        except Exception:
            opaque_entries = renderable if renderable else []
            transparent_entries = []
        try:
            self._scenev_render_forward_phases(opaque_entries, transparent_entries, view_f32, proj_f32, cam_pos, lights, dynamic_cubemaps, sky_component, selected_entities, outline_queue, rw, rh, snap)
        except Exception:
            pass
        if prof:
            prof.stop("render_meshes")
        try:
            if use_polygon_mode:
                self._ctx.wireframe = False
        except Exception:
            pass
        try:
            self._scenev_render_skinned(snap, view_f32, proj_f32, cam_pos, lights, prof)
        except Exception:
            pass
        try:
            self._scenev_render_projectors(snap, view_mat, proj_mat, rw, rh)
        except Exception:
            pass
        try:
            if prof:
                prof.start("render_text_world")
            if self._text and scene:
                with eng._scene_lock:
                    self._text.render(scene, view_mat, proj_mat, rw, rh, world_space_only=True)
            if prof:
                prof.stop("render_text_world")
        except Exception:
            pass
        try:
            if prof:
                prof.start("render_sprites")
            try:
                sprite_key = (id(scene), scene._render_version, scene._transform_version) if scene is not None else None
            except Exception:
                sprite_key = None
            self._sprites.render_snapshot(snap.sprite_items, view_mat, proj_mat, sprite_key)
            if prof:
                prof.stop("render_sprites")
        except Exception:
            pass
        try:
            if prof:
                prof.start("render_videos")
            self._videos.render_snapshot(snap.video_items, view_mat, proj_mat)
            if prof:
                prof.stop("render_videos")
        except Exception:
            pass
        try:
            if self._grid and self._grid.show:
                if prof:
                    prof.start("render_grid")
                if "u_bg_lum" in self._grid_prog:
                    try:
                        cc = self._clear_color or [0.18, 0.18, 0.18]
                        self._grid_prog["u_bg_lum"].value = float(cc[0]) * 0.299 + float(cc[1]) * 0.587 + float(cc[2]) * 0.114
                    except Exception:
                        pass
                if "u_viewport_size" in self._grid_prog:
                    self._grid_prog["u_viewport_size"].value = (float(viewport_w), float(viewport_h))
                self._ctx.enable(moderngl.BLEND)
                self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                self._grid.render(view_f32, proj_f32, cam_pos, self._clear_color, viewport_h, cam_fov)
                self._ctx.disable(moderngl.BLEND)
                if prof:
                    prof.stop("render_grid")
        except Exception:
            pass
        try:
            self._scenev_render_water(snap, water_components, view_mat, proj_mat, cam_pos, dir_light, rw, rh, cam_near, cam_far, shared_cache)
        except Exception:
            pass
        try:
            self._scenev_render_water_volumes(snap, water_components, view_mat, proj_mat, view_f32, proj_f32, cam_pos, dir_light, rw, rh, cam_near, cam_far)
        except Exception:
            pass
        try:
            self._scenev_render_clouds(snap, cloud_components, view_mat, proj_mat, dir_light, cam_pos, rw, rh)
        except Exception:
            pass
        try:
            self._scenev_present_composite(snap, scene, renderable, transparent_entries, view_mat, proj_mat, cam_pos, rw, rh, viewport_w, viewport_h, display_w, display_h, fbo, outline_queue, unjit_proj, stats_groups=getattr(self, "_fwd_stats_groups", None))
        except Exception:
            pass
        try:
            if prof:
                prof.start("render_graphics_done")
                prof.stop("render_graphics_done")
        except Exception:
            pass
        if prof:
            try:
                prof.stop("render_scene")
            except Exception:
                pass
