from __future__ import annotations

import gc as _gc
import math
import os
import time

import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen

from core.math3d import Vec3

try:
    import psutil as _psutil
    _psutil_available = True
except Exception:
    _psutil_available = False


def _get_ram_mb() -> float:
    if _psutil_available:
        try:
            return _psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            pass
    try:
        import resource as _resource
        return _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        pass
    try:
        import ctypes
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        class _PMC(ctypes.Structure):
            _fields_ = [
                ('cb', ctypes.c_uint32),
                ('PageFaultCount', ctypes.c_uint32),
                ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t),
            ]
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        h = ctypes.c_void_p(-1)
        if psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), ctypes.sizeof(pmc)):
            return pmc.WorkingSetSize / (1024 * 1024)
    except Exception:
        pass
    return 0.0


def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


_vram_cache = {'used_mb': 0.0, 'total_mb': 0.0, 'last_query': 0.0}


def _get_vram_mb() -> tuple[float, float]:
    global _vram_cache
    now = time.time()
    if now - _vram_cache['last_query'] < 2.0:
        return _vram_cache['used_mb'], _vram_cache['total_mb']

    used_mb = total_mb = 0.0
    try:
        import ctypes
        nvml = ctypes.WinDLL('nvml.dll')
        nvml.nvmlInit()
        handle = ctypes.c_void_p()
        nvml.nvmlDeviceGetHandleByIndex(0, ctypes.byref(handle))

        class _NVMLMem(ctypes.Structure):
            _fields_ = [
                ('total', ctypes.c_ulonglong),
                ('free', ctypes.c_ulonglong),
                ('used', ctypes.c_ulonglong),
            ]
        mem = _NVMLMem()
        nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem))
        total_mb = mem.total / (1024 * 1024)
        used_mb = mem.used / (1024 * 1024)
    except Exception:
        pass

    _vram_cache = {'used_mb': used_mb, 'total_mb': total_mb, 'last_query': now}
    return used_mb, total_mb


def _draw_val(painter, label, val, fm, cx, cy, line_height):
    color_map = {
        "FPS": QColor(100, 220, 100),
        "1%": QColor(255, 200, 100),
        "0.1%": QColor(255, 150, 100),
        "CPU": QColor(100, 200, 255),
        "GPU": QColor(100, 200, 255),
        "RAM": QColor(180, 255, 180),
        "VRAM": QColor(255, 180, 255),
        "GC": QColor(180, 180, 255),
        "TPS": QColor(180, 255, 180),
        "DSP": QColor(255, 255, 180),
        "Sounds": QColor(180, 255, 255),
        "Entities": QColor(255, 180, 180),
        "Draw Calls": QColor(200, 200, 200),
        "Tris": QColor(200, 220, 255),
        "Verts": QColor(200, 220, 255),
        "Batches": QColor(200, 200, 200),
        "Instanced": QColor(200, 200, 200),
        "Gizmo Draws": QColor(200, 220, 255),
        "GLines": QColor(200, 220, 255),
    }
    c = color_map.get(label, QColor(255, 255, 255))
    painter.setPen(c)
    painter.drawText(QRect(cx, cy, fm.horizontalAdvance(val), line_height),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, val)


def draw_stats_overlay(vp, painter):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont("Consolas", 9)
    font.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
    painter.setFont(font)

    fps = vp._fps if vp._fps > 0 else 0.0
    paint_dt = getattr(vp, '_paint_dt', 0.016)

    if not hasattr(vp, '_frame_times_ms'):
        vp._frame_times_ms = []

    if paint_dt > 0:
        vp._frame_times_ms.append(paint_dt * 1000.0)
        if len(vp._frame_times_ms) > 300:
            vp._frame_times_ms.pop(0)

    sorted_ft = sorted(vp._frame_times_ms)
    n = len(sorted_ft)

    p1_count = max(1, int(n * 0.01))
    p01_count = max(1, int(n * 0.001))
    p1_low = sum(sorted_ft[-p1_count:]) / p1_count if sorted_ft else 0.0
    p01_low = sum(sorted_ft[-p01_count:]) / p01_count if sorted_ft else 0.0

    cpu_ms = paint_dt * 1000.0

    tps = vp._engine.tps if hasattr(vp._engine, 'tps') else 0.0

    ram_mb = _get_ram_mb()
    vram_used, vram_total = _get_vram_mb()

    gc_gen0, gc_gen1, gc_gen2 = _gc.get_count()

    dsp_load = 0.0
    active_sounds = 0
    try:
        from core.audio_system import AudioSourceManager
        mgr = AudioSourceManager.instance()
        if mgr:
            dsp_load = mgr.get_dsp_load()
            active_sounds = mgr.get_active_sound_count()
    except Exception:
        pass

    entities = len(vp._engine.scene.get_all_entities()) if vp._engine.scene else 0
    triangles = vp._renderer._triangles_drawn if hasattr(vp._renderer, '_triangles_drawn') else 0
    vertices = vp._renderer._vertices_drawn if hasattr(vp._renderer, '_vertices_drawn') else 0
    draw_calls = vp._renderer._draw_calls if hasattr(vp._renderer, '_draw_calls') else 0

    gpu_ms = vp._last_render_ms if hasattr(vp, '_last_render_ms') else 0.0

    batches = 0
    instanced = 0
    if hasattr(vp._renderer, '_batcher') and vp._renderer._batcher:
        batches = vp._renderer._batcher.batches
        instanced = vp._renderer._batcher.instanced

    gizmo_lines = vp._renderer._gizmo._stat_lines if vp._renderer._gizmo else 0
    gizmo_draws = vp._renderer._gizmo._stat_draws if vp._renderer._gizmo else 0

    stats_lines = [
        f"FPS: {fps:.1f}  |  1%: {1000.0/max(p1_low,0.1):.1f}  |  0.1%: {1000.0/max(p01_low,0.1):.1f}  |  CPU: {cpu_ms:.1f}ms  |  GPU: {gpu_ms:.1f}ms",
        f"RAM: {ram_mb:.0f} MB  |  VRAM: {vram_used:.0f}/{vram_total:.0f} MB  |  GC: {gc_gen0}/{gc_gen1}/{gc_gen2}  |  TPS: {tps:.0f}",
        f"DSP: {dsp_load:.0f}%  |  Sounds: {active_sounds}",
        f"Entities: {entities}  |  Draw Calls: {draw_calls}  |  Tris: {_fmt_count(triangles)}  |  Verts: {_fmt_count(vertices)}",
        f"Batches: {batches}  |  Instanced: {instanced}  |  Gizmo Draws: {gizmo_draws}  |  GLines: {_fmt_count(gizmo_lines)}",
    ]

    text_color = QColor(255, 255, 255)
    label_color = QColor(160, 160, 160)
    bg_color = QColor(0, 0, 0, 160)
    border_color = QColor(80, 80, 80, 200)
    padding = 6
    line_height = 15
    total_h = len(stats_lines) * line_height + padding * 2

    fm = QFontMetrics(font)
    max_w = max(fm.horizontalAdvance(line) for line in stats_lines) + padding * 2
    max_w = max(max_w, 460)

    x = 8
    y = 35
    rect = QRect(x, y, int(max_w), total_h)
    painter.fillRect(rect, bg_color)
    painter.setPen(QPen(border_color, 1))
    painter.drawRect(rect)

    painter.setFont(font)
    for i, line in enumerate(stats_lines):
        cx = x + padding
        cy = y + padding + i * line_height
        segments = line.split("  |  ")
        for idx, seg in enumerate(segments):
            seg = seg.strip()
            if not seg:
                continue
            if ":" in seg:
                lab, val = seg.split(":", 1)
                lab = lab.strip() + ": "
                val = val.strip()
                painter.setPen(label_color)
                painter.drawText(QRect(cx, cy, fm.horizontalAdvance(lab), line_height),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lab)
                cx += fm.horizontalAdvance(lab)
                _draw_val(painter, lab.rstrip(": "), val, fm, cx, cy, line_height)
                cx += fm.horizontalAdvance(val)
            else:
                painter.setPen(text_color)
                painter.drawText(QRect(cx, cy, fm.horizontalAdvance(seg), line_height),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, seg)
                cx += fm.horizontalAdvance(seg)
            if idx < len(segments) - 1:
                painter.setPen(QColor(100, 100, 100))
                sep = " | "
                painter.drawText(QRect(cx, cy, fm.horizontalAdvance(sep), line_height),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sep)
                cx += fm.horizontalAdvance(sep)


def draw_delta_label(vp, painter):
    dt = vp._gizmo.delta_text
    if not dt or not vp._gizmo.show_delta_label:
        return
    f = QFont("Segoe UI", 12, QFont.Weight.Bold)
    f.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
    painter.setFont(f)
    mx, my = vp._last_mouse_pos
    fm = QFontMetrics(painter.font())
    tw = fm.horizontalAdvance(dt) + 16
    th = fm.height() + 6
    rect = QRect(mx + 12, my - th - 8, tw, th)
    painter.setPen(QPen(QColor(255, 170, 0, 220), 1))
    painter.setBrush(QBrush(QColor(30, 30, 30, 200)))
    painter.drawRoundedRect(rect, 4, 4)
    painter.setPen(QColor(255, 170, 0, 255))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, dt)


def get_grid_label_positions(vp):
    w, h = vp.width(), vp.height()
    if w <= 0 or h <= 0:
        return [], []
    cam_pos = vp._cam.position
    step = vp._renderer._compute_grid_size(cam_pos) if vp._renderer else 10.0
    inv_vp = (vp._cam.get_view_matrix() * vp._cam.get_projection_matrix(w / max(1, h))).inverted()
    corners_ndc = [
        np.array([-1.0, -1.0, -1.0, 1.0]),
        np.array([1.0, -1.0, -1.0, 1.0]),
        np.array([1.0, 1.0, -1.0, 1.0]),
        np.array([-1.0, 1.0, -1.0, 1.0]),
    ]
    ground_points = []
    for ndc in corners_ndc:
        near_w = ndc @ inv_vp._d
        near_w /= near_w[3]
        far_ndc = np.array([ndc[0], ndc[1], 1.0, 1.0])
        far_w = far_ndc @ inv_vp._d
        far_w /= far_w[3]
        dx = far_w[0] - near_w[0]
        dy = far_w[1] - near_w[1]
        dz = far_w[2] - near_w[2]
        if abs(dy) < 1e-8:
            continue
        t = -near_w[1] / dy
        if t > 0:
            gx = near_w[0] + dx * t
            gz = near_w[2] + dz * t
            ground_points.append((gx, gz))
    if len(ground_points) < 3:
        return [], []
    all_x = [p[0] for p in ground_points]
    all_z = [p[1] for p in ground_points]
    min_x, max_x = min(all_x), max(all_x)
    min_z, max_z = min(all_z), max(all_z)
    margin = step * 2.0
    start_x = int((min_x - margin) / step) * step
    end_x = int((max_x + margin) / step) * step
    start_z = int((min_z - margin) / step) * step
    end_z = int((max_z + margin) / step) * step
    x_labels = []
    z_labels = []
    MAX_ITERATIONS = 1000
    x_step = int(step)
    x_count = max(1, int((end_x - start_x) / x_step))
    if x_count > MAX_ITERATIONS:
        x_step = max(1, int(x_step * x_count / MAX_ITERATIONS))
    z_step = int(step)
    z_count = max(1, int((end_z - start_z) / z_step))
    if z_count > MAX_ITERATIONS:
        z_step = max(1, int(z_step * z_count / MAX_ITERATIONS))
    for val in range(int(start_x), int(end_x) + x_step, x_step):
        clip = inv_vp._d @ np.array([float(val), 0.0, cam_pos.z, 1.0])
        if abs(clip[3]) < 1e-6:
            continue
        ndc = clip[:3] / clip[3]
        sx = (ndc[0] + 1.0) * 0.5 * w
        sy = (1.0 - ndc[1]) * 0.5 * h
        if ndc[2] < -1 or ndc[2] > 1:
            continue
        if h * 0.75 <= sy <= h and 0 <= sx <= w:
            x_labels.append((sx, sy, val))
    for val in range(int(start_z), int(end_z) + z_step, z_step):
        clip = inv_vp._d @ np.array([cam_pos.x, 0.0, float(val), 1.0])
        if abs(clip[3]) < 1e-6:
            continue
        ndc = clip[:3] / clip[3]
        sx = (ndc[0] + 1.0) * 0.5 * w
        sy = (1.0 - ndc[1]) * 0.5 * h
        if ndc[2] < -1 or ndc[2] > 1:
            continue
        if sy <= h * 0.75 and 0 <= sx <= w:
            z_labels.append((sx, sy, val))
    return x_labels[:20], z_labels[:20]


def draw_grid_labels(vp, painter=None):
    x_labels, z_labels = get_grid_label_positions(vp)
    if not x_labels and not z_labels:
        return
    own_painter = False
    if painter is None:
        painter = QPainter(vp)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        own_painter = True
    font = QFont("Segoe UI", 9)
    font.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
    painter.setFont(font)
    margin = 4
    bg_color = QColor(30, 30, 30, 200)
    text_color = QColor(180, 180, 180)
    pen = QPen(QColor(100, 100, 100))
    for sx, sy, val in x_labels:
        text = str(val)
        rect = QRect(int(sx - 20), int(sy) - 7, 40, 16)
        painter.fillRect(rect, bg_color)
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    for sx, sy, val in z_labels:
        text = str(val)
        rect = QRect(int(sx - 20), int(sy) - 7, 40, 16)
        painter.fillRect(rect, bg_color)
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    if own_painter:
        painter.end()
