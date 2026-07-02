# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.ecs import Component, ComponentRegistry
from core.math3d import Vec3, Vec2
from core.components.inspector_meta import FieldType, InspectorField, ComponentInspectorMeta
from core.input_system import Input, KeyCode


# Р‘Р›РЇР”РЎРљРР™ CharacterController: РќР• РРЎРџРћР›Р¬Р—РЈР•Рў Р¤РР—РР§Р•РЎРљРР™ РЎРћР›Р’Р•Р  Р’РћРћР‘Р©Р•.
# Р’СЃС‘ РЅР°С…СѓР№ СЂСѓС‡РЅРѕРµ: position += vel * dt, ground check С‡РµСЂРµР· Р±СЂСѓС‚С„РѕСЂСЃ РІСЃРµС… СЌРЅС‚РёС‚Рё,
# РїСЂРѕРІРµСЂСЏРµС‚ РўРћР›Р¬РљРћ BoxCollider (СЃС„РµСЂС‹, РєР°РїСЃСѓР»С‹, РјРµС€Рё вЂ” РїРѕС…СѓР№).
# РЎРєРѕР»СЊР¶РµРЅРёСЏ РІРґРѕР»СЊ СЃС‚РµРЅ РЅРµС‚, step-up/down РЅРµ СЂР°Р±РѕС‚Р°РµС‚ (РїР°СЂР°РјРµС‚СЂС‹ РµСЃС‚СЊ вЂ” РїРѕС…СѓР№).
# Р”РІР°Р¶РґС‹ РєРѕРїРёРїР°СЃС‚РЅСѓС‚С‹Р№ ray-AABB Р°Р»РіРѕСЂРёС‚Рј (РѕС‚Р»РёС‡РёР№ РЅРѕР»СЊ).
# Engine.instance() РІРЅСѓС‚СЂРё С†РёРєР»Р° вЂ” РєСЂР°СЃРѕС‚Р°.
# РљС‚Рѕ СЌС‚Рѕ РїРёСЃР°Р» вЂ” СЂСѓРєРё РѕС‚РѕСЂРІР°С‚СЊ.
@ComponentRegistry.register
class CharacterController(Component):
    _icon = "CharacterController.png"
    _gizmo_icon_color = (100, 180, 255)
    _gizmo_icon_label = "CC"
    _show_gizmo_icon: bool = False

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
            InspectorField("sensitivity", "Mouse Sensitivity", FieldType.FLOAT, min_val=0.0, max_val=50.0),
            InspectorField("invert_y", "Invert Y", FieldType.BOOL),
            InspectorField("", "Physics", FieldType.HEADER),
            InspectorField("gravity", "Gravity", FieldType.FLOAT, min_val=0.0, max_val=5000.0),
            InspectorField("capsule_radius", "Radius", FieldType.FLOAT, min_val=0.01, max_val=10.0),
            InspectorField("capsule_height", "Height", FieldType.FLOAT, min_val=0.01, max_val=20.0),
            InspectorField("crouch_height", "Crouch Height", FieldType.FLOAT, min_val=0.01, max_val=20.0),
            InspectorField("step_up", "Step Up", FieldType.FLOAT, min_val=0.0, max_val=2.0),
            InspectorField("step_down", "Step Down", FieldType.FLOAT, min_val=0.0, max_val=10.0),
            InspectorField("ground_check_dist", "Ground Check", FieldType.FLOAT, min_val=0.001, max_val=2.0),
        ]

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
        self.invert_y: bool = False
        self.camera_entity_id: str = ""

        self.gravity: float = 800.0
        self.capsule_radius: float = 0.5
        self.capsule_height: float = 2.0
        self.crouch_height: float = 1.2
        self.step_up: float = 0.3
        self.step_down: float = 1.0
        self.ground_check_dist: float = 0.03

        self._rigidbody: Component | None = None
        self._velocity: Vec3 = Vec3.zero()
        self._pitch: float = 0.0
        self._yaw: float = 0.0
        self._is_crouching: bool = False
        self._wants_to_crouch: bool = False
        self._grounded: bool = False
        self._ground_normal: Vec3 = Vec3.up()
        self._coyote_timer: float = 0.0
        self._jump_buffer_timer: float = 0.0
        self._was_grounded: bool = False
        self._eye_height: float = 1.7
        self._target_eye_height: float = 1.7
        self._air_time: float = 0.0
        self._last_frame_speed: float = 0.0
        self._camera_entity_id: int | None = None
        self._ground_y: float = 0.0

    @property
    def velocity(self) -> Vec3:
        if self._rigidbody is not None:
            return self._rigidbody.velocity
        return self._velocity

    @velocity.setter
    def velocity(self, v: Vec3):
        if self._rigidbody is not None:
            self._rigidbody.velocity = v
        else:
            self._velocity = v

    @property
    def is_grounded(self) -> bool:
        return self._grounded

    @property
    def is_crouching(self) -> bool:
        return self._is_crouching

    def get_move_speed(self) -> float:
        if self._is_crouching:
            return self.crouch_speed * self.crouch_speed_mult
        if Input.GetKey(KeyCode.LEFT_SHIFT) or Input.GetKey(KeyCode.RIGHT_SHIFT):
            return self.run_speed
        return self.walk_speed

    def get_wish_dir(self) -> Vec3:
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

    # Р•Р‘РђРќР«Р™ Р‘Р РЈРўР¤РћР РЎ: Р±РµР¶РёС‚ РїРѕ Р’РЎР•Рњ Entity СЃС†РµРЅС‹.
    # РџСЂРѕРІРµСЂСЏРµС‚ РўРћР›Р¬РљРћ BoxCollider вЂ” СЃС„РµСЂР°/РєР°РїСЃСѓР»Р°/РјРµС€ РџРћР¤РР“РЈ.
    # Р’РЅСѓС‚СЂРё Р»СѓРїР° РґС‘СЂРіР°РµС‚ Engine.instance() РєР°Р¶РґС‹Р№ РєР°РґСЂ.
    # РЎ 1000+ РѕР±СЉРµРєС‚Р°РјРё СЌС‚Рѕ РїСЂРѕСЃС‚Рѕ floor(1/fps) СЃРµРєСѓРЅРґ РІ Р¶РѕРїРµ.
    # РќРµС‚ spatial hash, РЅРµС‚ broadphase, РЅРµС‚ cached Р±Р»РёР¶Р°Р№С€РёС… РїРѕРІРµСЂС…РЅРѕСЃС‚РµР№.
    # Р РґР°, РїР°СЂР°РјРµС‚СЂС‹ step_up/step_down Р’РћРћР‘Р©Р• РќР• РРЎРџРћР›Р¬Р—РЈР®РўРЎРЇ.
    def _check_ground(self) -> tuple[bool, float]:
        if not self.transform:
            return False, 0.0
        pos = self.transform.local_position
        total_half = self.capsule_height * 0.5 + self.capsule_radius
        origin = Vec3(pos.x, pos.y, pos.z)
        dist = total_half + self.ground_check_dist
        from core.engine import Engine
        engine = Engine.instance()
        if not engine or not engine._scene:
            return False, 0.0
        for ent in engine._scene.get_all_entities():
            if ent == self._entity or not ent.active:
                continue
            from core.components.physics.box_collider import BoxCollider
            bc = ent.get_component(BoxCollider)
            if bc and bc.enabled:
                tr = ent.get_component_by_name("Transform")
                if tr:
                    aabb_min, aabb_max = self._box_aabb(tr, bc)
                    if self._ray_aabb_intersect(origin, Vec3(0, -1, 0), dist, aabb_min, aabb_max):
                        entry = self._ray_aabb_entry(origin, Vec3(0, -1, 0), aabb_min, aabb_max)
                        if entry is not None and 0 <= entry < dist:
                            return True, aabb_max.y
        return False, 0.0

    def _box_aabb(self, tr, bc):
        sz = bc.scaled_size
        c = bc.scaled_center
        world_pos = tr.local_position + tr.local_rotation.rotate_vec3(c)
        h = Vec3(sz.x * 0.5, sz.y * 0.5, sz.z * 0.5)
        return (world_pos - h, world_pos + h)

    # РџРР—Р”Р•Р¦: _ray_aabb_intersect Рё _ray_aabb_entry вЂ” Р­РўРћ РћР”РќРћ Р РўРћ Р–Р•.
    # РЎРµСЂСЊС‘Р·РЅРѕ, РѕС‚РєСЂРѕР№ РіР»Р°Р·Р°: 95% РєРѕРґР° РёРґРµРЅС‚РёС‡РЅРѕ. РћРґРЅР° РІРѕР·РІСЂР°С‰Р°РµС‚ bool, РґСЂСѓРіР°СЏ float.
    # РњРѕР¶РЅРѕ Р±С‹Р»Рѕ СЃРґРµР»Р°С‚СЊ _ray_aabb_test(..., need_entry=True) вЂ” РЅРѕ РЅРµС‚, Р›Р•РќР¬.
    def _ray_aabb_intersect(self, origin: Vec3, dir: Vec3, max_dist: float,
                             aabb_min: Vec3, aabb_max: Vec3) -> bool:
        tmin = -1e9
        tmax = 1e9
        for i in range(3):
            o = [origin.x, origin.y, origin.z][i]
            d = [dir.x, dir.y, dir.z][i]
            mn = [aabb_min.x, aabb_min.y, aabb_min.z][i]
            mx = [aabb_max.x, aabb_max.y, aabb_max.z][i]
            if abs(d) < 1e-10:
                if o < mn or o > mx:
                    return False
            else:
                t1 = (mn - o) / d
                t2 = (mx - o) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin = max(tmin, t1)
                tmax = min(tmax, t2)
                if tmin > tmax:
                    return False
        return tmin < max_dist and tmax >= 0

    # Р‘Р›РЇР”Р¬, РљРћРџРРџРђРЎРўРђ _ray_aabb_intersect РЎ Р”Р РЈР“РРњ RETURN. РҐР’РђРўРР›Рћ РЈРњРђ РџР•Р Р•РРњР•РќРћР’РђРўР¬ min(tmin, max_dist) Р’ entry.
    def _ray_aabb_entry(self, origin: Vec3, dir: Vec3, aabb_min: Vec3, aabb_max: Vec3) -> float | None:
        tmin = -1e9
        tmax = 1e9
        for i in range(3):
            o = [origin.x, origin.y, origin.z][i]
            d = [dir.x, dir.y, dir.z][i]
            mn = [aabb_min.x, aabb_min.y, aabb_min.z][i]
            mx = [aabb_max.x, aabb_max.y, aabb_max.z][i]
            if abs(d) < 1e-10:
                if o < mn or o > mx:
                    return None
            else:
                t1 = (mn - o) / d
                t2 = (mx - o) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin = max(tmin, t1)
                tmax = min(tmax, t2)
                if tmin > tmax:
                    return None
        return max(0.0, tmin) if tmax >= 0 else None

    def _accelerate(self, wish_dir: Vec3, wish_speed: float, accel: float, dt: float):
        vel = self.velocity
        cur_speed = vel.dot(wish_dir)
        add = wish_speed - cur_speed
        if add <= 0:
            return
        add = min(add, accel * dt * wish_speed)
        self.velocity = vel + wish_dir * add

    def _apply_friction(self, dt: float):
        vel = self.velocity
        speed = vel.length()
        if speed < 0.001:
            self.velocity = Vec3.zero()
            return
        control = self.stop_speed if speed < self.stop_speed else speed
        drop = control * self.friction * dt
        new_speed = max(0.0, speed - drop) / speed
        self.velocity = vel * new_speed

    def _move_ground(self, dt: float):
        wish_dir = self.get_wish_dir()
        wish_speed = self.get_move_speed()
        self._accelerate(wish_dir, wish_speed, self.acceleration, dt)
        self._apply_friction(dt)

    def _move_air(self, dt: float):
        wish_dir = self.get_wish_dir()
        wish_speed = self.get_move_speed()
        self._accelerate(wish_dir, min(wish_speed, 30.0), self.air_acceleration, dt)

    def _jump(self):
        vel = self.velocity
        self.velocity = Vec3(vel.x, self.jump_power, vel.z)
        self._grounded = False
        self._ground_normal = Vec3.up()

    def _update_crouch(self):
        if self._is_crouching:
            self._target_eye_height = self.crouch_eye_offset
        else:
            self._target_eye_height = self.capsule_height - 0.3
        diff = self._target_eye_height - self._eye_height
        self._eye_height += diff * min(1.0, 10.0 * 0.016)

    def _find_camera(self):
        from core.engine import Engine
        engine = Engine.instance()
        if not engine or not engine._scene:
            return
        from core.components.rendering.camera import Camera
        for ent in engine._scene.get_entities_with_component(Camera):
            if ent.active:
                self._camera_entity_id = ent.id
                return

    def on_start(self):
        from core.components.physics.rigidbody import Rigidbody
        self._rigidbody = self._entity.get_component(Rigidbody) if self._entity else None
        if self._rigidbody is not None:
            self._rigidbody.use_gravity = False
            self._rigidbody.is_kinematic = True
        self.velocity = Vec3.zero()
        self._pitch = 0.0
        self._yaw = 0.0
        self._is_crouching = False
        self._wants_to_crouch = False
        self._grounded = False
        self._ground_y = 0.0
        self._ground_normal = Vec3.up()
        self._coyote_timer = 0.0
        self._jump_buffer_timer = 0.0
        self._was_grounded = False
        self._eye_height = self.capsule_height - 0.3
        self._target_eye_height = self._eye_height
        self._air_time = 0.0
        self._last_frame_speed = 0.0
        self._camera_entity_id = None
        if self.camera_entity_id:
            self._camera_entity_id = self.camera_entity_id

    def on_disable(self):
        Input.set_cursor_locked(False)

    def on_update(self, dt: float):
        if not self._entity or not self.enabled:
            return
        self._handle_mouse_look(dt)
        self._update_crouch()
        if self._camera_entity_id is None:
            self._find_camera()
        self._update_camera()

    def on_fixed_update(self, dt: float):
        if not self._entity or not self.enabled:
            return
        tr = self.transform
        if not tr:
            return

        self._was_grounded = self._grounded
        self._grounded, self._ground_y = self._check_ground()

        if self._grounded:
            self._coyote_timer = self.coyote_time
            self._air_time = 0.0
        else:
            self._coyote_timer -= dt
            self._air_time += dt

        if Input.GetKeyDown(KeyCode.SPACE):
            self._jump_buffer_timer = self.jump_buffer_time
        else:
            self._jump_buffer_timer -= dt

        if self._jump_buffer_timer > 0.0 and self._coyote_timer > 0.0:
            self._jump()
            self._jump_buffer_timer = 0.0
            self._coyote_timer = 0.0

        if Input.GetKeyDown(KeyCode.C):
            self._wants_to_crouch = not self._wants_to_crouch
            if self.crouch_toggle:
                self._is_crouching = self._wants_to_crouch
            else:
                self._is_crouching = not self._is_crouching
        if not self.crouch_toggle:
            self._is_crouching = Input.GetKey(KeyCode.C)

        vel = self.velocity
        if self._grounded:
            self._move_ground(dt)
            vel = self.velocity
            if vel.y < 0.0:
                vel = Vec3(vel.x, 0.0, vel.z)
                self.velocity = vel
        else:
            vel = Vec3(vel.x, vel.y - self.gravity * dt, vel.z)
            self.velocity = vel
            self._move_air(dt)
            vel = self.velocity

        # Р‘Р›РЇР”Р¬: РќР•Рў РЎРўР•Рќ. РќРРљРђРљРРҐ. position += vel * dt вЂ” Рё РІ РґР°РјРєРё.
        # РЎС‚СѓРїРµРЅСЊРєР° РІ 1 СЃРј? РџСЂРѕР№РґС‘С€СЊ. РЎС‚РµРЅР°? РџСЂРѕР№РґС‘С€СЊ РЅР°СЃРєРІРѕР·СЊ.
        # РќРµС‚ sliding, РЅРµС‚ response, РЅРµС‚ fucking collision check РїРѕ РіРѕСЂРёР·РѕРЅС‚Р°Р»Рё.
        # step_up/step_down РІ РїР°СЂР°РјРµС‚СЂР°С… РµСЃС‚СЊ вЂ” СЂР°Р±РѕС‚Р°СЋС‚ РєР°Рє placebo.
        pos = tr.local_position
        new_pos = Vec3(
            pos.x + vel.x * dt,
            pos.y + vel.y * dt,
            pos.z + vel.z * dt,
        )

        total_half = self.capsule_height * 0.5 + self.capsule_radius
        if self._grounded:
            min_y = self._ground_y + total_half
            if new_pos.y < min_y:
                new_pos = Vec3(new_pos.x, min_y, new_pos.z)
                vel = Vec3(vel.x, 0.0, vel.z)

        tr.local_position = new_pos
        self.velocity = vel

    def _update_camera(self):
        if self._camera_entity_id is None:
            return
        from core.engine import Engine
        engine = Engine.instance()
        if not engine or not engine._scene:
            return
        cam_ent = engine._scene.get_entity(self._camera_entity_id)
        if not cam_ent or not cam_ent.active:
            self._camera_entity_id = None
            return
        cam_tr = cam_ent.get_component_by_name("Transform")
        player_tr = self.transform
        if not cam_tr or not player_tr:
            return

        half_pitch = math.radians(self._pitch * 0.5)
        half_yaw = math.radians(self._yaw * 0.5)
        cp = math.cos(half_pitch)
        sp = math.sin(half_pitch)
        cy = math.cos(half_yaw)
        sy = math.sin(half_yaw)
        from core.math3d import Quat

        cam_is_child = cam_tr._entity.parent is self._entity if cam_tr._entity else False

        if cam_is_child:
            cam_tr.local_position = Vec3(0, self._eye_height, 0)
            cam_tr.local_rotation = Quat(sp, 0, 0, cp)
        else:
            cam_tr.local_position = player_tr.local_position + Vec3(0, self._eye_height, 0)
            cam_tr.local_rotation = Quat(sp * cy, cp * sy, -sp * sy, cp * cy)

    def _handle_mouse_look(self, dt: float):
        if not self._entity:
            return
        dx, dy = Input.mouseDelta
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return
        yaw_speed = self.sensitivity * 0.022
        pitch_speed = self.sensitivity * 0.022
        self._yaw -= dx * yaw_speed
        pitch_delta = dy * pitch_speed
        if self.invert_y:
            pitch_delta = -pitch_delta
        self._pitch -= pitch_delta
        self._pitch = max(-89.0, min(89.0, self._pitch))

        tr = self.transform
        if tr:
            half_yaw = math.radians(self._yaw * 0.5)
            cy = math.cos(half_yaw)
            sy = math.sin(half_yaw)
            from core.math3d import Quat
            tr.local_rotation = Quat(0, sy, 0, cy)

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
            "invert_y": self.invert_y, "camera_entity_id": self.camera_entity_id,
            "gravity": self.gravity,
            "capsule_radius": self.capsule_radius, "capsule_height": self.capsule_height,
            "crouch_height": self.crouch_height, "step_up": self.step_up,
            "step_down": self.step_down, "ground_check_dist": self.ground_check_dist,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> CharacterController:
        cc = cls()
        cc.enabled = data.get("enabled", True)
        for key in ("walk_speed", "run_speed", "crouch_speed", "acceleration",
                     "air_acceleration", "friction", "stop_speed", "jump_power",
                     "jump_buffer_time", "coyote_time", "crouch_speed_mult",
                     "crouch_eye_offset", "sensitivity", "gravity",
                     "capsule_radius", "capsule_height", "crouch_height",
                     "step_up", "step_down", "ground_check_dist"):
            setattr(cc, key, data.get(key, getattr(cc, key)))
        cc.crouch_toggle = data.get("crouch_toggle", cc.crouch_toggle)
        cc.invert_y = data.get("invert_y", cc.invert_y)
        cc.camera_entity_id = data.get("camera_entity_id", "")
        return cc
