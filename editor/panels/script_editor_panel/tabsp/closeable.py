# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
from PyQt6.QtWidgets import QTabWidget, QMenu
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from ..theme import tab_stylesheet


class _CloseableTabWidgetBase(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.tabCloseRequested.connect(self._on_close_requested)
        self.setStyleSheet(tab_stylesheet())
        self._closed_stack: list[dict] = []
        self._max_closed = 25
        try:
            bar = self.tabBar()
            bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            bar.customContextMenuRequested.connect(self._on_context_menu)
        except Exception:
            pass
        try:
            self._reopen_action = QAction("Reopen Closed Tab", self)
            self._reopen_action.triggered.connect(lambda: self.reopen_closed_tab())
            self.addAction(self._reopen_action)
        except Exception:
            pass

    def _on_close_requested(self, index: int):
        self.close_tab_at(index)

    def _norm_key(self, index: int) -> str:
        try:
            w = self.widget(index)
            p = getattr(w, "_file_path", "") or ""
            if p:
                return os.path.normcase(os.path.normpath(p))
            return ""
        except Exception:
            return ""

    def _duplicate_indices(self, index: int) -> list[int]:
        try:
            if index < 0 or index >= self.count():
                return []
            key = self._norm_key(index)
            w0 = self.widget(index)
            p0 = getattr(w0, "_file_path", "") if w0 is not None else ""
            out: list[int] = []
            for i in range(self.count()):
                if i == index:
                    continue
                if self._norm_key(i) != key:
                    continue
                if not key:
                    out.append(i)
                else:
                    out.append(i)
            if not key:
                return out
            return out
        except Exception:
            return []

    def duplicate_count(self, index: int) -> int:
        return len(self._duplicate_indices(index))

    def can_reopen(self) -> bool:
        return len(self._closed_stack) > 0

    def _snapshot_at(self, index: int):
        try:
            if index < 0 or index >= self.count():
                return None
            w = self.widget(index)
            if w is None:
                return None
            try:
                path = getattr(w, "_file_path", "") or ""
            except Exception:
                path = ""
            try:
                content = w._editor.toPlainText()
            except Exception:
                content = ""
            try:
                dirty = bool(w._dirty)
            except Exception:
                dirty = False
            try:
                git = getattr(w, "_vcs_git", None)
            except Exception:
                git = None
            try:
                title = self.tabText(index)
            except Exception:
                title = ""
            return {"path": path, "content": content, "dirty": dirty, "index": index, "git": git, "title": title}
        except Exception:
            return None

    def _push_closed(self, entry):
        try:
            if entry is None:
                return
            self._closed_stack.append(entry)
            while len(self._closed_stack) > self._max_closed:
                self._closed_stack.pop(0)
        except Exception:
            pass

    def close_tab_at(self, index: int) -> bool:
        try:
            if index < 0 or index >= self.count():
                return False
            snap = self._snapshot_at(index)
            w = self.widget(index)
            if w is None:
                return False
            try:
                before = self.count()
            except Exception:
                before = -1
            try:
                w._close_self()
            except Exception:
                pass
            try:
                still = False
                for k in range(self.count()):
                    try:
                        if self.widget(k) is w:
                            still = True
                            break
                    except Exception:
                        continue
                if still:
                    return False
                if before >= 0 and self.count() >= before:
                    return False
            except Exception:
                pass
            if snap is not None:
                self._push_closed(snap)
            return True
        except Exception:
            return False

    def close_other_tabs(self, keep: int):
        try:
            if keep < 0 or keep >= self.count():
                return
            indices = [i for i in range(self.count()) if i != keep]
            indices.sort(reverse=True)
            for i in indices:
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    try:
                        if i < self.count() and self.widget(i) is not None:
                            break
                    except Exception:
                        break
        except Exception:
            pass

    def close_tabs_left(self, index: int):
        try:
            if index <= 0 or index >= self.count():
                return
            for i in range(index - 1, -1, -1):
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def close_tabs_right(self, index: int):
        try:
            if index < 0 or index >= self.count() - 1:
                return
            for i in range(self.count() - 1, index, -1):
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def close_duplicate_tabs(self, index: int):
        try:
            dup = self._duplicate_indices(index)
            dup.sort(reverse=True)
            for i in dup:
                if i < 0 or i >= self.count():
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def _parent_editor(self):
        try:
            p = self.parent()
            while p is not None:
                try:
                    if hasattr(p, "open_script") and hasattr(p, "_tabs"):
                        return p
                except Exception:
                    pass
                try:
                    p = p.parent()
                except Exception:
                    break
            return None
        except Exception:
            return None

    def _on_context_menu(self, pos):
        try:
            bar = self.tabBar()
            idx = bar.tabAt(pos)
            menu = QMenu(bar)
            if idx < 0:
                act = menu.addAction("Reopen Closed Tab")
                act.setEnabled(self.can_reopen())
                act.triggered.connect(lambda: self.reopen_closed_tab())
                try:
                    menu.exec(bar.mapToGlobal(pos))
                except Exception:
                    pass
                return
            close_act = menu.addAction("Close Tab")
            close_act.triggered.connect(lambda checked=False, _i=idx: self.close_tab_at(_i))
            dup = self.duplicate_count(idx)
            if dup > 0:
                dup_act = menu.addAction(f"Close Duplicate Tabs ({dup})")
            else:
                dup_act = menu.addAction("Close Duplicate Tabs")
                dup_act.setEnabled(False)
            dup_act.triggered.connect(lambda checked=False, _i=idx: self.close_duplicate_tabs(_i))
            multi = menu.addMenu("Close Multiple Tabs")
            left = idx
            right = self.count() - idx - 1
            left_act = multi.addAction("Close Tabs to the Left")
            left_act.setEnabled(left > 0)
            left_act.triggered.connect(lambda checked=False, _i=idx: self.close_tabs_left(_i))
            if right > 0:
                right_act = multi.addAction(f"Close Tabs to the Right ({right})")
            else:
                right_act = multi.addAction("Close Tabs to the Right")
                right_act.setEnabled(False)
            right_act.triggered.connect(lambda checked=False, _i=idx: self.close_tabs_right(_i))
            other_act = multi.addAction("Close Other Tabs")
            other_act.setEnabled(self.count() > 1)
            other_act.triggered.connect(lambda checked=False, _i=idx: self.close_other_tabs(_i))
            reopen_act = menu.addAction("Reopen Closed Tab")
            reopen_act.setEnabled(self.can_reopen())
            reopen_act.triggered.connect(lambda: self.reopen_closed_tab())
            try:
                menu.exec(bar.mapToGlobal(pos))
            except Exception:
                pass
        except Exception:
            pass

    def add_closeable_tab(self, widget, title: str) -> int:
        return self.addTab(widget, title)
