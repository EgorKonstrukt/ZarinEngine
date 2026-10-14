# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import gc
import json
import os
import pickle
import shutil

from core.foundation.logger import Logger


SESSION_FORMAT_VERSION = 2


def _session_dir():
    return os.path.join(str(os.path.expanduser("~")), ".zarin", "session")


def _window_state_path():
    return os.path.join(str(os.path.expanduser("~")), ".zarin", "window_state.json")


def _debug_path():
    return os.path.join(str(os.path.expanduser("~")), ".zarin", "tab_session_debug.log")


_debug_rotated = False


def _debug_log(line: str):
    global _debug_rotated
    try:
        if not _debug_rotated:
            _debug_rotated = True
            try:
                if os.path.isfile(_debug_path()) and os.path.getsize(_debug_path()) > 1048576:
                    bak = _debug_path() + ".bak"
                    try:
                        if os.path.isfile(bak):
                            os.remove(bak)
                    except Exception:
                        pass
                    try:
                        os.replace(_debug_path(), bak)
                    except Exception:
                        pass
            except Exception:
                pass
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
    from core.ecs import Scene, ComponentRegistry
    from core.ecs.embed import extract_embedded_resources
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
    from core.ecs import Scene, ComponentRegistry
    from core.ecs.embed import extract_embedded_resources
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
    scene.mark_clean()
    if migrated:
        _mark_snapshotted(scene, os.path.splitext(snapshot_path)[0] + ".pkl")
    else:
        _mark_snapshotted(scene, snapshot_path)
    return scene
