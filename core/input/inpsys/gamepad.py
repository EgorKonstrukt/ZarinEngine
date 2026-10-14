# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Callable
import os
from core.input.inpsys.keys import InputAxis, InputButton, KeyCode
from core.input.inpsys.manager import InputState, classproperty, classproperty_setter

class Input:
    _state: InputState = InputState()
    _INPUT_EVENTS = {
        "any_key_down", "any_key_up", "key_down", "key_up",
        "mouse_down", "mouse_up", "mouse_move", "scroll",
        "frame_begin", "frame_end",
    }
    @classmethod
    def _state_ref(cls) -> InputState:
        return cls._state
    @classmethod
    def begin_frame(cls):
        cls._state.begin_frame()
    @classmethod
    def end_frame(cls):
        cls._state.end_frame()
    @classmethod
    def GetKey(cls, key: int) -> bool:
        if not cls._state._input_enabled:
            return False
        return cls._state._held.get(key, False)
    @classmethod
    def GetKeyDown(cls, key: int) -> bool:
        if not cls._state._input_enabled:
            return False
        return key in cls._state._frame_down
    @classmethod
    def GetKeyUp(cls, key: int) -> bool:
        if not cls._state._input_enabled:
            return False
        return key in cls._state._frame_up
    @classmethod
    def GetMouseButton(cls, button: int) -> bool:
        if not cls._state._input_enabled:
            return False
        mk = KeyCode.MOUSE_LEFT + button
        return cls._state._mouse_held.get(mk, False)
    @classmethod
    def GetMouseButtonDown(cls, button: int) -> bool:
        if not cls._state._input_enabled:
            return False
        mk = KeyCode.MOUSE_LEFT + button
        return mk in cls._state._frame_down
    @classmethod
    def GetMouseButtonUp(cls, button: int) -> bool:
        if not cls._state._input_enabled:
            return False
        mk = KeyCode.MOUSE_LEFT + button
        return mk in cls._state._frame_up
    @classmethod
    def GetButton(cls, name: str) -> bool:
        btn = cls._state._buttons.get(name)
        if not btn:
            return False
        for k in btn.keys:
            if cls.GetKey(k):
                return True
        for k in btn.alt_keys:
            if cls.GetKey(k):
                return True
        return False
    @classmethod
    def GetButtonDown(cls, name: str) -> bool:
        btn = cls._state._buttons.get(name)
        if not btn:
            return False
        for k in btn.keys:
            if cls.GetKeyDown(k):
                return True
        for k in btn.alt_keys:
            if cls.GetKeyDown(k):
                return True
        return False
    @classmethod
    def GetButtonUp(cls, name: str) -> bool:
        btn = cls._state._buttons.get(name)
        if not btn:
            return False
        for k in btn.keys:
            if cls.GetKeyUp(k):
                return True
        for k in btn.alt_keys:
            if cls.GetKeyUp(k):
                return True
        return False
    @classmethod
    def GetAxis(cls, name: str) -> float:
        if not cls._state._input_enabled:
            return 0.0
        if name.lower() in cls._state._mouse_axes:
            return cls._get_mouse_axis(name)
        axis = cls._state._axes.get(name)
        if not axis:
            return 0.0
        return -axis._value if axis.invert else axis._value
    @classmethod
    def _get_mouse_axis(cls, name: str) -> float:
        dx, dy = cls._state._mouse_delta
        sens = cls._state._mouse_sensitivity
        if name.lower() == "mouse x":
            v = dx * sens
            return -v if cls._state._invert_mouse_x else v
        v = dy * sens
        return -v if cls._state._invert_mouse_y else v
    @classmethod
    def GetAxisRaw(cls, name: str) -> float:
        if not cls._state._input_enabled:
            return 0.0
        if name.lower() in cls._state._mouse_axes:
            return cls._get_mouse_axis(name)
        axis = cls._state._axes.get(name)
        if not axis:
            return 0.0
        return -axis._raw_value if axis.invert else axis._raw_value
    @classmethod
    def DefineAxis(cls, name: str, positive: list[int], negative: list[int],
                   alt_positive: list[int] = None, alt_negative: list[int] = None,
                   gravity: float = 3.0, dead: float = 0.001, sensitivity: float = 1.0,
                   snap: bool = False, invert: bool = False):
        cls._state.define_axis(name, InputAxis(positive, negative, alt_positive, alt_negative,
                                                gravity, dead, sensitivity, snap, invert))
    @classmethod
    def DefineMouseAxis(cls, name: str):
        cls._state.define_mouse_axis(name)
    @classmethod
    def DefineButton(cls, name: str, keys: list[int], alt_keys: list[int] = None):
        cls._state.define_button(name, InputButton(keys, alt_keys))
    @classproperty
    def mousePosition(cls) -> tuple[float, float]:
        return cls._state._mouse_pos
    @classproperty
    def mouseDelta(cls) -> tuple[float, float]:
        return cls._state._mouse_delta
    @classproperty
    def mouseScrollDelta(cls) -> tuple[float, float]:
        return cls._state._scroll_delta
    @classproperty
    def anyKey(cls) -> bool:
        return cls._state._any_key
    @classproperty
    def anyKeyDown(cls) -> bool:
        return cls._state._any_key_down
    @classproperty
    def inputEnabled(cls) -> bool:
        return cls._state._input_enabled
    @classmethod
    def set_input_enabled(cls, value: bool):
        cls._state._input_enabled = value
    @classproperty
    def cursorLocked(cls) -> bool:
        return cls._state._cursor_locked
    @classmethod
    def set_cursor_locked(cls, value: bool):
        cls._state._cursor_locked = value
    @classproperty
    def cursorVisible(cls) -> bool:
        return cls._state._cursor_visible
    @classmethod
    def set_cursor_visible(cls, value: bool):
        cls._state._cursor_visible = value
    @classproperty
    def deltaTime(cls) -> float:
        return cls._state._dt
    @classproperty
    def mouseSensitivity(cls) -> float:
        return cls._state._mouse_sensitivity
    @classmethod
    def set_mouse_sensitivity(cls, value: float):
        cls._state._mouse_sensitivity = max(0.0, float(value))
    @classproperty
    def invertMouseY(cls) -> bool:
        return cls._state._invert_mouse_y
    @classmethod
    def set_invert_mouse_y(cls, value: bool):
        cls._state._invert_mouse_y = bool(value)
    @classproperty
    def invertMouseX(cls) -> bool:
        return cls._state._invert_mouse_x
    @classmethod
    def set_invert_mouse_x(cls, value: bool):
        cls._state._invert_mouse_x = bool(value)
    @classproperty
    def controlScheme(cls) -> str:
        return cls._state._control_scheme
    @classmethod
    def set_control_scheme(cls, value: str):
        cls._state._control_scheme = "tps" if str(value).lower() == "tps" else "fps"
    @classmethod
    def LoadProjectBindings(cls, project_path: str = None):
        from core.config.config import get_project_config
        cfg = get_project_config(project_path) if project_path else get_project_config(os.getcwd())
        inp = cfg.to_dict().get("input", {})
        scheme = str(inp.get("control_scheme", "fps")).lower()
        cls.set_control_scheme("tps" if scheme == "tps" else "fps")
        cls.set_mouse_sensitivity(inp.get("mouse_sensitivity", 1.0))
        cls.set_invert_mouse_y(bool(inp.get("invert_mouse_y", False)))
        cls.set_invert_mouse_x(bool(inp.get("invert_mouse_x", False)))
        gravity = float(inp.get("axis_gravity", 3.0))
        sensitivity = float(inp.get("axis_sensitivity", 1.0))
        dead = float(inp.get("axis_dead", 0.001))
        cls._state._axes.clear()
        cls._state._buttons.clear()
        cls._state._mouse_axes.clear()
        axis_map = {
            "horizontal": ("Horizontal", None),
            "vertical": ("Vertical", None),
            "fire_axis": ("Fire", None),
            "jump_axis": ("Jump", None),
        }
        for key, (axis_name, _) in axis_map.items():
            binding = inp.get(key)
            if binding:
                pos, neg = cls._split_axis_binding(binding)
                if pos or neg:
                    cls.DefineAxis(axis_name, pos, neg, gravity=gravity, dead=dead, sensitivity=sensitivity)
        for btn_key, btn_name in [("jump", "Jump"), ("fire", "Fire"),
                                  ("crouch", "Crouch"), ("sprint", "Sprint"),
                                  ("interact", "Interact"), ("reload", "Reload")]:
            binding = inp.get(btn_key)
            if not binding:
                continue
            keys, alt = cls._split_button_binding(binding)
            alt_binding = inp.get("alt_" + btn_key)
            if alt_binding:
                _, extra_alt = cls._split_button_binding(alt_binding)
                alt = alt + extra_alt
            if keys or alt:
                cls.DefineButton(btn_name, keys, alt)
        for mkey in ("mouse_axis_x", "mouse_axis_y"):
            mname = inp.get(mkey)
            if not mname:
                mname = "Mouse X" if mkey == "mouse_axis_x" else "Mouse Y"
            cls.DefineMouseAxis(mname)
    @staticmethod
    def _resolve_code(part: str):
        part = part.strip().lower()
        if part.startswith("mouse"):
            rest = part[5:].strip()
            if rest.isdigit():
                return KeyCode.MOUSE_LEFT + int(rest)
            named = {"left": KeyCode.MOUSE_LEFT, "right": KeyCode.MOUSE_RIGHT,
                     "middle": KeyCode.MOUSE_MIDDLE, "back": KeyCode.MOUSE_BACK,
                     "forward": KeyCode.MOUSE_FORWARD}
            return named.get(rest, 0)
        return KeyCode.from_name(part)
    @staticmethod
    def _split_axis_binding(binding) -> tuple:
        if isinstance(binding, (list, tuple)):
            parts = list(binding)
        else:
            parts = str(binding).split(",")
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            return [], []
        explicit = any(p.startswith("-") for p in parts)
        positive, negative = [], []
        if explicit:
            for part in parts:
                if part.startswith("-"):
                    code = Input._resolve_code(part[1:])
                    if code:
                        negative.append(code)
                else:
                    code = Input._resolve_code(part)
                    if code:
                        positive.append(code)
        elif len(parts) == 2:
            neg = Input._resolve_code(parts[0])
            pos = Input._resolve_code(parts[1])
            if neg:
                negative.append(neg)
            if pos:
                positive.append(pos)
        else:
            for part in parts:
                code = Input._resolve_code(part)
                if code:
                    positive.append(code)
        return positive, negative
    @staticmethod
    def _split_button_binding(binding) -> tuple:
        if isinstance(binding, (list, tuple)):
            parts = list(binding)
        else:
            parts = str(binding).split(",")
        keys = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            code = Input._resolve_code(part)
            if code:
                keys.append(code)
        return keys, []
    @classmethod
    def OnEvent(cls, event_name: str, callback: Callable):
        if event_name in cls._INPUT_EVENTS:
            cls._state.on_event(event_name, callback)
    @classmethod
    def OffEvent(cls, event_name: str, callback: Callable):
        cls._state.off_event(event_name, callback)
    @classmethod
    def Reset(cls):
        cls._state.reset_all()

class CursorLockMode:
    NONE = "none"
    LOCKED = "locked"
    CONFINED = "confined"

class _Cursor:
    @property
    def visible(self) -> bool:
        return Input.cursorVisible
    @visible.setter
    def visible(self, value):
        Input.set_cursor_visible(bool(value))
    @property
    def lockState(self) -> str:
        if Input.cursorLocked:
            return CursorLockMode.LOCKED
        return CursorLockMode.NONE
    @lockState.setter
    def lockState(self, value):
        if value == CursorLockMode.LOCKED:
            Input.set_cursor_locked(True)
            Input.set_cursor_visible(False)
        else:
            Input.set_cursor_locked(False)
            Input.set_cursor_visible(True)

Cursor = _Cursor()
