# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from core.maths.math3d import Vec3, Quat
from core.foundation.logger import Logger
from core.gizmo.core import GizmoMode


class ViewportSelectionMixin:

    def _set_gizmo_entity(self, entity):
        self._gizmo.entity = entity
        self._update_gizmo_pivot()

    def _update_gizmo_pivot(self):
        if len(self._selected_entities) > 1:
            center = Vec3.zero()
            count = 0
            for ent in self._selected_entities:
                t = ent.transform
                if t:
                    center += t.position
                    count += 1
            if count > 0:
                center /= count
            pt = self._gizmo.entity.transform if self._gizmo.entity else None
            self._gizmo._pivot_offset = center - (pt.position if pt else Vec3.zero())
            self._gizmo._visual_center = None
        else:
            self._gizmo._pivot_offset = Vec3.zero()
            self._gizmo._visual_center = None

    def set_selected_entity(self, entity):
        self._selected_entities = [entity] if entity else []
        self._set_gizmo_entity(entity)
        self._update_gizmo_pivot()
        from editor.viewport.collaboration import send_collab_selection
        send_collab_selection(self)

    def set_selected_entities(self, entities: list):
        self._selected_entities = list(entities)
        self._set_gizmo_entity(entities[0] if entities else None)
        self._update_gizmo_pivot()
        from editor.viewport.collaboration import send_collab_selection
        send_collab_selection(self)

    def _on_scene_loaded(self, scene):
        self._gizmos_api.clear()
        try:
            self._post_load_warmup = 2
        except Exception:
            pass
        Logger.info(f"_on_scene_loaded: selected={len(self._selected_entities)} scene_entities={len(scene._entities)}")
        old_ids = [e.id for e in self._selected_entities]
        resolved = [scene.get_entity(eid) for eid in old_ids if scene.get_entity(eid)]
        Logger.info(f"_on_scene_loaded: resolved {len(old_ids)} -> {len(resolved)}")
        self._selected_entities = resolved
        self._set_gizmo_entity(self._selected_entities[0] if self._selected_entities else None)
        if hasattr(self, "_sel_bounds_state"):
            self._sel_bounds_state = [None, None]
        if hasattr(self, "_sel_bounds_peers"):
            self._sel_bounds_peers.clear()
        self.entities_selected.emit(self._selected_entities)
        from editor.viewport.collaboration import send_collab_selection
        send_collab_selection(self)

    def _on_play_start(self, data=None):
        self._gizmos_api.clear()

    def _on_play_stop(self, data=None):
        self._gizmos_api.clear()
        self._cached_overlay_state = None
        self._throttle_next_t = 0.0
        self._throttle_armed = False

    def _delete_selected(self):
        if not self._selected_entities or not self._engine.scene:
            return
        from editor.viewport.collaboration import is_collab_locked
        if is_collab_locked(self):
            return
        from core.foundation.cmd import DeleteEntityCommand, get_history
        for ent in list(self._selected_entities):
            from editor.viewport.collaboration import send_collab_entity_delete
            send_collab_entity_delete(self, ent.id)
            cmd = DeleteEntityCommand(self._engine.scene, ent.id)
            get_history().execute(cmd)
        self._selected_entities.clear()
        self._set_gizmo_entity(None)
        self.entity_selected.emit(None)

    def _copy_selected_entities(self):
        if not self._selected_entities:
            return
        seen = set()
        to_serialize = []
        for e in self._selected_entities:
            if e.id in seen:
                continue
            stack = [(e, True)]
            while stack:
                current, is_top = stack.pop()
                if current.id in seen:
                    continue
                seen.add(current.id)
                to_serialize.append((current, is_top))
                for child in current.children:
                    stack.append((child, False))
        self._entity_clipboard = []
        for e, is_top in to_serialize:
            data = e.serialize()
            if is_top:
                data["parent"] = None
            if is_top:
                t = e.transform
                if t:
                    world_pos, world_rot, world_scale = t.world_matrix.decompose()
                    for comp_data in data.get("components", []):
                        if comp_data.get("_key") == "Transform":
                            comp_data["local_position"] = world_pos.to_list()
                            comp_data["local_rotation"] = world_rot.to_list()
                            comp_data["local_scale"] = world_scale.to_list()
                            break
            self._entity_clipboard.append(data)

    def _paste_entities(self):
        from core.engine.eng import Engine
        from core.foundation.cmd import PasteEntitiesCommand, get_history
        registry = Engine.instance()._component_registry
        if not self._entity_clipboard or not self._engine.scene:
            return
        cmd = PasteEntitiesCommand(self._engine.scene, self._entity_clipboard, registry)
        get_history().execute(cmd)
        top_entities = []
        for eid in cmd.spawned_ids:
            e = self._engine.scene.get_entity(eid)
            if e and e.parent is None:
                top_entities.append(e)
        self._selected_entities = top_entities
        self._set_gizmo_entity(top_entities[0] if top_entities else None)
        from editor.viewport.collaboration import send_collab_entity_create, send_collab_selection
        try:
            collab = self._engine.collab_manager
            connected = bool(collab and collab.connected)
        except Exception:
            connected = False
        if connected:
            for eid in cmd.spawned_ids:
                e = self._engine.scene.get_entity(eid)
                if e:
                    send_collab_entity_create(self, e.serialize())
        send_collab_selection(self)
        self.scene_modified.emit()
        self.entities_selected.emit(self._selected_entities)
        if top_entities:
            self.entity_selected.emit(top_entities[0])
        self.update()

    def _populate_viewport_create_menu(self, create_menu):
        from editor.panels.add_entity_menu import populate_add_menu
        populate_add_menu(create_menu, on_system=lambda mp: self._emit_create_request("system", mp), on_asset=lambda ap: self._emit_create_request("asset", ap), on_search=None)

    def _emit_create_request(self, obj_type="empty", subtype=None):
        from core.foundation.cmd import CreateSystemPrefabCommand, InstantiatePrefabCommand, get_history
        scene = self._engine.scene
        from editor.viewport.collaboration import is_collab_locked
        if not scene or is_collab_locked(self):
            return
        if obj_type == "system" and subtype:
            cmd = CreateSystemPrefabCommand(scene, subtype, None)
            get_history().execute(cmd)
            spawned = [scene.get_entity(eid) for eid in cmd._spawned_ids]
            spawned = [e for e in spawned if e]
            e = spawned[0] if spawned else None
            if e:
                self._selected_entities = [e]
                self._set_gizmo_entity(e)
                self.entity_selected.emit(e)
                from editor.viewport.collaboration import send_collab_entity_create
                send_collab_entity_create(self, e.serialize())
            return
        if obj_type == "asset" and subtype:
            from core.ecs.prefabp import PrefabLibrary
            prefab = PrefabLibrary.load(subtype)
            if not prefab:
                return
            cmd = InstantiatePrefabCommand(scene, prefab, self._engine._component_registry)
            get_history().execute(cmd)
            spawned = [scene.get_entity(eid) for eid in cmd._spawned_ids]
            spawned = [e for e in spawned if e]
            e = spawned[0] if spawned else None
            if e:
                self._selected_entities = [e]
                self._set_gizmo_entity(e)
                self.entity_selected.emit(e)
                from editor.viewport.collaboration import send_collab_entity_create
                send_collab_entity_create(self, e.serialize())
            return
        legacy_map = {"empty": "Create Empty", "cube": "3D Object/Cube", "sphere": "3D Object/Sphere", "plane": "3D Object/Plane", "sun": "Light/Sun", "camera": "Camera", "sky": "Effects/Procedural Sky", "clouds": "Effects/Clouds", "particle_system": "Effects/Particle System"}
        if obj_type == "light" and subtype:
            legacy_map[obj_type] = {"directional": "Light/Directional Light", "point": "Light/Point Light", "spot": "Light/Spot Light", "area": "Light/Area Light"}.get(subtype, "Light/Point Light")
        menu_path = legacy_map.get(obj_type)
        if menu_path:
            cmd = CreateSystemPrefabCommand(scene, menu_path, None)
            get_history().execute(cmd)
            spawned = [scene.get_entity(eid) for eid in cmd._spawned_ids]
            spawned = [e for e in spawned if e]
            e = spawned[0] if spawned else None
            if e:
                self._selected_entities = [e]
                self._set_gizmo_entity(e)
                self.entity_selected.emit(e)
                from editor.viewport.collaboration import send_collab_entity_create
                send_collab_entity_create(self, e.serialize())
            return
        return

    def _extrude_on_ctrl_press(self):
        try:
            from core.foundation.cmd import PasteEntitiesCommand, get_history
            from core.engine.eng import Engine
            scene = self._engine.scene
            if scene and self._selected_entities:
                clipboard = []
                for e in self._selected_entities:
                    clipboard.append(e.serialize())
                if clipboard:
                    reg = Engine.instance()._component_registry if Engine.instance() else None
                    cmd = PasteEntitiesCommand(scene, clipboard, reg)
                    get_history().execute(cmd)
                    new_entities = [scene.get_entity(eid) for eid in cmd.spawned_ids]
                    new_entities = [e for e in new_entities if e]
                    if new_entities:
                        self._selected_entities = new_entities
                        self._set_gizmo_entity(new_entities[0])
                        self.entities_selected.emit(self._selected_entities)
                        try:
                            from editor.viewport.collaboration import send_collab_selection, send_collab_entity_create
                            send_collab_selection(self)
                            try:
                                _cc = self._engine.collab_manager
                                _conn = bool(_cc and _cc.connected)
                            except Exception:
                                _conn = False
                            if _conn:
                                for ne in new_entities:
                                    send_collab_entity_create(self, ne.serialize())
                        except Exception:
                            pass
        except Exception:
            pass

    def _store_multi_initial(self):
        self._multi_entity_initial_transforms = {}
        for ent in self._selected_entities:
            et = ent.transform
            if et:
                self._multi_entity_initial_transforms[ent.id] = {"position": Vec3(et.position.x, et.position.y, et.position.z), "local_rotation": Quat(et.local_rotation.x, et.local_rotation.y, et.local_rotation.z, et.local_rotation.w), "local_scale": Vec3(et.local_scale.x, et.local_scale.y, et.local_scale.z)}

    def _drag_multi_entities(self, primary, pre_pos, pre_rot):
        if primary is None or pre_pos is None:
            return
        pt = primary.transform
        if not pt:
            return
        center = Vec3.zero()
        count = 0
        for init in self._multi_entity_initial_transforms.values():
            center += init["position"]
            count += 1
        if count > 0:
            center /= count
        if self._gizmo._mode == GizmoMode.ROTATE:
            primary_init = self._multi_entity_initial_transforms.get(primary.id)
            if primary_init:
                world_rot_rel = (pt.local_rotation * primary_init["local_rotation"].conjugate()).normalized()
                for eid, init in self._multi_entity_initial_transforms.items():
                    ent = self._engine.scene.get_entity(eid)
                    if not ent:
                        continue
                    et = ent.transform
                    if et:
                        offset = init["position"] - center
                        rotated = world_rot_rel.rotate_vec3(offset)
                        et.position = center + rotated
                        et.local_rotation = (world_rot_rel * init["local_rotation"]).normalized()
        elif self._gizmo._mode == GizmoMode.SCALE:
            primary_init = self._multi_entity_initial_transforms.get(primary.id)
            if primary_init:
                dS_current = Vec3(pt.local_scale.x / max(0.001, primary_init["local_scale"].x), pt.local_scale.y / max(0.001, primary_init["local_scale"].y), pt.local_scale.z / max(0.001, primary_init["local_scale"].z))
            else:
                dS_current = Vec3(1, 1, 1)
            world_rot_rel = (pt.local_rotation * pre_rot.conjugate()).normalized()
            for eid, init in self._multi_entity_initial_transforms.items():
                ent = self._engine.scene.get_entity(eid)
                if not ent:
                    continue
                et = ent.transform
                if et:
                    offset = init["position"] - center
                    et.position = center + Vec3(offset.x * dS_current.x, offset.y * dS_current.y, offset.z * dS_current.z)
                    et.local_rotation = (world_rot_rel * init["local_rotation"]).normalized()
                    if eid != primary.id:
                        et.local_scale = Vec3(max(0.001, init["local_scale"].x * dS_current.x), max(0.001, init["local_scale"].y * dS_current.y), max(0.001, init["local_scale"].z * dS_current.z))
        else:
            pos_delta = pt.position - pre_pos
            world_rot_rel = (pt.local_rotation * pre_rot.conjugate()).normalized()
            for ent in self._selected_entities:
                if ent is primary:
                    continue
                et = ent.transform
                if et:
                    et.position = et.position + pos_delta
                    et.local_rotation = (world_rot_rel * et.local_rotation).normalized()
        new_center = Vec3.zero()
        cnt = 0
        for ent in self._selected_entities:
            et = ent.transform
            if et:
                new_center += et.position
                cnt += 1
        if cnt > 0:
            new_center /= cnt
        self._gizmo._visual_center = new_center

    def _commit_multi_transform(self):
        if self._multi_entity_initial_transforms:
            from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history
            from core.components import Transform as TransformComponent
            cmds = []
            for ent in self._selected_entities:
                init = self._multi_entity_initial_transforms.get(ent.id)
                if not init:
                    continue
                et = ent.transform
                if not et:
                    continue
                if self._gizmo._mode == GizmoMode.TRANSLATE:
                    new_pos = et.position
                    if (new_pos - init["position"]).length() > 1e-8:
                        cmds.append(SetComponentCommand(ent, TransformComponent, "position", init["position"], new_pos))
                elif self._gizmo._mode in (GizmoMode.ROTATE, GizmoMode.SCALE):
                    new_pos = et.position
                    if (new_pos - init["position"]).length() > 1e-8:
                        cmds.append(SetComponentCommand(ent, TransformComponent, "position", init["position"], new_pos))
                    if self._gizmo._mode == GizmoMode.ROTATE:
                        new_rot = et.local_rotation
                        cmds.append(SetComponentCommand(ent, TransformComponent, "local_rotation", init["local_rotation"], new_rot))
                    else:
                        new_scale = et.local_scale
                        if (new_scale - init["local_scale"]).length() > 1e-8:
                            cmds.append(SetComponentCommand(ent, TransformComponent, "local_scale", init["local_scale"], new_scale))
            if cmds:
                get_history().set_current_selection(list(self._selected_entities))
                get_history().execute(CompoundCommand(cmds, "Multi-Entity Transform"))
            self._multi_entity_initial_transforms = {}
            self._update_gizmo_pivot()

    def _paint_gizmo_block(self, vp_mat, fw, fh, cam_pos, render_ms_holder=None):
        from editor.viewport.rend import render_component_gizmos, render_selection_bounds
        from editor.viewport.component_icons import render_component_icons_gl
        from editor.viewport.collaboration import render_remote_collaborator_gizmos
        import time as _t
        eng = self._engine
        _sel = list(self._selected_entities)
        _play = bool(getattr(eng, "play_mode", False))
        _acquired = eng._scene_lock.acquire(blocking=False)
        try:
            _warm = False
            if eng.scene is not None and getattr(self, "_post_load_warmup", 0) > 0:
                try:
                    self._post_load_warmup -= 1
                    _warm = True
                except Exception:
                    _warm = False
            if _acquired:
                if self._gizmo_visible and not _warm:
                    render_component_gizmos(self, vp_mat)
                if not _play:
                    render_selection_bounds(self, vp_mat, _t.perf_counter(), self._last_dt)
                    try:
                        if self._gizmo_icons_visible:
                            render_component_icons_gl(self)
                    except Exception:
                        pass
                    self._render_api_gizmos()
                    try:
                        render_remote_collaborator_gizmos(self, vp_mat, cam_pos, fw, fh)
                    except Exception:
                        pass
                else:
                    self._render_api_gizmos()
            elif not _play:
                if self._gizmo_visible and not _warm:
                    render_component_gizmos(self, vp_mat)
                render_selection_bounds(self, vp_mat, _t.perf_counter(), self._last_dt)
        finally:
            if _acquired:
                eng._scene_lock.release()
        if self._debug_lines and not _play:
            self._renderer.render_gizmo_lines(self._debug_lines, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.0)
            self._debug_lines.clear()
        elif _play and self._debug_lines:
            self._debug_lines.clear()
        if not _play:
            try:
                self._render_cursor(vp_mat, fw, fh, cam_pos)
            except Exception:
                pass
        if self._show_bvh_debug and not _play:
            self._render_bvh_debug()
        if self._pb_scale_gizmo and self._pb_scale_gizmo.active and not _play:
            self._pb_scale_gizmo.render()
        if not _play and self._gizmo.entity is not None and self._gizmo.mode != GizmoMode.NONE:
            from core.gizmo.core import GizmoMode as _GM
            gizmo_result = self._gizmo.get_gizmo_arrays(self._cam, fw, fh)
            if gizmo_result is not None:
                gs, ge, gcol = gizmo_result
                self._renderer.render_gizmo_arrays(gs, ge, gcol, vp_mat, fw, fh, thickness_multiplier=1.8, cam_pos=cam_pos)
            else:
                gizmo_lines = self._gizmo.get_gizmo_lines(self._cam, fw, fh)
                if gizmo_lines:
                    self._renderer.render_gizmo_lines(gizmo_lines, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.8)


__all__ = ["ViewportSelectionMixin"]
