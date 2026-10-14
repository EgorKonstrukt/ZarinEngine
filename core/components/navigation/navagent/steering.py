# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.maths.math3d import Vec3


_CC_TYPE = None
def _load_cc_type():
    global _CC_TYPE
    if _CC_TYPE is not None:
        return _CC_TYPE
    try:
        from core.components.physics.character import CharacterController
        _CC_TYPE = CharacterController
    except Exception:
        _CC_TYPE = None
    return _CC_TYPE
_load_cc_type()


class NavAgentSteeringMixin:

    def _active_controller(self):
        if not self.use_physical_controller or self.flying:
            return None
        try:
            ent = self.entity
        except Exception:
            return None
        if ent is None:
            return None
        try:
            cc_type = _load_cc_type()
            cc = ent.get_component(cc_type) if cc_type is not None else None
        except Exception:
            return None
        if cc is None:
            return None
        try:
            if not cc.enabled:
                return None
        except Exception:
            pass
        if not hasattr(cc, "set_ai_drive"):
            return None
        try:
            if getattr(cc, "_character", None) is None:
                return None
        except Exception:
            return None
        return cc


    def _set_cc_drive(self, cc, direction):
        try:
            prev = self._last_cc
        except Exception:
            prev = None
        if cc is None:
            if prev is not None:
                try:
                    prev.set_ai_drive(None, 0.0)
                except Exception:
                    pass
                self._last_cc = None
            return
        try:
            cc.set_ai_drive(direction, self.max_speed)
        except Exception:
            pass
        if prev is not None and prev is not cc:
            try:
                prev.set_ai_drive(None, 0.0)
            except Exception:
                pass
        self._last_cc = cc


    def _effective_nav_params(self):
        radius = self.agent_radius
        height = self.agent_height
        climb = self.max_climb
        slope = self.max_slope
        try:
            cc = self._active_controller()
        except Exception:
            cc = None
        if cc is not None:
            cc_radius = 0.0
            try:
                cc_radius = float(cc.capsule_radius)
                if cc_radius > 0.0:
                    radius = cc_radius
            except Exception:
                pass
            try:
                ch = float(cc.capsule_height)
                if ch > 0.0:
                    height = max(cc_radius * 2.0 + 0.1, ch) if cc_radius > 0.0 else ch
            except Exception:
                pass
            try:
                climb = max(0.0, float(cc.step_height))
            except Exception:
                pass
            try:
                slope = max(0.0, min(89.0, float(cc.max_slope)))
            except Exception:
                pass
        return radius, height, climb, slope


    def on_update(self, dt: float):
        if not self.auto_move:
            self._set_cc_drive(None, None)
            return
        if not self._ensure_nav_world():
            self._set_cc_drive(None, None)
            return

        self._poll_path_result()

        self._repath_timer += dt
        eff_interval = self.repath_interval * min(4, 2 ** min(self._fail_streak, 2))
        if self._repath_timer >= eff_interval:
            self._repath_timer = 0.0
            self._request_path()

        if not self._path or self._path_index >= len(self._path):
            self._set_cc_drive(None, None)
            return

        tr = self.transform
        if not tr:
            self._set_cc_drive(None, None)
            return

        target = self._path[self._path_index]
        current_pos = tr.local_position
        try:
            seg_free = self._nav_world.has_los(current_pos, target, self.flying)
        except Exception:
            seg_free = True
        if not seg_free:
            self._blocked_frames += 1
            adv = self._path_index
            try:
                for k in range(self._path_index + 1, len(self._path)):
                    if self._nav_world.has_los(current_pos, self._path[k], self.flying):
                        adv = k
            except Exception:
                pass
            if adv > self._path_index:
                self._path_index = adv
                self._blocked_frames = 0
                target = self._path[self._path_index]
            else:
                if self._blocked_frames >= 3:
                    self._blocked_frames = 0
                    self._pending_req_id = None
                    self._repath_timer = self.repath_interval
                self._set_cc_drive(None, None)
                return
        else:
            self._blocked_frames = 0
        to_target = target - current_pos
        dist = to_target.length()

        if dist <= self.arrival_distance:
            self._path_index += 1
            if self._path_index >= len(self._path):
                self._path = []
                self._path_index = 0
                self._set_cc_drive(None, None)
            return

        direction = to_target * (1.0 / dist) if dist > 0.001 else Vec3(0, 0, 1)
        cc = None
        try:
            cc = self._active_controller()
        except Exception:
            cc = None
        if cc is not None:
            try:
                fixed_count = cc.fixed_update_count
            except Exception:
                fixed_count = -1
            if fixed_count < 0:
                self._set_cc_drive(cc, direction)
            elif self._cc_dead:
                if fixed_count != self._cc_fixed_seen:
                    revived = False
                    try:
                        revived = bool(cc.resync_character())
                    except Exception:
                        revived = False
                    if revived:
                        self._cc_dead = False
                        self._cc_fixed_seen = fixed_count
                        self._cc_stall_time = 0.0
                        self._set_cc_drive(cc, direction)
                    else:
                        self._set_cc_drive(None, None)
                        move = direction * min(self.max_speed * dt, dist)
                        tr.local_position = current_pos + move
                else:
                    self._set_cc_drive(None, None)
                    move = direction * min(self.max_speed * dt, dist)
                    tr.local_position = current_pos + move
            elif fixed_count != self._cc_fixed_seen:
                self._cc_fixed_seen = fixed_count
                self._cc_stall_time = 0.0
                self._set_cc_drive(cc, direction)
            else:
                self._cc_stall_time += dt
                if self._cc_stall_time > 0.5:
                    self._cc_dead = True
                    self._set_cc_drive(None, None)
                    move = direction * min(self.max_speed * dt, dist)
                    tr.local_position = current_pos + move
                else:
                    self._set_cc_drive(cc, direction)
        else:
            self._set_cc_drive(None, None)
            move = direction * min(self.max_speed * dt, dist)
            tr.local_position = current_pos + move

        if self.max_angular_speed > 0:
            current_angles = tr.local_euler_angles
            target_yaw = math.degrees(math.atan2(direction.x, direction.z))
            diff = target_yaw - current_angles.y
            while diff > 180.0: diff -= 360.0
            while diff < -180.0: diff += 360.0
            max_step = self.max_angular_speed * dt
            if abs(diff) <= max_step:
                new_yaw = target_yaw
            else:
                new_yaw = current_angles.y + max_step * (1.0 if diff > 0 else -1.0)
            tr.local_euler_angles = Vec3(current_angles.x, new_yaw, current_angles.z)

