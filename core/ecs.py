from __future__ import annotations
import uuid
import json
import time
from typing import Any, Type, TypeVar, Iterator, Optional
from dataclasses import dataclass, field
T = TypeVar("T", bound="Component")

_UNSET = object()


def _get_engine():
    try:
        from core.engine import Engine
        return Engine.instance()
    except Exception:
        return None


class Component:
    _entity: Optional[Entity] = None
    _key: str = ""
    enabled: bool = True
    _allow_multiple: bool = False
    _updates: bool = False
    _fixed_updates: bool = False
    _gizmo_icon_color: tuple[int, int, int] = (140, 60, 200)
    _gizmo_icon_label: str = "?"
    _gizmo_icon_path: Optional[str] = None
    _show_gizmo_icon: bool = True
    _transform: Any = _UNSET

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._updates = cls.on_update is not Component.on_update
        cls._fixed_updates = cls.on_fixed_update is not Component.on_fixed_update

    def on_awake(self): pass
    def on_start(self): pass
    def on_update(self, dt: float): pass
    def on_fixed_update(self, dt: float): pass
    def on_destroy(self): pass
    def on_enable(self): pass
    def on_disable(self): pass

    @property
    def entity(self) -> Optional[Entity]: return self._entity

    @property
    def transform(self) -> Optional[Any]:
        t = self.__dict__.get('_transform', _UNSET)
        if t is not _UNSET:
            return t
        ent = self._entity
        if ent is None:
            self.__dict__['_transform'] = None
            return None
        cls = ent._component_name_index.get("Transform")
        if cls:
            clist = ent._component_type_index.get(cls)
            if clist:
                self.__dict__['_transform'] = clist[0]
                return clist[0]
        self.__dict__['_transform'] = None
        return None

    @property
    def gizmo_icon(self) -> Optional[tuple[int, int, int, str]]:
        if not self._show_gizmo_icon:
            return None
        return (self._gizmo_icon_color[0], self._gizmo_icon_color[1], self._gizmo_icon_color[2], self._gizmo_icon_label)

    def gizmo_lines(self) -> list[tuple[Any, Any, list[float]]]:
        return []

    def gizmo_meshes(self) -> list[tuple[list, list, list]]:
        return []

    def serialize(self) -> dict:
        return {"type": type(self).__name__, "enabled": self.enabled}

    @classmethod
    def deserialize(cls, data: dict) -> Component:
        inst = cls.__new__(cls)
        inst.enabled = data.get("enabled", True)
        inst._entity = None
        return inst


class Entity:
    __slots__ = (
        '_id', '_name', '_components', '_component_type_index',
        '_component_name_index', '_update_list', '_fixed_update_list',
        '_active', '_parent', '_children', '_tags', '_layer',
        '_scene', '_prefab_guid', '_prefab_data',
    )

    def __init__(self, name: str = "Entity", eid: Optional[str] = None,
                 prefab_guid: Optional[str] = None):
        self._id: str = eid or str(uuid.uuid4())
        self._name: str = name
        self._components: dict[str, Component] = {}
        self._component_type_index: dict[type, list[Component]] = {}
        self._component_name_index: dict[str, type] = {}
        self._update_list: list[Component] = []
        self._fixed_update_list: list[Component] = []
        self._active: bool = True
        self._parent: Optional[Entity] = None
        self._children: list[Entity] = []
        self._tags: set[str] = set()
        self._layer: int = 0
        self._scene: Optional[Scene] = None
        self._prefab_guid: Optional[str] = prefab_guid
        self._prefab_data: Optional[dict] = None

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
        self._active = v
        sc = self._scene
        if sc:
            sc._render_version += 1
            if v:
                sc._active_update_components.update(c for c in self._update_list if c.enabled)
                sc._active_fixed_components.update(c for c in self._fixed_update_list if c.enabled)
            else:
                sc._active_update_components.difference_update(self._update_list)
                sc._active_fixed_components.difference_update(self._fixed_update_list)
        cb = (lambda c: c.on_enable()) if v else (lambda c: c.on_disable())
        for c in self._components.values():
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
    def prefab_guid(self) -> Optional[str]: return self._prefab_guid

    @prefab_guid.setter
    def prefab_guid(self, v: Optional[str]): self._prefab_guid = v

    @property
    def prefab_data(self) -> Optional[dict]: return self._prefab_data

    @prefab_data.setter
    def prefab_data(self, v: Optional[dict]): self._prefab_data = v

    @property
    def is_prefab_instance(self) -> bool:
        return self._prefab_guid is not None

    def set_parent(self, parent: Optional[Entity], preserve_world: bool = True):
        t = self.get_component_by_name("Transform")
        old_world_pos = t.position if t and preserve_world else None
        old = self._parent
        if old is not None:
            ch = old._children
            try:
                ch.remove(self)
            except ValueError:
                pass
        self._parent = parent
        if parent is not None:
            parent._children.append(self)
        if old_world_pos is not None:
            t.position = old_world_pos

    def _invalidate_transform_cache(self):
        d_pop = dict.pop
        for c in self._components.values():
            d_pop(c.__dict__, '_transform', None)

    def _make_component_key(self, comp: Component) -> str:
        base = type(comp).__name__
        if getattr(type(comp), '_allow_multiple', False):
            return base + "." + str(uuid.uuid4())[:8]
        return base

    def add_component(self, comp: Component, key: Optional[str] = None) -> Component:
        if key is None:
            key = self._make_component_key(comp)
        comp._entity = self
        comp._key = key
        self._components[key] = comp
        comp_type = type(comp)
        type_index = self._component_type_index
        name_index = self._component_name_index
        if comp_type not in type_index:
            type_index[comp_type] = []
            cname = comp_type.__name__
            if cname not in name_index:
                name_index[cname] = comp_type
        type_index[comp_type].append(comp)
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
        if sc:
            base = comp_type.__name__
            idx = sc._component_indices
            if base not in idx:
                idx[base] = set()
            idx[base].add(self._id)
            sc._render_version += 1
        if comp_type.__name__ == "Transform":
            self._invalidate_transform_cache()
        elif '_transform' not in comp.__dict__:
            t_cls = name_index.get("Transform")
            if t_cls:
                t_list = type_index.get(t_cls)
                if t_list:
                    comp.__dict__['_transform'] = t_list[0]
        comp.on_awake()
        return comp

    def remove_component(self, cls: Type[T]):
        clist = self._component_type_index.get(cls)
        if not clist:
            return
        comp = clist.pop(0)
        key = comp._key
        comp.on_destroy()
        self._components.pop(key, None)
        if not clist:
            del self._component_type_index[cls]
            self._component_name_index.pop(cls.__name__, None)
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
        base = cls.__name__
        if sc:
            if base == "Transform":
                self._invalidate_transform_cache()
            idx = sc._component_indices.get(base)
            if idx:
                idx.discard(self._id)
            sc._render_version += 1

    def remove_all_components(self, cls: Type[T]):
        clist = self._component_type_index.pop(cls, None)
        if not clist:
            return
        base = cls.__name__
        sc = self._scene
        upd = self._update_list
        fupd = self._fixed_update_list
        for comp in clist:
            comp.on_destroy()
            self._components.pop(comp._key, None)
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
        self._component_name_index.pop(cls.__name__, None)
        if sc:
            if base == "Transform":
                self._invalidate_transform_cache()
            idx = sc._component_indices.get(base)
            if idx:
                idx.discard(self._id)

    def remove_component_by_key(self, key: str):
        comp = self._components.pop(key, None)
        if comp is None:
            return
        comp.on_destroy()
        comp_type = type(comp)
        clist = self._component_type_index.get(comp_type)
        if clist:
            try: clist.remove(comp)
            except ValueError: pass
            if not clist:
                del self._component_type_index[comp_type]
                self._component_name_index.pop(comp_type.__name__, None)
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
                self._invalidate_transform_cache()
            idx = sc._component_indices.get(base)
            if idx:
                idx.discard(self._id)

    def get_component(self, cls: Type[T]) -> Optional[T]:
        clist = self._component_type_index.get(cls)
        return clist[0] if clist else None

    def get_components(self, cls: Type[T]) -> list[T]:
        return list(self._component_type_index.get(cls, []))

    def get_component_by_name(self, name: str) -> Optional[Component]:
        cls = self._component_name_index.get(name)
        if cls:
            clist = self._component_type_index.get(cls)
            if clist:
                return clist[0]
        c = self._components.get(name)
        if c is not None:
            return c
        prefix = name + "."
        for k, c in self._components.items():
            if k.startswith(prefix):
                return c
        return None

    def has_component(self, cls: Type[T]) -> bool:
        return cls in self._component_type_index

    def get_all_components(self) -> list[Component]:
        return list(self._components.values())

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
        d = {
            "id": self._id, "name": self._name, "active": self._active,
            "tags": list(self._tags), "layer": self._layer,
            "parent": self._parent.id if self._parent else None,
            "components": [{"_key": k, **c.serialize()} for k, c in self._components.items()]
        }
        if self._prefab_guid:
            d["prefab_guid"] = self._prefab_guid
        if self._prefab_data:
            d["prefab_data"] = self._prefab_data
        return d

    @classmethod
    def deserialize(cls, data: dict, registry: ComponentRegistry) -> Entity:
        prefab_guid = data.get("prefab_guid")
        e = cls(data["name"], data["id"], prefab_guid=prefab_guid)
        e._active = data.get("active", True)
        e._tags = set(data.get("tags", []))
        e._layer = data.get("layer", 0)
        e._prefab_data = data.get("prefab_data")
        for cd in data.get("components", []):
            ctype = cd.get("type")
            comp_cls = registry.get(ctype)
            if comp_cls:
                comp = comp_cls.deserialize(cd)
                key = cd.get("_key", None)
                e.add_component(comp, key=key)
        return e


class ComponentRegistry:
    _registry: dict[str, Type[Component]] = {}
    _categories: dict[str, list[str]] = {}
    _category_name_map: dict[str, str] = {
        "transform": "Transform",
        "rendering": "Rendering",
        "physics": "Physics",
        "physics2d": "Physics 2D",
        "lighting": "Lighting",
        "audio": "Audio",
        "constraints": "Constraints",
        "network": "Network",
        "scripting": "Scripting",
    }

    @classmethod
    def register(cls, comp_cls: Type[Component]):
        name = comp_cls.__name__
        cls._registry[name] = comp_cls
        category = cls._infer_category(comp_cls)
        if category:
            cls._categories[name] = [category]
        return comp_cls

    @classmethod
    def _infer_category(cls, comp_cls: Type[Component]) -> Optional[str]:
        module = getattr(comp_cls, "__module__", "")
        parts = module.split(".")
        for i, part in enumerate(parts):
            if part == "components" and i + 1 < len(parts):
                sub = parts[i + 1]
                return cls._category_name_map.get(sub, sub.capitalize())
        return None

    @classmethod
    def get(cls, name: str) -> Optional[Type[Component]]:
        return cls._registry.get(name)

    @classmethod
    def all(cls) -> dict[str, Type[Component]]:
        return dict(cls._registry)

    @classmethod
    def get_categories(cls, comp_name: str) -> list[str]:
        return list(cls._categories.get(comp_name, []))

    @classmethod
    def all_categories(cls) -> dict[str, list[str]]:
        return dict(cls._categories)


class Scene:
    def __init__(self, name: str = "Scene"):
        self._name: str = name
        self._entities: dict[str, Entity] = {}
        self._entities_cache: list[Entity] = []
        self._entities_cache_valid: bool = False
        self._systems: list[Any] = []
        self._path: Optional[str] = None
        self._dirty: bool = False
        self._component_indices: dict[str, set[str]] = {}
        self._render_version: int = 0
        self._engine_ref = None
        self._scene_prof: Any = None
        self._active_update_components: set[Component] = set()
        self._active_fixed_components: set[Component] = set()
        self._update_list_cache: list[Component] = []
        self._fixed_list_cache: list[Component] = []
        self._update_cache_valid: bool = False
        self._fixed_cache_valid: bool = False

    def _invalidate_update_cache(self):
        self._update_cache_valid = False
        self._fixed_cache_valid = False

    def _get_update_list(self) -> list[Component]:
        if not self._update_cache_valid:
            self._update_list_cache = [c for c in self._active_update_components if c.enabled]
            self._update_cache_valid = True
        return self._update_list_cache

    def _get_fixed_list(self) -> list[Component]:
        if not self._fixed_cache_valid:
            self._fixed_list_cache = [c for c in self._active_fixed_components if c.enabled]
            self._fixed_cache_valid = True
        return self._fixed_list_cache

    @property
    def _engine(self):
        if self._engine_ref is None:
            from core.engine import Engine
            self._engine_ref = Engine.instance()
        return self._engine_ref

    def _ensure_entities_cache(self):
        if not self._entities_cache_valid:
            self._entities_cache = list(self._entities.values())
            self._entities_cache_valid = True
        return self._entities_cache

    @property
    def name(self) -> str: return self._name

    @name.setter
    def name(self, v: str):
        self._name = v
        self._dirty = True

    @property
    def path(self) -> Optional[str]: return self._path

    @path.setter
    def path(self, v: str): self._path = v

    @property
    def dirty(self) -> bool: return self._dirty

    def mark_dirty(self): self._dirty = True
    def mark_clean(self): self._dirty = False

    def create_entity(self, name: str = "Entity",
                      prefab_guid: Optional[str] = None) -> Entity:
        e = Entity(name, prefab_guid=prefab_guid)
        e._scene = self
        self._entities[e.id] = e
        self._dirty = True
        self._render_version += 1
        self._entities_cache_valid = False
        return e

    def add_entity(self, e: Entity):
        e._scene = self
        self._entities[e.id] = e
        eid = e.id
        idx = self._component_indices
        is_active = e._active
        for comp_type, clist in e._component_type_index.items():
            comp_name = comp_type.__name__
            if comp_name not in idx:
                idx[comp_name] = set()
            idx[comp_name].add(eid)
            if is_active:
                for comp in clist:
                    if comp.enabled:
                        if comp._updates:
                            self._active_update_components.add(comp)
                        if comp._fixed_updates:
                            self._active_fixed_components.add(comp)
        self._invalidate_update_cache()
        self._dirty = True
        self._render_version += 1
        self._entities_cache_valid = False

    def remove_entity(self, eid: str):
        e = self._entities.pop(eid, None)
        if not e:
            return
        for child in list(e._children):
            self.remove_entity(child._id)
        auc = self._active_update_components
        afc = self._active_fixed_components
        idx = self._component_indices
        for c in e._components.values():
            c.on_destroy()
        for comp_type, clist in e._component_type_index.items():
            comp_name = comp_type.__name__
            s = idx.get(comp_name)
            if s:
                s.discard(eid)
            for comp in clist:
                auc.discard(comp)
                afc.discard(comp)
        self._invalidate_update_cache()
        self._dirty = True
        self._render_version += 1
        self._entities_cache_valid = False

    def get_entity(self, eid: str) -> Optional[Entity]:
        return self._entities.get(eid)

    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        for e in self._entities.values():
            if e._name == name:
                return e
        return None

    def get_all_entities(self) -> list[Entity]:
        return self._ensure_entities_cache()

    def get_root_entities(self) -> list[Entity]:
        return [e for e in self._entities.values() if e._parent is None]

    def get_entities_with_component(self, cls: Type[T]) -> list[Entity]:
        key = cls.__name__
        s = self._component_indices.get(key)
        if not s:
            return []
        ents = self._entities
        return [ents[eid] for eid in s if eid in ents]

    def _rebuild_component_index(self, comp_cls_name: str):
        indices: set[str] = set()
        for eid, e in self._entities.items():
            for t in e._component_type_index:
                if t.__name__ == comp_cls_name:
                    indices.add(eid)
                    break
        self._component_indices[comp_cls_name] = indices

    def _get_profiler(self):
        p = self._scene_prof
        if p is not None:
            return p if p is not False else None
        eng = self._engine
        if eng and hasattr(eng, '_profiler'):
            self._scene_prof = eng._profiler
            return self._scene_prof
        self._scene_prof = False
        return None

    def update(self, dt: float):
        prof = self._get_profiler()
        if prof is None:
            return
        prof.start("scene_update")
        log_error = None
        for c in self._get_update_list():
            try:
                c.on_update(dt)
            except Exception as ex:
                if log_error is None:
                    from core.logger import Logger
                    log_error = Logger.error
                ent = c._entity
                log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
        prof.stop("scene_update")

    def fixed_update(self, dt: float):
        prof = self._get_profiler()
        if prof is None:
            return
        prof.start("scene_fixed_update")
        log_error = None
        for c in self._get_fixed_list():
            try:
                c.on_fixed_update(dt)
            except Exception as ex:
                if log_error is None:
                    from core.logger import Logger
                    log_error = Logger.error
                ent = c._entity
                log_error(f"FixedUpdate error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
        prof.stop("scene_fixed_update")

    def start(self):
        prof = self._get_profiler()
        if prof is None:
            return
        prof.start("scene_start")
        for e in list(self._entities.values()):
            for c in e.get_all_components():
                try:
                    c.on_start()
                except Exception as ex:
                    from core.logger import Logger
                    Logger.error(f"Start error: {ex}")
        prof.stop("scene_start")

    def serialize(self) -> dict:
        prof = self._get_profiler()
        if prof is None:
            return {"name": self._name}
        prof.start("scene_serialize")
        data = {"name": self._name, "entities": {eid: e.serialize() for eid, e in self._entities.items()}}
        prof.stop("scene_serialize")
        return data

    @classmethod
    def deserialize(cls, data: dict, registry: ComponentRegistry) -> Scene:
        eng = _get_engine()
        prof = None
        if eng and hasattr(eng, '_profiler'):
            prof = eng._profiler
            prof.start("scene_deserialize")
        s = cls(data["name"])
        raw = data.get("entities", {})
        entities: dict[str, Entity] = {}
        parent_map: dict[str, Optional[str]] = {}
        for eid, ed in raw.items():
            e = Entity.deserialize(ed, registry)
            entities[eid] = e
            parent_map[eid] = ed.get("parent")
        for eid, e in entities.items():
            pid = parent_map.get(eid)
            if pid and pid in entities:
                e.set_parent(entities[pid])
            s.add_entity(e)
        if prof:
            prof.stop("scene_deserialize")
        return s