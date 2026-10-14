# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from .history import Command
class SetComponentCommand(Command):
    def __init__(self, entity, component_type, prop_name: str, old_value, new_value):
        self._entity_id = entity.id
        self._scene = getattr(entity, '_scene', None)
        self._component_type = component_type
        self._prop = prop_name
        self._old = old_value
        self._new = new_value
    def _get_entity(self):
        if self._scene:
            e = self._scene.get_entity(self._entity_id)
            if e:
                return e
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng and eng.scene:
            return eng.scene.get_entity(self._entity_id)
        return None
    def execute(self):
        e = self._get_entity()
        if e:
            comp = e.get_component(self._component_type)
            if comp and hasattr(comp, self._prop):
                setattr(comp, self._prop, self._new)
    def undo(self):
        e = self._get_entity()
        if e:
            comp = e.get_component(self._component_type)
            if comp and hasattr(comp, self._prop):
                setattr(comp, self._prop, self._old)
    @property
    def description(self):
        e = self._get_entity()
        ename = getattr(e, "name", "") or getattr(e, "id", "?")
        return f"{ename}: {self._component_type.__name__}.{self._prop}"
class AddComponentCommand(Command):
    def __init__(self, entity, component_cls, component_data: dict = None, key: str = None):
        self._entity = entity
        self._component_cls = component_cls
        self._component_data = component_data
        self._key = key
        self._added_key: Optional[str] = None
    def execute(self):
        comp = self._component_cls()
        if self._component_data:
            for k, v in self._component_data.items():
                if hasattr(comp, k):
                    setattr(comp, k, v)
        self._entity.add_component(comp, key=self._key)
        for k, c in self._entity._components.items():
            if c is comp:
                self._added_key = k
                break
    def undo(self):
        if self._added_key:
            self._entity.remove_component_by_key(self._added_key)
        else:
            self._entity.remove_component(self._component_cls)
        self._component_data = None
    @property
    def description(self): return f"Add {self._component_cls.__name__}"
class RemoveComponentCommand(Command):
    def __init__(self, entity, component_cls, component_key: str = None):
        self._entity = entity
        self._component_cls = component_cls
        self._component_key = component_key
        self._component_data = None
        self._removed_key: Optional[str] = None
    def execute(self):
        if self._component_key:
            comp = self._entity._components.get(self._component_key)
            if comp:
                self._component_data = {k: getattr(comp, k) for k in vars(comp) if not k.startswith("_")}
                self._removed_key = self._component_key
                self._entity.remove_component_by_key(self._component_key)
        else:
            comp = self._entity.get_component(self._component_cls)
            if comp:
                self._component_data = {k: getattr(comp, k) for k in vars(comp) if not k.startswith("_")}
                for k, c in list(self._entity._components.items()):
                    if c is comp:
                        self._removed_key = k
                        break
                self._entity.remove_component(self._component_cls)
    def undo(self):
        if self._component_data is not None:
            comp = self._component_cls()
            for k, v in self._component_data.items():
                if hasattr(comp, k):
                    setattr(comp, k, v)
            self._entity.add_component(comp, key=self._removed_key)
    @property
    def description(self):
        base = f"Remove {self._component_cls.__name__}"
        if self._component_key:
            base += f" ({self._component_key})"
        return base
class MoveComponentCommand(Command):
    def __init__(self, source_entity, target_entity, component_key, component_cls, component_data: dict):
        self._source = source_entity
        self._target = target_entity
        self._component_key = component_key
        self._component_cls = component_cls
        self._component_data = component_data
        self._target_key = None
    def execute(self):
        if self._component_key:
            self._source.remove_component_by_key(self._component_key)
        else:
            self._source.remove_component(self._component_cls)
        new_comp = self._component_cls.deserialize(self._component_data)
        key_to_use = self._component_key if not getattr(self._component_cls, '_allow_multiple', False) else None
        self._target.add_component(new_comp, key=key_to_use)
        for k, c in self._target._components.items():
            if c is new_comp:
                self._target_key = k
                break
    def undo(self):
        if self._target_key:
            self._target.remove_component_by_key(self._target_key)
        new_comp = self._component_cls.deserialize(self._component_data)
        self._source.add_component(new_comp, key=self._component_key)
        self._target_key = None
    @property
    def description(self):
        return f"Move {self._component_cls.__name__}"
class CopyComponentCommand(Command):
    def __init__(self, target_entity, component_cls, component_data: dict, source_key: str = None):
        self._target = target_entity
        self._component_cls = component_cls
        self._component_data = component_data
        self._source_key = source_key
        self._target_key = None
    def execute(self):
        new_comp = self._component_cls.deserialize(self._component_data)
        key_to_use = self._source_key if not getattr(self._component_cls, '_allow_multiple', False) else None
        self._target.add_component(new_comp, key=key_to_use)
        for k, c in self._target._components.items():
            if c is new_comp:
                self._target_key = k
                break
    def undo(self):
        if self._target_key:
            self._target.remove_component_by_key(self._target_key)
    @property
    def description(self):
        return f"Copy {self._component_cls.__name__}"
