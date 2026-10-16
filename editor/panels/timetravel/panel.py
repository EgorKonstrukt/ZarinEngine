# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QLineEdit, QTabWidget, QTreeWidget, QTreeWidgetItem, QCheckBox
from PySide6.QtCore import Qt, QTimer
import editor.icons as qta
from PySide6.QtGui import QColor
from core.engine.eng import Engine
from core.foundation.time_travel import SnapshotRecorder, FrameSnapshot, find_entity_frame_changes
from core.config.editor_scale import scale
from editor.panels.timetravel.playback import _TimelineScrubber, TimeTravelPlaybackMixin
from editor.panels.timetravel.recorder import TimeTravelRecorderMixin
_H = chr(35)
_C_BG = QColor(_H + "1e1e2e")
_C_RULER = QColor(_H + "252535")
_C_RULER_TICK = QColor(_H + "555566")
_C_RULER_LABEL = QColor(_H + "888899")
_C_RULER_LINE = QColor(_H + "3a3a4a")
_C_PLAYHEAD = QColor(_H + "ffcc00")
_C_HOVER = QColor(_H + "7ec8e3")
_C_BOOKMARK = QColor(_H + "ff6688")
_C_BREAKPOINT = QColor(_H + "ff4444")
_C_TEXT = QColor(_H + "cccccc")
_C_DIM = QColor(_H + "888888")
_C_DIFF_ADD = QColor(_H + "44cc44")
_C_DIFF_DEL = QColor(_H + "cc4444")
_C_DIFF_CHG = QColor(_H + "cccc44")
class _DiffTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Change", "Detail"])
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.setStyleSheet("QTreeWidget { background: " + _H + "1e1e2e; color: " + _H + "ccc; border: none; font-size: 11px; } QTreeWidget::item { padding: 2px 4px; } QTreeWidget::item:alternate { background: " + _H + "252535; }")
        self.header().setStretchLastSection(True)
    def show_diff(self, diff: dict, names: Optional[dict] = None):
        self.clear()
        names = names or {}
        for eid in diff.get("created", []):
            name = names.get(eid, eid)
            item = QTreeWidgetItem(["+ " + str(name), "created"])
            item.setForeground(0, _C_DIFF_ADD)
            self.addTopLevelItem(item)
        for eid in diff.get("deleted", []):
            name = names.get(eid, eid)
            item = QTreeWidgetItem(["  " + str(name), "deleted"])
            item.setForeground(0, _C_DIFF_DEL)
            self.addTopLevelItem(item)
        for eid, changes in diff.get("changed", {}).items():
            name = names.get(eid, eid)
            parent = QTreeWidgetItem(["~ " + str(name), ""])
            parent.setForeground(0, _C_DIFF_CHG)
            self.addTopLevelItem(parent)
            for c in changes:
                tag = c[0]
                if tag == "name":
                    child = QTreeWidgetItem(["  name: " + str(c[1]) + " -> " + str(c[2]), ""])
                elif tag == "+comp":
                    child = QTreeWidgetItem(["  + " + str(c[1]), ""])
                    child.setForeground(0, _C_DIFF_ADD)
                elif tag == "-comp":
                    child = QTreeWidgetItem(["  - " + str(c[1]), ""])
                    child.setForeground(0, _C_DIFF_DEL)
                elif tag == "~comp":
                    cparent = QTreeWidgetItem(["  ~ " + str(c[1]), ""])
                    cparent.setForeground(0, _C_DIFF_CHG)
                    parent.addChild(cparent)
                    for field, ov, nv in c[2]:
                        QTreeWidgetItem(cparent, ["    " + str(field) + ": " + str(ov) + " -> " + str(nv), ""])
                    continue
                parent.addChild(child)
            parent.setExpanded(True)
    def show_entity_changes(self, frames: list[FrameSnapshot], entity_id: str, entity_name: str):
        self.clear()
        indices = find_entity_frame_changes(frames, entity_id)
        item = QTreeWidgetItem(["Entity: " + str(entity_name) + " (" + str(entity_id) + ")", ""])
        self.addTopLevelItem(item)
        for idx in indices:
            snap = frames[idx]
            child = QTreeWidgetItem(["  Frame " + str(snap.frame_number), str(snap.entity_count) + "e"])
            item.addChild(child)
        item.setExpanded(True)
class TimeTravelPanel(TimeTravelRecorderMixin, TimeTravelPlaybackMixin, QDockWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Time Travel", parent)
        self._engine = engine
        self._recorder: Optional[SnapshotRecorder] = None
        self._restored: bool = False
        self._live_data: Optional[dict] = None
        self._playing: bool = False
        self._prev_frame_data: Optional[dict] = None
        self._diff_cache: Optional[dict] = None
        self._diff_names: Optional[dict] = None
        if not getattr(engine, "_time_travel_recorder", None):
            engine._time_travel_recorder = SnapshotRecorder()
        self._recorder = engine._time_travel_recorder
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._play_step)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.setInterval(200)
        self._setup_ui()
    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        r1 = QHBoxLayout()
        r1.setSpacing(2)
        def btn(icon, tip, cb, w=26):
            b = QPushButton(icon, "")
            b.setToolTip(tip)
            b.setFixedSize(scale(w), scale(24))
            b.clicked.connect(cb)
            r1.addWidget(b)
            return b
        self._first_btn = btn(qta.icon("fa5s.fast-backward", color=_H + "d4d4d4"), "First", self._go_first)
        self._b10_btn = btn(qta.icon("fa5s.backward", color=_H + "d4d4d4"), "Back 10", self._go_back10)
        self._b1_btn = btn(qta.icon("fa5s.caret-left", color=_H + "d4d4d4"), "Back 1", self._go_back1)
        self._play_btn = btn(qta.icon("fa5s.play", color=_H + "d4d4d4"), "Play (Space)", self._toggle_play)
        self._f1_btn = btn(qta.icon("fa5s.caret-right", color=_H + "d4d4d4"), "Forward 1", self._go_forward1)
        self._f10_btn = btn(qta.icon("fa5s.forward", color=_H + "d4d4d4"), "Forward 10", self._go_forward10)
        self._last_btn = btn(qta.icon("fa5s.fast-forward", color=_H + "d4d4d4"), "Last", self._go_last)
        r1.addSpacing(6)
        self._record_btn = btn(qta.icon("fa5s.dot-circle", color=_H + "ff4444"), "Record snapshots", self._toggle_record, w=28)
        self._record_btn.setCheckable(True)
        self._record_btn.setStyleSheet("QPushButton:checked { color: " + _H + "fff; background: " + _H + "cc2222; }")
        r1.addSpacing(6)
        self._live_btn = btn(qta.icon("fa5s.undo", color=_H + "d4d4d4"), "Return to live scene", self._go_live, w=24)
        self._live_btn.setEnabled(False)
        r1.addSpacing(4)
        r1.addWidget(QLabel("Spd:"))
        self._speed_sb = QDoubleSpinBox()
        self._speed_sb.setRange(0.1, 10.0)
        self._speed_sb.setValue(1.0)
        self._speed_sb.setSingleStep(0.25)
        self._speed_sb.setFixedWidth(scale(55))
        self._speed_sb.valueChanged.connect(self._on_speed_changed)
        r1.addWidget(self._speed_sb)
        r1.addStretch()
        export_btn = btn(qta.icon("fa5s.save", color=_H + "d4d4d4"), "Export current frame as .zpes", self._export_frame, w=40)
        layout.addLayout(r1)
        r2 = QHBoxLayout()
        r2.setSpacing(4)
        r2.addWidget(QLabel("BP:"))
        self._bp_input = QLineEdit()
        self._bp_input.setPlaceholderText("entity_count > 5 and frame > 10")
        self._bp_input.setFixedHeight(scale(22))
        self._bp_input.returnPressed.connect(self._set_breakpoint)
        r2.addWidget(self._bp_input)
        bp_clear = QPushButton(qta.icon("fa5s.times", color=_H + "d4d4d4"), "")
        bp_clear.setFixedSize(scale(20), scale(22))
        bp_clear.clicked.connect(self._clear_breakpoint)
        r2.addWidget(bp_clear)
        layout.addLayout(r2)
        r3 = QHBoxLayout()
        r3.setSpacing(8)
        self._heat_cb = QCheckBox("Heatmap")
        self._heat_cb.toggled.connect(self._on_heatmap_toggled)
        r3.addWidget(self._heat_cb)
        self._dedup_cb = QCheckBox("Skip unchanged")
        self._dedup_cb.toggled.connect(self._on_dedup_toggled)
        r3.addWidget(self._dedup_cb)
        r3.addWidget(QLabel("Every:"))
        self._interval_sb = QSpinBox()
        self._interval_sb.setRange(1, 60)
        self._interval_sb.setValue(1)
        self._interval_sb.setFixedWidth(scale(45))
        self._interval_sb.valueChanged.connect(self._on_interval_changed)
        r3.addWidget(self._interval_sb)
        r3.addWidget(QLabel("f"))
        r3.addStretch()
        clear_btn = btn(qta.icon("fa5s.trash-alt", color=_H + "d4d4d4"), "Clear all frames", self._clear, w=50)
        layout.addLayout(r3)
        self._timeline = _TimelineScrubber()
        layout.addWidget(self._timeline)
        info = QHBoxLayout()
        self._frame_lbl = QLabel("No frames")
        self._frame_lbl.setStyleSheet("color: " + _H + "ccc; font-size: 11px;")
        info.addWidget(self._frame_lbl)
        info.addStretch()
        self._status_lbl = QLabel("Idle")
        self._status_lbl.setStyleSheet("color: " + _H + "888; font-size: 11px;")
        info.addWidget(self._status_lbl)
        layout.addLayout(info)
        self._bottom_tabs = QTabWidget()
        self._bottom_tabs.setStyleSheet("QTabWidget::pane { background: " + _H + "1e1e2e; border: 1px solid " + _H + "3a3a4a; } QTabBar::tab { background: " + _H + "252535; color: " + _H + "888; padding: 2px 8px; } QTabBar::tab:selected { background: " + _H + "1e1e2e; color: " + _H + "ffcc00; }")
        self._diff_tree = _DiffTree()
        self._bottom_tabs.addTab(self._diff_tree, "Diff")
        self._bottom_tabs.currentChanged.connect(self._on_tab_changed)
        self._bk_tree = QTreeWidget()
        self._bk_tree.setHeaderLabels(["Frame", "Entities", "Time"])
        self._bk_tree.setAlternatingRowColors(True)
        self._bk_tree.setStyleSheet(self._diff_tree.styleSheet())
        self._bk_tree.itemDoubleClicked.connect(self._on_bookmark_clicked)
        self._bottom_tabs.addTab(self._bk_tree, "Bookmarks")
        search_container = QWidget()
        search_layout = QVBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Entity ID or name...")
        self._search_input.setFixedHeight(scale(22))
        self._search_input.returnPressed.connect(self._do_entity_search)
        self._search_tree = QTreeWidget()
        self._search_tree.setHeaderLabels(["Frames where entity changed"])
        self._search_tree.setAlternatingRowColors(True)
        self._search_tree.setStyleSheet(self._diff_tree.styleSheet())
        self._search_tree.itemDoubleClicked.connect(self._on_search_result_clicked)
        search_layout.addWidget(self._search_input)
        search_layout.addWidget(self._search_tree)
        self._bottom_tabs.addTab(search_container, "Find Entity")
        self._bottom_tabs.setMaximumHeight(scale(180))
        layout.addWidget(self._bottom_tabs)
        self.setWidget(w)
    def _on_tab_changed(self, tab_index: int):
        if tab_index == 0:
            self._refresh_diff_tab()
    def _refresh_diff_tab(self):
        self._diff_tree.clear()
        if self._diff_cache:
            self._diff_tree.show_diff(self._diff_cache, self._diff_names)
        else:
            self._diff_tree.addTopLevelItem(
                QTreeWidgetItem(["Select two frames to see changes", ""]))
    def _on_bookmark_toggle(self, idx: int):
        if self._recorder:
            self._recorder.toggle_bookmark(idx)
            self._refresh_bookmarks()
    def _on_bookmark_clicked(self, item, col):
        text = item.text(0)
        if text.isdigit():
            self._on_frame_restore(int(text))
    def _on_search_result_clicked(self, item, col):
        text = item.text(0)
        if text.startswith("Frame "):
            try:
                self._on_frame_restore(int(text.split()[1]))
            except (ValueError, IndexError):
                pass
    def _do_entity_search(self):
        if not self._recorder:
            return
        query = self._search_input.text().strip().lower()
        if not query:
            return
        frames = self._recorder.frames()
        self._search_tree.clear()
        found = False
        for snap in reversed(frames):
            for eid, edata in snap.data.get("entities", {}).items():
                name = edata.get("name", "")
                if query in eid.lower() or query in name.lower():
                    item = QTreeWidgetItem(["Frame " + str(snap.frame_number) + "  " + str(name) + " (" + str(eid) + ")"])
                    self._search_tree.addTopLevelItem(item)
                    found = True
                    break
        if not found:
            self._search_tree.addTopLevelItem(QTreeWidgetItem(["No matches"]))
    def _refresh_bookmarks(self):
        if not self._recorder:
            self._bk_tree.clear()
            return
        self._bk_tree.clear()
        for i in self._recorder.bookmarked_indices():
            snap = self._recorder.get_frame(i)
            if snap:
                item = QTreeWidgetItem([
                    str(snap.frame_number),
                    str(snap.entity_count),
                    f"{snap.frame_time_ms:.1f}ms" if snap.frame_time_ms > 0 else ""
                ])
                self._bk_tree.addTopLevelItem(item)
    def _update_labels(self, snap: FrameSnapshot):
        parts = ["Frame " + str(snap.frame_number)]
        if snap.entity_count >= 0:
            parts.append(str(snap.entity_count) + " entities")
        if snap.frame_time_ms > 0:
            parts.append(f"{snap.frame_time_ms:.1f}ms")
        if snap.bookmarked:
            parts.append("BM")
        if snap.breakpoint_hit:
            parts.append("BP")
        self._frame_lbl.setText("  ".join(parts))
        self._status_lbl.setText(f"Viewing {_H}{snap.frame_number}")
    def load_config(self, config):
        pass
    def save_config(self, config):
        pass
