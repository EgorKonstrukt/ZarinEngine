from __future__ import annotations
import gc
import tracemalloc
from collections import deque

import os
from datetime import datetime

from collections import Counter

from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                             QHeaderView, QGroupBox, QGridLayout, QFileDialog,
                             QApplication, QPlainTextEdit)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QBrush


class TracemallocPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Tracemalloc Debug", parent)
        self.setObjectName("TracemallocDebugDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)

        root = QWidget()
        self.setWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._gc_group = QGroupBox("GC Collections")
        layout.addWidget(self._gc_group)
        gc_grid = QGridLayout(self._gc_group)
        self._gc_labels = {}
        for i, name in enumerate(["Gen 0", "Gen 1", "Gen 2", "Total"]):
            lbl = QLabel("0")
            lbl.setStyleSheet("font-family: monospace;")
            gc_grid.addWidget(QLabel(f"{name}:"), i, 0)
            gc_grid.addWidget(lbl, i, 1)
            self._gc_labels[name] = lbl
        self._gc_rate = QLabel("0  collections/s")
        self._gc_rate.setStyleSheet("font-family: monospace;")
        gc_grid.addWidget(self._gc_rate, 5, 0, 1, 2)

        self._trace_group = QGroupBox("tracemalloc")
        layout.addWidget(self._trace_group)
        trace_layout = QVBoxLayout(self._trace_group)

        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("Start")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)
        self._btn_snapshot = QPushButton("Snapshot")
        self._btn_snapshot.clicked.connect(self._on_snapshot)
        self._btn_snapshot.setEnabled(False)
        self._btn_clear = QPushButton("Clear")
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_stop)
        btn_row.addWidget(self._btn_snapshot)
        btn_row.addWidget(self._btn_clear)
        trace_layout.addLayout(btn_row)

        self._trace_status = QLabel("tracemalloc not started")
        self._trace_status.setStyleSheet("font-family: monospace; color: #888;")
        trace_layout.addWidget(self._trace_status)

        self._trace_tree = QTreeWidget()
        self._trace_tree.setHeaderLabels(["Location", "Size", "Count"])
        self._trace_tree.header().setStretchLastSection(False)
        self._trace_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._trace_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._trace_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._trace_tree.setRootIsDecorated(False)
        self._trace_tree.setAlternatingRowColors(True)
        trace_layout.addWidget(self._trace_tree)

        self._obj_group = QGroupBox("Object Counts (top types)")
        layout.addWidget(self._obj_group)
        obj_layout = QVBoxLayout(self._obj_group)
        self._obj_tree = QTreeWidget()
        self._obj_tree.setHeaderLabels(["Type", "Count", "Size (est.)"])
        self._obj_tree.header().setStretchLastSection(False)
        self._obj_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._obj_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._obj_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._obj_tree.setRootIsDecorated(False)
        self._obj_tree.setAlternatingRowColors(True)
        obj_layout.addWidget(self._obj_tree)

        self._gc_analysis_group = QGroupBox("GC Analysis")
        layout.addWidget(self._gc_analysis_group)
        analysis_layout = QVBoxLayout(self._gc_analysis_group)
        analysis_btn_row = QHBoxLayout()
        self._btn_analyze = QPushButton("Run Analysis")
        self._btn_analyze.clicked.connect(self._on_analyze)
        analysis_btn_row.addWidget(self._btn_analyze)
        self._analysis_status = QLabel("press Run Analysis to sample garbage")
        self._analysis_status.setStyleSheet("font-family: monospace; color: #888;")
        analysis_btn_row.addWidget(self._analysis_status, 1)
        analysis_layout.addLayout(analysis_btn_row)
        self._analysis_text = QPlainTextEdit()
        self._analysis_text.setReadOnly(True)
        self._analysis_text.setMaximumBlockCount(200)
        self._analysis_text.setStyleSheet("font-family: monospace; font-size: 9px; color: #ccc; background: #1e1e1e;")
        analysis_layout.addWidget(self._analysis_text)

        self._report_row = QHBoxLayout()
        self._btn_copy = QPushButton("Copy Report")
        self._btn_copy.clicked.connect(self._on_copy_report)
        self._btn_save = QPushButton("Save Report...")
        self._btn_save.clicked.connect(self._on_save_report)
        self._report_row.addWidget(self._btn_copy)
        self._report_row.addWidget(self._btn_save)
        layout.addLayout(self._report_row)

        self._gc_history: deque[int] = deque(maxlen=60)
        self._last_gc_counts = [0, 0, 0]
        self._prev_snapshot: tracemalloc.Snapshot | None = None

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(1000)

    def _build_short_report(self) -> str:
        lines = []
        counts = gc.get_count()
        thresh = gc.get_threshold()
        lines.append(f"GC collections: gen0={counts[0]}  gen1={counts[1]}  gen2={counts[2]}  total={sum(counts)}")
        lines.append(f"GC thresholds:  gen0={thresh[0]}  gen1={thresh[1]}  gen2={thresh[2]}")
        rate = sum(self._gc_history) / max(len(self._gc_history), 1)
        lines.append(f"GC rate: {rate:.1f} col/s")
        tracing = tracemalloc.is_tracing()
        lines.append(f"tracemalloc: {'RUNNING' if tracing else 'STOPPED'}")
        if tracing:
            cur, peak = tracemalloc.get_traced_memory()
            lines.append(f"traced memory: cur={cur/1024:.1f}K  peak={peak/1024:.1f}K")
            try:
                snap = tracemalloc.take_snapshot()
                stats = snap.statistics('lineno')[:10]
                lines.append(f"")
                lines.append("Top 10 allocators (file:line):")
                for st in stats:
                    lines.append(f"  {self._format_size(st.size):>10}  {st.count:>6}x  {str(st.traceback.format())[:100]}")
            except Exception:
                pass
        return "\n".join(lines)

    def _build_full_report(self) -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("Tracemalloc Debug Report")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append("=" * 72)
        lines.append(f"")

        lines.append("--- GC Collections ---")
        counts = gc.get_count()
        thresh = gc.get_threshold()
        lines.append(f"  Gen 0: {counts[0]}  (threshold: {thresh[0]})")
        lines.append(f"  Gen 1: {counts[1]}  (threshold: {thresh[1]})")
        lines.append(f"  Gen 2: {counts[2]}  (threshold: {thresh[2]})")
        lines.append(f"  Total: {sum(counts)}")
        rate = sum(self._gc_history) / max(len(self._gc_history), 1)
        lines.append(f"  Rate:  {rate:.1f} col/s  (60s window)")
        lines.append(f"")

        lines.append("--- tracemalloc ---")
        tracing = tracemalloc.is_tracing()
        lines.append(f"  Status: {'RUNNING' if tracing else 'STOPPED'}")
        if tracing:
            cur, peak = tracemalloc.get_traced_memory()
            lines.append(f"  Current: {self._format_size(cur)}")
            lines.append(f"  Peak:    {self._format_size(peak)}")
            lines.append(f"")
            try:
                snap = tracemalloc.take_snapshot()
                stats = snap.statistics('lineno')[:200]
                lines.append(f"Top allocators ({len(stats)} entries):")
                for i, st in enumerate(stats):
                    lines.append(f"  {i+1:>3}. {self._format_size(st.size):>10}  {st.count:>6}x  {str(st.traceback.format())[:120]}")
            except Exception as e:
                lines.append(f"  (snapshot error: {e})")
        else:
            lines.append(f"  (start tracemalloc to collect allocation data)")
        lines.append(f"")

        lines.append("--- gc.get_stats() ---")
        try:
            for i, stat in enumerate(gc.get_stats()):
                lines.append(f"  Gen {i}: collections={stat['collections']}  collected={stat['collected']}  uncollectable={stat['uncollectable']}")
        except Exception as e:
            lines.append(f"  (error: {e})")
        lines.append(f"")

        lines.append("--- Object Counts ---")
        try:
            objs = gc.get_objects()
            type_counts: dict[str, int] = {}
            for o in objs:
                try:
                    t = type(o).__name__
                    type_counts[t] = type_counts.get(t, 0) + 1
                except Exception:
                    pass
            sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])
            lines.append(f"Total objects tracked: {len(objs)}")
            lines.append(f"Distinct types: {len(sorted_types)}")
            lines.append(f"")
            lines.append("Top types:")
            for tname, cnt in sorted_types[:50]:
                lines.append(f"  {cnt:>8}x  {tname}")
        except Exception as e:
            lines.append(f"  (error: {e})")
        lines.append(f"")
        lines.append("=" * 72)
        lines.append("End of Report")
        return "\n".join(lines)

    def _on_copy_report(self):
        report = self._build_short_report()
        cb = QApplication.clipboard()
        cb.setText(report)
        self._btn_copy.setText("Copied!")
        QTimer.singleShot(1500, lambda: self._btn_copy.setText("Copy Report"))

    def _on_save_report(self):
        report = self._build_full_report()
        default_name = f"tracemalloc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Tracemalloc Report", default_name,
            "Text Files (*.txt);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
            self._btn_save.setText("Saved!")
            QTimer.singleShot(1500, lambda: self._btn_save.setText("Save Report..."))
        except Exception as e:
            self._btn_save.setText(f"Error: {e}")
            QTimer.singleShot(3000, lambda: self._btn_save.setText("Save Report..."))

    def _on_analyze(self):
        lines = []
        lines.append("--- gc.get_stats() ---")
        try:
            for i, stat in enumerate(gc.get_stats()):
                lines.append(f"  Gen {i}: collections={stat['collections']}  "
                             f"collected={stat['collected']}  "
                             f"uncollectable={stat['uncollectable']}")
        except Exception as e:
            lines.append(f"  error: {e}")
        lines.append("")

        lines.append("--- Garbage capture (DEBUG_SAVEALL) ---")
        old_debug = gc.get_debug()
        new_garbage = []
        n_collected = 0
        try:
            gc.set_debug(gc.DEBUG_SAVEALL)
            old_garbage_len = len(gc.garbage)
            n_collected = gc.collect()
            new_garbage = gc.garbage[old_garbage_len:]
            gc.garbage.clear()
        except Exception as e:
            lines.append(f"  error: {e}")
        finally:
            gc.set_debug(old_debug)

        lines.append(f"  gc.collect() freed {n_collected} objects")
        lines.append(f"  cyclic garbage entries: {len(new_garbage)}")
        if n_collected > 0:
            lines.append(f"  overhead ratio: {len(new_garbage)} cycles / {n_collected} objects"
                         f" = {len(new_garbage)/max(n_collected,1)*100:.1f}%")

        if new_garbage:
            type_cnt = Counter(type(o).__name__ for o in new_garbage)
            lines.append("")
            lines.append("  Top types in garbage (cycles):")
            for tname, cnt in type_cnt.most_common(20):
                lines.append(f"    {cnt:>6}x  {tname}")

            ctypes_types = {'CField', 'PyCStructType', 'getset_descriptor', '_FuncPtr',
                            'PyCFuncPtrType', 'WinDLL', 'py_object', 'py313(CField)'}
            ctypes_cycle = sum(v for k, v in type_cnt.items()
                               if any(c in k for c in ctypes_types))
            if ctypes_cycle > 0:
                pct = ctypes_cycle / len(new_garbage) * 100
                lines.append("")
                lines.append(f"  ⚠ ctypes cycle objects: {ctypes_cycle}/{len(new_garbage)} ({pct:.0f}%)")
                lines.append(f"    ctypes Structures/FuncPtrs define classes per-call → reference cycles")

            lines.append("")
            lines.append("  What garbage objects reference (top 10):")
            refs = Counter()
            for o in new_garbage[:200]:
                try:
                    for r in gc.get_referents(o):
                        refs[type(r).__name__] += 1
                except Exception:
                    pass
            for tname, cnt in refs.most_common(10):
                lines.append(f"    {cnt:>6}x  {tname}")

        self._analysis_text.setPlainText("\n".join(lines))
        self._analysis_status.setText(
            f"collected={n_collected}  cycles={len(new_garbage)}")

    def _refresh(self):
        self._update_gc_stats()
        if tracemalloc.is_tracing():
            self._update_tracemalloc()
        self._update_object_counts()

    def _update_gc_stats(self):
        counts = gc.get_count()
        c0, c1, c2 = counts[0], counts[1], counts[2]
        total = c0 + c1 + c2
        self._gc_labels["Gen 0"].setText(str(c0))
        self._gc_labels["Gen 1"].setText(str(c1))
        self._gc_labels["Gen 2"].setText(str(c2))
        self._gc_labels["Total"].setText(str(total))
        d0 = c0 - self._last_gc_counts[0]
        d1 = c1 - self._last_gc_counts[1]
        d2 = c2 - self._last_gc_counts[2]
        self._gc_history.append(d0 + d1 + d2)
        rate = sum(self._gc_history) / max(len(self._gc_history), 1)
        self._gc_rate.setText(f"{rate:.1f}  collections/s")
        self._last_gc_counts = [c0, c1, c2]
        thresh = gc.get_threshold()
        self._gc_group.setToolTip(
            f"thresholds: gen0={thresh[0]}  gen1={thresh[1]}  gen2={thresh[2]}")

    def _format_size(self, n: int, show_sign: bool = False) -> str:
        ab = abs(n)
        if ab >= 1024 * 1024:
            val = n / (1024 * 1024)
            unit = "MB"
        elif ab >= 1024:
            val = n / 1024
            unit = "K"
        else:
            return str(n)
        if show_sign and n > 0:
            return f"+{val:.1f}{unit}"
        return f"{val:.1f}{unit}"

    def _update_tracemalloc(self):
        try:
            snapshot = tracemalloc.take_snapshot()
            cur, peak = tracemalloc.get_traced_memory()
            self._trace_status.setText(
                f"current: {cur/1024:.1f}K  peak: {peak/1024:.1f}K")

            if self._prev_snapshot is not None:
                stats = snapshot.compare_to(self._prev_snapshot, 'lineno')
            else:
                stats = snapshot.statistics('lineno')
            stats = stats[:50]

            self._trace_tree.blockSignals(True)
            self._trace_tree.clear()
            has_diff = self._prev_snapshot is not None
            for st in stats:
                if has_diff:
                    sz = st.size_diff
                    ct = st.count_diff
                    if sz == 0 and ct == 0:
                        continue
                else:
                    sz = st.size
                    ct = st.count
                location = str(st.traceback.format())[:150]
                item = QTreeWidgetItem([location, self._format_size(sz, has_diff), str(ct)])
                item.setToolTip(0, str(st.traceback.format()))
                if has_diff:
                    if sz > 0:
                        item.setForeground(1, QBrush(QColor("#f88")))
                    elif sz < 0:
                        item.setForeground(1, QBrush(QColor("#8f8")))
                self._trace_tree.addTopLevelItem(item)

            self._trace_tree.blockSignals(False)
            self._prev_snapshot = snapshot
        except Exception:
            self._trace_status.setText("tracemalloc snapshot error")

    def _update_object_counts(self):
        try:
            objs = gc.get_objects()
        except Exception:
            return
        type_counts: dict[str, int] = {}
        for o in objs:
            try:
                t = type(o).__name__
                type_counts[t] = type_counts.get(t, 0) + 1
            except Exception:
                pass
        sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])[:30]
        self._obj_tree.blockSignals(True)
        self._obj_tree.clear()
        for tname, cnt in sorted_types:
            item = QTreeWidgetItem([tname, str(cnt), f"~{cnt * 64}B"])
            self._obj_tree.addTopLevelItem(item)
        self._obj_tree.blockSignals(False)

    def _on_start(self):
        tracemalloc.start()
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._btn_snapshot.setEnabled(True)
        self._trace_status.setText("tracemalloc running...")

    def _on_stop(self):
        tracemalloc.stop()
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._btn_snapshot.setEnabled(False)
        self._prev_snapshot = None
        self._trace_status.setText("tracemalloc stopped")

    def _on_snapshot(self):
        self._prev_snapshot = None
        self._update_tracemalloc()

    def _on_clear(self):
        self._prev_snapshot = None
        self._trace_tree.clear()
        self._gc_history.clear()
        self._trace_status.setText("cleared")
