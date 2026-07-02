# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from PyQt6 import QtCore, QtGui


class QUndoCommand:
    def __init__(self, text="", parent=None):
        self._text = text
        self._parent = parent

    def redo(self):
        pass

    def undo(self):
        pass

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


class UndoAction(QtGui.QAction):
    def __init__(self, stack, parent=None):
        super().__init__(parent)
        self._stack = stack
        self.setText('&Undo')
        self.triggered.connect(self._do_undo)

    def _do_undo(self):
        if self._stack:
            self._stack.undo()


class RedoAction(QtGui.QAction):
    def __init__(self, stack, parent=None):
        super().__init__(parent)
        self._stack = stack
        self.setText('&Redo')
        self.triggered.connect(self._do_redo)

    def _do_redo(self):
        if self._stack:
            self._stack.redo()


class QUndoStack:
    def __init__(self, parent=None):
        self._commands = []
        self._index = -1
        self._macro_commands = []
        self._in_macro = False

    def createUndoAction(self, parent=None, text='&Undo'):
        action = UndoAction(self, parent)
        action.setText(text)
        return action

    def createRedoAction(self, parent=None, text='&Redo'):
        action = RedoAction(self, parent)
        action.setText(text)
        return action

    def push(self, cmd):
        if self._in_macro:
            self._macro_commands.append(cmd)
            return
        self._commands = self._commands[:self._index + 1]
        self._commands.append(cmd)
        self._index += 1
        cmd.redo()

    def undo(self):
        if self._index >= 0:
            self._commands[self._index].undo()
            self._index -= 1

    def redo(self):
        if self._index < len(self._commands) - 1:
            self._index += 1
            self._commands[self._index].redo()

    def clear(self):
        self._commands.clear()
        self._index = -1

    def isClean(self):
        return self._index < 0

    def setClean(self):
        self._commands = self._commands[self._index + 1:]
        self._index = -1

    def index(self):
        return self._index

    def count(self):
        return len(self._commands)

    def beginMacro(self, text=''):
        self._in_macro = True
        self._macro_commands = []

    def endMacro(self):
        self._in_macro = False
        if self._macro_commands:
            for cmd in self._macro_commands:
                self._commands = self._commands[:self._index + 1]
                self._commands.append(cmd)
                self._index += 1
                cmd.redo()
            self._macro_commands = []
