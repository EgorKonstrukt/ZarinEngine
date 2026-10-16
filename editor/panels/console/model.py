# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import re
import time as _time
from PySide6.QtWidgets import QListWidget
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtWidgets import QStyle
from core.foundation.logger import LogLevel, LogEntry

_NUM_RE = re.compile(r"\d+(\.\d+)?")


def _normalize(msg: str) -> str:
    return _NUM_RE.sub("{n}", msg)


def _fmt_time(ts: float) -> str:
    return _time.strftime("%H:%M:%S", _time.localtime(ts))


class ConsoleGroup:
    def __init__(self, entry: LogEntry):
        self.message: str = entry.message
        self._pattern: str = _normalize(entry.message)
        self.level: LogLevel = entry.level
        self.traceback: str = entry.traceback_str or ""
        self.count: int = 1
        self.entries: list[LogEntry] = [entry]
        self.list_item: QListWidgetItem | None = None

    def matches(self, entry: LogEntry) -> bool:
        return (self._pattern == _normalize(entry.message)
                and self.level == entry.level
                and (entry.traceback_str or "") == self.traceback)

    def display_text(self) -> str:
        ts = _fmt_time(self.entries[0].timestamp)
        level_names = {LogLevel.DEBUG: "DEBUG", LogLevel.INFO: "INFO",
                       LogLevel.WARNING: "WARNING", LogLevel.ERROR: "ERROR"}
        label = f"[{ts}] {level_names.get(self.level, 'INFO')}: {self.message}"
        if self.count > 1:
            label += f"  ({self.count})"
        return label


_LEVEL_COLORS = {
    LogLevel.DEBUG: (QColor(chr(35) + "c0c0c0"), QColor(chr(35) + "2d2d2d")),
    LogLevel.INFO: (QColor(chr(35) + "ffffff"), QColor(chr(35) + "1a2a4a")),
    LogLevel.WARNING: (QColor(chr(35) + "ffffff"), QColor(chr(35) + "3a2e00")),
    LogLevel.ERROR: (QColor(chr(35) + "ffffff"), QColor(chr(35) + "4a1a1a")),
}

_LEVEL_STD_ICONS = {
    LogLevel.DEBUG: QStyle.StandardPixmap.SP_ArrowRight,
    LogLevel.INFO: QStyle.StandardPixmap.SP_MessageBoxInformation,
    LogLevel.WARNING: QStyle.StandardPixmap.SP_MessageBoxWarning,
    LogLevel.ERROR: QStyle.StandardPixmap.SP_MessageBoxCritical,
}


class _LogList(QListWidget):
    def __init__(self, panel: ConsolePanel, parent=None):
        super().__init__(parent)
        self._panel = panel

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if item is None:
            self.clearSelection()
            self.setCurrentItem(None)
            self._panel._deselect()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.matches(QKeySequence.StandardKey.Copy):
            items = self.selectedItems()
            if items:
                from PySide6.QtWidgets import QApplication
                lines = [item.text() for item in items]
                QApplication.clipboard().setText("\n".join(lines))
            return
        super().keyPressEvent(event)
