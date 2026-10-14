# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Any, Optional
from .gizmo_types import GizmoStyle, GizmoPrimitive
from .query import _UNSET
_GIZMO_PASSES: dict[str, list[type[Component]]] = {}
_GIZMO_PASS_ORDER: list[str] = ["collider", "particle", "force_field", "camera", "audio", "light", "script", "nav", "armature"]
_GIZMO_HOOK_CACHE: dict = {}


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
    def live_inspector_fields(self) -> tuple:
        return ()
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
