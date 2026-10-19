# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem

from core.foundation.logger import Logger

from .sources import _BUILTINS
from .sources import _collect_asset_rows
from .sources import _collect_entity_rows
from .sources import _collect_menu_commands
from .sources import _collect_tab_rows
from .sources import _matches
from .sources import _qta
from .sources import _try_calculate


def _viewport_of(mw):
    try:
        eng = getattr(mw, "_engine", None)
        return getattr(eng, "viewport", None)
    except Exception:
        return None


def _run_builtin(mw, key: str) -> None:
    try:
        if key == "play":
            from editor.main_window.handlersp import toggle_play_stop
            toggle_play_stop(mw)
        elif key == "save-all":
            mgr = getattr(mw, "_scene_tab_manager", None)
            if mgr is not None:
                mgr.save_all_dirty_tabs()
        elif key == "new-scene":
            from editor.main_window.handlersp import new_scene
            new_scene(mw)
        elif key == "open-scene":
            from editor.main_window.handlersp import open_scene
            open_scene(mw)
        elif key == "new-entity":
            from core.foundation.cmd import CreateEntityCommand, get_history
            eng = getattr(mw, "_engine", None)
            scene = getattr(eng, "scene", None)
            if scene is not None:
                get_history().execute(CreateEntityCommand(scene, "Entity"))
        elif key == "frame":
            vp = _viewport_of(mw)
            if vp is not None and getattr(vp, "_selected_entities", None):
                sel = vp._selected_entities
                if sel:
                    from editor.entframe import compute_entity_frame
                    ent = sel[0]
                    try:
                        center, radius = compute_entity_frame(ent, getattr(vp, "_renderer", None))
                        vp._cam.frame_bounds(center, radius)
                    except Exception:
                        pass
        elif key == "duplicate":
            vp = _viewport_of(mw)
            if vp is not None and getattr(vp, "_selected_entities", None):
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
            from editor.main_window.handlersp import on_entities_selected
            eng = getattr(mw, "_engine", None)
            scene = getattr(eng, "scene", None)
            if scene is not None:
                on_entities_selected(mw, scene.get_all_entities())
        elif key == "undo":
            from editor.main_window.handlersp import undo
            undo(mw)
        elif key == "redo":
            from editor.main_window.handlersp import redo
            redo(mw)
        elif key in ("gizmo-t", "gizmo-r", "gizmo-s"):
            vp = _viewport_of(mw)
            if vp is not None and getattr(vp, "_gizmo", None) is not None:
                from core.gizmo.core import GizmoMode
                vp._gizmo.mode = {"gizmo-t": GizmoMode.TRANSLATE, "gizmo-r": GizmoMode.ROTATE, "gizmo-s": GizmoMode.SCALE}[key]
        elif key == "copy-stats":
            from PySide6.QtWidgets import QApplication
            from core.renderer.stats import stats_text
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
            from editor.main_window.handlersp import open_scene_in_tab
            open_scene_in_tab(mw, path)
            return
        try:
            from core.assets.modelp import is_model_file
            if is_model_file(path):
                from editor.main_window.handlersp import on_open_model_as_scene
                on_open_model_as_scene(mw, path)
                return
        except Exception:
            pass
        if ext in (".py", ".pyx", ".txt", ".md", ".json", ".glsl", ".shader"):
            try:
                mw._script_editor._script_widget.open_script(path)
                return
            except Exception:
                pass
        try:
            from core.foundation.plugins import open_file_with_plugin
            if open_file_with_plugin(getattr(mw, "_engine", None), path):
                return
        except Exception:
            pass
        Logger.info(f"Asset: {path}")
    except Exception as e:
        Logger.error(f"Palette asset open failed: {e}")


def show_command_palette(mw) -> None:
    try:
        from PySide6.QtWidgets import QApplication
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
                        mgr = getattr(mw, "_scene_tab_manager", None)
                        if mgr is not None:
                            mgr.switch_to_tab(payload[1])
                    elif kind == "script":
                        mw._script_editor._script_widget.open_script(payload[1])
                    elif kind == "entity":
                        from editor.main_window.handlersp import on_entity_selected
                        eng = getattr(mw, "_engine", None)
                        scene = getattr(eng, "scene", None)
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
