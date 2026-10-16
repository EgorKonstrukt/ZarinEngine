# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import re
from PySide6.QtCore import Qt, QStringListModel, QTimer, QPoint
from PySide6.QtGui import QColor, QFontMetrics, QKeyEvent, QPainter, QTextCursor
from core.config.editor_scale import scale
from ..theme import Theme
from .. import doc_provider as docs
from .. import folding as fld
from ...syntax_config import KEYWORDS, BUILTINS, CONSTANTS, EXCEPTIONS
from ..api_words import ENGINE_API_WORDS
class CompleteMixin:
    def _mark_completion_dirty(self):
        try:
            self._completion_dirty = True
            if not self._completion_timer.isActive():
                self._completion_timer.start(1200)
        except Exception:
            pass
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
        if not prefix or len(prefix) < 2 or prefix[0].isdigit():
            try:
                self._completer.popup().hide()
            except Exception:
                pass
            return
        self._completer.setCompletionPrefix(prefix)
        try:
            if self._completer.completionCount() == 0:
                self._completer.popup().hide()
                return
        except Exception:
            return
        try:
            rect = self.cursorRect()
            rect.setWidth(scale(320))
            self._completer.complete(rect)
        except Exception:
            pass
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
                self._mark_completion_dirty()
            except Exception:
                pass
            try:
                if not self._completion_dirty:
                    self._update_completer_popup()
            except Exception:
                pass
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
    def _draw_fold_placeholders(self, event, painter=None):
        if not self._folded:
            return
        own = False
        if painter is None:
            painter = QPainter(self.viewport())
            own = True
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
        if own:
            painter.end()
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
            self._err_line_set = set()
            self._warn_line_set = set()
            self._diag_map = {}
            self._foldable_set = set()
            self._class_lines = set()
            self._def_lines = set()
            try:
                for idx, ln in enumerate(text.splitlines()):
                    if len(ln) < 4:
                        continue
                    s = ln.strip()
                    if s.startswith("class "):
                        self._foldable_set.add(idx)
                        self._class_lines.add(idx)
                    elif s.startswith("def "):
                        self._foldable_set.add(idx)
                        self._def_lines.add(idx)
                    elif s.startswith("import ") or s.startswith("from ") or s.startswith("try:"):
                        self._foldable_set.add(idx)
                    if len(self._foldable_set) > 4000:
                        break
            except Exception:
                pass
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
    def _draw_diff_markers(self, event, painter=None):
        try:
            if not self._vcs_diff_data:
                return
            viewport_h = self.viewport().height()
            first = self.firstVisibleBlock()
            if not first.isValid():
                return
            own = False
            if painter is None:
                painter = QPainter(self.viewport())
                own = True
            try:
                lh = self._cached_line_height()
            except Exception:
                lh = 18
            offset_x = int(self.contentOffset().x())
            marker_w = scale(3)
            c_add = QColor(*Theme.added)
            c_mod = QColor(*Theme.modified)
            c_del = QColor(*Theme.deleted)
            rt = event.rect().top()
            coff = self.contentOffset()
            try:
                y0 = int(self.blockBoundingGeometry(first).translated(coff).top())
            except Exception:
                y0 = 0
            try:
                lh = self._cached_line_height()
            except Exception:
                lh = 18
            vis_idx = 0
            block = first
            while block.isValid():
                if not block.isVisible():
                    block = block.next()
                    continue
                top = y0 + vis_idx * lh
                vis_idx += 1
                if top > viewport_h:
                    break
                line = block.blockNumber()
                status = self._vcs_diff_data.get(line, "")
                if not status:
                    block = block.next()
                    continue
                bottom = top + lh
                if bottom >= rt:
                    if status == "added":
                        painter.fillRect(offset_x, top, marker_w, bottom - top, c_add)
                    elif status == "modified":
                        painter.fillRect(offset_x, top, marker_w, bottom - top, c_mod)
                    elif status == "deleted":
                        painter.fillRect(offset_x, top + (bottom - top) // 2 - 1, marker_w, 2, c_del)
                block = block.next()
            if own:
                painter.end()
        except Exception:
            pass
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
