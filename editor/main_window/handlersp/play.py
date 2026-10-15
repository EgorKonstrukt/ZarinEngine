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
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen

from .selection import on_entity_selected

_PENDING_SNAPSHOTS: dict = {}


def _wait_pending_snapshot(info, timeout: float = 0.5) -> None:
    try:
        rec = _PENDING_SNAPSHOTS.get(id(info))
    except Exception:
        return
    if rec is None:
        return
    try:
        thr = rec[1]
        if thr is None:
            return
    except Exception:
        return
    try:
        thr.join(timeout=max(0.0, float(timeout)))
    except Exception:
        pass


def on_play_start(mw, _):
    from editor.main_window.toolbar import _set_play_btn_style
    _set_play_btn_style(mw._play_btn, "Stop")
    mw._pause_btn.setEnabled(True)
    mw._status_mode_lbl.setText("Play Mode")
    if hasattr(mw, '_gui_editor_widget') and mw._gui_editor_widget.canvas:
        canvas = mw._gui_editor_widget.canvas
        mw._viewport._overlay_canvas = canvas
        if hasattr(mw, '_play_dock') and hasattr(mw._play_dock, '_viewport'):
            mw._play_dock._viewport.show_overlay(canvas)
            if mw._viewport.renderer and mw._play_dock._viewport._renderer:
                mw._play_dock._viewport._renderer.skybox_enabled = mw._viewport.renderer.skybox_enabled
                mw._play_dock._viewport._renderer.set_effects_enabled(mw._viewport.renderer.effects_enabled)
        canvas.edit_mode = False


def on_play_stop(mw, _):
    from editor.main_window.toolbar import _set_play_btn_style
    _set_play_btn_style(mw._play_btn, "Play")
    mw._pause_btn.setEnabled(False)
    mw._status_mode_lbl.setText("Edit Mode")
    if hasattr(mw, '_viewport'):
        mw._viewport._overlay_canvas = None
    if hasattr(mw, '_play_dock') and hasattr(mw._play_dock, '_viewport'):
        mw._play_dock._viewport.hide_overlay()
    if hasattr(mw, '_gui_editor_widget'):
        mw._gui_editor_widget.canvas.edit_mode = True


def _tab_info(mw):
    if hasattr(mw, '_scene_tab_manager') and mw._scene_tab_manager:
        return mw._scene_tab_manager.get_tab_info(mw._scene_tab_manager.active_tab) if mw._scene_tab_manager.active_tab else None
    return None


def toggle_play_stop(mw):
    if mw._engine.play_mode:
        mw._engine.stop_play()
        mw._viewport_dock.raise_()
        info = _tab_info(mw)
        try:
            _wait_pending_snapshot(info)
        except Exception:
            pass
        if info and info.scene_snapshot and mw._engine.scene:
            from core.components.rendering.postfx.graphics_effect import GraphicsEffect
            GraphicsEffect.cleanup_registry()
            from core.ecs import Scene as S
            from core.engine.eng import Engine as Eng
            restored = S.deserialize(info.scene_snapshot, Eng.instance()._component_registry)
            restored.path = mw._engine.scene.path
            try:
                if getattr(mw, '_pre_play_dirty', False):
                    restored.mark_dirty()
            except Exception:
                pass
            mw._engine._scene = restored
            mw._engine._plugin_manager.notify_scene_loaded(restored)
            mw._engine._emit_event("scene_loaded", restored)
            info.scene = restored
            info.scene_snapshot = None
            info.play_mode = False
        if hasattr(mw, "_pre_play_selected_id") and mw._pre_play_selected_id:
            e = mw._engine.scene.get_entity(mw._pre_play_selected_id)
            if e:
                on_entity_selected(mw, e)
    else:
        sel = getattr(mw._hierarchy, "_selected_entity", None)
        mw._pre_play_selected_id = sel.id if sel else None
        try:
            mw._pre_play_dirty = bool(mw._engine.scene and mw._engine.scene.dirty)
        except Exception:
            mw._pre_play_dirty = False
        if mw._engine.scene:
            info = _tab_info(mw)
            if info:
                try:
                    info.scene_snapshot = None
                    info.play_mode = True
                    _tok = object()
                    _PENDING_SNAPSHOTS[id(info)] = [_tok, None]
                    _scene_ref = mw._engine.scene

                    def _snap_worker():
                        try:
                            _data = _scene_ref.serialize()
                        except Exception:
                            return
                        try:
                            _rec = _PENDING_SNAPSHOTS.get(id(info))
                            if _rec is None or _rec[0] is not _tok:
                                return
                            try:
                                _playing = bool(mw._engine.play_mode)
                            except Exception:
                                _playing = False
                            if not _playing:
                                return
                            try:
                                if not getattr(info, "play_mode", False):
                                    return
                            except Exception:
                                return
                            info.scene_snapshot = _data
                        except Exception:
                            pass
                        finally:
                            try:
                                _rec = _PENDING_SNAPSHOTS.get(id(info))
                                if _rec is not None and _rec[0] is _tok:
                                    _PENDING_SNAPSHOTS.pop(id(info), None)
                            except Exception:
                                pass

                    _thr = threading.Thread(target=_snap_worker, daemon=True)
                    _PENDING_SNAPSHOTS[id(info)][1] = _thr
                    _thr.start()
                except Exception:
                    try:
                        info.scene_snapshot = mw._engine.scene.serialize()
                    except Exception:
                        info.scene_snapshot = None
        mw._engine.start_play()
        mw._play_dock.raise_()


def toggle_pause(mw):
    if mw._play_dock:
        mw._play_dock._toggle_pause()
    info = _tab_info(mw)
    try:
        _wait_pending_snapshot(info)
    except Exception:
        pass
    if info and info.scene_snapshot and mw._engine.scene:
        from core.components.rendering.postfx.graphics_effect import GraphicsEffect
        GraphicsEffect.cleanup_registry()
        from core.ecs import Scene as S
        from core.engine.eng import Engine as Eng
        restored = S.deserialize(info.scene_snapshot, Eng.instance()._component_registry)
        restored.path = mw._engine.scene.path
        try:
            if getattr(mw, '_pre_play_dirty', False):
                restored.mark_dirty()
        except Exception:
            pass
        mw._engine._scene = restored
        mw._engine._plugin_manager.notify_scene_loaded(restored)
        mw._engine._emit_event("scene_loaded", restored)
        info.scene = restored
        info.scene_snapshot = None
        info.play_mode = False
    if hasattr(mw, "_pre_play_selected_id") and mw._pre_play_selected_id:
        e = mw._engine.scene.get_entity(mw._pre_play_selected_id)
        if e:
            on_entity_selected(mw, e)


def _find_engine_root():
    base = ""
    try:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if os.path.isfile(os.path.join(base, "player.py")):
            return base
    except Exception:
        pass
    try:
        cwd = os.getcwd()
        if os.path.isfile(os.path.join(cwd, "player.py")):
            return os.path.abspath(cwd)
    except Exception:
        pass
    try:
        for p in list(sys.path):
            try:
                if not p:
                    continue
                cand_root = os.path.abspath(p)
                if os.path.isfile(os.path.join(cand_root, "player.py")):
                    return cand_root
            except Exception:
                continue
    except Exception:
        pass
    return base


def _resolve_player_command(scene_path: str):
    try:
        frozen = bool(getattr(sys, "frozen", False))
    except Exception:
        frozen = False
    if frozen:
        try:
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            for name in ("ZarinPlayer.exe", "ZarinPlayer", "player.exe", "player"):
                cand = os.path.join(exe_dir, name)
                if os.path.isfile(cand):
                    return [cand, scene_path]
            exe_base = os.path.splitext(os.path.basename(sys.executable))[0].lower()
            if "player" in exe_base:
                return [sys.executable, scene_path]
        except Exception:
            pass
    root = _find_engine_root()
    player_py = os.path.join(root, "player.py") if root else ""
    if player_py and os.path.isfile(player_py):
        return [sys.executable, player_py, scene_path]
    return []


def _write_player_preview(mw, project_root: str):
    scene = mw._engine.scene
    snapshot = scene.serialize()
    try:
        embedded = getattr(scene, "embedded_resources", None)
        if embedded:
            snapshot["embedded_resources"] = dict(embedded)
    except Exception:
        pass
    try:
        mw._engine.relativize_scene_paths(snapshot)
    except Exception:
        pass
    preview_dir = os.path.join(project_root, "cache")
    try:
        os.makedirs(preview_dir, exist_ok=True)
    except Exception:
        pass
    preview_path = os.path.join(preview_dir, "player_preview.zpes")
    tmp_path = preview_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f)
    os.replace(tmp_path, preview_path)
    return os.path.abspath(preview_path)


def launch_external_player(mw):
    try:
        playing = bool(mw._engine.play_mode)
    except Exception:
        playing = False
    if playing:
        QMessageBox.information(mw, "Player", "Stop Play Mode before launching Player.")
        return
    scene = getattr(mw._engine, "scene", None)
    if scene is None:
        QMessageBox.warning(mw, "Player", "No scene to play.")
        return
    try:
        project_root = getattr(mw._engine, "_project_path", "") or ""
    except Exception:
        project_root = ""
    if not project_root or not os.path.isdir(project_root):
        try:
            project_root = str(mw._engine.project_root)
        except Exception:
            project_root = ""
    if not project_root or not os.path.isdir(project_root):
        project_root = os.getcwd()
    project_root = os.path.abspath(project_root)
    scene_path = ""
    try:
        current_path = getattr(scene, "path", "") or ""
        is_dirty = bool(getattr(scene, "dirty", False))
        if current_path and os.path.isfile(current_path) and not is_dirty:
            scene_path = os.path.abspath(current_path)
        else:
            scene_path = _write_player_preview(mw, project_root)
    except Exception as e:
        Logger.error(f"Failed to prepare preview scene for Player: {e}", e)
        QMessageBox.warning(mw, "Player", f"Failed to prepare scene: {e}")
        return
    cmd = _resolve_player_command(scene_path)
    if not cmd:
        QMessageBox.warning(mw, "Player", "Player entry not found.")
        return
    try:
        old = getattr(mw, "_external_player_proc", None)
        if old is not None:
            try:
                if old.poll() is None:
                    try:
                        old.terminate()
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass
    try:
        root = _find_engine_root()
        cwd = root if root and os.path.isdir(root) else project_root
        proc = subprocess.Popen(cmd, cwd=cwd)
        mw._external_player_proc = proc
        Logger.info(f"Player launched: {scene_path}")
    except Exception as e:
        Logger.error(f"Failed to launch Player: {e}", e)
        QMessageBox.warning(mw, "Player", f"Failed to launch Player: {e}")


