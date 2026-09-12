# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import numpy as np
from collections import OrderedDict
from typing import Optional
from core.ecs.ecs import Component, ComponentRegistry, GizmoPrimitive
from core.maths.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField


_MAX_CELLS = 12000000
_MERGE_CAP = 65536
_CACHE_SIZE = 8

try:
    from core._gs_volume import splat_occupancy as _cython_occupancy
    from core._gs_volume import dilate26 as _cython_dilate
    from core._gs_volume import greedy_merge_boxes as _cython_merge
except Exception:
    _cython_occupancy = None
    _cython_dilate = None
    _cython_merge = None


_VOLUME_CACHE: OrderedDict = OrderedDict()


def _volume_cache_get(key):
    entry = _VOLUME_CACHE.get(key)
    if entry is None:
        return None
    _VOLUME_CACHE.move_to_end(key)
    return entry


def _volume_cache_set(key, value):
    _VOLUME_CACHE[key] = value
    _VOLUME_CACHE.move_to_end(key)
    while len(_VOLUME_CACHE) > _CACHE_SIZE:
        _VOLUME_CACHE.popitem(last=False)


def _resolve_ply_path(path: str) -> Optional[str]:
    if not path:
        return None
    if os.path.isfile(path):
        return os.path.abspath(path)
    try:
        from core.engine.engine import Engine
        eng = Engine.instance()
        root = eng.project_root if eng and getattr(eng, "project_root", None) else os.getcwd()
    except Exception:
        root = os.getcwd()
    base = os.path.basename(path)
    for cand in (os.path.join(root, path), os.path.join(root, "assets", base)):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def _file_sig(resolved: str):
    try:
        st = os.stat(resolved)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return (0, 0)


def _build_volume_boxes(resolved: str, voxel: float, thr: float, dilation: int, max_boxes: int):
    try:
        from core.renderer.gaussian_splat_renderer import try_get_splat_arrays
        shared = try_get_splat_arrays(resolved)
    except Exception:
        shared = None
    if shared is not None:
        try:
            pos = np.ascontiguousarray(shared[0], dtype=np.float32)
            scl = np.ascontiguousarray(shared[1], dtype=np.float32)
            opa = np.ascontiguousarray(shared[2], dtype=np.float32).reshape(-1)
            return _boxes_from_arrays(pos, scl, opa, voxel, thr, dilation, max_boxes)
        except Exception:
            pass
    from core.assets.ply_loader import load_ply_gaussian_splat
    data = load_ply_gaussian_splat(resolved)
    if data is None or data.num_splats == 0:
        return np.zeros((0, 6), dtype=np.float32)
    try:
        pos = np.ascontiguousarray(data.positions, dtype=np.float32)
        scl = np.ascontiguousarray(data.scales, dtype=np.float32)
        opa = np.ascontiguousarray(data.opacity.reshape(-1), dtype=np.float32)
    except Exception:
        return np.zeros((0, 6), dtype=np.float32)
    return _boxes_from_arrays(pos, scl, opa, voxel, thr, dilation, max_boxes)


def _boxes_from_arrays(pos, scl, opa, voxel: float, thr: float, dilation: int, max_boxes: int):
    try:
        keep = np.isfinite(pos).all(axis=1) & np.isfinite(scl).all(axis=1) & (opa >= np.float32(thr))
    except Exception:
        return np.zeros((0, 6), dtype=np.float32)
    if not bool(keep.any()):
        return np.zeros((0, 6), dtype=np.float32)
    pts = pos[keep]
    try:
        mins = pts.min(axis=0).astype(np.float64)
        maxs = pts.max(axis=0).astype(np.float64)
    except Exception:
        return np.zeros((0, 6), dtype=np.float32)
    if not bool(np.isfinite(mins).all() and np.isfinite(maxs).all()):
        return np.zeros((0, 6), dtype=np.float32)
    vx = float(voxel)
    for _ in range(5):
        pad = (int(dilation) + 1) * vx
        origin = mins - pad
        dims = np.ceil((maxs - origin) / vx).astype(np.int64)
        dims = np.maximum(dims, 1)
        if int(dims.prod()) <= _MAX_CELLS:
            break
        vx *= 2.0
    for _ in range(4):
        origin = mins - (int(dilation) + 1) * vx
        dims = np.maximum(np.ceil((maxs - origin) / vx).astype(np.int64), 1)
        nx, ny, nz = int(dims[0]), int(dims[1]), int(dims[2])
        if nx * ny * nz > _MAX_CELLS:
            vx *= 2.0
            continue
        occ = np.zeros(nx * ny * nz, dtype=np.uint8)
        try:
            _cython_occupancy(
                np.ascontiguousarray(pos, dtype=np.float32),
                np.ascontiguousarray(scl, dtype=np.float32),
                np.ascontiguousarray(opa, dtype=np.float32),
                np.float32(thr), np.float32(vx), 2.0,
                float(origin[0]), float(origin[1]), float(origin[2]),
                nx, ny, nz, occ,
            )
        except Exception:
            return np.zeros((0, 6), dtype=np.float32)
        if int(occ.sum()) == 0:
            return np.zeros((0, 6), dtype=np.float32)
        cur = occ
        for _ in range(int(dilation)):
            nxt = np.zeros_like(cur)
            try:
                _cython_dilate(cur, nxt, nx, ny, nz)
            except Exception:
                break
            cur = nxt
        mask = np.zeros(nx * ny * nz, dtype=np.uint8)
        out = np.empty((_MERGE_CAP, 6), dtype=np.float32)
        try:
            cnt = int(_cython_merge(cur, nx, ny, nz, mask, out, _MERGE_CAP))
        except Exception:
            return np.zeros((0, 6), dtype=np.float32)
        if cnt < 0:
            vx *= 2.0
            continue
        if cnt == 0:
            return np.zeros((0, 6), dtype=np.float32)
        if cnt > int(max_boxes):
            vx *= 2.0
            continue
        cells = out[:cnt].copy()
        boxes = np.empty((cnt, 6), dtype=np.float32)
        boxes[:, 0] = origin[0] + cells[:, 0] * vx
        boxes[:, 1] = origin[1] + cells[:, 1] * vx
        boxes[:, 2] = origin[2] + cells[:, 2] * vx
        boxes[:, 3] = origin[0] + (cells[:, 3] + 1.0) * vx
        boxes[:, 4] = origin[1] + (cells[:, 4] + 1.0) * vx
        boxes[:, 5] = origin[2] + (cells[:, 5] + 1.0) * vx
        return np.ascontiguousarray(boxes)
    return np.zeros((0, 6), dtype=np.float32)


def get_volume_boxes(ply_path: str, voxel: float, thr: float, dilation: int, max_boxes: int):
    resolved = _resolve_ply_path(ply_path)
    if resolved is None:
        return np.zeros((0, 6), dtype=np.float32)
    key = (resolved, _file_sig(resolved), float(voxel), float(thr), int(dilation), int(max_boxes))
    cached = _volume_cache_get(key)
    if cached is not None:
        return cached
    boxes = _build_volume_boxes(resolved, float(voxel), float(thr), int(dilation), int(max_boxes))
    _volume_cache_set(key, boxes)
    return boxes


def _volume_box_edges_np(mins: np.ndarray, maxs: np.ndarray):
    n = mins.shape[0]
    corners = np.empty((n, 8, 3), dtype=np.float32)
    for i, (sx, sy, sz) in enumerate(((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1))):
        selx = np.where(sx, maxs[:, 0], mins[:, 0])
        sely = np.where(sy, maxs[:, 1], mins[:, 1])
        selz = np.where(sz, maxs[:, 2], mins[:, 2])
        corners[:, i, 0] = selx
        corners[:, i, 1] = sely
        corners[:, i, 2] = selz
    pairs = np.array([[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7]], dtype=np.int64)
    return np.ascontiguousarray(corners[:, pairs].reshape(n * 12, 2, 3))


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
            InspectorField("ply_path", "PLY Path", FieldType.RESOURCE_PATH,
                           file_filter="PLY (*.ply)"),
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
        from core.physics.shape_utils import resolve_physics_material
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
        from core.components.physics.mesh_collider import _edge_pairs_np
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
            from core.engine.engine import Engine
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
