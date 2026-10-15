# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QFileDialog
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QPainterPath
import editor.icons as qta
from core.foundation.time_travel import FrameSnapshot, diff_scenes
from core.config.editor_scale import scale
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
def _heat_color(t: float) -> QColor:
    r = min(255, int(255 * t * 2))
    g = min(255, int(255 * (1 - t) * 2))
    return QColor(r, g, 80)
class _TimelineScrubber(QWidget):
    MIN_PPF = 3
    MAX_PPF = 80
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: list[FrameSnapshot] = []
        self._current: int = -1
        self._hover: int = -1
        self._ppf: float = 8.0
        self._scroll: float = 0.0
        self._dragging: bool = False
        self._show_heat: bool = False
        self._max_time_ms: float = 33.0
        self.setMinimumHeight(scale(80))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._font = QFont("Segoe UI", 8)
        self._small = QFont("Segoe UI", 7)
    def ruler_h(self) -> int: return scale(28)
    def bar_h(self) -> int: return scale(44)
    def total_h(self) -> int: return self.ruler_h() + self.bar_h() + scale(4)
    def set_frames(self, frames: list[FrameSnapshot]):
        self._frames = frames
        if frames:
            times = [f.frame_time_ms for f in frames if f.frame_time_ms > 0]
            if times:
                self._max_time_ms = max(times)
        self._current = min(self._current, len(frames) - 1) if frames else -1
        self.update()
    def set_current(self, idx: int):
        self._current = max(-1, min(idx, len(self._frames) - 1))
        self._ensure_visible()
        self.update()
    def current_index(self) -> int: return self._current
    def frame_count(self) -> int: return len(self._frames)
    def set_heatmap(self, on: bool):
        self._show_heat = on
        self.update()
    def _frame_at(self, x: float) -> int:
        if not self._frames:
            return -1
        i = int((x + self._scroll) / self._ppf)
        return max(0, min(len(self._frames) - 1, i))
    def _x_of(self, i: int) -> float:
        return i * self._ppf - self._scroll
    def _ensure_visible(self):
        if self._current < 0:
            return
        cx = self._current * self._ppf
        vw = self.width()
        if cx < self._scroll:
            self._scroll = cx - vw * 0.1
        elif cx > self._scroll + vw - 20:
            self._scroll = cx - vw * 0.8
        self._scroll = max(0, self._scroll)
    def _call(self, attr: str, *args):
        p = self.parent()
        while p and not hasattr(p, attr):
            p = p.parent()
        if p:
            getattr(p, attr)(*args)
    def mousePressEvent(self, event):
        if not self._frames:
            super().mousePressEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            idx = self._frame_at(event.position().x())
            self._call("_on_bookmark_toggle", idx)
            self.update()
        else:
            self._dragging = True
            self._current = self._frame_at(event.position().x())
            self._call("_on_frame_restore", self._current)
            self.update()
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event):
        old_h = self._hover
        self._hover = self._frame_at(event.position().x())
        if self._dragging and self._frames:
            i = self._frame_at(event.position().x())
            if 0 <= i < len(self._frames) and i != self._current:
                self._current = i
                self._call("_on_frame_peek", i)
                self.update()
        if old_h != self._hover:
            self.update()
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            if self._current >= 0:
                self._call("_on_frame_restore", self._current)
            self.update()
        super().mouseReleaseEvent(event)
    def leaveEvent(self, event):
        self._hover = -1
        self._dragging = False
        self.update()
        super().leaveEvent(event)
    def wheelEvent(self, event):
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            old = self._ppf
            self._ppf *= 1.15 if event.angleDelta().y() > 0 else 0.87
            self._ppf = max(self.MIN_PPF, min(self.MAX_PPF, self._ppf))
            cx = event.position().x() + self._scroll
            self._scroll = max(0, cx - event.position().x())
        else:
            n = len(self._frames)
            if n == 0:
                super().wheelEvent(event)
                return
            step = -1 if event.angleDelta().y() > 0 else 1
            idx = max(0, min(n - 1, self._current + step))
            if idx != self._current:
                self._call("_on_frame_restore", idx)
        self.update()
        super().wheelEvent(event)
    def keyPressEvent(self, event):
        if not self._frames:
            super().keyPressEvent(event)
            return
        k = event.key()
        n = len(self._frames) - 1
        if k == Qt.Key.Key_Left:
            self._call("_on_frame_restore", max(0, self._current - 1))
        elif k == Qt.Key.Key_Right:
            self._call("_on_frame_restore", min(n, self._current + 1))
        elif k == Qt.Key.Key_Home:
            self._call("_on_frame_restore", 0)
        elif k == Qt.Key.Key_End:
            self._call("_on_frame_restore", n)
        elif k == Qt.Key.Key_PageUp:
            step = max(1, int(self.width() / max(self._ppf, 1)))
            self._call("_on_frame_restore", max(0, self._current - step))
        elif k == Qt.Key.Key_PageDown:
            step = max(1, int(self.width() / max(self._ppf, 1)))
            self._call("_on_frame_restore", min(n, self._current + step))
        else:
            super().keyPressEvent(event)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = self.width()
        rh = self.ruler_h()
        bh = self.bar_h()
        ppf = self._ppf
        n = len(self._frames)
        painter.fillRect(0, 0, w, self.height(), _C_BG)
        if n == 0:
            painter.setPen(_C_DIM)
            painter.setFont(self._font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Record to capture snapshots")
            painter.end()
            return
        bar_y = rh + scale(2)
        vs = max(0, int(self._scroll / ppf))
        ve = min(n, int((self._scroll + w) / ppf) + 1)
        painter.fillRect(0, 0, w, rh, _C_RULER)
        step = max(1, int(30 / ppf))
        for i in range(vs, ve, step):
            x = self._x_of(i)
            if x < -20 or x > w + 20:
                continue
            painter.setPen(_C_RULER_TICK)
            painter.drawLine(int(x), rh - scale(6), int(x), rh)
            painter.setPen(_C_RULER_LABEL)
            painter.setFont(self._small)
            painter.drawText(int(x) + scale(3), rh - scale(8), str(i))
        for i in range(vs, ve):
            if self._frames[i].bookmarked:
                x = self._x_of(i)
                painter.fillRect(int(x), 0, max(1, int(ppf)), scale(4), _C_BOOKMARK)
        for i in range(vs, ve):
            if self._frames[i].breakpoint_hit:
                x = self._x_of(i)
                painter.fillRect(int(x), scale(4), max(1, int(ppf)), scale(4), _C_BREAKPOINT)
        painter.setPen(_C_RULER_LINE)
        painter.drawLine(0, rh, w, rh)
        max_ent = max(f.entity_count for f in self._frames) or 1
        for i in range(vs, ve):
            x = self._x_of(i)
            f = self._frames[i]
            bw = max(1, ppf - 1)
            ent_h = max(2, int((f.entity_count / max_ent) * (bh - scale(4))))
            if self._show_heat and f.frame_time_ms > 0:
                t = min(1.0, f.frame_time_ms / max(self._max_time_ms, 1))
                color = _heat_color(t)
            elif i == self._current:
                color = _C_PLAYHEAD
            elif i == self._hover:
                color = _C_HOVER
            else:
                v = int(80 + (f.entity_count / max_ent) * 120)
                color = QColor(v, v, v)
            painter.fillRect(QRectF(x, bar_y + bh - ent_h, bw, ent_h), color)
        painter.setPen(_C_RULER_LINE)
        painter.drawLine(0, bar_y + bh, w, bar_y + bh)
        if self._current >= 0:
            px = self._x_of(self._current)
            painter.setPen(QPen(_C_PLAYHEAD, 2))
            painter.drawLine(int(px), 0, int(px), bar_y + bh)
            path = QPainterPath()
            path.moveTo(int(px), scale(6))
            path.lineTo(int(px) - scale(5), scale(6) + scale(7))
            path.lineTo(int(px) + scale(5), scale(6) + scale(7))
            path.closeSubpath()
            painter.fillPath(path, _C_PLAYHEAD)
        if self._current >= 0 and self._current < n:
            f = self._frames[self._current]
            painter.setPen(_C_PLAYHEAD)
            painter.setFont(self._font)
            parts = [f"{_H}{f.frame_number}", f"{f.entity_count}e"]
            if f.frame_time_ms > 0:
                parts.append(f"{f.frame_time_ms:.1f}ms")
            info = "  ".join(parts)
            tw = painter.fontMetrics().horizontalAdvance(info) + scale(10)
            ir = QRectF(w - tw - scale(4), bar_y + bh + scale(2), tw, scale(18))
            painter.fillRect(ir, _C_BG)
            painter.drawText(ir, Qt.AlignmentFlag.AlignCenter, info)
        painter.end()
class TimeTravelPlaybackMixin:
    def _go_first(self):
        self._on_frame_restore(0)
    def _go_back10(self):
        self._on_frame_restore(max(0, self._timeline.current_index() - 10))
    def _go_back1(self):
        self._on_frame_restore(max(0, self._timeline.current_index() - 1))
    def _toggle_play(self):
        if self._playing:
            self._playing = False
            self._play_timer.stop()
            self._play_btn.setIcon(qta.icon("fa5s.play", color=_H + "d4d4d4"))
        else:
            if self._timeline.current_index() < 0 and self._recorder and self._recorder.num_frames > 0:
                self._on_frame_restore(0)
            if self._timeline.current_index() >= 0:
                self._playing = True
                speed = max(0.1, self._speed_sb.value())
                self._play_timer.setInterval(int(33 / speed))
                self._play_timer.start()
                self._play_btn.setIcon(qta.icon("fa5s.pause", color=_H + "d4d4d4"))
    def _go_forward1(self):
        n = self._recorder.num_frames if self._recorder else 0
        self._on_frame_restore(min(n - 1, self._timeline.current_index() + 1))
    def _go_forward10(self):
        n = self._recorder.num_frames if self._recorder else 0
        self._on_frame_restore(min(n - 1, self._timeline.current_index() + 10))
    def _go_last(self):
        if self._recorder and self._recorder.num_frames > 0:
            self._on_frame_restore(self._recorder.num_frames - 1)
    def _play_step(self):
        idx = self._timeline.current_index()
        n = self._recorder.num_frames if self._recorder else 0
        if idx < 0 or idx >= n - 1:
            self._toggle_play()
            return
        speed = max(0.1, self._speed_sb.value())
        self._play_timer.setInterval(int(33 / speed))
        self._on_frame_restore(idx + 1)
    def _on_speed_changed(self, val: float):
        if self._playing:
            self._play_timer.setInterval(int(33 / max(0.1, val)))
    def _on_frame_peek(self, idx: int):
        if not self._recorder:
            return
        snap = self._recorder.get_frame(idx)
        if snap:
            self._update_labels(snap)
    def _on_frame_restore(self, idx: int):
        if not self._recorder or not self._recorder.num_frames:
            return
        idx = max(0, min(idx, self._recorder.num_frames - 1))
        snap = self._recorder.get_frame(idx)
        if snap is None:
            return
        if not self._restored and self._engine.scene:
            self._live_data = self._engine.scene.serialize()
            self._prev_frame_data = None
        if self._engine.play_mode:
            self._engine.stop_play()
        from core.ecs import Scene as SceneCls
        restored = SceneCls.deserialize(snap.data, self._engine._component_registry)
        restored.mark_dirty()
        old_path = self._engine.scene.path if self._engine.scene else None
        if old_path:
            restored.path = old_path
        self._engine._scene = restored
        self._engine._emit_event("scene_loaded", restored)
        self._restored = True
        self._live_btn.setEnabled(True)
        self._diff_cache = None
        if self._prev_frame_data is not None and idx > 0:
            self._diff_cache = diff_scenes(self._prev_frame_data, snap.data)
            self._diff_names = {}
            for eid in set(self._diff_cache.get("created", [])) | set(self._diff_cache.get("deleted", [])) | set(self._diff_cache.get("changed", {}).keys()):
                self._diff_names[eid] = snap.data.get("entities", {}).get(eid, {}).get("name", eid)
        self._prev_frame_data = snap.data
        if self._bottom_tabs.currentIndex() == 0:
            self._refresh_diff_tab()
        self._timeline.set_current(idx)
        self._update_labels(snap)
    def _go_live(self):
        if self._live_data is not None and self._engine.scene is not None:
            from core.ecs import Scene as SceneCls
            live = SceneCls.deserialize(self._live_data, self._engine._component_registry)
            live.mark_dirty()
            old_path = self._engine.scene.path if self._engine.scene else None
            if old_path:
                live.path = old_path
            self._engine._scene = live
            self._engine._emit_event("scene_loaded", live)
            self._live_data = None
            self._restored = False
            self._prev_frame_data = None
            self._diff_cache = None
            self._live_btn.setEnabled(False)
            self._status_lbl.setText("Live")
            self._timeline.set_current(-1)
            self._frame_lbl.setText("Live scene")
            self._diff_tree.clear()
    def _export_frame(self):
        if not self._recorder:
            return
        idx = self._timeline.current_index()
        snap = self._recorder.get_frame(idx)
        if not snap:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Frame as Scene", f"frame_{snap.frame_number}.zpes",
            "Scene (*.zpes)")
        if path:
            self._recorder.export_frame(idx, path)
