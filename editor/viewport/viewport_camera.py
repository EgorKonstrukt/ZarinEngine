# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.maths.math3d import Vec3


class ViewportCameraMixin:

    def _sync_toolbar_gizmo_mode(self, mode) -> None:
        try:
            name = mode.value if hasattr(mode, "value") else str(mode).lower()
            mw = getattr(self, "_mw", None)
            if mw is not None:
                try:
                    from editor.toolbar_registry import get_toolbar_registry
                    get_toolbar_registry(mw).store("gizmo_mode", str(name).lower())
                except Exception:
                    pass
                try:
                    tb = getattr(mw, "_scene_toolbar", None)
                    if tb is not None and hasattr(tb, "set_gizmo_mode"):
                        tb.set_gizmo_mode(mode)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_fov_changed(self, value: float):
        self._cam._fov = value

    def _on_near_changed(self, value: float):
        self._cam._near = value

    def _on_far_changed(self, value: float):
        self._cam._far = value

    def _on_move_speed_changed(self, value: float):
        self._cam._move_speed = value

    def _on_rotate_speed_changed(self, value: float):
        self._cam._rotate_speed = value

    def _on_render_scale_changed(self, value: int):
        self._cam._render_scale = max(0.05, min(1.0, value / 100.0))
        self.update()

    def _on_depth_changed(self, value: int):
        from PySide6.QtGui import QSurfaceFormat
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(value)
        fmt.setVersion(4, 6)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        self.setFormat(fmt)

    def set_grid_step(self, step: float):
        self._grid_step = max(0.01, step)

    def snap_to_grid(self, value: float) -> float:
        if self._grid_step <= 0:
            return value
        return round(value / self._grid_step) * self._grid_step

    def snap_vec3_to_grid(self, v: Vec3) -> Vec3:
        if self._grid_step <= 0:
            return v
        return Vec3(round(v.x / self._grid_step) * self._grid_step, round(v.y / self._grid_step) * self._grid_step, round(v.z / self._grid_step) * self._grid_step)

    def _paint_editor_update(self, now, prof=None):
        eng = self._engine
        if self._in_update:
            return
        dt = now - self._last_frame_time
        self._last_frame_time = now
        if dt > 0.05:
            dt = 0.05
        elif dt < 0.0:
            dt = 0.0
        self._last_dt = dt
        from core.gizmo.core import GizmoMode
        from core.input.constants import KEY_Q, KEY_W, KEY_E, KEY_R, KEY_F, KEY_DELETE
        prof.start("input_handling")
        if self._im:
            self._im.new_frame()
        if self._focused and self.isActiveWindow():
            if self._im and self._im.key_just_pressed(KEY_Q):
                self._gizmo.mode = GizmoMode.NONE
                try:
                    self._sync_toolbar_gizmo_mode(GizmoMode.NONE)
                except Exception:
                    pass
                from editor.viewport.collaboration import send_collab_gizmo_state
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_W):
                self._gizmo.mode = GizmoMode.TRANSLATE
                try:
                    self._sync_toolbar_gizmo_mode(GizmoMode.TRANSLATE)
                except Exception:
                    pass
                from editor.viewport.collaboration import send_collab_gizmo_state
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_E):
                self._gizmo.mode = GizmoMode.ROTATE
                try:
                    self._sync_toolbar_gizmo_mode(GizmoMode.ROTATE)
                except Exception:
                    pass
                from editor.viewport.collaboration import send_collab_gizmo_state
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_R):
                self._gizmo.mode = GizmoMode.SCALE
                try:
                    self._sync_toolbar_gizmo_mode(GizmoMode.SCALE)
                except Exception:
                    pass
                from editor.viewport.collaboration import send_collab_gizmo_state
                send_collab_gizmo_state(self)
            elif self._im and self._im.key_just_pressed(KEY_F):
                if self._selected_entities:
                    ent = self._selected_entities[0]
                    t = ent.transform
                    if t:
                        try:
                            from editor.entframe import compute_entity_frame
                            center, radius = compute_entity_frame(ent, self._renderer)
                            self._cam.frame_bounds(center, radius)
                        except Exception:
                            try:
                                self._cam.frame_bounds(t.position)
                            except Exception:
                                pass
            elif self._im and self._im.key_just_pressed(KEY_DELETE):
                if self._selected_entities and eng.scene:
                    from editor.viewport.collaboration import is_collab_locked
                    if not is_collab_locked(self):
                        from core.foundation.cmd import DeleteEntityCommand, get_history
                        for ent in list(self._selected_entities):
                            if ent.locked or ent.system:
                                continue
                            cmd = DeleteEntityCommand(eng.scene, ent.id)
                            get_history().execute(cmd)
                        self._selected_entities.clear()
                        self._set_gizmo_entity(None)
                        self.entity_selected.emit(None)
                        from editor.viewport.collaboration import send_collab_selection
                        send_collab_selection(self)
        prof.stop("input_handling")
        prof.start("editor_update")
        if not eng.play_mode:
            with prof.scope("editor_particles"):
                self._update_editor_particles(dt, self._selected_entities)
            if eng._scene_lock.acquire(blocking=False):
                try:
                    with prof.scope("gizmo_update"):
                        self._gizmos_api.update(dt)
                finally:
                    eng._scene_lock.release()
            with prof.scope("cam_update"):
                self._cam.update(dt)
        else:
            try:
                if self._gizmos_api is not None:
                    with prof.scope("gizmo_update"):
                        self._gizmos_api.update(dt)
            except Exception:
                pass
            with prof.scope("cam_update"):
                self._cam.update(dt)
        prof.stop("editor_update")


class _null_scope:

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


__all__ = ["ViewportCameraMixin"]
