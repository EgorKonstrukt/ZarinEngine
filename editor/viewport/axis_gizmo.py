from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter

from core.math3d import Vec3


def get_axis_gizmo_lines(vp):
    if not vp._axis_gizmo_enabled or not vp._cam or not getattr(vp, '_renderer', None):
        return []
    fw, fh = vp._get_physical_dims()
    if fw <= 0 or fh <= 0:
        return []
    cam = vp._cam
    gizmo_dist = max((cam._position - cam._orbit_target).length(), 2.0) if hasattr(cam, '_orbit_target') else 10.0
    aspect = fw / max(1, fh)
    effective_fov = min(cam.fov, 90.0) if not cam.is_orthographic else 60.0
    tan_hfov = math.tan(math.radians(effective_fov) * 0.5)
    vx = 0.85 * aspect * gizmo_dist * tan_hfov
    vy = 0.8 * gizmo_dist * tan_hfov
    gizmo_pos = cam.position + cam.forward * gizmo_dist + cam._right() * vx + cam._up() * vy
    world_len = 40.0 * gizmo_dist * tan_hfov / (fh * 0.5)
    world_len = max(world_len, 0.15)
    arrow_size = world_len * 0.22
    world_axes = [Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)]
    tips = [gizmo_pos + d * world_len for d in world_axes]
    vp._gizmo_data = (gizmo_pos, world_len, tips)
    lines = []
    axis_defs = [
        (world_axes[0], [1.0, 0.2, 0.2, 1.0]),
        (world_axes[1], [0.2, 1.0, 0.2, 1.0]),
        (world_axes[2], [0.2, 0.4, 1.0, 1.0]),
    ]
    highlight = [1.0, 1.0, 0.0, 1.0]
    for i, (direction, color) in enumerate(axis_defs):
        line_color = highlight if i == vp._axis_gizmo_hover else color
        tip = gizmo_pos + direction * world_len
        lines.append((gizmo_pos, tip, line_color))
        base = tip - direction * arrow_size
        ref_up = Vec3.up() if abs(direction.y) < 0.9 else Vec3.right()
        perp1 = direction.cross(ref_up).normalized()
        perp2 = direction.cross(perp1).normalized()
        hs = arrow_size * 0.35
        lines.append((tip, base + perp1 * hs, line_color))
        lines.append((tip, base - perp1 * hs, line_color))
        lines.append((tip, base + perp2 * hs, line_color))
        lines.append((tip, base - perp2 * hs, line_color))
    return lines


def hit_test_axis_gizmo(vp, mx, my):
    gizmo_data = getattr(vp, '_gizmo_data', None)
    if not vp._axis_gizmo_enabled or not vp._cam or not gizmo_data:
        return -1
    gizmo_pos, world_len, _ = gizmo_data
    w, h = vp.width(), vp.height()
    if w <= 0 or h <= 0:
        return -1
    vp_mat = vp._cam.get_view_matrix() * vp._cam.get_projection_matrix(w / max(1, h))

    def _project(v):
        clip = np.array([v.x, v.y, v.z, 1.0]) @ vp_mat._d
        if abs(clip[3]) < 1e-6:
            return None
        ndc = clip[:3] / clip[3]
        sx = (ndc[0] + 1.0) * 0.5 * w
        sy = (1.0 - ndc[1]) * 0.5 * h
        return (sx, sy)

    center_screen = _project(gizmo_pos)
    if not center_screen:
        return -1
    dx = mx - center_screen[0]
    dy = my - center_screen[1]
    if math.sqrt(dx * dx + dy * dy) > 80:
        return -1
    world_axes = [Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)]
    best_idx = -1
    best_dist = 30.0
    for i, direction in enumerate(world_axes):
        tip = gizmo_pos + direction * world_len
        sp = _project(tip)
        if sp:
            d = math.sqrt((mx - sp[0]) ** 2 + (my - sp[1]) ** 2)
            if d < best_dist:
                best_dist = d
                best_idx = i
    return best_idx


def snap_camera_to_axis(vp, axis_idx):
    if axis_idx < 0 or axis_idx > 2:
        return
    cam = vp._cam
    target = Vec3.zero()
    dist = max((cam._position - cam._orbit_target).length(), 5.0) if hasattr(cam, '_orbit_target') else 10.0
    if vp._selected_entities:
        t = vp._selected_entities[0].get_component_by_name("Transform")
        if t:
            target = t.position
    world_axes = [Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)]
    pos = target + world_axes[axis_idx] * dist
    cam._position = pos
    cam.focus_on(target, dist)


def draw_axis_gizmo_labels(vp, painter):
    gizmo_data = getattr(vp, '_gizmo_data', None)
    if not gizmo_data or len(gizmo_data) < 3:
        return
    gizmo_pos, world_len, tips = gizmo_data
    w, h = vp.width(), vp.height()
    if w <= 0 or h <= 0:
        return
    vp_mat = vp._cam.get_view_matrix() * vp._cam.get_projection_matrix(w / max(1, h))

    def _project(v):
        clip = np.array([v.x, v.y, v.z, 1.0]) @ vp_mat._d
        if abs(clip[3]) < 1e-6:
            return None
        ndc = clip[:3] / clip[3]
        if ndc[2] < -1.0 or ndc[2] > 1.0:
            return None
        sx = (ndc[0] + 1.0) * 0.5 * w
        sy = (1.0 - ndc[1]) * 0.5 * h
        if sx < -50 or sx > w + 50 or sy < -50 or sy > h + 50:
            return None
        return (sx, sy)

    labels = ["X", "Y", "Z"]
    colors = [QColor(255, 70, 70), QColor(70, 255, 70), QColor(70, 130, 255)]
    f2 = QFont("Segoe UI", 11, QFont.Weight.Bold)
    f2.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
    painter.setFont(f2)
    for i, (tip_world, label, color) in enumerate(zip(tips, labels, colors)):
        sp = _project(tip_world)
        if sp and sp[0] >= 0 and sp[0] < w and sp[1] >= 0 and sp[1] < h:
            c = QColor(color.red(), color.green(), color.blue(), 200)
            painter.setPen(c)
            painter.drawText(QRect(int(sp[0] - 12), int(sp[1] - 12), 24, 24), Qt.AlignmentFlag.AlignCenter, label)
