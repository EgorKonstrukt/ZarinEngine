# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.maths.math3d import Vec3, Mat4
from core.input.constants import KEY_W, KEY_A, KEY_S, KEY_D, KEY_Q, KEY_E, KEY_SHIFT


class FlyMixin:
    def get_projection_matrix(self, aspect: float) -> Mat4:
        if (self._is_2d_mode or self._mode_2d_transition) and self._use_ortho_in_2d and self._is_orthographic:
            if self._ortho_zoom_distance < 0.5:
                dist = (self._position - Vec3.zero()).length()
                self._ortho_zoom_distance = dist * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
                self._stored_ortho_size = self._ortho_zoom_distance
            half_size = self._ortho_zoom_distance * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
            return Mat4.orthographic(-half_size*aspect, half_size*aspect, -half_size, half_size, self._near, self._far)
        if not self._transition_active and not self._is_orthographic:
            return Mat4.perspective(self._fov, aspect, self._near, self._far)
        if self._ortho_zoom_distance < 0.5:
            dist = (self._position - Vec3.zero()).length()
            self._ortho_zoom_distance = dist * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
            self._stored_ortho_size = self._ortho_zoom_distance
        blend = self._ease_in_out_cubic(self._transition_blend)
        anim_fov = math.degrees(2.0 * math.atan(math.tan(math.radians(self.DEFAULT_FOV) * 0.5) ** (1.0 - blend)))
        if blend < 0.5:
            t = blend * 2.0
            persp_mat = Mat4.perspective(anim_fov, aspect, self._near, self._far)
            half_size = self._ortho_zoom_distance * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
            ortho_mat = Mat4.orthographic(-half_size*aspect, half_size*aspect, -half_size, half_size, self._near, self._far)
            return Mat4(persp_mat._d + (ortho_mat._d - persp_mat._d) * t)
        else:
            half_size = self._ortho_zoom_distance * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
            return Mat4.orthographic(-half_size*aspect, half_size*aspect, -half_size, half_size, self._near, self._far)

    def _apply_fly_dolly(self, dt: float) -> None:
        if abs(self._fly_dolly_remaining) < 1e-6:
            self._fly_dolly_remaining = 0.0
            return
        if self._is_orthographic or self._is_2d_mode:
            self._fly_dolly_remaining = 0.0
            return
        st = min(1.0, dt * self._zoom_smooth_speed)
        step = self._fly_dolly_remaining * st
        if abs(self._fly_dolly_remaining) < 0.002:
            step = self._fly_dolly_remaining
        self._position = self._position + self._forward() * step
        self._fly_dolly_remaining = self._fly_dolly_remaining - step
        if abs(self._fly_dolly_remaining) < 1e-6:
            self._fly_dolly_remaining = 0.0

    def toggle_2d_mode(self):
        if self._mode_2d_transition:
            return
        if not self._is_2d_mode:
            self._stored_yaw = self._yaw
            self._stored_pitch = self._pitch
            self._stored_fov = self._fov
            self._stored_ortho = self._is_orthographic
            self._mode_2d_transition = True
            self._mode_2d_to_2d = True
            self._mode_2d_blend = 0.0
            if self._use_ortho_in_2d:
                if not self._is_orthographic:
                    self._stored_fov_for_2d = self._fov
                    dist = (self._position - Vec3.zero()).length()
                    self._ortho_zoom_distance = dist * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
                    self._stored_ortho_size = self._ortho_zoom_distance
                    self._is_orthographic = True
                else:
                    if not hasattr(self, "_stored_fov_for_2d"):
                        self._stored_fov_for_2d = self._fov
                    if self._ortho_zoom_distance < 0.5:
                        dist = (self._position - Vec3.zero()).length()
                        self._ortho_zoom_distance = dist * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
                        self._stored_ortho_size = self._ortho_zoom_distance
            else:
                if not hasattr(self, "_stored_fov_for_2d"):
                    self._stored_fov_for_2d = self._fov
            self._zoom_target_distance = self._ortho_zoom_distance
            self._zoom_cursor_ndc = None
        else:
            self._mode_2d_transition = True
            self._mode_2d_to_2d = False
            self._mode_2d_blend = 1.0
            self._yaw = 0.0
            self._pitch = 0.0
            self._is_2d_mode = False
            if not self._stored_ortho:
                self._transition_active = True
                self._transition_blend = 1.0
                self._transition_to_ortho = False
                self._fov = self.PERSPECTIVE_TO_ORTHO_FOV
            elif self._is_orthographic:
                self._transition_active = True
                self._transition_blend = 0.0
                self._transition_to_ortho = False
                self._fov = self._stored_fov_for_2d if hasattr(self, "_stored_fov_for_2d") else self._stored_fov
        if hasattr(self, "_on_projection_changed"):
            self._on_projection_changed()

    def toggle_projection(self):
        self._stored_fov = self._fov
        if self._is_orthographic:
            self._transition_active = True
            self._transition_blend = 1.0
            self._transition_to_ortho = False
            self._fov = self.PERSPECTIVE_TO_ORTHO_FOV
        else:
            if self._ortho_zoom_distance < 0.5:
                dist = (self._position - Vec3.zero()).length()
                self._ortho_zoom_distance = dist * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
                self._stored_ortho_size = self._ortho_zoom_distance
            self._transition_active = True
            self._transition_blend = 0.0
            self._transition_to_ortho = True
            self._fov = self.PERSPECTIVE_TO_ORTHO_FOV
        if hasattr(self, "_on_projection_changed"):
            self._on_projection_changed()

    def _pan_2d(self, dx, dy) -> None:
        r = self._right()
        u = self._up()
        half_size = self._ortho_zoom_distance * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
        amt = (2.0 * half_size) / max(1, self._viewport_h)
        self._position = self._position - r * (dx * amt) + u * (dy * amt)

    def _fly_mouse_move(self, dx, dy) -> None:
        if self._right_mouse or self._alt_left:
            self._yaw -= dx * self._rotate_speed
            self._pitch = max(-89.0, min(89.0, self._pitch + dy * self._rotate_speed))
        elif self._middle_mouse:
            r = self._right()
            u = self._up()
            amt = self._persp_pan_amount((self._position - self._orbit_target).length())
            self._position = self._position - r * (dx * amt) + u * (dy * amt)

    def _scroll_ortho_step(self, scaled_delta, cursor_x, cursor_y) -> None:
        scale = 1.0 - scaled_delta * self._zoom_strength
        new_dist = self._ortho_zoom_distance * scale
        new_dist = max(0.1, min(new_dist, 1000.0))
        self._stored_ortho_size = new_dist
        if self._is_2d_mode:
            self._ortho_zoom_distance = new_dist
            self._zoom_target_distance = new_dist
            if cursor_x is not None and cursor_y is not None and self._viewport_w > 0 and self._viewport_h > 0:
                ndc_x = 2.0 * cursor_x / self._viewport_w - 1.0
                ndc_y = 1.0 - 2.0 * cursor_y / self._viewport_h
                self._zoom_cursor_ndc = (ndc_x, ndc_y)
        else:
            self._ortho_zoom_distance = new_dist

    def _fly_scroll_step(self, scaled_delta) -> None:
        want = self._fly_dolly_remaining + scaled_delta * self._zoom_speed
        want = max(-100.0, min(want, 100.0))
        self._fly_dolly_remaining = want

    def _update_projection_transition(self, dt) -> None:
        if self._transition_active:
            t = min(dt * self._transition_speed, 1.0)
            if self._transition_to_ortho:
                self._transition_blend += t
                if self._transition_blend >= 1.0:
                    self._transition_blend = 1.0
                    self._is_orthographic = True
                    self._transition_active = False
                    self._fov = self._stored_fov_for_2d if hasattr(self, "_stored_fov_for_2d") else self._stored_fov
            else:
                self._transition_blend -= t
                if self._transition_blend <= 0.0:
                    self._transition_blend = 0.0
                    self._transition_active = False
                    self._is_orthographic = False
                    self._fov = self._stored_fov_for_2d if hasattr(self, "_stored_fov_for_2d") else self._stored_fov

    def _update_mode_2d(self, dt) -> None:
        if self._mode_2d_transition:
            adv = min(dt * self._transition_speed, 1.0)
            if self._mode_2d_to_2d:
                self._mode_2d_blend += adv
                if self._mode_2d_blend >= 1.0:
                    self._mode_2d_blend = 1.0
                    self._is_2d_mode = True
                    self._mode_2d_transition = False
                    self._yaw = 0.0
                    self._pitch = 0.0
                    if self._on_2d_mode_changed:
                        self._on_2d_mode_changed()
                else:
                    e = self._ease_in_out_cubic(self._mode_2d_blend)
                    self._yaw = self._lerp_angle(self._stored_yaw, 0.0, e)
                    self._pitch = self._stored_pitch * (1.0 - e)
            else:
                self._mode_2d_blend -= adv
                if self._mode_2d_blend <= 0.0:
                    self._mode_2d_blend = 0.0
                    self._mode_2d_transition = False
                    self._yaw = self._stored_yaw
                    self._pitch = self._stored_pitch
                    self._fov = self._stored_fov
                    if self._on_2d_mode_changed:
                        self._on_2d_mode_changed()
                else:
                    e = self._ease_in_out_cubic(self._mode_2d_blend)
                    self._yaw = self._lerp_angle(0.0, self._stored_yaw, 1.0 - e)
                    self._pitch = self._stored_pitch * (1.0 - e)

    def _update_ortho_zoom(self, dt) -> None:
        if self._is_2d_mode and self._use_ortho_in_2d and abs(self._ortho_zoom_distance - self._zoom_target_distance) > 0.001:
            old_half = self._ortho_zoom_distance * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
            st = min(dt * self._zoom_smooth_speed, 1.0)
            self._ortho_zoom_distance += (self._zoom_target_distance - self._ortho_zoom_distance) * st
            self._stored_ortho_size = self._ortho_zoom_distance
            new_half = self._ortho_zoom_distance * math.tan(math.radians(self.DEFAULT_FOV) * 0.5)
            if old_half > 1e-8 and self._zoom_cursor_ndc is not None:
                per_frame_scale = new_half / old_half
                ndc_x, ndc_y = self._zoom_cursor_ndc
                aspect = self._viewport_w / max(1, self._viewport_h)
                dx = ndc_x * old_half * aspect * (1.0 - per_frame_scale)
                dy = ndc_y * old_half * (1.0 - per_frame_scale)
                self._position = self._position + self._right() * dx + self._up() * dy
                self._zoom_cursor_ndc = None

    def _update_2d_move(self, dt, im, boost_factor) -> None:
        right = self._right()
        up = self._up()
        accel = Vec3.zero()
        speed = self._move_speed * (self._ortho_zoom_distance / 5.0) * boost_factor
        if im.is_key_pressed(KEY_SHIFT):
            speed *= self._fast_mult
        if im.is_key_pressed(KEY_W):
            accel = accel + up * speed
        if im.is_key_pressed(KEY_S):
            accel = accel - up * speed
        if im.is_key_pressed(KEY_A):
            accel = accel - right * speed
        if im.is_key_pressed(KEY_D):
            accel = accel + right * speed
        if im.is_key_pressed(KEY_E):
            accel = accel + self._forward() * speed
        if im.is_key_pressed(KEY_Q):
            accel = accel - self._forward() * speed
        facc = dt * self._acceleration
        self._vel = self._vel + (accel - self._vel) * min(facc, 1.0)
        self._position = self._position + self._vel * dt

    def _update_fly_move(self, dt, im, boost_factor) -> None:
        self._apply_fly_dolly(dt)
        if self._right_mouse:
            fwd = self._forward()
            right = self._right()
            up = Vec3.up()
            accel = Vec3.zero()
            speed = self._move_speed * boost_factor
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
                accel = accel + up * speed
            if im.is_key_pressed(KEY_Q):
                accel = accel - up * speed
            facc = dt * self._acceleration
            self._vel = self._vel + (accel - self._vel) * min(facc, 1.0)
            self._position = self._position + self._vel * dt
        else:
            accel = Vec3.zero()
            self._vel = self._vel * 0.85
            self._position = self._position + self._vel * dt


__all__ = ["FlyMixin"]
