# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.ecs.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField, ListElementField


def _clamp_weight(value) -> float:
    try:
        w = float(value)
    except (TypeError, ValueError):
        return 0.0
    if w != w or w in (float("inf"), float("-inf")):
        return 0.0
    return w


@ComponentRegistry.register
class BlendShapes(Component):
    _icon = "BlendShapes.png"
    _show_gizmo_icon: bool = False
    _gizmo_icon_label = "B"
    _category = "Mesh"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("shapes", "Blend Shapes", FieldType.LIST, element_fields=[
                ListElementField("name", "Name", FieldType.STRING),
                ListElementField("weight", "Weight", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01),
            ]),
        ]

    def __init__(self):
        super().__init__()
        self.shapes: list[dict] = []
        self._weights_version: int = 0

    @property
    def weight_count(self) -> int:
        return len(self.shapes)

    @property
    def weight_names(self) -> list[str]:
        return [str(s.get("name", "")) for s in self.shapes]

    def _bump(self):
        self._weights_version += 1

    def get_weight(self, name_or_index) -> float:
        if isinstance(name_or_index, int):
            if 0 <= name_or_index < len(self.shapes):
                return _clamp_weight(self.shapes[name_or_index].get("weight", 0.0))
            return 0.0
        key = str(name_or_index)
        for s in self.shapes:
            if str(s.get("name", "")) == key:
                return _clamp_weight(s.get("weight", 0.0))
        return 0.0

    def set_weight(self, name_or_index, value: float) -> bool:
        w = _clamp_weight(value)
        if isinstance(name_or_index, int):
            if 0 <= name_or_index < len(self.shapes):
                if abs(_clamp_weight(self.shapes[name_or_index].get("weight", 0.0)) - w) < 1e-9:
                    return False
                self.shapes[name_or_index]["weight"] = w
                self._bump()
                return True
            return False
        key = str(name_or_index)
        for s in self.shapes:
            if str(s.get("name", "")) == key:
                if abs(_clamp_weight(s.get("weight", 0.0)) - w) < 1e-9:
                    return False
                s["weight"] = w
                self._bump()
                return True
        self.shapes.append({"name": key, "weight": w})
        self._bump()
        return True

    def reset_weights(self) -> bool:
        changed = False
        for s in self.shapes:
            if _clamp_weight(s.get("weight", 0.0)) != 0.0:
                s["weight"] = 0.0
                changed = True
        if changed:
            self._bump()
        return changed

    def sync_with_mesh(self, mesh) -> bool:
        names = list(getattr(mesh, "blendshape_names", []) or [])
        if not names:
            return False
        keep = {}
        for s in self.shapes:
            n = str(s.get("name", ""))
            if n and n not in keep:
                keep[n] = _clamp_weight(s.get("weight", 0.0))
        rebuilt = [{"name": n, "weight": keep.get(n, 0.0)} for n in names]
        if len(rebuilt) == len(self.shapes) and all(
            str(a.get("name")) == b["name"] and abs(_clamp_weight(a.get("weight", 0.0)) - b["weight"]) < 1e-12
            for a, b in zip(self.shapes, rebuilt)
        ):
            return False
        self.shapes = rebuilt
        self._bump()
        return True

    def weights_vector(self, mesh=None) -> list[float]:
        if mesh is not None:
            names = list(getattr(mesh, "blendshape_names", []) or [])
            if names:
                lut = {}
                for s in self.shapes:
                    n = str(s.get("name", ""))
                    if n and n not in lut:
                        lut[n] = _clamp_weight(s.get("weight", 0.0))
                return [lut.get(n, 0.0) for n in names]
        return [_clamp_weight(s.get("weight", 0.0)) for s in self.shapes]

    def get_field_value(self, name: str):
        if name.startswith("weight_"):
            key = name[len("weight_"):]
            if key.isdigit():
                return self.get_weight(int(key))
            return self.get_weight(key)
        return getattr(self, name, None)

    def set_field_value(self, name: str, value) -> None:
        if name.startswith("weight_"):
            key = name[len("weight_"):]
            if key.isdigit():
                self.set_weight(int(key), value)
                return
            self.set_weight(key, value)
            return
        setattr(self, name, value)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "shapes": [{"name": str(s.get("name", "")), "weight": _clamp_weight(s.get("weight", 0.0))} for s in self.shapes],
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> BlendShapes:
        inst = cls()
        inst.enabled = data.get("enabled", True)
        raw = data.get("shapes", [])
        items = []
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict):
                    n = str(entry.get("name", ""))
                    if n:
                        items.append({"name": n, "weight": _clamp_weight(entry.get("weight", 0.0))})
                elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    items.append({"name": str(entry[0]), "weight": _clamp_weight(entry[1])})
        elif isinstance(raw, dict):
            for n, w in raw.items():
                items.append({"name": str(n), "weight": _clamp_weight(w)})
        inst.shapes = items
        return inst
