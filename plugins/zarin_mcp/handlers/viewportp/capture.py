# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import base64
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


def register_capture(registry, engine):
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
