# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as _np

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen


_frame_metrics_cache: dict = {"key": None, "val": None}
_SPIKE_LOG: list = []
_last_spike_cumulative: dict = {}


def compute_frame_metrics(frame_times_ms) -> dict:
    if not frame_times_ms:
        return {
            'fps': 0.0, 'avg_fps': 0.0, 'max_fps': 0.0, 'min_fps': 0.0,
            'p1_fps': 0.0, 'p01_fps': 0.0, 'frame_ms': 0.0, 'avg_ms': 0.0,
            'p1_ms': 0.0, 'p01_ms': 0.0,
        }
    n = len(frame_times_ms)
    key = (n, frame_times_ms[-1] if n else 0, round(sum(frame_times_ms) * 0.1))
    cached = _frame_metrics_cache.get("key")
    if cached == key and _frame_metrics_cache.get("val") is not None:
        return _frame_metrics_cache["val"]
    try:
        arr = _np.asarray(frame_times_ms, dtype=_np.float32)
        s = _np.sort(arr)
        avg_ms = float(_np.mean(s))
        p1_c = max(1, int(n * 0.01))
        p01_c = max(1, int(n * 0.001))
        p1_ms = float(_np.mean(s[-p1_c:]))
        p01_ms = float(_np.mean(s[-p01_c:]))
        max_ms = float(s[0])
        min_ms = float(s[-1])
    except Exception:
        s = sorted(frame_times_ms)
        avg_ms = sum(s) / n
        p1_c = max(1, int(n * 0.01))
        p01_c = max(1, int(n * 0.001))
        p1_ms = sum(s[-p1_c:]) / p1_c
        p01_ms = sum(s[-p01_c:]) / p01_c
        max_ms = s[0]
        min_ms = s[-1]
    val = {
        'fps': 1000.0 / max(avg_ms, 0.01),
        'avg_fps': 1000.0 / max(avg_ms, 0.01),
        'max_fps': 1000.0 / max(max_ms, 0.01),
        'min_fps': 1000.0 / max(min_ms, 0.01),
        'p1_fps': 1000.0 / max(p1_ms, 0.01),
        'p01_fps': 1000.0 / max(p01_ms, 0.01),
        'frame_ms': frame_times_ms[-1],
        'avg_ms': avg_ms,
        'p1_ms': p1_ms,
        'p01_ms': p01_ms,
    }
    _frame_metrics_cache["key"] = key
    _frame_metrics_cache["val"] = val
    return val


def compute_tick_metrics(tick_dts) -> dict:
    try:
        dts = [float(d) for d in (tick_dts or []) if d and float(d) > 0.0]
    except Exception:
        return {'tps_p1': 0.0, 'tps_p01': 0.0}
    n = len(dts)
    if n < 10:
        return {'tps_p1': 0.0, 'tps_p01': 0.0}
    try:
        arr = _np.asarray(dts, dtype=_np.float32)
        s = _np.sort(arr)
        p1_c = max(1, int(n * 0.01))
        p01_c = max(1, int(n * 0.001))
        p1_dt = float(_np.mean(s[-p1_c:]))
        p01_dt = float(_np.mean(s[-p01_c:]))
    except Exception:
        s = sorted(dts)
        p1_c = max(1, int(n * 0.01))
        p01_c = max(1, int(n * 0.001))
        p1_dt = sum(s[-p1_c:]) / p1_c
        p01_dt = sum(s[-p01_c:]) / p01_c
    return {
        'tps_p1': 1.0 / max(p1_dt, 1e-6),
        'tps_p01': 1.0 / max(p01_dt, 1e-6),
    }


def _draw_bar_chart(painter, values, x: int, y: int, w: int, h: int,
                    caption: str, warn_ms: float, bad_ms: float, ref_ms: float) -> int:
    bg = QColor(0, 0, 0, 160)
    border = QColor(80, 80, 80, 200)
    chart_rect = QRect(x, y, w, h)
    painter.fillRect(chart_rect, bg)
    painter.setPen(QPen(border, 1))
    painter.drawRect(chart_rect)
    vals = [float(v) for v in (values or []) if v]
    n_bars = min(len(vals), chart_rect.width() - 4)
    try:
        prev_aa = painter.testRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    except Exception:
        prev_aa = None
    if n_bars > 1:
        stride = max(1, (n_bars + 119) // 120)
        n_draw = (n_bars + stride - 1) // stride
        bar_w = (chart_rect.width() - 4) / n_draw
        max_ft = max(max(vals[-n_bars:]) * 1.1, ref_ms)
        di = 0
        for bi in range(0, n_bars, stride):
            ft_val = vals[-n_bars + bi]
            bh = max(1, int((ft_val / max_ft) * (h - 4)))
            bar_x = chart_rect.x() + 2 + int(bar_w * di)
            bar_y = chart_rect.bottom() - 2 - bh
            if ft_val > bad_ms:
                color = QColor(255, 80, 80, 180)
            elif ft_val > warn_ms:
                color = QColor(255, 200, 80, 160)
            else:
                color = QColor(80, 200, 80, 140)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRect(int(bar_x), bar_y, max(1, int(bar_w)), bh))
            di += 1
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        ref_y = chart_rect.bottom() - 2 - int((ref_ms / max_ft) * (h - 4))
        if ref_y > chart_rect.y() + 2:
            painter.drawLine(chart_rect.x() + 2, ref_y, chart_rect.right() - 2, ref_y)
    try:
        if prev_aa is not None:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, prev_aa)
    except Exception:
        pass
    if caption:
        painter.setPen(QColor(140, 140, 140))
        painter.drawText(QRect(chart_rect.x() + 4, chart_rect.y() + 1,
                               chart_rect.width() - 8, 12),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, caption)
    return chart_rect.bottom()


def draw_frame_chart(painter, ft_list, x: int, y: int, w: int) -> int:
    return _draw_bar_chart(painter, ft_list, x, y, w, 30, "frame ms", 16.0, 33.0, 16.0)


def draw_tick_chart(painter, tick_list, x: int, y: int, w: int) -> int:
    return _draw_bar_chart(painter, tick_list, x, y, w, 22, "tick ms", 8.3, 16.6, 8.3)


def draw_spike_box(painter, spike, x: int, y: int, w: int):
    line_h = 15
    padding = 6
    spike_ft, spike_prof = spike
    lines = [f"Spike: {spike_ft:.0f}ms  frame"]
    sorted_spike = sorted(spike_prof.items(), key=lambda kv: -kv[1])[:3]
    for sp_name, sp_val in sorted_spike:
        lines.append(f"  {sp_name}: {sp_val:.1f}ms")
    spike_h = len(lines) * line_h + padding * 2
    rect = QRect(x, y, w, spike_h)
    painter.fillRect(rect, QColor(60, 20, 20, 200))
    painter.setPen(QPen(QColor(255, 80, 80, 200), 1))
    painter.drawRect(rect)
    for si, sline in enumerate(lines):
        sy = y + padding + si * line_h
        painter.setPen(QColor(255, 200, 200))
        painter.drawText(QRect(x + padding, sy, w, line_h),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sline)


def log_spike(frame_time_ms: float, prof):
    per_frame: dict = {}
    cf = getattr(prof, '_current_frame', None) if prof else None
    if cf is not None and cf.flat_data:
        per_frame = dict(cf.flat_data)
    else:
        frames = getattr(prof, 'frames', None)
        if frames:
            per_frame = dict(frames[-1].flat_data)
    if not per_frame:
        global _last_spike_cumulative
        cur = dict(prof.data) if prof else {}
        if _last_spike_cumulative:
            for k, v in cur.items():
                prev = _last_spike_cumulative.get(k, 0.0)
                if isinstance(v, (int, float)) and isinstance(prev, (int, float)):
                    delta = v - prev
                    if delta > 0.01:
                        per_frame[k] = delta
        _last_spike_cumulative = cur
    _SPIKE_LOG.append((frame_time_ms, per_frame))
    if len(_SPIKE_LOG) > 20:
        _SPIKE_LOG.pop(0)
