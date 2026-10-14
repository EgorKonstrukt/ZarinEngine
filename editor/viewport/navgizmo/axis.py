# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import math

import numpy as np

from core.maths.math3d import Vec3
from editor.viewport.navgizmo.gizmo import config, set_rect, set_draw_list, _DrawList, draw_gizmo


def draw_navigation_gizmo_overlay(vp, qp):
    indicator = getattr(vp, "_navigation_gizmo", None)
    if indicator is None or not getattr(vp, "_navigation_gizmo_enabled", True):
        return
    if not vp._cam:
        return
    w = vp.width()
    h = vp.height()
    if w <= 0 or h <= 0:
        return
    cam = vp._cam
    size = indicator.rect_size
    toolbar_h = getattr(vp, "_toolbar", None)
    top_offset = (toolbar_h.height() if toolbar_h is not None else 30) + 8
    x = w - size - indicator.corner_offset_x
    y = top_offset + indicator.corner_offset_y
    fw, fh = vp._get_physical_dims()
    aspect = fw / max(1, fh)
    view = cam.get_view_matrix()
    proj = cam.get_projection_matrix(aspect)
    view_col = view.to_f32().tolist()
    proj_col = proj.to_f32().tolist()
    cfg = config
    cfg.lineThicknessScale = 0.017
    cfg.axisLengthScale = 0.33
    cfg.positiveRadiusScale = 0.075
    cfg.negativeRadiusScale = 0.05
    cfg.hoverCircleRadiusScale = 0.88
    cfg.dragThreshold = 3.0
    cfg.dragSensitivity = indicator.drag_sensitivity
    cfg.drag = indicator.drag_enabled
    cfg.click = indicator.click_enabled
    if getattr(cam, "_is_orthographic", False):
        fov_rad = math.radians(getattr(cam, "fov", 60.0))
        persp_proj5 = 1.0 / math.tan(fov_rad * 0.5)
        ortho_proj5 = proj_col[5]
        if ortho_proj5 > 1e-6:
            factor = persp_proj5 / ortho_proj5
            factor = max(0.01, min(factor, 1000.0))
            cfg.axisLengthScale *= factor
    set_rect(x, y, size)
    set_draw_list(_DrawList(qp, 0.0, 0.0))
    cs = indicator.coordinate_system.value if hasattr(indicator.coordinate_system, "value") else int(indicator.coordinate_system)
    mx, my = getattr(vp, "_ng_mouse_pos", (0.0, 0.0))
    down = getattr(vp, "_ng_mouse_down", False)
    clicked = getattr(vp, "_ng_clicked", False)
    released = getattr(vp, "_ng_released", False)
    delta = getattr(vp, "_ng_mouse_delta", (0.0, 0.0))
    result, selection, center, hov = draw_gizmo(
        view_col, proj_col,
        pivot_distance=indicator.pivot_distance,
        cs=cs,
        mouse_pos=(mx, my),
        mouse_down=down,
        mouse_clicked=clicked,
        mouse_released=released,
        mouse_delta=delta,
    )
    vp._ng_clicked = False
    vp._ng_released = False
    vp._ng_mouse_delta = (0.0, 0.0)
    vp._navigation_gizmo_hover = selection
    vp._navigation_gizmo_center = center
    vp._navigation_gizmo_interacting = hov
    if result is not None and result[0] == "click":
        snap_camera_to_axis(vp, result[1] % 3)


_WORLD_AXES = (Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1))
_AXIS_LABELS_3D = ("X", "Y", "Z")


def _get_gizmo_world_pos(vp):
    fw, fh = vp._get_physical_dims()
    if fw <= 0 or fh <= 0:
        return None, 0.0
    cam = vp._cam
    gizmo_dist = max((cam._position - cam._orbit_target).length(), 2.0)
    aspect = fw / max(1, fh)
    effective_fov = min(cam.fov, 90.0) if not cam.is_orthographic else 60.0
    tan_hfov = math.tan(math.radians(effective_fov) * 0.5)
    vx = 0.85 * aspect * gizmo_dist * tan_hfov
    vy = 0.8 * gizmo_dist * tan_hfov
    gizmo_pos = cam.position + cam.forward * gizmo_dist + cam._right() * vx + cam._up() * vy
    world_len = max(40.0 * gizmo_dist * tan_hfov / (fh * 0.5), 0.15)
    return gizmo_pos, world_len


def draw_axis_gizmo_api(vp, vp_mat, fw=None, fh=None):
    result = _get_gizmo_world_pos(vp)
    if result is None:
        return
    gizmo_pos, world_len = result
    if world_len < 0.01:
        return
    if fw is None or fh is None:
        fw, fh = vp._get_physical_dims()
    neg_len = world_len * 0.5
    base_colors = ((1.0, 0.2, 0.2, 1.0), (0.2, 1.0, 0.2, 1.0), (0.2, 0.4, 1.0, 1.0))
    hover_col = (1.0, 1.0, 0.0, 1.0)
    tips = []
    neg_tips = []
    num_lines = 6
    starts = np.empty((num_lines, 3), dtype=np.float32)
    ends = np.empty((num_lines, 3), dtype=np.float32)
    cols = np.empty((num_lines, 4), dtype=np.float32)
    for i, (direction, color) in enumerate(zip(_WORLD_AXES, base_colors)):
        if i == getattr(vp, '_axis_gizmo_hover', None):
            col = hover_col
        else:
            col = color
        tip = gizmo_pos + direction * world_len
        nt = gizmo_pos - direction * neg_len
        tips.append(tip)
        neg_tips.append(nt)
        idx = i * 2
        starts[idx] = (gizmo_pos.x, gizmo_pos.y, gizmo_pos.z)
        ends[idx] = (tip.x, tip.y, tip.z)
        cols[idx] = col
        starts[idx + 1] = (gizmo_pos.x, gizmo_pos.y, gizmo_pos.z)
        ends[idx + 1] = (nt.x, nt.y, nt.z)
        cols[idx + 1] = (col[0] * 0.3, col[1] * 0.3, col[2] * 0.3, col[3])
    vp._renderer.render_gizmo_arrays(starts, ends, cols, vp_mat, fw, fh, thickness_multiplier=1.5)
    vp._axis_gizmo_tips_world = tips
    vp._axis_gizmo_neg_tips_world = neg_tips
    vp._axis_gizmo_center_world = gizmo_pos
    vp._axis_gizmo_world_len = world_len


def snap_camera_to_axis(vp, axis_idx):
    if axis_idx < 0 or axis_idx > 2:
        return
    cam = vp._cam
    target = Vec3.zero()
    if vp._selected_entities:
        t = vp._selected_entities[0].transform
        if t:
            target = t.position
    dist = max((cam._position - target).length(), 5.0)
    pos = target + _WORLD_AXES[axis_idx] * dist
    cam._position = pos
    cam.focus_on(target, dist)
