# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import concurrent.futures
import os
import uuid
from .entity import Entity
from .registry import ComponentRegistry


def _rebind_armatures(entities: list, id_map: dict) -> None:
    for e in entities:
        arm = e.get_component_by_name("Armature")
        if arm is not None and getattr(arm, "bone_entity_ids", None):
            arm.bone_entity_ids = [id_map.get(bid, bid) for bid in arm.bone_entity_ids]


def _serialize_inner(scene) -> dict:
    items = list(scene._entities.items())
    if len(items) > 64:
        workers = min(8, max(2, (os.cpu_count() or 4)))
        chunk = (len(items) + workers - 1) // workers
        out: dict = {}
        def task(part):
            return [(eid, e.serialize()) for eid, e in part]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(task, items[i:i + chunk]) for i in range(0, len(items), chunk)]
            for fu in concurrent.futures.as_completed(futs):
                try:
                    for eid, ed in fu.result():
                        out[eid] = ed
                except Exception:
                    pass
        data = {"name": scene._name, "entities": out}
    else:
        data = {"name": scene._name, "entities": {eid: e.serialize() for eid, e in scene._entities.items()}}
    if scene._embed_all:
        data["embed_all"] = True
    if scene._compress_resources:
        data["compress_resources"] = True
    if scene._compress_level is not None:
        data["compress_level"] = scene._compress_level
    prof = scene._get_profiler()
    if prof is not None:
        prof.set_value("scene_serialize", 0)
    return data


def _deserialize_inner(cls, data: dict, registry: ComponentRegistry):
    s = cls(data["name"])
    s._embed_all = bool(data.get("embed_all", False))
    s._compress_resources = bool(data.get("compress_resources", False))
    s._compress_level = data.get("compress_level")
    raw = data.get("entities", {})
    entities: dict[str, Entity] = {}
    parent_map: dict[str, str | None] = {}
    items = list(raw.items())
    if len(items) > 64:
        workers = min(8, max(2, (os.cpu_count() or 4)))
        chunk = (len(items) + workers - 1) // workers
        def task(part):
            res = []
            append = res.append
            for eid, ed in part:
                try:
                    append((eid, Entity.deserialize(ed, registry), ed.get("parent")))
                except Exception:
                    pass
            return res
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(task, items[i:i + chunk]) for i in range(0, len(items), chunk)]
            for fu in concurrent.futures.as_completed(futs):
                try:
                    for eid, e, pid in fu.result():
                        entities[eid] = e
                        parent_map[eid] = pid
                except Exception:
                    pass
    else:
        for eid, ed in raw.items():
            e = Entity.deserialize(ed, registry)
            entities[eid] = e
            parent_map[eid] = ed.get("parent")
    store = s._entities
    dirty_roots = s._dirty_roots
    for eid, e in entities.items():
        pid = parent_map.get(eid)
        if pid and pid in entities:
            parent = entities[pid]
            e._parent = parent
            parent._children.append(e)
        store[e.id] = e
        e._scene = s
        t = e._transform
        if t is not None and getattr(t, "_dirty", False):
            dirty_roots.add(t)
    if dirty_roots:
        s._transform_version_pending = True
    s._batch_sync_entities(entities)
    s._dirty = False
    return s


def _duplicate_entity_inner(scene, entity: Entity, new_name: str = ""):
    if entity._scene is not scene:
        entity = scene.get_entity(entity.id) or entity
    order = []
    stack = [entity]
    while stack:
        cur = stack.pop()
        order.append(cur)
        try:
            chs = list(cur._children)
        except Exception:
            chs = []
        for ch in reversed(chs):
            stack.append(ch)
    nodes = []
    id_map = {}
    for src in order:
        try:
            data = src.serialize()
        except Exception:
            continue
        nid = str(uuid.uuid4())
        data["id"] = nid
        data["parent"] = None
        id_map[src._id] = nid
        nodes.append((src, data))
    new_entities: list[Entity] = []
    for src, data in nodes:
        new_e = Entity.deserialize(data, ComponentRegistry)
        new_entities.append(new_e)
    if not new_entities:
        raise ValueError("duplicate failed")
    idx = scene._component_indices
    auc = scene._active_update_components
    afc = scene._active_fixed_components
    ents = scene._entities
    dirty_roots = scene._dirty_roots
    sde = scene._spatial_dirty_entities
    ske = scene._spatial_known_entities
    for new_e in new_entities:
        new_e._scene = scene
        eid = new_e._id
        ents[eid] = new_e
        is_active = new_e._active
        for comp_type, clist in new_e._type_map.items():
            comp_name = comp_type.__name__
            s = idx.get(comp_name)
            if s is None:
                idx[comp_name] = {eid}
            else:
                s.add(eid)
            if is_active:
                for comp in clist:
                    if comp.enabled:
                        if comp._updates:
                            auc.add(comp)
                        if comp._fixed_updates:
                            afc.add(comp)
        t = new_e._transform
        if t is not None and getattr(t, "_dirty", False):
            dirty_roots.add(t)
        sde.add(eid)
        ske.discard(eid)
    new_by_id = {src._id: e for (src, _), e in zip(nodes, new_entities)}
    for (src, _data), new_e in zip(nodes, new_entities):
        sp = src._parent
        if sp is None:
            continue
        if sp._id in new_by_id:
            np_ = new_by_id[sp._id]
            new_e._parent = np_
            np_._children.append(new_e)
        else:
            new_e._parent = sp
            sp._children.append(new_e)
    scene._invalidate_update_cache()
    scene._dirty = True
    scene._render_version += 1
    scene._entities_cache_valid = False
    scene._roots_cache_valid = False
    scene._spatial_dirty = True
    _rebind_armatures(new_entities, id_map)
    if new_name:
        new_entities[0].name = new_name
    return new_entities[0]


def _paste_entities_inner(scene, clipboard_data: list, registry) -> list:
    id_map: dict = {}
    spawned: list = []
    for data in clipboard_data:
        old_id = data.get("id")
        if not old_id:
            continue
        new_id = str(uuid.uuid4())
        id_map[old_id] = new_id
        d = dict(data)
        d["id"] = new_id
        e = Entity.deserialize(d, registry)
        spawned.append(e)
    if not spawned:
        return spawned
    idx = scene._component_indices
    auc = scene._active_update_components
    afc = scene._active_fixed_components
    ents = scene._entities
    dirty_roots = scene._dirty_roots
    sde = scene._spatial_dirty_entities
    ske = scene._spatial_known_entities
    for e in spawned:
        e._scene = scene
        eid = e._id
        ents[eid] = e
        is_active = e._active
        for comp_type, clist in e._type_map.items():
            comp_name = comp_type.__name__
            s = idx.get(comp_name)
            if s is None:
                idx[comp_name] = {eid}
            else:
                s.add(eid)
            if is_active:
                for comp in clist:
                    if comp.enabled:
                        if comp._updates:
                            auc.add(comp)
                        if comp._fixed_updates:
                            afc.add(comp)
        t = e._transform
        if t is not None and getattr(t, "_dirty", False):
            dirty_roots.add(t)
        sde.add(eid)
        ske.discard(eid)
    all_by_id = {e._id: e for e in spawned}
    need_roots_fix = False
    for data in clipboard_data:
        parent_id = data.get("parent")
        if not parent_id or parent_id not in id_map:
            continue
        child = all_by_id.get(id_map[data["id"]])
        new_parent = all_by_id.get(id_map[parent_id])
        if child is not None and new_parent is not None:
            child._parent = new_parent
            new_parent._children.append(child)
            need_roots_fix = True
    scene._invalidate_update_cache()
    scene._dirty = True
    scene._render_version += 1
    scene._entities_cache_valid = False
    scene._roots_cache_valid = False
    scene._spatial_dirty = True
    _rebind_armatures(spawned, id_map)
    return spawned
