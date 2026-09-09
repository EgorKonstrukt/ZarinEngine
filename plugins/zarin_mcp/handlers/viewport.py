# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import base64
import math
import os
import time as _time

from plugins.zarin_mcp.main_thread import run_on_main_thread

_CAPTURE_SUBDIR = ".mcp_captures"
_MAX_KEPT_CAPTURES = 20


def _captures_dir(engine) -> str:
    root = engine.project_root or os.getcwd()
    path = os.path.join(root, _CAPTURE_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def _prune_captures(folder: str) -> None:
    try:
        files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.startswith("viewport_") and os.path.isfile(os.path.join(folder, f))
        ]
    except OSError:
        return
    files.sort(key=lambda p: os.path.getmtime(p))
    for stale in files[:-_MAX_KEPT_CAPTURES]:
        try:
            os.remove(stale)
        except OSError:
            pass


def _resolve_viewport(engine):
    vp = getattr(engine, "viewport", None)
    if vp is not None:
        return vp
    try:
        mw = engine.get_main_window()
    except Exception:
        mw = None
    if mw is not None:
        for attr in ("_viewport", "viewport"):
            vp = getattr(mw, attr, None)
            if vp is not None:
                return vp
    return None


def _viewport_kind(vp) -> str:
    cls_name = type(vp).__name__
    if hasattr(vp, "_cam"):
        return "editor"
    if "GameViewport" in cls_name:
        return "game"
    return "unknown"


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


def register(registry, engine):

    @registry.tool(
        "viewport_get_info",
        "Get viewport info: kind (editor/game), size, visibility, fps",
        {"type": "object", "properties": {}},
    )
    def viewport_get_info():
        def _do():
            vp = _resolve_viewport(engine)
            if vp is None:
                return {"error": "No viewport (headless mode)"}
            try:
                w, h = int(vp.width()), int(vp.height())
            except Exception:
                w, h = 0, 0
            try:
                dpr = float(vp.devicePixelRatio())
            except Exception:
                dpr = 1.0
            try:
                visible = bool(vp.isVisible())
            except Exception:
                visible = False
            return {
                "kind": _viewport_kind(vp),
                "widget": type(vp).__name__,
                "width": w,
                "height": h,
                "device_pixel_ratio": dpr,
                "physical_width": int(w * dpr),
                "physical_height": int(h * dpr),
                "visible": visible,
                "widget_fps": round(float(getattr(vp, "_fps", 0.0)), 1),
                "play_mode": bool(getattr(engine, "play_mode", False)),
            }
        return run_on_main_thread(_do, timeout_ms=15000)

    @registry.tool(
        "viewport_screenshot",
        "Capture the viewport (editor or game view) to an image file. Returns the file path.",
        {
            "type": "object",
            "properties": {
                "max_width": {
                    "type": "integer",
                    "description": "Downscale image to this width (keeps aspect, never upscales)",
                    "default": 768,
                },
                "format": {
                    "type": "string",
                    "description": "Image format: jpg or png",
                    "default": "jpg",
                },
                "quality": {
                    "type": "integer",
                    "description": "JPEG quality 10-100 (ignored for png)",
                    "default": 70,
                },
                "fresh": {
                    "type": "boolean",
                    "description": "Force an immediate repaint before capture",
                    "default": True,
                },
                "inline": {
                    "type": "boolean",
                    "description": "Also embed base64 image content in the tool result",
                    "default": False,
                },
            },
        },
    )
    def viewport_screenshot(max_width=768, format="jpg", quality=70, fresh=True, inline=False):
        fmt = str(format).lower().strip()
        if fmt not in ("jpg", "jpeg", "png"):
            return {"error": f"Unsupported format '{format}', use jpg or png"}
        if fmt == "jpeg":
            fmt = "jpg"
        try:
            max_width = max(64, min(2048, int(max_width)))
        except (TypeError, ValueError):
            max_width = 768
        try:
            quality = max(10, min(100, int(quality)))
        except (TypeError, ValueError):
            quality = 70

        def _do():
            from PyQt6.QtCore import Qt
            vp = _resolve_viewport(engine)
            if vp is None:
                return {"error": "No viewport (headless mode)"}
            grab = getattr(vp, "grabFramebuffer", None)
            if not callable(grab):
                return {"error": f"Viewport '{type(vp).__name__}' does not support screenshots"}
            try:
                if not vp.isVisible():
                    return {"error": "Viewport is not visible"}
            except Exception:
                pass
            if fresh:
                try:
                    vp.repaint()
                except Exception:
                    try:
                        vp.update()
                    except Exception:
                        pass
            try:
                img = grab()
            except Exception as ex:
                return {"error": f"grabFramebuffer failed: {ex}"}
            if img is None or img.isNull():
                return {"error": "Captured null image"}
            if img.width() > max_width:
                img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
            folder = _captures_dir(engine)
            stamp = _time.strftime("%Y%m%d_%H%M%S")
            name = f"viewport_{stamp}_{img.width()}x{img.height()}.{fmt}"
            path = os.path.join(folder, name)
            try:
                if fmt == "jpg":
                    ok = img.save(path, "JPG", quality)
                    mime = "image/jpeg"
                else:
                    ok = img.save(path, "PNG")
                    mime = "image/png"
            except Exception as ex:
                return {"error": f"Failed to save screenshot: {ex}"}
            if not ok:
                return {"error": f"Failed to save screenshot to {path}"}
            _prune_captures(folder)
            result = {
                "path": path,
                "width": int(img.width()),
                "height": int(img.height()),
                "format": fmt,
                "viewport": type(vp).__name__,
            }
            if inline:
                try:
                    with open(path, "rb") as f:
                        result["image_base64"] = base64.b64encode(f.read()).decode("ascii")
                    result["mime_type"] = mime
                except OSError as ex:
                    result["inline_error"] = str(ex)
            return result
        return run_on_main_thread(_do, timeout_ms=30000)

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

    @registry.tool(
        "viewport_set_grid_visible",
        "Show or hide the editor world grid overlay (it is drawn on top of additive volume effects)",
        {
            "type": "object",
            "properties": {
                "visible": {
                    "type": "boolean",
                    "description": "True to show the grid, False to hide it",
                },
            },
            "required": ["visible"],
        },
    )
    def viewport_set_grid_visible(visible=True):
        flag = bool(visible)

        def _do():
            vp = _resolve_viewport(engine)
            if vp is None:
                return {"error": "No viewport (headless mode)"}
            renderer = getattr(vp, "_renderer", None)
            if renderer is None:
                return {"error": f"Viewport '{type(vp).__name__}' has no renderer"}
            if not hasattr(renderer, "show_grid"):
                return {"error": "Renderer does not support grid toggle"}
            try:
                previous = bool(renderer.show_grid)
            except Exception:
                previous = None
            try:
                renderer.show_grid = flag
            except Exception as ex:
                return {"error": f"Failed to set grid visibility: {ex}"}
            return {"message": f"Grid {'shown' if flag else 'hidden'}", "visible": flag, "previous": previous}
        return run_on_main_thread(_do, timeout_ms=15000)
