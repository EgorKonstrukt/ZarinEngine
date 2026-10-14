# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import gc
from typing import Any, Optional, Type, TypeVar
import numpy as np
from core.spatial import Octree
from . import query as _query
from . import scene_spatial as _spatial
from . import scene_serialize as _serial
from .entity import Entity
from .registry import _subclass_names
T = TypeVar("T", bound="Component")


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
        self._soa_world = np.zeros((0, 4, 4), dtype=np.float64)
        self._soa_cap: int = 0
        self._soa_free: list = []
        self._soa_used: int = 0
        self._soa_epoch: int = 0
    def _soa_ensure(self, need: int):
        if need <= self._soa_cap:
            return
        grown = self._soa_cap if self._soa_cap else 256
        while grown < need:
            grown <<= 1
        fresh = np.zeros((grown, 4, 4), dtype=np.float64)
        if self._soa_cap:
            fresh[:self._soa_cap] = self._soa_world
        self._soa_world = fresh
        self._soa_cap = grown
    def _soa_alloc_for(self, tr):
        try:
            cur = tr._soa
        except Exception:
            return -1
        if cur is not None and cur >= 0 and cur < self._soa_cap:
            try:
                self._soa_world[cur] = tr._world_matrix._d
            except Exception:
                pass
            return cur
        free = self._soa_free
        if free:
            idx = free.pop()
            self._soa_epoch += 1
        else:
            idx = self._soa_used
            self._soa_used = idx + 1
            self._soa_ensure(idx + 1)
            self._soa_epoch += 1
        try:
            tr._soa = idx
        except Exception:
            if free is not None:
                free.append(idx)
            return -1
        try:
            self._soa_world[idx] = tr._world_matrix._d
        except Exception:
            pass
        return idx
    def _soa_release(self, tr):
        try:
            idx = tr._soa
        except Exception:
            return
        if idx is None or idx < 0:
            return
        try:
            tr._soa = -1
        except Exception:
            pass
        try:
            if idx < self._soa_cap:
                self._soa_free.append(idx)
                self._soa_epoch += 1
        except Exception:
            pass
    def _soa_needed(self):
        ci = self._component_indices
        if ci.get("Armature"):
            return True
        if ci.get("SkinnedMeshRenderer"):
            return True
        return False
    def _soa_sync_one(self, tr):
        slot = tr._soa
        if slot < 0 or slot >= self._soa_cap:
            return
        self._soa_world[slot] = tr._world_matrix._d
    def _soa_sync_many(self, transforms):
        world = self._soa_world
        cap = self._soa_cap
        for tr in transforms:
            if tr._dirty:
                continue
            slot = tr._soa
            if slot < 0 or slot >= cap:
                continue
            world[slot] = tr._world_matrix._d
    def _soa_sync_many_flushed(self, transforms):
        world = self._soa_world
        cap = self._soa_cap
        for tr in transforms:
            slot = tr._soa
            if slot < 0 or slot >= cap:
                continue
            world[slot] = tr._world_matrix._d
    def _soa_write_world(self, tr):
        idx = tr._soa
        if idx < 0 or idx >= self._soa_cap:
            return
        self._soa_world[idx] = tr._world_matrix._d
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
        self._render_version += 1
    def _invalidate_update_cache(self):
        self._update_cache_valid = False
        self._fixed_cache_valid = False
        self._update_partition_valid = False
    def _get_update_list(self) -> list[Component]:
        return _query.cached_update_list(self)
    def _get_fixed_list(self) -> list[Component]:
        return _query.cached_fixed_list(self)
    def _get_partitioned_update(self):
        return _query.partitioned_update(self)
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
        self._render_version += 1
    @property
    def path(self) -> Optional[str]: return self._path
    @path.setter
    def path(self, v: str): self._path = v
    @property
    def dirty(self) -> bool: return self._dirty
    def mark_dirty(self): self._dirty = True; self._render_version += 1
    def mark_clean(self): self._dirty = False
    def _get_entity_depth(self, e: Entity) -> int:
        return _spatial._get_entity_depth(self, e)
    def take_flushed_transforms(self):
        return _spatial.take_flushed_transforms(self)
    def peek_flushed_transforms(self):
        return _spatial.peek_flushed_transforms(self)
    def flush_transforms(self):
        return _spatial.flush_transforms(self)
    def _get_entity_depth_key(self, t):
        return _spatial._get_entity_depth_key(self, t)
    def create_entity(self, name: str = "Entity", prefab_guid: Optional[str] = None) -> Entity:
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
            try:
                if getattr(c, "_soa", -1) >= 0:
                    self._soa_release(c)
            except Exception:
                pass
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
        return _serial._duplicate_entity_inner(self, entity, new_name)
    def _rebind_armatures(self, entities: list, id_map: dict) -> None:
        return _serial._rebind_armatures(entities, id_map)
    def paste_entities(self, clipboard_data: list, registry) -> list:
        return _serial._paste_entities_inner(self, clipboard_data, registry)
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
        return _query.query_entities(self, cls, _subclass_names(cls.__name__, cls))
    def _insert_spatial_single(self, e):
        return _spatial._insert_spatial_single(self, e)
    def rebuild_spatial(self):
        return _spatial.rebuild_spatial(self)
    def spatial_query(self, aabb) -> list[str]:
        return _spatial.spatial_query(self, aabb)
    def spatial_raycast(self, origin, direction, max_dist: float = 100.0) -> list:
        return _spatial.spatial_raycast(self, origin, direction, max_dist)
    def mark_spatial_dirty(self):
        return _spatial.mark_spatial_dirty(self)
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
    _CONSTRAINT_TYPES = frozenset({"PositionConstraint", "RotationConstraint", "ScaleConstraint", "ParentConstraint", "MoveTowardsConstraint", "RotateTowardsConstraint", "ScaleToConstraint", "AimConstraint", "LookAtConstraint", "FollowTransformConstraint"})
    _IK_TYPES = frozenset({"TwoBoneIK", "FABRIKChain"})
    def update(self, dt: float):
        return _query.run_update(self, dt)
    def fixed_update(self, dt: float):
        return _query.run_fixed(self, dt)
    def start(self):
        return _query.run_start(self)
    def serialize(self) -> dict:
        gc_enabled = gc.isenabled()
        if gc_enabled:
            gc.disable()
        try:
            return self._serialize_inner()
        finally:
            if gc_enabled:
                gc.enable()
    def _serialize_inner(self) -> dict:
        return _serial._serialize_inner(self)
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
    def deserialize(cls, data: dict, registry) -> Scene:
        gc_enabled = gc.isenabled()
        if gc_enabled:
            gc.disable()
        try:
            return cls._deserialize_inner(data, registry)
        finally:
            if gc_enabled:
                gc.enable()
    @classmethod
    def _deserialize_inner(cls, data: dict, registry) -> Scene:
        return _serial._deserialize_inner(cls, data, registry)
