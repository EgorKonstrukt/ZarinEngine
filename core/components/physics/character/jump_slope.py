# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.ecs import ComponentRegistry
from core.maths.math3d import Vec3, Quat
from core.components.inspector_meta import FieldType, InspectorField
from core.input.inpsys import Input, KeyCode
from core.components.physics.character.move import CharacterMoveBase
from core.components.physics.character.move import _quat_yaw
from core.components.physics.character.move import _quat_pitch_yaw
from core.components.physics.character.move import _get_physics_plugin
from core.components.physics.character.move import _resolve_solver
from core.components.physics.character.move import _HAS_CULVERIN


@ComponentRegistry.register
class CharacterController(CharacterMoveBase):
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Movement", FieldType.HEADER),
            InspectorField("walk_speed", "Walk Speed", FieldType.FLOAT, min_val=0.0, max_val=2000.0),
            InspectorField("run_speed", "Run Speed", FieldType.FLOAT, min_val=0.0, max_val=2000.0),
            InspectorField("crouch_speed", "Crouch Speed", FieldType.FLOAT, min_val=0.0, max_val=2000.0),
            InspectorField("acceleration", "Acceleration", FieldType.FLOAT, min_val=0.0, max_val=200.0),
            InspectorField("air_acceleration", "Air Acceleration", FieldType.FLOAT, min_val=0.0, max_val=200.0),
            InspectorField("friction", "Friction", FieldType.FLOAT, min_val=0.0, max_val=20.0),
            InspectorField("stop_speed", "Stop Speed", FieldType.FLOAT, min_val=0.0, max_val=500.0),
            InspectorField("", "Jump", FieldType.HEADER),
            InspectorField("jump_power", "Jump Power", FieldType.FLOAT, min_val=0.0, max_val=2000.0),
            InspectorField("jump_buffer_time", "Jump Buffer", FieldType.FLOAT, min_val=0.0, max_val=1.0),
            InspectorField("coyote_time", "Coyote Time", FieldType.FLOAT, min_val=0.0, max_val=1.0),
            InspectorField("", "Crouch", FieldType.HEADER),
            InspectorField("crouch_toggle", "Crouch Toggle", FieldType.BOOL),
            InspectorField("crouch_speed_mult", "Crouch Speed Mult", FieldType.FLOAT, min_val=0.0, max_val=1.0),
            InspectorField("crouch_eye_offset", "Crouch Eye Offset", FieldType.FLOAT, min_val=0.0, max_val=2.0),
            InspectorField("", "Mouse Look", FieldType.HEADER),
            InspectorField("camera_entity_id", "Camera", FieldType.GAMEOBJECT),
            InspectorField("sensitivity", "Sensitivity", FieldType.FLOAT, min_val=0.0, max_val=50.0),
            InspectorField("sensitivity_x", "Sensitivity X", FieldType.FLOAT, min_val=0.0, max_val=50.0),
            InspectorField("sensitivity_y", "Sensitivity Y", FieldType.FLOAT, min_val=0.0, max_val=50.0),
            InspectorField("invert_x", "Invert X", FieldType.BOOL),
            InspectorField("invert_y", "Invert Y", FieldType.BOOL),
            InspectorField("mouse_smoothing", "Mouse Smoothing", FieldType.FLOAT, min_val=0.0, max_val=1.0),
            InspectorField("smoothing_strength", "Smoothing Strength", FieldType.FLOAT, min_val=0.0, max_val=60.0),
            InspectorField("cursor_lock_on_start", "Lock Cursor On Start", FieldType.BOOL),
            InspectorField("unlock_key", "Unlock Key", FieldType.KEYBINDING),
            InspectorField("", "Camera", FieldType.HEADER),
            InspectorField("camera_fov", "Field of View", FieldType.FLOAT, min_val=1.0, max_val=179.0),
            InspectorField("camera_near", "Near Plane", FieldType.FLOAT, min_val=0.001, max_val=100.0),
            InspectorField("camera_far", "Far Plane", FieldType.FLOAT, min_val=0.1, max_val=100000.0),
            InspectorField("scroll_zoom", "Scroll Zoom", FieldType.BOOL),
            InspectorField("min_fov", "Min FOV (Zoom)", FieldType.FLOAT, min_val=1.0, max_val=179.0),
            InspectorField("max_fov", "Max FOV", FieldType.FLOAT, min_val=1.0, max_val=179.0),
            InspectorField("aim_fov", "Aim FOV", FieldType.FLOAT, min_val=1.0, max_val=179.0),
            InspectorField("aim_zoom_speed", "Aim Zoom Speed", FieldType.FLOAT, min_val=0.0, max_val=30.0),
            InspectorField("", "Physics", FieldType.HEADER),
            InspectorField("gravity", "Gravity", FieldType.FLOAT, min_val=0.0, max_val=5000.0),
            InspectorField("capsule_radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("capsule_height", "Height", FieldType.FLOAT, min_val=0.01, max_val=20.0),
            InspectorField("crouch_height", "Crouch Height", FieldType.FLOAT, min_val=0.01, max_val=20.0),
            InspectorField("step_height", "Step Height", FieldType.FLOAT, min_val=0.0, max_val=2.0),
            InspectorField("max_slope", "Max Slope", FieldType.FLOAT, min_val=0.0, max_val=90.0),
            InspectorField("push_strength", "Push Strength", FieldType.FLOAT, min_val=0.0, max_val=200.0),
        ]

    def resync_character(self) -> bool:
        try:
            if self._solver is not None and self._character is not None:
                try:
                    self._solver.destroy_character(self._character)
                except Exception:
                    pass
                self._character = None
            self._velocity = Vec3.zero()
            tr = self.transform
            if self._solver is None or tr is None:
                return False
            self._character = self._create_character(self._solver, tr.local_position)
            return self._character is not None
        except Exception:
            return False

    def _capsule_total_height(self) -> float:
        return max(self.capsule_radius * 2.0 + 0.1, self.capsule_height)

    def _create_character(self, solver, pos: Vec3):
        total = self._capsule_total_height()
        char = solver.create_character(
            (pos.x, pos.y, pos.z),
            height=total,
            radius=self.capsule_radius,
            step_height=self.step_height,
            max_slope=self.max_slope,
        )
        if char is not None:
            solver.set_character_rotation(char, _quat_yaw(self._yaw).to_list())
            solver.set_character_strength(char, self.push_strength)
        return char

    def on_start(self):
        self._solver = None
        self._character = None
        self._fixed_update_count = 0
        self._velocity = Vec3.zero()
        self._pitch = 0.0
        self._yaw = 0.0
        self._target_pitch = 0.0
        self._target_yaw = 0.0
        self._is_crouching = False
        self._wants_to_crouch = False
        self._grounded = False
        self._coyote_timer = 0.0
        self._jump_buffer_timer = 0.0
        self._camera_entity_id = None
        self._warned_no_world = False
        self._cursor_locked = False
        self._current_fov = self.camera_fov
        self._eye_height = self.capsule_height - 0.3
        self._target_eye_height = self._eye_height
        if self.camera_entity_id:
            self._camera_entity_id = self.camera_entity_id
        if not _HAS_CULVERIN:
            return
        self._solver = _resolve_solver()
        if self._solver is None:
            plugin = _get_physics_plugin()
            if plugin is not None and plugin.ensure_single_mode():
                self._solver = _resolve_solver()
        if self._solver is None:
            return
        tr = self.transform
        start = tr.local_position if tr else Vec3.zero()
        self._character = self._create_character(self._solver, start)
        if tr and self._character is not None:
            tr.local_rotation = _quat_yaw(self._yaw)
        if self.cursor_lock_on_start:
            self._set_cursor_locked(True)

    def on_disable(self):
        self._set_cursor_locked(False)
        if self._solver is not None and self._character is not None:
            self._solver.destroy_character(self._character)
            self._character = None

    def on_update(self, dt: float):
        if not self._entity or not self.enabled:
            return
        if Input.GetKeyDown(self.unlock_key):
            self._set_cursor_locked(not self._cursor_locked)
        self._handle_mouse_look(dt)
        self._update_crouch()
        if self._camera_entity_id is None:
            self._find_camera()
        self._update_camera(dt)

    def on_fixed_update(self, dt: float):
        if not self._entity or not self.enabled:
            return
        self._fixed_update_count += 1
        char = self._character
        if char is None or self._solver is None:
            if self._solver is None:
                self._solver = _resolve_solver()
                if self._solver is None:
                    plugin = _get_physics_plugin()
                    if plugin is not None and plugin.ensure_single_mode():
                        self._solver = _resolve_solver()
            if self._solver is not None and self.transform is not None:
                self._character = self._create_character(self._solver, self.transform.local_position)
                if self.transform:
                    self.transform.local_rotation = _quat_yaw(self._yaw)
            if self._character is None:
                if not self._warned_no_world:
                    from core.foundation.logger import Logger
                    Logger.warning(
                        "CharacterController: physics world is not available in-process. "
                        "Use single-threaded physics mode (simulation_mode='single') for characters."
                    )
                    self._warned_no_world = True
                return
            char = self._character
        tr = self.transform
        if not tr:
            return
        self._grounded = self._solver.is_character_grounded(char)
        if self._grounded:
            self._coyote_timer = self.coyote_time
        else:
            self._coyote_timer -= dt
        if not self.ai_driving and Input.GetKeyDown(KeyCode.SPACE):
            self._jump_buffer_timer = self.jump_buffer_time
        else:
            self._jump_buffer_timer -= dt
        if not self.ai_driving and Input.GetKeyDown(KeyCode.C):
            self._wants_to_crouch = not self._wants_to_crouch
            if self.crouch_toggle:
                self._is_crouching = self._wants_to_crouch
            else:
                self._is_crouching = not self._is_crouching
        if not self.crouch_toggle and not self.ai_driving:
            self._is_crouching = Input.GetKey(KeyCode.C)
        can_jump = self._jump_buffer_timer > 0.0 and self._coyote_timer > 0.0
        if can_jump:
            vel = self._velocity
            self._velocity = Vec3(vel.x, self.jump_power, vel.z)
            self._jump_buffer_timer = 0.0
            self._coyote_timer = 0.0
        vel = self._velocity
        if self._grounded:
            self._accelerate(self.get_wish_dir(), self.get_move_speed(), self.acceleration, dt)
            self._apply_friction(dt)
            vel = self._velocity
            if vel.y < 0.0:
                vel = Vec3(vel.x, 0.0, vel.z)
            self._velocity = vel
        else:
            self._velocity = Vec3(vel.x, vel.y - self.gravity * dt, vel.z)
            self._accelerate(self.get_wish_dir(), self.get_move_speed(), self.air_acceleration, dt)
            vel = self._velocity
        self._solver.move_character(char, (vel.x, vel.y, vel.z), dt)
        pos = self._solver.get_character_position(char)
        if pos is not None:
            tr.local_position = Vec3(pos[0], pos[1], pos[2])
        self._solver.set_character_rotation(char, _quat_yaw(self._yaw).to_list())

    def _update_camera(self, dt: float):
        if self._camera_entity_id is None:
            return
        from core.engine.eng import Engine
        engine = Engine.instance()
        if not engine or not engine._scene:
            return
        cam_ent = engine._scene.get_entity(self._camera_entity_id)
        if not cam_ent or not cam_ent.active:
            self._camera_entity_id = None
            return
        cam_tr = cam_ent.transform
        player_tr = self.transform
        if not cam_tr or not player_tr:
            return
        cam_comp = cam_ent.get_component(_CAMERA_TYPE) if (_CAMERA_TYPE is not None) else None
        if cam_comp is not None:
            self._apply_camera_settings(cam_comp, dt)
        cam_is_child = cam_tr._entity.parent is self._entity if cam_tr._entity else False
        if cam_is_child:
            cam_tr.local_position = Vec3(0, self._eye_height, 0)
            px = math.radians(self._pitch) * 0.5
            cam_tr.local_rotation = Quat(math.sin(px), 0.0, 0.0, math.cos(px))
        else:
            cam_tr.local_position = player_tr.local_position + Vec3(0, self._eye_height, 0)
            cam_tr.local_rotation = _quat_pitch_yaw(self._pitch, self._yaw)

    def _apply_camera_settings(self, cam_comp, dt: float):
        scroll = Input.mouseScrollDelta
        if self.scroll_zoom and scroll is not None:
            self._current_fov -= scroll[1] * 2.0
            self._current_fov = max(self.min_fov, min(self.max_fov, self._current_fov))
        aiming = Input.GetKey(KeyCode.MOUSE_RIGHT)
        target_fov = self.aim_fov if aiming else self.camera_fov
        rate = min(1.0, self.aim_zoom_speed * dt)
        self._current_fov += (target_fov - self._current_fov) * rate
        self._current_fov = max(1.0, min(179.0, self._current_fov))
        cam_comp.fov = self._current_fov
        cam_comp.near = self.camera_near
        cam_comp.far = self.camera_far

    @classmethod
    def deserialize(cls, data: dict) -> CharacterController:
        cc = cls()
        cc.enabled = data.get("enabled", True)
        for key in ("walk_speed", "run_speed", "crouch_speed", "acceleration",
                     "air_acceleration", "friction", "stop_speed", "jump_power",
                     "jump_buffer_time", "coyote_time", "crouch_speed_mult",
                     "crouch_eye_offset", "sensitivity", "sensitivity_x", "sensitivity_y",
                     "camera_near", "camera_far", "min_fov", "max_fov",
                     "aim_fov", "aim_zoom_speed", "gravity",
                     "capsule_radius", "capsule_height", "crouch_height",
                     "step_height", "max_slope", "push_strength", "smoothing_strength"):
            setattr(cc, key, data.get(key, getattr(cc, key)))
        for bkey in ("crouch_toggle", "invert_x", "invert_y", "scroll_zoom",
                     "cursor_lock_on_start"):
            setattr(cc, bkey, data.get(bkey, getattr(cc, bkey)))
        cc.camera_fov = data.get("camera_fov", cc.camera_fov)
        cc.mouse_smoothing = data.get("mouse_smoothing", cc.mouse_smoothing)
        cc.unlock_key = data.get("unlock_key", cc.unlock_key)
        cc.camera_entity_id = data.get("camera_entity_id", "")
        return cc


_CAMERA_TYPE = None
def _load_camera_type():
    global _CAMERA_TYPE
    if _CAMERA_TYPE is not None:
        return _CAMERA_TYPE
    try:
        from core.components.rendering.cameras.camera import Camera
        _CAMERA_TYPE = Camera
    except Exception:
        _CAMERA_TYPE = None
    return _CAMERA_TYPE
_load_camera_type()
