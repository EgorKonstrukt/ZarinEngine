# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton, QCheckBox, QTabWidget
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from core.config.editor_scale import scale
from .timeline import TimelineOverview, TimelineWidget, _FONT_BOLD, _FONT_SMALL
from .views import HierarchyView, ProfilerHeader
from .flame import FlameGraphWidget


class ProfilerPanel(QDockWidget):
    def __init__(self, engine, parent=None):
        super().__init__("Profiler", parent)
        self._engine = engine
        self._selected_frame_idx = -1
        self._updating_toggle = False
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(200)
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            enabled = bool(cfg.get("profiler.enabled", False))
        except Exception:
            enabled = False
        prof = getattr(engine, "_profiler", None)
        if prof is not None:
            prof.enabled = enabled
            prof.capture_frames = bool(enabled and self.isVisible())
        self._sync_toggle()
        self._update_timer_state()
    def showEvent(self, ev):
        super().showEvent(ev)
        prof = getattr(self._engine, "_profiler", None)
        if prof is not None and bool(getattr(prof, "enabled", False)):
            prof.capture_frames = True
        self._update_timer_state()
    def hideEvent(self, ev):
        super().hideEvent(ev)
        prof = getattr(self._engine, "_profiler", None)
        if prof is not None:
            prof.capture_frames = False
        if self._timer.isActive():
            self._timer.stop()
    def load_config(self, config) -> None:
        try:
            refresh_interval = int(config.get("profiler.refresh_interval", 200))
            self._timer.setInterval(refresh_interval)
        except Exception:
            pass
        try:
            enabled = bool(config.get("profiler.enabled", False))
        except Exception:
            return
        prof = getattr(self._engine, "_profiler", None)
        if prof is not None:
            if bool(prof.enabled) != enabled:
                prof.enabled = enabled
                prof.capture_frames = bool(enabled and self.isVisible())
                if not enabled:
                    self._clear_views()
        self._sync_toggle()
        self._update_timer_state()
    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        bar_layout.setSpacing(10)
        self._enabled_toggle = QCheckBox("Enabled")
        self._enabled_toggle.setFont(_FONT_BOLD)
        self._enabled_toggle.toggled.connect(self._on_toggle)
        bar_layout.addWidget(self._enabled_toggle)
        self._status_lbl = QLabel("Paused")
        self._status_lbl.setFont(_FONT_SMALL)
        bar_layout.addWidget(self._status_lbl)
        bar_layout.addStretch()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(scale(72))
        self._clear_btn.setFixedHeight(scale(24))
        self._clear_btn.clicked.connect(self._on_clear)
        bar_layout.addWidget(self._clear_btn)
        layout.addWidget(bar)
        self._header = ProfilerHeader()
        layout.addWidget(self._header)
        self._timeline_overview = TimelineOverview()
        layout.addWidget(self._timeline_overview)
        self._tabs = QTabWidget()
        self._hierarchy_tree = HierarchyView()
        self._tabs.addTab(self._hierarchy_tree, "Hierarchy")
        self._timeline_widget = TimelineWidget()
        self._tabs.addTab(self._timeline_widget, "Timeline")
        self._flame_graph = FlameGraphWidget()
        scroll_fg = QScrollArea()
        scroll_fg.setWidgetResizable(True)
        scroll_fg.setWidget(self._flame_graph)
        self._tabs.addTab(scroll_fg, "Flame Graph")
        layout.addWidget(self._tabs, 1)
        self.setWidget(container)
    def _on_toggle(self, checked: bool):
        if getattr(self, "_updating_toggle", False):
            return
        checked = bool(checked)
        prof = getattr(self._engine, "_profiler", None)
        if prof is not None:
            if checked:
                prof.enabled = True
                prof.capture_frames = bool(self.isVisible())
            else:
                prof.capture_frames = False
                prof.enabled = False
                self._clear_views()
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            cfg.set("profiler.enabled", checked, notify=False)
            cfg.save()
        except Exception:
            pass
        self._sync_toggle()
        self._update_timer_state()
    def _on_clear(self):
        prof = getattr(self._engine, "_profiler", None)
        if prof is not None:
            prof.reset()
        self._clear_views()
    def _clear_views(self):
        try:
            self._timeline_overview.clear_data()
        except Exception:
            pass
        try:
            self._timeline_widget.clear_data()
        except Exception:
            pass
        try:
            self._hierarchy_tree.clear_data()
        except Exception:
            pass
        try:
            self._flame_graph.clear_data()
        except Exception:
            pass
        self._selected_frame_idx = -1
    def _sync_toggle(self):
        prof = getattr(self._engine, "_profiler", None)
        enabled = bool(getattr(prof, "enabled", False)) if prof is not None else False
        self._updating_toggle = True
        try:
            self._enabled_toggle.blockSignals(True)
            self._enabled_toggle.setChecked(enabled)
            self._enabled_toggle.blockSignals(False)
            if enabled:
                self._status_lbl.setText("Recording")
            else:
                self._status_lbl.setText("Paused")
        finally:
            self._updating_toggle = False
    def _update_timer_state(self):
        prof = getattr(self._engine, "_profiler", None)
        enabled = bool(getattr(prof, "enabled", False)) if prof is not None else False
        if enabled and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            if self._timer.isActive():
                self._timer.stop()
    def _select_frame(self, idx: int):
        self._selected_frame_idx = idx
    def _get_fps(self):
        eng = self._engine
        vp = eng.viewport if hasattr(eng, "viewport") else None
        if vp and hasattr(vp, "_fps") and vp._fps > 0:
            return vp._fps
        if hasattr(eng, "fps") and eng.fps > 0:
            return eng.fps
        prof = getattr(eng, "_profiler", None)
        if prof:
            frames = prof.frames
            if len(frames) >= 2:
                recent = frames[-min(len(frames), 30):]
                total_ms = sum(f.frame_time_ms for f in recent)
                if total_ms > 0:
                    return len(recent) / (total_ms / 1000.0)
        return 0.0
    def _refresh(self):
        if not self.isVisible():
            return
        eng = self._engine
        fps = self._get_fps()
        prof = eng._profiler if hasattr(eng, "_profiler") else None
        if not prof:
            return
        if not bool(getattr(prof, "enabled", False)):
            return
        frames = prof.frames
        if not frames:
            return
        num_avg = min(15, len(frames))
        recent = frames[-num_avg:]
        last = frames[-1]
        flat = last.flat_data
        avg_frame_time = sum(f.frame_time_ms for f in recent) / num_avg
        agg = {}
        for f in recent:
            for s in f.samples:
                if s.name not in agg:
                    agg[s.name] = {"total": 0.0, "count": 0, "depth": s.depth}
                agg[s.name]["total"] += s.duration_ms
                agg[s.name]["count"] += 1
        from core.foundation.profiler import ProfileSample
        start_map: dict[str, float] = {}
        for s in last.samples:
            if s.name not in start_map:
                start_map[s.name] = s.start_ms
        averaged_samples = []
        for name, data in agg.items():
            st = start_map.get(name, 0.0)
            averaged_samples.append(
                ProfileSample(name, data["depth"], st, data["total"] / num_avg, QColor(170, 170, 170).name())
            )
        avg_flat = {}
        for f in recent:
            for key, val in f.flat_data.items():
                avg_flat[key] = avg_flat.get(key, 0.0) + val
        for key in avg_flat:
            avg_flat[key] /= num_avg
        self._timeline_overview.add_frame(flat, last.frame_time_ms)
        self._timeline_widget.add_frame(flat)
        fc = last.frame_number
        all_times = [f.frame_time_ms for f in frames]
        min_ms = min(all_times) if all_times else 0.0
        overall_avg = sum(all_times) / len(all_times) if all_times else 0.0
        max_ms = max(all_times) if all_times else 0.0
        self._header.update_stats(fps, fc, avg_frame_time, min_ms, overall_avg, max_ms)
        tab_idx = self._tabs.currentIndex()
        if tab_idx == 0:
            self._hierarchy_tree.set_frame_data(averaged_samples, avg_frame_time, avg_flat)
        elif tab_idx == 2:
            self._flame_graph.set_data(last.samples, last.frame_time_ms)
