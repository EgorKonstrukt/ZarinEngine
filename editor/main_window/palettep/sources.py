# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import ast
import math
import os

from PyQt6.QtGui import QIcon

try:
    import qtawesome as qta
except ImportError:
    qta = None

_ASSET_EXTS = {
    ".zpes", ".zterr", ".py", ".pyx", ".mat", ".zpem",
    ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".fbx", ".obj",
    ".gltf", ".glb", ".wav", ".mp3", ".ogg", ".glsl", ".json",
    ".txt", ".md", ".shader", ".prefab",
}
_SKIP_DIRS = {
    "Library", ".git", "__pycache__", ".venv", "build", "dist",
    "crash_logs", ".idea", ".pytest_cache", "node_modules",
}

_CALC_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp, "abs": abs,
    "round": round, "min": min, "max": max, "pow": pow,
    "pi": math.pi, "e": math.e, "tau": math.tau,
}

_BUILTINS = [
    ("Toggle Play / Stop", "play", "Start or stop play mode", "fa5s.play"),
    ("Save All Scenes", "save-all", "Save every dirty scene tab", "fa5s.save"),
    ("New Scene", "new-scene", "Create a new scene tab", "fa5s.file"),
    ("Open Scene...", "open-scene", "Open a scene file in a new tab", "fa5s.folder-open"),
    ("Create Entity", "new-entity", "Create an entity in the current scene", "fa5s.plus"),
    ("Frame Selection", "frame", "Focus camera on selection", "fa5s.crosshairs"),
    ("Duplicate Selection", "duplicate", "Copy and paste selected entities", "fa5s.copy"),
    ("Delete Selection", "delete", "Delete selected entities", "fa5s.trash"),
    ("Select All Entities", "select-all", "Select every entity in the scene", "fa5s.list"),
    ("Undo", "undo", "Undo last change in this tab", "fa5s.undo"),
    ("Redo", "redo", "Redo last change in this tab", "fa5s.redo"),
    ("Gizmo: Translate", "gizmo-t", "Switch gizmo to translate", "fa5s.arrows-alt"),
    ("Gizmo: Rotate", "gizmo-r", "Switch gizmo to rotate", "fa5s.sync-alt"),
    ("Gizmo: Scale", "gizmo-s", "Switch gizmo to scale", "fa5s.expand-arrows-alt"),
    ("Copy Performance Stats", "copy-stats", "Copy stats overlay text to clipboard", "fa5s.clipboard"),
]

_ASSET_ICONS = {
    ".png": "fa5s.file-image", ".jpg": "fa5s.file-image", ".jpeg": "fa5s.file-image",
    ".tga": "fa5s.file-image", ".bmp": "fa5s.file-image",
    ".wav": "fa5s.file-audio", ".mp3": "fa5s.file-audio", ".ogg": "fa5s.file-audio",
    ".fbx": "fa5s.cube", ".obj": "fa5s.cube", ".gltf": "fa5s.cube", ".glb": "fa5s.cube",
    ".prefab": "fa5s.cube",
    ".py": "fa5b.python", ".pyx": "fa5b.python",
    ".mat": "fa5s.brush", ".zpem": "fa5s.brush",
    ".glsl": "fa5s.file-code", ".shader": "fa5s.file-code", ".json": "fa5s.file-code",
    ".txt": "fa5s.file-alt", ".md": "fa5s.file-alt",
}

_icon_cache: dict[str, QIcon] = {}
_zarin_icon: QIcon | None = None


def _qta(name: str) -> QIcon:
    try:
        hit = _icon_cache.get(name)
        if hit is not None:
            return hit
        icon = qta.icon(name, color=chr(35) + "d4d4d4") if qta is not None else QIcon()
        _icon_cache[name] = icon
        return icon
    except Exception:
        return QIcon()


def _scene_icon() -> QIcon:
    global _zarin_icon
    try:
        if _zarin_icon is None:
            svg = os.path.join(os.path.dirname(__file__), "..", "..", "zarin_icon.svg")
            _zarin_icon = QIcon(svg) if os.path.exists(svg) else QIcon()
        return _zarin_icon
    except Exception:
        return QIcon()


def _asset_icon(ext: str) -> QIcon:
    if ext == ".zpes":
        return _scene_icon()
    return _qta(_ASSET_ICONS.get(ext, "fa5s.file"))


def _script_icon(path: str) -> QIcon:
    try:
        from editor.main_window.tabs import _icon_for_script
        return _icon_for_script(path)
    except Exception:
        return _qta("fa5s.file-code")


def _collect_menu_commands(mw) -> list[tuple[str, str, object, object]]:
    out: list[tuple[str, str, object, object]] = []
    try:
        mb = mw.menuBar()
    except Exception:
        return out
    try:
        for top in mb.actions():
            menu = top.menu()
            if menu is None:
                continue
            prefix = (top.text() or "").replace("&", "")
            try:
                for act in menu.actions():
                    if act.isSeparator() or act.menu() is not None:
                        continue
                    title = (act.text() or "").replace("&", "")
                    if not title:
                        continue
                    try:
                        shortcut = act.shortcut().toString()
                    except Exception:
                        shortcut = ""
                    try:
                        icon = act.icon()
                        if icon.isNull():
                            icon = _qta("fa5s.bolt")
                    except Exception:
                        icon = _qta("fa5s.bolt")
                    out.append((title, f"{prefix}   [{shortcut}]" if shortcut else prefix, act, icon))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _collect_tab_rows(mw) -> list[tuple[str, str, object, object]]:
    out: list[tuple[str, str, object, object]] = []
    try:
        mgr = getattr(mw, "_scene_tab_manager", None)
        bar = getattr(mw, "_scene_tab_bar", None)
        if mgr is None or bar is None:
            return out
        for i in range(bar.count()):
            try:
                if mgr.is_script_tab(i):
                    p = mgr.script_path_at(i)
                    out.append((f"Go to script: {os.path.basename(p) or 'Untitled'}", p, ("script", p), _script_icon(p)))
                else:
                    nm = mgr.tab_name_at(i)
                    if nm is None:
                        continue
                    info = mgr.get_tab_info(nm)
                    sub = (info.path or "") if info is not None else ""
                    out.append((f"Go to scene: {nm}", sub, ("scene", nm), _scene_icon()))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _collect_entity_rows(mw, limit: int = 400) -> list[tuple[str, str, object, object]]:
    out: list[tuple[str, str, object, object]] = []
    try:
        eng = getattr(mw, "_engine", None)
        scene = getattr(eng, "scene", None)
        if scene is None:
            return out
        icon = _qta("fa5s.cube")
        for ent in scene.get_all_entities()[:limit]:
            try:
                nm = ent.name or "Entity"
                out.append((f"Select entity: {nm}", getattr(ent, "id", ""), ("entity", ent.id), icon))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _collect_asset_rows(mw, limit: int = 1200) -> list[tuple[str, str, object, object]]:
    out: list[tuple[str, str, object, object]] = []
    try:
        eng = getattr(mw, "_engine", None)
        root = getattr(eng, "project_root", None) or getattr(eng, "project_path", None) or os.getcwd()
        for dirpath, dirnames, filenames in os.walk(root):
            try:
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
                for fn in filenames:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in _ASSET_EXTS:
                        continue
                    full = os.path.join(dirpath, fn)
                    try:
                        rel = os.path.relpath(full, root)
                    except Exception:
                        rel = full
                    out.append((f"Open asset: {rel}", ext, ("asset", full), _asset_icon(ext)))
                    if len(out) >= limit:
                        return out
            except Exception:
                continue
    except Exception:
        pass
    return out


def _try_calculate(query: str):
    try:
        expr = query.strip()
        if expr.startswith("="):
            expr = expr[1:].strip()
        if not expr or len(expr) > 120:
            return None
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.Expression):
                continue
            if isinstance(node, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.UAdd, ast.USub, ast.Load)):
                continue
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
                continue
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                continue
            if isinstance(node, ast.Name) and node.id in _CALC_FUNCS:
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CALC_FUNCS and not isinstance(_CALC_FUNCS[node.func.id], float):
                continue
            return None
        value = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, dict(_CALC_FUNCS))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
            value = int(value)
        return expr, value
    except Exception:
        return None


def _matches(title: str, detail: str, query: str) -> bool:
    try:
        hay = (title + " " + detail).lower()
        return all(tok in hay for tok in query.lower().split())
    except Exception:
        return False
