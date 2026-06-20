from __future__ import annotations

import math
import numpy as np
from core.math3d import Mat4, Vec3
from core.config import get_global_config

from editor.gizmo.gizmo_particle import get_particle_emitter_lines
from editor.gizmo.gizmo_camera import get_camera_frustum_lines
from editor.gizmo.gizmo_audio import get_audio_source_gizmo_lines
from editor.gizmo.api import Gizmos
from core.components.physics.mesh_collider import MeshCollider, CollisionMode
from core.components.physics.box_collider import BoxCollider
from core.components.physics.sphere_collider import SphereCollider
from core.components.physics.capsule_collider import CapsuleCollider
from core.components.physics.rigidbody import Rigidbody
from core.components.physics2d.box_collider2d import BoxCollider2D
from core.components.physics2d.circle_collider2d import CircleCollider2D
from editor.gizmo.gizmo_collider import _load_mesh_data, _get_convex_hull_edges_np, _get_decimated_hull_edges_np
from core.components.scripting.script_component import ScriptComponent
from core.components.rendering.particle_system import ParticleSystem
from core.components.rendering.camera import Camera
from core.components.audio.audio_source import AudioSource
from core.components.audio.reverb_zone import ReverbZone


_BOX_EDGE_PAIRS = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
_RECT_EDGE_PAIRS = [(0,1),(1,2),(2,3),(3,0)]


def _box_starts_ends(corners: list[Vec3], pairs: list | None = None) -> tuple[np.ndarray, np.ndarray]:
    if pairs is None:
        pairs = _BOX_EDGE_PAIRS
    n = len(pairs)
    starts = np.zeros((n, 3), dtype=np.float32)
    ends = np.zeros((n, 3), dtype=np.float32)
    for i, (a, b) in enumerate(pairs):
        starts[i, 0] = corners[a].x; starts[i, 1] = corners[a].y; starts[i, 2] = corners[a].z
        ends[i, 0] = corners[b].x; ends[i, 1] = corners[b].y; ends[i, 2] = corners[b].z
    return starts, ends


def _ring_starts_ends(pts: list[Vec3], segs: int) -> tuple[np.ndarray, np.ndarray]:
    starts = np.zeros((segs, 3), dtype=np.float32)
    ends = np.zeros((segs, 3), dtype=np.float32)
    for i in range(segs):
        starts[i, 0] = pts[i].x; starts[i, 1] = pts[i].y; starts[i, 2] = pts[i].z
        ends[i, 0] = pts[i+1].x; ends[i, 1] = pts[i+1].y; ends[i, 2] = pts[i+1].z
    return starts, ends


def _collider_color_arr(n: int, color: list) -> np.ndarray:
    c = np.zeros((n, 4), dtype=np.float32)
    c[:, 0] = color[0]; c[:, 1] = color[1]; c[:, 2] = color[2]
    c[:, 3] = color[3] if len(color) > 3 else 1.0
    return c


def _build_box_np(comp, pos: Vec3, rot, sc: Vec3, color: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sz = comp.scaled_size
    hx, hy, hz = sz.x * 0.5, sz.y * 0.5, sz.z * 0.5
    R = _quat_to_mat3(rot)
    c_local = np.array([comp.scaled_center.x, comp.scaled_center.y, comp.scaled_center.z], dtype=np.float32)
    c = c_local @ R + np.array([pos.x, pos.y, pos.z], dtype=np.float32)
    local_offsets = np.array([
        [-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
        [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz],
    ], dtype=np.float32)
    corners = local_offsets @ R + c
    edge_pairs = np.array(_BOX_EDGE_PAIRS, dtype=np.int32)
    starts = corners[edge_pairs[:, 0]]
    ends = corners[edge_pairs[:, 1]]
    return starts, ends, _collider_color_arr(12, color)


def _build_sphere_np(comp, pos: Vec3, rot, sc: Vec3, color: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    radius = comp.scaled_radius
    R = _quat_to_mat3(rot)
    c_local = np.array([comp.scaled_center.x, comp.scaled_center.y, comp.scaled_center.z], dtype=np.float32)
    c = c_local @ R + np.array([pos.x, pos.y, pos.z], dtype=np.float32)
    segs = 24
    total = segs * 3
    starts = np.zeros((total, 3), dtype=np.float32)
    ends = np.zeros((total, 3), dtype=np.float32)
    idx = 0
    for axis_idx in range(3):
        theta = np.linspace(0, 2.0 * math.pi, segs + 1, dtype=np.float32)
        ct = np.cos(theta) * radius; st = np.sin(theta) * radius
        pts = np.zeros((segs + 1, 3), dtype=np.float32)
        if axis_idx == 0:
            pts[:, 1] = ct; pts[:, 2] = st
        elif axis_idx == 1:
            pts[:, 0] = ct; pts[:, 2] = st
        else:
            pts[:, 0] = ct; pts[:, 1] = st
        pts = pts @ R + c
        starts[idx:idx+segs] = pts[:-1]
        ends[idx:idx+segs] = pts[1:]
        idx += segs
    return starts, ends, _collider_color_arr(total, color)


def _build_capsule_np(comp, pos: Vec3, rot, sc: Vec3, color: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    R = _quat_to_mat3(rot)
    pos_np = np.array([pos.x, pos.y, pos.z], dtype=np.float32)
    c_local = np.array([comp.scaled_center.x, comp.scaled_center.y, comp.scaled_center.z], dtype=np.float32)
    c = c_local @ R + pos_np
    radius = comp.scaled_radius
    half_h = max(0, comp.scaled_height * 0.5 - radius)
    dir_idx = getattr(comp, "direction", 1)
    axis_vecs = [np.array([1,0,0], dtype=np.float32), np.array([0,1,0], dtype=np.float32), np.array([0,0,1], dtype=np.float32)]
    axis = axis_vecs[dir_idx] if dir_idx < 3 else axis_vecs[1]
    segs = 20
    axis_rot = axis @ R
    top_center = c + axis_rot * half_h
    bottom_center = c - axis_rot * half_h
    total = 0
    for ring_axis in range(3):
        if ring_axis != dir_idx:
            total += segs * 2
    total += 8
    starts = np.zeros((total, 3), dtype=np.float32)
    ends = np.zeros((total, 3), dtype=np.float32)
    idx = 0
    for ring_axis in range(3):
        if ring_axis == dir_idx:
            continue
        u_base = np.array([0,1,0] if ring_axis == 0 else [1,0,0], dtype=np.float32)
        v_base = np.array([0,0,1] if ring_axis == 2 else [0,1,0], dtype=np.float32)
        if ring_axis == 1:
            u_base = np.array([1,0,0], dtype=np.float32); v_base = np.array([0,0,1], dtype=np.float32)
        u = u_base @ R; v = v_base @ R
        theta = np.linspace(0, 2.0 * math.pi, segs + 1, dtype=np.float32)
        ct = np.cos(theta) * radius; st = np.sin(theta) * radius
        pts = np.outer(ct, u) + np.outer(st, v)
        pts_top = pts + top_center
        pts_bot = pts + bottom_center
        n = segs
        starts[idx:idx+n] = pts_top[:-1]; ends[idx:idx+n] = pts_top[1:]; idx += n
        starts[idx:idx+n] = pts_bot[:-1]; ends[idx:idx+n] = pts_bot[1:]; idx += n
    theta = np.linspace(0, 2.0 * math.pi, 9, dtype=np.float32)[:-1]
    ct = np.cos(theta) * radius; st = np.sin(theta) * radius
    pts = np.outer(ct, u) + np.outer(st, v)
    starts[idx:idx+8] = pts + top_center
    ends[idx:idx+8] = pts + bottom_center
    return starts, ends, _collider_color_arr(total, color)


def _quat_to_mat3(rot) -> np.ndarray:
    x, y, z, w = rot.x, rot.y, rot.z, rot.w
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n > 1e-10:
        inv = 1.0 / n; x *= inv; y *= inv; z *= inv; w *= inv
    return np.array([
        [1-2*y*y-2*z*z, 2*x*y+2*w*z, 2*x*z-2*w*y],
        [2*x*y-2*w*z, 1-2*x*x-2*z*z, 2*y*z+2*w*x],
        [2*x*z+2*w*y, 2*y*z-2*w*x, 1-2*x*x-2*y*y],
    ], dtype=np.float32)


def _build_mesh_collider_lines_np(comp, entity, pos: Vec3, rot, sc: Vec3):
    mesh_color = [0.0, 0.8, 0.2, 0.6]
    mesh_path = getattr(comp, "mesh_path", "")
    mode = getattr(comp, "collision_mode", CollisionMode.AUTO)
    max_verts = getattr(comp, "max_vertices", 2000)
    md = _load_mesh_data(mesh_path) if mesh_path else None
    if md is None or md["num_verts"] == 0:
        R = _quat_to_mat3(rot)
        pos_np = np.array([pos.x, pos.y, pos.z], dtype=np.float32)
        s = 0.5
        local_offsets = np.array([
            [-s,-s,-s],[s,-s,-s],[s,s,-s],[-s,s,-s],
            [-s,-s,s],[s,-s,s],[s,s,s],[-s,s,s],
        ], dtype=np.float32)
        corners = local_offsets @ R + pos_np
        edge_pairs = np.array(_BOX_EDGE_PAIRS, dtype=np.int32)
        starts = corners[edge_pairs[:, 0]]
        ends = corners[edge_pairs[:, 1]]
        Gizmos.draw_lines(starts, ends, _collider_color_arr(12, mesh_color))
        return

    R = _quat_to_mat3(rot)
    pos_np = np.array([pos.x, pos.y, pos.z], dtype=np.float32)
    sc_np = np.array([sc.x, sc.y, sc.z], dtype=np.float32)

    s_list: list[np.ndarray] = []
    e_list: list[np.ndarray] = []

    def _submit_np(edge_verts: np.ndarray):
        if edge_verts.shape[0] == 0:
            return
        scaled = edge_verts * sc_np
        rotated = scaled @ R
        s_list.append(rotated[:, 0, :] + pos_np)
        e_list.append(rotated[:, 1, :] + pos_np)

    if mode == CollisionMode.BOX:
        size = md["maxs"] - md["mins"]
        if np.all(size < 100.0):
            mins = md["mins"]; maxs = md["maxs"]
            ctr = (mins + maxs) * 0.5
            half = size * 0.5
            local_offsets = np.array([
                [-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],
            ], dtype=np.float32) * half
            lc = ctr + local_offsets
            lc_t = lc * sc_np @ R + pos_np
            edge_pairs = np.array([(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7),
                                   (0,2),(1,3),(4,6),(5,7),(0,7),(1,6),(2,5),(3,4)], dtype=np.int32)
            s_list.append(lc_t[edge_pairs[:, 0]])
            e_list.append(lc_t[edge_pairs[:, 1]])
        else:
            c = np.array([pos.x, pos.y, pos.z], dtype=np.float32)
            s = 0.5
            corners = np.array([
                [-s,-s,-s],[s,-s,-s],[s,s,-s],[-s,s,-s],
                [-s,-s,s],[s,-s,s],[s,s,s],[-s,s,s],
            ], dtype=np.float32) @ R + c
            edge_pairs = np.array([(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)])
            s_list.append(corners[edge_pairs[:, 0]])
            e_list.append(corners[edge_pairs[:, 1]])

    elif mode == CollisionMode.SPHERE:
        c = np.array([md["center"][0], md["center"][1], md["center"][2]], dtype=np.float32)
        max_sc = max(sc.x, sc.y, sc.z)
        radius = md["radius"] * max_sc
        segs = 24
        for axis_idx in range(3):
            theta = np.linspace(0, 2.0 * math.pi, segs + 1, dtype=np.float32)
            ct = np.cos(theta) * radius; st = np.sin(theta) * radius
            pts = np.zeros((segs + 1, 3), dtype=np.float32)
            if axis_idx == 0:
                pts[:, 1] = ct; pts[:, 2] = st
            elif axis_idx == 1:
                pts[:, 0] = ct; pts[:, 2] = st
            else:
                pts[:, 0] = ct; pts[:, 1] = st
            pts = pts @ R + (c * sc_np @ R + pos_np)
            s_list.append(pts[:-1])
            e_list.append(pts[1:])

    elif mode == CollisionMode.CONVEX_HULL:
        hull_np = _get_convex_hull_edges_np(mesh_path)
        if hull_np is not None:
            _submit_np(hull_np)
        elif md.get("edge_verts_np", None) is not None and md["edge_verts_np"].shape[0] > 0:
            _submit_np(md["edge_verts_np"])

    elif mode == CollisionMode.AUTO:
        if md["num_verts"] > max_verts:
            hull_np = _get_decimated_hull_edges_np(mesh_path, max_verts)
            if hull_np is not None:
                _submit_np(hull_np)
            else:
                size = md["maxs"] - md["mins"]
                if np.all(size < 100.0):
                    mins = md["mins"]; maxs = md["maxs"]
                    ctr = (mins + maxs) * 0.5
                    half = size * 0.5
                    local_offsets = np.array([
                        [-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                        [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],
                    ], dtype=np.float32) * half
                    lc = ctr + local_offsets
                    lc_t = lc * sc_np @ R + pos_np
                    edge_pairs = np.array([(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7),
                                           (0,2),(1,3),(4,6),(5,7),(0,7),(1,6),(2,5),(3,4)], dtype=np.int32)
                    s_list.append(lc_t[edge_pairs[:, 0]])
                    e_list.append(lc_t[edge_pairs[:, 1]])
                else:
                    c = np.array([pos.x, pos.y, pos.z], dtype=np.float32)
                    s = 0.5
                    corners = np.array([
                        [-s,-s,-s],[s,-s,-s],[s,s,-s],[-s,s,-s],
                        [-s,-s,s],[s,-s,s],[s,s,s],[-s,s,s],
                    ], dtype=np.float32) @ R + c
                    edge_pairs = np.array([(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)])
                    s_list.append(corners[edge_pairs[:, 0]])
                    e_list.append(corners[edge_pairs[:, 1]])
        else:
            ev = md.get("edge_verts_np")
            if ev is not None and ev.shape[0] > 0:
                _submit_np(ev)

    elif md.get("edge_verts_np", None) is not None and md["edge_verts_np"].shape[0] > 0:
        _submit_np(md["edge_verts_np"])

    if s_list:
        n = sum(s.shape[0] for s in s_list)
        if n > 0:
            starts = np.concatenate(s_list, axis=0)
            ends = np.concatenate(e_list, axis=0)
            Gizmos.draw_lines(starts, ends, _collider_color_arr(n, mesh_color))


def _get_tr_hash(tr):
    p = tr.local_position; r = tr.local_rotation; s = tr.local_scale
    return (p.x, p.y, p.z, r.x, r.y, r.z, r.w, s.x, s.y, s.z)

_collider_gizmo_cache: dict[tuple, tuple] = {}

def render_collider_wireframes(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    cam_pos = vp._cam.position if vp._cam else Vec3(0, 0, 0)
    MAX_DISTANCE = 20.0
    color = [0.0, 1.0, 0.0, 0.6]
    types = [(BoxCollider, 'box'), (SphereCollider, 'sphere'), (CapsuleCollider, 'capsule'), (MeshCollider, 'mesh')]
    used_keys: set[tuple] = set()

    for collider_type, type_tag in types:
        for entity in scene.get_entities_with_component(collider_type):
            if not entity.active:
                continue
            tr = entity.get_component_by_name("Transform")
            if not tr:
                continue
            pos = tr.local_position
            rot = tr.local_rotation
            sc = tr.local_scale
            hash_key = (entity.id, type_tag)
            used_keys.add(hash_key)
            tr_hash = _get_tr_hash(tr)

            if collider_type is MeshCollider:
                if (pos - cam_pos).length() > MAX_DISTANCE:
                    continue
                if getattr(vp._engine, 'play_mode', False) and entity.get_component(Rigidbody):
                    continue
                _build_mesh_collider_lines_np(entity.get_component(MeshCollider), entity, pos, rot, sc)
                continue

            cached = _collider_gizmo_cache.get(hash_key)
            if cached is not None and cached[3] == tr_hash:
                Gizmos.draw_lines(cached[0], cached[1], cached[2])
                continue

            comp = entity.get_component(collider_type)
            if comp is None:
                continue
            if collider_type is BoxCollider:
                starts, ends, cols = _build_box_np(comp, pos, rot, sc, color)
            elif collider_type is SphereCollider:
                starts, ends, cols = _build_sphere_np(comp, pos, rot, sc, color)
            elif collider_type is CapsuleCollider:
                starts, ends, cols = _build_capsule_np(comp, pos, rot, sc, color)
            else:
                continue
            _collider_gizmo_cache[hash_key] = (starts, ends, cols, tr_hash)
            Gizmos.draw_lines(starts, ends, cols)

    _render_collider2d(scene, color)

    stale = set(_collider_gizmo_cache.keys()) - used_keys
    if stale:
        for k in stale:
            del _collider_gizmo_cache[k]


def _render_collider2d(scene, color):
    for entity in scene.get_entities_with_component(BoxCollider2D):
        if not entity.active:
            continue
        _render_box2d(entity, color)
    for entity in scene.get_entities_with_component(CircleCollider2D):
        if not entity.active:
            continue
        _render_circle2d(entity, color)

def _render_box2d(entity, color):
    tr = entity.get_component_by_name("Transform")
    if not tr:
        return
    pos = np.array([tr.local_position.x, tr.local_position.y, tr.local_position.z], dtype=np.float32)
    R = _quat_to_mat3(tr.local_rotation)
    box = entity.get_component(BoxCollider2D)
    if not box:
        return
    sz = box.scaled_size
    off_v2 = box.scaled_offset
    c = np.array([off_v2.x, off_v2.y, 0.0], dtype=np.float32) @ R + pos
    hx, hy = sz.x * 0.5, sz.y * 0.5
    corners = np.array([[-hx, -hy, 0.0], [hx, -hy, 0.0], [hx, hy, 0.0], [-hx, hy, 0.0]], dtype=np.float32) @ R + c
    edge_pairs = np.array(_RECT_EDGE_PAIRS, dtype=np.int32)
    Gizmos.draw_lines(corners[edge_pairs[:, 0]], corners[edge_pairs[:, 1]], _collider_color_arr(4, color))

def _render_circle2d(entity, color):
    tr = entity.get_component_by_name("Transform")
    if not tr:
        return
    pos = np.array([tr.local_position.x, tr.local_position.y, tr.local_position.z], dtype=np.float32)
    R = _quat_to_mat3(tr.local_rotation)
    circle = entity.get_component(CircleCollider2D)
    if not circle:
        return
    radius = circle.scaled_radius
    off_v2 = circle.scaled_offset
    c = np.array([off_v2.x, off_v2.y, 0.0], dtype=np.float32) @ R + pos
    segs = 24
    theta = np.linspace(0, 2.0 * math.pi, segs + 1, dtype=np.float32)
    pts = np.zeros((segs + 1, 3), dtype=np.float32)
    pts[:, 0] = np.cos(theta) * radius; pts[:, 1] = np.sin(theta) * radius
    pts = pts @ R + c
    Gizmos.draw_lines(pts[:-1], pts[1:], _collider_color_arr(segs, color))


def _submit_lines_fast(lines: list, thickness_multiplier: float = 1.0):
    if not lines:
        return
    n = len(lines)
    starts = np.zeros((n, 3), dtype=np.float32)
    ends = np.zeros((n, 3), dtype=np.float32)
    colors = np.zeros((n, 4), dtype=np.float32)
    for i, (s, e, c) in enumerate(lines):
        starts[i, 0] = s.x; starts[i, 1] = s.y; starts[i, 2] = s.z
        ends[i, 0] = e.x; ends[i, 1] = e.y; ends[i, 2] = e.z
        colors[i, 0] = c[0]; colors[i, 1] = c[1]; colors[i, 2] = c[2]
        colors[i, 3] = c[3] if len(c) > 3 else 1.0
    Gizmos.draw_lines(starts, ends, colors)


def render_particle_emitter_wireframes(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    for entity in scene.get_entities_with_component(ParticleSystem):
        if entity.active:
            lines.extend(get_particle_emitter_lines(entity))
    _submit_lines_fast(lines)


def render_camera_frustums(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    for entity in scene.get_entities_with_component(Camera):
        if entity.active:
            lines.extend(get_camera_frustum_lines(entity))
    _submit_lines_fast(lines)


def render_audio_source_gizmos(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    for entity in scene.get_entities_with_component(AudioSource):
        if entity.active:
            lines.extend(get_audio_source_gizmo_lines(entity))
    _submit_lines_fast(lines)


def render_reverb_zone_gizmos(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    for entity in scene.get_entities_with_component(ReverbZone):
        if not entity.active:
            continue
        rz = entity.get_component(ReverbZone)
        if rz and rz.enabled:
            try:
                lines.extend(rz.gizmo_lines())
            except Exception:
                pass
    _submit_lines_fast(lines)


def render_script_gizmos(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    meshes = []
    for entity in scene.get_entities_with_component(ScriptComponent):
        if not entity.active:
            continue
        for c in entity.get_components(ScriptComponent):
            try:
                lns = c.gizmo_lines()
                if lns:
                    lines.extend(lns)
            except Exception:
                pass
            try:
                msh = c.gizmo_meshes()
                if msh:
                    meshes.extend(msh)
            except Exception:
                pass
    _submit_lines_fast(lines)
    if meshes:
        vp._renderer.render_gizmo_meshes(meshes, vp_mat)


def _box_edges(bmin: np.ndarray, bmax: np.ndarray) -> list[tuple[Vec3, Vec3]]:
    x0, y0, z0 = float(bmin[0]), float(bmin[1]), float(bmin[2])
    x1, y1, z1 = float(bmax[0]), float(bmax[1]), float(bmax[2])
    pts = [
        Vec3(x0, y0, z0), Vec3(x1, y0, z0),
        Vec3(x1, y0, z0), Vec3(x1, y1, z0),
        Vec3(x1, y1, z0), Vec3(x0, y1, z0),
        Vec3(x0, y1, z0), Vec3(x0, y0, z0),
        Vec3(x0, y0, z1), Vec3(x1, y0, z1),
        Vec3(x1, y0, z1), Vec3(x1, y1, z1),
        Vec3(x1, y1, z1), Vec3(x0, y1, z1),
        Vec3(x0, y1, z1), Vec3(x0, y0, z1),
        Vec3(x0, y0, z0), Vec3(x0, y0, z1),
        Vec3(x1, y0, z0), Vec3(x1, y0, z1),
        Vec3(x1, y1, z0), Vec3(x1, y1, z1),
        Vec3(x0, y1, z0), Vec3(x0, y1, z1),
    ]
    return [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]


DASH_LEN = 0.3
GAP_LEN = 0.15


def _dashed_lines(segments: list[tuple[Vec3, Vec3, list]],
                  time_s: float) -> list[tuple[Vec3, Vec3, list]]:
    total = DASH_LEN + GAP_LEN
    offset = (time_s * 1.2) % total
    out = []
    color = None
    for start, end, c in segments:
        if color is None:
            color = c
        dx = end.x - start.x
        dy = end.y - start.y
        dz = end.z - start.z
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 0.001:
            continue
        nx = dx / length
        ny = dy / length
        nz = dz / length
        pos = offset
        while pos < length:
            d_end = min(pos + DASH_LEN, length)
            out.append((
                Vec3(start.x + nx * pos, start.y + ny * pos, start.z + nz * pos),
                Vec3(start.x + nx * d_end, start.y + ny * d_end, start.z + nz * d_end),
                color
            ))
            pos += total
    return out


def _build_unit_sphere_cache(segments: int = 8):
    verts = []
    idx = []
    for lat in range(segments):
        theta1 = math.pi * lat / segments
        theta2 = math.pi * (lat + 1) / segments
        for lon in range(segments):
            phi1 = 2.0 * math.pi * lon / segments
            phi2 = 2.0 * math.pi * (lon + 1) / segments
            s = math.sin
            c = math.cos
            p0 = (s(theta1) * c(phi1), c(theta1), s(theta1) * s(phi1))
            p1 = (s(theta1) * c(phi2), c(theta1), s(theta1) * s(phi2))
            p2 = (s(theta2) * c(phi2), c(theta2), s(theta2) * s(phi2))
            p3 = (s(theta2) * c(phi1), c(theta2), s(theta2) * s(phi1))
            i0 = len(verts)
            verts.extend([p0, p1, p2, p3])
            idx.extend([i0, i0 + 1, i0 + 2, i0, i0 + 2, i0 + 3])
    return (verts, idx)


def _render_corner_spheres(vp, vp_mat, cam_pos, fw, fh, corners, radius, color):
    cache = getattr(_render_corner_spheres, '_cache', None)
    if cache is None:
        cache = _build_unit_sphere_cache(segments=8)
        _render_corner_spheres._cache = cache
    cverts, cidx = cache
    nv = len(cverts)
    all_verts = []
    all_idx = []
    all_cols = []
    for corner in corners:
        base = len(all_verts)
        for v in cverts:
            all_verts.append(Vec3(corner.x + v[0] * radius, corner.y + v[1] * radius, corner.z + v[2] * radius))
        for i in cidx:
            all_idx.append(base + i)
        all_cols.extend([color] * nv)
    vp._renderer.render_gizmo_meshes([(all_verts, all_idx, all_cols)], vp_mat)


def _render_entity_bounds(vp, vp_mat, time_s, dt, entities, color, state):
    from editor.viewport.picking import _world_aabb_of
    bmin_t = None
    bmax_t = None
    for entity in entities:
        if entity is None:
            continue
        box = _world_aabb_of(entity)
        if box is not None:
            if bmin_t is None:
                bmin_t, bmax_t = box[0].copy(), box[1].copy()
            else:
                bmin_t = np.minimum(bmin_t, box[0])
                bmax_t = np.maximum(bmax_t, box[1])
    if state is None:
        return
    if len(state) < 3:
        state.append(0.0)
    cur_min, cur_max, alpha = state[0], state[1], state[2]
    cfg = get_global_config()
    speed = cfg.get("gizmo.selection_bounds_speed", 8.0)
    fade_speed = cfg.get("gizmo.selection_bounds_fade_speed", 4.0)
    factor = 1.0 - np.exp(-speed * dt) if dt > 0.0 else 1.0
    fade_factor = 1.0 - np.exp(-fade_speed * dt) if dt > 0.0 else 1.0
    if bmin_t is not None:
        if cur_min is None:
            center = (bmin_t + bmax_t) * 0.5
            cur_min = center.copy()
            cur_max = center.copy()
            state[0] = cur_min
            state[1] = cur_max
            alpha = 0.0
        else:
            cur_min = cur_min + (bmin_t - cur_min) * factor
            cur_max = cur_max + (bmax_t - cur_max) * factor
            alpha = min(1.0, alpha + fade_factor)
    else:
        if cur_min is not None:
            alpha = max(0.0, alpha - fade_factor)
            if alpha <= 0.0:
                state[0] = None
                state[1] = None
                state[2] = 0.0
                return
            center = (cur_min + cur_max) * 0.5
            t = 1.0 - alpha
            cur_min = cur_min + (center - cur_min) * t
            cur_max = cur_max + (center - cur_max) * t
        else:
            return
    state[0], state[1], state[2] = cur_min, cur_max, alpha
    cam_pos = vp._cam.position if vp._cam else Vec3(0, 0, 0)
    fw, fh = vp._get_physical_dims()
    raw_segments = [(a, b, color) for a, b in _box_edges(cur_min, cur_max)]
    dashed = _dashed_lines(raw_segments, time_s * 1.5)
    vp._renderer.render_gizmo_lines(dashed, vp_mat, cam_pos, fw, fh, thickness_multiplier=1.5)
    cx = float(cur_min[0]); cy = float(cur_min[1]); cz = float(cur_min[2])
    dx = float(cur_max[0]); dy = float(cur_max[1]); dz = float(cur_max[2])
    verts_3d = [
        Vec3(cx, cy, cz), Vec3(dx, cy, cz), Vec3(dx, dy, cz), Vec3(cx, dy, cz),
        Vec3(cx, cy, dz), Vec3(dx, cy, dz), Vec3(dx, dy, dz), Vec3(cx, dy, dz),
    ]
    center = Vec3((cx + dx) * 0.5, (cy + dy) * 0.5, (cz + dz) * 0.5)
    dist = (center - cam_pos).length()
    fov_rad = math.radians(vp._cam.fov) if vp._cam else 1.0
    pixel_r = 6
    world_r = pixel_r * 2.0 * dist * math.tan(fov_rad * 0.5) / fh if fh > 0 else 0.05
    world_r = max(world_r, 0.01)
    if alpha < 1.0:
        faded = list(color)
        if len(faded) > 3:
            faded[3] = faded[3] * alpha
        else:
            faded.append(alpha)
        _render_corner_spheres(vp, vp_mat, cam_pos, fw, fh, verts_3d, world_r, faded)
    else:
        _render_corner_spheres(vp, vp_mat, cam_pos, fw, fh, verts_3d, world_r, color)


def render_selection_bounds(vp, vp_mat: Mat4, time_s: float, dt: float = 0.0):
    cfg = get_global_config()
    if not cfg.get("gizmo.selection_bounds", True):
        return
    if not hasattr(vp, '_sel_bounds_state'):
        old_min = getattr(vp, '_sel_bounds_min', None)
        old_max = getattr(vp, '_sel_bounds_max', None)
        vp._sel_bounds_state = [old_min, old_max]
    color = [
        cfg.get("gizmo.selection_bounds_color_r", 0.25),
        cfg.get("gizmo.selection_bounds_color_g", 0.55),
        cfg.get("gizmo.selection_bounds_color_b", 1.0),
        1.0,
    ]
    selected = getattr(vp, '_selected_entities', None) or []
    _render_entity_bounds(vp, vp_mat, time_s, dt, selected, color, vp._sel_bounds_state)
    collab = vp._engine.collab_manager if hasattr(vp._engine, 'collab_manager') else None
    if not collab or not collab.connected:
        return
    scene = vp._engine.scene
    if not scene:
        return
    if not hasattr(vp, '_sel_bounds_peers'):
        vp._sel_bounds_peers = {}
    for peer_id, peer in collab.peers.items():
        if not peer.selected_entity_ids:
            vp._sel_bounds_peers.pop(peer_id, None)
            continue
        peer_entities = [scene.get_entity(eid) for eid in peer.selected_entity_ids]
        peer_entities = [e for e in peer_entities if e is not None]
        if not peer_entities:
            vp._sel_bounds_peers.pop(peer_id, None)
            continue
        peer_color = peer.color + [1.0]
        if peer_id not in vp._sel_bounds_peers:
            vp._sel_bounds_peers[peer_id] = [None, None]
        _render_entity_bounds(vp, vp_mat, time_s, dt, peer_entities, peer_color, vp._sel_bounds_peers[peer_id])
