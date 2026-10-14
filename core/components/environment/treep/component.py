# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import random
import numpy as np
from typing import Optional
from core.ecs import Component, ComponentRegistry, Entity
from core.components.inspector_meta import FieldType, InspectorField
from core.maths.math3d import Vec3
from core.components.environment.treep.gen import _GEN_PARAMS, _normalize, _BranchNode, _BranchGen, _tube_along_curve
def _make_leaf(position: tuple, size: float, rot_y: float,
               tilt_x: float, tilt_z: float,
               phase_off: float, stiffness: float, branch_lvl: float) -> tuple:
    hw = size * 0.35
    hs = size * 0.5
    def _rotate_y(v, a):
        c = math.cos(a); s = math.sin(a)
        return (v[0]*c - v[2]*s, v[1], v[0]*s + v[2]*c)
    def _rotate_x(v, a):
        c = math.cos(a); s = math.sin(a)
        return (v[0], v[1]*c - v[2]*s, v[1]*s + v[2]*c)
    def _rotate_z(v, a):
        c = math.cos(a); s = math.sin(a)
        return (v[0]*c - v[1]*s, v[0]*s + v[1]*c, v[2])
    all_verts = []
    all_norms = []
    all_uvs = []
    all_colors = []
    all_idxs = []
    base = 0
    for cross_angle in [0.0, math.pi * 0.5]:
        corners = [(-hw, 0.0, -hs), ( hw, 0.0, -hs), ( hw, 0.0,  hs), (-hw, 0.0,  hs)]
        rotated = []
        for c in corners:
            c = _rotate_y(c, cross_angle)
            c = _rotate_y(c, rot_y)
            c = _rotate_x(c, tilt_x)
            c = _rotate_z(c, tilt_z)
            rotated.append((c[0] + position[0], c[1] + position[1] + size * 0.1, c[2] + position[2]))
        nrm = (0.0, 1.0, 0.0)
        nrm = _rotate_y(nrm, cross_angle)
        nrm = _rotate_y(nrm, rot_y)
        nrm = _rotate_x(nrm, tilt_x)
        nrm = _rotate_z(nrm, tilt_z)
        nrm = _normalize(nrm)
        for c in rotated:
            all_verts.extend(c)
        all_norms.extend(nrm * 4)
        all_uvs.extend([0, 0,  1, 0,  1, 1,  0, 1])
        all_colors.extend([branch_lvl, stiffness, phase_off, 1.0] * 4)
        all_idxs.extend([base, base+2, base+1,  base, base+3, base+2])
        base += 4
    return all_verts, all_norms, all_uvs, all_colors, all_idxs
def _leaf_cluster(position: tuple, size: float, count: int,
                  phase_off: float, level: int, rng: random.Random) -> tuple:
    verts, norms, uvs, colors = [], [], [], []
    idxs = []
    base_idx = 0
    branch_lvl = min(1.0, level / 5.0)
    stiffness = max(0.01, 1.0 - branch_lvl * 0.85)
    for i in range(count):
        phi = rng.random() * math.pi * 0.45
        theta = rng.random() * math.pi * 2.0
        r_offset = size * 0.3 * math.sqrt(rng.random())
        lx = r_offset * math.sin(phi) * math.cos(theta)
        ly = r_offset * math.cos(phi) + size * 0.1
        lz = r_offset * math.sin(phi) * math.sin(theta)
        leaf_pos = (position[0] + lx, position[1] + ly, position[2] + lz)
        tilt_x = (rng.random() - 0.5) * math.radians(20)
        tilt_z = (rng.random() - 0.5) * math.radians(20)
        leaf_rot = rng.random() * math.pi * 2.0
        l_scale = size * (0.7 + 0.6 * rng.random())
        lv, ln, lu, lc, li = _make_leaf(
            leaf_pos, l_scale, leaf_rot, tilt_x, tilt_z,
            phase_off, stiffness, branch_lvl
        )
        verts.extend(lv); norms.extend(ln); uvs.extend(lu); colors.extend(lc)
        idxs.extend(base_idx + i for i in li)
        base_idx += 8
    return verts, norms, uvs, colors, idxs
def _collect_branch_geometry(node: _BranchNode, segments: int,
                             leaf_size: float, leaf_density: int,
                             bark: list, leaves: list,
                             rng: random.Random,
                             gnarliness: float = 0.0,
                             gravity: float = 0.0) -> None:
    rings = 6 if node.level == 0 else 5
    bv, bn, bu, bc, bi = _tube_along_curve(node, segments, rings,
                                            gnarliness=gnarliness,
                                            gravity=gravity, rng=rng)
    if bv:
        base = len(bark[0]) // 3
        bark[0].extend(bv); bark[1].extend(bn); bark[2].extend(bu)
        bark[3].extend(bc); bark[4].extend(i + base for i in bi)
    for sub in node.sub_branches:
        sub_gnarl = gnarliness * 1.5
        sv, sn, su, sc, si = _tube_along_curve(sub, max(3, segments // 2), 4,
                                                gnarliness=sub_gnarl,
                                                gravity=gravity, rng=rng)
        if sv:
            base = len(bark[0]) // 3
            bark[0].extend(sv); bark[1].extend(sn); bark[2].extend(su)
            bark[3].extend(sc); bark[4].extend(i + base for i in si)
        if sub.is_terminal and leaf_density > 0:
            lv, ln, lu, lc, li = _leaf_cluster(
                sub.end, leaf_size * 0.6, max(1, leaf_density // 2),
                sub.phase_off, sub.level, rng
            )
            if lv:
                base = len(leaves[0]) // 3
                leaves[0].extend(lv); leaves[1].extend(ln); leaves[2].extend(lu)
                leaves[3].extend(lc); leaves[4].extend(i + base for i in li)
    if node.is_terminal and leaf_density > 0:
        lv, ln, lu, lc, li = _leaf_cluster(
            node.end, leaf_size, leaf_density,
            node.phase_off, node.level + 1, rng
        )
        if lv:
            base = len(leaves[0]) // 3
            leaves[0].extend(lv); leaves[1].extend(ln); leaves[2].extend(lu)
            leaves[3].extend(lc); leaves[4].extend(i + base for i in li)
    for child in node.children:
        _collect_branch_geometry(child, segments, leaf_size, leaf_density,
                                 bark, leaves, rng,
                                 gnarliness=gnarliness, gravity=gravity)
def generate_tree_mesh(height: float = 10.0, trunk_radius: float = 0.3,
                       trunk_segments: int = 8, levels: int = 4,
                       branch_angle: float = 35.0, ratio: float = 0.6,
                       taper: float = 0.8, branches_per_node: int = 3,
                       spiral_twist: float = 1.2, leaf_size: float = 0.35,
                       leaf_density: int = 4, seed: int = 0,
                       branch_curvature: float = 0.4,
                       gnarliness: float = 0.0, gravity: float = 0.0):
    from core.renderer.meshd import MeshData
    gen = _BranchGen(seed)
    rng = random.Random(seed + 999)
    root = gen.generate(height, trunk_radius, levels, branch_angle,
                        ratio, taper, branches_per_node, spiral_twist,
                        leaf_size, leaf_density, branch_curvature)
    bark = [[], [], [], [], []]
    leaves = [[], [], [], [], []]
    _collect_branch_geometry(root, trunk_segments, leaf_size, leaf_density,
                             bark, leaves, rng,
                             gnarliness=gnarliness, gravity=gravity)
    all_verts = bark[0] + leaves[0]
    all_norms = bark[1] + leaves[1]
    all_uvs = bark[2] + leaves[2]
    all_colors = bark[3] + leaves[3]
    bark_vert_count = len(bark[0]) // 3
    all_idxs = bark[4] + [i + bark_vert_count for i in leaves[4]]
    if not all_verts:
        md = MeshData()
        h_ = 0.5
        md.vertices = np.array([-h_,0,-h_, h_,0,-h_, h_,0,h_, -h_,0,h_], dtype=np.float32)
        md.normals = np.array([0,1,0, 0,1,0, 0,1,0, 0,1,0], dtype=np.float32)
        md.uvs = np.array([0,0, 1,0, 1,1, 0,1], dtype=np.float32)
        md.indices = np.array([0,1,2, 0,2,3], dtype=np.uint32)
        return md
    mesh = MeshData()
    mesh.vertices = np.array(all_verts, dtype=np.float32)
    mesh.normals = np.array(all_norms, dtype=np.float32)
    mesh.uvs = np.array(all_uvs, dtype=np.float32)
    mesh.colors = np.array(all_colors, dtype=np.float32)
    mesh.indices = np.array(all_idxs, dtype=np.uint32)
    if leaves[4]:
        mesh.sub_mesh_ranges = [(0, len(bark[4])), (len(bark[4]), len(leaves[4]))]
    mesh.compute_aabb()
    return mesh
@ComponentRegistry.register
class Tree(Component):
    _icon = "Tree.png"
    _gizmo_icon_color = (60, 180, 60)
    _gizmo_icon_label = "T"
    _show_gizmo_icon = True
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Tree", FieldType.HEADER),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=1.0, max_val=100.0, step=0.5, decimals=2),
            InspectorField("trunk_radius", "Trunk Radius", FieldType.FLOAT, min_val=0.01, max_val=3.0, step=0.05, decimals=3),
            InspectorField("trunk_segments", "Trunk Segments", FieldType.INT, min_val=4, max_val=24, step=1),
            InspectorField("levels", "Branch Levels", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("branch_angle", "Branch Angle (deg)", FieldType.FLOAT, min_val=5.0, max_val=80.0, step=1.0, decimals=1),
            InspectorField("ratio", "Branch Length Ratio", FieldType.SLIDER, min_val=0.2, max_val=0.95, step=0.01, decimals=3),
            InspectorField("taper", "Branch Taper", FieldType.SLIDER, min_val=0.3, max_val=1.0, step=0.01, decimals=3),
            InspectorField("branches_per_node", "Branches Per Node", FieldType.INT, min_val=1, max_val=6, step=1),
            InspectorField("spiral_twist", "Spiral Twist", FieldType.FLOAT, min_val=0.0, max_val=6.0, step=0.1, decimals=2),
            InspectorField("branch_curvature", "Branch Curvature", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
            InspectorField("gnarliness", "Gnarliness", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("gravity", "Gravity Droop", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.05, decimals=2),
            InspectorField("", "Leaves", FieldType.HEADER),
            InspectorField("leaf_size", "Leaf Size", FieldType.FLOAT, min_val=0.05, max_val=1.5, step=0.05, decimals=3),
            InspectorField("leaf_density", "Leaf Density", FieldType.INT, min_val=0, max_val=20, step=1),
            InspectorField("seed", "Seed", FieldType.INT, min_val=0, max_val=999999, step=1),
            InspectorField("random_seed", "Random Seed", FieldType.BOOL),
            InspectorField("material_path", "Bark Material", FieldType.RESOURCE_PATH, file_filter="Material (*.mat)"),
            InspectorField("leaf_material_path", "Leaf Material", FieldType.RESOURCE_PATH, file_filter="Material (*.mat)"),
            InspectorField("auto_regenerate", "Auto Regenerate", FieldType.BOOL),
            InspectorField("_btn_regenerate", "Regenerate", FieldType.BUTTON),
        ]
    def __init__(self):
        self._init_done = False
        super().__init__()
        self.height: float = 10.0
        self.trunk_radius: float = 0.3
        self.trunk_segments: int = 8
        self.levels: int = 4
        self.branch_angle: float = 35.0
        self.ratio: float = 0.6
        self.taper: float = 0.8
        self.branches_per_node: int = 3
        self.spiral_twist: float = 1.2
        self.branch_curvature: float = 0.4
        self.gnarliness: float = 0.3
        self.gravity: float = 0.5
        self.leaf_size: float = 0.35
        self.leaf_density: int = 4
        self.seed: int = 0
        self.random_seed: bool = False
        self.material_path: str = ""
        self.leaf_material_path: str = ""
        self.auto_regenerate: bool = True
        self._generated: bool = False
        self._gpu_dirty: bool = True
        self._mesh_data: Optional['MeshData'] = None
        self._mesh_name: str = ""
        self._params_hash: int = 0
        self._init_done = True
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in _GEN_PARAMS and getattr(self, '_init_done', False):
            self._mark_dirty()
            if self.auto_regenerate:
                try:
                    ent = getattr(self, '_entity', None)
                    if ent:
                        sc = getattr(ent, '_scene', None)
                        if sc:
                            sc._render_version += 1
                except Exception:
                    pass
    def _current_params_hash(self) -> int:
        return hash((
            self.height, self.trunk_radius, self.trunk_segments,
            self.levels, self.branch_angle, self.ratio, self.taper,
            self.branches_per_node, self.spiral_twist, self.branch_curvature,
            self.gnarliness, self.gravity,
            self.leaf_size, self.leaf_density, self.seed, self.random_seed,
        ))
    def _mark_dirty(self):
        self._generated = False
        self._gpu_dirty = True
    def _btn_regenerate(self):
        self._mark_dirty()
        self.generate()
        try:
            ent = getattr(self, '_entity', None)
            if ent:
                sc = getattr(ent, '_scene', None)
                if sc:
                    sc._render_version += 1
        except Exception:
            pass
    def generate(self) -> 'MeshData':
        actual_seed = random.randint(0, 999999) if self.random_seed else self.seed
        self._mesh_data = generate_tree_mesh(
            height=self.height, trunk_radius=self.trunk_radius,
            trunk_segments=self.trunk_segments, levels=self.levels,
            branch_angle=self.branch_angle, ratio=self.ratio,
            taper=self.taper, branches_per_node=self.branches_per_node,
            spiral_twist=self.spiral_twist,
            leaf_size=self.leaf_size, leaf_density=self.leaf_density,
            seed=actual_seed, branch_curvature=self.branch_curvature,
            gnarliness=self.gnarliness, gravity=self.gravity,
        )
        self._generated = True
        self._gpu_dirty = True
        self._params_hash = self._current_params_hash()
        return self._mesh_data
    def needs_regenerate(self) -> bool:
        if self._mesh_data is None:
            return True
        if not self._generated:
            return True
        if self.auto_regenerate and self._current_params_hash() != self._params_hash:
            return True
        return False
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "height": self.height, "trunk_radius": self.trunk_radius,
            "trunk_segments": self.trunk_segments, "levels": self.levels,
            "branch_angle": self.branch_angle, "ratio": self.ratio,
            "taper": self.taper, "branches_per_node": self.branches_per_node,
            "spiral_twist": self.spiral_twist, "branch_curvature": self.branch_curvature,
            "gnarliness": self.gnarliness, "gravity": self.gravity,
            "leaf_size": self.leaf_size, "leaf_density": self.leaf_density,
            "seed": self.seed, "random_seed": self.random_seed,
            "material_path": self.material_path,
            "leaf_material_path": self.leaf_material_path,
            "auto_regenerate": self.auto_regenerate,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> Tree:
        t = cls()
        t.enabled = data.get("enabled", True)
        t.height = data.get("height", 10.0)
        t.trunk_radius = data.get("trunk_radius", 0.3)
        t.trunk_segments = data.get("trunk_segments", 8)
        t.levels = data.get("levels", 4)
        t.branch_angle = data.get("branch_angle", 35.0)
        t.ratio = data.get("ratio", 0.6)
        t.taper = data.get("taper", 0.8)
        t.branches_per_node = data.get("branches_per_node", 3)
        t.spiral_twist = data.get("spiral_twist", 1.2)
        t.branch_curvature = data.get("branch_curvature", 0.4)
        t.gnarliness = data.get("gnarliness", 0.3)
        t.gravity = data.get("gravity", 0.5)
        t.leaf_size = data.get("leaf_size", 0.35)
        t.leaf_density = data.get("leaf_density", 4)
        t.seed = data.get("seed", 0)
        t.random_seed = data.get("random_seed", False)
        t.material_path = data.get("material_path", "")
        t.leaf_material_path = data.get("leaf_material_path", "")
        t.auto_regenerate = data.get("auto_regenerate", True)
        return t
