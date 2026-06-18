from __future__ import annotations

import math
import numpy as np
from core.math3d import Mat4, Vec3
from core.config import get_global_config
from editor.gizmo.gizmo_drawer import GizmoDrawer, FillMode
from editor.gizmo.gizmo_collider import get_collider_wireframe_lines
from editor.gizmo.gizmo_particle import get_particle_emitter_lines
from editor.gizmo.gizmo_camera import get_camera_frustum_lines
from editor.gizmo.gizmo_audio import get_audio_source_gizmo_lines
from core.components.physics.mesh_collider import MeshCollider
from core.components.physics.box_collider import BoxCollider
from core.components.physics.sphere_collider import SphereCollider
from core.components.physics.capsule_collider import CapsuleCollider
from core.components.physics.rigidbody import Rigidbody
from core.components.scripting.script_component import ScriptComponent
from core.components.rendering.particle_system import ParticleSystem
from core.components.rendering.camera import Camera
from core.components.audio.audio_source import AudioSource
from core.components.audio.reverb_zone import ReverbZone


def render_collider_wireframes(vp, vp_mat: Mat4):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    cam_pos = vp._cam.position if vp._cam else Vec3(0, 0, 0)
    MAX_DISTANCE = 20.0
    lines = []
    seen = set()
    for collider_type in (MeshCollider, BoxCollider, SphereCollider, CapsuleCollider):
        for entity in scene.get_entities_with_component(collider_type):
            if not entity.active or entity.id in seen:
                continue
            seen.add(entity.id)
            if collider_type is MeshCollider:
                tr = entity.get_component_by_name("Transform")
                if tr and (tr.local_position - cam_pos).length() > MAX_DISTANCE:
                    continue
                if getattr(vp._engine, 'play_mode', False) and entity.get_component(Rigidbody):
                    continue
            lines.extend(get_collider_wireframe_lines(entity))
    if lines:
        cp = vp._cam.position if vp._cam else Vec3(0, 0, 0)
        fw, fh = vp._get_physical_dims()
        vp._renderer.render_gizmo_lines(lines, vp_mat, cp, fw, fh, thickness_multiplier=1.0)


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
    if bmin_t is None:
        if state is not None:
            state[0] = None
            state[1] = None
        return
    cur_min = state[0] if state is not None else None
    cur_max = state[1] if state is not None else None
    if cur_min is None:
        cur_min = bmin_t.copy()
        cur_max = bmax_t.copy()
    else:
        cfg = get_global_config()
        speed = cfg.get("gizmo.selection_bounds_speed", 8.0)
        factor = 1.0 - np.exp(-speed * dt) if dt > 0.0 else 1.0
        cur_min = cur_min + (bmin_t - cur_min) * factor
        cur_max = cur_max + (bmax_t - cur_max) * factor
    if state is not None:
        state[0] = cur_min
        state[1] = cur_max
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
    sphere_color = [color[0], color[1], color[2], 1.0] if len(color) >= 3 else [0.6, 0.2, 0.8, 1.0]
    meshes = []
    for v in verts_3d:
        _, sphere_meshes = GizmoDrawer.sphere(v, world_r, sphere_color, FillMode.SOLID, segments=8)
        meshes.extend(sphere_meshes)
    if meshes:
        vp._renderer.render_gizmo_meshes(meshes, vp_mat)


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
