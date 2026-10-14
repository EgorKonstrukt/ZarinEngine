# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Callable
class Command:
    def execute(self): raise NotImplementedError
    def undo(self): raise NotImplementedError
    def redo(self):
        self.execute()
    def merge(self, other: Command) -> bool:
        return False
    @property
    def description(self) -> str:
        return self.__class__.__name__
_global_on_undo: list = []
_global_on_redo: list = []
_history_provider = None
def set_history_provider(fn) -> None:
    global _history_provider
    _history_provider = fn
class CompoundCommand(Command):
    def __init__(self, commands: list[Command], description: str = "Compound"):
        self._commands = commands
        self._desc = description
    def execute(self):
        for c in self._commands:
            c.execute()
    def undo(self):
        for c in reversed(self._commands):
            c.undo()
    @property
    def description(self) -> str:
        return self._desc
class CommandHistory:
    def __init__(self, max_size: int = 100):
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._undo_sel: list = []
        self._redo_sel: list = []
        self._max_size = max_size
        self._saved_index: int = 0
        self._last_affected_entity = None
        self._current_selection = None
        self._recording = True
    def set_on_undo(self, cb: Optional[Callable[[Command], None]]):
        if cb is None:
            _global_on_undo.clear()
        elif cb not in _global_on_undo:
            _global_on_undo.append(cb)
    def set_on_redo(self, cb: Optional[Callable[[Command], None]]):
        if cb is None:
            _global_on_redo.clear()
        elif cb not in _global_on_redo:
            _global_on_redo.append(cb)
    def add_on_change(self, cb: Callable[[Command], None]):
        if cb not in _global_on_undo:
            _global_on_undo.append(cb)
        if cb not in _global_on_redo:
            _global_on_redo.append(cb)
    @property
    def can_undo(self) -> bool: return len(self._undo_stack) > 0
    @property
    def can_redo(self) -> bool: return len(self._redo_stack) > 0
    @property
    def is_dirty(self) -> bool:
        return len(self._undo_stack) != self._saved_index
    @property
    def last_affected_entity(self):
        return self._last_affected_entity
    @staticmethod
    def _extract_entity(cmd):
        e = getattr(cmd, "_entity", None)
        if e is not None:
            return e
        eid = getattr(cmd, "_entity_id", None)
        if eid is not None:
            scene = getattr(cmd, "_scene", None)
            if scene is None:
                from core.engine.eng import Engine
                scene = Engine.instance().scene
            if scene:
                e = scene.get_entity(eid)
                if e:
                    return e
        cmds = getattr(cmd, "_commands", None)
        if cmds:
            for c in cmds:
                e = CommandHistory._extract_entity(c)
                if e is not None:
                    return e
        return None
    @property
    def undo_text(self) -> str:
        if self._undo_stack:
            return f"Undo {self._undo_stack[-1].description}"
        return "Can't Undo"
    @property
    def redo_text(self) -> str:
        if self._redo_stack:
            return f"Redo {self._redo_stack[-1].description}"
        return "Can't Redo"
    def set_current_selection(self, sel):
        self._current_selection = sel
    @property
    def current_selection(self):
        return self._current_selection
    def execute(self, command: Command):
        if self._recording:
            self._undo_sel.append(self._current_selection)
        command.execute()
        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._undo_sel.clear()
        self._redo_sel.clear()
        if len(self._undo_stack) > self._max_size:
            self._undo_stack.pop(0)
            if self._undo_sel:
                self._undo_sel.pop(0)
            if self._saved_index > 0:
                self._saved_index -= 1
        self._emit_history_changed()
    def _emit_history_changed(self):
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            if eng:
                eng._emit_event("history_changed", None)
        except Exception:
            pass
    def undo(self):
        if not self._undo_stack:
            return
        was_recording = self._recording
        self._recording = False
        cmd = self._undo_stack.pop()
        pre_sel = self._undo_sel.pop() if self._undo_sel else None
        self._redo_sel.append(self._current_selection)
        cmd.undo()
        self._redo_stack.append(cmd)
        self._current_selection = pre_sel
        self._last_affected_entity = self._extract_entity(cmd) or pre_sel
        self._recording = was_recording
        if was_recording and _global_on_undo:
            for cb in list(_global_on_undo):
                cb(cmd)
            self._emit_history_changed()
    def redo(self):
        if not self._redo_stack:
            return
        was_recording = self._recording
        self._recording = False
        cmd = self._redo_stack.pop()
        post_sel = self._redo_sel.pop() if self._redo_sel else None
        self._undo_sel.append(self._current_selection)
        cmd.redo()
        self._undo_stack.append(cmd)
        self._current_selection = post_sel
        self._last_affected_entity = self._extract_entity(cmd) or post_sel
        self._recording = was_recording
        if was_recording and _global_on_redo:
            for cb in list(_global_on_redo):
                cb(cmd)
            self._emit_history_changed()
    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)
    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)
    def get_undo_descriptions(self) -> list[str]:
        return [c.description for c in self._undo_stack]
    def get_redo_descriptions(self) -> list[str]:
        return [c.description for c in self._redo_stack]
    def seek(self, target_head: int):
        total = len(self._undo_stack) + len(self._redo_stack)
        target_head = max(0, min(target_head, total))
        current = len(self._undo_stack)
        if current == target_head:
            return
        was_recording = self._recording
        self._recording = False
        if current > target_head:
            n = current - target_head
            for _ in range(n):
                cmd = self._undo_stack.pop()
                pre_sel = self._undo_sel.pop() if self._undo_sel else None
                self._redo_sel.append(self._current_selection)
                cmd.undo()
                self._redo_stack.append(cmd)
                self._current_selection = pre_sel
            self._last_affected_entity = (
                self._extract_entity(self._redo_stack[-1])
                if self._redo_stack else None
            ) or pre_sel
        else:
            n = target_head - current
            for _ in range(n):
                cmd = self._redo_stack.pop()
                post_sel = self._redo_sel.pop() if self._redo_sel else None
                self._undo_sel.append(self._current_selection)
                cmd.redo()
                self._undo_stack.append(cmd)
                self._current_selection = post_sel
                self._last_affected_entity = (
                    self._extract_entity(self._undo_stack[-1])
                    if self._undo_stack else None
                ) or post_sel
        self._recording = was_recording
        self._emit_history_changed()
    def mark_saved(self):
        self._saved_index = len(self._undo_stack)
    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._undo_sel.clear()
        self._redo_sel.clear()
        self._saved_index = 0
_history: Optional[CommandHistory] = None
def get_history() -> CommandHistory:
    global _history
    if _history_provider is not None:
        try:
            provided = _history_provider()
        except Exception:
            provided = None
        if provided is not None:
            return provided
    if _history is None:
        _history = CommandHistory()
    return _history
