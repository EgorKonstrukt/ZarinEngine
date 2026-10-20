# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from concurrent.futures.thread import ThreadPoolExecutor
import copy
import uuid
from core.ecs import Entity, ComponentRegistry
from core.foundation.logger import Logger
from core.ecs.prefabp.prefab import Prefab, PrefabOverrideType, _ROOT_TRANSFORM_SKIP_COMPARE
def compute_overrides(entity: Entity) -> list[dict]:
    if not entity._prefab_guid:
        return []
    prefab = Prefab._resolve_prefab_for_entity(entity)
    if prefab is None:
        return []
    source_id = entity._prefab_source_id
    prefab_data = Prefab._find_source_data(prefab.roots_data, source_id)
    if prefab_data is None:
        for rd in prefab.roots_data:
            prefab_data = Prefab._find_source_data([rd], source_id)
            if prefab_data:
                break
    if prefab_data is None:
        return []
    current = entity.serialize()
    is_root_of_instance = Prefab._is_root_of_instance(entity)
    overrides = Prefab._diff_entity(current, prefab_data, entity, is_root_of_instance)
    return overrides
def compute_all_overrides(entities: list[Entity]) -> list[dict]:
    if len(entities) <= 4:
        all_overrides = []
        for e in entities:
            all_overrides.extend(Prefab.compute_overrides(e))
            all_overrides.extend(Prefab.compute_all_overrides(e.children))
        return all_overrides
    def one(ent):
        out: list[dict] = []
        try:
            out.extend(Prefab.compute_overrides(ent))
        except Exception:
            pass
        try:
            out.extend(Prefab.compute_all_overrides(ent.children))
        except Exception:
            pass
        return out
    all_overrides = []
    with ThreadPoolExecutor(max_workers=min(8, len(entities))) as ex:
        for part in ex.map(one, entities):
            all_overrides.extend(part)
    return all_overrides
def _diff_entity(current: dict, prefab_data: dict, entity: Entity,
                 is_root: bool = False) -> list[dict]:
    overrides = []
    if current.get("name") != prefab_data.get("name"):
        overrides.append({
            "entity_id": entity.id,
            "entity_name": entity.name,
            "source_id": entity._prefab_source_id,
            "type": PrefabOverrideType.MODIFIED_PROPERTY.value,
            "property": "name",
            "old_value": prefab_data.get("name"),
            "new_value": current.get("name")
        })
    if current.get("active") != prefab_data.get("active"):
        overrides.append({
            "entity_id": entity.id,
            "entity_name": entity.name,
            "source_id": entity._prefab_source_id,
            "type": PrefabOverrideType.MODIFIED_PROPERTY.value,
            "property": "active",
            "old_value": prefab_data.get("active", True),
            "new_value": current.get("active", True)
        })
    if set(current.get("tags", [])) != set(prefab_data.get("tags", [])):
        overrides.append({
            "entity_id": entity.id,
            "entity_name": entity.name,
            "source_id": entity._prefab_source_id,
            "type": PrefabOverrideType.MODIFIED_PROPERTY.value,
            "property": "tags",
            "old_value": prefab_data.get("tags", []),
            "new_value": current.get("tags", [])
        })
    if current.get("layer") != prefab_data.get("layer"):
        overrides.append({
            "entity_id": entity.id,
            "entity_name": entity.name,
            "source_id": entity._prefab_source_id,
            "type": PrefabOverrideType.MODIFIED_PROPERTY.value,
            "property": "layer",
            "old_value": prefab_data.get("layer"),
            "new_value": current.get("layer")
        })
    cur_comps = {}
    for c in current.get("components", []):
        ct = c.get("type")
        key = c.get("_key", ct)
        cur_comps[key] = c
    snap_comps = {}
    for c in prefab_data.get("components", []):
        ct = c.get("type")
        key = c.get("_key", ct)
        snap_comps[key] = c
    snap_by_type = {}
    for key, c in snap_comps.items():
        ct = c.get("type")
        snap_by_type.setdefault(ct, []).append(c)
    for comp_type, snap_list in snap_by_type.items():
        matching_cur = [c for k, c in cur_comps.items() if c.get("type") == comp_type]
        for idx, snap_c in enumerate(snap_list):
            if idx < len(matching_cur):
                cur_c = matching_cur[idx]
                comp_overrides = Prefab._diff_component(cur_c, snap_c, entity, comp_type, is_root)
                overrides.extend(comp_overrides)
            else:
                overrides.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "source_id": entity._prefab_source_id,
                    "type": PrefabOverrideType.REMOVED_COMPONENT.value,
                    "component_type": comp_type,
                    "component_key": "",
                    "old_value": snap_c,
                    "new_value": None
                })
    for cur_key, cur_c in cur_comps.items():
        comp_type = cur_c.get("type")
        snap_count = len(snap_by_type.get(comp_type, []))
        cur_count = len([c for k, c in cur_comps.items() if c.get("type") == comp_type])
        if cur_count > snap_count:
            is_excess = False
            type_list = [c for k, c in sorted(cur_comps.items()) if c.get("type") == comp_type]
            if type_list.index(cur_c) >= snap_count:
                is_excess = True
            if is_excess:
                overrides.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "source_id": entity._prefab_source_id,
                    "type": PrefabOverrideType.ADDED_COMPONENT.value,
                    "component_type": comp_type,
                    "component_key": cur_key,
                    "old_value": None,
                    "new_value": cur_c
                })
    for snap_key, snap_c in snap_comps.items():
        if snap_key not in cur_comps:
            comp_type = snap_c.get("type")
            already_removed = any(
                o["type"] == PrefabOverrideType.REMOVED_COMPONENT.value
                and o["component_type"] == comp_type
                for o in overrides
            )
            if not already_removed:
                overrides.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "source_id": entity._prefab_source_id,
                    "type": PrefabOverrideType.REMOVED_COMPONENT.value,
                    "component_type": comp_type,
                    "component_key": snap_key,
                    "old_value": snap_c,
                    "new_value": None
                })
    cur_children = current.get("children", [])
    snap_children = prefab_data.get("children", [])
    snap_child_ids = {}
    for sc in snap_children:
        sc_id = sc.get("source_id", sc.get("id"))
        snap_child_ids[sc_id] = sc
    cur_child_ids = {}
    for child_ent in entity.children:
        sid = child_ent._prefab_source_id
        if sid:
            cur_child_ids[sid] = child_ent
    if snap_child_ids or cur_child_ids:
        for sc_id, sc in snap_child_ids.items():
            if sc_id not in cur_child_ids:
                overrides.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "source_id": entity._prefab_source_id,
                    "type": PrefabOverrideType.REMOVED_CHILD.value,
                    "child_source_id": sc_id,
                    "child_name": sc.get("name", "?"),
                    "old_value": sc,
                    "new_value": None
                })
        for child_ent in entity.children:
            if not child_ent._prefab_source_id or child_ent._prefab_source_id not in snap_child_ids:
                if not child_ent._prefab_guid:
                    serialized = child_ent.serialize()
                    serialized.pop("parent", None)
                    overrides.append({
                        "entity_id": entity.id,
                        "entity_name": entity.name,
                        "source_id": entity._prefab_source_id,
                        "type": PrefabOverrideType.ADDED_CHILD.value,
                        "child_id": child_ent.id,
                        "child_name": child_ent.name,
                        "old_value": None,
                        "new_value": serialized
                    })
    return overrides
def _diff_component(comp_cur: dict, comp_snap: dict, entity: Entity,
                    comp_type: str, is_root: bool) -> list[dict]:
    overrides = []
    all_keys = set(comp_cur.keys()) | set(comp_snap.keys())
    skip_keys = {"type", "_key"}
    for key in all_keys:
        if key in skip_keys:
            continue
        cur_val = comp_cur.get(key)
        snap_val = comp_snap.get(key)
        if cur_val != snap_val:
            if is_root and comp_type == "Transform" and key in _ROOT_TRANSFORM_SKIP_COMPARE:
                continue
            overrides.append({
                "entity_id": entity.id,
                "entity_name": entity.name,
                "source_id": entity._prefab_source_id,
                "type": PrefabOverrideType.MODIFIED_PROPERTY.value,
                "component_type": comp_type,
                "property": f"{comp_type}.{key}",
                "old_value": snap_val,
                "new_value": cur_val
            })
    if comp_cur.get("enabled") != comp_snap.get("enabled"):
        if not any(o.get("property") == f"{comp_type}.enabled" for o in overrides):
            overrides.append({
                "entity_id": entity.id,
                "entity_name": entity.name,
                "source_id": entity._prefab_source_id,
                "type": PrefabOverrideType.MODIFIED_PROPERTY.value,
                "component_type": comp_type,
                "property": f"{comp_type}.enabled",
                "old_value": comp_snap.get("enabled"),
                "new_value": comp_cur.get("enabled")
            })
    return overrides
def has_overrides(entities: list[Entity]) -> bool:
    return len(Prefab.compute_all_overrides(entities)) > 0
def apply_overrides(entity_root: Entity):
    from core.ecs.prefabp.library import PrefabLibrary
    prefab_path = PrefabLibrary.path_for_guid(entity_root._prefab_guid)
    if not prefab_path:
        Logger.warning("Cannot apply overrides: prefab asset not found.")
        return
    overrides = Prefab.compute_all_overrides([entity_root])
    prefab = Prefab.load(prefab_path)
    if not prefab:
        return
    roots_data = Prefab._apply_overrides_to_data(prefab.roots_data, overrides, entity_root, prefab)
    prefab.roots_data = roots_data
    prefab.save(prefab_path)
    PrefabLibrary.invalidate(prefab_path)
    Logger.info(f"Applied overrides to prefab: {prefab_path}")
def _apply_overrides_to_data(roots_data: list[dict], overrides: list[dict],
                              entity_root: Entity, prefab: Prefab) -> list[dict]:
    result = copy.deepcopy(roots_data)
    for ov in overrides:
        otype = ov["type"]
        source_id = ov.get("source_id")
        if otype == PrefabOverrideType.MODIFIED_PROPERTY.value:
            prop = ov["property"]
            if "." in prop:
                comp_type, prop_key = prop.split(".", 1)
            else:
                comp_type = None
                prop_key = prop
            def apply_prop(items):
                for item in items:
                    sid = item.get("source_id", item.get("id"))
                    if sid == source_id:
                        if comp_type:
                            for c in item.get("components", []):
                                if c.get("type") == comp_type:
                                    c[prop_key] = ov["new_value"]
                        else:
                            if prop_key == "name":
                                item[prop_key] = ov["new_value"]
                            elif prop_key in ("active", "tags", "layer"):
                                item[prop_key] = ov["new_value"]
                    apply_prop(item.get("children", []))
            apply_prop(result)
        elif otype == PrefabOverrideType.ADDED_COMPONENT.value:
            def add_comp(items):
                for item in items:
                    sid = item.get("source_id", item.get("id"))
                    if sid == source_id:
                        existing = [c for c in item.get("components", [])
                                    if c.get("type") == ov["component_type"]]
                        if not existing:
                            new_comp = copy.deepcopy(ov["new_value"])
                            new_comp.pop("_key", None)
                            item.setdefault("components", []).append(new_comp)
                    add_comp(item.get("children", []))
            add_comp(result)
        elif otype == PrefabOverrideType.REMOVED_COMPONENT.value:
            def rem_comp(items):
                for item in items:
                    sid = item.get("source_id", item.get("id"))
                    if sid == source_id:
                        item["components"] = [c for c in item.get("components", [])
                                              if not (c.get("type") == ov["component_type"]
                                                      and c.get("_key", c.get("type")) == ov.get("component_key", ""))]
                    rem_comp(item.get("children", []))
            rem_comp(result)
        elif otype == PrefabOverrideType.ADDED_CHILD.value:
            def add_child(items):
                for item in items:
                    sid = item.get("source_id", item.get("id"))
                    if sid == source_id:
                        child_data = copy.deepcopy(ov["new_value"])
                        child_data.pop("id", None)
                        child_data.pop("parent", None)
                        child_data["source_id"] = str(uuid.uuid4())
                        if "children" not in child_data:
                            child_data["children"] = []
                        item.setdefault("children", []).append(child_data)
                    add_child(item.get("children", []))
            add_child(result)
        elif otype == PrefabOverrideType.REMOVED_CHILD.value:
            def remove_child(items):
                for item in items:
                    sid = item.get("source_id", item.get("id"))
                    if sid == source_id:
                        child_sid = ov.get("child_source_id")
                        item["children"] = [c for c in item.get("children", [])
                                            if c.get("source_id", c.get("id")) != child_sid]
                    remove_child(item.get("children", []))
            remove_child(result)
    return result
def revert_instance(root_entity: Entity, registry: ComponentRegistry):
    from core.ecs.prefabp.library import PrefabLibrary
    prefab_path = PrefabLibrary.path_for_guid(root_entity._prefab_guid)
    if not prefab_path:
        Logger.warning("Cannot revert: prefab asset not found.")
        return
    prefab = Prefab.load(prefab_path)
    if not prefab:
        return
    def revert_subtree(entity):
        source_id = entity._prefab_source_id
        source_data = Prefab._find_source_data(prefab.roots_data, source_id) if source_id else None
        if source_data:
            entity._name = source_data.get("name", entity._name)
            entity._active = source_data.get("active", True)
            comp_types_to_remove = list(entity._components.keys())
            for ct_key in comp_types_to_remove:
                comp = entity._components[ct_key]
                comp.on_destroy()
            entity._components.clear()
            entity._type_map.clear()
            entity._type_name_map.clear()
            entity._update_list.clear()
            entity._fixed_update_list.clear()
            for cd in source_data.get("components", []):
                cd_copy = copy.deepcopy(cd)
                cd_copy.pop("_key", None)
                ctype = cd_copy.get("type")
                comp_cls = registry.get(ctype)
                if comp_cls:
                    comp = comp_cls.deserialize(cd_copy)
                    entity.add_component(comp)
        source_children = source_data.get("children", []) if source_data else []
        source_child_ids = {}
        for sc in source_children:
            sc_id = sc.get("source_id", sc.get("id"))
            source_child_ids[sc_id] = sc
        for child in list(entity.children):
            if child._prefab_source_id and child._prefab_source_id in source_child_ids:
                revert_subtree(child)
            else:
                entity._scene.remove_entity(child.id)
        for sc_id, sc in source_child_ids.items():
            found = any(c._prefab_source_id == sc_id for c in entity.children)
            if not found:
                cd = copy.deepcopy(sc)
                cd["id"] = str(uuid.uuid4())
                cd.pop("parent", None)
                cd.pop("_key", None)
                child = Entity.deserialize(cd, registry)
                if not child._prefab_guid:
                    child._prefab_guid = root_entity._prefab_guid
                    child._prefab_source_id = sc_id
                entity._scene.add_entity(child)
                child.set_parent(entity)
                prefab_guid = child._prefab_guid or root_entity._prefab_guid
                Prefab._restore_source_children(child, sc.get("children", []), registry,
                                                 prefab_guid)
    revert_subtree(root_entity)
def _restore_source_children(parent_entity, source_children, registry, prefab_guid):
    for sc in source_children:
        sc_id = sc.get("source_id", sc.get("id"))
        cd = copy.deepcopy(sc)
        cd["id"] = str(uuid.uuid4())
        cd.pop("parent", None)
        child = Entity.deserialize(cd, registry)
        if not child._prefab_guid:
            child._prefab_guid = prefab_guid
            child._prefab_source_id = sc_id
        parent_entity._scene.add_entity(child)
        child.set_parent(parent_entity)
        child_prefab_guid = child._prefab_guid or prefab_guid
        Prefab._restore_source_children(child, sc.get("children", []), registry, child_prefab_guid)
Prefab.compute_overrides = staticmethod(compute_overrides)
Prefab.compute_all_overrides = staticmethod(compute_all_overrides)
Prefab._diff_entity = staticmethod(_diff_entity)
Prefab._diff_component = staticmethod(_diff_component)
Prefab.has_overrides = staticmethod(has_overrides)
Prefab.apply_overrides = staticmethod(apply_overrides)
Prefab._apply_overrides_to_data = staticmethod(_apply_overrides_to_data)
Prefab.revert_instance = staticmethod(revert_instance)
Prefab._restore_source_children = staticmethod(_restore_source_children)
