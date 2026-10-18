# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import base64
import json
import os
import pickle
import tempfile

from core.foundation.logger import Logger

from .state import SESSION_FORMAT_VERSION, _debug_log, _file_entity_count, _live_entity_count, _mark_snapshotted, _reusable_snapshot, _session_dir, _window_state_path


def save_state(mw, include_tabs=True):
    path = _window_state_path()
    previous: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                previous = stored
        except Exception:
            previous = {}
    try:
        fg = mw.geometry()
        sw = getattr(mw, '_script_editor', None)
        script_paths = []
        if sw:
            sw = sw._script_widget
            for i in range(sw._tabs.count()):
                tab = sw._tabs.widget(i)
                if tab._file_path:
                    script_paths.append(tab._file_path)
        data = {
            "v": SESSION_FORMAT_VERSION,
            "geometry": [fg.x(), fg.y(), fg.width(), fg.height()],
            "windowState": base64.b64encode(bytes(mw.saveState())).decode("ascii"),
            "scriptPaths": script_paths,
        }
        if include_tabs:
            entries, active = _collect_tab_entries(mw)
            data["tabs"] = entries
            data["active"] = active
            try:
                mgr = getattr(mw, '_scene_tab_manager', None)
                extra = mgr.closed_snapshot_files() if mgr is not None else set()
            except Exception:
                extra = set()
            _prune_session_dir(entries, extra)
        else:
            for key in ("tabs", "active", "scriptPaths"):
                if key in previous:
                    data[key] = previous[key]
            if "v" not in data and "v" in previous:
                data["v"] = previous["v"]
        parent = os.path.dirname(path) or "."
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".session_", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(tmp, path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        Logger.error(f"Failed to save window state: {e}")
    try:
        from editor.main_window.toolbar import save_main_toolbar_state
        save_main_toolbar_state(mw)
    except Exception:
        pass
    if mw._viewport.camera:
        cam_data = json.dumps(mw._viewport.camera.serialize())
        mw._settings.setValue("sceneCamera", cam_data)


def _prune_session_dir(entries: list, extra_keep=None):
    try:
        keep = set()
        for entry in entries:
            if isinstance(entry, dict):
                snap = entry.get("snapshot", "") or ""
                if snap:
                    keep.add(os.path.basename(snap))
        if extra_keep:
            for fn in extra_keep:
                if fn:
                    keep.add(os.path.basename(fn))
        session_dir = _session_dir()
        if not os.path.isdir(session_dir):
            return
        for fn in os.listdir(session_dir):
            if (fn.startswith("scene_") and (fn.endswith(".json") or fn.endswith(".pkl"))) and fn not in keep:
                try:
                    os.remove(os.path.join(session_dir, fn))
                except Exception:
                    pass
    except Exception:
        pass


def _write_scene_snapshot(scene, filename: str, scene_path: str) -> str:
    try:
        session_dir = _session_dir()
        os.makedirs(session_dir, exist_ok=True)
        full_path = os.path.join(session_dir, os.path.basename(filename))
        data = scene.serialize()
        entities = data.get("entities", {})
        count = len(entities) if isinstance(entities, dict) else -1
        if count == 0:
            if scene_path and os.path.isfile(scene_path) and _file_entity_count(scene_path) > 0:
                Logger.warning(f"Skipping empty snapshot, keeping file version: {scene_path}")
                return ""
        with open(full_path, "wb") as f:
            pickle.dump(data, f, protocol=5)
        _mark_snapshotted(scene, filename)
        return os.path.basename(filename)
    except Exception as e:
        Logger.error(f"Failed to write scene snapshot: {e}")
        return ""


def _collect_tab_entries(mw):
    mgr = getattr(mw, '_scene_tab_manager', None)
    bar = getattr(mw, '_scene_tab_bar', None)
    entries: list = []
    active = -1
    if mgr is None or bar is None:
        return entries, active
    current = bar.currentIndex()
    snapshot_index = 0
    used_names: set[str] = set()
    for i in range(bar.count()):
        entry = None
        if mgr.is_script_tab(i):
            entry = {"type": "script", "path": mgr.script_path_at(i)}
        else:
            name = mgr.tab_name_at(i)
            if name is not None:
                info = mgr.get_tab_info(name)
                if info is not None and not info.prefab_path:
                    entry = {"type": "scene", "name": info.name, "path": info.path or ""}
                    if getattr(info, "pinned", False):
                        entry["pinned"] = True
                    scene = info.scene
                    pending = getattr(info, "pending_snapshot", "") or ""
                    carried = getattr(info, "restored_snapshot", "") or ""
                    if scene is None:
                        if pending:
                            entry["snapshot"] = os.path.basename(pending)
                            used_names.add(os.path.basename(pending))
                    elif ((not info.path) or not os.path.isfile(info.path or "") or scene.dirty):
                        hit = _reusable_snapshot(scene)
                        if hit:
                            entry["snapshot"] = hit
                            if scene.dirty:
                                entry["dirty"] = True
                            used_names.add(hit)
                            try:
                                info.restored_snapshot = os.path.basename(hit)
                            except Exception:
                                pass
                        else:
                            while True:
                                cand = f"scene_{snapshot_index}.pkl"
                                snapshot_index += 1
                                if cand not in used_names:
                                    break
                            filename = _write_scene_snapshot(scene, cand, info.path or "")
                            if filename:
                                entry["snapshot"] = filename
                                if scene.dirty:
                                    entry["dirty"] = True
                                used_names.add(filename)
                                try:
                                    info.restored_snapshot = os.path.basename(filename)
                                except Exception:
                                    pass
                    elif carried:
                        carried_path = os.path.join(_session_dir(), os.path.basename(carried))
                        if os.path.isfile(carried_path):
                            entry["snapshot"] = os.path.basename(carried)
                            used_names.add(os.path.basename(carried))
        if entry is not None:
            entries.append(entry)
            if i == current:
                active = len(entries) - 1
    for entry in entries:
        if entry.get("type") == "scene":
            info = mgr.get_tab_info(entry["name"]) if mgr else None
            scene = info.scene if info else None
            _debug_log(
                f"save entry scene name={entry.get('name')} path={entry.get('path')} "
                f"dirty={bool(info and (info.dirty or (scene and scene.dirty)))} "
                f"live_entities={_live_entity_count(scene) if scene is not None else -1} "
                f"snapshot={entry.get('snapshot', '')}"
            )
        else:
            _debug_log(f"save entry script path={entry.get('path')}")
    _debug_log(f"save done tabs={len(entries)} active={active}")
    return entries, active
