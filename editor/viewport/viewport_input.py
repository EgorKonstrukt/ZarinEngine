# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent
from core.maths.math3d import Vec3
from core.input.constants import KEY_Q, KEY_W, KEY_E, KEY_R, KEY_F, KEY_DELETE, KEY_SHIFT, KEY_CTRL, KEY_ALT, KEY_SPACE, KEY_S, KEY_D, KEY_A, MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE, MOUSE_L, MOUSE_R, MOUSE_M


class ViewportInputMixin:

    def mousePressEvent(self, event: QMouseEvent):
        if self._overlay_canvas:
            if self._overlay_canvas.edit_mode:
                self._overlay_canvas.mousePressEvent(event)
                return
            hit = self._overlay_canvas.hit_test_widget(event.position().x(), event.position().y())
            if hit:
                self._overlay_canvas.mousePressEvent(event)
                return
        self._focused = True
        self.setFocus()
        dpr = self.devicePixelRatio()
        lx, ly = int(event.position().x()), int(event.position().y())
        x, y = int(lx * dpr), int(ly * dpr)
        qt_btn = event.button()
        if qt_btn == Qt.MouseButton.LeftButton and self._stats_enabled:
            try:
                from core.renderer.render_stats import stats_header_at, toggle_stats_section
                hdr = stats_header_at(x, y)
            except Exception:
                hdr = None
            if hdr:
                try:
                    toggle_stats_section(hdr)
                except Exception:
                    pass
                event.accept()
                return
        alt = self._im.is_key_pressed(KEY_ALT) if self._im else False
        shift = self._im.is_key_pressed(KEY_SHIFT) if self._im else False
        ctrl = self._im.is_key_pressed(KEY_CTRL) if self._im else False
        self._gizmo.ctrl_down = ctrl
        self._gizmo.shift_down = shift
        btn = MOUSE_L if qt_btn == Qt.MouseButton.LeftButton else (MOUSE_R if qt_btn == Qt.MouseButton.RightButton else MOUSE_M)
        if self._im:
            self._im.feed_mouse_button(btn, True)
        if btn == MOUSE_L:
            self._ng_mouse_down = True
            self._ng_clicked = True
            self._ng_mouse_pos = (float(lx), float(ly))
            self._ng_last_mouse = (lx, ly)
        if btn == MOUSE_R:
            self._rmb_press_pos = (lx, ly)
            try:
                self._rmb_press_shift = bool(self._im.is_key_pressed(KEY_SHIFT)) if self._im else bool(shift)
            except Exception:
                self._rmb_press_shift = bool(shift)
        self._cam.on_mouse_press(btn, lx, ly, alt)
        from editor.viewport.collaboration import send_collab_cursor
        send_collab_cursor(self, lx, ly)
        if btn == MOUSE_L and not alt:
            cx, cy = getattr(self, "_navigation_gizmo_center", (0.0, 0.0))
            interacting = getattr(self, "_navigation_gizmo_interacting", False)
            if interacting and (cx, cy) != (0.0, 0.0):
                self._navigation_gizmo_orbit = True
                self._cam.on_mouse_press(btn, lx, ly, alt)
                return
            if self._pb_scale_gizmo and self._pb_scale_gizmo.active and self._pb_scale_gizmo.on_mouse_press(lx, ly):
                return
            if self._pb_grab and self._pb_grab.on_mouse_press(lx, ly):
                ge = self._pb_grab.grab_entity
                if ge is not None:
                    self._selected_entities = [ge]
                    self._set_gizmo_entity(ge)
                    self.entity_selected.emit(ge)
                    from editor.viewport.collaboration import send_collab_selection
                    send_collab_selection(self)
                return
            if self._gizmo.on_mouse_press(x, y, self._cam, *self._get_physical_dims()):
                if self._gizmo.ctrl_down and getattr(self._gizmo, "_active_op", "translate") in ("translate", "scale") and self._selected_entities:
                    self._extrude_on_ctrl_press()
                self._store_multi_initial()
                return
            from editor.viewport.picking import pick_entity
            picked = pick_entity(self, lx, ly)
            if shift or ctrl:
                if picked:
                    if picked in self._selected_entities:
                        self._selected_entities.remove(picked)
                    else:
                        self._selected_entities.append(picked)
                    self._set_gizmo_entity(self._selected_entities[0] if self._selected_entities else None)
                    self.entities_selected.emit(self._selected_entities)
                else:
                    self._selected_entities = []
                    self._selected_set_version += 1
                    self._set_gizmo_entity(None)
                    self.entity_selected.emit(None)
                from editor.viewport.collaboration import send_collab_selection
                send_collab_selection(self)
                return
            self._area_selecting = True
            self._area_start = (lx, ly)
            self._area_end = (lx, ly)
            self.update()
            if picked != (self._selected_entities[0] if self._selected_entities else None):
                self._selected_entities = [picked] if picked else []
                self._set_gizmo_entity(picked)
                self.entity_selected.emit(picked)
                from editor.viewport.collaboration import send_collab_selection
                send_collab_selection(self)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._overlay_canvas and self._overlay_canvas.edit_mode:
            self._overlay_canvas.mouseMoveEvent(event)
            return
        dpr = self.devicePixelRatio()
        lx, ly = int(event.position().x()), int(event.position().y())
        self._last_mouse_pos = (lx, ly)
        px, py = int(lx * dpr), int(ly * dpr)
        ctrl = self._im.is_key_pressed(KEY_CTRL) if self._im else False
        shift = self._im.is_key_pressed(KEY_SHIFT) if self._im else False
        self._gizmo.ctrl_down = ctrl
        self._gizmo.shift_down = shift
        self._cam.on_mouse_move(lx, ly)
        self._ng_mouse_pos = (float(lx), float(ly))
        dx = lx - self._ng_last_mouse[0]
        dy = ly - self._ng_last_mouse[1]
        self._ng_mouse_delta = (self._ng_mouse_delta[0] + dx, self._ng_mouse_delta[1] + dy)
        self._ng_last_mouse = (lx, ly)
        self._ng_mouse_down = bool(event.buttons() & Qt.MouseButton.LeftButton)
        if not self._stats_enabled and not self._no_qt_overlay:
            _now_hov = __import__("time").perf_counter()
            if _now_hov - getattr(self, "_last_overlay_update", 0.0) >= 0.1:
                self._last_overlay_update = _now_hov
                self._overlay_widget.update()
        from editor.viewport.collaboration import send_collab_cursor
        send_collab_cursor(self, lx, ly)
        from editor.viewport.projection import screen_to_world
        world_pos = screen_to_world(self, lx, ly)
        _tx = f"X: {world_pos.x:.2f}"
        _ty = f"Y: {world_pos.y:.2f}"
        _tz = f"Z: {world_pos.z:.2f}"
        _cached = getattr(self, "_cursor_label_cache", ("", "", ""))
        if _cached != (_tx, _ty, _tz):
            self._cursor_x_label.setText(_tx)
            self._cursor_y_label.setText(_ty)
            self._cursor_z_label.setText(_tz)
            self._cursor_label_cache = (_tx, _ty, _tz)
        if self._area_selecting:
            self._area_end = (lx, ly)
            self.update()
        else:
            if self._pb_grab and self._pb_grab.dragging:
                self._pb_grab.on_mouse_move(lx, ly)
                self.update()
                return
            if self._pb_scale_gizmo and self._pb_scale_gizmo._dragging:
                self._pb_scale_gizmo.on_mouse_move(lx, ly)
                self.update()
                return
            primary = self._gizmo._entity
            multi = len(self._selected_entities) > 1 and primary is not None and self._gizmo._dragging
            pre_pos = None
            pre_rot = None
            if multi:
                pt = primary.transform
                if pt:
                    from core.maths.math3d import Vec3 as _V, Quat as _Q
                    pre_pos = _V(pt.position.x, pt.position.y, pt.position.z)
                    pre_rot = _Q(pt.local_rotation.x, pt.local_rotation.y, pt.local_rotation.z, pt.local_rotation.w)
            self._gizmo.on_mouse_move(px, py, self._cam, *self._get_physical_dims())
            from editor.viewport.collaboration import send_collab_gizmo_state, send_collab_transforms
            send_collab_gizmo_state(self)
            if self._gizmo._dragging:
                send_collab_transforms(self)
            if multi and pre_pos is not None:
                self._drag_multi_entities(primary, pre_pos, pre_rot)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._overlay_canvas:
            if self._overlay_canvas.edit_mode:
                self._overlay_canvas.mouseReleaseEvent(event)
                return
            hit = self._overlay_canvas.hit_test_widget(event.position().x(), event.position().y())
            if hit:
                self._overlay_canvas.mouseReleaseEvent(event)
                return
        qt_btn = event.button()
        btn = MOUSE_L if qt_btn == Qt.MouseButton.LeftButton else (MOUSE_R if qt_btn == Qt.MouseButton.RightButton else MOUSE_M)
        if self._im:
            self._im.feed_mouse_button(btn, False)
        if btn == MOUSE_L:
            self._ng_mouse_down = False
            self._ng_released = True
            self._ng_mouse_pos = (float(event.position().x()), float(event.position().y()))
        self._cam.on_mouse_release(btn)
        self._navigation_gizmo_orbit = False
        if btn == MOUSE_R:
            try:
                rx, ry = int(event.position().x()), int(event.position().y())
            except Exception:
                rx, ry = (0, 0)
            try:
                px, py = getattr(self, "_rmb_press_pos", (rx, ry))
            except Exception:
                px, py = (rx, ry)
            try:
                shift_at_press = bool(getattr(self, "_rmb_press_shift", False))
            except Exception:
                shift_at_press = False
            try:
                shift_now = bool(self._im.is_key_pressed(KEY_SHIFT)) if self._im else False
            except Exception:
                shift_now = False
            try:
                mods = event.modifiers()
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    shift_now = True
            except Exception:
                pass
            if (shift_at_press or shift_now) and abs(rx - px) < 5 and abs(ry - py) < 5:
                try:
                    self._place_cursor_at(rx, ry)
                except Exception:
                    pass
        if btn == MOUSE_L and self._area_selecting:
            self._area_selecting = False
            x1, y1 = self._area_start
            x2, y2 = self._area_end
            if abs(x2 - x1) > 3 or abs(y2 - y1) > 3:
                from editor.viewport.picking import pick_entities_in_rect
                selected = pick_entities_in_rect(self, min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                if selected:
                    self._selected_entities = selected
                    self._set_gizmo_entity(self._selected_entities[0] if self._selected_entities else None)
                    self.entities_selected.emit(self._selected_entities)
                    from editor.viewport.collaboration import send_collab_selection
                    send_collab_selection(self)
            self.update()
        multi = bool(self._multi_entity_initial_transforms and len(self._selected_entities) > 1)
        self._gizmo._multi_undo_active = multi
        self._gizmo.on_mouse_release()
        self._gizmo._multi_undo_active = False
        if self._pb_scale_gizmo and self._pb_scale_gizmo._dragging:
            self._pb_scale_gizmo.on_mouse_release()
            self.update()
        if self._pb_grab and self._pb_grab.dragging:
            self._pb_grab.on_mouse_release()
            self.update()
        self._commit_multi_transform()
        from editor.viewport.collaboration import send_collab_transforms
        send_collab_transforms(self)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y() / 120.0
        cx, cy = int(event.position().x()), int(event.position().y())
        self._cam.on_scroll(delta, cx, cy)
        if self._im:
            self._im.feed_scroll(0.0, delta)

    def keyPressEvent(self, event: QKeyEvent):
        self._focused = True
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C:
                self._copy_selected_entities()
                event.accept()
                return
            if event.key() == Qt.Key.Key_V:
                self._paste_entities()
                event.accept()
                return
            if event.key() == Qt.Key.Key_D:
                if self._selected_entities:
                    self._copy_selected_entities()
                    self._paste_entities()
                event.accept()
                return
        if self._im:
            vk = self._qt_key_to_vk(event.key())
            if vk is None:
                nvk = event.nativeVirtualKey()
                if 65 <= nvk <= 90:
                    vk = nvk
            if vk is not None:
                self._im.feed_key(vk, True)
            from core.input.input_system import KeyCode
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self._im.feed_key(KeyCode.LEFT_SHIFT, True)
            if mods & Qt.KeyboardModifier.ControlModifier:
                self._im.feed_key(KeyCode.LEFT_CONTROL, True)
            if mods & Qt.KeyboardModifier.AltModifier:
                self._im.feed_key(KeyCode.LEFT_ALT, True)
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        if self._im:
            mods = event.modifiers()
            vk = self._qt_key_to_vk(event.key())
            if vk is None:
                nvk = event.nativeVirtualKey()
                if 65 <= nvk <= 90:
                    vk = nvk
            if vk is not None:
                self._im.feed_key(vk, False)
            from core.input.input_system import KeyCode
            if not (mods & Qt.KeyboardModifier.ShiftModifier):
                self._im.feed_key(KeyCode.LEFT_SHIFT, False)
            if not (mods & Qt.KeyboardModifier.ControlModifier):
                self._im.feed_key(KeyCode.LEFT_CONTROL, False)
            if not (mods & Qt.KeyboardModifier.AltModifier):
                self._im.feed_key(KeyCode.LEFT_ALT, False)
        event.accept()

    @staticmethod
    def _qt_key_to_vk(qt_key: int) -> Optional[int]:
        mapping = {Qt.Key.Key_W: KEY_W, Qt.Key.Key_A: KEY_A, Qt.Key.Key_S: KEY_S, Qt.Key.Key_D: KEY_D, Qt.Key.Key_Q: KEY_Q, Qt.Key.Key_E: KEY_E, Qt.Key.Key_R: KEY_R, Qt.Key.Key_F: KEY_F, Qt.Key.Key_Shift: KEY_SHIFT, Qt.Key.Key_Control: KEY_CTRL, Qt.Key.Key_Alt: KEY_ALT, Qt.Key.Key_Delete: KEY_DELETE, Qt.Key.Key_Space: KEY_SPACE}
        return mapping.get(qt_key)

    def contextMenuEvent(self, event):
        from core.gizmo.gizmo import GizmoAxis
        if self._gizmo._hover_axis != GizmoAxis.NONE and self._gizmo._is_multigizmo_active():
            from PyQt6.QtGui import QAction
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            gizmo_menu = menu.addMenu("Gizmo")
            vis_act = gizmo_menu.addAction("Visible")
            vis_act.setCheckable(True)
            vis_act.setChecked(self._gizmo.multigizmo_visible)
            vis_act.triggered.connect(lambda c: self._on_gizmo_visibility_toggled(c))
            gizmo_menu.addSeparator()
            align_menu = gizmo_menu.addMenu("Align To")
            for label in ["View", "World", "Local", "Custom"]:
                act = align_menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(self._gizmo.alignment.lower() == label.lower())
                act.triggered.connect(lambda c, l=label.lower(): self._on_gizmo_align_changed(l))
            gizmo_menu.addSeparator()
            lock_act = gizmo_menu.addAction("Orientation Lock")
            lock_act.setCheckable(True)
            lock_act.setChecked(self._gizmo.orientation_lock)
            lock_act.triggered.connect(lambda c: self._on_gizmo_orientation_lock_toggled(c))
            hide_act = gizmo_menu.addAction("Hide Gizmo")
            hide_act.triggered.connect(lambda: self._on_gizmo_visibility_toggled(False))
            create_menu = menu.addMenu("Create")
            self._populate_viewport_create_menu(create_menu)
            menu.exec(event.globalPos())
            return
        from PyQt6.QtWidgets import QMenu as _QMenu
        from editor.viewport.collaboration import is_collab_locked
        menu = _QMenu(self)
        create_menu = menu.addMenu("Create")
        self._populate_viewport_create_menu(create_menu)
        if self._selected_entities:
            menu.addSeparator()
            delete_act = menu.addAction("Delete")
            delete_act.setEnabled(not is_collab_locked(self))
            delete_act.triggered.connect(self._delete_selected)
        if is_collab_locked(self):
            create_menu.setEnabled(False)
        menu.exec(event.globalPos())

    def enterEvent(self, event):
        self._focused = True

    def focusInEvent(self, event):
        self._focused = True
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._focused = False
        super().focusOutEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-zpep"):
            event.acceptProposedAction()

    def _drop_world_pos(self, sx: int, sy: int):
        from editor.viewport.projection import screen_to_ray
        ray_origin, ray_dir = screen_to_ray(self, sx, sy)
        from editor.viewport.picking import pick_entity
        hit_entity = pick_entity(self, sx, sy)
        if hit_entity is not None:
            from editor.viewport.picking import _world_aabb_of, _ray_aabb_min
            box = _world_aabb_of(hit_entity)
            if box is not None:
                d = _ray_aabb_min(ray_origin.x, ray_origin.y, ray_origin.z, ray_dir.x, ray_dir.y, ray_dir.z, box[0][0], box[0][1], box[0][2], box[1][0], box[1][1], box[1][2])
                if d > 0 and d < 1e6:
                    return ray_origin + ray_dir * d, hit_entity
            return ray_origin + ray_dir * 50.0, hit_entity
        if abs(ray_dir.y) > 0.0001:
            t = -ray_origin.y / ray_dir.y
            if t > 0:
                return ray_origin + ray_dir * t, None
        return ray_origin + ray_dir * 10.0, None

    def _place_cursor_at(self, sx: int, sy: int):
        world_pos, _hit = self._drop_world_pos(sx, sy)
        try:
            set_fn = getattr(self._cam, "set_cursor", None)
            if callable(set_fn):
                set_fn(world_pos)
            else:
                self._cam._orbit_target = world_pos
        except Exception:
            pass
        self.update()

    def dropEvent(self, event):
        pos = event.position()
        sx, sy = int(pos.x()), int(pos.y())
        world_pos, hit_entity = self._drop_world_pos(sx, sy)
        if event.mimeData().hasFormat("application/x-zpep"):
            path = bytes(event.mimeData().data("application/x-zpep")).decode()
            self.entity_dropped.emit(path, world_pos, hit_entity)
        elif event.mimeData().hasText():
            text = event.mimeData().text()
            self.entity_dropped.emit(text, world_pos, hit_entity)
        event.acceptProposedAction()


__all__ = ["ViewportInputMixin"]
