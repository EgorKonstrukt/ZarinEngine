# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import copy
import json
import os
import uuid
from enum import Enum
from typing import Optional, Any
from core.ecs import Scene, Entity, ComponentRegistry
from core.foundation.logger import Logger


class PrefabOverrideType(Enum):
    MODIFIED_PROPERTY = "modified_property"
    ADDED_COMPONENT = "added_component"
    REMOVED_COMPONENT = "removed_component"
    ADDED_CHILD = "added_child"
    REMOVED_CHILD = "removed_child"


ROOT_TRANSFORM_EXCLUDED = frozenset({"local_position", "local_rotation"})
_ROOT_TRANSFORM_SKIP_COMPARE = frozenset({"local_position", "local_rotation", "position", "rotation"})


class Prefab:
    TRANSFORM_PASSTHROUGH = frozenset({"local_position", "local_rotation"})

    def __init__(self, name: str = "Prefab", guid: Optional[str] = None,
                 base_guid: Optional[str] = None, menu_path: Optional[str] = None):
        self.name: str = name
        self.guid: str = guid or str(uuid.uuid4())
        self.roots_data: list[dict] = []
        self.base_guid: Optional[str] = base_guid
        self.menu_path: Optional[str] = menu_path

    @property
    def is_variant(self) -> bool:
        return self.base_guid is not None

    @classmethod
    def create_via_code(cls, name: str, build=None, menu_path: Optional[str] = None,
                        guid: Optional[str] = None) -> Prefab:
        pref = cls(name, guid=guid, menu_path=menu_path)
        if build is not None:
            result = build(pref)
            if isinstance(result, list):
                pref.roots_data = result
        return pref

    def instantiate_plain(self, scene: Scene, registry: ComponentRegistry,
                          parent: Optional[Entity] = None) -> list[Entity]:
        spawned = self.instantiate(scene, registry, parent)
        for root in spawned:
            Prefab.unpack(root)
        return spawned

    def capture(self, entities: list[Entity]):
        self.roots_data = []
        for e in entities:
            data = self._capture_entity_data(e)
            data.pop("prefab_guid", None)
            data.pop("prefab_source_id", None)
            self.roots_data.append(data)

    def _capture_entity_data(self, entity: Entity) -> dict:
        data = entity.serialize()
        old_id = data.get("id")
        data["source_id"] = old_id
        data.pop("parent", None)
        data["children"] = []
        for child in entity.children:
            child_data = self._capture_entity_data(child)
            data["children"].append(child_data)
        return data

    def instantiate(self, scene: Scene, registry: ComponentRegistry,
                    parent: Optional[Entity] = None) -> list[Entity]:
        if not self.roots_data:
            Logger.warning("Prefab has no root data.")
            return []
        spawned: list[Entity] = []
        for rd in self.roots_data:
            data = copy.deepcopy(rd)
            id_map: dict[str, str] = {}
            self._remap_ids(data, id_map)
            source_id = rd.get("source_id", rd.get("id"))
            children_data = data.pop("children", [])
            e = Entity.deserialize(data, registry)
            e._prefab_guid = self.guid
            e._prefab_source_id = source_id
            scene.add_entity(e)
            if parent:
                e.set_parent(parent)
            spawned.append(e)
            self._instantiate_children(e, children_data, id_map, scene, registry)
        return spawned

    def _instantiate_children(self, parent_entity: Entity, children_data: list[dict],
                               id_map: dict[str, str], scene: Scene,
                               registry: ComponentRegistry):
        for cd in children_data:
            child_source_id = cd.get("source_id", cd.get("id"))
            sub_children = cd.pop("children", [])
            child_id = cd.get("id")
            if child_id in id_map:
                cd["id"] = id_map[child_id]
            e = Entity.deserialize(cd, registry)
            nested_prefab_guid = cd.get("prefab_guid")
            if nested_prefab_guid:
                e._prefab_guid = nested_prefab_guid
            else:
                e._prefab_guid = self.guid
            e._prefab_source_id = child_source_id
            scene.add_entity(e)
            e.set_parent(parent_entity)
            self._instantiate_children(e, sub_children, id_map, scene, registry)

    def _remap_ids(self, data: dict, id_map: dict[str, str]):
        old_id = data.get("id")
        new_id = str(uuid.uuid4())
        if old_id:
            id_map[old_id] = new_id
        data["id"] = new_id
        for child in data.get("children", []):
            self._remap_ids(child, id_map)

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        roots = self._serialize_roots(self.roots_data)
        for root in roots:
            root.pop("prefab_guid", None)
            root.pop("prefab_source_id", None)
        self._relativize_roots_for_save(roots)
        out = {
            "guid": self.guid,
            "name": self.name,
            "roots": roots
        }
        if self.base_guid:
            out["base_guid"] = self.base_guid
        if self.menu_path:
            out["menu_path"] = self.menu_path
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        Logger.info(f"Prefab saved: {path}")

    def _serialize_roots(self, roots: list[dict]) -> list[dict]:
        result = []
        for root in roots:
            data = copy.deepcopy(root)
            data.pop("parent", None)
            if "id" in data and "source_id" not in data:
                data["source_id"] = data.pop("id")
            for comp in data.get("components", []):
                comp.pop("_key", None)
            if "children" in data:
                data["children"] = self._serialize_roots(data["children"])
            result.append(data)
        return result

    @staticmethod
    def _relativize_roots_for_save(roots: list[dict]):
        root = None
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            root = eng.project_root if eng and getattr(eng, "project_root", None) else None
        except Exception:
            pass
        if not root:
            return

        def walk(items):
            for item in items:
                for comp in item.get("components", []):
                    Engine._relativize_component_paths(comp, root)
                walk(item.get("children", []))
        walk(roots)

    def _resolve_roots_for_load(self):
        root = None
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            root = eng.project_root if eng and getattr(eng, "project_root", None) else None
        except Exception:
            pass
        if not root:
            return

        def walk(items):
            for item in items:
                for comp in item.get("components", []):
                    Engine._resolve_component_paths(comp, root)
                walk(item.get("children", []))
        walk(self.roots_data)

    @classmethod
    def load(cls, path: str) -> Optional[Prefab]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            p = cls(data.get("name", "Prefab"), data.get("guid"),
                    data.get("base_guid"), data.get("menu_path"))
            roots = data.get("roots")
            if roots is not None:
                p.roots_data = roots
            elif "entity" in data:
                p.roots_data = [data["entity"]]
            elif "entities" in data:
                p.roots_data = list(data["entities"].values())
            p._resolve_roots_for_load()
            return p
        except Exception as e:
            Logger.error(f"Failed to load prefab '{path}': {e}", exc=e)
            return None

    @staticmethod
    def _resolve_prefab_for_entity(entity: Entity) -> Optional[Prefab]:
        from core.ecs.prefabp.library import PrefabLibrary
        guid = entity._prefab_guid
        if not guid:
            return None
        path = PrefabLibrary.path_for_guid(guid)
        if not path:
            return None
        prefab = PrefabLibrary.load(path)
        if prefab is None:
            return None
        if prefab.is_variant:
            return Prefab._resolve_variant_data(prefab, entity)
        return prefab

    @staticmethod
    def _resolve_variant_data(variant: Prefab, entity: Entity) -> Optional[Prefab]:
        from core.ecs.prefabp.library import PrefabLibrary
        chain = []
        current = variant
        while current:
            chain.append(current)
            if not current.base_guid:
                break
            base_path = PrefabLibrary.path_for_guid(current.base_guid)
            if not base_path:
                break
            base = PrefabLibrary.load(base_path)
            if base is None:
                break
            current = base
        if not chain:
            return None
        resolved = Prefab(variant.name, variant.guid, variant.base_guid)
        resolved.roots_data = copy.deepcopy(chain[-1].roots_data)
        for layer in reversed(chain[:-1]):
            resolved.roots_data = Prefab._merge_overrides(resolved.roots_data, layer.roots_data)
        return resolved

    @staticmethod
    def _merge_overrides(base_roots: list[dict], override_roots: list[dict]) -> list[dict]:
        merged = copy.deepcopy(base_roots)
        for ov_root in override_roots:
            ov_source_id = ov_root.get("source_id", ov_root.get("id"))
            found = False
            for base in merged:
                base_sid = base.get("source_id", base.get("id"))
                if base_sid == ov_source_id:
                    Prefab._merge_entity_data(base, ov_root)
                    found = True
                    break
            if not found:
                merged.append(copy.deepcopy(ov_root))
        return merged

    @staticmethod
    def _merge_entity_data(base: dict, override: dict):
        if override.get("name") != base.get("name"):
            base["name"] = override["name"]
        if override.get("active") != base.get("active"):
            base["active"] = override.get("active", True)
        ov_comps = {c.get("type"): c for c in override.get("components", [])}
        base_comps = {c.get("type"): c for c in base.get("components", [])}
        for ctype, ov_c in ov_comps.items():
            if ctype in base_comps:
                base_c = base_comps[ctype]
                for k, v in ov_c.items():
                    if k not in ("type", "enabled", "_key"):
                        base_c[k] = v
            else:
                base.setdefault("components", []).append(copy.deepcopy(ov_c))
        for ctype in list(base_comps.keys()):
            if ctype not in ov_comps:
                base["components"] = [c for c in base.get("components", [])
                                      if c.get("type") != ctype]
        ov_child_map = {}
        for c in override.get("children", []):
            sid = c.get("source_id", c.get("id"))
            ov_child_map[sid] = c
        base_child_map = {}
        for c in base.get("children", []):
            sid = c.get("source_id", c.get("id"))
            base_child_map[sid] = c
        for sid, ov_c in ov_child_map.items():
            if sid in base_child_map:
                Prefab._merge_entity_data(base_child_map[sid], ov_c)
            else:
                base.setdefault("children", []).append(copy.deepcopy(ov_c))
        for sid in list(base_child_map.keys()):
            if sid not in ov_child_map:
                base["children"] = [c for c in base.get("children", [])
                                    if c.get("source_id", c.get("id")) != sid]

    @staticmethod
    def _is_root_of_instance(entity: Entity) -> bool:
        if not entity._prefab_guid:
            return False
        p = entity._parent
        while p:
            if p._prefab_guid == entity._prefab_guid:
                return False
            p = p._parent
        return True

    @staticmethod
    def _find_source_data(roots_data: list[dict], source_id: str) -> Optional[dict]:
        def walk(items):
            for item in items:
                sid = item.get("source_id") or item.get("id")
                if sid == source_id:
                    return item
                found = walk(item.get("children", []))
                if found:
                    return found
            return None
        return walk(roots_data)

    @staticmethod
    def get_prefab_roots(instances: list[Entity]) -> list[Entity]:
        roots = []
        for e in instances:
            if not e.is_prefab_instance:
                continue
            p = e._parent
            while p and p.is_prefab_instance and p._prefab_guid == e._prefab_guid:
                p = p._parent
            if p is None or not p.is_prefab_instance or p._prefab_guid != e._prefab_guid:
                roots.append(e)
        return roots

    @staticmethod
    def unpack(entity_root: Entity):
        def walk(e):
            e._prefab_guid = None
            e._prefab_source_id = None
            for c in e.children:
                walk(c)
        walk(entity_root)

    @staticmethod
    def create_variant(base_prefab: Prefab, name: str, guid: Optional[str] = None) -> Prefab:
        variant = Prefab(name, guid, base_guid=base_prefab.guid)
        variant.roots_data = copy.deepcopy(base_prefab.roots_data)
        return variant

    @staticmethod
    def get_source(entity) -> Optional[str]:
        if isinstance(entity, Prefab):
            return entity.base_guid
        return entity._prefab_guid

    @staticmethod
    def get_original_source(entity, library=None) -> Optional[str]:
        if isinstance(entity, Prefab):
            p = entity
            while p.base_guid:
                base = None
                for path, cached in (library._prefabs.items() if library else {}).items():
                    if cached.guid == p.base_guid:
                        base = cached
                        break
                if base is None:
                    break
                p = base
            return p.guid
        return entity._prefab_guid
