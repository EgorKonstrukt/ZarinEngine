# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from .cells import (
    COLUMNS_PER_CHANNEL,
    COL_EFF,
    COL_INS,
    COL_NOTE,
    COL_VOL,
    _BASE_BRUSH,
    _COL_LABELS,
    _HIGHLIGHT_BRUSH,
    _eff_text,
    _inst_text,
    _note_text,
    _parse_effect,
    _parse_inst,
    _parse_note,
    _parse_vol,
    _vol_text,
)


class _PatternGridBase(QTableWidget):
    patternChanged = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pattern = None
        self._loading = False
        self._current_row: int = -1
        self._highlight_refs: list[tuple[int, QTableWidgetItem]] = []
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._pending_char = ""
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.verticalHeader().setDefaultSectionSize(20)
        self.horizontalHeader().setDefaultSectionSize(64)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setVisible(True)
        self.itemChanged.connect(self._on_item_changed)

    def clear_rows(self):
        self._current_row = -1
        self._highlight_refs.clear()
        self.clearSelection()

    def load_pattern(self, pattern) -> None:
        self.setRowCount(0)
        self.setColumnCount(0)
        self._pattern = pattern
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._refresh_grid()

    def _refresh_grid(self) -> None:
        self._loading = True
        self._highlight_refs.clear()
        self._current_row = -1
        self.setRowCount(0)
        self.setColumnCount(0)
        if self._pattern is None:
            self._loading = False
            return
        rows = int(getattr(self._pattern, "n_rows", 0) or 0)
        channels = int(getattr(self._pattern, "n_channels", 0) or 0)
        self.setRowCount(rows)
        self.setColumnCount(channels * COLUMNS_PER_CHANNEL)
        headers = []
        for c in range(channels):
            for sub in range(COLUMNS_PER_CHANNEL):
                label = f"Ch{c} {_COL_LABELS[sub]}" if sub == COL_NOTE else _COL_LABELS[sub]
                headers.append(label)
        self.setHorizontalHeaderLabels(headers)
        data = getattr(self._pattern, "data", None) or []
        for ch in range(channels):
            if ch >= len(data):
                continue
            chan = data[ch]
            for r in range(rows):
                if r >= len(chan):
                    continue
                note = chan[r]
                texts = [_note_text(note), _inst_text(note), _vol_text(note), _eff_text(note)]
                for sub in range(COLUMNS_PER_CHANNEL):
                    item = QTableWidgetItem(texts[sub])
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(r, ch * COLUMNS_PER_CHANNEL + sub, item)
        self._current_row = -1
        self._loading = False

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._loading or self._pattern is None or item is None:
            return
        row = item.row()
        col = item.column()
        ch = col // COLUMNS_PER_CHANNEL
        field = col % COLUMNS_PER_CHANNEL
        data = getattr(self._pattern, "data", None) or []
        if ch >= len(data) or row >= len(data[ch]):
            return
        note = data[ch][row]
        parsed = self._parse_field(field, item.text())
        if parsed is None or self._parsed_is_current(note, field, parsed):
            self._set_item_text(item, self._field_text(note, field))
            return
        self._push_undo()
        self._apply_field(note, field, parsed)
        self._set_item_text(item, self._field_text(note, field))
        self.patternChanged.emit()

    def _parse_field(self, field: int, text: str):
        if field == COL_NOTE:
            return _parse_note(text)
        if field == COL_INS:
            return _parse_inst(text)
        if field == COL_VOL:
            return _parse_vol(text)
        if field == COL_EFF:
            return _parse_effect(text)
        return None

    def _parsed_is_current(self, note, field: int, parsed) -> bool:
        if field == COL_NOTE:
            return (getattr(note, "period", "") or "") == parsed
        if field == COL_INS:
            return int(getattr(note, "instrument_idx", 0) or 0) == int(parsed)
        if field == COL_VOL:
            cmd, val = parsed
            if hasattr(note, "vol_cmd"):
                return str(getattr(note, "vol_cmd", "") or "") == cmd and int(
                    getattr(note, "vol_val", -1) or -1) == val
            if hasattr(note, "volume"):
                return int(getattr(note, "volume", -1) or -1) == val
            return False
        if field == COL_EFF:
            return (getattr(note, "effect", "") or "") == parsed
        return False

    def _apply_field(self, note, field: int, parsed) -> None:
        if field == COL_NOTE:
            note.period = parsed
        elif field == COL_INS:
            note.instrument_idx = int(parsed)
        elif field == COL_VOL:
            cmd, val = parsed
            if hasattr(note, "vol_cmd"):
                note.vol_cmd = cmd
                note.vol_val = val
            elif hasattr(note, "volume"):
                note.volume = val
        elif field == COL_EFF:
            note.effect = parsed

    def _field_text(self, note, field: int) -> str:
        if field == COL_NOTE:
            return _note_text(note)
        if field == COL_INS:
            return _inst_text(note)
        if field == COL_VOL:
            return _vol_text(note)
        return _eff_text(note)

    def _set_item_text(self, item: QTableWidgetItem, text: str) -> None:
        self._loading = True
        try:
            item.setText(text)
        finally:
            self._loading = False

    def _empty_parsed(self, field: int):
        if field in (COL_NOTE, COL_EFF):
            return ""
        if field == COL_INS:
            return 0
        return ("", -1)

    def _current_cell(self):
        item = self.currentItem()
        if item is None:
            return None
        return item.row(), item.column()

    def _push_undo(self) -> None:
        if self._pattern is None:
            return
        self._undo_stack.append(copy.deepcopy(getattr(self._pattern, "data", None)))
        if len(self._undo_stack) > 200:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack or self._pattern is None:
            return
        self._redo_stack.append(copy.deepcopy(getattr(self._pattern, "data", None)))
        self._pattern.data = self._undo_stack.pop()
        self._refresh_after_structure()

    def redo(self) -> None:
        if not self._redo_stack or self._pattern is None:
            return
        self._undo_stack.append(copy.deepcopy(getattr(self._pattern, "data", None)))
        self._pattern.data = self._redo_stack.pop()
        self._refresh_after_structure()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def _refresh_after_structure(self) -> None:
        current = self.currentItem()
        keep = (current.row(), current.column()) if current is not None else (0, 0)
        self._refresh_grid()
        if self.rowCount() and self.columnCount():
            r = max(0, min(keep[0], self.rowCount() - 1))
            c = max(0, min(keep[1], self.columnCount() - 1))
            self.setCurrentCell(r, c)
        self.patternChanged.emit()

    def highlight_row(self, row: int) -> None:
        if row == self._current_row and self._highlight_refs:
            return
        for _, item in self._highlight_refs:
            if item is not None:
                try:
                    item.setBackground(_BASE_BRUSH)
                except RuntimeError:
                    pass
        self._highlight_refs = []
        self._current_row = row
        if row < 0 or row >= self.rowCount():
            return
        refs = []
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item is not None:
                item.setBackground(_HIGHLIGHT_BRUSH)
                refs.append((col, item))
        self._highlight_refs = refs
        first = self.item(row, 0) if self.item(row, 0) else None
        self.scrollToItem(first)
