# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import ast
import math
import os

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem

from core.foundation.logger import Logger

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
        icon = qta.icon(name, color="#d4d4d4") if qta is not None else QIcon()
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
        from editor.main_window.scene_tabs import _icon_for_script
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
        mgr = getattr(mw, '_scene_tab_manager', None)
        bar = getattr(mw, '_scene_tab_bar', None)
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
        eng = getattr(mw, '_engine', None)
        scene = getattr(eng, 'scene', None)
        if scene is None:
            return out
        icon = _qta("fa5s.cube")
        for ent in scene.get_all_entities()[:limit]:
            try:
                nm = ent.name or "Entity"
                out.append((f"Select entity: {nm}", getattr(ent, 'id', ''), ("entity", ent.id), icon))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _collect_asset_rows(mw, limit: int = 1200) -> list[tuple[str, str, object, object]]:
    out: list[tuple[str, str, object, object]] = []
    try:
        eng = getattr(mw, '_engine', None)
        root = getattr(eng, 'project_root', None) or getattr(eng, 'project_path', None) or os.getcwd()
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


def _viewport_of(mw):
    try:
        eng = getattr(mw, '_engine', None)
        return getattr(eng, 'viewport', None)
    except Exception:
        return None


def _run_builtin(mw, key: str) -> None:
    try:
        if key == "play":
            from editor.main_window.handlers import toggle_play_stop
            toggle_play_stop(mw)
        elif key == "save-all":
            mgr = getattr(mw, '_scene_tab_manager', None)
            if mgr is not None:
                mgr.save_all_dirty_tabs()
        elif key == "new-scene":
            from editor.main_window.handlers import new_scene
            new_scene(mw)
        elif key == "open-scene":
            from editor.main_window.handlers import open_scene
            open_scene(mw)
        elif key == "new-entity":
            from core.foundation.commands import CreateEntityCommand, get_history
            eng = getattr(mw, '_engine', None)
            scene = getattr(eng, 'scene', None)
            if scene is not None:
                get_history().execute(CreateEntityCommand(scene, "Entity"))
        elif key == "frame":
            vp = _viewport_of(mw)
            if vp is not None and getattr(vp, '_selected_entities', None):
                sel = vp._selected_entities
                if sel:
                    from editor.entity_frame import compute_entity_frame
                    ent = sel[0]
                    try:
                        center, radius = compute_entity_frame(ent, getattr(vp, '_renderer', None))
                        vp._cam.frame_bounds(center, radius)
                    except Exception:
                        pass
        elif key == "duplicate":
            vp = _viewport_of(mw)
            if vp is not None and getattr(vp, '_selected_entities', None):
                try:
                    vp._copy_selected_entities()
                    vp._paste_entities()
                except Exception:
                    pass
        elif key == "delete":
            vp = _viewport_of(mw)
            if vp is not None:
                try:
                    vp._delete_selected()
                except Exception:
                    pass
        elif key == "select-all":
            from editor.main_window.handlers import on_entities_selected
            eng = getattr(mw, '_engine', None)
            scene = getattr(eng, 'scene', None)
            if scene is not None:
                on_entities_selected(mw, scene.get_all_entities())
        elif key == "undo":
            from editor.main_window.handlers import undo
            undo(mw)
        elif key == "redo":
            from editor.main_window.handlers import redo
            redo(mw)
        elif key in ("gizmo-t", "gizmo-r", "gizmo-s"):
            vp = _viewport_of(mw)
            if vp is not None and getattr(vp, '_gizmo', None) is not None:
                from core.gizmo.gizmo import GizmoMode
                vp._gizmo.mode = {"gizmo-t": GizmoMode.TRANSLATE, "gizmo-r": GizmoMode.ROTATE, "gizmo-s": GizmoMode.SCALE}[key]
        elif key == "copy-stats":
            from PyQt6.QtWidgets import QApplication
            from core.renderer.render_stats import stats_text
            text = stats_text()
            if text:
                try:
                    QApplication.clipboard().setText(text)
                except Exception:
                    pass
                Logger.info("Performance stats copied to clipboard.")
            else:
                Logger.info("No performance stats available yet.")
    except Exception as e:
        Logger.error(f"Palette builtin '{key}' failed: {e}")


def _open_asset(mw, path: str) -> None:
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".zpes":
            from editor.main_window.handlers import open_scene_in_tab
            open_scene_in_tab(mw, path)
            return
        if ext in (".py", ".pyx", ".txt", ".md", ".json", ".glsl", ".shader"):
            try:
                mw._script_editor._script_widget.open_script(path)
                return
            except Exception:
                pass
        try:
            from core.foundation.plugin_manager import open_file_with_plugin
            if open_file_with_plugin(getattr(mw, '_engine', None), path):
                return
        except Exception:
            pass
        Logger.info(f"Asset: {path}")
    except Exception as e:
        Logger.error(f"Palette asset open failed: {e}")


def show_command_palette(mw) -> None:
    try:
        from PyQt6.QtWidgets import QApplication
        menu_rows = _collect_menu_commands(mw)
        tab_rows = _collect_tab_rows(mw)
        entity_rows = _collect_entity_rows(mw)
        asset_rows = _collect_asset_rows(mw)
        dlg = QDialog(mw)
        dlg.setWindowTitle("Search Everywhere")
        dlg.resize(620, 460)
        lay = QVBoxLayout(dlg)
        edit = QLineEdit(dlg)
        edit.setPlaceholderText("Commands, tabs, entities, assets...  (try  2+2*3)")
        edit.setClearButtonEnabled(True)
        lay.addWidget(edit)
        lst = QListWidget(dlg)
        lst.setIconSize(QSize(18, 18))
        lay.addWidget(lst)
        state = {"menu": menu_rows, "tabs": tab_rows, "entities": entity_rows, "assets": asset_rows}

        def add_row(title: str, detail: str, payload: object, icon: object) -> None:
            item = QListWidgetItem(title + (f"   [{detail}]" if detail else ""))
            try:
                if isinstance(icon, QIcon) and not icon.isNull():
                    item.setIcon(icon)
            except Exception:
                pass
            item.setData(Qt.ItemDataRole.UserRole, payload)
            lst.addItem(item)

        def refilter(text: str):
            lst.clear()
            q = (text or "").strip()
            if not q:
                for title, key, _d, icon in _BUILTINS:
                    add_row(title, _d, ("builtin", key), _qta(icon))
                for title, detail, payload, icon in state["tabs"]:
                    add_row(title, detail, payload, icon)
                if lst.count() > 0:
                    lst.setCurrentRow(0)
                return
            calc = _try_calculate(q)
            if calc is not None:
                expr, value = calc
                add_row(f"= {value}", "Calculator, Enter logs to console", ("calc", expr, str(value)), _qta("fa5s.calculator"))
            for title, key, _d, icon in _BUILTINS:
                if _matches(title, key, q):
                    add_row(title, _d, ("builtin", key), _qta(icon))
            shown = lst.count()
            for title, detail, payload, icon in state["tabs"] + state["menu"]:
                if _matches(title, detail, q):
                    add_row(title, detail, payload, icon)
                    shown += 1
                    if shown >= 100:
                        break
            if shown < 100:
                for title, detail, payload, icon in state["entities"] + state["assets"]:
                    if _matches(title, detail, q):
                        add_row(title, detail, payload, icon)
                        shown += 1
                        if shown >= 100:
                            break
            if lst.count() > 0:
                lst.setCurrentRow(0)

        def run_current():
            item = lst.currentItem()
            if item is None:
                return
            payload = item.data(Qt.ItemDataRole.UserRole)
            dlg.accept()
            try:
                if isinstance(payload, tuple):
                    kind = payload[0]
                    if kind == "scene":
                        mgr = getattr(mw, '_scene_tab_manager', None)
                        if mgr is not None:
                            mgr.switch_to_tab(payload[1])
                    elif kind == "script":
                        mw._script_editor._script_widget.open_script(payload[1])
                    elif kind == "entity":
                        from editor.main_window.handlers import on_entity_selected
                        eng = getattr(mw, '_engine', None)
                        scene = getattr(eng, 'scene', None)
                        ent = scene.get_entity(payload[1]) if scene is not None else None
                        if ent is not None:
                            on_entity_selected(mw, ent)
                    elif kind == "asset":
                        _open_asset(mw, payload[1])
                    elif kind == "builtin":
                        _run_builtin(mw, payload[1])
                    elif kind == "calc":
                        _expr, value = payload[1], payload[2]
                        Logger.info(f"calc: {_expr} = {value}")
                        try:
                            QApplication.clipboard().setText(value)
                        except Exception:
                            pass
                else:
                    payload.trigger()
            except Exception:
                pass

        edit.textChanged.connect(refilter)
        edit.returnPressed.connect(run_current)
        lst.itemDoubleClicked.connect(lambda _i: run_current())
        refilter("")
        edit.setFocus()
        dlg.exec()
    except Exception as e:
        Logger.error(f"Search palette failed: {e}")
