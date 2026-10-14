# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Callable
import time
from collections import defaultdict
from core.input.inpsys.keys import InputAxis, InputButton

class InputState:
    def __init__(self):
        self._held: dict[int, bool] = {}
        self._mouse_held: dict[int, bool] = {}
        self._acc_down: set[int] = set()
        self._acc_up: set[int] = set()
        self._frame_down: set[int] = set()
        self._frame_up: set[int] = set()
        self._mouse_pos: tuple[float, float] = (0.0, 0.0)
        self._mouse_delta: tuple[float, float] = (0.0, 0.0)
        self._scroll_delta: tuple[float, float] = (0.0, 0.0)
        self._any_key_down: bool = False
        self._any_key: bool = False
        self._axes: dict[str, InputAxis] = {}
        self._mouse_axes: set[str] = set()
        self._buttons: dict[str, InputButton] = {}
        self._event_callbacks: dict[str, list[Callable]] = defaultdict(list)
        self._input_enabled: bool = True
        self._cursor_locked: bool = False
        self._cursor_visible: bool = True
        self._frame_count: int = 0
        self._time: float = 0.0
        self._last_time: float = time.perf_counter()
        self._dt: float = 0.0
        self._mouse_sensitivity: float = 1.0
        self._invert_mouse_x: bool = False
        self._invert_mouse_y: bool = False
        self._control_scheme: str = "fps"
    def define_axis(self, name: str, axis: InputAxis):
        self._axes[name] = axis
    def define_button(self, name: str, button: InputButton):
        self._buttons[name] = button
    def define_mouse_axis(self, name: str):
        self._mouse_axes.add(name.lower())
    def on_event(self, event_name: str, callback: Callable):
        self._event_callbacks[event_name].append(callback)
    def off_event(self, event_name: str, callback: Callable):
        if event_name in self._event_callbacks:
            try:
                self._event_callbacks[event_name].remove(callback)
            except ValueError:
                pass
    def _fire_event(self, event_name: str, data=None):
        for cb in self._event_callbacks.get(event_name, []):
            try:
                cb(data)
            except Exception:
                pass
    def begin_frame(self):
        now = time.perf_counter()
        self._dt = max(0.0, min(0.1, now - self._last_time))
        self._last_time = now
        self._frame_count += 1
        self._time = now
        self._frame_down = set(self._acc_down)
        self._frame_up = set(self._acc_up)
        self._acc_down.clear()
        self._acc_up.clear()
        self._any_key_down = False
        self._any_key = bool(self._held or self._mouse_held or self._frame_down)
        self._update_axes(self._dt)
        self._fire_event("frame_begin", None)
    def end_frame(self):
        self._scroll_delta = (0.0, 0.0)
        self._mouse_delta = (0.0, 0.0)
        self._fire_event("frame_end", None)
    def _update_axes(self, dt: float):
        for axis in self._axes.values():
            positive = any(self._held.get(k, False) for k in axis.positive) or \
                       any(self._held.get(k, False) for k in axis.alt_positive)
            negative = any(self._held.get(k, False) for k in axis.negative) or \
                       any(self._held.get(k, False) for k in axis.alt_negative)
            raw = (1.0 if positive else 0.0) - (1.0 if negative else 0.0)
            axis._raw_value = raw
            if abs(raw) < axis.dead or (axis.snap and positive and negative):
                raw = 0.0
            if raw != 0:
                axis._value += raw * axis.sensitivity * dt
                axis._value = max(-1.0, min(1.0, axis._value))
            else:
                if axis._value > 0:
                    axis._value = max(0.0, axis._value - axis.gravity * dt)
                elif axis._value < 0:
                    axis._value = min(0.0, axis._value + axis.gravity * dt)
    @staticmethod
    def _is_mouse_key(key: int) -> bool:
        return key >= 1000
    def press_key(self, key: int):
        if self._is_mouse_key(key):
            if not self._mouse_held.get(key, False):
                self._acc_down.add(key)
            self._mouse_held[key] = True
        else:
            if not self._held.get(key, False):
                self._acc_down.add(key)
            self._held[key] = True
        self._any_key_down = True
        self._fire_event("key_down", key)
    def release_key(self, key: int):
        if self._is_mouse_key(key):
            if self._mouse_held.get(key, False):
                self._acc_up.add(key)
            self._mouse_held[key] = False
        else:
            if self._held.get(key, False):
                self._acc_up.add(key)
            self._held[key] = False
        self._fire_event("key_up", key)
    def set_mouse_pos(self, x: float, y: float, delta_x: float = 0.0, delta_y: float = 0.0):
        self._mouse_pos = (x, y)
        self._mouse_delta = (self._mouse_delta[0] + delta_x, self._mouse_delta[1] + delta_y)
    def set_scroll(self, dx: float, dy: float):
        self._scroll_delta = (self._scroll_delta[0] + dx, self._scroll_delta[1] + dy)
    def reset_all(self):
        self._held.clear()
        self._mouse_held.clear()
        self._acc_down.clear()
        self._acc_up.clear()
        self._frame_down.clear()
        self._frame_up.clear()
        self._mouse_pos = (0.0, 0.0)
        self._mouse_delta = (0.0, 0.0)
        self._scroll_delta = (0.0, 0.0)

class classproperty:
    def __init__(self, fget):
        self.fget = fget
    def __get__(self, instance, owner):
        return self.fget(owner)

class classproperty_setter:
    def __init__(self, fget=None, fset=None):
        self.fget = fget
        self.fset = fset
    def __get__(self, instance, owner):
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(owner)
    def __set__(self, instance, value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        self.fset(type(instance) if instance else None, value)
    def setter(self, fset):
        return classproperty_setter(self.fget, fset)
