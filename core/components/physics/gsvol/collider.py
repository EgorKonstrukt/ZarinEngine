# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from core.ecs import Component, ComponentRegistry, GizmoPrimitive
from core.maths.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
from .volume import get_volume_boxes, _volume_box_edges_np, _cython_occupancy, _cython_merge


@ComponentRegistry.register
class GSVolumeCollider(Component):
    _icon = "BoxCollider.png"
    _allow_multiple = True
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False
    _gizmo_pass = "collider"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Gs Volume Collider", FieldType.HEADER),
            InspectorField("ply_path", "Splat Path", FieldType.RESOURCE_PATH,
                           file_filter="Splats (*.ply *.sog *.ssog)"),
            InspectorField("voxel_size", "Voxel Size", FieldType.FLOAT,
                           min_val=0.02, max_val=4.0, step=0.05, decimals=3),
            InspectorField("opacity_threshold", "Opacity Cutoff", FieldType.FLOAT,
                           min_val=0.0, max_val=1.0, step=0.01),
            InspectorField("dilation", "Dilation", FieldType.INT,
                           min_val=0, max_val=3, step=1, decimals=0),
            InspectorField("max_boxes", "Max Boxes", FieldType.INT,
                           min_val=64, max_val=16384, step=64, decimals=0),
            InspectorField("center", "Center", FieldType.VEC3),
            InspectorField("layer", "Layer", FieldType.LAYER),
            InspectorField("mask", "Collision Mask", FieldType.LAYER_MASK),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
            InspectorField("physic_material", "Physic Material", FieldType.ASSET, resource_type="physicmaterial"),
        ]

    def __init__(self):
        super().__init__()
        self.ply_path: str = ""
        self.voxel_size: float = 0.25
        self.opacity_threshold: float = 0.05
        self.dilation: int = 1
        self.max_boxes: int = 2048
        self.center: Vec3 = Vec3.zero()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.is_trigger: bool = False
        self.physic_material: str = ""
        self.material_friction: float = 0.6
        self.material_bounciness: float = 0.0

    def _volume_key(self):
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        return (self.ply_path, float(self.voxel_size), float(self.opacity_threshold),
                int(self.dilation), int(self.max_boxes), c.x, c.y, c.z)

    def volume_boxes(self):
        if _cython_occupancy is None or _cython_merge is None:
            return np.zeros((0, 6), dtype=np.float32)
        try:
            return get_volume_boxes(self.ply_path, float(self.voxel_size),
                                    float(self.opacity_threshold), int(self.dilation),
                                    int(self.max_boxes))
        except Exception:
            return np.zeros((0, 6), dtype=np.float32)

    def collider_shapes(self, transform=None):
        from core.physics.shapep import resolve_physics_material
        boxes = self.volume_boxes()
        if boxes is None or len(boxes) == 0:
            return []
        if transform is not None:
            s = transform.local_scale
        else:
            s = Vec3.one()
        try:
            sx, sy, sz = float(s.x), float(s.y), float(s.z)
        except Exception:
            sx = sy = sz = 1.0
        if abs(sx) < 1e-9:
            sx = 1.0
        if abs(sy) < 1e-9:
            sy = 1.0
        if abs(sz) < 1e-9:
            sz = 1.0
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        try:
            mat = resolve_physics_material(self)
        except Exception:
            mat = {"path": "", "dynamic_friction": 0.6, "static_friction": 0.6,
                   "bounciness": 0.0, "friction_combine": 1, "bounce_combine": 1}
        try:
            friction = float(mat.get("dynamic_friction", 0.6))
            restitution = float(mat.get("bounciness", 0.0))
        except Exception:
            friction = 0.6
            restitution = 0.0
        out = []
        for b in boxes:
            cx = (float(b[0]) + float(b[3])) * 0.5 + c.x
            cy = (float(b[1]) + float(b[4])) * 0.5 + c.y
            cz = (float(b[2]) + float(b[5])) * 0.5 + c.z
            out.append({
                "cname": "GSVolumeCollider",
                "type": "box",
                "params": {
                    "size": [max((float(b[3]) - float(b[0])) * sx, 1e-4),
                             max((float(b[4]) - float(b[1])) * sy, 1e-4),
                             max((float(b[5]) - float(b[2])) * sz, 1e-4)],
                    "center": [cx * sx, cy * sy, cz * sz],
                },
                "friction": friction,
                "restitution": restitution,
                "material": mat,
                "is_trigger": bool(self.is_trigger),
                "layer": int(self.layer),
                "mask": int(self.mask),
            })
        return out

    def _gizmo_sig(self):
        tr = self.transform
        if tr is None:
            return None
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        return (
            self._volume_key(),
            tr.local_position.x, tr.local_position.y, tr.local_position.z,
            tr.local_rotation.x, tr.local_rotation.y, tr.local_rotation.z, tr.local_rotation.w,
            tr.local_scale.x, tr.local_scale.y, tr.local_scale.z,
        )

    def gizmo_primitives(self):
        tr = self.transform
        if not tr:
            return None
        boxes = self.volume_boxes()
        if boxes is None or len(boxes) == 0:
            return None
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        co = np.array([c.x, c.y, c.z], dtype=np.float32)
        mins = boxes[:, 0:3].astype(np.float32) + co
        maxs = boxes[:, 3:6].astype(np.float32) + co
        if len(mins) > 4000:
            step = int((len(mins) + 3999) // 4000)
            mins = mins[::step]
            maxs = maxs[::step]
        from core.components.physics.meshcol import _edge_pairs_np
        edge_verts = _volume_box_edges_np(mins, maxs)
        color = [0.0, 1.0, 0.0, 0.6]
        return _edge_pairs_np(edge_verts, color, tr.local_position, tr.local_rotation, tr.local_scale)

    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        prim = self.gizmo_primitives()
        if prim is None:
            return []
        s, e, c = prim
        n = s.shape[0]
        color = [float(c[0, 0]), float(c[0, 1]), float(c[0, 2]), float(c[0, 3])]
        result = []
        for i in range(n):
            result.append((
                Vec3(float(s[i, 0]), float(s[i, 1]), float(s[i, 2])),
                Vec3(float(e[i, 0]), float(e[i, 1]), float(e[i, 2])),
                color,
            ))
        return result

    def gizmo(self):
        try:
            from core.engine.eng import Engine
            from core.components.physics.rigidbody import Rigidbody
            eng = Engine.instance()
            if eng and getattr(eng, 'play_mode', False) and self.entity:
                if self.entity.get_component(Rigidbody):
                    return []
            if eng:
                vp = eng.viewport
                cam = getattr(vp, '_cam', None) if vp else None
                cam_pos = cam.position if cam else None
                if cam_pos and self.entity:
                    tr = self.transform
                    if tr and (tr.position - cam_pos).length() > 20.0:
                        return []
        except Exception:
            pass
        prims = self.gizmo_primitives()
        if prims is None:
            return []
        s, e, c = prims
        if s.shape[0] == 0:
            return []
        return [GizmoPrimitive(s, e, c)]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "ply_path": self.ply_path,
            "voxel_size": float(self.voxel_size),
            "opacity_threshold": float(self.opacity_threshold),
            "dilation": int(self.dilation),
            "max_boxes": int(self.max_boxes),
            "center": self.center.to_list(),
            "is_trigger": self.is_trigger,
            "friction": self.material_friction,
            "bounciness": self.material_bounciness,
            "physic_material": self.physic_material,
            "layer": self.layer, "mask": self.mask,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> GSVolumeCollider:
        g = cls()
        g.enabled = data.get("enabled", True)
        g.ply_path = data.get("ply_path", "") or ""
        g.voxel_size = float(data.get("voxel_size", 0.25))
        g.opacity_threshold = float(data.get("opacity_threshold", 0.05))
        g.dilation = int(data.get("dilation", 1))
        g.max_boxes = int(data.get("max_boxes", 2048))
        g.center = Vec3(*data.get("center", [0, 0, 0]))
        g.is_trigger = data.get("is_trigger", False)
        g.material_friction = data.get("friction", 0.6)
        g.material_bounciness = data.get("bounciness", 0.0)
        g.physic_material = data.get("physic_material", "") or ""
        g.layer = data.get("layer", 0)
        g.mask = data.get("mask", 0xFFFF)
        return g
