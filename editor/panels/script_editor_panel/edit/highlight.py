# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap, QPen, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit
from core.config.editor_scale import scale
from ..theme import Theme
from .. import blame as blame_mod
class HighlightMixin:
    def set_indent_guides(self, on: bool):
        self._show_indent_guides = on
        self.viewport().update()
    def _indent_levels(self, block) -> int:
        text = block.text()
        column = 0
        for ch in text:
            if ch == " ":
                column += 1
            elif ch == "\t":
                column += 4
            else:
                break
        return column // 4
    def _indent_guide_records(self):
        viewport_h = self.viewport().height()
        first = self.firstVisibleBlock()
        if not first.isValid():
            return [], 0
        try:
            lh = self._cached_line_height()
        except Exception:
            lh = 18
        try:
            y0 = int(self.blockBoundingGeometry(first).translated(self.contentOffset()).top())
        except Exception:
            y0 = 0
        visible = []
        block = first
        vidx = 0
        while block.isValid():
            if not block.isVisible():
                block = block.next()
                continue
            top = y0 + vidx * lh
            vidx += 1
            if top > viewport_h:
                break
            visible.append([block, top, top + lh])
            block = block.next()
        if not visible:
            return [], 0
        cursor_level = self._indent_levels(self.textCursor().block())
        limit = 10
        prev_level = None
        p = first.previous()
        steps = 0
        while p.isValid() and steps < limit:
            if p.text().strip():
                prev_level = self._indent_levels(p)
                break
            p = p.previous()
            steps += 1
        trailing_next = None
        t = visible[-1][0].next()
        steps = 0
        while t.isValid() and steps < limit:
            if t.text().strip():
                trailing_next = self._indent_levels(t)
                break
            t = t.next()
            steps += 1
        n = len(visible)
        raw = [self._indent_levels(v[0]) for v in visible]
        empty = [not v[0].text().strip() for v in visible]
        prev = [None] * n
        cur = prev_level
        for i in range(n):
            prev[i] = cur
            if not empty[i]:
                cur = raw[i]
        nxt = [None] * n
        cur = trailing_next
        for i in range(n - 1, -1, -1):
            nxt[i] = cur
            if not empty[i]:
                cur = raw[i]
        for i in range(n):
            if empty[i]:
                cand = [c for c in (prev[i], nxt[i]) if c is not None]
                visible[i].append(min(cand) if cand else 0)
            else:
                visible[i].append(raw[i])
        return visible, cursor_level
    def _draw_indent_guides(self, event, painter=None):
        try:
            tab_w = self.tabStopDistance()
            if tab_w <= 0:
                return
            if self._cached_space_w <= 0 or self._cached_tab_w != tab_w:
                try:
                    self._cached_space_w = float(QFontMetrics(self.font()).horizontalAdvance(" "))
                except Exception:
                    self._cached_space_w = 7.0
                self._cached_tab_w = float(tab_w)
            space_w = self._cached_space_w
            if space_w <= 0:
                return
            records, cursor_level = self._indent_guide_records()
            if not records:
                return
            offset_x = self.contentOffset().x()
            width = self.viewport().width()
            rect_top = event.rect().top()
            rect_bottom = event.rect().bottom()
            guide_offset = 2.0 * space_w
            own = False
            if painter is None:
                painter = QPainter(self.viewport())
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                own = True
            pen_g = self._pen_guide
            pen_a = self._pen_guide_active
            for block, top, bottom, level in records:
                if level <= 0:
                    continue
                if top > rect_bottom or bottom < rect_top:
                    continue
                seg_top = top if top >= rect_top else rect_top
                seg_bottom = bottom if bottom <= rect_bottom else rect_bottom
                for L in range(1, level + 1):
                    x = int(offset_x + float(L) * float(tab_w) - guide_offset)
                    if x < 0 or x > width:
                        continue
                    painter.setPen(pen_a if L <= cursor_level else pen_g)
                    painter.drawLine(x, seg_top, x, seg_bottom)
            if own:
                painter.end()
        except Exception:
            pass
    def _update_current_line_only(self):
        try:
            cur = self.textCursor()
            cur.clearSelection()
            base = QTextEdit.ExtraSelection()
            base.format.setBackground(QColor(*Theme.current_line))
            base.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            base.cursor = cur
            selections: list = [base]
            try:
                selections.extend(self._diag_selections)
            except Exception:
                pass
            for _pid, info in self._remote_cursors.items():
                try:
                    if info.get("sel_anchor", 0) != info.get("sel_end", 0):
                        sel = QTextEdit.ExtraSelection()
                        c = info.get("color", QColor(100, 150, 220))
                        if not isinstance(c, QColor):
                            c = QColor(100, 150, 220)
                        cc = QColor(c)
                        cc.setAlpha(60)
                        sel.format.setBackground(cc)
                        tc = QTextCursor(self.document())
                        tc.setPosition(info.get("sel_anchor", 0))
                        tc.setPosition(info.get("sel_end", 0), QTextCursor.MoveMode.KeepAnchor)
                        sel.cursor = tc
                        selections.append(sel)
                except Exception:
                    continue
            self.setExtraSelections(selections)
        except Exception:
            pass
    def _update_current_line_highlight(self):
        try:
            self._rebuild_diag_selections()
        except Exception:
            pass
        self._update_current_line_only()
    def _rebuild_diag_selections(self):
        try:
            out: list = []
            doc = self.document()
            for d in self._diagnostic_errors[:200]:
                try:
                    blk = doc.findBlockByNumber(d.line)
                    if not blk.isValid():
                        continue
                    sel = QTextEdit.ExtraSelection()
                    fmt = QTextCharFormat()
                    fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                    fmt.setUnderlineColor(QColor(*Theme.error_red))
                    sel.format = fmt
                    tc = QTextCursor(doc)
                    s = blk.position() + max(0, d.col)
                    e = blk.position() + max(d.col + 1, d.end_col)
                    tc.setPosition(s)
                    tc.setPosition(e, QTextCursor.MoveMode.KeepAnchor)
                    sel.cursor = tc
                    out.append(sel)
                except Exception:
                    continue
            for d in self._diagnostic_warnings[:200]:
                try:
                    blk = doc.findBlockByNumber(d.line)
                    if not blk.isValid():
                        continue
                    sel = QTextEdit.ExtraSelection()
                    fmt = QTextCharFormat()
                    fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                    fmt.setUnderlineColor(QColor(*Theme.warn_wave))
                    sel.format = fmt
                    tc = QTextCursor(doc)
                    s = blk.position() + max(0, d.col)
                    e = blk.position() + max(d.col + 1, d.end_col)
                    tc.setPosition(s)
                    tc.setPosition(e, QTextCursor.MoveMode.KeepAnchor)
                    sel.cursor = tc
                    out.append(sel)
                except Exception:
                    continue
            self._diag_selections = out
            try:
                self._err_line_set = {d.line for d in self._diagnostic_errors}
            except Exception:
                self._err_line_set = set()
            try:
                self._warn_line_set = {d.line for d in self._diagnostic_warnings}
            except Exception:
                self._warn_line_set = set()
            try:
                m: dict[int, list] = {}
                for d in self._diagnostic_errors:
                    m.setdefault(d.line, []).append(d)
                for d in self._diagnostic_warnings:
                    m.setdefault(d.line, []).append(d)
                self._diag_map = m
            except Exception:
                self._diag_map = {}
        except Exception:
            pass
    def diagnostic_counts(self) -> tuple[int, int]:
        return len(self._diagnostic_errors), len(self._diagnostic_warnings)
    def _draw_current_blame(self, event, painter=None):
        if not self._show_blame:
            return
        if not self._vcs_blame_data:
            return
        cur = self.textCursor().block()
        if not cur.isValid():
            return
        info = self._vcs_blame_data.get(cur.blockNumber())
        if not info:
            return
        label = blame_mod.format_label(info)
        if not label:
            return
        geom = self.blockBoundingGeometry(cur).translated(self.contentOffset())
        top = int(geom.top())
        if top < 0 or top > self.viewport().height():
            return
        own = False
        if painter is None:
            painter = QPainter(self.viewport())
            own = True
        f = QFont(self.font().family(), 9)
        f.setItalic(True)
        painter.setFont(f)
        fm = QFontMetrics(f)
        txt = cur.text()
        if len(txt) > 300:
            base_w = QFontMetrics(self.font()).horizontalAdvance(" ") * 60.0
        else:
            base_w = QFontMetrics(self.font()).horizontalAdvance(txt)
        x = int(self.contentOffset().x() + base_w + scale(18))
        vw = self.viewport().width()
        tw = fm.horizontalAdvance(label)
        if x + tw > vw - scale(30):
            x = vw - tw - scale(30)
        if x < scale(80):
            x = scale(80)
        painter.setPen(QColor(130, 150, 180))
        painter.drawText(x, top + QFontMetrics(self.font()).ascent(), label)
        if own:
            painter.end()
    def _rebuild_minimap(self):
        mw = max(1, self._minimap.width())
        mh = max(1, self._minimap.height())
        blocks = max(1, self.document().blockCount())
        key = (mw, mh, blocks, self._font_size, len(self._diagnostic_errors), len(self._diagnostic_warnings))
        if self._minimap_cache is not None and self._minimap_cache_key == key:
            return self._minimap_cache
        pm = QPixmap(mw, mh)
        pm.fill(QColor(*Theme.stripe_bg))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        total = max(1, blocks)
        for d in self._diagnostic_warnings:
            try:
                y = int(d.line * mh / total)
                painter.fillRect(1, y, mw - 2, scale(3), QColor(*Theme.warn_yellow))
            except Exception:
                continue
        for d in self._diagnostic_errors:
            try:
                y = int(d.line * mh / total)
                painter.fillRect(1, y, mw - 2, scale(3), QColor(*Theme.error_stripe))
            except Exception:
                continue
        painter.end()
        self._minimap_cache = pm
        self._minimap_cache_key = key
        return pm
    def minimap_paint(self, event, area):
        painter = QPainter(area)
        painter.fillRect(event.rect(), QColor(*Theme.stripe_bg))
        pm = self._rebuild_minimap()
        painter.drawPixmap(0, 0, pm)
        vsb = self.verticalScrollBar()
        if vsb is not None:
            total = vsb.maximum() + vsb.pageStep()
            if total > 0:
                y = int(vsb.value() * area.height() / total)
                h = int(vsb.pageStep() * area.height() / total)
            else:
                y = 0
                h = area.height()
            y = max(0, min(area.height() - 1, y))
            h = max(scale(8), min(area.height() - y, h))
            painter.setPen(QColor(*Theme.viewport_indicator))
            painter.setBrush(QColor(*Theme.viewport_indicator))
            painter.setOpacity(0.35)
            painter.drawRect(0, y, area.width() - 1, h)
            painter.setOpacity(1.0)
            painter.setPen(QColor(34, 34, 34))
            painter.drawLine(0, 0, 0, area.height())
            cur = self.textCursor().blockNumber()
            blocks = max(1, self.document().blockCount())
            cy = int(cur * area.height() / blocks)
            painter.fillRect(1, cy, area.width() - 2, scale(2), QColor(*Theme.viewport_indicator))
        painter.end()
    def blame_gutter_paint(self, event, area):
        painter = QPainter(area)
        painter.fillRect(event.rect(), QColor(27, 27, 27))
        painter.end()
    def line_number_paint(self, event, area):
        painter = QPainter(area)
        painter.setFont(self.font())
        painter.fillRect(event.rect(), QColor(*Theme.gutter))
        block = self.firstVisibleBlock()
        if not block.isValid():
            painter.end()
            return
        try:
            lh = self._cached_line_height()
        except Exception:
            lh = 18
        try:
            y0 = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        except Exception:
            y0 = 0
        cur_block = self.textCursor().blockNumber()
        fm = painter.fontMetrics()
        fm_h = fm.height()
        c_add = QColor(*Theme.added)
        c_mod = QColor(*Theme.modified)
        c_del = QColor(*Theme.deleted)
        c_cur_bg = QColor(*Theme.gutter_current)
        c_cur = QColor(*Theme.line_number_current)
        c_err = QColor(*Theme.error_red)
        c_warn = QColor(*Theme.warn_yellow)
        c_norm = QColor(*Theme.line_number)
        c_fold = QColor(150, 150, 150)
        c_foldable = QColor(80, 80, 80)
        c_blue = QColor(*Theme.lens_blue)
        c_green = QColor(*Theme.lens_green)
        err_lines = self._err_line_set
        warn_lines = self._warn_line_set
        folded = self._folded
        vcs = self._vcs_diff_data
        aw = area.width()
        right_x = aw - scale(18)
        fold_x = aw - scale(14)
        evt_top = event.rect().top()
        evt_bot = event.rect().bottom()
        vidx = 0
        while block.isValid():
            if not block.isVisible():
                block = block.next()
                continue
            top = y0 + vidx * lh
            vidx += 1
            if top > evt_bot:
                break
            bottom = top + lh
            if bottom < evt_top:
                block = block.next()
                continue
            line = block.blockNumber()
            txt = str(line + 1)
            vcs_status = vcs.get(line, "")
            if line == cur_block:
                painter.fillRect(0, top, aw, lh, c_cur_bg)
                painter.setPen(c_cur)
            elif line in err_lines:
                painter.setPen(c_err)
            elif line in warn_lines:
                painter.setPen(c_warn)
            elif vcs_status == "added":
                painter.setPen(c_add)
            elif vcs_status == "modified":
                painter.setPen(c_mod)
            elif vcs_status == "deleted":
                painter.setPen(c_del)
            else:
                painter.setPen(c_norm)
            if vcs_status == "added":
                painter.fillRect(0, top, scale(3), lh, c_add)
            elif vcs_status == "modified":
                painter.fillRect(0, top, scale(3), lh, c_mod)
            elif vcs_status == "deleted":
                painter.fillRect(0, top + lh // 2 - 1, scale(3), 2, c_del)
            painter.drawText(0, top, right_x, fm_h, Qt.AlignmentFlag.AlignRight, txt)
            if line in folded:
                painter.setPen(c_fold)
                painter.drawText(fold_x, top, scale(12), fm_h, Qt.AlignmentFlag.AlignLeft, ">")
            elif line in self._foldable_set:
                painter.setPen(c_foldable)
                painter.drawText(fold_x, top, scale(12), fm_h, Qt.AlignmentFlag.AlignLeft, "v")
            if line in self._class_lines:
                painter.setPen(c_blue)
                painter.drawText(scale(2), top, scale(12), fm_h, Qt.AlignmentFlag.AlignLeft, chr(9424))
            elif line in self._def_lines:
                painter.setPen(c_green)
                painter.drawText(scale(2), top, scale(12), fm_h, Qt.AlignmentFlag.AlignLeft, chr(11377))
            block = block.next()
        painter.end()
