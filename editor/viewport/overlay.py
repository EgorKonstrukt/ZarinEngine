from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen

from core.math3d import Vec3


def draw_stats_overlay(vp, painter):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont("Segoe UI", 10, QFont.Weight.Bold)
    font.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
    painter.setFont(font)
    vp._fps_history.append(vp._fps)
    if len(vp._fps_history) > 60:
        vp._fps_history.pop(0)
    avg_fps = sum(vp._fps_history) / max(len(vp._fps_history), 1)
    prof_data = vp._engine.profiler_data if hasattr(vp._engine, 'profiler_data') else {}
    stats_lines = [
        f"FPS: {avg_fps:.1f}",
        f"Entities: {len(vp._engine.scene.get_all_entities()) if vp._engine.scene else 0}",
        f"Draw Calls: {vp._renderer._draw_calls if hasattr(vp._renderer, '_draw_calls') else 'N/A'}",
        f"Triangles: {vp._renderer._triangles_drawn if hasattr(vp._renderer, '_triangles_drawn') else 'N/A'}",
    ]
    for key in sorted(prof_data.keys()):
        val = prof_data[key]
        stats_lines.append(f"{key}: {val:.2f}ms")
    text_color = QColor(0, 255, 0)
    bg_color = QColor(0, 0, 0, 150)
    padding = 8
    line_height = 16
    total_h = len(stats_lines) * line_height + padding * 2
    rect = QRect(vp.width() - 220, 70, 200, total_h)
    painter.fillRect(rect, bg_color)
    painter.setPen(text_color)
    for i, line in enumerate(stats_lines):
        painter.drawText(QRect(vp.width() - 215, 70 + i * line_height, 190, line_height),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)


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
