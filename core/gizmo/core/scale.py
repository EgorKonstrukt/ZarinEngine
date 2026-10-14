# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from typing import Optional, TYPE_CHECKING
from core.maths.math3d import Vec3, Mat4, Quat
from core.gizmo.core.enums import GizmoMode, GizmoSpace, GizmoAlignment, GizmoAxis, AXIS_COLORS, AXIS_HIGHLIGHT
from core.gizmo.core.batch import FLOAT_T, DEF_CAP
if TYPE_CHECKING:
    from core.ecs import Entity
    from editor.cam import SceneCamera

class ScaleMixin:

    def _get_scale_lines_batch(self, pos, transform, cam, vw, vh):
        batch = self._batch
        rx, ry, rz = self._get_axis_directions(transform)
        active = self._active_axis if self._dragging else self._hover_axis
        vp = self._vp_mat_cache
        inv_vp = self._inv_vp_cache
        cam_fwd = self._cam_fwd_cache
        world_len = self._wpp_cache * self.SCREEN_AXIS_LENGTH
        tip_x = pos + rx * world_len
        tip_y = pos + ry * world_len
        tip_z = pos + rz * world_len
        entity_sp = self._project_to_screen(pos, vp, vw, vh)
        tip_sp_x = self._project_to_screen(tip_x, vp, vw, vh)
        tip_sp_y = self._project_to_screen(tip_y, vp, vw, vh)
        tip_sp_z = self._project_to_screen(tip_z, vp, vw, vh)
        half_px = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / (self.BASE_AXIS_LENGTH * 2.0)

        color = AXIS_HIGHLIGHT if active == GizmoAxis.X else AXIS_COLORS[GizmoAxis.X]
        batch.append(pos, tip_x, color)
        if tip_sp_x:
            self._add_cube_handle(tip_x, tip_sp_x, half_px, inv_vp, cam_fwd, vw, vh, color)
        color = AXIS_HIGHLIGHT if active == GizmoAxis.Y else AXIS_COLORS[GizmoAxis.Y]
        batch.append(pos, tip_y, color)
        if tip_sp_y:
            self._add_cube_handle(tip_y, tip_sp_y, half_px, inv_vp, cam_fwd, vw, vh, color)
        color = AXIS_HIGHLIGHT if active == GizmoAxis.Z else AXIS_COLORS[GizmoAxis.Z]
        batch.append(pos, tip_z, color)
        if tip_sp_z:
            self._add_cube_handle(tip_z, tip_sp_z, half_px, inv_vp, cam_fwd, vw, vh, color)
        color = AXIS_HIGHLIGHT if active == GizmoAxis.ALL else AXIS_COLORS[GizmoAxis.ALL]
        if entity_sp:
            self._add_cube_handle(pos, entity_sp, half_px * 1.2, inv_vp, cam_fwd, vw, vh, color)

    def _get_multigizmo_lines_batch(self, pos, transform, cam, vw, vh):
        prev_active = self._active_axis
        prev_hover = self._hover_axis
        prev_op_active = getattr(self, '_active_op', 'translate')
        prev_op_hover = getattr(self, '_hover_op', 'translate')
        try:
            is_active_translate = (prev_op_active == 'translate')
            is_hover_translate = (prev_op_hover == 'translate')
            self._active_axis = prev_active if is_active_translate else GizmoAxis.NONE
            self._hover_axis = prev_hover if is_hover_translate else GizmoAxis.NONE
            self._get_translate_lines_batch(pos, transform, cam, vw, vh)
            is_active_scale = (prev_op_active == 'scale')
            is_hover_scale = (prev_op_hover == 'scale')
            self._active_axis = prev_active if is_active_scale else GizmoAxis.NONE
            self._hover_axis = prev_hover if is_hover_scale else GizmoAxis.NONE
            self._get_scale_lines_batch(pos, transform, cam, vw, vh)
            is_active_rotate = (prev_op_active == 'rotate')
            is_hover_rotate = (prev_op_hover == 'rotate')
            self._active_axis = prev_active if is_active_rotate else GizmoAxis.NONE
            self._hover_axis = prev_hover if is_hover_rotate else GizmoAxis.NONE
            self._get_vertex_rotate_lines_batch(pos, transform, cam, vw, vh)
        finally:
            self._active_axis = prev_active
            self._hover_axis = prev_hover

    def _add_cube_handle(self, center_w: Vec3, center_sp: tuple,
                          half_px: float, inv_vp: Mat4, cam_fwd: Vec3,
                          vw: int, vh: int, color: list):
        batch = self._batch
        cx, cy = center_sp
        corners_w = []
        for sx, sy in [
            (cx - half_px, cy - half_px),
            (cx + half_px, cy - half_px),
            (cx + half_px, cy + half_px),
            (cx - half_px, cy + half_px),
        ]:
            corners_w.append(self._screen_pos_to_world(sx, sy, center_w, inv_vp, cam_fwd, vw, vh))
        batch.append(corners_w[0], corners_w[1], color)
        batch.append(corners_w[1], corners_w[2], color)
        batch.append(corners_w[2], corners_w[3], color)
        batch.append(corners_w[3], corners_w[0], color)
        batch.append(corners_w[0], corners_w[2], color)

    def _pick_multigizmo_axis(self, mx: int, my: int, transform, cam: SceneCamera, vw: int, vh: int):
        if self._orientation_lock and self._orientation_lock_cache is not None:
            rx, ry, rz = self._orientation_lock_cache
        else:
            rx, ry, rz = self._get_axis_directions(transform, cam)
        pos = transform.position + self._pivot_offset
        self._update_cache(cam, vw, vh)
        vp_mat = self._vp_mat_cache
        wpp = self._wpp_cache
        sp_start = self._project_to_screen(pos, vp_mat, vw, vh)
        if sp_start is None:
            return GizmoAxis.NONE, "translate"
        best_axis = GizmoAxis.NONE
        best_op = "translate"
        best_dist = float('inf')
        is_2d = cam.is_2d_mode
        def _scr_dir(axis):
            eps = pos + axis * max(0.001, wpp * 10.0)
            sp = self._project_to_screen(eps, vp_mat, vw, vh)
            if sp_start and sp:
                dx = sp[0] - sp_start[0]
                dy = sp[1] - sp_start[1]
                d = math.sqrt(dx*dx+dy*dy)
                if d > 1e-8:
                    return (dx/d, dy/d)
            return None
        sd_x = _scr_dir(rx)
        sd_y = _scr_dir(ry)
        sd_z = _scr_dir(rz) if not is_2d else None
        ph_px = self.PLANE_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / self.BASE_AXIS_LENGTH
        offset_px = ph_px * 0.2
        planes = [(GizmoAxis.XY, sd_x, sd_y)]
        if not is_2d:
            planes.extend([(GizmoAxis.XZ, sd_x, sd_z), (GizmoAxis.YZ, sd_y, sd_z)])
        for axis_id, sd1, sd2 in planes:
            if sd1 and sd2 and sp_start:
                d1x, d1y = sd1
                d2x, d2y = sd2
                ox = sp_start[0] + d1x*offset_px + d2x*offset_px
                oy = sp_start[1] + d1y*offset_px + d2y*offset_px
                corners = [(ox, oy), (ox+d1x*ph_px, oy+d1y*ph_px), (ox+d1x*ph_px+d2x*ph_px, oy+d1y*ph_px+d2y*ph_px), (ox+d2x*ph_px, oy+d2y*ph_px)]
                if self._point_in_convex_quad(mx, my, corners):
                    self._hover_op = "translate"
                    return axis_id
        if sp_start:
            half_px = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH * 0.5
            if abs(mx - sp_start[0]) <= half_px and abs(my - sp_start[1]) <= half_px:
                if best_dist > half_px:
                    best_dist = half_px
                    best_axis = GizmoAxis.ALL
                    best_op = "translate"
        if sp_start and self._shift_down:
            half_px_s = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / (self.BASE_AXIS_LENGTH*2.0)*1.2
            d = math.sqrt((mx-sp_start[0])**2 + (my-sp_start[1])**2)
            if d < half_px_s*1.5:
                if d < best_dist:
                    best_dist = d
                    best_axis = GizmoAxis.ALL
                    best_op = "scale"
        world_len = wpp * self.SCREEN_AXIS_LENGTH
        for axis_id, axis_dir in [(GizmoAxis.X, rx), (GizmoAxis.Y, ry), (GizmoAxis.Z, rz)]:
            if is_2d and axis_id == GizmoAxis.Z:
                continue
            tip = pos + axis_dir * world_len
            tip_sp = self._project_to_screen(tip, vp_mat, vw, vh)
            if tip_sp:
                half_px = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / (self.BASE_AXIS_LENGTH*2.0)
                if abs(mx - tip_sp[0]) <= half_px and abs(my - tip_sp[1]) <= half_px:
                    d = math.sqrt((mx-tip_sp[0])**2 + (my-tip_sp[1])**2)
                    if d < best_dist:
                        best_dist = d
                        best_axis = axis_id
                        best_op = "scale"
        axes = [GizmoAxis.X, GizmoAxis.Y]
        if not is_2d:
            axes.append(GizmoAxis.Z)
        axis_dirs = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}
        for axis_id in axes:
            direction = axis_dirs[axis_id]
            eps_pos = pos + direction * 0.001
            sp_eps = self._project_to_screen(eps_pos, vp_mat, vw, vh)
            if sp_start and sp_eps:
                dx = sp_eps[0]-sp_start[0]
                dy = sp_eps[1]-sp_start[1]
                screen_len = math.sqrt(dx*dx+dy*dy)
                if screen_len < 1e-8:
                    d = math.sqrt((mx-sp_start[0])**2 + (my-sp_start[1])**2)
                else:
                    sp_end_x = sp_start[0] + dx/screen_len*self.SCREEN_AXIS_LENGTH
                    sp_end_y = sp_start[1] + dy/screen_len*self.SCREEN_AXIS_LENGTH
                    d = self._point_to_segment_dist(mx, my, sp_start[0], sp_start[1], sp_end_x, sp_end_y)
                if d < best_dist and d < self.PICK_THRESHOLD:
                    best_dist = d
                    best_axis = axis_id
                    best_op = "translate"
        if not is_2d:
            rx_r, ry_r, rz_r = rx, ry, rz
            circle_defs = [(GizmoAxis.X, rx_r), (GizmoAxis.Y, ry_r), (GizmoAxis.Z, rz_r)]
            segs = 32
            d_mat = vp_mat._d
            px, py, pz = pos.x, pos.y, pos.z
            world_radius = wpp * self.SCREEN_AXIS_LENGTH * 0.72
            for axis_id, normal in circle_defs:
                p1, p2 = self._get_perpendiculars(normal)
                angles = np.linspace(0.0, math.pi*0.5, segs+1, endpoint=True)
                cos_a = np.cos(angles)
                sin_a = np.sin(angles)
                p1x, p1y, p1z = p1.x*world_radius, p1.y*world_radius, p1.z*world_radius
                p2x, p2y, p2z = p2.x*world_radius, p2.y*world_radius, p2.z*world_radius
                wxs = px + p1x*cos_a + p2x*sin_a
                wys = py + p1y*cos_a + p2y*sin_a
                wzs = pz + p1z*cos_a + p2z*sin_a
                cxs = wxs*d_mat[0,0]+wys*d_mat[1,0]+wzs*d_mat[2,0]+d_mat[3,0]
                cys = wxs*d_mat[0,1]+wys*d_mat[1,1]+wzs*d_mat[2,1]+d_mat[3,1]
                cws = wxs*d_mat[0,3]+wys*d_mat[1,3]+wzs*d_mat[2,3]+d_mat[3,3]
                valid = np.abs(cws) > 1e-6
                inv_w = np.where(valid, 1.0/np.where(valid, cws, 1.0), 0.0)
                sxs = (cxs*inv_w+1.0)*0.5*vw
                sys_ = (1.0 - cys*inv_w)*0.5*vh
                min_d = float('inf')
                for i in range(segs):
                    if not valid[i] or not valid[i+1]:
                        continue
                    ax, ay = sxs[i], sys_[i]
                    bx, by = sxs[i+1], sys_[i+1]
                    ddx, ddy = bx-ax, by-ay
                    len_sq = ddx*ddx+ddy*ddy
                    if len_sq < 1e-6:
                        dd = math.sqrt((mx-ax)**2+(my-ay)**2)
                    else:
                        t = max(0.0, min(1.0, ((mx-ax)*ddx+(my-ay)*ddy)/len_sq))
                        dd = math.sqrt((mx-ax-t*ddx)**2+(my-ay-t*ddy)**2)
                    if dd < min_d:
                        min_d = dd
                if min_d < best_dist and min_d < self.PICK_THRESHOLD:
                    best_dist = min_d
                    best_axis = axis_id
                    best_op = "rotate"
                end_pt = pos + p2 * world_radius * 1.08
                end_sp = self._project_to_screen(end_pt, vp_mat, vw, vh)
                if end_sp is not None:
                    d = math.sqrt((mx-end_sp[0])**2 + (my-end_sp[1])**2)
                    if d < 12 and d < best_dist:
                        best_dist = d
                        best_axis = axis_id
                        best_op = "scale"
            sp_center = sp_start
            if sp_center is not None:
                outer_px = self.SCREEN_AXIS_LENGTH * 0.85 * 1.18
                dist = math.sqrt((mx-sp_center[0])**2 + (my-sp_center[1])**2)
                if abs(dist-outer_px) < self.PICK_THRESHOLD*0.7 and dist < best_dist:
                    best_dist = abs(dist-outer_px)
                    best_axis = GizmoAxis.ALL
                    best_op = "rotate"
        if best_axis != GizmoAxis.NONE:
            self._hover_op = best_op
            return best_axis
        self._hover_op = "translate"
        return GizmoAxis.NONE

    def _apply_scale(self, transform, cam: SceneCamera, mx: int, my: int, vw: int, vh: int):
        pos = self._drag_entity_start_pos + self._pivot_offset
        ray_origin, ray_dir = self._screen_to_ray(mx, my, cam, vw, vh)
        snap_active = self._snap_enabled and not self._ctrl_down
        if self._active_axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
            axis_dir = self._drag_axis_dir
            plane_normal = self._best_translate_plane_normal(axis_dir, cam.forward)
            hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
            if hit is None:
                t = self._closest_point_ray_to_line(ray_origin, ray_dir, pos, axis_dir)
                if t is None:
                    return
                hit = ray_origin + ray_dir * t
            delta = hit - self._drag_hit_start
            axis_delta = delta.dot(axis_dir)
            if snap_active and self._snap_scale > 0:
                axis_delta = self._apply_snap(axis_delta, self._snap_scale, f"s_{self._active_axis.value}")
            sx = self._drag_start_scale.x
            sy = self._drag_start_scale.y
            sz = self._drag_start_scale.z
            if self._active_axis == GizmoAxis.X:
                sx = max(0.001, sx + axis_delta)
            elif self._active_axis == GizmoAxis.Y:
                sy = max(0.001, sy + axis_delta)
            else:
                sz = max(0.001, sz + axis_delta)
            delta_val = sx - self._drag_start_scale.x if self._active_axis == GizmoAxis.X else \
                        sy - self._drag_start_scale.y if self._active_axis == GizmoAxis.Y else \
                        sz - self._drag_start_scale.z
            self._delta_text = f"\u0394 {delta_val:+.3f}"
            transform.local_scale = Vec3(sx, sy, sz)
        elif self._active_axis == GizmoAxis.ALL:
            plane_normal = cam.forward
            hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
            if not hit:
                return
            delta = hit - self._drag_hit_start
            axis_delta = delta.length() * (1 if delta.dot(hit - pos) >= 0 else -1)
            if snap_active and self._snap_scale > 0:
                axis_delta = self._apply_snap(axis_delta, self._snap_scale, "sa")
            scale_factor = 1.0 + axis_delta
            scale_factor = max(0.001, scale_factor)
            new_s = Vec3(
                max(0.001, self._drag_start_scale.x * scale_factor),
                max(0.001, self._drag_start_scale.y * scale_factor),
                max(0.001, self._drag_start_scale.z * scale_factor)
            )
            self._delta_text = f"\u0394 {scale_factor-1.0:+.3f}"
            transform.local_scale = new_s
