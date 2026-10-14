# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import math

from plugins.zarin_mcp.main_thread import run_on_main_thread
from .capture import _resolve_viewport


def _read_editor_cam(cam) -> dict:
    pos = cam.position
    try:
        fwd = cam.forward
        fwd_list = [float(fwd.x), float(fwd.y), float(fwd.z)]
    except Exception:
        fwd_list = [0.0, 0.0, -1.0]
    return {
        "position": [float(pos.x), float(pos.y), float(pos.z)],
        "yaw": float(cam.yaw),
        "pitch": float(cam.pitch),
        "forward": fwd_list,
        "fov": float(getattr(cam, "fov", 60.0)),
        "near": float(getattr(cam, "near", 0.01)),
        "far": float(getattr(cam, "far", 1000.0)),
        "is_2d_mode": bool(cam.is_2d_mode) if callable(getattr(cam, "is_2d_mode", None)) else bool(getattr(cam, "is_2d_mode", False)),
    }


def _snap_editor_cam(cam, position=None, target=None, yaw=None, pitch=None, fov=None) -> None:
    from core.maths.math3d import Vec3
    if position is not None:
        cam._position = Vec3(float(position[0]), float(position[1]), float(position[2]))
    if target is not None:
        tgt = Vec3(float(target[0]), float(target[1]), float(target[2]))
        direction = (tgt - cam._position).normalized()
        if direction.length() > 1e-9:
            yaw = math.degrees(math.atan2(-direction.x, -direction.z))
            pitch = math.degrees(math.asin(max(-1.0, min(1.0, -direction.y))))
    if yaw is not None:
        cam._yaw = float(yaw)
    if pitch is not None:
        cam._pitch = max(-89.0, min(89.0, float(pitch)))
    if fov is not None:
        try:
            cam.fov = float(fov)
        except Exception:
            cam._fov = max(1.0, min(179.0, float(fov)))
    try:
        cam._orbiting = False
    except Exception:
        pass
    try:
        from core.maths.math3d import Vec3 as _V
        cam._vel = _V.zero()
    except Exception:
        pass
    cam._focus_active = False
    cam._focus_transition_blend = 1.0


def _find_active_camera_entity(scene):
    try:
        from core.components.rendering.cameras.camera import Camera
    except Exception:
        return None, None
    try:
        candidates = scene.get_entities_with_component(Camera)
    except Exception:
        return None, None
    for ent in candidates:
        if not ent.active:
            continue
        comp = ent.get_component(Camera)
        if comp is not None and comp.enabled:
            return ent, comp
    return None, None


def register_camera(registry, engine):
    @registry.tool(
        "viewport_get_camera",
        "Get the viewport camera pose (editor camera, or active Camera entity in play mode)",
        {"type": "object", "properties": {}},
    )
    def viewport_get_camera():
        def _do():
            vp = _resolve_viewport(engine)
            if vp is None:
                return {"error": "No viewport (headless mode)"}
            cam = getattr(vp, "_cam", None)
            if cam is not None:
                data = _read_editor_cam(cam)
                data["source"] = "editor_camera"
                return data
            scene = engine.scene
            if scene is None:
                return {"error": "No scene loaded"}
            ent, _comp = _find_active_camera_entity(scene)
            if ent is None:
                return {"error": "No active Camera entity and no editor camera"}
            t = ent.transform
            pos = [float(t.position.x), float(t.position.y), float(t.position.z)] if t else [0.0, 0.0, 0.0]
            try:
                fwd = t.forward
                fwd_list = [float(fwd.x), float(fwd.y), float(fwd.z)]
            except Exception:
                fwd_list = [0.0, 0.0, -1.0]
            return {
                "source": "camera_entity",
                "entity_id": ent.id,
                "entity_name": ent.name,
                "position": pos,
                "forward": fwd_list,
            }
        return run_on_main_thread(_do, timeout_ms=15000)

    @registry.tool(
        "viewport_set_camera",
        "Move the viewport camera. Editor: position + target (or yaw/pitch) + fov. Play mode: moves the active Camera entity (position + target).",
        {
            "type": "object",
            "properties": {
                "position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[x, y, z] camera world position",
                },
                "target": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[x, y, z] look-at target world position",
                },
                "yaw": {"type": "number", "description": "Yaw in degrees (editor camera only)"},
                "pitch": {"type": "number", "description": "Pitch in degrees, clamped to [-89, 89] (editor camera only)"},
                "fov": {"type": "number", "description": "Field of view in degrees (editor camera only)"},
            },
        },
    )
    def viewport_set_camera(position=None, target=None, yaw=None, pitch=None, fov=None):
        if position is not None and len(list(position)) != 3:
            return {"error": "position must be [x, y, z]"}
        if target is not None and len(list(target)) != 3:
            return {"error": "target must be [x, y, z]"}
        if position is None and target is None and yaw is None and pitch is None and fov is None:
            return {"error": "Nothing to set: pass position, target, yaw, pitch or fov"}

        def _do():
            vp = _resolve_viewport(engine)
            if vp is None:
                return {"error": "No viewport (headless mode)"}
            cam = getattr(vp, "_cam", None)
            if cam is not None:
                _snap_editor_cam(cam, position, target, yaw, pitch, fov)
                try:
                    vp.update()
                except Exception:
                    pass
                return {"message": "Editor camera updated", **_read_editor_cam(cam)}
            if position is None or target is None:
                return {"error": "Play-mode camera needs both position and target"}
            scene = engine.scene
            if scene is None:
                return {"error": "No scene loaded"}
            ent, _comp = _find_active_camera_entity(scene)
            if ent is None:
                return {"error": "No active Camera entity"}
            t = ent.transform
            if t is None:
                return {"error": "Camera entity has no Transform"}
            from core.maths.math3d import Vec3, Quat
            t.position = Vec3(float(position[0]), float(position[1]), float(position[2]))
            direction = Vec3(*[float(v) for v in target]) - t.position
            if direction.length() < 1e-10:
                return {"error": "Target is at the same position as camera"}
            t.rotation = Quat.look_rotation(direction, Vec3(0, 1, 0))
            return {
                "message": f"Moved camera entity '{ent.name}'",
                "entity_id": ent.id,
                "position": [float(v) for v in position],
                "target": [float(v) for v in target],
            }
        return run_on_main_thread(_do, timeout_ms=15000)

    @registry.tool(
        "viewport_frame_entity",
        "Animate the editor camera to frame an entity (by ID or name)",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "entity_name": {"type": "string", "description": "Entity name fallback"},
                "radius": {"type": "number", "description": "Bounding radius used for framing", "default": 5.0},
            },
        },
    )
    def viewport_frame_entity(entity_id="", entity_name="", radius=5.0):
        def _do():
            vp = _resolve_viewport(engine)
            if vp is None:
                return {"error": "No viewport (headless mode)"}
            cam = getattr(vp, "_cam", None)
            if cam is None or not hasattr(cam, "frame_bounds"):
                return {"error": "Editor camera does not support framing"}
            scene = engine.scene
            if scene is None:
                return {"error": "No scene loaded"}
            ent = None
            if entity_id:
                ent = scene.get_entity(entity_id)
            if ent is None and entity_name:
                ent = scene.get_entity_by_name(entity_name)
            if ent is None:
                return {"error": "Entity not found"}
            t = ent.transform
            if t is None:
                return {"error": "Entity has no Transform"}
            try:
                radius_f = max(0.1, float(radius))
            except (TypeError, ValueError):
                radius_f = 5.0
            from core.maths.math3d import Vec3
            center = Vec3(float(t.position.x), float(t.position.y), float(t.position.z))
            try:
                cam.frame_bounds(center, radius_f)
            except Exception as ex:
                return {"error": f"frame_bounds failed: {ex}"}
            return {"message": f"Framing entity '{ent.name}'", "center": [center.x, center.y, center.z], "radius": radius_f}
        return run_on_main_thread(_do, timeout_ms=15000)
