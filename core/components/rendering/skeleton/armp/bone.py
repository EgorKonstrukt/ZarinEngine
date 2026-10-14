# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
from typing import Optional
from core.ecs import Component, ComponentRegistry
from core.maths.math3d import Mat4
from core.components.inspector_meta import FieldType, InspectorField


@ComponentRegistry.register
class Bone(Component):
    _icon = "Bone.png"
    _show_gizmo_icon: bool = False
    _gizmo_icon_label = "B"
    _category = "Skinned Mesh"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Bone", FieldType.HEADER),
            InspectorField("bone_name", "Bone Name", FieldType.STRING),
            InspectorField("bone_index", "Bone Index", FieldType.INT),
        ]

    def __init__(self):
        super().__init__()
        self.bone_name: str = ""
        self.bone_index: int = -1

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"bone_name": self.bone_name, "bone_index": self.bone_index})
        return d

    @classmethod
    def deserialize(cls, data: dict) -> Bone:
        b = cls()
        b.enabled = data.get("enabled", True)
        b.bone_name = data.get("bone_name", "")
        b.bone_index = int(data.get("bone_index", -1))
        return b


class _ArmatureBase(Component):
    _icon = "Armature.png"
    _show_gizmo_icon: bool = False
    _gizmo_icon_label = "A"
    _category = "Skinned Mesh"
    _gizmo_pass = "armature"
    _gizmo_bone_color = (1.0, 0.78, 0.22, 1.0)
    _gizmo_root_color = (0.42, 0.9, 1.0, 1.0)

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Armature", FieldType.HEADER),
            InspectorField("bone_count", "Bone Count", FieldType.INT),
            InspectorField("root_bone_name", "Root Bone", FieldType.STRING),
        ]

    def __init__(self):
        super().__init__()
        self.bone_names: list[str] = []
        self.bone_parents: list[int] = []
        self.bone_offset_matrices: list[np.ndarray] = []
        self.bone_bind_local: list[np.ndarray] = []
        self.bone_entity_ids: list[str] = []
        self.root_bone_name: str = ""
        self._skin_flat: Optional[np.ndarray] = None
        self._skin_flat_size: int = 0
        self._skin_mat: Optional[np.ndarray] = None
        self._inv_cache: Optional[np.ndarray] = None
        self._inv_cache_key: int = 0
        self._bone_slots: Optional[np.ndarray] = None
        self._bone_slots_epoch: int = -1
        self._bone_slots_scene = None
        self._bone_slots_ids: tuple = ()
        self._bone_offsets_f64: Optional[np.ndarray] = None
        self._soa_scratch: Optional[tuple] = None

    def setup(self, skeleton) -> None:
        if isinstance(skeleton, dict):
            self.bone_names = list(skeleton.get("bone_names", []))
            self.bone_parents = list(skeleton.get("bone_parents", []))
            self.bone_offset_matrices = [np.array(m, dtype=np.float32) for m in skeleton.get("bone_offset_matrices", [])]
            self.bone_bind_local = [np.array(m, dtype=np.float32) for m in skeleton.get("bone_bind_local", [])]
        else:
            self.bone_names = list(getattr(skeleton, "bone_names", []))
            self.bone_parents = list(getattr(skeleton, "bone_parents", []))
            self.bone_offset_matrices = [np.array(m, dtype=np.float32) for m in getattr(skeleton, "bone_offset_matrices", [])]
            self.bone_bind_local = [np.array(m, dtype=np.float32) for m in getattr(skeleton, "bone_bind_local", [])]
        self.bone_entity_ids = [""] * len(self.bone_names)
        for name in self.bone_names:
            idx = self.bone_names.index(name)
            if self.bone_parents[idx] < 0:
                self.root_bone_name = name
                break
        self._bone_slots = None
        self._bone_slots_epoch = -1
        self._bone_slots_scene = None
        self._bone_slots_ids = ()
        self._bone_offsets_f64 = None
        self._soa_scratch = None

    def create_bone_entities(self, scene, root_entity) -> None:
        from core.components import Transform
        n = len(self.bone_names)
        if n == 0:
            return
        entities: list = [None] * n
        for i in range(n):
            be = scene.create_entity(self.bone_names[i])
            bt = Transform()
            local = Mat4(self.bone_bind_local[i])
            pos, rot, scale = local.decompose()
            bt.local_position = pos
            bt.local_rotation = rot
            bt.local_scale = scale
            be.add_component(bt)
            bn = Bone()
            bn.bone_name = self.bone_names[i]
            bn.bone_index = i
            be.add_component(bn)
            entities[i] = be
        for i in range(n):
            parent_idx = self.bone_parents[i]
            parent_ent = None
            if parent_idx >= 0 and parent_idx < n:
                parent_ent = entities[parent_idx]
            else:
                parent_ent = root_entity
            if parent_ent is not None and entities[i] is not None:
                entities[i].set_parent(parent_ent, preserve_world=False)
            self.bone_entity_ids[i] = entities[i].id if entities[i] is not None else ""

    @property
    def bone_count(self) -> int:
        return len(self.bone_names)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "bone_names": self.bone_names,
            "bone_parents": self.bone_parents,
            "bone_offset_matrices": [m.tolist() for m in self.bone_offset_matrices],
            "bone_bind_local": [m.tolist() for m in self.bone_bind_local],
            "bone_entity_ids": self.bone_entity_ids,
            "root_bone_name": self.root_bone_name,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> Armature:
        a = cls()
        a.enabled = data.get("enabled", True)
        a.bone_names = list(data.get("bone_names", []))
        a.bone_parents = list(data.get("bone_parents", []))
        a.bone_offset_matrices = [np.array(m, dtype=np.float32) for m in data.get("bone_offset_matrices", [])]
        a.bone_bind_local = [np.array(m, dtype=np.float32) for m in data.get("bone_bind_local", [])]
        a.bone_entity_ids = list(data.get("bone_entity_ids", [""] * len(a.bone_names)))
        a.root_bone_name = data.get("root_bone_name", "")
        if len(a.bone_entity_ids) != len(a.bone_names):
            a.bone_entity_ids = [""] * len(a.bone_names)
        return a
