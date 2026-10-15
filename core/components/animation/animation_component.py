# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from core.ecs import Component, ComponentRegistry
from core.components.animation.animation_clip import AnimationClip


def _as_quat(value):
    from core.maths.math3d import Quat
    if isinstance(value, Quat):
        return value
    try:
        t = tuple(value)
        if len(t) == 4 and all(isinstance(c, (int, float)) for c in t):
            return Quat(t[0], t[1], t[2], t[3])
    except TypeError:
        pass
    return value


def _resolve_bone_path(root, bone_path: str):
    if not bone_path:
        return root
    parts = [p for p in bone_path.split("/") if p]
    if not parts:
        return root
    current = root
    if parts[0] and parts[0] == (getattr(root, "name", "") or ""):
        parts = parts[1:]
    for seg in parts:
        found = None
        for child in (current.children if current is not None else []):
            if child.name == seg:
                found = child
                break
        if found is None:
            return current or root
        current = found
    return current or root


@ComponentRegistry.register
class Animation(Component):
    _updates: bool = True

    def __init__(self):
        super().__init__()
        self.clip: str = ""
        self.play_on_start: bool = True
        self.speed: float = 1.0
        self._time: float = 0.0
        self._is_playing: bool = False
        self._clip_cache: Optional[AnimationClip] = None
        self._prop_cache = None

    @classmethod
    def _inspector_fields(cls):
        from core.components.inspector_meta import InspectorField, FieldType
        return [
            InspectorField("", "Animation", FieldType.HEADER),
            InspectorField("clip", "Animation Clip", FieldType.ASSET, resource_type="animclip"),
            InspectorField("play_on_start", "Play on Start", FieldType.BOOL),
            InspectorField("speed", "Speed", FieldType.FLOAT),
        ]

    def _get_clip(self) -> Optional[AnimationClip]:
        if not self.clip:
            return None
        if self._clip_cache is None:
            self._clip_cache = AnimationClip.load(self.clip)
        return self._clip_cache

    def play(self):
        clip = self._get_clip()
        self._is_playing = True
        if self._time >= (clip.length if clip else 1.0):
            self._time = 0.0

    def stop(self):
        self._is_playing = False

    def pause(self):
        self._is_playing = False

    def on_start(self):
        clip = self._get_clip()
        if self.play_on_start and clip:
            self.play()

    def on_update(self, dt: float):
        clip = self._get_clip()
        if not self._is_playing or not clip:
            return
        self._time += dt * self.speed
        clip_len = clip.length
        if self._time >= clip_len:
            if clip.loop:
                self._time %= clip_len
            else:
                self._time = clip_len
                self._is_playing = False
                return
        self._apply_curves()

    def _apply_curves(self):
        clip = self._get_clip()
        if not clip:
            return
        ent = self._entity
        if ent is None:
            return
        cache = self._prop_cache
        if cache is not None and cache[0] is clip and self._validate_prop_cache(ent, cache[2]):
            if self._apply_cached(clip, cache[1]):
                return
        rows = list(clip.evaluate_all(self._time))
        rots = list(clip.evaluate_rotations_all(self._time))
        for bone_path, prop, value in rows:
            target = _resolve_bone_path(ent, bone_path)
            self._apply_value(target, prop, value)
        for bone_path, prop, quat in rots:
            target = _resolve_bone_path(ent, bone_path)
            self._apply_rotation(target, prop, quat)
        self._build_prop_cache(ent, clip, rows, rots)

    def _validate_prop_cache(self, ent, targets) -> bool:
        try:
            eparent = ent._parent
            for t in targets:
                e = t["eref"]()
                if e is None:
                    return False
                if e.get_component(t["ctype"]) is not t["cref"]():
                    return False
                w = e
                for cid in reversed(t["chain"]):
                    if w is None or w.id != cid:
                        return False
                    w = w._parent
                if w is not eparent:
                    return False
        except Exception:
            return False
        return True

    def _build_prop_cache(self, ent, clip, rows, rots):
        import weakref
        grouped = {}
        index = {}
        targets = []
        for bone_path, prop, _ in list(rows) + list(rots):
            if "/" not in prop:
                continue
            cname, rest = prop.split("/", 1)
            if "." in rest:
                name, leaf = rest.split(".", 1)
            else:
                name, leaf = rest, None
            target = _resolve_bone_path(ent, bone_path)
            if target is None:
                continue
            comp = target.get_component_by_name(cname)
            if comp is None:
                continue
            try:
                chain = []
                e = target
                while e is not None and e is not ent:
                    chain.append(e.id)
                    e = e._parent
                if e is not ent:
                    continue
                chain.append(ent.id)
                chain.reverse()
            except Exception:
                continue
            key = (id(target), cname, name)
            g = grouped.get(key)
            if g is None:
                setter = getattr(comp, "set_field_value", None)
                g = {"eref": weakref.ref(target), "cref": weakref.ref(comp), "ctype": type(comp), "chain": tuple(chain), "name": name, "setter": setter if callable(setter) else None, "leaves": [], "plain": False}
                grouped[key] = g
                targets.append(g)
            if leaf is not None and leaf not in g["leaves"]:
                g["leaves"].append(leaf)
            index[(bone_path, prop)] = (g, leaf)
        self._prop_cache = (clip, index, targets)

    def _apply_cached(self, clip, index) -> bool:
        from core.components.properties import _read_field, _replace_leaf
        grouped = {}
        order = []
        for bone_path, prop, value in list(clip.evaluate_all(self._time)):
            hit = index.get((bone_path, prop))
            if hit is None:
                return False
            g, leaf = hit
            gid = id(g)
            acc = grouped.get(gid)
            if acc is None:
                acc = [g, {}, []]
                grouped[gid] = acc
                order.append(acc)
            if leaf is not None:
                acc[1][leaf] = value
            else:
                acc[2].append(value)
        for bone_path, prop, quat in list(clip.evaluate_rotations_all(self._time)):
            hit = index.get((bone_path, prop))
            if hit is None:
                return False
            g, _ = hit
            gid = id(g)
            acc = grouped.get(gid)
            if acc is None:
                acc = [g, {}, []]
                grouped[gid] = acc
                order.append(acc)
            acc[2].append(_as_quat(quat))
        try:
            for g, leaf_vals, plain_vals in order:
                if leaf_vals and plain_vals:
                    return False
                comp = g["cref"]()
                if comp is None:
                    return False
                if leaf_vals:
                    v = _read_field(comp, g["name"])
                    for leaf, scalar in leaf_vals.items():
                        v = _replace_leaf(v, leaf, scalar)
                        if v is None:
                            return False
                    if g["setter"] is not None:
                        g["setter"](g["name"], v)
                    else:
                        setattr(comp, g["name"], v)
                else:
                    for scalar in plain_vals:
                        if g["setter"] is not None:
                            g["setter"](g["name"], scalar)
                        else:
                            setattr(comp, g["name"], scalar)
        except Exception:
            return False
        return True

    def _apply_value(self, entity, path: str, value: float):
        try:
            from core.components.properties import write_prop
            write_prop(entity, path, value)
        except Exception:
            pass

    def _apply_rotation(self, entity, path: str, quat):
        if entity is None:
            return
        try:
            from core.components.properties import write_prop
            write_prop(entity, path, _as_quat(quat))
        except Exception:
            pass

    def serialize(self) -> dict:
        data = super().serialize()
        data["clip"] = self.clip
        data["play_on_start"] = self.play_on_start
        data["speed"] = self.speed
        data["_time"] = self._time
        data["_is_playing"] = self._is_playing
        return data

    @classmethod
    def deserialize(cls, data: dict) -> Animation:
        inst = super().deserialize(data)
        inst.clip = data.get("clip", "")
        inst.play_on_start = data.get("play_on_start", True)
        inst.speed = data.get("speed", 1.0)
        inst._time = data.get("_time", 0.0)
        inst._is_playing = data.get("_is_playing", False)
        return inst
