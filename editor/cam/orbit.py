# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.maths.math3d import Vec3
from core.input.constants import KEY_W, KEY_A, KEY_S, KEY_D, KEY_Q, KEY_E, KEY_SHIFT


class OrbitMixin:
    def set_cursor(self, pos: Vec3) -> None:
        try:
            cx = float(pos.x)
            cy = float(pos.y)
            cz = float(pos.z)
        except Exception:
            return
        target = Vec3(cx, cy, cz)
        delta = target - self._position
        dist = delta.length()
        if dist < 1e-6:
            return
        direction = delta.normalized()
        self._orbit_target = target
        self._focus_active = False
        self._focus_transition_blend = 1.0
        self._fly_dolly_remaining = 0.0
        self._yaw = math.degrees(math.atan2(-direction.x, -direction.z))
        self._pitch = math.degrees(math.asin(max(-1.0, min(1.0, -direction.y))))
        self._pitch = max(-89.0, min(89.0, self._pitch))
        dist = max(self.ORBIT_MIN_DIST, min(dist, self.ORBIT_MAX_DIST))
        self._orbit_dist = dist
        self._orbit_dist_target = dist

    def set_nav_mode(self, mode: str) -> None:
        if mode not in (self.NAV_FLY, self.NAV_ORBIT):
            return
        if mode == self._nav_mode:
            return
        if mode == self.NAV_ORBIT:
            fwd = self._forward()
            cur = (self._position - self._orbit_target).length()
            base = self._orbit_dist
            if base < self.ORBIT_MIN_DIST or base > self.ORBIT_MAX_DIST:
                base = 10.0
            if cur < 1e-6:
                self._orbit_target = self._position + fwd * base
                self._orbit_dist = base
                self._orbit_dist_target = base
            else:
                to_target = (self._orbit_target - self._position).normalized()
                dot = max(-1.0, min(1.0, to_target.dot(fwd)))
                if dot < 0.999:
                    use_d = cur
                    if use_d < self.ORBIT_MIN_DIST or use_d > self.ORBIT_MAX_DIST:
                        use_d = base
                    self._orbit_target = self._position + fwd * use_d
                    self._orbit_dist = use_d
                    self._orbit_dist_target = use_d
                else:
                    self._orbit_dist = max(self.ORBIT_MIN_DIST, min(cur, self.ORBIT_MAX_DIST))
                    self._orbit_dist_target = self._orbit_dist
            self._vel = Vec3.zero()
            self._fly_dolly_remaining = 0.0
            self._focus_active = False
            self._focus_transition_blend = 1.0
        else:
            self._fly_dolly_remaining = 0.0
            self._vel = Vec3.zero()
            self._focus_active = False
            self._focus_transition_blend = 1.0
        self._nav_mode = mode
        if self._on_nav_mode_changed is not None:
            try:
                self._on_nav_mode_changed(mode)
            except Exception:
                pass

    def toggle_nav_mode(self) -> str:
        self.set_nav_mode(self.NAV_FLY if self._nav_mode == self.NAV_ORBIT else self.NAV_ORBIT)
        return self._nav_mode

    def _apply_orbit_transform(self) -> None:
        fwd = self._forward()
        self._position = self._orbit_target - fwd * self._orbit_dist

    def _persp_pan_amount(self, dist: float) -> float:
        try:
            d = max(float(dist), 0.5)
        except Exception:
            d = 10.0
        fov = self._fov
        try:
            fov = max(1.0, min(float(fov), 120.0))
        except Exception:
            fov = self.DEFAULT_FOV
        half = d * math.tan(math.radians(fov) * 0.5)
        base = (2.0 * half) / max(1, self._viewport_h)
        try:
            norm = self.MOVE_SPEED * self.PAN_SPEED
            gain = (self._move_speed * self._pan_speed) / norm if norm > 0 else 1.0
        except Exception:
            gain = 1.0
        return base * gain

    def _sync_orbit_dist_from_transform(self) -> None:
        d = (self._position - self._orbit_target).length()
        d = max(self.ORBIT_MIN_DIST, min(d, self.ORBIT_MAX_DIST))
        self._orbit_dist = d
        self._orbit_dist_target = d

    def _apply_orbit_dolly(self, dt: float) -> None:
        if abs(self._orbit_dist - self._orbit_dist_target) < 1e-5:
            self._orbit_dist = self._orbit_dist_target
        else:
            st = min(1.0, dt * self._zoom_smooth_speed)
            self._orbit_dist = self._orbit_dist + (self._orbit_dist_target - self._orbit_dist) * st
            if abs(self._orbit_dist - self._orbit_dist_target) < 0.001:
                self._orbit_dist = self._orbit_dist_target
        self._apply_orbit_transform()

    def _orbit_mouse_move(self, dx, dy) -> None:
        if self._middle_mouse:
            ctrl = self._is_ctrl_down()
            if ctrl:
                factor = 1.0 + dy * 0.01
                if factor < 0.5:
                    factor = 0.5
                if factor > 2.0:
                    factor = 2.0
                new_dist = self._orbit_dist_target * factor
                new_dist = max(self.ORBIT_MIN_DIST, min(new_dist, self.ORBIT_MAX_DIST))
                self._orbit_dist_target = new_dist
                return
            r = self._right()
            u = self._up()
            amt = self._persp_pan_amount(self._orbit_dist)
            off = r * (-dx * amt) + u * (dy * amt)
            self._position = self._position + off
            self._orbit_target = self._orbit_target + off
            return
        if self._right_mouse or self._alt_left:
            shift = self._is_shift_down()
            if shift and self._right_mouse:
                r = self._right()
                u = self._up()
                amt = self._persp_pan_amount(self._orbit_dist)
                off = r * (-dx * amt) + u * (dy * amt)
                self._position = self._position + off
                self._orbit_target = self._orbit_target + off
                return
            self._yaw -= dx * self._rotate_speed
            self._pitch = max(-89.0, min(89.0, self._pitch + dy * self._rotate_speed))
            self._apply_orbit_transform()
            return
        return

    def _orbit_scroll_step(self, scaled_delta) -> None:
        scale = 1.0 - scaled_delta * self._zoom_strength
        if scale < 0.1:
            scale = 0.1
        if scale > 4.0:
            scale = 4.0
        new_dist = self._orbit_dist_target * scale
        new_dist = max(self.ORBIT_MIN_DIST, min(new_dist, self.ORBIT_MAX_DIST))
        self._orbit_dist_target = new_dist

    def _update_focus_blend(self, dt) -> None:
        if self._focus_transition_blend < 1.0:
            adv = min(dt * self._transition_speed, 1.0)
            self._focus_transition_blend += adv
            if self._focus_transition_blend >= 1.0:
                self._focus_transition_blend = 1.0
                self._position = self._focus_target_pos
                self._orbit_target = self._focus_target_orbit
                self._yaw = self._focus_target_yaw
                self._pitch = self._focus_target_pitch
                if self._nav_mode == self.NAV_ORBIT:
                    self._sync_orbit_dist_from_transform()
            else:
                e = self._ease_in_out_cubic(self._focus_transition_blend)
                self._position = Vec3(
                    self._focus_start_pos.x + (self._focus_target_pos.x - self._focus_start_pos.x) * e,
                    self._focus_start_pos.y + (self._focus_target_pos.y - self._focus_start_pos.y) * e,
                    self._focus_start_pos.z + (self._focus_target_pos.z - self._focus_start_pos.z) * e,
                )
                self._orbit_target = Vec3(
                    self._focus_start_orbit.x + (self._focus_target_orbit.x - self._focus_start_orbit.x) * e,
                    self._focus_start_orbit.y + (self._focus_target_orbit.y - self._focus_start_orbit.y) * e,
                    self._focus_start_orbit.z + (self._focus_target_orbit.z - self._focus_start_orbit.z) * e,
                )
                self._yaw = self._lerp_angle(self._focus_start_yaw, self._focus_target_yaw, e)
                self._pitch = self._focus_start_pitch + (self._focus_target_pitch - self._focus_start_pitch) * e
                if self._nav_mode == self.NAV_ORBIT:
                    self._sync_orbit_dist_from_transform()

    def _orbit_update_move(self, dt, im, boost_factor, any_move) -> None:
        if self._focus_transition_blend < 1.0:
            return
        self._apply_orbit_dolly(dt)
        right = self._right()
        fwd = self._forward()
        up = self._up()
        world_up = Vec3.up()
        accel = Vec3.zero()
        dist_scale = max(0.2, self._orbit_dist / 10.0)
        speed = self._move_speed * dist_scale * boost_factor
        if im.is_key_pressed(KEY_SHIFT):
            speed *= self._fast_mult
        if im.is_key_pressed(KEY_W):
            accel = accel + fwd * speed
        if im.is_key_pressed(KEY_S):
            accel = accel - fwd * speed
        if im.is_key_pressed(KEY_A):
            accel = accel - right * speed
        if im.is_key_pressed(KEY_D):
            accel = accel + right * speed
        if im.is_key_pressed(KEY_E):
            accel = accel + world_up * speed
        if im.is_key_pressed(KEY_Q):
            accel = accel - world_up * speed
        if any_move:
            facc = dt * self._acceleration
            self._vel = self._vel + (accel - self._vel) * min(facc, 1.0)
            step = self._vel * dt
            self._position = self._position + step
            self._orbit_target = self._orbit_target + step
            self._apply_orbit_transform()
        else:
            self._vel = self._vel * 0.85
            if self._vel.length() > 1e-6:
                step = self._vel * dt
                self._position = self._position + step
                self._orbit_target = self._orbit_target + step
                self._apply_orbit_transform()
            else:
                self._vel = Vec3.zero()
        _ = up

    def focus_on(self, target: Vec3, distance: float = 5.0):
        dir_to_target = (target - self._position).normalized()
        self._focus_start_pos = self._position
        self._focus_target_pos = target - dir_to_target * distance
        self._focus_start_orbit = self._orbit_target
        self._focus_target_orbit = target
        self._focus_start_yaw = self._yaw
        self._focus_start_pitch = self._pitch
        self._focus_target_yaw = math.degrees(math.atan2(-dir_to_target.x, -dir_to_target.z))
        self._focus_target_pitch = math.degrees(math.asin(max(-1.0, min(1.0, -dir_to_target.y))))
        self._focus_active = True
        self._focus_transition_blend = 0.0
        self._fly_dolly_remaining = 0.0

    def frame_bounds(self, center: Vec3, radius: float = 1.0):
        self.focus_on(center, max(radius * 2.5, 1.0))


__all__ = ["OrbitMixin"]
