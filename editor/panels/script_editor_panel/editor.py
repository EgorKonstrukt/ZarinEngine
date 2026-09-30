# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import re
import threading
from typing import Optional

from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QCompleter
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QStringListModel, QTimer, QPoint
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QWheelEvent, QTextCharFormat, QTextCursor, QPainter, QPixmap, QPen, QTextBlock, QMouseEvent, QKeySequence

from core.config.editor_scale import scale

from .theme import Theme, editor_stylesheet, editor_font
from .gutter import LineNumberArea, VcsBlameGutter
from .stripe import StripeBar
from .inspection import InspectionOverlay
from .doc_popup import DocPopup
from . import doc_provider as docs
from . import diagnostics as diags
from . import folding as fld
from . import vision as vis
from . import blame as blame_mod

try:
    from core.config.syntax_config import KEYWORDS, BUILTINS, CONSTANTS, EXCEPTIONS
except ImportError:
    try:
        from ..syntax_config import KEYWORDS, BUILTINS, CONSTANTS, EXCEPTIONS
    except ImportError:
        from syntax_config import KEYWORDS, BUILTINS, CONSTANTS, EXCEPTIONS

try:
    from editor.panels.vcs_panel import _Git
except ImportError:
    _Git = None

from .api_words import ENGINE_API_WORDS


class CodeEditor(QPlainTextEdit):
    MIN_FONT = 8
    MAX_FONT = 48
    DEFAULT_FONT = 13

    cursorMoved = pyqtSignal(int, int)
    vcs_result_ready = pyqtSignal(object)
    _vcs_result_ready = pyqtSignal(object)
    diagnostics_changed = pyqtSignal(int, int)
    analysis_ready = pyqtSignal(int, object, object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_size = self.DEFAULT_FONT
        self._wrap = False
        self._show_indent_guides = True
        self._show_blame = True
        self._vcs_result_ready.connect(self._on_vcs_result)
        self.vcs_result_ready.connect(self._on_vcs_result)
        self._vcs_git = None
        self._vcs_file_path: str = ""
        self._vcs_blame_data: dict[int, dict] = {}
        self._vcs_diff_data: dict[int, str] = {}
        self._vcs_status: str = ""
        self._vcs_branch: str = ""
        self._vcs_refreshing: bool = False
        self._vcs_pending: bool = False
        self._line_number = LineNumberArea(self)
        self._blame_gutter = VcsBlameGutter(self)
        self._minimap = StripeBar(self)
        self._minimap_cache = None
        self._minimap_cache_key = (-1, -1, -1, -1)
        self._inspection = InspectionOverlay(self)
        self._inspection.show()
        self._doc_popup = DocPopup(self)
        self._folded: dict[int, tuple[int, str]] = {}
        self._diagnostic_errors: list = []
        self._diagnostic_warnings: list = []
        self._vision_usages: dict[int, str] = {}
        self._vision_complexity: dict[int, str] = {}
        self._remote_cursors: dict[str, dict] = {}
        self._ops_callback = None
        self._suppress_ops = False
        self._old_text = ""
        self._analysis_version = 0
        self._diag_selections: list = []
        self._completion_cache: list[str] = []
        self._completion_dirty = True
        self._line_width_cache: dict = {}
        self.analysis_ready.connect(self._apply_analysis)
        self.document().contentsChange.connect(self._on_contents_change)
        QTimer.singleShot(0, self._init_old_text)
        self._apply_font()
        self.setUndoRedoEnabled(True)
        self.setCursorWidth(scale(2))
        self.setMouseTracking(True)
        self._completer = QCompleter([], self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setModelSorting(QCompleter.ModelSorting.CaseInsensitivelySortedModel)
        self._completer.activated.connect(self._insert_completion)
        self.blockCountChanged.connect(self._update_line_number)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._emit_cursor)
        self.cursorPositionChanged.connect(self._update_current_line_only)
        self.textChanged.connect(self._invalidate_minimap)
        self.textChanged.connect(self._schedule_analysis)
        self.textChanged.connect(self._mark_completion_dirty)
        self._analysis_timer = QTimer(self)
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.timeout.connect(self._run_analysis)
        self._completion_timer = QTimer(self)
        self._completion_timer.setSingleShot(True)
        self._completion_timer.timeout.connect(self._rebuild_completions)
        self._update_line_number()
        self._update_minimap()
        self._update_current_line_only()
        try:
            self.verticalScrollBar().valueChanged.connect(lambda v: self._minimap.update())
        except Exception:
            pass
        QTimer.singleShot(600, self._run_analysis)

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
        visible = []
        block = first
        while block.isValid():
            geom = self.blockBoundingGeometry(block).translated(self.contentOffset())
            top = int(geom.top())
            if top > viewport_h:
                break
            if not block.isVisible():
                block = block.next()
                continue
            bottom = top + int(self.blockBoundingRect(block).height())
            visible.append([block, top, bottom])
            block = block.next()
        if not visible:
            return [], 0
        cursor_level = self._indent_levels(self.textCursor().block())
        limit = 200
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

    def paintEvent(self, event):
        super().paintEvent(event)
        try:
            if self._show_indent_guides:
                self._draw_indent_guides(event)
            if self._vcs_diff_data:
                self._draw_diff_markers(event)
            if self._remote_cursors:
                self._draw_remote_cursors(event)
            if self._vision_usages or self._vision_complexity:
                self._draw_code_vision(event)
            if self._folded:
                self._draw_fold_placeholders(event)
            if self._show_blame and self._vcs_blame_data:
                self._draw_current_blame(event)
        except Exception:
            pass

    def _position_inspection(self):
        try:
            vw = self.viewport().width()
            iw = scale(170)
            ih = scale(18)
            x = vw - iw - scale(30)
            y = scale(2)
            g = self._inspection.geometry()
            if g.x() != x or g.y() != y or g.width() != iw or g.height() != ih:
                self._inspection.setGeometry(x, y, iw, ih)
                self._inspection.raise_()
        except Exception:
            pass

    def _draw_indent_guides(self, event):
        tab_w = self.tabStopDistance()
        if tab_w <= 0:
            return
        fm = QFontMetrics(self.font())
        space_w = fm.horizontalAdvance(" ")
        if space_w <= 0:
            return
        records, cursor_level = self._indent_guide_records()
        if not records:
            return
        offset_x = self.contentOffset().x()
        width = self.viewport().width()
        rect_top = event.rect().top()
        rect_bottom = event.rect().bottom()
        guide_offset = 2 * space_w
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        guide_color = QColor(*Theme.indent_guide)
        active_color = QColor(*Theme.indent_guide_active)
        for block, top, bottom, level in records:
            if level <= 0:
                continue
            seg_top = max(top, rect_top)
            seg_bottom = min(bottom, rect_bottom)
            if seg_top > seg_bottom:
                continue
            for L in range(1, level + 1):
                x = int(offset_x + L * tab_w - guide_offset)
                if x < 0 or x > width:
                    continue
                painter.setPen(active_color if L <= cursor_level else guide_color)
                painter.drawLine(x, seg_top, x, seg_bottom)
        painter.end()

    def _draw_diff_markers(self, event):
        viewport_h = self.viewport().height()
        first = self.firstVisibleBlock()
        if not first.isValid():
            return
        painter = QPainter(self.viewport())
        offset_x = self.contentOffset().x()
        marker_w = scale(3)
        block = first
        while block.isValid():
            if not block.isVisible():
                block = block.next()
                continue
            line = block.blockNumber()
            status = self._vcs_diff_data.get(line, "")
            if status:
                geom = self.blockBoundingGeometry(block).translated(self.contentOffset())
                top = int(geom.top())
                bottom = top + int(self.blockBoundingRect(block).height())
                if top > viewport_h:
                    break
                if bottom >= event.rect().top():
                    if status == "added":
                        painter.fillRect(int(offset_x), top, marker_w, bottom - top, QColor(*Theme.added))
                    elif status == "modified":
                        painter.fillRect(int(offset_x), top, marker_w, bottom - top, QColor(*Theme.modified))
                    elif status == "deleted":
                        painter.fillRect(int(offset_x), top + (bottom - top) // 2 - 1, marker_w, 2, QColor(*Theme.deleted))
            block = block.next()
        painter.end()

    def set_remote_cursors(self, cursors: dict[str, dict]):
        self._remote_cursors = dict(cursors)
        self._update_current_line_only()
        self.viewport().update()

    def _update_remote_extra_selections(self):
        self._update_current_line_highlight()

    def _draw_remote_cursors(self, event):
        if not self._remote_cursors:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fm = painter.fontMetrics()
        for info in self._remote_cursors.values():
            try:
                col = info.get("color", QColor(100, 150, 220))
                qcol = col if isinstance(col, QColor) else QColor(100, 150, 220)
                name = info.get("name", "")
                pos = info.get("pos", 0)
                tc = QTextCursor(self.document())
                tc.setPosition(pos)
                rect = self.cursorRect(tc)
                x = rect.x()
                y_top = rect.y()
                painter.setPen(QPen(qcol, 2))
                painter.drawLine(x, y_top, x, y_top + rect.height())
                lw = fm.horizontalAdvance(name) + 6
                lh = fm.height() + 2
                bg = QColor(qcol)
                bg.setAlpha(200)
                painter.fillRect(x, y_top - lh - 2, lw, lh, bg)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(x + 3, y_top - lh - 2 + fm.ascent() + 1, name)
            except Exception:
                continue
        painter.end()

    def _schedule_analysis(self):
        try:
            if self._analysis_timer.isActive():
                return
            try:
                bc = self.blockCount()
            except Exception:
                bc = 0
            delay = 350
            if bc > 3000:
                delay = 900
            elif bc > 1000:
                delay = 600
            self._analysis_timer.start(delay)
        except Exception:
            pass

    def _mark_completion_dirty(self):
        try:
            self._completion_dirty = True
            if not self._completion_timer.isActive():
                self._completion_timer.start(1200)
        except Exception:
            pass

    def set_text_fast(self, text: str):
        try:
            self.setUpdatesEnabled(False)
            self.blockSignals(True)
            self._suppress_ops = True
            self.setPlainText(text)
            self._old_text = text
            self._folded.clear()
            self._diagnostic_errors = []
            self._diagnostic_warnings = []
            self._diag_selections = []
            self._vision_usages = {}
            self._vision_complexity = {}
            self._completion_dirty = True
            self.document().setModified(False)
        except Exception:
            pass
        try:
            self.blockSignals(False)
            self._suppress_ops = False
            self.setUpdatesEnabled(True)
        except Exception:
            pass
        try:
            self._update_current_line_only()
            self._update_line_number()
        except Exception:
            pass
        try:
            QTimer.singleShot(120, self._run_analysis)
        except Exception:
            pass

    def _run_analysis(self):
        try:
            self._analysis_version += 1
            ver = self._analysis_version
            try:
                bc = self.blockCount()
            except Exception:
                bc = 0
            if bc > 8000:
                try:
                    self._inspection.set_counts(0, 0)
                except Exception:
                    pass
                return
            text = self.toPlainText()
            path = self._vcs_file_path or ""
            def _work():
                try:
                    errs, warns = diags.analyze_text(text, path)
                    lines = text.splitlines()
                    usages = vis.compute_usages(text, lines)
                    comp = vis.compute_complexity(lines)
                    try:
                        self.analysis_ready.emit(ver, errs, warns, usages, comp)
                    except Exception:
                        pass
                except Exception:
                    pass
            threading.Thread(target=_work, daemon=True).start()
        except Exception:
            pass

    def _apply_analysis(self, ver: int, errs, warns, usages, comp):
        try:
            if ver != self._analysis_version:
                return
            self._diagnostic_errors = errs
            self._diagnostic_warnings = warns
            self._vision_usages = usages
            self._vision_complexity = comp
            try:
                self._inspection.set_counts(len(errs), len(warns))
            except Exception:
                pass
            try:
                self.diagnostics_changed.emit(len(errs), len(warns))
            except Exception:
                pass
            try:
                lines = self.toPlainText().splitlines()
                self._ensure_import_fold(lines)
            except Exception:
                pass
            self._rebuild_diag_selections()
            self._update_current_line_only()
            try:
                self.viewport().update()
                self._line_number.update()
                self._minimap_cache = None
                self._minimap.update()
            except Exception:
                pass
        except Exception:
            pass

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
        except Exception:
            pass

    def diagnostic_counts(self) -> tuple[int, int]:
        return len(self._diagnostic_errors), len(self._diagnostic_warnings)

    def _ensure_import_fold(self, lines=None):
        if self._folded:
            return
        if lines is None:
            lines = self.toPlainText().splitlines()
        r = fld.find_import_block(lines)
        if r is not None:
            s, e = r
            self._fold_range(s, e, "import ...")

    def _fold_range(self, start: int, end: int, placeholder: str):
        self._folded[start] = (end, placeholder)
        doc = self.document()
        for ln in range(start + 1, end + 1):
            blk = doc.findBlockByNumber(ln)
            if blk.isValid():
                blk.setVisible(False)
        doc.markContentsDirty(0, doc.characterCount())
        self.viewport().update()
        self._update_line_number()
        self._minimap.update()

    def _unfold(self, start: int):
        if start not in self._folded:
            return
        end, _ph = self._folded.pop(start)
        doc = self.document()
        for ln in range(start + 1, end + 1):
            blk = doc.findBlockByNumber(ln)
            if blk.isValid():
                blk.setVisible(True)
        doc.markContentsDirty(0, doc.characterCount())
        self.viewport().update()
        self._update_line_number()

    def _toggle_fold(self, line: int):
        if line in self._folded:
            self._unfold(line)
            return
        for s, (e, _ph) in list(self._folded.items()):
            if s < line <= e:
                self._unfold(s)
                return
        text_lines = self.toPlainText().splitlines()
        r = fld.find_indent_block(text_lines, line)
        if r is not None:
            s, e = r
            self._fold_range(s, e, fld.placeholder_for(text_lines[s] if 0 <= s < len(text_lines) else ""))

    def _draw_fold_placeholders(self, event):
        if not self._folded:
            return
        painter = QPainter(self.viewport())
        fm = QFontMetrics(self.font())
        for s, (e, ph) in self._folded.items():
            blk = self.document().findBlockByNumber(s)
            if not blk.isValid() or not blk.isVisible():
                continue
            geom = self.blockBoundingGeometry(blk).translated(self.contentOffset())
            top = int(geom.top())
            if top < -50 or top > self.viewport().height() + 50:
                continue
            txt = blk.text()
            indent = len(txt) - len(txt.lstrip())
            x_base = int(self.contentOffset().x() + fm.horizontalAdvance(" ") * indent)
            if "import" in txt or ph.startswith("import"):
                draw_txt = "import ..."
                kw_w = fm.horizontalAdvance("import ")
                x = x_base + kw_w
                h = fm.height() + scale(2)
                y = top + scale(1)
                painter.fillRect(x - scale(2), y, fm.horizontalAdvance(draw_txt) + scale(6), h, QColor(*Theme.background))
                painter.setPen(QColor(150, 150, 150))
                painter.drawRect(x - scale(2), y, fm.horizontalAdvance(draw_txt) + scale(6), h)
                painter.setPen(QColor(200, 200, 200))
                painter.drawText(x, y + fm.ascent() + scale(1), draw_txt)
            else:
                x = x_base + fm.horizontalAdvance(txt.strip()[:12])
                painter.setPen(QColor(140, 140, 140))
                painter.drawText(x, top + fm.ascent(), "...")
        painter.end()

    def _draw_code_vision(self, event):
        if not self._vision_usages and not self._vision_complexity:
            return
        painter = QPainter(self.viewport())
        small_font = QFont(self.font().family(), 9)
        painter.setFont(small_font)
        fm_small = QFontMetrics(small_font)
        fm_main = QFontMetrics(self.font())
        block = self.firstVisibleBlock()
        while block.isValid():
            if not block.isVisible():
                block = block.next()
                continue
            ln = block.blockNumber()
            geom = self.blockBoundingGeometry(block).translated(self.contentOffset())
            top = int(geom.top())
            if top > self.viewport().height():
                break
            if top + fm_main.height() < 0:
                block = block.next()
                continue
            txt = block.text()
            indent = len(txt) - len(txt.lstrip())
            x_ind = int(self.contentOffset().x() + fm_main.horizontalAdvance(" ") * indent)
            if ln in self._vision_usages:
                usages = self._vision_usages[ln]
                base_w = fm_main.horizontalAdvance(txt)
                x_u = int(self.contentOffset().x() + base_w + scale(14))
                painter.setPen(QColor(*Theme.lens))
                painter.drawText(x_u, top + fm_main.ascent(), usages)
                blame = self._vcs_blame_data.get(ln)
                if blame and blame.get("author"):
                    x_a = x_u + fm_small.horizontalAdvance(usages) + scale(14)
                    painter.setPen(QColor(*Theme.lens))
                    painter.drawText(x_a, top + fm_main.ascent(), chr(11377) + " " + str(blame.get("author", ""))[:40])
                if txt.strip().startswith("class "):
                    painter.setPen(QColor(*Theme.lens_blue))
                    painter.drawText(scale(2), top + fm_main.ascent(), chr(9424))
            if ln in self._vision_complexity:
                comp = self._vision_complexity[ln]
                prev = block.previous()
                draw_y = top
                if prev.isValid() and prev.text().strip() == "":
                    pg = self.blockBoundingGeometry(prev).translated(self.contentOffset())
                    draw_y = int(pg.top())
                painter.setPen(QColor(*Theme.lens_green))
                painter.drawText(x_ind, draw_y + fm_small.ascent(), chr(11377))
                painter.setPen(QColor(*Theme.lens))
                painter.drawText(x_ind + fm_small.horizontalAdvance(chr(11377) + " "), draw_y + fm_small.ascent(), comp)
            block = block.next()
        painter.end()

    def _draw_current_blame(self, event):
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
        painter = QPainter(self.viewport())
        f = QFont(self.font().family(), 9)
        f.setItalic(True)
        painter.setFont(f)
        fm = QFontMetrics(f)
        txt = cur.text()
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
        painter.end()

    def _word_under_cursor_text(self) -> tuple[str, QTextCursor]:
        try:
            cur = self.textCursor()
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
            return cur.selectedText(), cur
        except Exception:
            return "", self.textCursor()

    def show_documentation_at_cursor(self) -> bool:
        try:
            word, cur = self._word_under_cursor_text()
            if not word:
                blk = self.textCursor().block().text()
                col = self.textCursor().positionInBlock()
                word = docs.word_at(blk, col)
            if not word:
                return False
            r = self.cursorRect(self.textCursor())
            gp = self.viewport().mapToGlobal(QPoint(r.x() + scale(20), r.y() + scale(22)))
            return self._doc_popup.show_documentation(word, gp)
        except Exception:
            return False

    def hide_doc_popup(self):
        try:
            self._doc_popup.hide()
        except Exception:
            pass

    def _apply_font(self):
        f = editor_font(self._font_size)
        self.setFont(f)
        self.setTabStopDistance(QFontMetrics(f).horizontalAdvance(" ") * 4)
        self.setStyleSheet(editor_stylesheet())
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if self._wrap
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._minimap_cache = None
        QTimer.singleShot(0, self._update_minimap)

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

    def _init_old_text(self):
        self._old_text = self.toPlainText()

    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        if self._suppress_ops or (chars_removed == 0 and chars_added == 0):
            return
        if self._ops_callback is None:
            return
        current = self.toPlainText()
        if chars_removed > 0 and position + chars_removed <= len(self._old_text):
            removed = self._old_text[position:position + chars_removed]
        else:
            removed = ""
        if chars_added > 0 and position + chars_added <= len(current):
            added = current[position:position + chars_added]
        else:
            added = ""
        self._old_text = current
        if removed or added:
            self._ops_callback(position, chars_removed, added)

    def set_ops_callback(self, cb):
        self._ops_callback = cb

    def line_number_width(self) -> int:
        try:
            bc = self.blockCount()
        except Exception:
            bc = 1
        digits = 2
        if bc >= 10000:
            digits = 5
        elif bc >= 1000:
            digits = 4
        elif bc >= 100:
            digits = 3
        try:
            key = (digits, self._font_size)
            cached = self._line_width_cache.get(key)
            if cached is not None:
                return cached
            fm = QFontMetrics(self.font())
            w = 6 + int(fm.horizontalAdvance("9") * digits) + scale(22)
            self._line_width_cache[key] = w
            if len(self._line_width_cache) > 8:
                try:
                    self._line_width_cache.clear()
                except Exception:
                    pass
            return w
        except Exception:
            return scale(52)

    def blame_gutter_width(self) -> int:
        return 0

    def _update_extra(self):
        lw = self.line_number_width()
        mw = self._minimap.width()
        if mw <= 0:
            mw = self._minimap.sizeHint().width()
        bw = self.blame_gutter_width()
        self._line_number.setFixedWidth(lw)
        self._blame_gutter.setFixedWidth(bw)
        self._minimap.setFixedWidth(mw)
        right_margin = mw + bw
        self.setViewportMargins(lw, 0, right_margin, 0)
        cr = self.contentsRect()
        self._line_number.setGeometry(cr.x(), cr.y(), lw, cr.height())
        blame_x = cr.x() + cr.width() - right_margin
        self._blame_gutter.setGeometry(blame_x, cr.y(), bw, cr.height())
        self._minimap.setGeometry(blame_x + bw, cr.y(), mw, cr.height())
        self._line_number.update()
        self._blame_gutter.update()
        self._minimap.update()
        self._position_inspection()

    def _update_line_number(self):
        self._update_extra()

    def _update_minimap(self):
        self._update_extra()

    def _invalidate_minimap(self):
        self._minimap_cache = None
        self._minimap.update()

    def _on_update_request(self, rect, dy):
        if dy:
            self._line_number.scroll(0, dy)
            self._blame_gutter.scroll(0, dy)
        else:
            self._line_number.update(0, rect.y(), self._line_number.width(), rect.height())
            self._blame_gutter.update(0, rect.y(), self._blame_gutter.width(), rect.height())
        self._minimap.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._minimap_cache = None
        self._update_line_number()
        self._update_minimap()
        self._position_inspection()

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

    def line_number_paint(self, event, area):
        painter = QPainter(area)
        painter.setFont(self.font())
        painter.fillRect(event.rect(), QColor(*Theme.gutter))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        cur_block = self.textCursor().blockNumber()
        fm = painter.fontMetrics()
        vcs_colors = {
            "added": QColor(*Theme.added),
            "modified": QColor(*Theme.modified),
            "deleted": QColor(*Theme.deleted),
        }
        err_lines = {d.line for d in self._diagnostic_errors}
        warn_lines = {d.line for d in self._diagnostic_warnings}
        while block.isValid() and top <= event.rect().bottom():
            if not block.isVisible():
                block = block.next()
                block_number += 1
                if not block.isValid():
                    break
                top = bottom
                bottom = top + int(self.blockBoundingRect(block).height())
                continue
            if block.isVisible() and bottom >= event.rect().top():
                line = block_number
                txt = str(line + 1)
                vcs_status = self._vcs_diff_data.get(line, "")
                if line == cur_block:
                    painter.fillRect(0, top, area.width(), int(self.blockBoundingRect(block).height()), QColor(*Theme.gutter_current))
                    painter.setPen(QColor(*Theme.line_number_current))
                elif line in err_lines:
                    painter.setPen(QColor(*Theme.error_red))
                elif line in warn_lines:
                    painter.setPen(QColor(*Theme.warn_yellow))
                elif vcs_status in vcs_colors:
                    painter.setPen(vcs_colors[vcs_status])
                else:
                    painter.setPen(QColor(*Theme.line_number))
                if vcs_status in vcs_colors:
                    marker_w = scale(3)
                    painter.fillRect(0, top, marker_w, int(self.blockBoundingRect(block).height()), vcs_colors[vcs_status])
                painter.drawText(0, top, area.width() - scale(18), fm.height(), Qt.AlignmentFlag.AlignRight, txt)
                if line in self._folded:
                    painter.setPen(QColor(150, 150, 150))
                    painter.drawText(area.width() - scale(14), top, scale(12), fm.height(), Qt.AlignmentFlag.AlignLeft, ">")
                else:
                    t = block.text().strip()
                    if t.startswith("import ") or t.startswith("from ") or t.startswith("class ") or t.startswith("def ") or t.startswith("try:"):
                        painter.setPen(QColor(80, 80, 80))
                        painter.drawText(area.width() - scale(14), top, scale(12), fm.height(), Qt.AlignmentFlag.AlignLeft, "v")
                btxt = block.text().strip()
                if btxt.startswith("class "):
                    painter.setPen(QColor(*Theme.lens_blue))
                    painter.drawText(scale(2), top, scale(12), fm.height(), Qt.AlignmentFlag.AlignLeft, chr(9424))
                if btxt.startswith("def "):
                    painter.setPen(QColor(*Theme.lens_green))
                    painter.drawText(scale(2), top, scale(12), fm.height(), Qt.AlignmentFlag.AlignLeft, chr(11377))
            block = block.next()
            top = bottom
            if not block.isValid():
                break
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    def line_number_mouse_move(self, event: QMouseEvent, area):
        try:
            y = int(event.position().y())
            block = self._find_block_at_y(y)
            if block is not None:
                line = block.blockNumber()
                diags_here: list[str] = []
                for d in self._diagnostic_errors:
                    if d.line == line:
                        diags_here.append("error: " + d.message)
                for d in self._diagnostic_warnings:
                    if d.line == line:
                        diags_here.append("warning: " + d.message)
                if line in self._vcs_blame_data:
                    info = self._vcs_blame_data[line]
                    tip_parts: list[str] = []
                    if diags_here:
                        tip_parts.extend(diags_here)
                    author = info.get("author", "")
                    when = info.get("time_str", "")
                    msg = info.get("message", "")
                    if author or when or msg:
                        tip_parts.append(str(author) + "  " + str(when) + "  " + str(msg))
                    self.setToolTip(chr(10).join(tip_parts))
                else:
                    if diags_here:
                        self.setToolTip(chr(10).join(diags_here))
                    else:
                        self.setToolTip("")
            area.update()
        except Exception:
            pass

    def line_number_mouse_press(self, event: QMouseEvent, area):
        try:
            y = int(event.position().y())
            if event.position().x() > area.width() - scale(16):
                block = self._find_block_at_y(y)
                if block is not None:
                    self._toggle_fold(block.blockNumber())
                    event.accept()
                    return
        except Exception:
            pass

    def line_number_mouse_leave(self, event):
        self.setToolTip("")

    def _find_block_at_y(self, y: int):
        block = self.firstVisibleBlock()
        while block.isValid():
            if not block.isVisible():
                block = block.next()
                continue
            geom = self.blockBoundingGeometry(block).translated(self.contentOffset())
            top = int(geom.top())
            bottom = top + int(self.blockBoundingRect(block).height())
            if top <= y <= bottom:
                return block
            if top > y:
                return None
            block = block.next()
        return None

    def blame_gutter_paint(self, event, area):
        painter = QPainter(area)
        painter.fillRect(event.rect(), QColor(27, 27, 27))
        painter.end()

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

    def minimap_pressed(self, y: int):
        self._minimap_scroll_to(y)

    def minimap_dragged(self, y: int):
        self._minimap_scroll_to(y)

    def _minimap_scroll_to(self, y: int):
        vsb = self.verticalScrollBar()
        if vsb is None:
            return
        total = vsb.maximum() + vsb.pageStep()
        if total <= 0:
            return
        mh = max(1, self._minimap.height())
        ratio = max(0.0, min(1.0, y / mh))
        target = int(ratio * total - vsb.pageStep() * 0.5)
        vsb.setValue(max(0, min(vsb.maximum(), target)))

    def _emit_cursor(self):
        QTimer.singleShot(0, self._report_cursor)

    def _report_cursor(self):
        line = self.textCursor().blockNumber() + 1
        col = self.textCursor().positionInBlock() + 1
        self.cursorMoved.emit(line, col)

    def set_font_size(self, size: int):
        self._font_size = max(self.MIN_FONT, min(self.MAX_FONT, size))
        self._apply_font()

    def zoom(self, delta: int):
        self.set_font_size(self._font_size + (1 if delta > 0 else -1))

    def set_wrap(self, enabled: bool):
        self._wrap = enabled
        self._apply_font()

    def refresh_completions(self):
        try:
            if not self._completion_dirty and self._completer.model() is not None:
                return
            self._rebuild_completions()
        except Exception:
            pass

    def _rebuild_completions(self):
        try:
            base = set(KEYWORDS) | set(BUILTINS) | set(CONSTANTS) | set(EXCEPTIONS) | set(ENGINE_API_WORDS)
            try:
                bc = self.blockCount()
            except Exception:
                bc = 0
            if bc > 5000:
                model = QStringListModel(sorted(base), self)
                self._completer.setModel(model)
                self._completion_cache = sorted(base)
                self._completion_dirty = False
                return
            text = self.toPlainText()
            if len(text) > 400000:
                text = text[:400000]
            seen: set[str] = set(base)
            extra: list[str] = []
            for match in re.finditer(r"[A-Za-z_]\w{1,40}", text):
                w = match.group(0)
                if w not in seen:
                    seen.add(w)
                    extra.append(w)
                    if len(extra) >= 2500:
                        break
            words = sorted(seen)[:4000]
            model = QStringListModel(words, self)
            self._completer.setModel(model)
            self._completion_cache = words
            self._completion_dirty = False
        except Exception:
            pass

    def _word_under_cursor(self) -> QTextCursor:
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor

    def _insert_completion(self, completion: str):
        cursor = self._word_under_cursor()
        extra = len(completion) - len(self._completer.completionPrefix())
        if extra > 0:
            cursor.insertText(completion[-extra:])
            self.setTextCursor(cursor)

    def _update_completer_popup(self):
        cursor = self._word_under_cursor()
        prefix = cursor.selectedText()
        if not prefix or prefix[0].isdigit():
            self._completer.popup().hide()
            return
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            self._completer.popup().hide()
            return
        popup = self._completer.popup()
        if popup is None:
            return
        scroll = popup.verticalScrollBar()
        scroll_width = scroll.sizeHint().width() if scroll is not None else 0
        rect = self.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + scroll_width)
        self._completer.complete(rect)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self._doc_popup.isVisible():
                self._doc_popup.hide()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.show_documentation_at_cursor():
                event.accept()
                return
        if event.key() == Qt.Key.Key_F1:
            if self.show_documentation_at_cursor():
                event.accept()
                return
        popup = self._completer.popup()
        if popup.isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab, Qt.Key.Key_Escape):
                event.ignore()
                return
        if event.key() == Qt.Key.Key_Tab:
            if self.textCursor().hasSelection():
                self._indent_selected_lines()
            else:
                self.textCursor().insertText("    ")
            return
        if event.key() == Qt.Key.Key_Backtab:
            self._unindent_selected_lines()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._auto_indent(event)
            return
        if event.key() == Qt.Key.Key_Space and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            try:
                self._rebuild_completions()
            except Exception:
                pass
            self._update_completer_popup()
            return
        super().keyPressEvent(event)
        if event.text() and event.text().isalnum() or event.key() == Qt.Key.Key_Period:
            try:
                if self._completion_dirty:
                    self._rebuild_completions()
            except Exception:
                pass
            self._update_completer_popup()

    def _auto_indent(self, event: QKeyEvent):
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.insertText("\n")
            self.setTextCursor(cursor)
            return
        block = cursor.block()
        text = block.text()
        indent = len(text) - len(text.lstrip())
        indent_text = text[:indent]
        h = chr(35)
        code = text.split(h, 1)[0].rstrip()
        if code.endswith(":"):
            indent_text += "    "
        cursor.insertText("\n" + indent_text)
        self.setTextCursor(cursor)

    def _indent_selected_lines(self):
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        start_block = cursor.block().blockNumber()
        cursor.setPosition(end)
        end_block = cursor.block().blockNumber()
        if end_block > start_block and cursor.atBlockStart() and end != start:
            end_block -= 1
        if end_block < start_block:
            return
        cursor.beginEditBlock()
        for number in range(start_block, end_block + 1):
            block = self.document().findBlockByNumber(number)
            cursor.setPosition(block.position())
            cursor.insertText("    ")
        cursor.endEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(end + 4 * (end_block - start_block + 1), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def _unindent_selected_lines(self):
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        start_block = cursor.block().blockNumber()
        start_block_pos = self.document().findBlockByNumber(start_block).position()
        cursor.setPosition(end)
        end_block = cursor.block().blockNumber()
        if end_block > start_block and cursor.atBlockStart() and end != start:
            end_block -= 1
        if end_block < start_block:
            return
        cursor.beginEditBlock()
        removed_first = 0
        total_removed = 0
        for number in range(start_block, end_block + 1):
            block = self.document().findBlockByNumber(number)
            text = block.text()
            remove = 0
            if text.startswith("    "):
                remove = 4
            elif text.startswith("\t"):
                remove = 1
            else:
                while remove < 4 and remove < len(text) and text[remove] == " ":
                    remove += 1
            if remove:
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, remove)
                cursor.removeSelectedText()
                if number == start_block:
                    removed_first = remove
                total_removed += remove
        cursor.endEditBlock()
        new_start = max(start - removed_first, start_block_pos)
        new_end = end - total_removed
        cursor.setPosition(new_start)
        cursor.setPosition(max(new_start, new_end), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def focusInEvent(self, event):
        self._completer.setWidget(self)
        super().focusInEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        try:
            tc = self.cursorForPosition(event.pos())
            if tc.isNull():
                return
            blk = tc.block()
            txt = blk.text()
            off = tc.positionInBlock()
            word = docs.word_at(txt, off)
            if word and docs.is_doc_trigger(word):
                self.setToolTip("Press Ctrl+Q for documentation")
            else:
                errs = [d for d in self._diagnostic_errors if d.line == blk.blockNumber()]
                warns = [d for d in self._diagnostic_warnings if d.line == blk.blockNumber()]
                msgs: list[str] = []
                for d in errs:
                    msgs.append("error: " + d.message)
                for d in warns:
                    msgs.append("warning: " + d.message)
                if msgs:
                    self.setToolTip(chr(10).join(msgs[:4]))
                else:
                    self.setToolTip("")
        except Exception:
            pass

    def vcs_set_git(self, git):
        self._vcs_git = git

    def vcs_set_file(self, path: str):
        self._vcs_file_path = path
        self.vcs_refresh()

    def vcs_refresh(self):
        self._vcs_blame_data = {}
        self._vcs_diff_data = {}
        self._vcs_status = ""
        self._vcs_branch = ""
        if self._vcs_git is None:
            self._update_extra()
            return
        try:
            if not self._vcs_git.available or not self._vcs_git.repo_root:
                self._update_extra()
                return
        except Exception:
            self._update_extra()
            return
        if not self._vcs_file_path:
            self._update_extra()
            return
        try:
            rel = os.path.relpath(self._vcs_file_path, self._vcs_git.repo_root)
        except ValueError:
            self._update_extra()
            return
        rel = rel.replace("\\", "/")
        if self._vcs_refreshing:
            self._vcs_pending = True
            return
        self._vcs_refreshing = True
        threading.Thread(
            target=self._vcs_worker,
            args=(self._vcs_git, rel, self._vcs_file_path, self._show_blame),
            daemon=True,
        ).start()

    def _vcs_worker(self, git, rel: str, file_path: str, show_blame: bool):
        result: dict = {"branch": "", "status": "", "diff_data": {}, "blame_data": {}}
        try:
            result["branch"] = git.current_branch()
            rc, out, _ = git.status()
            if rc == 0:
                for entry in out.strip().split("\n"):
                    entry = entry.rstrip()
                    if not entry or len(entry) < 3:
                        continue
                    xy = entry[:2]
                    path = entry[3:]
                    if path == rel:
                        if xy[0] == "?" and xy[1] == "?":
                            result["status"] = "untracked"
                        elif xy[0] == "M" or xy[1] == "M" or xy[0] == "A":
                            result["status"] = "modified"
                        elif xy[0] == "D" or xy[1] == "D":
                            result["status"] = "deleted"
                        elif xy[0] == "U" or xy[1] == "U":
                            result["status"] = "conflict"
                        break
            diff_text = git.file_diff(rel)
            if diff_text:
                current = None
                for line in diff_text.split("\n"):
                    if line.startswith("@@ "):
                        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                        if m:
                            current = int(m.group(1))
                    elif line.startswith("+"):
                        if current is not None:
                            result["diff_data"][current - 1] = "added"
                        current = (current or 0) + 1
                    elif line.startswith("-"):
                        pass
                    elif line.startswith(" "):
                        if current is not None:
                            current += 1
            if show_blame:
                try:
                    if "GIT_AUTHOR_NAME" not in os.environ:
                        os.environ["GIT_AUTHOR_NAME"] = ""
                    if "GIT_COMMITTER_NAME" not in os.environ:
                        os.environ["GIT_COMMITTER_NAME"] = ""
                    blame_text = git.blame(file_path)
                    parsed = blame_mod.parse_blame_output(blame_text if blame_text else "")
                    parsed = blame_mod.enrich_with_log(parsed, git)
                    result["blame_data"] = parsed
                except Exception:
                    result["blame_data"] = {}
        except Exception:
            pass
        try:
            self._vcs_result_ready.emit(result)
        except Exception:
            try:
                self.vcs_result_ready.emit(result)
            except Exception:
                pass

    def _on_vcs_result(self, result: dict):
        self._vcs_refreshing = False
        try:
            self._vcs_branch = result.get("branch", "")
            self._vcs_status = result.get("status", "")
            self._vcs_diff_data = result.get("diff_data", {})
            self._vcs_blame_data = result.get("blame_data", {})
            self._update_extra()
            self._line_number.update()
            self._blame_gutter.update()
            self.viewport().update()
        except RuntimeError:
            pass
        if self._vcs_pending:
            self._vcs_pending = False
            self.vcs_refresh()

    def vcs_set_blame_visible(self, visible: bool):
        self._show_blame = visible
        self.vcs_refresh()
        self._update_extra()
        self._blame_gutter.update()
        self.viewport().update()

    def vcs_is_blame_visible(self) -> bool:
        return self._show_blame

    def vcs_branch(self) -> str:
        return self._vcs_branch

    def vcs_file_status(self) -> str:
        return self._vcs_status


_CodeEditor = CodeEditor
_LineNumberArea = LineNumberArea
_VcsBlameGutter = VcsBlameGutter
_Minimap = StripeBar
