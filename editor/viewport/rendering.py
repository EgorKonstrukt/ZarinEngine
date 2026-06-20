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
from editor.gizmo.gizmo_collider import _load_mesh_data, _get_convex_hull_edges, _get_decimated_hull_edges
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
    c = pos + rot.rotate_vec3(comp.scaled_center)
    local_offsets = [
        Vec3(-hx, -hy, -hz), Vec3(hx, -hy, -hz), Vec3(hx, hy, -hz), Vec3(-hx, hy, -hz),
        Vec3(-hx, -hy, hz), Vec3(hx, -hy, hz), Vec3(hx, hy, hz), Vec3(-hx, hy, hz),
    ]
    corners = [(c + rot.rotate_vec3(o)) for o in local_offsets]
    starts, ends = _box_starts_ends(corners)
    return starts, ends, _collider_color_arr(12, color)


def _build_sphere_np(comp, pos: Vec3, rot, sc: Vec3, color: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    radius = comp.scaled_radius
    c = pos + rot.rotate_vec3(comp.scaled_center)
    segs = 24
    total = segs * 3
    starts = np.zeros((total, 3), dtype=np.float32)
    ends = np.zeros((total, 3), dtype=np.float32)
    idx = 0
    for axis_idx in range(3):
        pts = []
        for i in range(segs + 1):
            theta = 2.0 * math.pi * i / segs
            if axis_idx == 0:
                pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
            elif axis_idx == 1:
                pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
            else:
                pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
            pts.append(c + rot.rotate_vec3(pt))
        for i in range(segs):
            starts[idx, 0] = pts[i].x; starts[idx, 1] = pts[i].y; starts[idx, 2] = pts[i].z
            ends[idx, 0] = pts[i+1].x; ends[idx, 1] = pts[i+1].y; ends[idx, 2] = pts[i+1].z
            idx += 1
    return starts, ends, _collider_color_arr(total, color)


def _build_capsule_np(comp, pos: Vec3, rot, sc: Vec3, color: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    radius = comp.scaled_radius
    half_h = max(0, comp.scaled_height * 0.5 - radius)
    c = pos + rot.rotate_vec3(comp.scaled_center)
    dir_idx = getattr(comp, "direction", 1)
    axis_vecs = [Vec3.right(), Vec3.up(), Vec3.forward()]
    axis = axis_vecs[dir_idx] if dir_idx < 3 else Vec3.up()
    segs = 20
    top_center = c + rot.rotate_vec3(axis * half_h)
    bottom_center = c - rot.rotate_vec3(axis * half_h)
    lines_per_ring = segs * 2
    total = 0
    ring_counts = []
    for ring_axis in range(3):
        if ring_axis == dir_idx:
            continue
        total += lines_per_ring
        ring_counts.append(lines_per_ring)
    total += 8
    starts = np.zeros((total, 3), dtype=np.float32)
    ends = np.zeros((total, 3), dtype=np.float32)
    idx = 0
    for ring_axis in range(3):
        if ring_axis == dir_idx:
            continue
        u = Vec3.right(); v = Vec3.forward()
        if ring_axis == 0:
            u = Vec3(0, 1, 0); v = Vec3(0, 0, 1)
        elif ring_axis == 1:
            u = Vec3(1, 0, 0); v = Vec3(0, 0, 1)
        pts_top = []; pts_bot = []
        for i in range(segs + 1):
            theta = 2.0 * math.pi * i / segs
            rp = (u * math.cos(theta) + v * math.sin(theta)) * radius
            pts_top.append(top_center + rot.rotate_vec3(rp))
            pts_bot.append(bottom_center + rot.rotate_vec3(rp))
        for i in range(segs):
            starts[idx, 0] = pts_top[i].x; starts[idx, 1] = pts_top[i].y; starts[idx, 2] = pts_top[i].z
            ends[idx, 0] = pts_top[i+1].x; ends[idx, 1] = pts_top[i+1].y; ends[idx, 2] = pts_top[i+1].z
            idx += 1
            starts[idx, 0] = pts_bot[i].x; starts[idx, 1] = pts_bot[i].y; starts[idx, 2] = pts_bot[i].z
            ends[idx, 0] = pts_bot[i+1].x; ends[idx, 1] = pts_bot[i+1].y; ends[idx, 2] = pts_bot[i+1].z
            idx += 1
    for i in range(8):
        theta = 2.0 * math.pi * i / 8
        u = Vec3.right(); v = Vec3.forward()
        if dir_idx == 0:
            u = Vec3(0, 1, 0); v = Vec3(0, 0, 1)
        elif dir_idx == 1:
            u = Vec3(1, 0, 0); v = Vec3(0, 0, 1)
        rp = (u * math.cos(theta) + v * math.sin(theta)) * radius
        tp = top_center + rot.rotate_vec3(rp)
        bp = bottom_center + rot.rotate_vec3(rp)
        starts[idx, 0] = tp.x; starts[idx, 1] = tp.y; starts[idx, 2] = tp.z
        ends[idx, 0] = bp.x; ends[idx, 1] = bp.y; ends[idx, 2] = bp.z
        idx += 1
    return starts, ends, _collider_color_arr(total, color)


def _build_mesh_collider_lines_np(comp, entity, pos: Vec3, rot, sc: Vec3):
    mesh_color = [0.0, 0.8, 0.2, 0.6]
    mesh_path = getattr(comp, "mesh_path", "")
    mode = getattr(comp, "collision_mode", CollisionMode.AUTO)
    max_verts = getattr(comp, "max_vertices", 2000)
    md = _load_mesh_data(mesh_path) if mesh_path else None
    if md is None or md["num_verts"] == 0:
        c = pos + rot.rotate_vec3(Vec3(0, 0, 0))
        s = 0.5
        corners = [c + rot.rotate_vec3(Vec3(-s, -s, -s)), c + rot.rotate_vec3(Vec3(s, -s, -s)),
                   c + rot.rotate_vec3(Vec3(s, s, -s)), c + rot.rotate_vec3(Vec3(-s, s, -s)),
                   c + rot.rotate_vec3(Vec3(-s, -s, s)), c + rot.rotate_vec3(Vec3(s, -s, s)),
                   c + rot.rotate_vec3(Vec3(s, s, s)), c + rot.rotate_vec3(Vec3(-s, s, s))]
        starts, ends = _box_starts_ends(corners)
        Gizmos.draw_lines(starts, ends, _collider_color_arr(12, mesh_color))
        return

    def _tw(v: Vec3) -> Vec3:
        return pos + rot.rotate_vec3(Vec3(v.x * sc.x, v.y * sc.y, v.z * sc.z))

    starts_list: list[Vec3] = []
    ends_list: list[Vec3] = []

    def _box_from_bounds(mins_np, maxs_np):
        size = maxs_np - mins_np
        ctr_np = (mins_np + maxs_np) * 0.5
        ctr = Vec3(float(ctr_np[0]), float(ctr_np[1]), float(ctr_np[2]))
        sv = Vec3(float(size[0]) * 0.5, float(size[1]) * 0.5, float(size[2]) * 0.5)
        local_offsets = [Vec3(-sv.x, -sv.y, -sv.z), Vec3(sv.x, -sv.y, -sv.z),
                         Vec3(sv.x, sv.y, -sv.z), Vec3(-sv.x, sv.y, -sv.z),
                         Vec3(-sv.x, -sv.y, sv.z), Vec3(sv.x, -sv.y, sv.z),
                         Vec3(sv.x, sv.y, sv.z), Vec3(-sv.x, sv.y, sv.z)]
        lc = [ctr + o for o in local_offsets]
        corners = [_tw(lc[i]) for i in range(8)]
        edge_pairs = [(0, 1), (1, 2), (2, 3), (3, 0),
                      (4, 5), (5, 6), (6, 7), (7, 4),
                      (0, 4), (1, 5), (2, 6), (3, 7)]
        for a, b in edge_pairs:
            starts_list.append(corners[a])
            ends_list.append(corners[b])
        for face in [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)]:
            starts_list.append(corners[face[0]]); ends_list.append(corners[face[2]])
            starts_list.append(corners[face[1]]); ends_list.append(corners[face[3]])

    if mode == CollisionMode.BOX:
        size = md["maxs"] - md["mins"]
        if np.all(size < 100.0):
            _box_from_bounds(md["mins"], md["maxs"])
        else:
            c = pos + rot.rotate_vec3(Vec3(0, 0, 0))
            s = 0.5
            corners = [c + rot.rotate_vec3(Vec3(-s, -s, -s)), c + rot.rotate_vec3(Vec3(s, -s, -s)),
                       c + rot.rotate_vec3(Vec3(s, s, -s)), c + rot.rotate_vec3(Vec3(-s, s, -s)),
                       c + rot.rotate_vec3(Vec3(-s, -s, s)), c + rot.rotate_vec3(Vec3(s, -s, s)),
                       c + rot.rotate_vec3(Vec3(s, s, s)), c + rot.rotate_vec3(Vec3(-s, s, s))]
            for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]:
                starts_list.append(corners[a]); ends_list.append(corners[b])

    elif mode == CollisionMode.SPHERE:
        c = _tw(Vec3(float(md["center"][0]), float(md["center"][1]), float(md["center"][2])))
        max_sc = max(sc.x, sc.y, sc.z)
        radius = md["radius"] * max_sc
        segs = 24
        for axis_idx in range(3):
            pts = []
            for i in range(segs + 1):
                theta = 2.0 * math.pi * i / segs
                if axis_idx == 0:
                    pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                elif axis_idx == 1:
                    pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                else:
                    pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                pts.append(c + rot.rotate_vec3(pt))
            for i in range(segs):
                starts_list.append(pts[i]); ends_list.append(pts[i + 1])

    elif mode == CollisionMode.CONVEX_HULL:
        hull_edges = _get_convex_hull_edges(mesh_path)
        if hull_edges is not None:
            for v0, v1 in hull_edges:
                starts_list.append(_tw(v0)); ends_list.append(_tw(v1))
        elif md["edges"]:
            for v0, v1 in md["edges"]:
                starts_list.append(_tw(v0)); ends_list.append(_tw(v1))

    elif mode == CollisionMode.AUTO:
        if md["num_verts"] > max_verts:
            hull_edges = _get_decimated_hull_edges(mesh_path, max_verts)
            if hull_edges is not None:
                for v0, v1 in hull_edges:
                    starts_list.append(_tw(v0)); ends_list.append(_tw(v1))
            else:
                size = md["maxs"] - md["mins"]
                if np.all(size < 100.0):
                    _box_from_bounds(md["mins"], md["maxs"])
                else:
                    c = pos + rot.rotate_vec3(Vec3(0, 0, 0))
                    s = 0.5
                    corners = [c + rot.rotate_vec3(Vec3(-s, -s, -s)), c + rot.rotate_vec3(Vec3(s, -s, -s)),
                               c + rot.rotate_vec3(Vec3(s, s, -s)), c + rot.rotate_vec3(Vec3(-s, s, -s)),
                               c + rot.rotate_vec3(Vec3(-s, -s, s)), c + rot.rotate_vec3(Vec3(s, -s, s)),
                               c + rot.rotate_vec3(Vec3(s, s, s)), c + rot.rotate_vec3(Vec3(-s, s, s))]
                    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]:
                        starts_list.append(corners[a]); ends_list.append(corners[b])
        else:
            for v0, v1 in md["edges"]:
                starts_list.append(_tw(v0)); ends_list.append(_tw(v1))

    elif md["edges"]:
        for v0, v1 in md["edges"]:
            starts_list.append(_tw(v0)); ends_list.append(_tw(v1))

    if starts_list:
        n = len(starts_list)
        starts = np.zeros((n, 3), dtype=np.float32)
        ends = np.zeros((n, 3), dtype=np.float32)
        for i in range(n):
            s = starts_list[i]; e = ends_list[i]
            starts[i, 0] = s.x; starts[i, 1] = s.y; starts[i, 2] = s.z
            ends[i, 0] = e.x; ends[i, 1] = e.y; ends[i, 2] = e.z
        Gizmos.draw_lines(starts, ends, _collider_color_arr(n, mesh_color))


def render_collider_wireframes(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    cam_pos = vp._cam.position if vp._cam else Vec3(0, 0, 0)
    MAX_DISTANCE = 20.0
    color = [0.0, 1.0, 0.0, 0.6]
    seen = set()
    for collider_type in (MeshCollider, BoxCollider, SphereCollider, CapsuleCollider):
        for entity in scene.get_entities_with_component(collider_type):
            if not entity.active or entity.id in seen:
                continue
            seen.add(entity.id)
            tr = entity.get_component_by_name("Transform")
            if not tr:
                continue
            if collider_type is MeshCollider:
                if (tr.local_position - cam_pos).length() > MAX_DISTANCE:
                    continue
                if getattr(vp._engine, 'play_mode', False) and entity.get_component(Rigidbody):
                    continue
            pos = tr.local_position
            rot = tr.local_rotation
            sc = tr.local_scale
            for comp in entity.get_all_components():
                cname = type(comp).__name__
                if cname == "BoxCollider":
                    Gizmos.draw_lines(*_build_box_np(comp, pos, rot, sc, color))
                elif cname == "SphereCollider":
                    Gizmos.draw_lines(*_build_sphere_np(comp, pos, rot, sc, color))
                elif cname == "CapsuleCollider":
                    Gizmos.draw_lines(*_build_capsule_np(comp, pos, rot, sc, color))
                elif cname == "BoxCollider2D":
                    sz = comp.scaled_size
                    off_v2 = comp.scaled_offset
                    c = pos + rot.rotate_vec3(Vec3(off_v2.x, off_v2.y, 0.0))
                    hx, hy = sz.x * 0.5, sz.y * 0.5
                    corners = [
                        c + rot.rotate_vec3(Vec3(-hx, -hy, 0.0)),
                        c + rot.rotate_vec3(Vec3(hx, -hy, 0.0)),
                        c + rot.rotate_vec3(Vec3(hx, hy, 0.0)),
                        c + rot.rotate_vec3(Vec3(-hx, hy, 0.0)),
                    ]
                    starts, ends = _box_starts_ends(corners, _RECT_EDGE_PAIRS)
                    Gizmos.draw_lines(starts, ends, _collider_color_arr(4, color))
                elif cname == "CircleCollider2D":
                    radius = comp.scaled_radius
                    off_v2 = comp.scaled_offset
                    c = pos + rot.rotate_vec3(Vec3(off_v2.x, off_v2.y, 0.0))
                    segs = 24
                    pts = []
                    for i in range(segs + 1):
                        theta = 2.0 * math.pi * i / segs
                        pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0.0)
                        pts.append(c + rot.rotate_vec3(pt))
                    starts, ends = _ring_starts_ends(pts, segs)
                    Gizmos.draw_lines(starts, ends, _collider_color_arr(segs, color))
                elif cname == "MeshCollider":
                    _build_mesh_collider_lines_np(comp, entity, pos, rot, sc)


def render_particle_emitter_wireframes(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    for entity in scene.get_entities_with_component(ParticleSystem):
        if entity.active:
            lines.extend(get_particle_emitter_lines(entity))
    if lines:
        cp = vp._cam.position if vp._cam else Vec3(0, 0, 0)
        fw, fh = vp._get_physical_dims()
        vp._renderer.render_gizmo_lines(lines, vp_mat, cp, fw, fh, thickness_multiplier=1.0)


def render_camera_frustums(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    for entity in scene.get_entities_with_component(Camera):
        if entity.active:
            lines.extend(get_camera_frustum_lines(entity))
    if lines:
        cp = vp._cam.position if vp._cam else Vec3(0, 0, 0)
        fw, fh = vp._get_physical_dims()
        vp._renderer.render_gizmo_lines(lines, vp_mat, cp, fw, fh, thickness_multiplier=0.3)


def render_audio_source_gizmos(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    lines = []
    for entity in scene.get_entities_with_component(AudioSource):
        if entity.active:
            lines.extend(get_audio_source_gizmo_lines(entity))
    if lines:
        cp = vp._cam.position if vp._cam else Vec3(0, 0, 0)
        fw, fh = vp._get_physical_dims()
        vp._renderer.render_gizmo_lines(lines, vp_mat, cp, fw, fh, thickness_multiplier=1.0)


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
    if lines:
        cp = vp._cam.position if vp._cam else Vec3(0, 0, 0)
        fw, fh = vp._get_physical_dims()
        vp._renderer.render_gizmo_lines(lines, vp_mat, cp, fw, fh, thickness_multiplier=1.0)


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
    if lines:
        cp = vp._cam.position if vp._cam else Vec3(0, 0, 0)
        fw, fh = vp._get_physical_dims()
        vp._renderer.render_gizmo_lines(lines, vp_mat, cp, fw, fh, thickness_multiplier=1.0)
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
