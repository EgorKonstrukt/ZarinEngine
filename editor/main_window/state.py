# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import gc
import json
import os
import base64
import pickle
import shutil

from PyQt6.QtCore import QByteArray, QRect, QSettings
from PyQt6.QtGui import QGuiApplication

from core.foundation.logger import Logger


def save_state(mw, include_tabs=True):
    path = _window_state_path()
    previous: dict = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
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
            "geometry": [fg.x(), fg.y(), fg.width(), fg.height()],
            "windowState": base64.b64encode(bytes(mw.saveState())).decode("ascii"),
            "scriptPaths": script_paths,
        }
        if include_tabs:
            entries, active = _collect_tab_entries(mw)
            data["tabs"] = entries
            data["active"] = active
            _prune_session_dir(entries)
        else:
            for key in ("tabs", "active", "scriptPaths"):
                if key in previous:
                    data[key] = previous[key]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        Logger.error(f"Failed to save window state: {e}")
    if mw._viewport.camera:
        cam_data = json.dumps(mw._viewport.camera.serialize())
        mw._settings.setValue("sceneCamera", cam_data)


def _session_dir():
    return os.path.join(str(os.path.expanduser("~")), ".zarin", "session")


def _debug_path():
    return os.path.join(str(os.path.expanduser("~")), ".zarin", "tab_session_debug.log")


def _debug_log(line: str):
    try:
        with open(_debug_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _live_entity_count(scene) -> int:
    try:
        return len(scene.get_all_entities())
    except Exception:
        return -1


def _clear_session_dir():
    session_dir = _session_dir()
    if os.path.isdir(session_dir):
        try:
            shutil.rmtree(session_dir)
        except Exception as e:
            Logger.error(f"Failed to clear session dir: {e}")


def _prune_session_dir(entries: list):
    try:
        keep = set()
        for entry in entries:
            if isinstance(entry, dict):
                snap = entry.get("snapshot", "") or ""
                if snap:
                    keep.add(os.path.basename(snap))
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


def _read_snapshot_file(path: str):
    try:
        if path.endswith(".pkl"):
            with open(path, "rb") as f:
                data = pickle.load(f)
            return data if isinstance(data, dict) else None
    except Exception:
        pass
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    try:
        alt = os.path.splitext(path)[0] + (".json" if path.endswith(".pkl") else ".pkl")
        if os.path.isfile(alt):
            return _read_snapshot_file(alt)
    except Exception:
        pass
    return None


def _file_entity_count(path: str) -> int:
    try:
        data = _read_snapshot_file(path)
        if not isinstance(data, dict):
            return -1
        entities = data.get("entities", {})
        return len(entities) if isinstance(entities, dict) else -1
    except Exception:
        return -1


def _snapshotted_version(scene):
    try:
        return getattr(scene, "_snapshot_rev", None)
    except Exception:
        return None


def _mark_snapshotted(scene, filename: str):
    try:
        scene._snapshot_rev = scene._render_version
        scene._snapshot_file = os.path.basename(filename)
    except Exception:
        pass


def _reusable_snapshot(scene) -> str:
    try:
        sf = getattr(scene, "_snapshot_file", "") or ""
        rev = getattr(scene, "_snapshot_rev", None)
        if not sf or rev is None:
            return ""
        if rev != scene._render_version:
            return ""
        cand = os.path.join(_session_dir(), os.path.basename(sf))
        if os.path.isfile(cand):
            return os.path.basename(sf)
    except Exception:
        pass
    return ""


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
                    scene = info.scene
                    if scene is not None and ((not info.path) or not os.path.isfile(info.path or "") or scene.dirty):
                        hit = _reusable_snapshot(scene)
                        if hit:
                            entry["snapshot"] = hit
                            entry["dirty"] = True
                            used_names.add(hit)
                        else:
                            while True:
                                cand = f"scene_{snapshot_index}.pkl"
                                snapshot_index += 1
                                if cand not in used_names:
                                    break
                            filename = _write_scene_snapshot(scene, cand, info.path or "")
                            if filename:
                                entry["snapshot"] = filename
                                entry["dirty"] = True
                                used_names.add(filename)
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


def _read_state_data():
    path = _window_state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        Logger.error(f"Failed to read window state: {e}")
        return {}


def _load_scene_file(eng, path: str):
    from core.ecs.ecs import Scene, ComponentRegistry
    from core.ecs.embedded_resources import extract_embedded_resources
    was_enabled = gc.isenabled()
    if was_enabled:
        gc.disable()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["_source"] = path
        embedded = extract_embedded_resources(data, eng.project_root, eng._embedded_cache_mode())
        eng.resolve_scene_paths(data)
        scene = Scene.deserialize(data, ComponentRegistry)
        scene.embedded_resources = embedded
        scene.path = path
        scene.name = os.path.splitext(os.path.basename(path))[0]
        scene.mark_clean()
        return scene
    finally:
        if was_enabled:
            gc.enable()
        try:
            gc.freeze()
        except Exception:
            pass


def _migrate_snapshot_to_pkl(snapshot_path: str, data: dict) -> str:
    try:
        if not snapshot_path.endswith(".json") or not os.path.isfile(snapshot_path):
            return ""
        pkl_path = os.path.splitext(snapshot_path)[0] + ".pkl"
        if os.path.isfile(pkl_path):
            return os.path.basename(pkl_path)
        with open(pkl_path, "wb") as f:
            pickle.dump(data, f, protocol=5)
        return os.path.basename(pkl_path)
    except Exception:
        return ""


def _load_scene_snapshot(eng, snapshot_path: str, scene_path: str, entry_name: str):
    from core.ecs.ecs import Scene, ComponentRegistry
    from core.ecs.embedded_resources import extract_embedded_resources
    data = _read_snapshot_file(snapshot_path)
    if data is None:
        raise ValueError(f"Unreadable snapshot: {snapshot_path}")
    migrated = _migrate_snapshot_to_pkl(snapshot_path, data)
    entities = data.get("entities", {})
    if isinstance(entities, dict) and len(entities) == 0:
        if scene_path and os.path.isfile(scene_path) and _file_entity_count(scene_path) > 0:
            Logger.warning(f"Ignoring empty snapshot, loading file instead: {scene_path}")
            return None
    data["_source"] = scene_path or snapshot_path
    embedded = extract_embedded_resources(data, eng.project_root, eng._embedded_cache_mode())
    eng.resolve_scene_paths(data)
    scene = Scene.deserialize(data, ComponentRegistry)
    scene.embedded_resources = embedded
    if scene_path:
        scene.path = scene_path
        scene.name = os.path.splitext(os.path.basename(scene_path))[0]
    elif entry_name:
        scene.name = entry_name
    scene.mark_dirty()
    if migrated:
        _mark_snapshotted(scene, os.path.splitext(snapshot_path)[0] + ".pkl")
    else:
        _mark_snapshotted(scene, snapshot_path)
    return scene


def _bar_index_of(mgr, bar, kind: str, key: str) -> int:
    for i in range(bar.count()):
        if kind == "scene":
            if mgr.tab_name_at(i) == key:
                return i
        elif mgr.is_script_tab(i) and mgr.script_path_at(i) == key:
            return i
    return -1


def _activate_bar_index(mgr, bar, idx: int):
    if idx < 0 or idx >= bar.count():
        return
    if bar.currentIndex() == idx:
        mgr._on_tab_changed(idx)
    else:
        bar.setCurrentIndex(idx)


def restore_tabs(mw) -> bool:
    data = _read_state_data()
    entries = data.get("tabs") or []
    if not entries:
        legacy = data.get("scriptPaths") or []
        entries = [{"type": "script", "path": p} for p in legacy if p]
    if not entries:
        return False
    _debug_log(f"restore start entries={len(entries)} active={data.get('active', -1)}")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "scene":
            scene_path = entry.get("path", "") or ""
            snapshot = entry.get("snapshot", "") or ""
            snapshot_path = os.path.join(_session_dir(), os.path.basename(snapshot)) if snapshot else ""
            try:
                fsize = os.path.getsize(scene_path) if scene_path and os.path.isfile(scene_path) else -1
            except Exception:
                fsize = -1
            try:
                ssize = os.path.getsize(snapshot_path) if snapshot_path and os.path.isfile(snapshot_path) else -1
            except Exception:
                ssize = -1
            _debug_log(
                f"restore entry scene name={entry.get('name')} path={scene_path} "
                f"file_bytes={fsize} "
                f"snapshot_bytes={ssize}"
            )
        else:
            _debug_log(f"restore entry script path={entry.get('path')}")
    mgr = getattr(mw, '_scene_tab_manager', None)
    bar = getattr(mw, '_scene_tab_bar', None)
    script_editor = getattr(mw, '_script_editor', None)
    sw = getattr(script_editor, '_script_widget', None)
    if mgr is None or bar is None or sw is None:
        return False
    eng = mw._engine
    mgr.begin_restore()
    try:
        placeholder = None
        for i in range(sw._tabs.count()):
            tab = sw._tabs.widget(i)
            if tab is not None and not tab._file_path:
                placeholder = tab
                break
        placeholder_used = False
        restored: list = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            kind = entry.get("type", "")
            if kind == "script":
                script_path = entry.get("path", "") or ""
                if script_path:
                    if ("script", script_path) in restored:
                        continue
                    if os.path.isfile(script_path):
                        try:
                            sw.open_script(script_path)
                        except Exception as e:
                            Logger.error(f"Failed to restore script tab: {e}")
                            continue
                        restored.append(("script", script_path))
                elif placeholder is not None and not placeholder_used:
                    placeholder_used = True
                    restored.append(("script", ""))
            elif kind == "scene":
                name = entry.get("name", "") or "Scene"
                scene_path = entry.get("path", "") or ""
                snapshot = entry.get("snapshot", "") or ""
                scene = None
                if snapshot:
                    snapshot_path = os.path.join(_session_dir(), os.path.basename(snapshot))
                    if os.path.isfile(snapshot_path):
                        try:
                            scene = _load_scene_snapshot(eng, snapshot_path, scene_path, name)
                        except Exception as e:
                            Logger.error(f"Failed to restore scene snapshot: {e}")
                            scene = None
                if scene is None and scene_path:
                    if eng.scene is not None and getattr(eng.scene, 'path', None) == scene_path:
                        scene = eng.scene
                    elif os.path.isfile(scene_path):
                        try:
                            scene = _load_scene_file(eng, scene_path)
                        except Exception as e:
                            Logger.error(f"Failed to restore scene tab: {e}")
                            scene = None
                if scene is None:
                    _debug_log(f"restore skip scene name={name} path={scene_path}")
                    continue
                try:
                    tab_name = mgr.add_tab(name, path=scene_path or None, scene=scene)
                except Exception as e:
                    Logger.error(f"Failed to restore scene tab: {e}")
                    continue
                _debug_log(
                    f"restore added scene tab={tab_name} source_entities={_live_entity_count(scene)}"
                )
                restored.append(("scene", tab_name))
        placeholder_kept = False
        for i in range(sw._tabs.count() - 1, -1, -1):
            tab = sw._tabs.widget(i)
            if tab is None or tab._file_path or tab._dirty:
                continue
            if ("script", "") in restored and not placeholder_kept:
                placeholder_kept = True
                continue
            if sw._tabs.count() > 1:
                try:
                    tab._close_self()
                except Exception as e:
                    Logger.error(f"Failed to close placeholder tab: {e}")
        if not any(kind == "scene" for kind, _ in restored) and eng.scene is not None:
            scene_path = getattr(eng.scene, 'path', None) or ""
            if scene_path:
                scene_name = os.path.splitext(os.path.basename(scene_path))[0]
            else:
                scene_name = eng.scene.name or "Scene"
            try:
                tab_name = mgr.add_tab(scene_name, path=scene_path or None, scene=eng.scene)
                restored.append(("scene", tab_name))
            except Exception as e:
                Logger.error(f"Failed to register current scene tab: {e}")
        for order, (kind, key) in enumerate(restored):
            idx = _bar_index_of(mgr, bar, kind, key)
            if idx >= 0 and idx != order:
                bar.moveTab(idx, order)
    finally:
        mgr.end_restore()
    if not restored:
        return False
    first_scene = None
    for kind, key in restored:
        if kind == "scene":
            first_scene = key
            break
    saved_active = data.get("active", -1)
    if isinstance(saved_active, int) and 0 <= saved_active < len(restored):
        kind, key = restored[saved_active]
    elif first_scene is not None:
        kind, key = "scene", first_scene
    else:
        return True
    if kind == "scene":
        _activate_bar_index(mgr, bar, _bar_index_of(mgr, bar, "scene", key))
    else:
        if first_scene is not None:
            _activate_bar_index(mgr, bar, _bar_index_of(mgr, bar, "scene", first_scene))
        _activate_bar_index(mgr, bar, _bar_index_of(mgr, bar, "script", key))
    engine_scene = getattr(mw._engine, 'scene', None)
    _debug_log(
        f"restore done active_tab={mgr.active_tab} bar_current={bar.currentIndex()} "
        f"engine_scene={getattr(engine_scene, 'name', None)} "
        f"engine_entities={_live_entity_count(engine_scene) if engine_scene is not None else -1}"
    )
    return True


def restore_camera(mw):
    path = _window_state_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            g = data.get("geometry")
            if g and len(g) == 4:
                mw.setGeometry(QRect(*g))
                rect = mw.geometry()
                for screen in QGuiApplication.screens():
                    if screen.availableGeometry().intersects(rect):
                        mw._restored_geometry_once = True
                        break
            ws = data.get("windowState")
            if ws:
                raw = base64.b64decode(ws)
                if mw.restoreState(QByteArray(raw)):
                    mw._layout_restored = True
        except Exception as e:
            Logger.error(f"Failed to restore window state: {e}")
    cam_data = mw._settings.value("sceneCamera")
    if cam_data:
        try:
            mw._viewport.camera.deserialize(json.loads(cam_data))
        except Exception:
            pass


def _window_state_path():
    return os.path.join(str(os.path.expanduser("~")), ".zarin", "window_state.json")


def reset_layout(mw):
    for dock in mw._docks:
        dock.setVisible(True)
