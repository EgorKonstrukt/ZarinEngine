from __future__ import annotations
import json
import os
import uuid
import copy
from typing import Optional, Any
from core.ecs import Scene, Entity, ComponentRegistry
from core.logger import Logger


class Prefab:
    def __init__(self, name: str = "Prefab", guid: Optional[str] = None):
        self.name: str = name
        self.guid: str = guid or str(uuid.uuid4())
        self.roots_data: list[dict] = []

    def capture(self, entities: list[Entity]):
        self.roots_data = [self._capture_entity_data(e) for e in entities]

    def _capture_entity_data(self, entity: Entity) -> dict:
        data = entity.serialize()
        data.pop("parent", None)
        data.pop("prefab_guid", None)
        data.pop("prefab_data", None)
        children = []
        for child in entity.children:
            children.append(self._capture_entity_data(child))
        if children:
            data["children"] = children
        return data

    def instantiate(self, scene: Scene, registry: ComponentRegistry,
                    parent: Optional[Entity] = None) -> list[Entity]:
        if not self.roots_data:
            Logger.warning("Prefab has no root data.")
            return []
        spawned: list[Entity] = []
        for rd in self.roots_data:
            data = copy.deepcopy(rd)
            self._remap_ids(data)
            e = Entity.deserialize(data, registry)
            e._prefab_guid = self.guid
            e._prefab_data = self._build_snapshot(e)
            scene.add_entity(e)
            if parent:
                e.set_parent(parent)
            spawned.append(e)
            self._restore_children(e, data, scene, registry)
        return spawned

    def _restore_children(self, parent_entity: Entity, data: dict,
                          scene: Scene, registry: ComponentRegistry):
        for cd in data.get("children", []):
            self._remap_ids(cd)
            child = Entity.deserialize(cd, registry)
            child._prefab_guid = self.guid
            child._prefab_data = self._build_snapshot(child)
            scene.add_entity(child)
            child.set_parent(parent_entity)
            self._restore_children(child, cd, scene, registry)

    def _remap_ids(self, data: dict):
        data["id"] = str(uuid.uuid4())
        data["parent"] = None
        for child in data.get("children", []):
            self._remap_ids(child)

    def _build_snapshot(self, entity: Entity) -> dict:
        return entity.serialize()

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "guid": self.guid,
                "name": self.name,
                "roots": self.roots_data
            }, f, indent=2)
        Logger.info(f"Prefab saved: {path}")

    @classmethod
    def load(cls, path: str) -> Optional[Prefab]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            p = cls(data.get("name", "Prefab"), data.get("guid"))
            roots = data.get("roots")
            if roots is not None:
                p.roots_data = roots
            elif "entity" in data:
                p.roots_data = [data["entity"]]
            elif "entities" in data:
                p.roots_data = list(data["entities"].values())
            return p
        except Exception as e:
            Logger.error(f"Failed to load prefab '{path}': {e}", exc=e)
            return None

    @staticmethod
    def compute_overrides(entity: Entity) -> list[dict]:
        if not entity._prefab_data:
            return []
        current = entity.serialize()
        snapshot = entity._prefab_data
        overrides = []
        for key in ("name", "active", "layer"):
            if current.get(key) != snapshot.get(key):
                overrides.append({
                    "entity_id": entity.id,
                    "property": f"_{key}",
                    "old_value": snapshot.get(key),
                    "new_value": current.get(key)
                })
        if set(current.get("tags", [])) != set(snapshot.get("tags", [])):
            overrides.append({
                "entity_id": entity.id,
                "property": "_tags",
                "old_value": snapshot.get("tags", []),
                "new_value": current.get("tags", [])
            })
        cur_comps = {c.get("type"): c for c in current.get("components", [])}
        snap_comps = {c.get("type"): c for c in snapshot.get("components", [])}
        for comp_type, snap_c in snap_comps.items():
            cur_c = cur_comps.get(comp_type)
            if cur_c is None:
                overrides.append({
                    "entity_id": entity.id,
                    "property": f"component:{comp_type}",
                    "old_value": snap_c,
                    "new_value": None,
                    "type": "removed"
                })
            elif cur_c != snap_c:
                overrides.append({
                    "entity_id": entity.id,
                    "property": f"component:{comp_type}",
                    "old_value": snap_c,
                    "new_value": cur_c,
                    "type": "modified"
                })
        for comp_type, cur_c in cur_comps.items():
            if comp_type not in snap_comps:
                overrides.append({
                    "entity_id": entity.id,
                    "property": f"component:{comp_type}",
                    "old_value": None,
                    "new_value": cur_c,
                    "type": "added"
                })
        return overrides

    @staticmethod
    def compute_all_overrides(entities: list[Entity]) -> list[dict]:
        all_overrides = []
        for e in entities:
            all_overrides.extend(Prefab.compute_overrides(e))
            all_overrides.extend(Prefab.compute_all_overrides(e.children))
        return all_overrides

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
    def has_overrides(entities: list[Entity]) -> bool:
        return len(Prefab.compute_all_overrides(entities)) > 0


class PrefabLibrary:
    _prefabs: dict[str, Prefab] = {}
    _guids: dict[str, str] = {}

    @classmethod
    def register(cls, path: str, prefab: Prefab):
        cls._prefabs[path] = prefab
        cls._guids[prefab.guid] = path

    @classmethod
    def load(cls, path: str) -> Optional[Prefab]:
        if not os.path.exists(path):
            return None
        if path in cls._prefabs:
            return cls._prefabs[path]
        p = Prefab.load(path)
        if p:
            cls._prefabs[path] = p
            cls._guids[p.guid] = path
        return p

    @classmethod
    def get_all(cls) -> dict[str, Prefab]:
        return dict(cls._prefabs)

    @classmethod
    def path_for_guid(cls, guid: str) -> Optional[str]:
        return cls._guids.get(guid)

    @classmethod
    def invalidate(cls, path: str):
        p = cls._prefabs.pop(path, None)
        if p:
            cls._guids.pop(p.guid, None)

    @classmethod
    def clear(cls):
        cls._prefabs.clear()
        cls._guids.clear()
