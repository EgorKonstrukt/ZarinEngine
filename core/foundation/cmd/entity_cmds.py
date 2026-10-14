# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from core.ecs import Entity, Scene
from .history import Command
class CreateEntityCommand(Command):
    def __init__(self, scene: Scene, name: str = "Entity"):
        self._scene = scene
        self._name = name
        self._entity_id: Optional[str] = None
        self._entity_data: Optional[dict] = None
    def execute(self):
        from core.ecs import Entity
        e = self._scene.create_entity(self._name)
        self._entity_id = e.id
    def undo(self):
        if self._entity_id is not None:
            e = self._scene.get_entity(self._entity_id)
            if e:
                self._entity_data = e.serialize()
            self._scene.remove_entity(self._entity_id)
    def redo(self):
        if self._entity_data is not None:
            from core.engine.eng import Engine
            from core.ecs import Entity
            reg = Engine.instance()._component_registry
            e = Entity.deserialize(self._entity_data, reg)
            self._scene.add_entity(e)
            self._entity_id = e.id
        else:
            self.execute()
    @property
    def description(self): return f"Create '{self._name}'"
class DeleteEntityCommand(Command):
    def __init__(self, scene: Scene, entity_id: str):
        self._scene = scene
        self._entity_id = entity_id
        self._entity_data: Optional[dict] = None
    def execute(self):
        e = self._scene.get_entity(self._entity_id)
        if e:
            self._entity_data = e.serialize()
            self._scene.remove_entity(self._entity_id)
    def undo(self):
        if self._entity_data:
            from core.engine.eng import Engine
            from core.ecs import Entity
            reg = Engine.instance()._component_registry
            e = Entity.deserialize(self._entity_data, reg)
            self._scene.add_entity(e)
    @property
    def description(self): return f"Delete Entity {chr(35)}{self._entity_id}"
class InstantiatePrefabCommand(Command):
    def __init__(self, scene, prefab, registry, parent=None, position=None):
        self._scene = scene
        self._prefab = prefab
        self._registry = registry
        self._parent = parent
        self._position = position
        self._spawned_ids: list[str] = []
    def execute(self):
        spawned = self._prefab.instantiate(self._scene, self._registry, self._parent)
        self._spawned_ids = [e.id for e in spawned]
    def undo(self):
        for eid in self._spawned_ids:
            e = self._scene.get_entity(eid)
            if e:
                self._scene.remove_entity(eid)
        self._spawned_ids.clear()
    def redo(self):
        self.execute()
    @property
    def description(self): return f"Instantiate '{self._prefab.name}'"
class CreateSystemPrefabCommand(Command):
    def __init__(self, scene, menu_path: str, parent_id: Optional[str] = None):
        self._scene = scene
        self._menu_path = menu_path
        self._parent_id = parent_id
        self._spawned_ids: list[str] = []
        self._spawned_data: list[dict] = []
    def execute(self):
        from core.prefabs.registry import create_system_prefab
        parent = self._scene.get_entity(self._parent_id) if self._parent_id else None
        spawned = create_system_prefab(self._menu_path, self._scene, parent)
        self._spawned_ids = [e.id for e in spawned]
        self._spawned_data = [e.serialize() for e in spawned]
    def undo(self):
        for eid in self._spawned_ids:
            e = self._scene.get_entity(eid)
            if e:
                self._scene.remove_entity(eid)
    def redo(self):
        if self._spawned_data:
            from core.engine.eng import Engine
            from core.ecs import Entity
            try:
                reg = Engine.instance()._component_registry
            except Exception:
                reg = None
            if reg is None:
                self.execute()
                return
            self._spawned_ids = []
            for data in self._spawned_data:
                import copy
                payload = copy.deepcopy(data)
                parent_id = payload.get("parent")
                payload.pop("parent", None)
                e = Entity.deserialize(payload, reg)
                self._scene.add_entity(e)
                if parent_id:
                    parent_ent = self._scene.get_entity(parent_id)
                    if parent_ent is not None:
                        e.set_parent(parent_ent)
                elif self._parent_id:
                    parent_ent = self._scene.get_entity(self._parent_id)
                    if parent_ent is not None:
                        e.set_parent(parent_ent)
                self._spawned_ids.append(e.id)
        else:
            self.execute()
    @property
    def description(self): return f"Create '{self._menu_path}'"
class RevertPrefabInstanceCommand(Command):
    def __init__(self, scene, root_entities: list, registry=None):
        self._scene = scene
        self._roots = root_entities
        self._registry = registry
        self._old_data: list[tuple[str, dict]] = []
    def _collect(self, entity) -> list[tuple[str, dict]]:
        items = [(entity.id, entity.serialize())]
        for c in entity.children:
            items.extend(self._collect(c))
        return items
    def execute(self):
        from core.ecs.prefabp import Prefab
        if self._registry is None:
            from core.engine.eng import Engine
            self._registry = Engine.instance()._component_registry
        self._old_data.clear()
        for root in self._roots:
            self._old_data.extend(self._collect(root))
        for root in self._roots:
            Prefab.revert_instance(root, self._registry)
    def undo(self):
        for eid, data in self._old_data:
            e = self._scene.get_entity(eid)
            if e:
                for ct in list(e._components.keys()):
                    c = e._components[ct]
                    c.on_destroy()
                e._components.clear()
                for cd in data.get("components", []):
                    ctype = cd.get("type")
                    comp_cls = self._registry.get(ctype)
                    if comp_cls:
                        comp = comp_cls.deserialize(cd)
                        e.add_component(comp)
                e._name = data.get("name", e._name)
                e._active = data.get("active", e._active)
                e._tags = set(data.get("tags", []))
                e._layer = data.get("layer", e._layer)
    @property
    def description(self): return "Revert Prefab"
class UnpackPrefabCommand(Command):
    def __init__(self, scene, root_entities: list):
        self._scene = scene
        self._roots = root_entities
        self._old_links: list[tuple[str, Optional[str], Optional[str]]] = []
    def execute(self):
        from core.ecs.prefabp import Prefab
        self._old_links.clear()
        def unpack(e):
            self._old_links.append((e.id, e._prefab_guid, e._prefab_source_id))
            Prefab.unpack(e)
        for root in self._roots:
            unpack(root)
    def undo(self):
        for eid, guid, source_id in self._old_links:
            e = self._scene.get_entity(eid)
            if e:
                e._prefab_guid = guid
                e._prefab_source_id = source_id
    @property
    def description(self): return "Unpack Prefab"
class ApplyPrefabOverridesCommand(Command):
    def __init__(self, scene, root_entities: list, registry=None):
        self._scene = scene
        self._roots = root_entities
        self._registry = registry
    def execute(self):
        from core.ecs.prefabp import Prefab
        if self._registry is None:
            from core.engine.eng import Engine
            self._registry = Engine.instance()._component_registry
        for root in self._roots:
            Prefab.apply_overrides(root)
    def undo(self):
        pass
    @property
    def description(self): return "Apply Prefab Overrides"
class PasteEntitiesCommand(Command):
    def __init__(self, scene, clipboard_data: list[dict], registry):
        self._scene = scene
        self._clipboard_data = clipboard_data
        self._registry = registry
        self._spawned_ids: list[str] = []
        self._entity_datas: list[dict] = []
        self._entity_id: Optional[str] = None
    @property
    def spawned_ids(self) -> list[str]:
        return list(self._spawned_ids)
    def execute(self):
        self._spawned_ids.clear()
        self._entity_datas.clear()
        self._entity_id = None
        for e in self._scene.paste_entities(self._clipboard_data, self._registry):
            self._spawned_ids.append(e.id)
        if self._spawned_ids:
            self._entity_id = self._spawned_ids[0]
    def undo(self):
        for eid in self._spawned_ids:
            e = self._scene.get_entity(eid)
            if e:
                self._scene.remove_entity(eid)
    def redo(self):
        self.execute()
    @property
    def description(self):
        n = len(self._clipboard_data)
        return f"Paste {n} entit{'y' if n == 1 else 'ies'}"
