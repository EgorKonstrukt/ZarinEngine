# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import hashlib
from collections import deque
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QScrollArea, QPushButton, QCheckBox,
                               QTabWidget, QTreeWidget, QTreeWidgetItem,
                               QHeaderView, QFrame, QStyledItemDelegate,
                               QAbstractItemView, QApplication, QStyle)
from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QFontMetrics, QPalette
from PyQt6.QtWidgets import QStyleOptionViewItem
from core.config.editor_scale import scale

def _name_to_color(name: str) -> QColor:
    key = name.replace("_ms", "").replace("_", "").replace(" ", "").strip().lower()
    known = {
        "frame": (128, 128, 128),
        "tick": (66, 116, 200),
        "update": (66, 116, 200),
        "fixedupdate": (66, 116, 200),
        "game_tick": (66, 116, 200),
        "game_input": (126, 87, 194),
        "game_render": (230, 126, 34),
        "inputhandling": (126, 87, 194),
        "input_handling": (126, 87, 194),
        "editorupdate": (41, 182, 246),
        "editor_update": (41, 182, 246),
        "camupdate": (41, 182, 246),
        "cam_update": (41, 182, 246),
        "gizmoupdate": (255, 183, 77),
        "gizmo_update": (255, 183, 77),
        "editorparticles": (171, 71, 188),
        "editor_particles": (171, 71, 188),
        "sceneupdate": (56, 142, 60),
        "scene_update": (56, 142, 60),
        "scenefixedupdate": (56, 142, 60),
        "scene_fixed_update": (56, 142, 60),
        "constraints": (56, 142, 60),
        "components": (66, 165, 245),
        "ik": (38, 198, 218),
        "render": (230, 126, 34),
        "renderscene": (230, 126, 34),
        "rendermeshes": (230, 126, 34),
        "renderskybox": (230, 126, 34),
        "rendershadowpass": (200, 100, 30),
        "renderoverlay": (200, 150, 40),
        "rendergrid": (120, 144, 156),
        "renderstats": (120, 144, 156),
        "rendergraphicseffects": (142, 80, 180),
        "glsetup": (200, 120, 80),
        "glstatesetup": (200, 120, 80),
        "gizmos": (200, 150, 40),
        "overlaydraw": (40, 150, 200),
        "overlay_draw": (40, 150, 200),
        "physics": (70, 130, 200),
        "physicsstep": (70, 130, 200),
        "physics_step": (70, 130, 200),
        "meshasyncload": (130, 110, 200),
        "processpendingtextures": (130, 110, 200),
        "rendertextworld": (80, 150, 90),
        "rendersprites": (80, 150, 90),
        "rendervideos": (80, 150, 90),
        "playviewport": (70, 130, 200),
        "play_viewport": (70, 130, 200),
        "playcameras": (41, 182, 246),
        "play_cameras": (41, 182, 246),
        "playguisync": (38, 198, 218),
        "play_gui_sync": (38, 198, 218),
        "unaccounted": (130, 130, 130),
    }
    if key in known:
        r, g, b = known[key]
        return QColor(r, g, b)
    if not key:
        return QColor(140, 140, 140)
    h = int(hashlib.md5(key.encode()).hexdigest()[:6], 16)
    return QColor.fromHsl(h % 360, 45, 55)

def _name_to_hex(name: str) -> str:
    return _name_to_color(name).name()

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)
_FONT_TINY = QFont("Segoe UI", 7)
_FONT_LARGE = QFont("Segoe UI", 13, QFont.Weight.Bold)
_FONT_MED = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

class TimelineOverview(QWidget):
    HEIGHT = 64
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames_data: deque[dict] = deque(maxlen=300)
        self._selected_index = -1
        self._hover_index = -1
        self._budget_ms = 16.67
        self.setMouseTracking(True)
        self.setFixedHeight(scale(self.HEIGHT))
        self.setMinimumWidth(100)
    def add_frame(self, flat_data: dict, frame_time_ms: float):
        self._frames_data.append({"flat": dict(flat_data), "total": frame_time_ms})
        self.update()
    def clear_data(self):
        self._frames_data.clear()
        self._selected_index = -1
        self._hover_index = -1
        self.update()
    def _bar_color(self, total: float) -> QColor:
        if total <= self._budget_ms:
            return QColor(76, 175, 80)
        if total <= self._budget_ms * 2.0:
            return QColor(245, 150, 30)
        return QColor(211, 80, 80)
    def paintEvent(self, event):
        p = QPainter(self)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        txt = pal.color(QPalette.ColorRole.Text)
        mut = pal.color(QPalette.ColorRole.PlaceholderText)
        hl = pal.color(QPalette.ColorRole.Highlight)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, base)
        n = len(self._frames_data)
        if n == 0:
            p.setPen(mut)
            p.setFont(_FONT_SMALL)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No frame data")
            p.end()
            return
        for frac in (0.25, 0.5, 0.75):
            y = int(h * (1.0 - frac))
            p.setPen(QPen(mid, 1))
            p.drawLine(0, y, w, y)
        y_max = self._budget_ms * 1.4
        for d in self._frames_data:
            if d["total"] > y_max:
                y_max = d["total"]
        if y_max < 8.0:
            y_max = 8.0
        bar_w = w // max(n, 1)
        if bar_w > 9:
            bar_w = 9
        if bar_w < 2:
            bar_w = 2
        gap = 1 if bar_w > 3 else 0
        step = bar_w + gap
        self._bar_w = step
        total_w = n * step
        offset = max(0, total_w - w)
        budget_y = int(h - (h * min(self._budget_ms / y_max, 1.0)))
        hlc = QColor(hl.red(), hl.green(), hl.blue(), 150)
        p.setPen(QPen(hlc, 1, Qt.PenStyle.DashLine))
        p.drawLine(0, budget_y, w, budget_y)
        lbl = str(round(self._budget_ms, 1)) + "ms"
        p.setPen(mut)
        p.setFont(_FONT_TINY)
        p.drawText(w - 52, max(2, budget_y - 15), 48, 13, Qt.AlignmentFlag.AlignRight, lbl)
        for i, d in enumerate(self._frames_data):
            x = i * step - offset
            if x < -step or x > w:
                continue
            total = d["total"]
            bar_h = max(2, int((total / y_max) * (h - 6)))
            y0 = h - bar_h - 2
            base_c = self._bar_color(total)
            if i == self._selected_index:
                c = base_c.lighter(118)
            elif i == self._hover_index:
                c = base_c.lighter(108)
            else:
                c = base_c
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.fillRect(x, y0, bar_w, bar_h, c)
            if i == self._selected_index:
                p.setPen(QPen(txt, 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(x, y0, bar_w, bar_h)
        if self._hover_index >= 0 and self._hover_index < n:
            d = self._frames_data[self._hover_index]
            ms = d["total"]
            fps = 1000.0 / ms if ms > 0.001 else 0.0
            info = "Frame " + str(self._hover_index) + "  " + format(ms, ".2f") + "ms  " + format(fps, ".0f") + " FPS"
            fm = QFontMetrics(_FONT_SMALL)
            tw = fm.horizontalAdvance(info) + 16
            tx = self._hover_index * step - offset - tw // 2
            if tx < 4:
                tx = 4
            if tx + tw > w - 4:
                tx = w - tw - 4
            p.setPen(QPen(mid, 1))
            tip = QColor(base)
            tip.setAlpha(235)
            p.setBrush(QBrush(tip))
            p.drawRoundedRect(tx, 4, tw, 19, 4, 4)
            p.setPen(txt)
            p.setFont(_FONT_SMALL)
            p.drawText(tx, 4, tw, 19, Qt.AlignmentFlag.AlignCenter, info)
        p.end()
    def mouseMoveEvent(self, event):
        x = event.position().x()
        n = len(self._frames_data)
        step = getattr(self, "_bar_w", 4)
        if step <= 0:
            step = 4
        w = self.width()
        total_w = n * step
        offset = max(0, total_w - w)
        idx = (int(x) + offset) // step if step > 0 else -1
        if 0 <= idx < n:
            self._hover_index = idx
        else:
            self._hover_index = -1
        self.update()
    def mousePressEvent(self, event):
        x = event.position().x()
        n = len(self._frames_data)
        step = getattr(self, "_bar_w", 4)
        if step <= 0:
            step = 4
        w = self.width()
        total_w = n * step
        offset = max(0, total_w - w)
        idx = (int(x) + offset) // step if step > 0 else -1
        if 0 <= idx < n:
            self._selected_index = idx
            parent_panel = self.parent()
            while parent_panel and not hasattr(parent_panel, "_select_frame"):
                parent_panel = parent_panel.parent()
            if parent_panel:
                parent_panel._select_frame(idx)
        self.update()
    def leaveEvent(self, event):
        self._hover_index = -1
        self.update()

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

class TimelineWidget(QWidget):
    MAX_SAMPLES = 300
    def __init__(self, parent=None):
        super().__init__(parent)
        self._series: dict[str, deque] = {}
        self._colors: dict[str, QColor] = {}
        self._total_frames = 0
        self.setMinimumHeight(120)
    def add_frame(self, flat_data: dict[str, float]):
        self._total_frames += 1
        if not flat_data:
            self.update()
            return
        for key, val in flat_data.items():
            if key not in self._series:
                self._colors[key] = _name_to_color(key)
                self._series[key] = deque(maxlen=self.MAX_SAMPLES)
            self._series[key].append(val)
        for key in list(self._series.keys()):
            if key not in flat_data:
                self._series[key].append(0.0)
        self.update()
    def clear_data(self):
        self._series.clear()
        self._colors.clear()
        self._total_frames = 0
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        mut = pal.color(QPalette.ColorRole.PlaceholderText)
        hl = pal.color(QPalette.ColorRole.Highlight)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, base)
        margin = 46
        plot_w = w - margin * 2
        plot_h = h - margin * 2
        if plot_w < 10 or plot_h < 10:
            p.end()
            return
        if not self._series:
            p.setPen(mut)
            p.setFont(_FONT)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No timeline data")
            p.end()
            return
        p.setPen(QPen(mid, 1))
        for i in range(5):
            y = margin + plot_h * (1.0 - i * 0.25)
            p.drawLine(margin, int(y), w - margin, int(y))
        p.setPen(mut)
        p.setFont(_FONT_SMALL)
        for i in range(5):
            val = i * 0.25 * 33.33
            p.drawText(4, int(margin + plot_h * (1.0 - i * 0.25) + 3), format(val, ".0f") + "ms")
        budget_y = margin + plot_h * (1.0 - 16.67 / 33.33)
        hlc = QColor(hl.red(), hl.green(), hl.blue(), 130)
        p.setPen(QPen(hlc, 1, Qt.PenStyle.DashLine))
        p.drawLine(margin, int(budget_y), w - margin, int(budget_y))
        p.setPen(hl)
        p.setFont(_FONT_TINY)
        p.drawText(w - margin - 44, int(budget_y) - 4, "16.67ms")
        global_max = 0.1
        for key, data in self._series.items():
            if data:
                m = max(data)
                if m > global_max:
                    global_max = m
        y_max = global_max * 1.2
        if y_max < 16.67:
            y_max = 16.67
        keys = sorted(self._series.keys(), key=lambda k: max(self._series[k]) if self._series[k] else 0.0, reverse=True)[:8]
        for key in keys:
            data = self._series.get(key)
            if data is None or len(data) < 2:
                continue
            color = self._colors.get(key, pal.color(QPalette.ColorRole.Text))
            n = len(data)
            pts = []
            for i, val in enumerate(data):
                px = margin + (plot_w * i / max(n - 1, 1))
                py = margin + plot_h * (1.0 - val / y_max)
                pts.append(QPointF(px, py))
            pen = QPen(color, 1.6)
            p.setPen(pen)
            for i in range(1, len(pts)):
                p.drawLine(pts[i-1], pts[i])
        legend_x = margin
        legend_y = h - margin + 6
        p.setFont(_FONT_SMALL)
        for key in keys:
            if legend_x + 130 < w:
                color = self._colors.get(key, pal.color(QPalette.ColorRole.Text))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(color))
                p.drawRoundedRect(legend_x, legend_y, 8, 8, 2, 2)
                p.setPen(mut)
                label = key.replace("_ms", "").replace("_", " ").title()
                p.drawText(legend_x + 11, legend_y - 2, 120, 12, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
                fm = QFontMetrics(_FONT_SMALL)
                legend_x += fm.horizontalAdvance(label) + 30
        p.end()

class FlameGraphWidget(QWidget):
    ROW_H = 21
    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples: list = []
        self._frame_time_ms: float = 1.0
        self._work_time_ms: float = 1.0
        self._hovered: tuple | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(120)
    def set_data(self, samples: list, frame_time_ms: float):
        self._samples = samples
        self._frame_time_ms = max(frame_time_ms, 0.001)
        work_ms = self._frame_time_ms
        for s in samples:
            if s.name == "frame" and s.depth == 0:
                work_ms = max(s.duration_ms, 0.001)
                break
        self._work_time_ms = work_ms
        h = (max((s.depth for s in samples), default=0) + 2) * self.ROW_H
        self.setMinimumHeight(max(h, 120))
        self.update()
    def clear_data(self):
        self._samples = []
        self._frame_time_ms = 1.0
        self._work_time_ms = 1.0
        self._hovered = None
        self.setMinimumHeight(120)
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        txt = pal.color(QPalette.ColorRole.Text)
        mut = pal.color(QPalette.ColorRole.PlaceholderText)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, base)
        if not self._samples:
            p.setPen(mut)
            p.setFont(_FONT)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No profile data")
            p.end()
            return
        margin = 8
        plot_w = w - margin * 2
        if plot_w < 10:
            p.end()
            return
        bft = max(getattr(self, "_work_time_ms", 1.0), 0.001)
        pft = max(self._frame_time_ms, 0.001)
        frame_end_ms = 0.0
        for s in self._samples:
            if s.name == "frame" and s.depth == 0:
                frame_end_ms = s.start_ms + s.duration_ms
                break
        if frame_end_ms > 0 and frame_end_ms < self._frame_time_ms:
            idle_x = margin + (frame_end_ms / bft) * plot_w
            if idle_x < w - margin:
                p.setPen(mut)
                p.setFont(_FONT_TINY)
                idle_pct = (self._frame_time_ms - frame_end_ms) / self._frame_time_ms * 100
                p.drawText(QRectF(idle_x + 4, 4, w - idle_x - 12, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                           "Idle " + format(idle_pct, ".0f") + " %")
        ordered = sorted(self._samples, key=lambda s: (s.depth, s.start_ms))
        for s in ordered:
            x = margin + (s.start_ms / bft) * plot_w
            bw = max(2, (s.duration_ms / bft) * plot_w)
            y = s.depth * self.ROW_H + 6
            bh = self.ROW_H - 4
            if x + bw < 0 or x > w:
                continue
            color = _name_to_color(s.name)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(QRectF(x, y, bw, bh), 3, 3)
            p.setPen(QPen(QColor(0, 0, 0, 70), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, bw - 1, bh - 1), 3, 3)
            if bw > 46:
                p.setPen(QColor(22, 22, 22))
                p.setFont(_FONT_SMALL)
                pct = s.duration_ms / pft * 100.0
                label = s.name + "  " + format(pct, ".1f") + " %"
                tw = QFontMetrics(_FONT_SMALL).horizontalAdvance(label)
                if tw < bw - 10:
                    p.drawText(QRectF(x + 6, y, bw - 12, bh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            elif bw > 22 and s.depth > 0:
                p.setPen(QColor(22, 22, 22))
                p.setFont(_FONT_TINY)
                pct = s.duration_ms / pft * 100.0
                label = format(pct, ".0f") + " %"
                tw = QFontMetrics(_FONT_TINY).horizontalAdvance(label)
                if tw < bw - 6:
                    p.drawText(QRectF(x + 3, y, bw - 6, bh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        if self._hovered:
            sx, sy, sample = self._hovered
            pct = sample.duration_ms / pft * 100.0
            info = sample.name + "  " + format(sample.duration_ms, ".3f") + "ms  " + format(pct, ".1f") + " %"
            fm = QFontMetrics(_FONT)
            tw = fm.horizontalAdvance(info) + 18
            tx = sx
            if tx < 4:
                tx = 4
            if tx + tw > w - 4:
                tx = w - tw - 4
            ty = sy - 26
            if ty < 2:
                ty = sy + 24
            p.setPen(QPen(mid, 1))
            tip = QColor(base)
            tip.setAlpha(240)
            p.setBrush(QBrush(tip))
            p.drawRoundedRect(tx, ty, tw, 21, 4, 4)
            p.setPen(txt)
            p.setFont(_FONT)
            p.drawText(tx, ty, tw, 21, Qt.AlignmentFlag.AlignCenter, info)
        p.end()
    def mouseMoveEvent(self, event):
        x, y = event.position().x(), event.position().y()
        margin = 8
        w = self.width()
        plot_w = w - margin * 2
        ft = max(getattr(self, "_work_time_ms", 1.0), 0.001)
        self._hovered = None
        if plot_w > 0 and self._samples:
            for s in self._samples:
                sx = margin + (s.start_ms / ft) * plot_w
                bw = max(2, (s.duration_ms / ft) * plot_w)
                sy = s.depth * self.ROW_H + 6
                bh = self.ROW_H - 4
                if sx <= x <= sx + bw and sy <= y <= sy + bh:
                    self._hovered = (int(sx), int(sy), s)
                    break
        self.update()
    def leaveEvent(self, event):
        self._hovered = None
        self.update()

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
