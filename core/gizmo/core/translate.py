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

class TranslateMixin:

    def _screen_pos_to_world(self, sx: float, sy: float, ref_pos: Vec3,
                              inv_vp: Mat4, cam_fwd: Vec3, vw: int, vh: int) -> Vec3:
        ndc_x = (2.0 * sx / vw) - 1.0
        ndc_y = 1.0 - (2.0 * sy / vh)
        near_ndc = np.array([ndc_x, ndc_y, -1.0, 1.0])
        far_ndc = np.array([ndc_x, ndc_y, 1.0, 1.0])
        near_w = near_ndc @ inv_vp._d
        far_w = far_ndc @ inv_vp._d
        near_w /= near_w[3]
        far_w /= far_w[3]
        origin = Vec3(float(near_w[0]), float(near_w[1]), float(near_w[2]))
        direction = Vec3(
            float(far_w[0] - near_w[0]),
            float(far_w[1] - near_w[1]),
            float(far_w[2] - near_w[2])
        ).normalized()
        denom = direction.dot(cam_fwd)
        if abs(denom) < 1e-8:
            return ref_pos
        t = (ref_pos - origin).dot(cam_fwd) / denom
        if t < 0:
            return ref_pos
        return origin + direction * t

    def _screen_to_ray(self, sx: int, sy: int, cam: SceneCamera, vw: int, vh: int):
        aspect = vw / max(1, vh)
        ndc_x = (2.0 * sx / vw) - 1.0
        ndc_y = 1.0 - (2.0 * sy / vh)
        view = cam.get_view_matrix()
        proj = cam.get_projection_matrix(aspect)
        inv_vp = (view * proj).inverted()
        near_ndc = np.array([ndc_x, ndc_y, -1.0, 1.0])
        far_ndc = np.array([ndc_x, ndc_y, 1.0, 1.0])
        near_w = near_ndc @ inv_vp._d
        far_w = far_ndc @ inv_vp._d
        near_w /= near_w[3]
        far_w /= far_w[3]
        origin = Vec3(float(near_w[0]), float(near_w[1]), float(near_w[2]))
        direction = Vec3(
            float(far_w[0] - near_w[0]),
            float(far_w[1] - near_w[1]),
            float(far_w[2] - near_w[2])
        ).normalized()
        return origin, direction

    def _ray_plane_intersect(self, ray_o: Vec3, ray_d: Vec3,
                              plane_point: Vec3, plane_normal: Vec3) -> Optional[Vec3]:
        denom = plane_normal.dot(ray_d)
        if abs(denom) < 1e-6:
            return None
        t = (plane_point - ray_o).dot(plane_normal) / denom
        if t < 0:
            return None
        return ray_o + ray_d * t

    def _point_to_segment_dist(self, px, py, ax, ay, bx, by) -> float:
        dx = bx - ax
        dy = by - ay
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-6:
            return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

    def _project_to_screen(self, world_pos: Vec3, vp_mat: Mat4, vw: int, vh: int):
        d = vp_mat._d
        wx, wy, wz = world_pos.x, world_pos.y, world_pos.z
        cx = wx*d[0,0]+wy*d[1,0]+wz*d[2,0]+d[3,0]
        cy = wx*d[0,1]+wy*d[1,1]+wz*d[2,1]+d[3,1]
        cw = wx*d[0,3]+wy*d[1,3]+wz*d[2,3]+d[3,3]
        if abs(cw) < 1e-6: return None
        inv_w = 1.0 / cw
        return ((cx * inv_w + 1.0) * 0.5 * vw, (1.0 - cy * inv_w) * 0.5 * vh)

    def _get_translate_lines_batch(self, pos, transform, cam, vw, vh):
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
        arrow_len_px = self.ARROW_SIZE_RATIO * self.SCREEN_AXIS_LENGTH
        ph_px = self.PLANE_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / self.BASE_AXIS_LENGTH
        is_2d = cam.is_2d_mode if cam else False

        color = AXIS_HIGHLIGHT if active == GizmoAxis.X else AXIS_COLORS[GizmoAxis.X]
        batch.append(pos, tip_x, color)
        if entity_sp and tip_sp_x:
            self._add_arrow_head(tip_x, tip_sp_x, entity_sp, arrow_len_px, inv_vp, cam_fwd, vw, vh, color)
        color = AXIS_HIGHLIGHT if active == GizmoAxis.Y else AXIS_COLORS[GizmoAxis.Y]
        batch.append(pos, tip_y, color)
        if entity_sp and tip_sp_y:
            self._add_arrow_head(tip_y, tip_sp_y, entity_sp, arrow_len_px, inv_vp, cam_fwd, vw, vh, color)
        if not is_2d:
            color = AXIS_HIGHLIGHT if active == GizmoAxis.Z else AXIS_COLORS[GizmoAxis.Z]
            batch.append(pos, tip_z, color)
            if entity_sp and tip_sp_z:
                self._add_arrow_head(tip_z, tip_sp_z, entity_sp, arrow_len_px, inv_vp, cam_fwd, vw, vh, color)
            color = AXIS_HIGHLIGHT if active == GizmoAxis.XZ else AXIS_COLORS[GizmoAxis.XZ]
            if entity_sp and tip_sp_x and tip_sp_z:
                self._add_plane_handle(pos, entity_sp, tip_sp_x, tip_sp_z, ph_px, inv_vp, cam_fwd, vw, vh, color)
            color = AXIS_HIGHLIGHT if active == GizmoAxis.YZ else AXIS_COLORS[GizmoAxis.YZ]
            if entity_sp and tip_sp_y and tip_sp_z:
                self._add_plane_handle(pos, entity_sp, tip_sp_y, tip_sp_z, ph_px, inv_vp, cam_fwd, vw, vh, color)
        color = AXIS_HIGHLIGHT if active == GizmoAxis.XY else AXIS_COLORS[GizmoAxis.XY]
        if entity_sp and tip_sp_x and tip_sp_y:
            self._add_plane_handle(pos, entity_sp, tip_sp_x, tip_sp_y, ph_px, inv_vp, cam_fwd, vw, vh, color)
        center_color = AXIS_HIGHLIGHT if active == GizmoAxis.ALL else [1.0, 1.0, 1.0, 0.8]
        if entity_sp:
            self._add_center_handle(pos, entity_sp, inv_vp, cam_fwd, vw, vh, center_color)

    def _add_arrow_head(self, tip_w: Vec3, tip_sp: tuple, entity_sp: tuple,
                         arrow_len_px: float, inv_vp: Mat4, cam_fwd: Vec3,
                         vw: int, vh: int, color: list):
        batch = self._batch
        dx = tip_sp[0] - entity_sp[0]
        dy = tip_sp[1] - entity_sp[1]
        screen_len = math.sqrt(dx * dx + dy * dy)
        if screen_len < 1e-8:
            return
        ndx, ndy = dx / screen_len, dy / screen_len
        cone_len_px = arrow_len_px * 1.0
        cone_radius_px = arrow_len_px * 0.45
        base_x = tip_sp[0] - ndx * cone_len_px
        base_y = tip_sp[1] - ndy * cone_len_px
        pdx, pdy = -ndy, ndx
        f1x = base_x + pdx * cone_radius_px
        f1y = base_y + pdy * cone_radius_px
        f2x = base_x - pdx * cone_radius_px
        f2y = base_y - pdy * cone_radius_px
        f3x = base_x + pdx * cone_radius_px * 0.5 + ndx * cone_len_px * 0.3
        f3y = base_y + pdy * cone_radius_px * 0.5 + ndy * cone_len_px * 0.3
        f4x = base_x - pdx * cone_radius_px * 0.5 + ndx * cone_len_px * 0.3
        f4y = base_y - pdy * cone_radius_px * 0.5 + ndy * cone_len_px * 0.3
        tip_w2 = self._screen_pos_to_world(tip_sp[0], tip_sp[1], tip_w, inv_vp, cam_fwd, vw, vh)
        f1_w = self._screen_pos_to_world(f1x, f1y, tip_w, inv_vp, cam_fwd, vw, vh)
        f2_w = self._screen_pos_to_world(f2x, f2y, tip_w, inv_vp, cam_fwd, vw, vh)
        base_w = self._screen_pos_to_world(base_x, base_y, tip_w, inv_vp, cam_fwd, vw, vh)
        batch.append(tip_w2, f1_w, color)
        batch.append(tip_w2, f2_w, color)
        batch.append(f1_w, f2_w, color)

    def _add_center_handle(self, center_w: Vec3, center_sp: tuple,
                            inv_vp: Mat4, cam_fwd: Vec3,
                            vw: int, vh: int, color: list):
        batch = self._batch
        cx, cy = center_sp
        half_px = 4.0
        corners_w = []
        for sx, sy in [
            (cx - half_px, cy),
            (cx, cy + half_px),
            (cx + half_px, cy),
            (cx, cy - half_px),
        ]:
            corners_w.append(self._screen_pos_to_world(sx, sy, center_w, inv_vp, cam_fwd, vw, vh))
        batch.append(corners_w[0], corners_w[1], color)
        batch.append(corners_w[1], corners_w[2], color)
        batch.append(corners_w[2], corners_w[3], color)
        batch.append(corners_w[3], corners_w[0], color)

    def _add_plane_handle(self, center_w: Vec3, center_sp: tuple,
                           axis1_sp: tuple, axis2_sp: tuple, size_px: float,
                           inv_vp: Mat4, cam_fwd: Vec3,
                           vw: int, vh: int, color: list):
        batch = self._batch
        OFFSET_RATIO = 0.2
        def norm_dir(sp):
            dx = sp[0] - center_sp[0]
            dy = sp[1] - center_sp[1]
            d = math.sqrt(dx * dx + dy * dy)
            if d < 1e-8:
                return (1.0, 0.0)
            return (dx / d, dy / d)
        d1x, d1y = norm_dir(axis1_sp)
        d2x, d2y = norm_dir(axis2_sp)
        offset_px = size_px * OFFSET_RATIO
        ox = center_sp[0] + d1x * offset_px + d2x * offset_px
        oy = center_sp[1] + d1y * offset_px + d2y * offset_px
        corners_w = []
        for sx, sy in [
            (ox, oy),
            (ox + d1x * size_px, oy + d1y * size_px),
            (ox + d1x * size_px + d2x * size_px, oy + d1y * size_px + d2y * size_px),
            (ox + d2x * size_px, oy + d2y * size_px),
        ]:
            corners_w.append(self._screen_pos_to_world(sx, sy, center_w, inv_vp, cam_fwd, vw, vh))
        batch.append_quad(corners_w, color)

    def _pick_axis(self, mx: int, my: int, transform, cam: SceneCamera, vw: int, vh: int) -> GizmoAxis:
        if self._is_multigizmo_active():
            axis = self._pick_multigizmo_axis(mx, my, transform, cam, vw, vh)
            return axis
        pos = transform.position + self._pivot_offset
        self._update_cache(cam, vw, vh)
        vp_mat = self._vp_mat_cache
        if self._mode == GizmoMode.ROTATE:
            return self._pick_rotation_axis(mx, my, transform, cam, vp_mat, vw, vh)
        rx, ry, rz = self._get_axis_directions(transform)
        is_2d = cam.is_2d_mode
        sp_start = self._project_to_screen(pos, vp_mat, vw, vh)
        wpp = self._wpp_cache
        def _scr_dir(axis):
            eps = pos + axis * max(0.001, wpp * 10.0)
            sp = self._project_to_screen(eps, vp_mat, vw, vh)
            if sp_start and sp:
                dx = sp[0] - sp_start[0]
                dy = sp[1] - sp_start[1]
                d = math.sqrt(dx * dx + dy * dy)
                if d > 1e-8:
                    return (dx / d, dy / d)
            return None
        sd_x = _scr_dir(rx)
        sd_y = _scr_dir(ry)
        sd_z = _scr_dir(rz) if not is_2d else None
        if self._mode == GizmoMode.TRANSLATE:
            if sp_start:
                half_px = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH * 0.5
                cx, cy = sp_start
                if abs(mx - cx) <= half_px and abs(my - cy) <= half_px:
                    return GizmoAxis.ALL
            ph_px = self.PLANE_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / self.BASE_AXIS_LENGTH
            offset_px = ph_px * 0.2
            plane_axes = [(GizmoAxis.XY, sd_x, sd_y)]
            if not is_2d:
                plane_axes.extend([
                    (GizmoAxis.XZ, sd_x, sd_z),
                    (GizmoAxis.YZ, sd_y, sd_z),
                ])
            for axis_id, sd1, sd2 in plane_axes:
                if sd1 and sd2 and sp_start:
                    d1x, d1y = sd1
                    d2x, d2y = sd2
                    ox = sp_start[0] + d1x * offset_px + d2x * offset_px
                    oy = sp_start[1] + d1y * offset_px + d2y * offset_px
                    corners_sp = [
                        (ox, oy),
                        (ox + d1x * ph_px, oy + d1y * ph_px),
                        (ox + d1x * ph_px + d2x * ph_px, oy + d1y * ph_px + d2y * ph_px),
                        (ox + d2x * ph_px, oy + d2y * ph_px),
                    ]
                    if self._point_in_convex_quad(mx, my, corners_sp):
                        return axis_id
        if self._mode == GizmoMode.SCALE and sp_start:
            half_px = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / (self.BASE_AXIS_LENGTH * 2.0) * 1.2
            d = math.sqrt((mx - sp_start[0])**2 + (my - sp_start[1])**2)
            if d < half_px * 1.5:
                return GizmoAxis.ALL
        best_axis = GizmoAxis.NONE
        best_dist = self.PICK_THRESHOLD
        axes = [GizmoAxis.X, GizmoAxis.Y]
        if not is_2d:
            axes.append(GizmoAxis.Z)
        axis_dirs = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}
        for axis_id in axes:
            direction = axis_dirs[axis_id]
            eps_pos = pos + direction * 0.001
            sp_eps = self._project_to_screen(eps_pos, vp_mat, vw, vh)
            if sp_start and sp_eps:
                dx = sp_eps[0] - sp_start[0]
                dy = sp_eps[1] - sp_start[1]
                screen_len = math.sqrt(dx * dx + dy * dy)
                if screen_len < 1e-8:
                    d = math.sqrt((mx - sp_start[0])**2 + (my - sp_start[1])**2)
                else:
                    sp_end_x = sp_start[0] + dx / screen_len * self.SCREEN_AXIS_LENGTH
                    sp_end_y = sp_start[1] + dy / screen_len * self.SCREEN_AXIS_LENGTH
                    d = self._point_to_segment_dist(mx, my, sp_start[0], sp_start[1], sp_end_x, sp_end_y)
                if d < best_dist:
                    best_dist = d
                    best_axis = axis_id
        return best_axis

    def _point_in_convex_quad(self, px, py, corners) -> bool:
        n = len(corners)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = corners[i]
            xj, yj = corners[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def _closest_point_ray_to_line(self, ray_o: Vec3, ray_d: Vec3, line_o: Vec3, line_d: Vec3) -> Optional[float]:
        w0 = ray_o - line_o
        a = ray_d.dot(ray_d)
        b = ray_d.dot(line_d)
        c = line_d.dot(line_d)
        d = ray_d.dot(w0)
        e = line_d.dot(w0)
        denom = a * c - b * b
        if abs(denom) < 1e-10:
            return None
        return (b * e - c * d) / denom

    def _best_translate_plane_normal(self, axis_dir: Vec3, cam_fwd: Vec3) -> Vec3:
        perp = axis_dir.cross(cam_fwd)
        if perp.length() < 1e-6:
            perp = axis_dir.cross(Vec3(0, 1, 0))
        if perp.length() < 1e-6:
            perp = axis_dir.cross(Vec3(1, 0, 0))
        return perp.cross(axis_dir).normalized()

    def _apply_translate(self, transform, cam: SceneCamera, mx: int, my: int, vw: int, vh: int):
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
            axis_delta = (hit - self._drag_hit_start).dot(axis_dir)
            if snap_active and self._snap_translate > 0:
                axis_delta = self._apply_snap(axis_delta, self._snap_translate, f"t_{self._active_axis.value}")
            self._drag_delta = axis_dir * axis_delta
            self._delta_text = f"\u0394 {axis_delta:+.3f}"
            new_world_pos = self._drag_entity_start_pos + self._drag_delta
        elif self._active_axis in (GizmoAxis.XY, GizmoAxis.XZ, GizmoAxis.YZ, GizmoAxis.ALL):
            a1, a2 = self._drag_plane_axes
            if self._active_axis == GizmoAxis.ALL:
                plane_normal = cam.forward
            else:
                plane_normal = a1.cross(a2).normalized()
            hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
            if not hit:
                return
            delta = hit - self._drag_hit_start
            if self._active_axis == GizmoAxis.ALL:
                if snap_active and self._snap_translate > 0:
                    dx_snap = self._apply_snap(delta.x, self._snap_translate, f"tp_{self._active_axis.value}_x")
                    dy_snap = self._apply_snap(delta.y, self._snap_translate, f"tp_{self._active_axis.value}_y")
                    dz_snap = self._apply_snap(delta.z, self._snap_translate, f"tp_{self._active_axis.value}_z")
                    delta = Vec3(dx_snap, dy_snap, dz_snap)
                self._drag_delta = delta
                self._delta_text = f"\u0394 {delta.x:+.3f}, {delta.y:+.3f}, {delta.z:+.3f}"
            else:
                d1 = delta.dot(a1)
                d2 = delta.dot(a2)
                if snap_active and self._snap_translate > 0:
                    d1 = self._apply_snap(d1, self._snap_translate, f"tp_{self._active_axis.value}_1")
                    d2 = self._apply_snap(d2, self._snap_translate, f"tp_{self._active_axis.value}_2")
                self._drag_delta = a1 * d1 + a2 * d2
                self._delta_text = f"\u0394 {d1:+.3f}, {d2:+.3f}"
            new_world_pos = self._drag_entity_start_pos + self._drag_delta
        else:
            return
        entity = self._entity
        if entity and entity.parent:
            pt = entity.parent.transform
            if pt:
                from core.math_helpers import mat4_inv_fast
                from core.maths.math3d import FLOAT_TYPE
                pt._update_world_matrix()
                inv = mat4_inv_fast(pt._world_matrix._d)
                world_arr = np.array([new_world_pos.x, new_world_pos.y, new_world_pos.z, 1.0], dtype=FLOAT_TYPE)
                local_arr = world_arr @ inv
                transform.local_position = Vec3(float(local_arr[0]), float(local_arr[1]), float(local_arr[2]))
                return
        transform.position = new_world_pos
