# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Scene snapshot collection."""

from __future__ import annotations
import os
from core.components import LightType, LightAreaType
from core.components.lighting import Light, Projector
from core.components.rendering.renderers.mesh_filter import MeshFilter
from core.components.rendering.renderers.mesh_renderer import MeshRenderer
from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
from core.components.rendering.renderers.gaussian_splat_renderer import GaussianSplatRenderer as GaussianSplatComponent
from core.components.rendering.skeleton.armature import Armature
from core.components.rendering.deform.blendshapes import BlendShapes
from core.components.rendering.renderers.sprite_renderer import SpriteRenderer
from core.components.rendering.renderers.svg_renderer import SvgRenderer
from core.components.rendering.particles.particle_system import ParticleSystem
from core.components.rendering.particles.particle_force_field import ParticleForceField, FORCE_FIELD_DTYPE, MAX_FORCE_FIELDS
from core.components.rendering.renderers.video_renderer import VideoRenderer
from core.maths.math3d import Mat4, Vec3
from core.components.rendering.environment.sky import Sky, release_env_cache
from core.components.rendering.environment.clouds import Cloud
from core.components.rendering.environment.water import Water
from core.components.rendering.environment.dynamic_cubemap import DynamicCubemaps
from core.components.environment.wind_zone import WindZone
from core.components.physics.sphere_collider import SphereCollider
from core.components.physics.box_collider import BoxCollider
from core.components.physics.capsule_collider import CapsuleCollider
from core.components.physics.rigidbody import Rigidbody
from core.renderer.render_items import _ProjectorItem, _SpriteItem, _SvgItem, _VideoItem
from core.renderer.render_snapshot import _RenderSnapshot


class SceneCollectorMixin:
    """Scene snapshot collection."""


    def _blend_snapshot_sig(self, scene) -> tuple:
        try:
            ents = scene.get_entities_with_component(BlendShapes)
        except Exception:
            return ()
        if not ents:
            return ()
        out = []
        for ent in ents:
            try:
                if not ent.active:
                    continue
                bs = ent.get_component(BlendShapes)
                if bs is None or not getattr(bs, "enabled", True):
                    continue
                items = []
                for s in bs.shapes:
                    try:
                        items.append((str(s.get("name", "")), float(s.get("weight", 0.0))))
                    except (TypeError, ValueError):
                        continue
                out.append((ent.id, tuple(sorted(items))))
            except Exception:
                continue
        return tuple(out)


    def _collect_snapshot(self, scene, cam_near, cam_far, cam_fov, view_mat, proj_mat, cam_pos) -> _RenderSnapshot:
        n_updated = scene.flush_transforms()
        struct_version = scene._render_version
        mesh_gen = self._mesh_loader._loaded_generation if self._mesh_loader else 0
        morph_sig = self._blend_snapshot_sig(scene)
        if (self._snap_cache is not None
                and self._snap_scene is scene
                and self._snap_struct_version == struct_version
                and self._snap_mesh_gen == mesh_gen
                and self._snap_morph_sig == morph_sig):
            self._refresh_snapshot_world_matrices(scene)
            self._collect_interactors(self._snap_cache, scene)
            return self._snap_cache
        snap = _RenderSnapshot()
        if not self._import_meta_cache:
            self._preload_import_meta(scene)
        for ent in scene.get_entities_with_component(Light):
            if not ent.active:
                continue
            l = ent.get_component(Light)
            t = ent.transform
            if l and l.enabled and t:
                snap.lights.append((l, t))
                if snap.dir_light is None and l.light_type == LightType.DIRECTIONAL:
                    snap.dir_light = (l, t)
        for ent in scene.get_entities_with_component(Sky):
            if ent.active:
                snap.sky_component = ent.get_component(Sky)
                snap.sky_entity = ent
                break
        for ent in scene.get_entities_with_component(Cloud):
            if ent.active:
                cloud = ent.get_component(Cloud)
                if cloud and cloud.enabled:
                    snap.cloud_components.append(cloud)
        for ent in scene.get_entities_with_component(Water):
            if ent.active:
                water = ent.get_component(Water)
                if water and water.enabled:
                    snap.water_components.append(water)
        best_dist_sq = None
        for ent in scene.get_entities_with_component(DynamicCubemaps):
            if ent.active:
                dc = ent.get_component(DynamicCubemaps)
                if dc and dc.enabled:
                    probe_pos = ent.transform.position
                    d = probe_pos - cam_pos
                    dist_sq = d.x * d.x + d.y * d.y + d.z * d.z
                    if best_dist_sq is None or dist_sq < best_dist_sq:
                        best_dist_sq = dist_sq
                        snap.dynamic_cubemaps = dc
                        snap.dynamic_cubemaps_pos = probe_pos
                        snap.dynamic_cubemaps_entity = ent
        for ent in scene.get_entities_with_component(WindZone):
            if ent.active:
                wz = ent.get_component(WindZone)
                if wz and wz.enabled:
                    snap.wind_zones.append(wz)
        self._collect_interactors(snap, scene)
        self._sync_probuilder_meshes(scene)
        self._sync_terrain_meshes(scene)
        self._sync_tree_meshes(scene)
        needs_shadow = any(l.cast_shadows for l, _ in snap.lights)
        if not needs_shadow:
            for ent in scene.get_entities_with_component(Projector):
                if ent.active:
                    pj = ent.get_component(Projector)
                    if pj and pj.enabled and pj.cast_shadows:
                        needs_shadow = True
                        break
        get_mesh = self.get_or_create_mesh
        sync_meta = self._sync_import_meta
        find_fx = self._find_object_effect
        renderable = snap.renderable
        cull_entries = snap.cull_entries
        cull_offsets = snap.cull_offsets
        cull_counts = snap.cull_counts
        shadow_list = snap.shadow_renderables
        splitext = os.path.splitext
        basename = os.path.basename
        for ent in scene.get_entities_with_component(MeshFilter):
            if not ent._active:
                continue
            mr_list = ent._type_map.get(MeshRenderer)
            if not mr_list:
                continue
            mr = mr_list[0]
            if not mr.enabled:
                continue
            tt = ent._transform_type
            if tt is not None:
                tl = ent._type_map.get(tt)
                tr = tl[0] if tl else None
            else:
                tr = ent.transform
            if tr is None:
                continue
            mf_list = ent._type_map.get(MeshFilter)
            mf = mf_list[0] if mf_list else ent.get_component(MeshFilter)
            if mf is None:
                continue
            mesh_name = mf.mesh_name
            mesh_path = mf.mesh_path or ""
            if mesh_path:
                _meta = sync_meta(mesh_path)
                scale, cp, fuvs = _meta[0], _meta[1], _meta[2]
            else:
                scale, cp, fuvs = 1.0, False, False
            if not mesh_name and not mesh_path:
                mesh_name = "cube"
            elif not mesh_name:
                mesh_name = splitext(basename(mesh_path))[0]
            mesh = get_mesh(mesh_name, mesh_path, scale, cp, fuvs)
            if mesh is not None:
                try:
                    ov = self._soft_override_mesh(ent, mesh)
                    if ov is not None:
                        mesh = ov
                except Exception:
                    pass
                try:
                    mesh = self._morphed_mesh(ent, mesh)
                except Exception:
                    pass
            if mesh is not None:
                wm = tr.world_matrix
                sub_ranges = mesh.sub_mesh_ranges
                fx_list = find_fx(ent)
                block_start = len(renderable)
                if sub_ranges:
                    for sub_idx in range(len(sub_ranges)):
                        renderable.append([ent, tr, mesh, mr, wm, sub_idx, fx_list])
                    n_sub = len(sub_ranges)
                else:
                    renderable.append([ent, tr, mesh, mr, wm, -1, fx_list])
                    n_sub = 1
                cull_entries.append(renderable[block_start])
                cull_offsets.append(block_start)
                cull_counts.append(n_sub)
                if needs_shadow and mr.cast_shadows:
                    shadow_list.append([mesh, tr])
        for ent in scene.get_entities_with_component(SkinnedMeshRenderer):
            if not ent.active:
                continue
            smr = ent.get_component(SkinnedMeshRenderer)
            tr = ent.transform
            if not tr or not smr or not smr.enabled:
                continue
            armature = ent.get_component(Armature)
            mesh_name = smr.mesh_name
            mesh_path = smr.mesh_path or ""
            if mesh_path:
                _meta = self._sync_import_meta(mesh_path)
                scale, cp, fuvs = _meta[0], _meta[1], _meta[2]
            else:
                scale, cp, fuvs = 1.0, False, False
            if not mesh_name and not mesh_path:
                continue
            elif not mesh_name and mesh_path:
                mesh_name = os.path.splitext(os.path.basename(mesh_path))[0]
            mesh = self.get_or_create_mesh(mesh_name, mesh_path, 1.0, False, fuvs)
            if not mesh or not getattr(mesh, 'has_skeleton', False):
                continue
            try:
                mesh = self._morphed_mesh(ent, mesh)
            except Exception:
                pass
            wm = tr.world_matrix
            sub_ranges = mesh.sub_mesh_ranges
            if sub_ranges:
                for sub_idx in range(len(sub_ranges)):
                    snap.skinned_renderables.append([ent, tr, mesh, smr, wm, armature, sub_idx])
            else:
                snap.skinned_renderables.append([ent, tr, mesh, smr, wm, armature, -1])
            if needs_shadow and smr.cast_shadows:
                snap.skinned_shadow_renderables.append([mesh, ent, armature, wm])
        for ent in scene.get_entities_with_component(SpriteRenderer):
            if not ent.active:
                continue
            sr = ent.get_component(SpriteRenderer)
            if not sr or not sr.enabled:
                continue
            tr = ent.transform
            if not tr:
                continue
            snap.sprite_items.append(_SpriteItem(
                tr.world_matrix, sr.color, sr.flip_x, sr.flip_y, sr.texture_path, tr))
        for ent in scene.get_entities_with_component(VideoRenderer):
            if not ent.active:
                continue
            vr = ent.get_component(VideoRenderer)
            if not vr or not vr.enabled:
                continue
            tr = ent.transform
            if not tr:
                continue
            snap.video_items.append(_VideoItem(
                tr.world_matrix, vr.color, vr.flip_x, vr.flip_y,
                vr.video_path, ent._id, vr.loop, vr.volume, vr.offset,
                vr.audio_source_entity_id, tr))
        for ent in scene.get_entities_with_component(SvgRenderer):
            if not ent.active:
                continue
            sr = ent.get_component(SvgRenderer)
            if not sr or not sr.enabled:
                continue
            tr = ent.transform
            if not tr:
                continue
            abs_path = self._svgs.resolve_path(sr.svg_path)
            snap.svg_items.append(_SvgItem(
                tr.world_matrix, sr.color, sr.flip_x, sr.flip_y,
                abs_path or "", sr.pixels_per_unit, tr))
        for ent in scene.get_entities_with_component(Projector):
            if not ent.active:
                continue
            pj = ent.get_component(Projector)
            if not pj or not pj.enabled:
                continue
            tr = ent.transform
            if not tr:
                continue
            pos = tr.position
            fwd = tr.forward
            up = tr.up
            view = Mat4.look_at(pos, pos + fwd, up)
            proj = Mat4.perspective(pj.spot_angle, pj.aspect_ratio, pj.near_plane, pj.far_plane)
            vp = (view @ proj).to_f32()
            snap.projectors.append(_ProjectorItem(
                pj.texture_path, pj.color, pj.intensity, pj.range,
                pj.spot_angle, pj.aspect_ratio, pj.near_plane, pj.far_plane,
                vp, pos, fwd, up, flip_y=pj.flip_y, flip_x=pj.flip_x,
                cast_shadows=pj.cast_shadows, tr=tr))
        for ent in scene.get_entities_with_component(ParticleSystem):
            if not ent.active:
                continue
            ps = ent.get_component(ParticleSystem)
            if not ps or not ps.enabled:
                continue
            if ps._alive_count == 0:
                continue
            snap.particle_systems.append(ps)
        for ent in scene.get_entities_with_component(ParticleForceField):
            if not ent.active:
                continue
            ff = ent.get_component(ParticleForceField)
            if ff and ff.enabled:
                snap.force_fields.append(ff)
        for ent in scene.get_entities_with_component(GaussianSplatComponent):
            if not ent.active:
                continue
            gs = ent.get_component(GaussianSplatComponent)
            if not gs or not gs.enabled:
                continue
            if not gs.ply_path:
                continue
            snap.gaussian_splats.append((ent, gs))
        self._snap_cache = snap
        self._snap_version = struct_version
        self._snap_struct_version = struct_version
        self._snap_mesh_gen = mesh_gen
        self._snap_morph_sig = morph_sig
        self._snap_scene = scene
        return snap


    def _collect_interactors(self, snap, scene):
        interactors = []
        collider_types = (SphereCollider, BoxCollider, CapsuleCollider)
        for ent in scene.get_entities_with_component(SphereCollider):
            c = ent.get_component(SphereCollider)
            if not c or not c.enabled or not ent.active:
                continue
            tr = ent.transform
            if not tr:
                continue
            rb = ent.get_component(Rigidbody)
            vel = rb.velocity if rb else Vec3.zero()
            center = tr.position + c.scaled_center
            interactors.append((ent, center, c.scaled_radius, vel, c.scaled_radius))
        for ent in scene.get_entities_with_component(BoxCollider):
            c = ent.get_component(BoxCollider)
            if not c or not c.enabled or not ent.active:
                continue
            tr = ent.transform
            if not tr:
                continue
            rb = ent.get_component(Rigidbody)
            vel = rb.velocity if rb else Vec3.zero()
            center = tr.position + c.scaled_center
            hsize = c.scaled_size * 0.5
            radius = max(hsize.x, hsize.z)
            if radius <= 0.0:
                continue
            interactors.append((ent, center, radius, vel, hsize.y))
        for ent in scene.get_entities_with_component(CapsuleCollider):
            c = ent.get_component(CapsuleCollider)
            if not c or not c.enabled or not ent.active:
                continue
            tr = ent.transform
            if not tr:
                continue
            rb = ent.get_component(Rigidbody)
            vel = rb.velocity if rb else Vec3.zero()
            center = tr.position + c.scaled_center
            interactors.append((ent, center, c.scaled_radius, vel, c.scaled_radius))
        capped = sorted(interactors, key=lambda it: abs(it[1].y), reverse=False)[:64]
        snap.interactors = capped


    def _refresh_snapshot_world_matrices(self, scene):
        snap = self._snap_cache
        if snap is None:
            return
        renderable = snap.renderable
        for entry in renderable:
            tr = entry[1]
            if tr is not None:
                entry[4] = tr.world_matrix
        for entry in snap.skinned_renderables:
            tr = entry[1]
            if tr is not None:
                entry[4] = tr.world_matrix
        for entry in snap.skinned_shadow_renderables:
            ent = entry[1]
            tr = ent.transform if ent is not None else None
            if tr is not None:
                entry[3] = tr.world_matrix
        for item in snap.sprite_items:
            tr = item._tr
            if tr is not None:
                item.world_matrix = tr.world_matrix
        for item in snap.video_items:
            tr = item._tr
            if tr is not None:
                item.world_matrix = tr.world_matrix
        for item in snap.svg_items:
            tr = item._tr
            if tr is not None:
                item.world_matrix = tr.world_matrix
        for item in snap.projectors:
            item.refresh_vp()
        try:
            self._refresh_soft_snapshot_meshes(scene)
        except Exception:
            pass
