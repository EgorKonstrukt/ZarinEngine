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

import qtawesome as qta
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen


def on_scene_loaded(mw, scene):
    tab_name = (mw._scene_tab_manager.active_tab
                if hasattr(mw, '_scene_tab_manager') and mw._scene_tab_manager and mw._scene_tab_manager.active_tab
                else (scene.name if scene else "None"))
    mw._status_scene_lbl.setText(f"Scene: {tab_name}")
    mw.setWindowTitle(f"Zarin Engine Editor - {tab_name}")
    if hasattr(mw, '_viewport') and mw._viewport and hasattr(mw._viewport, 'renderer') and mw._viewport.renderer:
        mw._viewport.renderer.clear_scene_caches()
    try:
        scene_path = getattr(scene, "path", "") or ""
        eng = getattr(mw, "_engine", None)
        project_path = getattr(eng, "_project_path", "") or ""
        if scene_path and project_path:
            from editor.project_manager import _set_last_scene
            _set_last_scene(project_path, scene_path)
    except Exception:
        pass


def new_scene(mw):
    mw._scene_tab_manager.add_tab("NewScene")


def open_scene(mw):
    path, _ = QFileDialog.getOpenFileName(mw, "Open Scene", "scenes/", "Scenes (*.zpes)")
    if path:
        _do_open_scene(mw, path)


def open_scene_in_tab(mw, path: str):
    mgr = getattr(mw, '_scene_tab_manager', None)
    if mgr is not None and path:
        want = os.path.normcase(os.path.normpath(path))
        for name in mgr.tab_names:
            info = mgr.get_tab_info(name)
            if info and info.path and os.path.normcase(os.path.normpath(info.path)) == want:
                mgr.switch_to_tab(name)
                return
    _do_open_scene(mw, path)


def load_scene_in_tab(mw, path: str):
    mgr = getattr(mw, '_scene_tab_manager', None)
    if mgr is not None and path:
        want = os.path.normcase(os.path.normpath(path))
        for name in mgr.tab_names:
            info = mgr.get_tab_info(name)
            if info and info.path and os.path.normcase(os.path.normpath(info.path)) == want:
                mgr.switch_to_tab(name)
                return mw._engine.scene
    scene = mw._engine.load_scene(path)
    if scene is None or mgr is None:
        return scene
    tab_name = os.path.splitext(os.path.basename(path))[0]
    mgr.add_tab(tab_name, path=path, scene=scene)
    return scene


def _confirm_discard_dirty(mw) -> bool:
    if mw._engine.scene and mw._engine.scene.dirty:
        reply = QMessageBox.question(mw, "Unsaved Changes", "Save current scene?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Yes:
            mw._engine.save_scene()
    return True


def _do_open_scene(mw, path):
    eng = mw._engine
    from core.foundation.progress import task_start, task_update, task_complete
    from core.ecs.embed import extract_embedded_resources as _extract
    task_id = "scene:open"
    task_start(task_id, f"Opening {os.path.basename(path)}...", fraction=0.0, total=1.0)
    def _report():
        import time as _t
        state = [0.0, -1.0]
        def _cb(done: int, total_: int, name: str):
            if total_ <= 0:
                return
            frac = done / max(1, total_)
            now = _t.monotonic()
            if done >= total_ or (frac - state[1]) >= 0.02 or (now - state[0]) >= 0.08:
                state[0] = now
                state[1] = frac
                task_update(task_id, fraction=frac, detail=name)
        return _cb
    def _worker():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _extract(data, eng.project_root, eng._embedded_cache_mode(), progress_cb=_report())
            eng.resolve_scene_paths(data)
        except Exception as ex:
            msg = str(ex)
            Logger.error(f"Error opening scene: {ex}", ex)
            def _err():
                task_complete(task_id)
                from core.foundation import progress
                progress.notify_error(f"Failed to open scene: {msg}")
            from editor.scene_async import call_on_main
            call_on_main(_err)
            return
        try:
            from core.ecs import Scene, ComponentRegistry
            scene = Scene.deserialize(data, ComponentRegistry)
            scene.embedded_resources = data.get("embedded_resources", {})
            scene.path = path
            tab_name = os.path.splitext(os.path.basename(path))[0]
            scene.name = tab_name
            try:
                eng._ensure_shadow_system(scene)
            except Exception:
                pass
            scene.mark_clean()
        except Exception as ex:
            msg = str(ex)
            Logger.error(f"Error opening scene: {ex}", ex)
            def _err():
                task_complete(task_id)
                from core.foundation import progress
                progress.notify_error(f"Failed to open scene: {msg}")
            from editor.scene_async import call_on_main
            call_on_main(_err)
            return
        def _apply():
            try:
                mw._scene_tab_manager.add_tab(tab_name, path=path, scene=scene)
            except Exception as e:
                Logger.error(f"Error opening scene: {e}", e)
            finally:
                task_complete(task_id)
        from editor.scene_async import call_on_main
        call_on_main(_apply)
    import threading
    threading.Thread(target=_worker, name="scene-open-worker", daemon=True).start()


def _sync_tab_after_save(mw):
    if hasattr(mw, '_scene_tab_manager') and mw._scene_tab_manager:
        active = mw._scene_tab_manager.active_tab
        if active:
            info = mw._scene_tab_manager.get_tab_info(active)
            if info:
                info.path = mw._engine.scene.path if mw._engine.scene else info.path
    try:
        eng = getattr(mw, "_engine", None)
        scene = getattr(eng, "scene", None)
        scene_path = getattr(scene, "path", "") or ""
        project_path = getattr(eng, "_project_path", "") or ""
        if scene_path and project_path:
            from editor.project_manager import _set_last_scene
            _set_last_scene(project_path, scene_path)
    except Exception:
        pass


def save_scene(mw):
    if not mw._engine.scene:
        return
    if not mw._engine.scene.path:
        save_scene_as(mw)
    else:
        mw._engine.save_scene_async(on_done=lambda _ok: _sync_tab_after_save(mw))


def save_scene_as(mw):
    if not mw._engine.scene:
        return
    path, _ = QFileDialog.getSaveFileName(mw, "Save Scene", "scenes/", "Scenes (*.zpes)")
    if path:
        if not path.endswith(".zpes"):
            path += ".zpes"
        mw._engine.save_scene_async(path, on_done=lambda _ok: _sync_tab_after_save(mw))
        if hasattr(mw, '_scene_tab_manager') and mw._scene_tab_manager:
            active = mw._scene_tab_manager.active_tab
            if active:
                info = mw._scene_tab_manager.get_tab_info(active)
                if info:
                    info.path = path


def open_scene_by_path(mw, path: str):
    if not os.path.exists(path):
        return
    _do_open_scene(mw, path)


