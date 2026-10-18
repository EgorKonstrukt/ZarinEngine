# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os

from PySide6.QtCore import Qt

from core.foundation.logger import Logger
from core.maths.math3d import Vec3
from editor.main_window.tabs.info import SceneTabInfo


class SceneTabSyncMixin:
    def _resolve_active_history(self):
        try:
            if self._active_tab and self._active_tab in self._tabs:
                return self._tabs[self._active_tab].history
        except Exception:
            pass
        return self._fallback_history

    def _on_engine_scene_saved(self, scene):
        try:
            if scene is None:
                return
            for tab_name, info in list(self._tabs.items()):
                if info.scene is not scene:
                    continue
                info.restored_snapshot = ""
                info.pending_snapshot = ""
                try:
                    info.dirty = bool(scene.dirty)
                except Exception:
                    info.dirty = False
                try:
                    sp = getattr(scene, "path", None)
                    if sp:
                        info.path = sp
                except Exception:
                    pass
                self.refresh_tab_title(tab_name)
        except Exception:
            pass

    def _is_tab_dirty(self, info: SceneTabInfo) -> bool:
        try:
            if info.scene is not None:
                return bool(info.scene.dirty)
            return bool(info.pending_snapshot) and not info.path
        except Exception:
            return False

    def _tab_title(self, info: SceneTabInfo) -> str:
        try:
            title = info.name
            if self._is_tab_dirty(info):
                title = "\u25cf " + title
            dup_index, dup_total = self._dup_position(info.name)
            if dup_total > 1:
                title = f"{title} ({dup_index})"
            return title
        except Exception:
            pass
        return info.name

    def _dup_key(self, info: SceneTabInfo):
        try:
            if info.path:
                return ("scene-file", self._norm_path(info.path))
            import re
            base = re.sub(r"\s+\d+$", "", info.name or "")
            return ("scene-unsaved", base.lower())
        except Exception:
            return ("scene-name", info.name)

    def _dup_position(self, tab_name: str) -> tuple[int, int]:
        try:
            info = self._tabs.get(tab_name)
            if info is None:
                return 1, 1
            key = self._dup_key(info)
            order: list[str] = []
            for i in range(self._tab_bar.count()):
                nm = self.tab_name_at(i)
                if nm is None:
                    continue
                other = self._tabs.get(nm)
                if other is None:
                    continue
                if self._dup_key(other) == key:
                    order.append(nm)
            if len(order) <= 1:
                return 1, 1
            return order.index(tab_name) + 1, len(order)
        except Exception:
            return 1, 1

    def _tab_tooltip(self, info: SceneTabInfo) -> str:
        try:
            base = info.path if info.path else "Unsaved scene (no file yet)"
            parts = [base]
            if info.pinned:
                parts.append("Pinned")
            idx, total = self._dup_position(info.name)
            if total > 1:
                parts.append(f"Duplicate {idx} of {total}")
            if self._is_tab_dirty(info):
                parts.append("\u25cf Unsaved changes")
            return "\n".join(parts)
        except Exception:
            return info.name

    def refresh_tab_title(self, tab_name: str):
        try:
            info = self._tabs.get(tab_name)
            if info is None:
                return
            idx = self._scene_tab_idx(tab_name)
            if idx < 0:
                return
            title = self._tab_title(info)
            if self._tab_bar.tabText(idx) != title:
                self._tab_bar.setTabText(idx, title)
            tip = self._tab_tooltip(info)
            if self._tab_bar.tabToolTip(idx) != tip:
                self._tab_bar.setTabToolTip(idx, tip)
        except Exception:
            pass

    def refresh_all_tab_titles(self):
        try:
            for tab_name in list(self._tab_names):
                self.refresh_tab_title(tab_name)
        except Exception:
            pass

    def is_tab_loaded(self, tab_name: str) -> bool:
        info = self._tabs.get(tab_name)
        if info is None:
            return False
        return info.scene is not None

    def ensure_tab_loaded(self, tab_name: str) -> bool:
        info = self._tabs.get(tab_name)
        if info is None:
            return False
        if info.scene is not None:
            return True
        if info.prefab_path:
            return False
        from editor.main_window.statep import _session_dir, _load_scene_snapshot, _load_scene_file
        scene = None
        snap = info.pending_snapshot or ""
        if snap:
            snap_path = os.path.join(_session_dir(), os.path.basename(snap))
            if os.path.isfile(snap_path):
                try:
                    scene = _load_scene_snapshot(self._engine, snap_path, info.path or "", info.name)
                except Exception as e:
                    Logger.error(f"Failed to lazy-load scene snapshot '{tab_name}': {e}")
                    scene = None
        if scene is None and info.path and os.path.isfile(info.path):
            try:
                if self._engine.scene is not None and getattr(self._engine.scene, "path", None) == info.path:
                    scene = self._engine.scene
                else:
                    scene = _load_scene_file(self._engine, info.path)
            except Exception as e:
                Logger.error(f"Failed to lazy-load scene file '{tab_name}': {e}")
                scene = None
        if scene is None:
            return False
        info.scene = scene
        if snap and os.path.isfile(snap_path):
            info.restored_snapshot = os.path.basename(snap)
        else:
            info.restored_snapshot = ""
        info.pending_snapshot = ""
        self.refresh_tab_title(tab_name)
        return True

    def _save_current_to_tab(self):
        if self._active_tab and self._active_tab in self._tabs and self._engine.scene:
            info = self._tabs[self._active_tab]
            if info.scene is None:
                return
            info.scene = self._engine.scene
            info.dirty = self._engine.scene.dirty
            scene_path = getattr(self._engine.scene, "path", None)
            if scene_path:
                info.path = scene_path
            vp = getattr(self._mw, "_viewport", None)
            if vp and hasattr(vp, "_cam"):
                cam = vp._cam
                info.camera_state = {
                    "position": cam._position.to_list(),
                    "yaw": cam._yaw,
                    "pitch": cam._pitch,
                    "nav_mode": getattr(cam, "_nav_mode", "fly"),
                    "orbit_target": cam._orbit_target.to_list(),
                    "orbit_dist": cam._orbit_dist,
                    "orbit_dist_target": getattr(cam, "_orbit_dist_target", cam._orbit_dist),
                    "is_2d_mode": cam._is_2d_mode,
                    "ortho_zoom_distance": cam._ortho_zoom_distance,
                    "stored_ortho_size": cam._stored_ortho_size,
                    "fov": cam._fov,
                    "near": cam._near,
                    "far": cam._far,
                }
            if vp:
                info.selected_entity_ids = [e.id for e in vp._selected_entities]
            info.play_mode = self._engine.play_mode
            self.refresh_tab_title(self._active_tab)

    def _norm_path(self, p: str) -> str:
        try:
            if not p:
                return ""
            return os.path.normcase(os.path.normpath(p))
        except Exception:
            return p or ""

    def _load_scene(self, info: SceneTabInfo):
        if info.scene is None and not info.prefab_path:
            if info.pending_snapshot or (info.path and os.path.isfile(info.path or "")):
                if not self.ensure_tab_loaded(info.name):
                    raise RuntimeError(f"Unable to load scene '{info.name}'")
            else:
                self._engine.new_scene(info.name)
                if info.path:
                    self._engine.scene.path = info.path
                info.scene = self._engine.scene
                info.pending_snapshot = ""
        if self._engine.scene is not info.scene:
            if self._engine.scene:
                self._engine._plugin_manager.notify_scene_unloaded(self._engine.scene)
            from core.components.rendering.postfx.graphics_effect import GraphicsEffect
            try:
                GraphicsEffect.cleanup_registry()
            except Exception as e:
                Logger.error(f"GraphicsEffect cleanup failed: {e}", e)
            self._engine._scene = info.scene
            self._engine._plugin_manager.notify_scene_loaded(info.scene)
        self._engine._emit_event("scene_loaded", info.scene)
        vp = getattr(self._mw, "_viewport", None)
        if vp and hasattr(vp, "_cam") and info.camera_state:
            cs = info.camera_state
            cam = vp._cam
            cam._position = Vec3(*cs["position"])
            cam._yaw = cs["yaw"]
            cam._pitch = cs["pitch"]
            nav = cs.get("nav_mode", getattr(cam, "_nav_mode", "fly"))
            if nav in ("fly", "orbit"):
                cam._nav_mode = nav
            cam._orbit_target = Vec3(*cs["orbit_target"])
            cam._orbit_dist = cs["orbit_dist"]
            try:
                cam._orbit_dist_target = float(cs.get("orbit_dist_target", cam._orbit_dist))
            except Exception:
                cam._orbit_dist_target = cam._orbit_dist
            try:
                cam._fly_dolly_remaining = 0.0
            except Exception:
                pass
            try:
                cam._vel = Vec3.zero()
            except Exception:
                pass
            cam._focus_active = False
            try:
                cam._focus_transition_blend = 1.0
            except Exception:
                pass
            if cam._nav_mode == "orbit":
                try:
                    cam._apply_orbit_transform()
                except Exception:
                    pass
            try:
                sync_fn = getattr(self._mw, "_sync_nav_mode_ui", None)
                if callable(sync_fn):
                    sync_fn(cam._nav_mode)
            except Exception:
                pass
            cam._is_2d_mode = cs["is_2d_mode"]
            cam._ortho_zoom_distance = cs["ortho_zoom_distance"]
            cam._stored_ortho_size = cs["stored_ortho_size"]
            cam._fov = cs.get("fov", cam.DEFAULT_FOV)
            cam._near = cs.get("near", cam.DEFAULT_NEAR)
            cam._far = cs.get("far", cam.DEFAULT_FAR)
            try:
                tb = getattr(self._mw, "_render_toolbar", None)
                if tb is not None:
                    if hasattr(tb, "set_camera_2d"):
                        tb.set_camera_2d(cam._is_2d_mode)
                    if hasattr(tb, "set_camera_projection"):
                        tb.set_camera_projection(cam.is_orthographic)
            except Exception:
                pass
        if vp:
            resolved = [info.scene.get_entity(eid) for eid in info.selected_entity_ids if info.scene.get_entity(eid)]
            vp._selected_entities = resolved
            vp._set_gizmo_entity(resolved[0] if resolved else None)
            vp.entity_selected.emit(resolved[0] if resolved else None)
            vp.entities_selected.emit(resolved)
            from editor.viewport.collaboration import send_collab_selection
            send_collab_selection(vp)
        if hasattr(self._mw, "_hierarchy"):
            self._mw._hierarchy.refresh()
        self.refresh_tab_title(info.name)

    def _save_scene_tab(self, info: SceneTabInfo):
        if info.scene is None:
            return
        if not info.path:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(self._mw, "Save Scene", "scenes/", "Scenes (*.zpes)")
            if not path:
                return
            if not path.endswith(".zpes"):
                path += ".zpes"
            info.path = path
        try:
            self._engine.save_scene_object(info.scene, info.path)
        except Exception as e:
            Logger.error(f"Failed to save scene tab '{info.name}': {e}")
        self.refresh_tab_title(info.name)

    def dirty_scene_tabs(self) -> list[str]:
        out: list[str] = []
        try:
            for tab_name in list(self._tab_names):
                info = self._tabs.get(tab_name)
                if info is None or info.prefab_path:
                    continue
                if self._is_tab_dirty(info):
                    out.append(tab_name)
        except Exception:
            pass
        return out

    def save_all_dirty_tabs(self) -> tuple[int, list[str]]:
        saved = 0
        failed: list[str] = []
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        except Exception:
            pass
        try:
            for tab_name in self.dirty_scene_tabs():
                try:
                    info = self._tabs.get(tab_name)
                    if info is None:
                        continue
                    if info.scene is None:
                        if not self.ensure_tab_loaded(tab_name):
                            failed.append(tab_name)
                            continue
                    before = bool(info.scene is not None and info.scene.dirty)
                    self._save_scene_tab(info)
                    after = bool(info.scene is not None and info.scene.dirty)
                    if before and not after:
                        saved += 1
                except Exception:
                    failed.append(tab_name)
        finally:
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.restoreOverrideCursor()
            except Exception:
                pass
        return saved, failed

    def update_tab_name(self, old_name: str, new_name: str):
        if old_name not in self._tabs:
            return
        info = self._tabs.pop(old_name)
        info.name = new_name
        self._tabs[new_name] = info
        idx = self._scene_tab_idx(old_name)
        if idx >= 0:
            self._tab_bar.setTabData(idx, new_name)
        name_idx = self._tab_names.index(old_name)
        self._tab_names[name_idx] = new_name
        if self._active_tab == old_name:
            self._active_tab = new_name
        self.refresh_tab_title(new_name)
