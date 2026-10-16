# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun


from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu

try:
    import editor.icons as qta
except ImportError:
    qta = None


_QTA_COLORS = {"\x23d4d4d4": "\x23d4d4d4"}


def _qta_icon(name: str) -> QIcon:
    if qta is None:
        return QIcon()
    return qta.icon(name, color="\x23d4d4d4")


def _icon_for_script(path: str) -> QIcon:
    ext = os.path.splitext(path)[1].lower()
    mapping = {
        ".py": "fa5b.python",
        ".pyx": "fa5b.python",
        ".txt": "fa5s.file-alt",
        ".md": "fa5s.file-alt",
        ".json": "fa5s.file-code",
        ".xml": "fa5s.file-code",
        ".yaml": "fa5s.file-code",
        ".yml": "fa5s.file-code",
        ".toml": "fa5s.file-code",
        ".cfg": "fa5s.file-code",
        ".ini": "fa5s.file-code",
        ".csv": "fa5s.file-csv",
        ".html": "fa5s.file-code",
        ".css": "fa5s.file-code",
        ".js": "fa5s.file-code",
        ".ts": "fa5s.file-code",
        ".sh": "fa5s.terminal",
        ".bat": "fa5s.terminal",
        ".ps1": "fa5s.terminal",
        ".cpp": "fa5s.file-code",
        ".h": "fa5s.file-code",
        ".rs": "fa5s.file-code",
        ".go": "fa5s.file-code",
    }
    name = mapping.get(ext, "fa5s.file")
    return _qta_icon(name)


class SceneTabPeersMixin:
    def find_prefab_tab(self) -> Optional[str]:
        for name, info in self._tabs.items():
            if info.prefab_path:
                return name
        return None

    def update_peer_indicators(self, tab_peers: dict[str, list[list[float]]]):
        DOT_SIZE = 8
        PAD = 2
        for tab_name in self._tab_names:
            colors = tab_peers.get(tab_name, [])
            idx = self._scene_tab_idx(tab_name)
            if idx < 0:
                continue
            self._set_tab_icon(idx, colors)

    def update_script_peer_indicators(self, script_peers: dict[str, list[list[float]]]):
        DOT_SIZE = 8
        PAD = 2
        for i in range(self._tab_bar.count()):
            if not self.is_script_tab(i):
                continue
            path = self.script_path_at(i)
            colors = script_peers.get(path, [])
            self._set_tab_icon(i, colors)

    def _set_tab_icon(self, idx: int, colors: list[list[float]]):
        DOT_SIZE = 8
        PAD = 2
        if colors:
            n = len(colors)
            pw = DOT_SIZE * n + PAD * (n - 1) + PAD * 2
            ph = DOT_SIZE + PAD * 2
            pix = QPixmap(pw, ph)
            pix.fill(Qt.GlobalColor.transparent)
            with QPainter(pix) as p:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                for i, rgb in enumerate(colors):
                    r, g, b = (int(c * 255) for c in rgb[:3])
                    p.setBrush(QBrush(QColor(r, g, b)))
                    p.setPen(Qt.PenStyle.NoPen)
                    cx = PAD + i * (DOT_SIZE + PAD) + DOT_SIZE // 2
                    cy = PAD + DOT_SIZE // 2
                    p.drawEllipse(cx - DOT_SIZE // 2, cy - DOT_SIZE // 2, DOT_SIZE, DOT_SIZE)
            self._tab_bar.setTabIcon(idx, QIcon(pix))
        else:
            self._tab_bar.setTabIcon(idx, QIcon())

    def _on_context_menu(self, pos):
        try:
            bar = self._tab_bar
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
            if not self.is_script_tab(idx):
                nm = self.tab_name_at(idx)
                pin_act = menu.addAction("Unpin Tab" if (nm is not None and self.is_pinned(nm)) else "Pin Tab")
                pin_act.triggered.connect(lambda checked=False, _i=idx: self._toggle_pin_at(_i))
            dup = self.duplicate_count(idx)
            if dup > 0:
                dup_act = menu.addAction(f"Close Duplicate Tabs ({dup})")
            else:
                dup_act = menu.addAction("Close Duplicate Tabs")
                dup_act.setEnabled(False)
            dup_act.triggered.connect(lambda checked=False, _i=idx: self.close_duplicate_tabs(_i))
            multi = menu.addMenu("Close Multiple Tabs")
            left = idx
            right = bar.count() - idx - 1
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
            other_act.setEnabled(bar.count() > 1)
            other_act.triggered.connect(lambda checked=False, _i=idx: self.close_other_tabs(_i))
            nofile_act = multi.addAction("Close Tabs without File")
            nofile_act.triggered.connect(lambda checked=False: self.close_fileless_tabs())
            sort_act = menu.addAction("Sort Scene Tabs by Name")
            sort_act.triggered.connect(lambda checked=False: self.sort_scene_tabs())
            reopen_act = menu.addAction("Reopen Closed Tab")
            reopen_act.setEnabled(self.can_reopen())
            reopen_act.triggered.connect(lambda: self.reopen_closed_tab())
            try:
                menu.exec(bar.mapToGlobal(pos))
            except Exception:
                pass
        except Exception:
            pass
