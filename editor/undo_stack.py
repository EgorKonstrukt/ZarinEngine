from __future__ import annotations
from typing import Callable, Optional
from PyQt6.QtCore import QObject, pyqtSignal
class UndoCommand:
    def __init__(self, description: str = ""):
        self.description = description
    def redo(self): raise NotImplementedError
    def undo(self): raise NotImplementedError
class CallbackCommand(UndoCommand):
    def __init__(self, do_fn: Callable, undo_fn: Callable, description: str = ""):
        super().__init__(description)
        self._do = do_fn
        self._undo = undo_fn
    def redo(self): self._do()
    def undo(self): self._undo()
class MacroCommand(UndoCommand):
    def __init__(self, commands: list[UndoCommand], description: str = ""):
        super().__init__(description)
        self._commands = list(commands)
    def redo(self):
        for cmd in self._commands:
            cmd.redo()
    def undo(self):
        for cmd in reversed(self._commands):
            cmd.undo()
class UndoStack(QObject):
    index_changed = pyqtSignal(int)
    can_undo_changed = pyqtSignal(bool)
    can_redo_changed = pyqtSignal(bool)
    MAX_STACK: int = 200
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stack: list[UndoCommand] = []
        self._index: int = -1
        self._macro_stack: list[list[UndoCommand]] = []
    @property
    def can_undo(self) -> bool: return self._index >= 0
    @property
    def can_redo(self) -> bool: return self._index < len(self._stack) - 1
    @property
    def index(self) -> int: return self._index
    def push(self, cmd: UndoCommand):
        if self._macro_stack:
            self._macro_stack[-1].append(cmd)
            cmd.redo()
            return
        if self._index < len(self._stack) - 1:
            self._stack = self._stack[:self._index + 1]
        self._stack.append(cmd)
        if len(self._stack) > self.MAX_STACK:
            self._stack.pop(0)
        else:
            self._index += 1
        cmd.redo()
        self._notify()
    def undo(self):
        if not self.can_undo: return
        self._stack[self._index].undo()
        self._index -= 1
        self._notify()
    def redo(self):
        if not self.can_redo: return
        self._index += 1
        self._stack[self._index].redo()
        self._notify()
    def begin_macro(self, description: str = ""):
        self._macro_stack.append([])
    def end_macro(self, description: str = ""):
        if not self._macro_stack: return
        cmds = self._macro_stack.pop()
        if cmds:
            macro = MacroCommand(cmds, description)
            if self._index < len(self._stack) - 1:
                self._stack = self._stack[:self._index + 1]
            self._stack.append(macro)
            if len(self._stack) > self.MAX_STACK:
                self._stack.pop(0)
            else:
                self._index += 1
            self._notify()
    def clear(self):
        self._stack.clear()
        self._index = -1
        self._macro_stack.clear()
        self._notify()
    def undo_description(self) -> str:
        if not self.can_undo: return ""
        return self._stack[self._index].description
    def redo_description(self) -> str:
        if not self.can_redo: return ""
        return self._stack[self._index + 1].description
    def _notify(self):
        self.index_changed.emit(self._index)
        self.can_undo_changed.emit(self.can_undo)
        self.can_redo_changed.emit(self.can_redo)