# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from typing import Optional
from core.maths.math3d import Vec3, Mat4
from core.input.input_manager import InputManager
from core.input.constants import KEY_W, KEY_A, KEY_S, KEY_D, KEY_Q, KEY_E, KEY_SHIFT, KEY_CTRL, MOUSE_R, MOUSE_M, MOUSE_L
from core.components.rendering.cameras.camera_base import CameraBase
from editor.cam.orbit import OrbitMixin
from editor.cam.fly import FlyMixin


class SceneCamera(OrbitMixin, FlyMixin, CameraBase):
    NAV_FLY = "fly"
    NAV_ORBIT = "orbit"
    ORBIT_MIN_DIST = 0.1
    ORBIT_MAX_DIST = 1000.0
    PERSPECTIVE_TO_ORTHO_FOV = 179.0
    TRANSITION_SPEED = 2.5
    MOVE_SPEED = 5.0
    FAST_MULT = 3.0
    ROTATE_SPEED = 0.3
    ZOOM_SPEED = 4.0
    PAN_SPEED = 0.01
    DAMPING = 8.0
    ACCEL = 12.0
    ZOOM_SMOOTH_SPEED = 15.0
    SPEED_BOOST_MULT = 3.0
    SPEED_BOOST_RAMP_TIME = 2.0

    def __init__(self):
        super().__init__()
        self._position: Vec3 = Vec3(0.0, 3.0, 10.0)
        self._yaw: float = 0.0
        self._pitch: float = -15.0
        self._move_speed: float = self.MOVE_SPEED
        self._fast_mult: float = self.FAST_MULT
        self._rotate_speed: float = self.ROTATE_SPEED
        self._zoom_speed: float = self.ZOOM_SPEED
        self._pan_speed: float = self.PAN_SPEED
        self._damping: float = self.DAMPING
        self._acceleration: float = self.ACCEL
        self._transition_speed: float = self.TRANSITION_SPEED
        self._zoom_smooth_speed: float = self.ZOOM_SMOOTH_SPEED
        self._zoom_strength: float = 0.3
        self._use_ortho_in_2d: bool = True
        self._right_mouse: bool = False
        self._middle_mouse: bool = False
        self._alt_left: bool = False
        self._last_mx: int = 0
        self._last_my: int = 0
        self._vel: Vec3 = Vec3.zero()
        self._orbit_target: Vec3 = Vec3.zero()
        self._orbit_dist: float = 10.0
        self._orbit_dist_target: float = 10.0
        self._orbiting: bool = False
        self._nav_mode: str = self.NAV_FLY
        self._fly_dolly_remaining: float = 0.0
        self._on_nav_mode_changed = None
        self._transition_blend: float = 0.0
        self._transition_active: bool = False
        self._transition_to_ortho: bool = False
        self._ortho_zoom_distance: float = 0.0
        self._stored_ortho_size: float = 5.0
        self._is_2d_mode: bool = False
        self._mode_2d_transition: bool = False
        self._mode_2d_blend: float = 0.0
        self._mode_2d_to_2d: bool = False
        self._stored_yaw: float = 0.0
        self._stored_pitch: float = -15.0
        self._stored_fov: float = self.DEFAULT_FOV
        self._stored_ortho: bool = False
        self._viewport_w: int = 800
        self._viewport_h: int = 600
        self._zoom_target_distance: float = 0.0
        self._zoom_cursor_ndc: Optional[tuple[float, float]] = None
        self._on_2d_mode_changed = None
        self._release_damping: float = 1.0
        self._focus_transition_blend: float = 1.0
        self._focus_start_pos: Vec3 = self._position
        self._focus_target_pos: Vec3 = self._position
        self._focus_start_orbit: Vec3 = self._orbit_target
        self._focus_target_orbit: Vec3 = self._orbit_target
        self._focus_start_yaw: float = self._yaw
        self._focus_start_pitch: float = self._pitch
        self._focus_target_yaw: float = self._yaw
        self._focus_target_pitch: float = self._pitch
        self._focus_active: bool = False
        self._scroll_accumulator: float = 0.0
        self._speed_boost_time: float = 0.0
        self._speed_boost_enabled: bool = True
        self._speed_boost_mult: float = self.SPEED_BOOST_MULT
        self._speed_boost_ramp_time: float = self.SPEED_BOOST_RAMP_TIME

    def load_config(self, config) -> None:
        self._fov = config.get("camera.fov", self.DEFAULT_FOV)
        self._near = config.get("camera.near", self.DEFAULT_NEAR)
        self._far = config.get("camera.far", self.DEFAULT_FAR)
        self._move_speed = config.get("camera.move_speed", self.MOVE_SPEED)
        self._fast_mult = config.get("camera.fast_mult", self.FAST_MULT)
        self._rotate_speed = config.get("camera.rotate_speed", self.ROTATE_SPEED)
        self._zoom_speed = config.get("camera.zoom_speed", self.ZOOM_SPEED)
        self._pan_speed = config.get("camera.pan_speed", self.PAN_SPEED)
        self._damping = config.get("camera.damping", self.DAMPING)
        self._acceleration = config.get("camera.acceleration", self.ACCEL)
        self._transition_speed = config.get("camera.transition_speed", self.TRANSITION_SPEED)
        self._zoom_smooth_speed = config.get("camera.zoom_smooth_speed", self.ZOOM_SMOOTH_SPEED)
        self._zoom_strength = config.get("camera.zoom_strength", 0.3)
        self._use_ortho_in_2d = config.get("camera.use_ortho_in_2d", True)
        self._speed_boost_enabled = config.get("camera.speed_boost_enabled", True)
        self._speed_boost_mult = config.get("camera.speed_boost_mult", self.SPEED_BOOST_MULT)
        self._speed_boost_ramp_time = config.get("camera.speed_boost_ramp_time", self.SPEED_BOOST_RAMP_TIME)
        self._render_scale = float(config.get("camera.render_scale", 1.0))
        self._resolution_mode = config.get("camera.resolution_mode", "native")
        self._resolution_w = int(config.get("camera.resolution_w", 1920))
        self._resolution_h = int(config.get("camera.resolution_h", 1080))
        nav = config.get("camera.nav_mode", self._nav_mode)
        if nav in (self.NAV_FLY, self.NAV_ORBIT):
            self._nav_mode = nav

    @property
    def forward(self) -> Vec3:
        return self._forward()

    @property
    def position(self) -> Vec3:
        return self._position

    @property
    def yaw(self) -> float:
        return self._yaw

    @property
    def pitch(self) -> float:
        return self._pitch

    @property
    def is_2d_mode(self) -> bool:
        return self._is_2d_mode

    @property
    def nav_mode(self) -> str:
        return self._nav_mode

    @property
    def is_orbit_mode(self) -> bool:
        return self._nav_mode == self.NAV_ORBIT

    @property
    def cursor(self) -> Vec3:
        return self._orbit_target

    def _forward(self) -> Vec3:
        if self._is_2d_mode:
            return Vec3(0.0, 0.0, -1.0)
        pr = math.radians(self._pitch)
        yr = math.radians(self._yaw)
        return Vec3(
            -math.cos(pr) * math.sin(yr),
            -math.sin(pr),
            -math.cos(pr) * math.cos(yr)
        ).normalized()

    def _right(self) -> Vec3:
        if self._is_2d_mode:
            return Vec3(1.0, 0.0, 0.0)
        return self._forward().cross(Vec3.up()).normalized()

    def _up(self) -> Vec3:
        if self._is_2d_mode:
            return Vec3(0.0, 1.0, 0.0)
        return self._right().cross(self._forward()).normalized()

    def get_view_matrix(self) -> Mat4:
        if self._focus_active or self._nav_mode == self.NAV_ORBIT:
            return Mat4.look_at(self._position, self._orbit_target, Vec3.up())
        return Mat4.look_at(self._position, self._position + self._forward(), Vec3.up())

    def on_mouse_press(self, btn, x, y, alt_pressed=False):
        self._focus_active = False
        self._focus_transition_blend = 1.0
        if btn == MOUSE_R:
            self._right_mouse = True
        elif btn == MOUSE_M:
            self._middle_mouse = True
        elif btn == MOUSE_L and alt_pressed:
            self._alt_left = True
        self._last_mx = x
        self._last_my = y

    def on_mouse_release(self, btn):
        if btn == MOUSE_R:
            self._right_mouse = False
            self._release_damping = 0.95
        elif btn == MOUSE_M:
            self._middle_mouse = False
        elif btn == MOUSE_L:
            self._alt_left = False

    def set_viewport_size(self, w: int, h: int):
        self._viewport_w = w
        self._viewport_h = h

    @staticmethod
    def _ease_in_out_cubic(t: float) -> float:
        if t < 0.5:
            return 4.0 * t * t * t
        else:
            return 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0

    def _lerp_angle(self, a, b, t):
        diff = (b - a) % 360.0
        if diff > 180.0:
            diff -= 360.0
        return a + diff * t

    def _is_shift_down(self) -> bool:
        try:
            return bool(InputManager.instance().is_key_pressed(KEY_SHIFT))
        except Exception:
            return False

    def _is_ctrl_down(self) -> bool:
        try:
            return bool(InputManager.instance().is_key_pressed(KEY_CTRL))
        except Exception:
            return False

    def on_mouse_move(self, x, y):
        dx = float(x - self._last_mx)
        dy = float(y - self._last_my)
        self._last_mx = x
        self._last_my = y
        if dx != 0 or dy != 0:
            self._focus_active = False
            self._focus_transition_blend = 1.0
        if self._is_2d_mode and (self._right_mouse or self._middle_mouse):
            self._pan_2d(dx, dy)
            return
        if self._nav_mode == self.NAV_ORBIT and not self._is_2d_mode:
            self._orbit_mouse_move(dx, dy)
            return
        self._fly_mouse_move(dx, dy)

    def on_scroll(self, delta, cursor_x=None, cursor_y=None):
        self._focus_active = False
        self._focus_transition_blend = 1.0
        self._scroll_accumulator += delta * 0.1
        accel = max(1.0, pow(1.05, abs(self._scroll_accumulator)) - 1.0)
        scaled_delta = delta * (1.0 + accel)
        if self._is_orthographic or (self._is_2d_mode and self._use_ortho_in_2d):
            self._scroll_ortho_step(scaled_delta, cursor_x, cursor_y)
            return
        if self._is_2d_mode:
            forward = self._forward()
            self._position = self._position + forward * scaled_delta * self._zoom_speed
            return
        if self._nav_mode == self.NAV_ORBIT:
            self._orbit_scroll_step(scaled_delta)
            return
        self._fly_scroll_step(scaled_delta)

    def update(self, dt):
        self._update_projection_transition(dt)
        self._update_mode_2d(dt)
        self._update_focus_blend(dt)
        self._update_ortho_zoom(dt)
        try:
            decay = 1.0 - min(1.0, dt * 4.0)
            if decay < 0.0:
                decay = 0.0
            self._scroll_accumulator = self._scroll_accumulator * decay
            if abs(self._scroll_accumulator) < 0.001:
                self._scroll_accumulator = 0.0
        except Exception:
            pass
        if dt > 0.05:
            dt = 0.05
        im = InputManager.instance()
        any_move = im.is_key_pressed(KEY_W) or im.is_key_pressed(KEY_A) or im.is_key_pressed(KEY_S) or im.is_key_pressed(KEY_D) or im.is_key_pressed(KEY_Q) or im.is_key_pressed(KEY_E)
        if any_move or im.is_key_pressed(KEY_SHIFT):
            self._focus_active = False
            self._focus_transition_blend = 1.0
        if self._speed_boost_enabled and any_move:
            self._speed_boost_time += dt
        elif not any_move:
            self._speed_boost_time = 0.0
        if self._speed_boost_enabled:
            boost_t = min(self._speed_boost_time / max(self._speed_boost_ramp_time, 0.001), 1.0)
            boost_factor = 1.0 + (self._speed_boost_mult - 1.0) * boost_t
        else:
            boost_factor = 1.0
        if self._is_2d_mode:
            self._update_2d_move(dt, im, boost_factor)
            return
        if self._nav_mode == self.NAV_ORBIT:
            self._orbit_update_move(dt, im, boost_factor, any_move)
            return
        self._update_fly_move(dt, im, boost_factor)

    def serialize(self) -> dict:
        d = self.serialize_base()
        d.update({
            "position": self._position.to_list(),
            "yaw": self._yaw,
            "pitch": self._pitch,
            "nav_mode": self._nav_mode,
            "orbit_target": self._orbit_target.to_list(),
            "orbit_dist": self._orbit_dist,
            "orbit_dist_target": self._orbit_dist_target,
        })
        return d

    def deserialize(self, data: dict):
        self.deserialize_base(data)
        p = data.get("position", [0, 3, 10])
        self._position = Vec3(*p)
        self._yaw = data.get("yaw", 0.0)
        self._pitch = data.get("pitch", -15.0)
        nav = data.get("nav_mode", self.NAV_FLY)
        self._nav_mode = nav if nav in (self.NAV_FLY, self.NAV_ORBIT) else self.NAV_FLY
        try:
            self._orbit_target = Vec3(*data.get("orbit_target", [0, 0, 0]))
        except Exception:
            self._orbit_target = Vec3.zero()
        try:
            self._orbit_dist = float(data.get("orbit_dist", 10.0))
        except Exception:
            self._orbit_dist = 10.0
        try:
            self._orbit_dist_target = float(data.get("orbit_dist_target", self._orbit_dist))
        except Exception:
            self._orbit_dist_target = self._orbit_dist
        self._fly_dolly_remaining = 0.0
        self._vel = Vec3.zero()
        self._focus_active = False
        self._focus_transition_blend = 1.0
        if self._nav_mode == self.NAV_ORBIT:
            self._sync_orbit_dist_from_transform()
            self._apply_orbit_transform()


__all__ = ["SceneCamera"]
