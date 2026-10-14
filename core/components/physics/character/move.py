# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from typing import Optional
from core.ecs import Component
from core.maths.math3d import Vec3, Quat
from core.input.inpsys import Input, KeyCode

try:
    import culverin
    from culverin import Character as CulverinCharacter
    _HAS_CULVERIN = True
except Exception:
    culverin = None
    CulverinCharacter = None
    _HAS_CULVERIN = False


def _quat_yaw(yaw_deg: float) -> Quat:
    a = math.radians(yaw_deg) * 0.5
    return Quat(0.0, math.sin(a), 0.0, math.cos(a))


def _quat_pitch_yaw(pitch_deg: float, yaw_deg: float) -> Quat:
    px = math.radians(pitch_deg) * 0.5
    py = math.radians(yaw_deg) * 0.5
    sp, cp = math.sin(px), math.cos(px)
    sy, cy = math.sin(py), math.cos(py)
    return Quat(sp * sy, cp * sy, -sp * cy, cp * cy)


def _get_physics_plugin():
    from core.engine.eng import Engine
    engine = Engine.instance()
    if engine is None:
        return None
    try:
        return engine.plugin_manager.get("PhysicsPlugin")
    except Exception:
        return None


def _resolve_solver():
    plugin = _get_physics_plugin()
    if plugin is None:
        return None
    solver = getattr(plugin, "_solver", None)
    if solver is not None and getattr(solver, "_world", None) is not None:
        return solver
    return None


class CharacterMoveBase(Component):
    _icon = "CharacterController.png"
    _gizmo_icon_color = (100, 180, 255)
    _gizmo_icon_label = "CC"
    _show_gizmo_icon: bool = False

    def __init__(self):
        super().__init__()
        self.walk_speed: float = 260.0
        self.run_speed: float = 440.0
        self.crouch_speed: float = 130.0
        self.acceleration: float = 10.0
        self.air_acceleration: float = 10.0
        self.friction: float = 4.0
        self.stop_speed: float = 80.0
        self.jump_power: float = 300.0
        self.jump_buffer_time: float = 0.1
        self.coyote_time: float = 0.1
        self.crouch_toggle: bool = True
        self.crouch_speed_mult: float = 0.5
        self.crouch_eye_offset: float = 0.6
        self.sensitivity: float = 5.0
        self.sensitivity_x: float = 5.0
        self.sensitivity_y: float = 5.0
        self.invert_x: bool = False
        self.invert_y: bool = False
        self.mouse_smoothing: float = 0.0
        self.smoothing_strength: float = 18.0
        self.cursor_lock_on_start: bool = True
        self.unlock_key: int = KeyCode.ESCAPE
        self.camera_fov: float = 60.0
        self.camera_near: float = 0.05
        self.camera_far: float = 1000.0
        self.scroll_zoom: bool = True
        self.min_fov: float = 20.0
        self.max_fov: float = 90.0
        self.aim_fov: float = 45.0
        self.aim_zoom_speed: float = 12.0
        self.gravity: float = 800.0
        self.capsule_radius: float = 0.5
        self.capsule_height: float = 2.0
        self.crouch_height: float = 1.2
        self.step_height: float = 0.3
        self.max_slope: float = 45.0
        self.push_strength: float = 30.0
        self._solver = None
        self._character: Optional["CulverinCharacter"] = None
        self._ai_wish_dir: Optional[Vec3] = None
        self._ai_wish_speed: Optional[float] = None
        self._fixed_update_count: int = 0
        self._velocity: Vec3 = Vec3.zero()
        self._pitch: float = 0.0
        self._yaw: float = 0.0
        self._target_pitch: float = 0.0
        self._target_yaw: float = 0.0
        self._is_crouching: bool = False
        self._wants_to_crouch: bool = False
        self._grounded: bool = False
        self._coyote_timer: float = 0.0
        self._jump_buffer_timer: float = 0.0
        self._eye_height: float = 1.7
        self._target_eye_height: float = 1.7
        self._camera_entity_id: Optional[str] = None
        self._current_fov: float = 60.0
        self._warned_no_world: bool = False
        self._cursor_locked: bool = False

    @property
    def velocity(self) -> Vec3:
        return self._velocity

    @property
    def is_grounded(self) -> bool:
        return self._grounded

    @property
    def is_crouching(self) -> bool:
        return self._is_crouching

    @property
    def camera_entity_id(self) -> str:
        return self._camera_entity_id or ""

    @camera_entity_id.setter
    def camera_entity_id(self, v: str):
        self._camera_entity_id = v or ""

    def set_ai_drive(self, wish_dir: Optional[Vec3], speed: float = 0.0):
        if wish_dir is None:
            self._ai_wish_dir = None
            self._ai_wish_speed = None
            return
        try:
            length = wish_dir.length()
        except Exception:
            return
        if length < 1e-6:
            self._ai_wish_dir = None
            self._ai_wish_speed = None
            return
        self._ai_wish_dir = wish_dir * (1.0 / length)
        self._ai_wish_speed = max(0.0, float(speed))

    @property
    def ai_driving(self) -> bool:
        return (self._ai_wish_dir is not None and self._ai_wish_speed is not None
                and self._ai_wish_speed > 0.0)

    @property
    def fixed_update_count(self) -> int:
        return self._fixed_update_count

    def get_move_speed(self) -> float:
        if self.ai_driving:
            return float(self._ai_wish_speed)
        if self._is_crouching:
            return self.crouch_speed * self.crouch_speed_mult
        if Input.GetKey(KeyCode.LEFT_SHIFT) or Input.GetKey(KeyCode.RIGHT_SHIFT):
            return self.run_speed
        return self.walk_speed

    def get_wish_dir(self) -> Vec3:
        if self.ai_driving:
            flat = Vec3(self._ai_wish_dir.x, 0.0, self._ai_wish_dir.z)
            if flat.length_sq() > 1e-8:
                return flat.normalized()
            return Vec3.zero()
        fwd = self.transform.forward if self.transform else Vec3.forward()
        right = self.transform.right if self.transform else Vec3.right()
        fwd.y = 0.0
        right.y = 0.0
        fwd = fwd.normalized()
        right = right.normalized()
        move_x = 0.0
        move_z = 0.0
        if Input.GetKey(KeyCode.W): move_z += 1.0
        if Input.GetKey(KeyCode.S): move_z -= 1.0
        if Input.GetKey(KeyCode.A): move_x -= 1.0
        if Input.GetKey(KeyCode.D): move_x += 1.0
        wish = (fwd * move_z + right * move_x)
        if wish.length_sq() > 0.001:
            wish = wish.normalized()
        return wish

    def _accelerate(self, wish_dir: Vec3, wish_speed: float, accel: float, dt: float):
        vel = self._velocity
        cur_speed = vel.dot(wish_dir)
        add = wish_speed - cur_speed
        if add <= 0:
            return
        add = min(add, accel * dt * wish_speed)
        self._velocity = vel + wish_dir * add

    def _apply_friction(self, dt: float):
        vel = self._velocity
        speed = vel.length()
        if speed < 0.001:
            self._velocity = Vec3.zero()
            return
        control = self.stop_speed if speed < self.stop_speed else speed
        drop = control * self.friction * dt
        new_speed = max(0.0, speed - drop) / speed
        self._velocity = vel * new_speed

    def _update_crouch(self):
        if self._is_crouching:
            self._target_eye_height = self.crouch_eye_offset
        else:
            self._target_eye_height = self.capsule_height - 0.3
        diff = self._target_eye_height - self._eye_height
        self._eye_height += diff * min(1.0, 10.0 * 0.016)

    def _find_camera(self):
        from core.engine.eng import Engine
        engine = Engine.instance()
        if not engine or not engine._scene:
            return
        from core.components.rendering.cameras.camera import Camera
        for ent in engine._scene.get_entities_with_component(Camera):
            if ent.active:
                self._camera_entity_id = ent.id
                return

    def _set_cursor_locked(self, locked: bool):
        if locked == self._cursor_locked:
            return
        self._cursor_locked = locked
        Input.set_cursor_locked(locked)
        Input.set_cursor_visible(not locked)

    def _handle_mouse_look(self, dt: float):
        if not self._entity:
            return
        dx, dy = Input.mouseDelta
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return
        sx = self.sensitivity_x if self.sensitivity_x > 0.0 else self.sensitivity
        sy = self.sensitivity_y if self.sensitivity_y > 0.0 else self.sensitivity
        yaw_speed = sx * 0.022
        pitch_speed = sy * 0.022
        self._target_yaw -= dx * yaw_speed
        if self.invert_x:
            self._target_yaw = -self._target_yaw
        pitch_delta = dy * pitch_speed
        if self.invert_y:
            pitch_delta = -pitch_delta
        self._target_pitch -= pitch_delta
        self._target_pitch = max(-89.0, min(89.0, self._target_pitch))
        smoothing = self.mouse_smoothing
        if smoothing <= 0.0:
            self._yaw = self._target_yaw
            self._pitch = self._target_pitch
        else:
            k = min(1.0, self.smoothing_strength * dt)
            self._yaw += (self._target_yaw - self._yaw) * k
            self._pitch += (self._target_pitch - self._pitch) * k
        tr = self.transform
        if tr:
            tr.local_rotation = _quat_yaw(self._yaw)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "walk_speed": self.walk_speed, "run_speed": self.run_speed,
            "crouch_speed": self.crouch_speed, "acceleration": self.acceleration,
            "air_acceleration": self.air_acceleration, "friction": self.friction,
            "stop_speed": self.stop_speed, "jump_power": self.jump_power,
            "jump_buffer_time": self.jump_buffer_time, "coyote_time": self.coyote_time,
            "crouch_toggle": self.crouch_toggle, "crouch_speed_mult": self.crouch_speed_mult,
            "crouch_eye_offset": self.crouch_eye_offset, "sensitivity": self.sensitivity,
            "sensitivity_x": self.sensitivity_x, "sensitivity_y": self.sensitivity_y,
            "invert_x": self.invert_x, "invert_y": self.invert_y,
            "mouse_smoothing": self.mouse_smoothing, "smoothing_strength": self.smoothing_strength,
            "cursor_lock_on_start": self.cursor_lock_on_start, "unlock_key": self.unlock_key,
            "camera_fov": self.camera_fov, "camera_near": self.camera_near, "camera_far": self.camera_far,
            "scroll_zoom": self.scroll_zoom, "min_fov": self.min_fov, "max_fov": self.max_fov,
            "aim_fov": self.aim_fov, "aim_zoom_speed": self.aim_zoom_speed,
            "gravity": self.gravity,
            "capsule_radius": self.capsule_radius, "capsule_height": self.capsule_height,
            "crouch_height": self.crouch_height, "step_height": self.step_height,
            "max_slope": self.max_slope, "push_strength": self.push_strength,
        })
        return d
