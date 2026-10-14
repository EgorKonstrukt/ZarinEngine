# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import uuid
from typing import Optional, Type, TypeVar
from .component import Component
from .query import _TRANSFORM_NAME, _UNSET
from .registry import ComponentRegistry
T = TypeVar("T", bound="Component")

class Entity:
    __slots__ = ('_id', '_name', '_type_map', '_type_name_map', '_components', '_update_list', '_fixed_update_list', '_active', '_parent', '_children', '_tags', '_layer', '_scene', '_prefab_guid', '_prefab_source_id', '_transform_type', '_transform', '_embed_resources', '_locked', '_system')
    def __init__(self, name: str = "Entity", eid: Optional[str] = None, prefab_guid: Optional[str] = None):
        self._id: str = eid or str(uuid.uuid4()); self._name: str = name
        self._type_map: dict[type, list[Component]] = {}
        self._type_name_map: dict[str, type] = {}
        self._components: dict[str, Component] = {}
        self._update_list: list[Component] = []; self._fixed_update_list: list[Component] = []
        self._active: bool = True
        self._parent: Optional[Entity] = None; self._children: list[Entity] = []
        self._tags: set[str] = set(); self._layer: int = 0
        self._scene: Optional[Scene] = None
        self._prefab_guid: Optional[str] = prefab_guid; self._prefab_source_id: Optional[str] = None
        self._transform_type: Optional[type] = None; self._transform: Optional[Component] = None
        self._embed_resources: bool = False; self._locked: bool = False; self._system: bool = False
    def _get_transform_type(self):
        tt = self._transform_type
        if tt is not None:
            return tt
        tm = self._type_map
        for t in tm:
            if t.__name__ == _TRANSFORM_NAME:
                self._transform_type = t
                return t
        from core.components.transform import Transform
        self._transform_type = Transform
        return Transform
    @property
    def transform(self):
        tr = self._transform
        if tr is not None:
            return tr
        tt = self._transform_type
        if tt is not None:
            clist = self._type_map.get(tt)
            if clist:
                self._transform = clist[0]
                return clist[0]
        tm = self._type_map
        for t in tm:
            if t.__name__ == _TRANSFORM_NAME:
                self._transform_type = t
                clist = tm.get(t)
                if clist:
                    self._transform = clist[0]
                    return clist[0]
                return None
        return None
    @property
    def id(self) -> str: return self._id
    @property
    def name(self) -> str: return self._name
    @name.setter
    def name(self, v: str): self._name = v
    @property
    def active(self) -> bool: return self._active
    @active.setter
    def active(self, v: bool):
        if self._active == v:
            return
        self._active = v
        sc = self._scene
        if sc:
            sc._render_version += 1
            if v:
                sc._active_update_components.update(c for c in self._update_list if c.enabled)
                sc._active_fixed_components.update(c for c in self._fixed_update_list if c.enabled)
                sc._spatial_dirty = True
                sc._spatial_dirty_entities.add(self._id)
            else:
                sc._active_update_components.difference_update(self._update_list)
                sc._active_fixed_components.difference_update(self._fixed_update_list)
                sc._spatial.remove(self._id)
                sc._spatial_dirty_entities.discard(self._id)
                sc._spatial_known_entities.discard(self._id)
        cb = (lambda c: c.on_enable()) if v else (lambda c: c.on_disable())
        comps = self._components
        for c in comps.values():
            if c.enabled:
                cb(c)
    @property
    def parent(self) -> Optional[Entity]: return self._parent
    @property
    def children(self) -> list[Entity]: return self._children
    @property
    def tags(self) -> set[str]: return self._tags
    @property
    def layer(self) -> int: return self._layer
    @layer.setter
    def layer(self, v: int): self._layer = v
    @property
    def embed_resources(self) -> bool: return self._embed_resources
    @embed_resources.setter
    def embed_resources(self, v: bool):
        if self._embed_resources == v:
            return
        self._embed_resources = bool(v)
        sc = self._scene
        if sc:
            sc._render_version += 1
    @property
    def locked(self) -> bool: return self._locked
    @locked.setter
    def locked(self, v: bool): self._locked = bool(v)
    @property
    def system(self) -> bool: return self._system
    @system.setter
    def system(self, v: bool): self._system = bool(v)
    @property
    def prefab_guid(self) -> Optional[str]: return self._prefab_guid
    @prefab_guid.setter
    def prefab_guid(self, v: Optional[str]): self._prefab_guid = v
    @property
    def prefab_source_id(self) -> Optional[str]: return self._prefab_source_id
    @prefab_source_id.setter
    def prefab_source_id(self, v: Optional[str]): self._prefab_source_id = v
    @property
    def is_prefab_instance(self) -> bool:
        return self._prefab_guid is not None
    def set_parent(self, parent: Optional[Entity], preserve_world: bool = True):
        t = self.transform
        if t and preserve_world:
            world = t.world_matrix
        else:
            world = None
        old = self._parent
        if old is not None:
            ch = old._children
            try: ch.remove(self)
            except ValueError: pass
        self._parent = parent
        if parent is not None:
            parent._children.append(self)
        if world is not None:
            t.world_matrix = world
        if t is not None:
            t._mark_dirty()
        sc = self._scene
        if sc:
            sc._roots_cache_valid = False
            dc = sc._depth_cache
            stack = [self]
            while stack:
                e = stack.pop()
                dc.pop(e._id, None)
                ch = e._children
                for c in ch:
                    stack.append(c)
    def _invalidate_transform_cache(self):
        for c in self._components.values(): c._transform = _UNSET
    def _make_component_key(self, comp: Component) -> str:
        t = type(comp); base = t.__name__
        if t._allow_multiple:
            return base + "." + str(uuid.uuid4())[:8]
        return base
    def add_component(self, comp: Component, key: Optional[str] = None) -> Component:
        if key is None:
            t = type(comp)
            base = t.__name__
            if t._allow_multiple:
                key = base + "." + str(uuid.uuid4())[:8]
            else:
                key = base
        comp._entity = self; comp._key = key
        comp_type = type(comp)
        comps = self._components
        comps[key] = comp
        type_map = self._type_map
        lst = type_map.get(comp_type)
        if lst is None:
            type_map[comp_type] = [comp]
            self._type_name_map[comp_type.__name__] = comp_type
        else:
            lst.append(comp)
        sc = self._scene
        is_active = self._active
        if comp._updates:
            self._update_list.append(comp)
            if sc and is_active and comp.enabled:
                sc._active_update_components.add(comp)
        if comp._fixed_updates:
            self._fixed_update_list.append(comp)
            if sc and is_active and comp.enabled:
                sc._active_fixed_components.add(comp)
        if sc is not None:
            comp_name = comp_type.__name__
            idx = sc._component_indices
            s = idx.get(comp_name)
            if s is None:
                idx[comp_name] = {self._id}
            else:
                s.add(self._id)
            sc._render_version += 1
            sc._invalidate_update_cache()
        if comp_type.__name__ == _TRANSFORM_NAME:
            self._transform_type = comp_type
            self._transform = comp
            for c in comps.values():
                c._transform = _UNSET
            if sc is not None and getattr(comp, "_dirty", False):
                sc._dirty_roots.add(comp)
            if sc is not None:
                try:
                    if getattr(comp, "_soa", -1) < 0:
                        sc._soa_alloc_for(comp)
                except Exception:
                    pass
        comp.on_awake()
        return comp
    def remove_component(self, cls: Type[T]):
        clist = self._type_map.get(cls)
        if not clist:
            return
        comp = clist.pop(0)
        key = comp._key
        comp.on_destroy()
        self._components.pop(key, None)
        try:
            if getattr(comp, "_soa", -1) >= 0 and self._scene is not None:
                self._scene._soa_release(comp)
        except Exception:
            pass
        if not clist:
            del self._type_map[cls]
            self._type_name_map.pop(cls.__name__, None)
            if cls.__name__ == "Transform":
                self._transform_type = None; self._transform = None
                self._invalidate_transform_cache()
        sc = self._scene
        if comp._updates:
            try: self._update_list.remove(comp)
            except ValueError: pass
            if sc:
                sc._active_update_components.discard(comp)
        if comp._fixed_updates:
            try: self._fixed_update_list.remove(comp)
            except ValueError: pass
            if sc:
                sc._active_fixed_components.discard(comp)
        if sc:
            base = cls.__name__
            if base == "Transform":
                self._transform_type = None; self._transform = None
            idx = sc._component_indices.get(base)
            if idx:
                idx.discard(self._id)
            sc._render_version += 1
            sc._invalidate_update_cache()
    def remove_all_components(self, cls: Type[T]):
        clist = self._type_map.pop(cls, None)
        if not clist:
            return
        base = cls.__name__
        sc = self._scene
        upd = self._update_list
        fupd = self._fixed_update_list
        for comp in clist:
            comp.on_destroy()
            self._components.pop(comp._key, None)
            try:
                if getattr(comp, "_soa", -1) >= 0 and sc is not None:
                    sc._soa_release(comp)
            except Exception:
                pass
            if comp._updates:
                try: upd.remove(comp)
                except ValueError: pass
                if sc:
                    sc._active_update_components.discard(comp)
            if comp._fixed_updates:
                try: fupd.remove(comp)
                except ValueError: pass
                if sc:
                    sc._active_fixed_components.discard(comp)
        if not clist:
            del self._type_map[cls]
            self._type_name_map.pop(cls.__name__, None)
        if base == "Transform":
            self._transform_type = None; self._transform = None
            self._invalidate_transform_cache()
        if sc:
            idx = sc._component_indices.get(base)
            if idx:
                idx.discard(self._id)
            sc._invalidate_update_cache()
    def remove_component_by_key(self, key: str):
        comp = self._components.pop(key, None)
        if comp is None:
            return
        comp.on_destroy()
        comp_type = type(comp)
        clist = self._type_map.get(comp_type)
        if clist:
            try: clist.remove(comp)
            except ValueError: pass
            if not clist:
                del self._type_map[comp_type]
                self._type_name_map.pop(comp_type.__name__, None)
                if comp_type.__name__ == "Transform":
                    self._transform_type = None; self._transform = None
                    self._invalidate_transform_cache()
        sc = self._scene
        if comp._updates:
            try: self._update_list.remove(comp)
            except ValueError: pass
            if sc:
                sc._active_update_components.discard(comp)
        if comp._fixed_updates:
            try: self._fixed_update_list.remove(comp)
            except ValueError: pass
            if sc:
                sc._active_fixed_components.discard(comp)
        base = key.split(".")[0]
        if sc:
            if base == "Transform":
                self._transform_type = None; self._transform = None
            idx = sc._component_indices.get(base)
            if idx:
                idx.discard(self._id)
            sc._invalidate_update_cache()
    def get_component(self, cls: Type[T]) -> Optional[T]:
        clist = self._type_map.get(cls)
        if clist:
            return clist[0]
        for comp_type, items in self._type_map.items():
            try:
                if issubclass(comp_type, cls) and items:
                    return items[0]
            except Exception: continue
        return None
    def get_components(self, cls: Type[T]) -> list[T]:
        exact = self._type_map.get(cls)
        if exact:
            return list(exact)
        result: list[T] = []
        for comp_type, items in self._type_map.items():
            try:
                if issubclass(comp_type, cls):
                    result.extend(items)
            except Exception: continue
        return result
    def get_component_by_name(self, name: str) -> Optional[Component]:
        t = self._type_name_map.get(name)
        if t is not None:
            clist = self._type_map.get(t)
            if clist:
                return clist[0]
        c = self._components.get(name)
        if c is not None:
            return c
        prefix = name + "."
        for k, c in self._components.items():
            if k.startswith(prefix):
                return c
        base_cls = ComponentRegistry._registry.get(name)
        if base_cls is not None:
            for comp_type, items in self._type_map.items():
                try:
                    if issubclass(comp_type, base_cls) and items:
                        return items[0]
                except Exception: continue
        return None
    def has_component(self, cls: Type[T]) -> bool:
        if cls in self._type_map:
            return True
        for comp_type in self._type_map:
            try:
                if issubclass(comp_type, cls):
                    return True
            except Exception: continue
        return False
    def get_all_components(self) -> list[Component]:
        result = []
        for clist in self._type_map.values(): result.extend(clist)
        return result
    def move_component(self, key: str, direction: int):
        keys = list(self._components.keys())
        if key not in keys:
            return
        idx = keys.index(key)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(keys):
            return
        keys[idx], keys[new_idx] = keys[new_idx], keys[idx]
        self._components = {k: self._components[k] for k in keys}
    def get_component_in_children(self, cls: Type[T]) -> Optional[T]:
        for child in self._children:
            c = child.get_component(cls)
            if c:
                return c
            c = child.get_component_in_children(cls)
            if c:
                return c
        return None
    def serialize(self) -> dict:
        comps = []
        comps_append = comps.append
        for k, c in self._components.items():
            cd = c.serialize()
            cd["_key"] = k
            comps_append(cd)
        d = {"id": self._id, "name": self._name, "active": self._active, "tags": list(self._tags), "layer": self._layer, "parent": self._parent.id if self._parent else None, "components": comps}
        if self._prefab_guid:
            d["prefab_guid"] = self._prefab_guid
        if self._prefab_source_id:
            d["prefab_source_id"] = self._prefab_source_id
        if self._embed_resources:
            d["embed_resources"] = True
        if self._locked:
            d["locked"] = True
        if self._system:
            d["system"] = True
        return d
    @classmethod
    def deserialize(cls, data: dict, registry: ComponentRegistry) -> Entity:
        prefab_guid = data.get("prefab_guid")
        e = cls(data["name"], data["id"], prefab_guid=prefab_guid)
        e._active = data.get("active", True)
        e._tags = set(data.get("tags", []))
        e._layer = data.get("layer", 0)
        e._prefab_source_id = data.get("prefab_source_id")
        e._embed_resources = bool(data.get("embed_resources", False))
        e._locked = bool(data.get("locked", False))
        e._system = bool(data.get("system", False))
        for cd in data.get("components", []):
            ctype = cd.get("type")
            comp_cls = registry.get(ctype)
            if comp_cls:
                comp = comp_cls.deserialize(cd)
                key = cd.get("_key", None)
                e.add_component(comp, key=key)
        return e
