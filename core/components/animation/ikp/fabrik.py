# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import List
import math
from core.ecs import ComponentRegistry
from core.components.inspector_meta import InspectorField, FieldType, ListElementField
from core.components.animation.ikp.ccd import _IKBase
from core.components.animation.ikp.ccd import _quat_mul, _quat_from_two_vecs, _world_quat, _parent_world_quat, _quat_to_local, _apply_local_py

@ComponentRegistry.register
class FABRIKChain(_IKBase):

    def __init__(self):
        super().__init__()
        self.root_bone: str = ""
        self.bones: List[str] = []
        self.chain_length: int = 0
        self.iterations: int = 8
        self.tolerance: float = 1e-4
        self.bone_weights: List[float] = []

    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("", "Chain", FieldType.HEADER),
            InspectorField("root_bone", "Root Bone", FieldType.STRING),
            InspectorField(
                "bones",
                "Bones",
                FieldType.LIST,
                element_fields=[
                    ListElementField("", "Bone", FieldType.STRING),
                ],
            ),
            InspectorField("chain_length", "Chain Length", FieldType.INT),
            InspectorField("", "Target", FieldType.HEADER),
            InspectorField("target_entity_id", "Target", FieldType.GAMEOBJECT),
            InspectorField("target_position", "Target Pos", FieldType.VEC3),
            InspectorField("pole_entity_id", "Pole", FieldType.GAMEOBJECT),
            InspectorField("pole_position", "Pole Pos", FieldType.VEC3),
            InspectorField("", "Solver", FieldType.HEADER),
            InspectorField("iterations", "Iterations", FieldType.INT),
            InspectorField("tolerance", "Tolerance", FieldType.FLOAT),
            InspectorField(
                "bone_weights",
                "Bone Weights",
                FieldType.LIST,
                element_fields=[ListElementField("", "Weight", FieldType.FLOAT, 0.0, 1.0, 0.01, 2)],
            ),
            InspectorField("weight", "Weight", FieldType.FLOAT, 0.0, 1.0, 0.01, 2),
        ]

    def _bones(self):
        ent = self._entity
        if ent is None:
            return []
        root = self._resolve_bone(self.root_bone)
        if root is None:
            return []
        if self.bones:
            return [self._resolve_bone(p) for p in self.bones]
        out = [root]
        cur = root
        for _ in range(1, max(self.chain_length, 1)):
            if not cur._children:
                break
            cur = cur._children[0]
            out.append(cur)
        return out

    def on_update(self, dt: float):
        try:
            from core._ik import batch_update_ik
            batch_update_ik([self], dt)
            return
        except ImportError:
            pass
        self._solve_python()

    def _solve_python(self):
        bones = [b for b in self._bones()]
        if len(bones) < 2 or any(b is None or b.transform is None for b in bones):
            return
        target = self._target_world()
        if target is None:
            return
        pts = np_points([b.transform.position for b in bones])
        res = _fabrik_positions_py(pts, target, self.iterations, self.tolerance)
        pole = self._pole_world()
        _apply_fabrik_py(bones, res, pole, self.weight, self.bone_weights)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update(self._base_serialize({}))
        d.update({
            "root_bone": self.root_bone,
            "bones": list(self.bones),
            "chain_length": self.chain_length,
            "iterations": self.iterations,
            "tolerance": self.tolerance,
            "bone_weights": list(self.bone_weights),
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> FABRIKChain:
        inst = cls()
        inst.enabled = data.get("enabled", True)
        _IKBase._base_deserialize(inst, data)
        inst.root_bone = data.get("root_bone", "")
        inst.bones = list(data.get("bones", []))
        inst.chain_length = int(data.get("chain_length", 0))
        inst.iterations = int(data.get("iterations", 8))
        inst.tolerance = float(data.get("tolerance", 1e-4))
        inst.bone_weights = [float(x) for x in data.get("bone_weights", [])]
        return inst

def np_points(vecs):
    return [[v.x, v.y, v.z] for v in vecs]

def _fabrik_positions_py(points, target, iterations, tolerance):
    import numpy as np
    P = np.asarray(points, dtype=np.float64).copy()
    n = P.shape[0]
    if n < 2:
        return P
    T = np.asarray([target.x, target.y, target.z], dtype=np.float64)
    lens = np.sqrt(((P[1:] - P[:-1]) ** 2).sum(axis=1))
    lens = np.maximum(lens, 1e-10)
    base = P[0].copy()
    total = lens.sum()
    d0 = np.linalg.norm(T - base)
    if d0 >= total:
        dirn = (T - base) / d0
        ts = total * np.arange(n) / (n - 1)
        return base[None, :] + dirn[None, :] * ts[:, None]
    for _ in range(iterations):
        P[-1] = T
        for i in range(n - 2, -1, -1):
            d = P[i + 1] - P[i]
            nrm = np.linalg.norm(d)
            d = d / nrm if nrm > 1e-10 else d
            P[i] = P[i + 1] - d * lens[i]
        P[0] = base
        for i in range(n - 1):
            d = P[i + 1] - P[i]
            nrm = np.linalg.norm(d)
            d = d / nrm if nrm > 1e-10 else d
            P[i + 1] = P[i] + d * lens[i]
        if np.linalg.norm(P[-1] - T) < tolerance:
            break
    return P

def _apply_fabrik_py(bones, new_pts, pole, weight, bone_weights):
    n = len(bones)
    old_pos = [b.transform.position for b in bones]
    old_wq = [_world_quat(b.transform) for b in bones]
    parent_wq = _parent_world_quat(bones[0])
    for i in range(n - 1):
        d0 = (
            old_pos[i + 1].x - old_pos[i].x,
            old_pos[i + 1].y - old_pos[i].y,
            old_pos[i + 1].z - old_pos[i].z,
        )
        d1 = (
            new_pts[i + 1][0] - new_pts[i][0],
            new_pts[i + 1][1] - new_pts[i][1],
            new_pts[i + 1][2] - new_pts[i][2],
        )
        d0 = _two_denorm(d0)
        d1 = _two_denorm(d1)
        newwq = _quat_mul(_quat_from_two_vecs(d0, d1), old_wq[i])
        local = _quat_to_local(parent_wq, newwq)
        w = weight
        if bone_weights and i < len(bone_weights):
            w = weight * bone_weights[i]
        _apply_local_py(bones[i].transform, local, w)
        parent_wq = newwq

def _two_denorm(v):
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    return tuple(x / n for x in v) if n > 1e-10 else v
