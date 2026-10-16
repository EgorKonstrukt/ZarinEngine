# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import copy

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QLineEdit, QTableWidgetItem

from .cells import COLUMNS_PER_CHANNEL, _transpose_note
from .grid import _PatternGridBase


class PatternEditorWidget(_PatternGridBase):
    def insert_row(self) -> None:
        if self._pattern is None:
            return
        row = max(0, self.currentRow())
        self._push_undo()
        data = getattr(self._pattern, "data", None) or []
        for ch in range(len(data)):
            chan = data[ch]
            if not chan:
                continue
            chan.insert(row, type(chan[row % len(chan)])())
            chan.pop()
        self._refresh_after_structure()

    def delete_row(self) -> None:
        if self._pattern is None:
            return
        row = self.currentRow()
        if row < 0:
            return
        data = getattr(self._pattern, "data", None) or []
        for ch in range(len(data)):
            chan = data[ch]
            if not chan:
                continue
            cls = type(chan[row])
            chan.pop(row)
            chan.append(cls())
        self._refresh_after_structure()

    def clear_row(self) -> None:
        if self._pattern is None:
            return
        row = self.currentRow()
        if row < 0:
            return
        self._push_undo()
        data = getattr(self._pattern, "data", None) or []
        for ch in range(len(data)):
            chan = data[ch]
            if row < len(chan):
                chan[row] = type(chan[row])()
        self._refresh_after_structure()

    def transpose_rows(self, semis: int) -> None:
        if self._pattern is None:
            return
        rows = sorted({i.row() for i in self.selectedItems()}) or [self.currentRow()]
        if not rows or rows[0] < 0:
            return
        self._push_undo()
        data = getattr(self._pattern, "data", None) or []
        for row in rows:
            for ch in range(len(data)):
                if row >= len(data[ch]):
                    continue
                note = data[ch][row]
                p = getattr(note, "period", "") or ""
                if p.lower() == "off":
                    continue
                transposed = _transpose_note(p, semis)
                if transposed != p:
                    note.period = transposed
        self._refresh_after_structure()

    def copy_row(self) -> None:
        if self._pattern is None:
            return
        row = self.currentRow()
        if row < 0:
            return
        data = getattr(self._pattern, "data", None) or []
        self._clipboard = [copy.deepcopy(data[ch][row]) for ch in range(len(data))]

    def cut_row(self) -> None:
        self.copy_row()
        self.clear_row()

    def paste_row(self) -> None:
        if self._pattern is None or not getattr(self, "_clipboard", None):
            return
        row = self.currentRow()
        if row < 0:
            return
        self._push_undo()
        data = getattr(self._pattern, "data", None) or []
        for ch in range(min(len(data), len(self._clipboard))):
            if row < len(data[ch]):
                data[ch][row] = copy.deepcopy(self._clipboard[ch])
        self._refresh_after_structure()

    def select_all_rows(self) -> None:
        if self._pattern is None:
            return
        row = self.currentRow()
        if row < 0:
            return
        if not self.columnCount():
            return
        sel = QItemSelection(self.model().index(row, 0), self.model().index(row, self.columnCount() - 1))
        self.selectionModel().select(sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def _start_edit_with_char(self, item: QTableWidgetItem, text: str) -> None:
        self._pending_char = text
        self.editItem(item)
        QTimer.singleShot(0, self._prefill_editor)

    def _prefill_editor(self) -> None:
        ed = self.findChild(QLineEdit)
        if ed is not None:
            ed.setText(self._pending_char or "")
            ed.selectAll()
        self._pending_char = ""

    def keyPressEvent(self, event):
        if self.state() == QAbstractItemView.State.EditingState:
            super().keyPressEvent(event)
            return
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        item = self.currentItem()
        if ctrl and key == Qt.Key.Key_C:
            self.copy_row()
            return
        if ctrl and key == Qt.Key.Key_X:
            self.cut_row()
            return
        if ctrl and key == Qt.Key.Key_V:
            self.paste_row()
            return
        if ctrl and key == Qt.Key.Key_Z and not shift:
            self.undo()
            return
        if (ctrl and key == Qt.Key.Key_Y) or (ctrl and shift and key == Qt.Key.Key_Z):
            self.redo()
            return
        if key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
            if item is not None:
                fields = self._field_item(item)
                if fields is not None:
                    note = fields[0]
                    field = fields[1]
                    if not self._parsed_is_current(note, field, self._empty_parsed(field)):
                        parsed = self._empty_parsed(field)
                        self._push_undo()
                        self._apply_field(note, field, parsed)
                        self._set_item_text(item, self._field_text(note, field))
                        self.patternChanged.emit()
            return
        if key == Qt.Key.Key_Insert:
            self.insert_row()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and item is not None:
            r = min(item.row() + 1, self.rowCount() - 1)
            self.setCurrentCell(max(0, r), item.column())
            return
        if item is not None and key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            if shift:
                self.setCurrentCell(item.row(), max(0, item.column() - 1))
            else:
                self.setCurrentCell(item.row(), min(self.columnCount() - 1, item.column() + 1))
            return
        if self._edit_key(event) and item is not None:
            self._start_edit_with_char(item, event.text())
            return
        super().keyPressEvent(event)

    def _field_item(self, item: QTableWidgetItem):
        if self._pattern is None or item is None:
            return None
        ch = item.column() // COLUMNS_PER_CHANNEL
        row = item.row()
        data = getattr(self._pattern, "data", None) or []
        if ch >= len(data) or row >= len(data[ch]):
            return None
        return (data[ch][row], item.column() % COLUMNS_PER_CHANNEL)

    def _edit_key(self, event) -> bool:
        nav = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
               Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End,
               Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab,
               Qt.Key.Key_Backtab, Qt.Key.Key_Delete, Qt.Key.Key_Backspace,
               Qt.Key.Key_Insert)
        if event.key() in nav:
            return False
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        return bool(event.text())
