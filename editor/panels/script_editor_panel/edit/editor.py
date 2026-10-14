# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PyQt6.QtWidgets import QPlainTextEdit, QCompleter
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen, QTextCursor, QWheelEvent
from core.config.editor_scale import scale
from ..theme import Theme, editor_stylesheet, editor_font
from ..gutter import LineNumberArea, VcsBlameGutter
from ..stripe import StripeBar
from ..inspection import InspectionOverlay
from ..doc_popup import DocPopup
from ..smooth import SmoothScrollState
from .highlight import HighlightMixin
from .complete import CompleteMixin
from .search import SearchMixin
class CodeEditor(HighlightMixin, CompleteMixin, SearchMixin, QPlainTextEdit):
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
        self._err_line_set: set = set()
        self._warn_line_set: set = set()
        self._diag_map: dict[int, list] = {}
        self._foldable_set: set = set()
        self._class_lines: set = set()
        self._def_lines: set = set()
        self._cached_lh = 0
        self._cached_space_w = 0.0
        self._cached_tab_w = 0.0
        self._pen_guide = QPen(QColor(*Theme.indent_guide))
        self._pen_guide_active = QPen(QColor(*Theme.indent_guide_active))
        self._pen_lens = QPen(QColor(*Theme.lens))
        self._pen_lens_green = QPen(QColor(*Theme.lens_green))
        self._pen_lens_blue = QPen(QColor(*Theme.lens_blue))
        self._minimap_throttle = QTimer(self)
        self._minimap_throttle.setSingleShot(True)
        self._minimap_throttle.setInterval(50)
        self._minimap_throttle.timeout.connect(self._flush_minimap)
        self._minimap_pending = False
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
        try:
            self._smooth = SmoothScrollState(self, self)
        except Exception:
            self._smooth = None
        try:
            self.setCenterOnScroll(False)
        except Exception:
            pass
        try:
            vsb = self.verticalScrollBar()
            vsb.setSingleStep(1)
        except Exception:
            pass
        self._update_line_number()
        self._update_minimap()
        self._update_current_line_only()
        try:
            self.verticalScrollBar().valueChanged.connect(lambda v: self._queue_minimap())
        except Exception:
            pass
        QTimer.singleShot(600, self._run_analysis)
    def _apply_font(self):
        f = editor_font(self._font_size)
        self.setFont(f)
        try:
            self._cached_lh = int(QFontMetrics(f).height())
        except Exception:
            self._cached_lh = 0
        try:
            self._cached_space_w = 0.0
            self._cached_tab_w = 0.0
            self._line_width_cache = {}
        except Exception:
            pass
        try:
            self._pen_guide = QPen(QColor(*Theme.indent_guide))
            self._pen_guide_active = QPen(QColor(*Theme.indent_guide_active))
            self._pen_lens = QPen(QColor(*Theme.lens))
            self._pen_lens_green = QPen(QColor(*Theme.lens_green))
            self._pen_lens_blue = QPen(QColor(*Theme.lens_blue))
        except Exception:
            pass
        self.setTabStopDistance(QFontMetrics(f).horizontalAdvance(" ") * 4)
        self.setStyleSheet(editor_stylesheet())
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if self._wrap
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._minimap_cache = None
        QTimer.singleShot(0, self._update_minimap)
    def set_font_size(self, size: int):
        self._font_size = max(self.MIN_FONT, min(self.MAX_FONT, size))
        self._apply_font()
    def zoom(self, delta: int):
        self.set_font_size(self._font_size + (1 if delta > 0 else -1))
    def set_wrap(self, enabled: bool):
        self._wrap = enabled
        self._apply_font()
    def _cached_line_height(self) -> int:
        try:
            if self._cached_lh > 0:
                return self._cached_lh
            h = QFontMetrics(self.font()).height()
            if h <= 0:
                h = 18
            self._cached_lh = int(h)
            return self._cached_lh
        except Exception:
            return 18
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
        self._queue_minimap()
    def _queue_minimap(self):
        try:
            try:
                if self._smooth and self._smooth.is_scrolling():
                    self._minimap_pending = True
                    return
            except Exception:
                pass
            if self._minimap_throttle.isActive():
                self._minimap_pending = True
                return
            self._minimap_throttle.start()
            self._minimap.update()
        except Exception:
            try:
                self._minimap.update()
            except Exception:
                pass
    def _flush_minimap(self):
        try:
            if self._minimap_pending:
                self._minimap_pending = False
                self._minimap.update()
        except Exception:
            pass
    def _on_smooth_idle(self):
        try:
            self.viewport().update()
            self._line_number.update()
            try:
                if self._minimap_pending:
                    self._minimap_pending = False
                    self._minimap_cache = None
                    self._minimap.update()
            except Exception:
                pass
        except Exception:
            pass
    def _on_update_request(self, rect, dy):
        if dy:
            self._line_number.scroll(0, dy)
            self._blame_gutter.scroll(0, dy)
        else:
            self._line_number.update(0, rect.y(), self._line_number.width(), rect.height())
            self._blame_gutter.update(0, rect.y(), self._blame_gutter.width(), rect.height())
        self._queue_minimap()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._minimap_cache = None
        self._update_line_number()
        self._update_minimap()
        self._position_inspection()
    def paintEvent(self, event):
        super().paintEvent(event)
        try:
            try:
                fast = bool(self._smooth and self._smooth.is_scrolling())
            except Exception:
                fast = False
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            try:
                if self._show_indent_guides:
                    self._draw_indent_guides(event, painter)
                if self._vcs_diff_data:
                    self._draw_diff_markers(event, painter)
                if self._folded:
                    self._draw_fold_placeholders(event, painter)
                if fast:
                    painter.end()
                    return
                if self._remote_cursors:
                    painter.end()
                    self._draw_remote_cursors(event, None)
                    painter = QPainter(self.viewport())
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                if self._vision_usages or self._vision_complexity:
                    self._draw_code_vision(event, painter)
                if self._show_blame and self._vcs_blame_data:
                    self._draw_current_blame(event, painter)
            except Exception:
                pass
            try:
                painter.end()
            except Exception:
                pass
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
    def set_remote_cursors(self, cursors: dict[str, dict]):
        self._remote_cursors = dict(cursors)
        self._update_current_line_only()
        self.viewport().update()
    def _update_remote_extra_selections(self):
        self._update_current_line_highlight()
    def _draw_remote_cursors(self, event, painter=None):
        if not self._remote_cursors:
            return
        own = False
        if painter is None:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            own = True
        else:
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            except Exception:
                pass
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
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        except Exception:
            pass
        if own:
            painter.end()
    def focusInEvent(self, event):
        self._completer.setWidget(self)
        super().focusInEvent(event)
    def wheelEvent(self, event: QWheelEvent):
        try:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.zoom(event.angleDelta().y())
                event.accept()
                return
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().wheelEvent(event)
                return
            try:
                pd = event.pixelDelta()
            except Exception:
                pd = None
            handled = False
            try:
                if pd is not None and (pd.x() != 0 or pd.y() != 0):
                    if abs(pd.y()) >= abs(pd.x()):
                        handled = bool(self._smooth and self._smooth.add_pixels(float(pd.y())))
                    else:
                        super().wheelEvent(event)
                        return
                else:
                    ad = event.angleDelta()
                    dy = float(ad.y())
                    if dy != 0.0:
                        handled = bool(self._smooth and self._smooth.add_wheel(dy))
            except Exception:
                handled = False
            if handled:
                event.accept()
                return
        except Exception:
            pass
        super().wheelEvent(event)
    def _emit_cursor(self):
        QTimer.singleShot(0, self._report_cursor)
    def _report_cursor(self):
        line = self.textCursor().blockNumber() + 1
        col = self.textCursor().positionInBlock() + 1
        self.cursorMoved.emit(line, col)
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
