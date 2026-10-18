# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import base64
import json
import os

from PySide6.QtCore import QByteArray, QRect
from PySide6.QtGui import QGuiApplication

from core.foundation.logger import Logger

from .state import SESSION_FORMAT_VERSION, _debug_log, _live_entity_count, _load_scene_file, _load_scene_snapshot, _read_state_data, _session_dir, _window_state_path


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


def _apply_restored_flags(mgr, tab_name: str, entry: dict):
    try:
        info = mgr.get_tab_info(tab_name)
        if info is None:
            return
        if entry.get("pinned"):
            info.pinned = True
    except Exception:
        pass


def _move_pinned_front(mgr, bar):
    try:
        pinned: list[str] = []
        for i in range(bar.count()):
            try:
                if mgr.is_script_tab(i):
                    continue
                nm = mgr.tab_name_at(i)
                if nm is None:
                    continue
                info = mgr.get_tab_info(nm)
                if info is not None and getattr(info, "pinned", False):
                    pinned.append(nm)
            except Exception:
                continue
        slot = 0
        for nm in pinned:
            try:
                idx = -1
                for i in range(bar.count()):
                    if not mgr.is_script_tab(i) and mgr.tab_name_at(i) == nm:
                        idx = i
                        break
                if idx >= 0 and idx != slot:
                    bar.moveTab(idx, slot)
                slot += 1
            except Exception:
                continue
    except Exception:
        pass


def restore_tabs(mw) -> bool:
    data = _read_state_data()
    try:
        if int(data.get("v", 1)) > SESSION_FORMAT_VERSION:
            Logger.warning("Ignoring session state from a newer format version.")
            return False
    except Exception:
        pass
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
    valid = [e for e in entries if isinstance(e, dict) and e.get("type") in ("script", "scene")]
    first_scene_pos = -1
    for pos, e in enumerate(valid):
        if e.get("type") == "scene":
            first_scene_pos = pos
            break
    saved_active = data.get("active", -1)
    target_pos = -1
    if isinstance(saved_active, int) and 0 <= saved_active < len(entries):
        cand = entries[saved_active]
        if isinstance(cand, dict) and cand.get("type") in ("script", "scene"):
            try:
                target_pos = valid.index(cand)
            except ValueError:
                target_pos = -1
    eager_positions: set[int] = set()
    if target_pos >= 0 and valid[target_pos].get("type") == "scene":
        eager_positions.add(target_pos)
    elif first_scene_pos >= 0:
        eager_positions.add(first_scene_pos)
    mgr.begin_restore()
    bar.blockSignals(True)
    try:
        placeholder = None
        for i in range(sw._tabs.count()):
            tab = sw._tabs.widget(i)
            if tab is not None and not tab._file_path:
                placeholder = tab
                break
        placeholder_used = False
        restored: list = []
        valid_to_restored: dict[int, int] = {}
        for pos, entry in enumerate(valid):
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
                        valid_to_restored[pos] = len(restored)
                        restored.append(("script", script_path))
                elif placeholder is not None and not placeholder_used:
                    placeholder_used = True
                    valid_to_restored[pos] = len(restored)
                    restored.append(("script", ""))
            elif kind == "scene":
                name = entry.get("name", "") or "Scene"
                scene_path = entry.get("path", "") or ""
                snapshot = entry.get("snapshot", "") or ""
                if pos in eager_positions:
                    scene = None
                    from_snapshot = False
                    if snapshot:
                        snapshot_path = os.path.join(_session_dir(), os.path.basename(snapshot))
                        if os.path.isfile(snapshot_path):
                            try:
                                scene = _load_scene_snapshot(eng, snapshot_path, scene_path, name)
                                if scene is not None:
                                    from_snapshot = True
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
                        if snapshot:
                            snapshot_path = os.path.join(_session_dir(), os.path.basename(snapshot))
                            if os.path.isfile(snapshot_path):
                                try:
                                    tab_name = mgr.add_lazy_tab(name, path=scene_path or None, snapshot=snapshot)
                                except Exception as e:
                                    Logger.error(f"Failed to restore scene tab: {e}")
                                    continue
                                _apply_restored_flags(mgr, tab_name, entry)
                                valid_to_restored[pos] = len(restored)
                                restored.append(("scene", tab_name))
                                continue
                        if scene_path and os.path.isfile(scene_path):
                            try:
                                tab_name = mgr.add_lazy_tab(name, path=scene_path or None, snapshot="")
                            except Exception as e:
                                Logger.error(f"Failed to restore scene tab: {e}")
                                continue
                            _apply_restored_flags(mgr, tab_name, entry)
                            valid_to_restored[pos] = len(restored)
                            restored.append(("scene", tab_name))
                            continue
                        _debug_log(f"restore skip scene name={name} path={scene_path}")
                        continue
                    try:
                        tab_name = mgr.add_tab(name, path=scene_path or None, scene=scene)
                    except Exception as e:
                        Logger.error(f"Failed to restore scene tab: {e}")
                        continue
                    if snapshot and from_snapshot:
                        try:
                            info = mgr.get_tab_info(tab_name)
                            if info is not None:
                                info.restored_snapshot = os.path.basename(snapshot)
                        except Exception:
                            pass
                    _apply_restored_flags(mgr, tab_name, entry)
                    _debug_log(
                        f"restore added scene tab={tab_name} source_entities={_live_entity_count(scene)}"
                    )
                    valid_to_restored[pos] = len(restored)
                    restored.append(("scene", tab_name))
                else:
                    snapshot_ok = False
                    if snapshot:
                        snapshot_path = os.path.join(_session_dir(), os.path.basename(snapshot))
                        try:
                            snapshot_ok = os.path.isfile(snapshot_path)
                        except Exception:
                            snapshot_ok = False
                    file_ok = False
                    if scene_path:
                        if eng.scene is not None and getattr(eng.scene, 'path', None) == scene_path:
                            file_ok = True
                        else:
                            try:
                                file_ok = os.path.isfile(scene_path)
                            except Exception:
                                file_ok = False
                    if not snapshot_ok and not file_ok:
                        _debug_log(f"restore skip scene name={name} path={scene_path}")
                        continue
                    try:
                        tab_name = mgr.add_lazy_tab(
                            name,
                            path=scene_path or None,
                            snapshot=snapshot if snapshot_ok else "",
                        )
                    except Exception as e:
                        Logger.error(f"Failed to restore scene tab: {e}")
                        continue
                    _apply_restored_flags(mgr, tab_name, entry)
                    valid_to_restored[pos] = len(restored)
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
        _move_pinned_front(mgr, bar)
    finally:
        try:
            bar.blockSignals(False)
        except Exception:
            pass
        mgr.end_restore()
    if not restored:
        return False
    first_scene = None
    for kind, key in restored:
        if kind == "scene":
            first_scene = key
            break
    kind = ""
    key = ""
    if target_pos >= 0 and target_pos in valid_to_restored:
        kind, key = restored[valid_to_restored[target_pos]]
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
    try:
        from editor.main_window.toolbar import load_main_toolbar_state, apply_toolbar_runtime_state
        load_main_toolbar_state(mw)
        apply_toolbar_runtime_state(mw)
    except Exception:
        pass
    cam_data = mw._settings.value("sceneCamera")
    if cam_data:
        try:
            mw._viewport.camera.deserialize(json.loads(cam_data))
        except Exception:
            pass
        try:
            sync_fn = getattr(mw, "_sync_nav_mode_ui", None)
            if callable(sync_fn):
                sync_fn(mw._viewport.camera.nav_mode)
        except Exception:
            pass
        try:
            from editor.main_window.toolbar import apply_toolbar_runtime_state as _apply2
            _apply2(mw)
        except Exception:
            pass


def reset_layout(mw):
    for dock in mw._docks:
        dock.setVisible(True)
