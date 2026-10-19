# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os


def is_model_tab_info(info) -> bool:
    try:
        return bool(getattr(info, "model_path", "") or "")
    except Exception:
        return False


def is_model_tab(mw, tab_name: str = "") -> bool:
    try:
        mgr = getattr(mw, "_scene_tab_manager", None)
        if mgr is None:
            return False
        name = tab_name or getattr(mgr, "active_tab", "")
        if not name:
            return False
        return is_model_tab_info(mgr.get_tab_info(name))
    except Exception:
        return False


def find_model_tab(mw, model_path: str) -> str:
    try:
        mgr = getattr(mw, "_scene_tab_manager", None)
        if mgr is None or not model_path:
            return ""
        want = os.path.normcase(os.path.normpath(os.path.abspath(model_path)))
        for name in list(getattr(mw._scene_tab_manager, "tab_names", []) or []):
            try:
                info = mgr.get_tab_info(name)
                cand = getattr(info, "model_path", "") or ""
                if cand and os.path.normcase(os.path.normpath(os.path.abspath(cand))) == want:
                    return name
            except Exception:
                continue
        return ""
    except Exception:
        return ""


def active_model_path(mw) -> str:
    try:
        mgr = getattr(mw, "_scene_tab_manager", None)
        if mgr is None:
            return ""
        info = mgr.get_tab_info(getattr(mgr, "active_tab", "") or "")
        return getattr(info, "model_path", "") or ""
    except Exception:
        return ""


def on_open_model_as_scene(mw, path: str):
    try:
        from core.assets.modelp import is_model_file
        from core.assets.modelp import model_tab_title
        from core.foundation.logger import Logger
    except Exception:
        return ""
    try:
        if not path or not os.path.isfile(path):
            return ""
        if not is_model_file(path):
            try:
                Logger.warning("Not a 3D model: " + str(path))
            except Exception:
                pass
            return ""
        abs_path = os.path.abspath(path)
        existing = find_model_tab(mw, abs_path)
        if existing:
            try:
                mw._scene_tab_manager.switch_to_tab(existing)
            except Exception:
                pass
            return existing
        from core.ecs import Scene
        title = model_tab_title(abs_path)
        scene = Scene(title)
        try:
            mw._engine._ensure_shadow_system(scene)
        except Exception:
            pass
        try:
            scene.mark_clean()
        except Exception:
            pass
        try:
            tab_name = mw._scene_tab_manager.add_tab(title, path=None, scene=scene)
        except Exception:
            return ""
        try:
            info = mw._scene_tab_manager.get_tab_info(tab_name)
            if info is not None:
                info.model_path = abs_path
            mw._scene_tab_manager.refresh_tab_title(tab_name)
        except Exception:
            pass
        _fill_model_tab_async(mw, tab_name, abs_path)
        return tab_name
    except Exception:
        return ""


def _rel_or_abs(mw, path: str) -> str:
    try:
        root = getattr(mw._engine, "project_root", "") or os.getcwd()
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return os.path.abspath(path)
    except Exception:
        return path


def _fill_model_tab_async(mw, tab_name: str, abs_path: str):
    try:
        from PySide6.QtCore import QTimer
        from core.assets.importer import load_mesh_future
        fut = load_mesh_future(abs_path)
    except Exception:
        return
    def _poll():
        try:
            mgr = getattr(mw, "_scene_tab_manager", None)
            info = mgr.get_tab_info(tab_name) if mgr is not None else None
            if info is None:
                return
            if not fut.done():
                QTimer.singleShot(50, _poll)
                return
            try:
                import_data = fut.result()
            except Exception:
                import_data = None
            _build_model_entities(mw, tab_name, abs_path, import_data)
        except Exception:
            pass
    try:
        QTimer.singleShot(0, _poll)
    except Exception:
        pass


def _build_model_entities(mw, tab_name: str, abs_path: str, import_data) -> str:
    try:
        from core.foundation.logger import Logger
    except Exception:
        Logger = None
    try:
        mgr = getattr(mw, "_scene_tab_manager", None)
        if mgr is None:
            return ""
        info = mgr.get_tab_info(tab_name)
        if info is None or getattr(info, "scene", None) is None:
            return ""
        scene = info.scene
        name = os.path.splitext(os.path.basename(abs_path))[0] or "Model"
        mesh_path = _rel_or_abs(mw, abs_path)
        if import_data is None:
            if Logger is not None:
                try:
                    Logger.warning("Cannot load model: " + abs_path)
                except Exception:
                    pass
            try:
                from core.foundation import progress
                progress.notify_error("Failed to load model: " + os.path.basename(abs_path))
            except Exception:
                pass
            return ""
        ent = None
        try:
            is_skinned = bool(getattr(import_data, "has_skeleton", False))
        except Exception:
            is_skinned = False
        if is_skinned:
            try:
                from core.components.rendering.skeleton.skinned_factory import _build_skinned_entity
                ent = _build_skinned_entity(scene, abs_path, name, mesh_path, None, import_data)
            except Exception:
                ent = None
            if ent is not None:
                try:
                    _apply_import_materials(ent, abs_path)
                except Exception:
                    pass
                try:
                    _attach_blendshapes(mw, scene, ent, import_data)
                except Exception:
                    pass
        if ent is None and not is_skinned:
            try:
                from core.components import Transform, MeshFilter, MeshRenderer
                ent = scene.create_entity(name)
                ent.add_component(Transform())
                mf = MeshFilter()
                mf.mesh_name = name
                mf.mesh_path = mesh_path
                ent.add_component(mf)
                ent.add_component(MeshRenderer())
            except Exception:
                ent = None
            if ent is not None:
                try:
                    _apply_import_materials(ent, abs_path)
                except Exception:
                    pass
                try:
                    _attach_blendshapes(mw, scene, ent, import_data)
                except Exception:
                    pass
        if ent is None:
            return ""
        try:
            scene.mark_dirty()
        except Exception:
            pass
        try:
            mgr.refresh_tab_title(tab_name)
        except Exception:
            pass
        if getattr(mgr, "active_tab", "") == tab_name:
            try:
                mw._hierarchy.refresh()
            except Exception:
                pass
            try:
                from editor.main_window.handlersp.selection import on_entity_selected
                on_entity_selected(mw, ent)
            except Exception:
                pass
        else:
            try:
                ent_id = getattr(ent, "id", "")
                if ent_id:
                    cur = list(getattr(info, "selected_entity_ids", []) or [])
                    if ent_id not in cur:
                        cur.append(ent_id)
                        info.selected_entity_ids = cur
            except Exception:
                pass
        if Logger is not None:
            try:
                Logger.info("Opened model as scene: " + name)
            except Exception:
                pass
        return getattr(ent, "id", "") or ""
    except Exception:
        return ""


def _apply_import_materials(ent, asset_path: str):
    try:
        from core.assets.importer import _read_mesh_import
        mats = [p for p in _read_mesh_import(asset_path).get("materials", []) if p]
        if not mats:
            return
        comp = None
        for candidate in list(ent._components.values()):
            if type(candidate).__name__ in ("MeshRenderer", "SkinnedMeshRenderer"):
                comp = candidate
                break
        if comp is not None:
            comp.materials = [{"path": p} for p in mats]
    except Exception:
        pass


def _attach_blendshapes(mw, scene, ent, import_data):
    try:
        if not list(getattr(import_data, "blendshape_names", []) or []):
            return
        from core.components.rendering.deform.blendshapes import BlendShapes
        if ent.get_component(BlendShapes) is not None:
            return
        bs = BlendShapes()
        bs.sync_with_mesh(import_data)
        ent.add_component(bs)
    except Exception:
        pass


def open_model_via_dialog(mw) -> str:
    try:
        from PySide6.QtWidgets import QFileDialog
        from core.assets.modelp import MODEL_FILE_FILTER
        start = ""
        try:
            start = getattr(mw._engine, "project_root", "") or ""
        except Exception:
            start = ""
        filt = "Scenes (*.zpes);;" + MODEL_FILE_FILTER + ";;All Files (*)"
        path, _ = QFileDialog.getOpenFileName(mw, "Open Model As Scene", start, filt)
        if not path:
            return ""
        from core.assets.modelp import is_model_file
        if is_model_file(path):
            return on_open_model_as_scene(mw, path) or ""
        try:
            from editor.main_window.handlersp.scene_ops import open_scene_in_tab
            open_scene_in_tab(mw, path)
            return path
        except Exception:
            return ""
    except Exception:
        return ""
