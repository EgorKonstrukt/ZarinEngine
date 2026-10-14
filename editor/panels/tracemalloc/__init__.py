# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import gc
import threading
import time
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

from editor.panels.tracemalloc.panel import TracemallocPanelBase

class TracemallocPanel(TracemallocPanelBase):
    def _refresh(self):
        if not self.isVisible():
            return
        self._refresh_tick += 1
        tick = self._refresh_tick

        self._update_gc_stats()

        _need_trace = (tick % 5 == 0) and tracemalloc.is_tracing()
        _need_objs = (tick % 3 == 0)
        if _need_trace or _need_objs:
            self._kick_heavy(_need_trace, _need_objs)

    def _kick_heavy(self, do_trace: bool, do_objs: bool):
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        try:
            if self._heavy_running:
                try:
                    if (now - self._heavy_since) < 30.0:
                        return
                except Exception:
                    return
                try:
                    self._heavy_running = False
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._heavy_gen += 1
        except Exception:
            self._heavy_gen = 1
        try:
            _gen = self._heavy_gen
            _prev = self._prev_snapshot
        except Exception:
            return
        try:
            self._heavy_running = True
            self._heavy_since = now
        except Exception:
            pass
        try:
            _t = threading.Thread(
                target=self._heavy_worker,
                args=(_gen, bool(do_trace), bool(do_objs), _prev),
                daemon=True,
            )
            _t.start()
        except Exception:
            try:
                self._heavy_running = False
            except Exception:
                pass

    def _heavy_worker(self, gen: int, do_trace: bool, do_objs: bool, prev):
        obj_rows = None
        trace_status = None
        trace_rows = None
        new_snapshot = None
        try:
            if do_objs:
                try:
                    objs = gc.get_objects()
                except Exception:
                    objs = []
                type_counts: dict[str, int] = {}
                for o in objs:
                    try:
                        t = type(o).__name__
                        type_counts[t] = type_counts.get(t, 0) + 1
                    except Exception:
                        pass
                try:
                    top = sorted(type_counts.items(), key=lambda x: -x[1])[:30]
                except Exception:
                    top = []
                obj_rows = [(t, str(c), f"~{c * 64}B") for t, c in top]
            if do_trace:
                try:
                    snapshot = tracemalloc.take_snapshot()
                    cur, peak = tracemalloc.get_traced_memory()
                    trace_status = f"current: {cur/1024:.1f}K  peak: {peak/1024:.1f}K"
                    if prev is not None:
                        stats = snapshot.compare_to(prev, 'lineno')
                    else:
                        stats = snapshot.statistics('lineno')
                    stats = stats[:50]
                    has_diff = prev is not None
                    rows = []
                    for st in stats:
                        try:
                            if has_diff:
                                sz = st.size_diff
                                ct = st.count_diff
                                if sz == 0 and ct == 0:
                                    continue
                            else:
                                sz = st.size
                                ct = st.count
                            loc = str(st.traceback.format())[:150]
                            tip = str(st.traceback.format())
                            if has_diff:
                                if sz > 0:
                                    col = chr(35) + "f88"
                                elif sz < 0:
                                    col = chr(35) + "8f8"
                                else:
                                    col = None
                            else:
                                col = None
                            rows.append((loc, self._format_size(sz, has_diff), str(ct), col, tip))
                        except Exception:
                            continue
                    trace_rows = rows
                    new_snapshot = snapshot
                except Exception:
                    trace_status = "tracemalloc snapshot error"
        except Exception:
            pass
        try:
            from editor.scene_async import call_on_main
            call_on_main(lambda: self._apply_heavy(gen, obj_rows, trace_status, trace_rows, new_snapshot, do_trace))
        except Exception:
            try:
                self._heavy_running = False
            except Exception:
                pass

    def _apply_heavy(self, gen: int, obj_rows, trace_status, trace_rows, new_snapshot, do_trace: bool):
        try:
            if gen != self._heavy_gen:
                return
        except Exception:
            return
        finally:
            try:
                self._heavy_running = False
            except Exception:
                pass
        try:
            if not self.isVisible():
                if do_trace and new_snapshot is not None:
                    try:
                        self._prev_snapshot = new_snapshot
                    except Exception:
                        pass
                return
        except Exception:
            pass
        try:
            if obj_rows is not None:
                self._obj_tree.blockSignals(True)
                self._obj_tree.clear()
                for tname, cnt, approx in obj_rows:
                    item = QTreeWidgetItem([tname, cnt, approx])
                    self._obj_tree.addTopLevelItem(item)
                self._obj_tree.blockSignals(False)
        except Exception:
            pass
        try:
            if trace_status is not None:
                self._trace_status.setText(trace_status)
        except Exception:
            pass
        try:
            if trace_rows is not None:
                self._trace_tree.blockSignals(True)
                self._trace_tree.clear()
                for loc, sz_text, cnt_text, col, tip in trace_rows:
                    item = QTreeWidgetItem([loc, sz_text, cnt_text])
                    try:
                        item.setToolTip(0, tip)
                    except Exception:
                        pass
                    if col is not None:
                        try:
                            item.setForeground(1, QBrush(QColor(col)))
                        except Exception:
                            pass
                    self._trace_tree.addTopLevelItem(item)
                self._trace_tree.blockSignals(False)
            if do_trace and new_snapshot is not None:
                try:
                    self._prev_snapshot = new_snapshot
                except Exception:
                    pass
        except Exception:
            pass

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
                        item.setForeground(1, QBrush(QColor(chr(35) + "f88")))
                    elif sz < 0:
                        item.setForeground(1, QBrush(QColor(chr(35) + "8f8")))
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
