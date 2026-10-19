# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import editor.icons as qta
from PySide6.QtWidgets import QMessageBox, QFileDialog
from PySide6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen

from .selection import on_entity_selected

def on_project_file_double_clicked(mw, path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".zpep":
        instantiate_prefab(mw, path)
        return
    try:
        from core.assets.modelp import is_model_file
        if is_model_file(path):
            try:
                from editor.main_window.handlersp.model_scene import on_open_model_as_scene
                on_open_model_as_scene(mw, path)
            except Exception:
                pass
            return
    except Exception:
        pass
    if ext == ".zterr":
        if hasattr(mw, '_terrain_editor') and mw._terrain_editor is not None:
            mw._terrain_editor.load_graph(path)
            mw._terrain_editor.show()
            mw._terrain_editor.raise_()
    elif ext in (".py", ".pyx"):
        se = getattr(mw, "_script_editor", None)
        opened = False
        if se is not None:
            widget = getattr(se, "_script_widget", se)
            opener = getattr(widget, "open_script", None)
            if callable(opener):
                try:
                    opener(path)
                    opened = True
                except Exception:
                    opened = False
            if opened:
                try:
                    se.show()
                    se.raise_()
                except Exception:
                    pass


def on_open_prefab_editor(mw, path: str):
    from core.ecs.prefabp import Prefab
    from core.ecs import Scene
    pref = Prefab.load(path)
    if not pref:
        Logger.warning(f"Cannot load prefab: {path}")
        return
    tab_name = f"Prefab: {pref.name}"
    edit_scene = Scene(tab_name)
    pref.instantiate(edit_scene, mw._engine._component_registry)
    edit_scene.mark_clean()
    origin = mw._scene_tab_manager.active_tab
    mw._scene_tab_manager.add_tab(tab_name, scene=edit_scene)
    info = mw._scene_tab_manager.get_tab_info(tab_name)
    if info:
        info.prefab_path = path
        info.origin_tab = origin
    mw._prefab_mode = True
    mw._prefab_path = path
    mw._viewport._prefab_btns.show()
    from core.config.editor_scale import scale
    mw._viewport._toolbar.setFixedHeight(scale(56))
    _start_prefab_autosave(mw, tab_name)


def _start_prefab_autosave(mw, prefab_tab_name: str = ""):
    from PySide6.QtCore import QTimer
    mw._prefab_autosave_tab = prefab_tab_name
    if hasattr(mw, '_prefab_save_timer') and mw._prefab_save_timer:
        mw._prefab_save_timer.stop()
    mw._prefab_save_timer = QTimer()
    mw._prefab_save_timer.setSingleShot(True)
    mw._prefab_save_timer.timeout.connect(lambda: _do_auto_save(mw))
    if hasattr(mw, '_prefab_modified_slot'):
        try:
            mw._viewport.scene_modified.disconnect(mw._prefab_modified_slot)
        except TypeError:
            pass
    mw._prefab_modified_slot = lambda: _on_prefab_modified(mw)
    mw._viewport.scene_modified.connect(mw._prefab_modified_slot)


def _on_prefab_modified(mw):
    if not mw._prefab_mode:
        return
    if hasattr(mw, '_prefab_save_timer') and mw._prefab_save_timer:
        mw._prefab_save_timer.start(2000)


def _do_auto_save(mw):
    if not mw._prefab_mode:
        return
    tab_name = getattr(mw, '_prefab_autosave_tab', '')
    mgr = getattr(mw, '_scene_tab_manager', None)
    if tab_name and mgr:
        info = mgr.get_tab_info(tab_name)
        if info and info.scene:
            _save_prefab_direct(mw._prefab_path, info.scene)
            return
    on_save_prefab(mw)


def on_return_to_scene(mw):
    if hasattr(mw, '_prefab_modified_slot'):
        try:
            mw._viewport.scene_modified.disconnect(mw._prefab_modified_slot)
        except TypeError:
            pass
        mw._prefab_modified_slot = None
    if hasattr(mw, '_prefab_save_timer') and mw._prefab_save_timer:
        mw._prefab_save_timer.stop()
        mw._prefab_save_timer = None
    mgr = mw._scene_tab_manager
    prefab_tab = mgr.find_prefab_tab() if mgr else None
    if not prefab_tab:
        mw._prefab_mode = False
        mw._prefab_path = None
        mw._viewport._prefab_btns.hide()
        from core.config.editor_scale import scale
        mw._viewport._toolbar.setFixedHeight(scale(30))
        return
    info = mgr.get_tab_info(prefab_tab)
    origin = info.origin_tab if info else None
    prefab_path = info.prefab_path if info else None
    if prefab_path:
        from core.ecs.prefabp import Prefab, PrefabLibrary
        pref = PrefabLibrary.load(prefab_path)
        prefab_guid = pref.guid if pref else None
        if info and info.scene:
            _save_prefab_direct(prefab_path, info.scene)
        if origin and origin in mgr._tabs:
            origin_info = mgr.get_tab_info(origin)
            if origin_info and origin_info.scene and prefab_guid:
                _refresh_prefab_instances(origin_info.scene, prefab_guid, mw._engine._component_registry)
    mgr.remove_tab(prefab_tab)
    mw._prefab_mode = False
    mw._prefab_path = None
    mw._prefab_autosave_tab = ""
    mw._viewport._prefab_btns.hide()
    from core.config.editor_scale import scale
    mw._viewport._toolbar.setFixedHeight(scale(30))


def _refresh_prefab_instances(scene, prefab_guid, registry):
    from core.ecs.prefabp import Prefab, PrefabLibrary
    prefab_path = PrefabLibrary.path_for_guid(prefab_guid)
    if not prefab_path:
        return
    prefab = PrefabLibrary.load(prefab_path)
    if not prefab:
        return
    all_entities = scene.get_all_entities()
    instances = [e for e in all_entities if getattr(e, '_prefab_guid', None) == prefab_guid]
    if not instances:
        return
    roots = Prefab.get_prefab_roots(instances)
    saved = []
    for root in roots:
        t = root.transform
        saved.append({
            "parent_id": root._parent.id if root._parent else None,
            "position": list(t.local_position) if t else None,
            "rotation": list(t.local_euler_angles) if t else None,
            "scale": list(t.local_scale) if t else None,
        })
        scene.remove_entity(root.id)
    for data in saved:
        spawned = prefab.instantiate(scene, registry)
        for new_root in spawned:
            if data["parent_id"]:
                parent_ent = scene.get_entity(data["parent_id"])
                if parent_ent:
                    new_root.set_parent(parent_ent)
            t = new_root.transform
            if t and data["position"]:
                from core.maths.math3d import Vec3
                t.local_position = Vec3(*data["position"])
            if t and data["rotation"]:
                from core.maths.math3d import Vec3
                t.local_euler_angles = Vec3(*data["rotation"])
            if t and data["scale"]:
                from core.maths.math3d import Vec3
                t.local_scale = Vec3(*data["scale"])


def _save_prefab_direct(path: str, scene):
    from core.ecs.prefabp import Prefab, PrefabLibrary
    pref = Prefab.load(path)
    if not pref:
        return
    roots = scene.get_root_entities()
    prefab_roots = [e for e in roots if getattr(e, '_prefab_guid', None) == pref.guid]
    if not prefab_roots:
        return
    pref.capture(prefab_roots)
    pref.save(path)
    PrefabLibrary._prefabs[path] = pref
    PrefabLibrary._guids[pref.guid] = path


def on_save_prefab(mw):
    if not mw._prefab_path or not mw._engine.scene:
        return
    _save_prefab_direct(mw._prefab_path, mw._engine.scene)
    pref.capture(prefab_roots)
    pref.save(mw._prefab_path)
    PrefabLibrary._prefabs[mw._prefab_path] = pref
    PrefabLibrary._guids[pref.guid] = mw._prefab_path


def instantiate_prefab(mw, path: str, world_pos=None):
    if not mw._engine.scene:
        return
    from core.ecs.prefabp import PrefabLibrary
    from core.foundation.cmd import InstantiatePrefabCommand, get_history
    pref = PrefabLibrary.load(path)
    if not pref:
        return
    cmd = InstantiatePrefabCommand(mw._engine.scene, pref, mw._engine._component_registry)
    get_history().execute(cmd)
    spawned = [mw._engine.scene.get_entity(eid) for eid in cmd._spawned_ids]
    spawned = [e for e in spawned if e]
    if spawned and world_pos is not None:
        t = spawned[0].transform
        if t:
            t.local_position = world_pos
    if spawned:
        on_entity_selected(mw, spawned[0])
    mw._hierarchy.refresh()


