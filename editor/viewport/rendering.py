from __future__ import annotations

from core.math3d import Mat4, Vec3
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
