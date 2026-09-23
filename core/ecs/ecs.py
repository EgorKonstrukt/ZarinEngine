# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Any, Type, TypeVar, Optional
import numpy as np
from core.spatial import Octree, AABB
try:
    from core._constraint_update import batch_update_constraints as _batch_constraints
except ImportError:
    _batch_constraints = None
try:
    from core._ik import batch_update_ik as _batch_ik
except ImportError:
    _batch_ik = None

try:
    from core._scene_query import fast_get_entities_with_component as _fast_get
    _HAS_FAST_QUERY = True
except ImportError:
    _fast_get = None
    _HAS_FAST_QUERY = False
try:
    from core._ecs_batch import batch_update_flat as _batch_flat
    from core._ecs_batch import batch_update_from_transforms as _batch_from_transforms
except ImportError:
    _batch_flat = None
    _batch_from_transforms = None

T = TypeVar("T", bound="Component")

_UNSET = object()

_GIZMO_PASSES: dict[str, list[type[Component]]] = {}
_GIZMO_PASS_ORDER: list[str] = ["collider", "particle", "force_field", "camera", "audio", "light", "script", "nav", "armature"]

_TRANSFORM_NAME = "Transform"

_SUBCLASS_CACHE: dict = {}
_SUBCLASS_CACHE_VERSION: int = 0

_GIZMO_HOOK_CACHE: dict = {}


def _subclass_names(key: str, cls) -> list:
    cached = _SUBCLASS_CACHE.get(key)
    if cached is not None and cached[0] == _SUBCLASS_CACHE_VERSION:
        return cached[1]
    found: list = []
    try:
        for reg_name, reg_cls in ComponentRegistry._registry.items():
            if reg_name != key and issubclass(reg_cls, cls):
                found.append(reg_name)
    except Exception:
        found = []
    _SUBCLASS_CACHE[key] = (_SUBCLASS_CACHE_VERSION, found)
    return found

def _get_engine():
    try:
        from core.engine.engine import Engine
        return Engine.instance()
    except Exception:
        return None


class Component:
    _entity: Optional[Entity] = None
    _key: str = ""
    _enabled: bool = True
    _allow_multiple: bool = False
    _updates: bool = False
    _fixed_updates: bool = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, v: bool):
        if self._enabled == v:
            return
        self._enabled = bool(v)
        ent = self._entity
        if ent is not None and ent._scene is not None:
            sc = ent._scene
            sc._invalidate_update_cache()
            if self._enabled:
                if self._updates:
                    sc._active_update_components.add(self)
                if self._fixed_updates:
                    sc._active_fixed_components.add(self)
            else:
                sc._active_update_components.discard(self)
                sc._active_fixed_components.discard(self)
    _gizmo_icon_color: tuple[int, int, int] = (140, 60, 200)
    _gizmo_icon_label: str = "?"
    _gizmo_icon_path: Optional[str] = None
    _show_gizmo_icon: bool = True
    _transform: Any = _UNSET
    _gizmo_pass: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._updates = cls.on_update is not Component.on_update
        cls._fixed_updates = cls.on_fixed_update is not Component.on_fixed_update
        pname = cls.__dict__.get('_gizmo_pass', '')
        if pname:
            if pname not in _GIZMO_PASSES:
                _GIZMO_PASSES[pname] = []
            _GIZMO_PASSES[pname].append(cls)

    def on_awake(self): pass
    def on_start(self): pass
    def on_update(self, dt: float): pass
    def on_fixed_update(self, dt: float): pass
    def on_destroy(self): pass
    def on_enable(self): pass
    def on_disable(self): pass

    @property
    def entity(self) -> Optional[Entity]:
        return self._entity

    @property
    def transform(self):
        cached = self._transform
        if cached is not _UNSET:
            return cached
        ent = self._entity
        if ent is None:
            self._transform = None
            return None
        tr = ent._transform
        if tr is not None:
            self._transform = tr
            return tr
        t_type = ent._transform_type
        if t_type is None:
            t_type = ent._get_transform_type()
            if t_type is None:
                self._transform = None
                return None
        t_list = ent._type_map.get(t_type)
        result = t_list[0] if t_list else None
        self._transform = result
        return result

    @property
    def gizmo_icon(self) -> Optional[tuple[int, int, int, str]]:
        if not self._show_gizmo_icon:
            return None
        return (self._gizmo_icon_color[0], self._gizmo_icon_color[1], self._gizmo_icon_color[2], self._gizmo_icon_label)

    def gizmo_lines(self) -> list[tuple[Any, Any, list[float]]]:
        return []

    def gizmo_primitives(self):
        return None

    def gizmo_instance_data(self):
        return None

    def gizmo_instances(self):
        return None

    def gizmo_cache_sig(self):
        attrs = getattr(type(self), "_gizmo_cache_attrs", None)
        if not attrs:
            return None
        tr = self.transform
        if tr is None:
            return None
        try:
            wm = tr.world_matrix._d.tobytes()
        except Exception:
            return None
        from core.maths.math3d import Vec2, Vec3, Vec4
        from enum import Enum
        parts = [wm]
        for a in attrs:
            v = getattr(self, a, None)
            if v is None:
                parts.append(None)
            elif isinstance(v, (list, tuple)):
                parts.append(tuple(v))
            elif isinstance(v, (Vec2, Vec3, Vec4)):
                parts.append((v.x, v.y, v.z, getattr(v, "w", 0.0)))
            elif isinstance(v, Enum):
                parts.append(v.value)
            else:
                parts.append(v)
        return tuple(parts)

    def gizmo_meshes(self) -> list[tuple[list, list, list]]:
        return []

    def gizmo(self):
        prims = self.gizmo_primitives()
        if prims is not None:
            s, e, c = prims
            if s.shape[0] > 0:
                return [GizmoPrimitive(s, e, c, self._gizmo_line_style())]
        lines = self.gizmo_lines()
        if lines:
            return [GizmoPrimitive.from_lines(lines)]
        return []

    def _gizmo_line_style(self):
        tw = getattr(self, "thickness", None)
        if tw is None:
            return GizmoStyle.DEFAULT
        try:
            return GizmoStyle(line_width=max(0.1, float(tw)))
        except Exception:
            return GizmoStyle.DEFAULT

    @classmethod
    def gizmo_collect(cls, pipe, scene):
        hk = _GIZMO_HOOK_CACHE.get(cls)
        if hk is None:
            hk = (cls.gizmo_instances is not Component.gizmo_instances,
                  cls.gizmo_instance_data is not Component.gizmo_instance_data,
                  cls.gizmo_lines is not Component.gizmo_lines or cls.gizmo_primitives is not Component.gizmo_primitives)
            _GIZMO_HOOK_CACHE[cls] = hk
        has_insts, has_data, has_lines = hk
        if not has_insts and not has_data and not has_lines:
            return
        add = pipe.add_instance if (has_insts or has_data) else None
        for entity in scene.get_entities_with_component(cls):
            if not entity.active:
                continue
            lst = entity._type_map.get(cls)
            if lst is None:
                lst = entity.get_components(cls)
                if not lst:
                    continue
            for comp in lst:
                try:
                    if has_insts:
                        insts = comp.gizmo_instances()
                        if insts:
                            for ip in insts:
                                add(ip.shape_type, ip.transform_flat, ip.color)
                    if has_data:
                        inst = comp.gizmo_instance_data()
                        if inst is not None:
                            add(inst.shape_type, inst.transform_flat, inst.color)
                    if has_lines:
                        for prim in comp.gizmo():
                            if prim.starts.shape[0] > 0:
                                pipe.add(prim)
                except Exception:
                    pass

    @classmethod
    def gizmo_collect_meshes(cls, scene):
        return []

    def serialize(self) -> dict:
        return {"type": type(self).__name__, "enabled": self.enabled}

    @classmethod
    def deserialize(cls, data: dict) -> Component:
        inst = cls()
        inst._enabled = bool(data.get("enabled", True))
        inst._entity = None
        return inst


@dataclass
class GizmoStyle:
    glow: bool = False
    dashed: bool = False
    pulsating: bool = False
    color_cycling: bool = False
    xray: bool = False
    line_width: float = 1.0
    dash_length: float = 0.3
    gap_length: float = 0.15
    glow_layers: int = 3
    glow_intensity: float = 0.4
    pulse_speed: float = 2.0
    pulse_min_alpha: float = 0.2
    cycle_speed: float = 1.0
    cull_distance: float = 0.0

    DEFAULT: Optional[GizmoStyle] = None


GizmoStyle.DEFAULT = GizmoStyle()


@dataclass
class GizmoPrimitive:
    starts: np.ndarray
    ends: np.ndarray
    colors: np.ndarray
    style: GizmoStyle = field(default_factory=lambda: GizmoStyle.DEFAULT)

    @classmethod
    def from_lines(cls, lines: list, style: GizmoStyle = None) -> GizmoPrimitive:
        n = len(lines)
        starts = np.zeros((n, 3), dtype=np.float32)
        ends = np.zeros((n, 3), dtype=np.float32)
        colors = np.zeros((n, 4), dtype=np.float32)
        for i, (s, e, c) in enumerate(lines):
            starts[i, 0] = s.x; starts[i, 1] = s.y; starts[i, 2] = s.z
            ends[i, 0] = e.x; ends[i, 1] = e.y; ends[i, 2] = e.z
            colors[i, 0] = c[0]; colors[i, 1] = c[1]; colors[i, 2] = c[2]
            colors[i, 3] = c[3] if len(c) > 3 else 1.0
        return cls(starts, ends, colors, style or GizmoStyle.DEFAULT)


@dataclass
class InstancePrimitive:
    shape_type: str
    transform_flat: np.ndarray
    color: list


class Entity:
    __slots__ = (
        '_id', '_name', '_type_map', '_type_name_map', '_components',
        '_update_list', '_fixed_update_list',
        '_active', '_parent', '_children', '_tags', '_layer',
        '_scene', '_prefab_guid', '_prefab_source_id',
        '_transform_type', '_transform', '_embed_resources', '_locked', '_system',
    )

    def __init__(self, name: str = "Entity", eid: Optional[str] = None,
                 prefab_guid: Optional[str] = None):
        self._id: str = eid or str(uuid.uuid4())
        self._name: str = name
        self._type_map: dict[type, list[Component]] = {}
        self._type_name_map: dict[str, type] = {}
        self._components: dict[str, Component] = {}
        self._update_list: list[Component] = []
        self._fixed_update_list: list[Component] = []
        self._active: bool = True
        self._parent: Optional[Entity] = None
        self._children: list[Entity] = []
        self._tags: set[str] = set()
        self._layer: int = 0
        self._scene: Optional[Scene] = None
        self._prefab_guid: Optional[str] = prefab_guid
        self._prefab_source_id: Optional[str] = None
        self._transform_type: Optional[type] = None
        self._transform: Optional[Component] = None
        self._embed_resources: bool = False
        self._locked: bool = False
        self._system: bool = False

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
            try:
                ch.remove(self)
            except ValueError:
                pass
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
            sc._depth_cache.clear()

    def _invalidate_transform_cache(self):
        comps = self._components
        for c in comps.values():
            c._transform = _UNSET

    def _make_component_key(self, comp: Component) -> str:
        t = type(comp)
        base = t.__name__
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
        comp._entity = self
        comp._key = key
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
        if not clist:
            del self._type_map[cls]
            self._type_name_map.pop(cls.__name__, None)
            if cls.__name__ == "Transform":
                self._transform_type = None
                self._transform = None
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
                self._transform_type = None
                self._transform = None
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
            self._transform_type = None
            self._transform = None
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
                    self._transform_type = None
                    self._transform = None
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
                self._transform_type = None
                self._transform = None
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
            except Exception:
                continue
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
            except Exception:
                continue
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
                except Exception:
                    continue
        return None

    def has_component(self, cls: Type[T]) -> bool:
        if cls in self._type_map:
            return True
        for comp_type in self._type_map:
            try:
                if issubclass(comp_type, cls):
                    return True
            except Exception:
                continue
        return False

    def get_all_components(self) -> list[Component]:
        result = []
        for clist in self._type_map.values():
            result.extend(clist)
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
        d = {
            "id": self._id, "name": self._name, "active": self._active,
            "tags": list(self._tags), "layer": self._layer,
            "parent": self._parent.id if self._parent else None,
            "components": [{"_key": k, **c.serialize()} for k, c in self._components.items()]
        }
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


class ComponentRegistry:
    _registry: dict[str, Type[Component]] = {}
    _aliases: dict[str, str] = {"Sky": "ProceduralSky"}
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
        global _SUBCLASS_CACHE_VERSION
        name = comp_cls.__name__
        cls._registry[name] = comp_cls
        _SUBCLASS_CACHE_VERSION += 1
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
        comp = cls._registry.get(name)
        if comp is None and name:
            alias = cls._aliases.get(name)
            if alias is not None:
                comp = cls._registry.get(alias)
        return comp

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
        self._embed_all: bool = False
        self._compress_resources: bool = False
        self._compress_level = None
        self._embedded_resources: dict = {}
        self._active_update_components: set[Component] = set()
        self._active_fixed_components: set[Component] = set()
        self._update_list_cache: list[Component] = []
        self._fixed_list_cache: list[Component] = []
        self._update_cache_valid: bool = False
        self._fixed_cache_valid: bool = False
        self._update_constraints_cache: list[Component] = []
        self._update_iks_cache: list[Component] = []
        self._update_others_cache: list[Component] = []
        self._update_partition_valid: bool = False
        self._dirty_roots: set = set()
        self._transform_version: int = 0
        self._transform_version_pending: bool = False
        self._last_flushed: list = []
        self._last_flushed_set: set = set()
        self._flushed_overflow: bool = False
        self._depth_cache: dict[str, int] = {}
        self._component_entity_frame_cache: dict = {}
        self._spatial: Octree = Octree(world_size=1000.0)
        self._spatial_dirty: bool = True
        self._spatial_dirty_entities: set[str] = set()
        self._spatial_known_entities: set[str] = set()
        self._roots_cache: list[Entity] = []
        self._roots_cache_valid: bool = False

    def _batch_sync_entities(self, entities: dict[str, Entity]):
        idx = self._component_indices
        auc = self._active_update_components
        afc = self._active_fixed_components
        for eid, e in entities.items():
            is_active = e._active
            for comp_type, clist in e._type_map.items():
                comp_name = comp_type.__name__
                if comp_name not in idx:
                    idx[comp_name] = set()
                idx[comp_name].add(eid)
                if is_active:
                    for comp in clist:
                        if comp.enabled:
                            if comp._updates:
                                auc.add(comp)
                            if comp._fixed_updates:
                                afc.add(comp)
        self._entities_cache_valid = False
        self._roots_cache_valid = False
        self._spatial_dirty = True
        self._spatial_dirty_entities.update(entities.keys())
        self._invalidate_update_cache()
        self._dirty = True
        self._render_version += 1

    def _invalidate_update_cache(self):
        self._update_cache_valid = False
        self._fixed_cache_valid = False
        self._update_partition_valid = False

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

    def _get_partitioned_update(self):
        if self._update_partition_valid:
            return self._update_constraints_cache, self._update_iks_cache, self._update_others_cache
        lst = self._get_update_list()
        CT = self._CONSTRAINT_TYPES
        IK = self._IK_TYPES
        cons = []
        iks = []
        others = []
        ac = cons.append
        ai = iks.append
        ao = others.append
        for c in lst:
            tn = type(c).__name__
            if tn in CT:
                ac(c)
            elif tn in IK:
                ai(c)
            else:
                ao(c)
        self._update_constraints_cache = cons
        self._update_iks_cache = iks
        self._update_others_cache = others
        self._update_partition_valid = True
        return cons, iks, others

    @property
    def _engine(self):
        if self._engine_ref is None:
            from core.engine.engine import Engine
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

    def _get_entity_depth(self, e: Entity) -> int:
        eid = e._id
        cached = self._depth_cache.get(eid)
        if cached is not None:
            return cached
        depth = 0
        p = e._parent
        while p is not None:
            depth += 1
            p = p._parent
        self._depth_cache[eid] = depth
        return depth

    def take_flushed_transforms(self):
        lst = self._last_flushed
        if not lst:
            return lst
        self._last_flushed = []
        try:
            self._last_flushed_set.clear()
        except Exception:
            pass
        return lst

    def peek_flushed_transforms(self):
        return self._last_flushed

    def flush_transforms(self):
        dr = self._dirty_roots
        if not dr:
            if self._transform_version_pending:
                self._transform_version += 1
                self._transform_version_pending = False
            return 0
        if self._transform_version_pending:
            self._transform_version += 1
            self._transform_version_pending = False
        roots = list(dr)
        dr.clear()
        flat = []
        hier = []
        flat_tgt = []
        flat_append = flat.append
        hier_append = hier.append
        flat_tgt_append = flat_tgt.append
        for t in roots:
            if not t._dirty:
                continue
            ent = t._entity
            if ent is None:
                continue
            if ent._parent is not None or ent._children:
                hier_append(t)
            elif t._world_target is not None:
                flat_tgt_append(t)
            else:
                flat_append(t)
        count = 0
        if flat:
            nflat = len(flat)
            if nflat == 1:
                flat[0]._update_world_matrix()
            elif _batch_flat is not None:
                _batch_flat(flat)
            else:
                for t in flat:
                    t._update_world_matrix()
            count += nflat
        if flat_tgt:
            for t in flat_tgt:
                t._update_world_matrix()
            count += len(flat_tgt)
        if hier:
            nhier = len(hier)
            if nhier == 1:
                hier[0]._update_world_matrix()
            else:
                dc = self._depth_cache
                dc_get = dc.get
                for t in hier:
                    e = t._entity
                    if e is None:
                        continue
                    eid = e._id
                    if dc_get(eid) is None:
                        depth = 0
                        p = e._parent
                        while p is not None:
                            depth += 1
                            p = p._parent
                        dc[eid] = depth
                hier.sort(key=self._get_entity_depth_key)
                has_target = False
                for t in hier:
                    if t._world_target is not None:
                        has_target = True
                        break
                if has_target:
                    for t in hier:
                        t._update_world_matrix()
                elif _batch_from_transforms is not None:
                    _batch_from_transforms(hier)
                else:
                    for t in hier:
                        t._update_world_matrix()
            count += nhier
        if count:
            try:
                lf = self._last_flushed
                lfs = self._last_flushed_set
                total = len(lf) + len(flat) + len(flat_tgt) + len(hier)
                if total > 32768:
                    self._last_flushed = []
                    try:
                        lfs.clear()
                    except Exception:
                        pass
                    self._flushed_overflow = True
                else:
                    for t in flat:
                        tid = id(t)
                        if tid not in lfs:
                            lfs.add(tid)
                            lf.append(t)
                    for t in flat_tgt:
                        tid = id(t)
                        if tid not in lfs:
                            lfs.add(tid)
                            lf.append(t)
                    for t in hier:
                        tid = id(t)
                        if tid not in lfs:
                            lfs.add(tid)
                            lf.append(t)
            except Exception:
                pass
        return count

    def _get_entity_depth_key(self, t):
        e = t._entity
        if e is None:
            return 0
        d = self._depth_cache.get(e._id)
        if d is not None:
            return d
        return 0

    def create_entity(self, name: str = "Entity",
                      prefab_guid: Optional[str] = None) -> Entity:
        e = Entity(name, prefab_guid=prefab_guid)
        e._scene = self
        self._entities[e.id] = e
        self._dirty = True
        self._render_version += 1
        self._entities_cache_valid = False
        self._roots_cache_valid = False
        self._spatial_dirty = True
        self._spatial_dirty_entities.add(e.id)
        return e

    def add_entity(self, e: Entity):
        e._scene = self
        self._entities[e.id] = e
        eid = e.id
        idx = self._component_indices
        is_active = e._active
        for comp_type, clist in e._type_map.items():
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
        t = e.transform
        if t and t._dirty:
            self._dirty_roots.add(t)
        self._invalidate_update_cache()
        self._dirty = True
        self._render_version += 1
        self._entities_cache_valid = False
        self._roots_cache_valid = False
        self._spatial_dirty = True
        self._spatial_dirty_entities.add(eid)
        self._spatial_known_entities.discard(eid)

    def remove_entity(self, eid: str):
        e = self._entities.pop(eid, None)
        if not e:
            return
        self._spatial.remove(eid)
        self._spatial_dirty_entities.discard(eid)
        self._spatial_known_entities.discard(eid)
        self._depth_cache.pop(eid, None)
        for child in list(e._children):
            self.remove_entity(child._id)
        auc = self._active_update_components
        afc = self._active_fixed_components
        idx = self._component_indices
        for c in e._components.values():
            c.on_destroy()
        for comp_type, clist in e._type_map.items():
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
        self._roots_cache_valid = False
        self._spatial_dirty = True

    def duplicate_entity(self, entity: Entity, new_name: str = "") -> Entity:
        if entity._scene is not self:
            entity = self.get_entity(entity.id) or entity
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
        idx = self._component_indices
        auc = self._active_update_components
        afc = self._active_fixed_components
        ents = self._entities
        dirty_roots = self._dirty_roots
        sde = self._spatial_dirty_entities
        ske = self._spatial_known_entities
        for new_e in new_entities:
            new_e._scene = self
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
        self._invalidate_update_cache()
        self._dirty = True
        self._render_version += 1
        self._entities_cache_valid = False
        self._roots_cache_valid = False
        self._spatial_dirty = True
        self._rebind_armatures(new_entities, id_map)
        if new_name:
            new_entities[0].name = new_name
        return new_entities[0]

    def _rebind_armatures(self, entities: list, id_map: dict) -> None:
        """Point every copied Armature's bone_entity_ids at the freshly created bone entities."""
        for e in entities:
            arm = e.get_component_by_name("Armature")
            if arm is not None and getattr(arm, "bone_entity_ids", None):
                arm.bone_entity_ids = [id_map.get(bid, bid) for bid in arm.bone_entity_ids]

    def paste_entities(self, clipboard_data: list, registry) -> list:
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
        idx = self._component_indices
        auc = self._active_update_components
        afc = self._active_fixed_components
        ents = self._entities
        dirty_roots = self._dirty_roots
        sde = self._spatial_dirty_entities
        ske = self._spatial_known_entities
        for e in spawned:
            e._scene = self
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
        self._invalidate_update_cache()
        self._dirty = True
        self._render_version += 1
        self._entities_cache_valid = False
        self._roots_cache_valid = False
        self._spatial_dirty = True
        self._rebind_armatures(spawned, id_map)
        return spawned

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
        if not self._roots_cache_valid:
            self._roots_cache = [e for e in self._entities.values() if e._parent is None]
            self._roots_cache_valid = True
        return self._roots_cache

    def get_entities_with_component(self, cls: Type[T]) -> list[Entity]:
        key = cls.__name__
        if _HAS_FAST_QUERY:
            exact = _fast_get(self._component_indices, self._entities, key, self._render_version, self._component_entity_frame_cache)
            sub_names = _subclass_names(key, cls)
            if not sub_names:
                return exact
            seen: set[str] = set()
            merged: list[Entity] = []
            for e in exact:
                if e.id not in seen:
                    seen.add(e.id)
                    merged.append(e)
            for sub_key in sub_names:
                try:
                    sub_ents = _fast_get(self._component_indices, self._entities, sub_key, self._render_version, self._component_entity_frame_cache)
                except Exception:
                    continue
                for e in sub_ents:
                    if e.id not in seen:
                        seen.add(e.id)
                        merged.append(e)
            return merged
        s = self._component_indices.get(key)
        ids: set[str] = set(s) if s else set()
        for sub_key in _subclass_names(key, cls):
            sub = self._component_indices.get(sub_key)
            if sub:
                ids.update(sub)
        if not ids:
            return []
        rv = self._render_version
        cache_tag = (key, rv)
        cc = self._component_entity_frame_cache
        cached = cc.get(cache_tag)
        if cached is not None:
            return cached
        ents = self._entities
        result = [ents[eid] for eid in ids if eid in ents]
        cc[cache_tag] = result
        if len(cc) > 256:
            cc.clear()
            cc[cache_tag] = result
        return result

    def _insert_spatial_single(self, e):
        from core.maths.math3d import Vec3
        tr = e._transform
        if tr is None:
            tr = e.transform
            if tr is None:
                return
        if tr._dirty:
            tr._update_world_matrix()
        d = tr._world_matrix._d
        cx = float(d[3, 0])
        cy = float(d[3, 1])
        cz = float(d[3, 2])
        self._spatial.insert(e._id, AABB(Vec3(cx - 2.5, cy - 2.5, cz - 2.5), Vec3(cx + 2.5, cy + 2.5, cz + 2.5)))

    def rebuild_spatial(self):
        if not self._spatial_dirty:
            return
        self.flush_transforms()
        from core.maths.math3d import Vec3
        try:
            from core.components.rendering.renderers.mesh_filter import MeshFilter as _MF
            from core.components.rendering.renderers.mesh_renderer import MeshRenderer as _MR
        except ImportError:
            _MF = None
            _MR = None
        meshes = None
        try:
            from core.engine.engine import Engine as _Eng
            _eng = _Eng.instance()
            _r = getattr(_eng, "_renderer", None) if _eng else None
            if _r is None and _eng is not None:
                _vp = getattr(_eng, "viewport", None)
                if _vp is not None:
                    _r = getattr(_vp, "_renderer", None)
            if _r is not None:
                meshes = getattr(_r, "_meshes", None)
        except Exception:
            meshes = None
        radius_cache: dict = {}
        spatial = self._spatial
        dirty = self._spatial_dirty_entities
        if dirty and len(dirty) < len(self._entities) * 0.6:
            get_e = self._entities.get
            for eid in list(dirty):
                spatial.remove(eid)
                e = get_e(eid)
                if e is None or not e._active:
                    continue
                tr = e._transform
                if tr is None:
                    tr = e.transform
                    if tr is None:
                        continue
                d = tr._world_matrix._d
                cx = float(d[3, 0])
                cy = float(d[3, 1])
                cz = float(d[3, 2])
                rad = 2.5
                if _MF is not None and meshes is not None:
                    ml = e._type_map.get(_MF)
                    if ml:
                        mf = ml[0]
                        rl = e._type_map.get(_MR)
                        mr = rl[0] if rl else None
                        if mr is not None and mr.enabled:
                            name = mf.mesh_name or "cube"
                            r0 = radius_cache.get(name)
                            if r0 is None:
                                m = meshes.get(name)
                                if m is None and mf.mesh_path:
                                    m = meshes.get(mf.mesh_path)
                                try:
                                    r0 = float(getattr(m, "bounding_radius", 2.5)) if m is not None else 2.5
                                except Exception:
                                    r0 = 2.5
                                radius_cache[name] = r0
                            try:
                                sx = d[0, 0] * d[0, 0] + d[1, 0] * d[1, 0] + d[2, 0] * d[2, 0]
                                sy = d[0, 1] * d[0, 1] + d[1, 1] * d[1, 1] + d[2, 1] * d[2, 1]
                                sz = d[0, 2] * d[0, 2] + d[1, 2] * d[1, 2] + d[2, 2] * d[2, 2]
                                ms = sx
                                if sy > ms:
                                    ms = sy
                                if sz > ms:
                                    ms = sz
                                ms = ms ** 0.5
                            except Exception:
                                ms = 1.0
                            rad = r0 * ms + 0.5
                spatial.insert(eid, AABB(Vec3(cx - rad, cy - rad, cz - rad), Vec3(cx + rad, cy + rad, cz + rad)))
            dirty.clear()
            if not dirty:
                self._spatial_dirty = False
            return
        self._spatial.clear()
        self._spatial_known_entities.clear()
        known_add = self._spatial_known_entities.add
        for e in self._ensure_entities_cache():
            if not e._active:
                continue
            tr = e._transform
            if tr is None:
                tr = e.transform
                if tr is None:
                    continue
            d = tr._world_matrix._d
            cx = float(d[3, 0])
            cy = float(d[3, 1])
            cz = float(d[3, 2])
            rad = 2.5
            if _MF is not None and meshes is not None:
                ml = e._type_map.get(_MF)
                if ml:
                    mf = ml[0]
                    rl = e._type_map.get(_MR)
                    mr = rl[0] if rl else None
                    if mr is not None and mr.enabled:
                        name = mf.mesh_name or "cube"
                        r0 = radius_cache.get(name)
                        if r0 is None:
                            m = meshes.get(name)
                            if m is None and mf.mesh_path:
                                m = meshes.get(mf.mesh_path)
                            try:
                                r0 = float(getattr(m, "bounding_radius", 2.5)) if m is not None else 2.5
                            except Exception:
                                r0 = 2.5
                            radius_cache[name] = r0
                        try:
                            sx = d[0, 0] * d[0, 0] + d[1, 0] * d[1, 0] + d[2, 0] * d[2, 0]
                            sy = d[0, 1] * d[0, 1] + d[1, 1] * d[1, 1] + d[2, 1] * d[2, 1]
                            sz = d[0, 2] * d[0, 2] + d[1, 2] * d[1, 2] + d[2, 2] * d[2, 2]
                            ms = sx
                            if sy > ms:
                                ms = sy
                            if sz > ms:
                                ms = sz
                            ms = ms ** 0.5
                        except Exception:
                            ms = 1.0
                        rad = r0 * ms + 0.5
            spatial.insert(e._id, AABB(Vec3(cx - rad, cy - rad, cz - rad), Vec3(cx + rad, cy + rad, cz + rad)))
            known_add(e._id)
        dirty.clear()
        self._spatial_dirty = False

    def spatial_query(self, aabb: AABB) -> list[str]:
        if self._spatial_dirty:
            self.rebuild_spatial()
        return self._spatial.query(aabb)

    def spatial_raycast(self, origin: 'Vec3', direction: 'Vec3', max_dist: float = 100.0) -> list[tuple[str, float]]:
        if self._spatial_dirty:
            self.rebuild_spatial()
        return self._spatial.raycast(origin, direction, max_dist)

    def mark_spatial_dirty(self):
        self._spatial_dirty = True

    def _rebuild_component_index(self, comp_cls_name: str):
        indices: set[str] = set()
        for eid, e in self._entities.items():
            for t in e._type_map:
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

    _CONSTRAINT_TYPES = frozenset({
        "PositionConstraint", "RotationConstraint", "ScaleConstraint",
        "ParentConstraint", "MoveTowardsConstraint", "RotateTowardsConstraint",
        "ScaleToConstraint", "AimConstraint", "LookAtConstraint",
        "FollowTransformConstraint",
    })

    _IK_TYPES = frozenset({
        "TwoBoneIK", "FABRIKChain",
    })

    def update(self, dt: float):
        prof = self._get_profiler()
        if prof is None:
            return
        prof.start("scene_update")
        log_error = None
        constraints, iks, others = self._get_partitioned_update()
        if not constraints and not iks and not others:
            prof.stop("scene_update")
            return
        if constraints:
            if _batch_constraints is not None:
                try:
                    _batch_constraints(constraints, dt)
                except Exception as ex:
                    if log_error is None:
                        from core.foundation.logger import Logger
                        log_error = Logger.error
                    log_error(f"Constraint batch update error: {ex}")
            else:
                for c in constraints:
                    try:
                        c.on_update(dt)
                    except Exception as ex:
                        if log_error is None:
                            from core.foundation.logger import Logger
                            log_error = Logger.error
                        ent = c._entity
                        log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
        for c in others:
            try:
                c.on_update(dt)
            except Exception as ex:
                if log_error is None:
                    from core.foundation.logger import Logger
                    log_error = Logger.error
                ent = c._entity
                log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
        if iks:
            if _batch_ik is not None:
                try:
                    _batch_ik(iks, dt)
                except Exception as ex:
                    if log_error is None:
                        from core.foundation.logger import Logger
                        log_error = Logger.error
                    log_error(f"IK batch update error: {ex}")
                    for c in iks:
                        try:
                            c.on_update(dt)
                        except Exception as ex2:
                            if log_error is None:
                                from core.foundation.logger import Logger
                                log_error = Logger.error
                            ent = c._entity
                            log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex2}")
            else:
                for c in iks:
                    try:
                        c.on_update(dt)
                    except Exception as ex:
                        if log_error is None:
                            from core.foundation.logger import Logger
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
                    from core.foundation.logger import Logger
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
                    from core.foundation.logger import Logger
                    Logger.error(f"Start error: {ex}")
        prof.stop("scene_start")

    def serialize(self) -> dict:
        data = {"name": self._name, "entities": {eid: e.serialize() for eid, e in self._entities.items()}}
        if self._embed_all:
            data["embed_all"] = True
        if self._compress_resources:
            data["compress_resources"] = True
        if self._compress_level is not None:
            data["compress_level"] = self._compress_level
        prof = self._get_profiler()
        if prof is not None:
            prof.set_value("scene_serialize", 0)
        return data

    @property
    def compress_resources(self) -> bool:
        return self._compress_resources

    @compress_resources.setter
    def compress_resources(self, v: bool):
        if self._compress_resources == bool(v):
            return
        self._compress_resources = bool(v)
        self._render_version += 1

    @property
    def compress_level(self):
        return self._compress_level

    @compress_level.setter
    def compress_level(self, v):
        self._compress_level = int(v) if isinstance(v, bool) else v

    @property
    def embed_all(self) -> bool:
        return self._embed_all

    @embed_all.setter
    def embed_all(self, v: bool):
        if self._embed_all == bool(v):
            return
        self._embed_all = bool(v)
        self._render_version += 1

    @property
    def embedded_resources(self) -> dict:
        return self._embedded_resources

    @embedded_resources.setter
    def embedded_resources(self, v: dict):
        self._embedded_resources = v or {}

    @classmethod
    def deserialize(cls, data: dict, registry: ComponentRegistry) -> Scene:
        s = cls(data["name"])
        s._embed_all = bool(data.get("embed_all", False))
        s._compress_resources = bool(data.get("compress_resources", False))
        s._compress_level = data.get("compress_level")
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
                e.set_parent(entities[pid], preserve_world=False)
            s._entities[e.id] = e
            e._scene = s
        s._batch_sync_entities(entities)
        return s
