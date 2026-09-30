# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def engine_api_words() -> set[str]:
    words = {
        "on_awake", "awake", "on_start", "start", "on_update", "update",
        "on_fixed_update", "fixed_update", "on_destroy", "destroy",
        "on_enable", "enable", "on_disable", "disable",
        "on_collision_enter", "on_collision_stay", "on_collision_exit",
        "gizmo_lines", "gizmo_meshes", "_entity", "_inspector_buttons",
        "Input", "KeyCode", "GetKey", "GetKeyDown", "GetKeyUp",
        "GetMouseButton", "GetMouseButtonDown", "GetMouseButtonUp",
        "GetButton", "GetButtonDown", "GetButtonUp", "GetAxis", "GetAxisRaw",
        "DefineAxis", "DefineButton", "mousePosition", "anyKey", "anyKeyDown",
        "cursorLocked", "cursorVisible", "deltaTime",
        "Vec2", "Vec3", "Vec4", "Quat", "Mat4", "Curve", "Range", "Logger",
        "get_component", "get_components", "get_component_by_name",
        "get_all_components", "transform", "position", "local_position",
        "local_euler_angles", "local_scale", "rotate", "translate", "look_at",
        "active", "enabled", "add_component", "get_entity",
    }
    try:
        from core.input.input_system import KeyCode as _KC
        try:
            words.update(m.name for m in _KC)
        except Exception:
            pass
    except Exception:
        pass
    return words


ENGINE_API_WORDS = engine_api_words()
