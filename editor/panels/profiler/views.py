# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QHeaderView, QFrame, QStyledItemDelegate, QAbstractItemView, QApplication, QStyle, QHBoxLayout, QLabel
from PySide6.QtWidgets import QStyleOptionViewItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QFontMetrics, QPalette
from core.config.editor_scale import scale
from .timeline import _name_to_color, _FONT, _FONT_SMALL, _FONT_TINY, _FONT_LARGE, _FONT_MED


class HierarchyDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        w = opt.widget
        style = w.style() if w is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, w)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = opt.rect
        col = index.column()
        raw = index.data(Qt.ItemDataRole.DisplayRole)
        text = "" if raw is None else str(raw)
        pal = opt.palette
        is_sel = bool(opt.state & QStyle.State_Selected)
        name_pen = pal.color(QPalette.ColorRole.HighlightedText) if is_sel else pal.color(QPalette.ColorRole.Text)
        mut_pen = pal.color(QPalette.ColorRole.HighlightedText) if is_sel else pal.color(QPalette.ColorRole.PlaceholderText)
        if col == 0:
            cdata = index.data(Qt.ItemDataRole.UserRole + 1)
            dot = cdata if isinstance(cdata, QColor) else QColor(140, 140, 140)
            dot_d = 9
            dot_y = rect.y() + (rect.height() - dot_d) // 2
            dot_x = rect.x() + 22
            painter.setPen(QPen(dot.darker(135), 1))
            painter.setBrush(QBrush(dot))
            painter.drawRoundedRect(dot_x, dot_y, dot_d, dot_d, 2, 2)
            painter.setPen(name_pen)
            painter.setFont(_FONT)
            fm = QFontMetrics(_FONT)
            avail = rect.width() - (dot_x - rect.x()) - 14 - 6
            if avail < 10:
                avail = 10
            elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, avail)
            painter.drawText(dot_x + 14, rect.y(), avail, rect.height(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        elif col == 4:
            fdata = index.data(Qt.ItemDataRole.UserRole)
            try:
                frac = float(fdata) / 100.0 if fdata is not None else 0.0
            except Exception:
                frac = 0.0
            if frac < 0.0:
                frac = 0.0
            if frac > 1.0:
                frac = 1.0
            if frac > 0.001:
                cdata = index.data(Qt.ItemDataRole.UserRole + 1)
                base = cdata if isinstance(cdata, QColor) else pal.color(QPalette.ColorRole.Highlight)
                bw = int(rect.width() * frac)
                if bw < 3:
                    bw = 3
                soft = QColor(base.red(), base.green(), base.blue(), 40)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.fillRect(rect.x(), rect.y() + 3, bw, rect.height() - 6, soft)
                painter.fillRect(rect.x(), rect.y() + 3, 2, rect.height() - 6, base)
            pct = frac * 100.0
            if pct > 50.0 and not is_sel:
                tc = QColor(190, 60, 60)
            elif pct > 20.0 and not is_sel:
                tc = QColor(180, 120, 30)
            else:
                tc = name_pen
            painter.setPen(tc)
            painter.setFont(_FONT_SMALL)
            painter.drawText(rect.x(), rect.y(), rect.width() - 10, rect.height(), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
        else:
            if col == 1:
                tc = name_pen
            else:
                tc = mut_pen
            painter.setPen(tc)
            painter.setFont(_FONT_SMALL)
            painter.drawText(rect.x(), rect.y(), rect.width() - 10, rect.height(), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


class HierarchyView(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Name", "Total", "Self", "Calls", "%"])
        self.setColumnCount(5)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(4, scale(110))
        self.header().setMinimumSectionSize(scale(64))
        self.setAlternatingRowColors(False)
        self.setIndentation(scale(18))
        self.setAnimated(True)
        self.setUniformRowHeights(True)
        self.setExpandsOnDoubleClick(True)
        self.setRootIsDecorated(True)
        self.setItemsExpandable(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.setSortingEnabled(False)
        self.setItemDelegate(HierarchyDelegate(self))
        self._items: dict[str, QTreeWidgetItem] = {}
        self._scope_order: list[str] = []
        self._parent_map: dict[str, str | None] = {}
        self._children_map: dict[str, list[str]] = {}
        self._built = False
    def set_frame_data(self, samples: list, frame_time_ms: float, flat_data: dict | None = None):
        frame_dur = frame_time_ms
        for s in samples:
            if s.name == "frame" and s.depth == 0:
                frame_dur = s.duration_ms
                break
        unaccounted = max(0.0, frame_time_ms - frame_dur)
        if unaccounted > frame_time_ms * 0.03:
            from core.foundation.profiler import ProfileSample
            samples = list(samples) + [ProfileSample("Unaccounted", 0, 0.0, unaccounted, QColor(130, 130, 130).name())]
        self._base_frame_ms = frame_time_ms
        agg: dict[str, dict] = {}
        for s in samples:
            agg.setdefault(s.name, {"total": 0.0, "count": 0})
            agg[s.name]["total"] += s.duration_ms
            agg[s.name]["count"] += 1
        parent_map: dict[str, str | None] = {}
        depth_stack: list[tuple[str, int]] = []
        for s in sorted(samples, key=lambda x: (x.start_ms, x.depth)):
            while depth_stack and depth_stack[-1][1] >= s.depth:
                depth_stack.pop()
            parent_map[s.name] = depth_stack[-1][0] if depth_stack else None
            depth_stack.append((s.name, s.depth))
        children_map: dict[str, list[str]] = {}
        for name, parent in parent_map.items():
            children_map.setdefault(parent if parent else "", []).append(name)
        def dfs(name: str, out: list[str]):
            if name not in out:
                out.append(name)
            for c in children_map.get(name, []):
                dfs(c, out)
        this_order: list[str] = []
        for s in samples:
            if parent_map.get(s.name) is None:
                dfs(s.name, this_order)
        for name in this_order:
            if name not in self._scope_order:
                self._scope_order.append(name)
        self._parent_map.update(parent_map)
        for parent, children in children_map.items():
            for child in children:
                if child not in self._children_map.setdefault(parent, []):
                    self._children_map[parent].append(child)
        if not self._built:
            self._build_tree(agg, self._base_frame_ms)
            self._built = True
        else:
            self._update_tree(agg, self._base_frame_ms)
    def _setup_item(self, item: QTreeWidgetItem, name: str, total: float, self_ms: float,
                    count: int, frame_time_ms: float):
        pct = total / max(frame_time_ms, 0.001) * 100.0
        frac = min(pct, 100.0)
        dot = _name_to_color(name)
        item.setData(4, Qt.ItemDataRole.UserRole, frac)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, dot)
        item.setData(4, Qt.ItemDataRole.UserRole + 1, dot)
        item.setText(0, name)
        item.setText(1, format(total, ".3f"))
        item.setText(2, format(self_ms, ".3f"))
        item.setText(3, str(count))
        item.setText(4, format(pct, ".1f") + " %")
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(4, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    def _build_tree(self, agg: dict, frame_time_ms: float):
        self.clear()
        self._items.clear()
        def add(parent_widget, names: list[str]):
            for name in names:
                if name not in self._scope_order:
                    continue
                info = agg.get(name, {"total": 0.0, "count": 0})
                total = info["total"]
                children_total = sum(
                    agg.get(c, {}).get("total", 0.0)
                    for c in self._children_map.get(name, [])
                )
                self_ms = max(0.0, total - children_total)
                item = QTreeWidgetItem(parent_widget)
                self._items[name] = item
                self._setup_item(item, name, total, self_ms, info["count"], frame_time_ms)
                if name in self._children_map:
                    add(item, self._children_map[name])
        roots = [n for n in self._scope_order if self._parent_map.get(n) is None]
        add(self, roots)
        self.expandAll()
    def _update_tree(self, agg: dict, frame_time_ms: float):
        for name, item in list(self._items.items()):
            info = agg.get(name, {"total": 0.0, "count": 0})
            total = info["total"]
            children_total = sum(
                agg.get(c, {}).get("total", 0.0)
                for c in self._children_map.get(name, [])
            )
            self_ms = max(0.0, total - children_total)
            self._setup_item(item, name, total, self_ms, info["count"], frame_time_ms)
        for name in self._scope_order:
            if name in self._items:
                continue
            parent_name = self._parent_map.get(name)
            if parent_name and parent_name in self._items:
                parent_item = self._items[parent_name]
            else:
                parent_item = self
            info = agg.get(name, {"total": 0.0, "count": 0})
            total = info["total"]
            children_total = sum(
                agg.get(c, {}).get("total", 0.0)
                for c in self._children_map.get(name, [])
            )
            self_ms = max(0.0, total - children_total)
            item = QTreeWidgetItem(parent_item)
            self._items[name] = item
            self._setup_item(item, name, total, self_ms, info["count"], frame_time_ms)
        self.expandAll()
    def clear_data(self):
        self.clear()
        self._items.clear()
        self._scope_order.clear()
        self._parent_map.clear()
        self._children_map.clear()
        self._built = False


class ProfilerHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(12)
        self._fps_val = QLabel("0.0")
        self._fps_val.setFont(_FONT_LARGE)
        layout.addWidget(self._fps_val)
        self._fps_cap = QLabel("FPS")
        self._fps_cap.setFont(_FONT_TINY)
        layout.addWidget(self._fps_cap)
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFixedHeight(scale(26))
        layout.addWidget(sep1)
        self._time_val = QLabel("0.00 ms")
        self._time_val.setFont(_FONT_MED)
        layout.addWidget(self._time_val)
        self._pill = QLabel("60 FPS")
        self._pill.setFont(_FONT_TINY)
        layout.addWidget(self._pill)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFixedHeight(scale(26))
        layout.addWidget(sep2)
        self._min_lbl = QLabel("Min 0.00")
        self._min_lbl.setFont(_FONT_SMALL)
        layout.addWidget(self._min_lbl)
        self._avg_lbl = QLabel("Avg 0.00")
        self._avg_lbl.setFont(_FONT_SMALL)
        layout.addWidget(self._avg_lbl)
        self._max_lbl = QLabel("Max 0.00")
        self._max_lbl.setFont(_FONT_SMALL)
        layout.addWidget(self._max_lbl)
        layout.addStretch()
        self._frame_lbl = QLabel("Frame 0")
        self._frame_lbl.setFont(_FONT_SMALL)
        layout.addWidget(self._frame_lbl)
    def update_stats(self, fps: float, frame_count: int, frame_time_ms: float,
                     min_ms: float, avg_ms: float, max_ms: float):
        self._fps_val.setText(format(fps, ".1f"))
        self._time_val.setText(format(frame_time_ms, ".2f") + " ms")
        self._min_lbl.setText("Min " + format(min_ms, ".2f"))
        self._avg_lbl.setText("Avg " + format(avg_ms, ".2f"))
        self._max_lbl.setText("Max " + format(max_ms, ".2f"))
        self._frame_lbl.setText("Frame " + str(frame_count))
        if frame_time_ms <= 16.67:
            pill_txt = "60 FPS"
            tc = QColor(60, 140, 70)
        elif frame_time_ms <= 33.33:
            pill_txt = "30 FPS"
            tc = QColor(180, 120, 30)
        else:
            pill_txt = "OVER BUDGET"
            tc = QColor(190, 60, 60)
        self._pill.setText(pill_txt)
        fg = self._time_val.palette()
        fg.setColor(QPalette.ColorRole.WindowText, tc)
        self._time_val.setPalette(fg)
        pp = self._pill.palette()
        pp.setColor(QPalette.ColorRole.WindowText, tc)
        self._pill.setPalette(pp)
