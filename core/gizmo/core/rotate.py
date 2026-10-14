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

class RotateMixin:

    def _update_cache(self, cam: SceneCamera, vw: int, vh: int):
        vp = cam.get_view_matrix() * cam.get_projection_matrix(vw / max(1, vh))
        self._vp_mat_cache = vp
        self._inv_vp_cache = vp.inverted()
        self._cam_fwd_cache = cam.forward
        if cam.is_orthographic or cam.is_2d_mode:
            half_size = cam._ortho_zoom_distance * math.tan(math.radians(cam.DEFAULT_FOV) * 0.5)
            self._wpp_cache = (2.0 * half_size) / max(1, vh)
        else:
            pos = self._visual_center if self._visual_center is not None else (
                self._entity.transform.position + self._pivot_offset
                if self._entity else Vec3.zero())
            view_dist = max((pos - cam.position).dot(cam.forward), 0.1)
            fov_rad = math.radians(cam.fov)
            self._wpp_cache = (2.0 * view_dist * math.tan(fov_rad * 0.5)) / max(1, vh)

    def _get_world_per_pixel(self, cam: SceneCamera, entity_pos: Vec3, vh: int) -> float:
        if cam.is_orthographic or cam.is_2d_mode:
            half_size = cam._ortho_zoom_distance * math.tan(math.radians(cam.DEFAULT_FOV) * 0.5)
            return (2.0 * half_size) / max(1, vh)
        cam_dir = cam.forward
        view_dist = max((entity_pos - cam.position).dot(cam_dir), 0.1)
        fov_rad = math.radians(cam.fov)
        return (2.0 * view_dist * math.tan(fov_rad * 0.5)) / max(1, vh)

    def _screen_axis_tip(self, pos: Vec3, axis_dir: Vec3, cam: SceneCamera, vw: int, vh: int) -> Vec3:
        if self._vp_mat_cache is None:
            self._update_cache(cam, vw, vh)
        vp = self._vp_mat_cache
        sp_base = self._project_to_screen(pos, vp, vw, vh)
        if sp_base is None:
            return pos + axis_dir * self.BASE_AXIS_LENGTH
        wpp = self._wpp_cache
        eps_pos = pos + axis_dir * wpp * 10.0
        sp_eps = self._project_to_screen(eps_pos, vp, vw, vh)
        if sp_eps is None:
            return pos + axis_dir * self.BASE_AXIS_LENGTH
        dx = sp_eps[0] - sp_base[0]
        dy = sp_eps[1] - sp_base[1]
        screen_len = math.sqrt(dx * dx + dy * dy)
        if screen_len < 1e-8:
            return pos + axis_dir * wpp * self.SCREEN_AXIS_LENGTH
        sx = sp_base[0] + dx / screen_len * self.SCREEN_AXIS_LENGTH
        sy = sp_base[1] + dy / screen_len * self.SCREEN_AXIS_LENGTH
        ray_o, ray_d = self._screen_to_ray(sx, sy, cam, vw, vh)
        n = ray_d.cross(axis_dir)
        n_len_sq = n.dot(n)
        if n_len_sq < 1e-12:
            cam_fwd = cam.forward
            denom = ray_d.dot(cam_fwd)
            if abs(denom) < 1e-8:
                return pos + axis_dir * wpp * self.SCREEN_AXIS_LENGTH
            t = (pos - ray_o).dot(cam_fwd) / denom
            if t < 0:
                return pos + axis_dir * wpp * self.SCREEN_AXIS_LENGTH
            return ray_o + ray_d * t
        p = pos - ray_o
        t_axis = p.cross(ray_d).dot(n) / n_len_sq
        if t_axis < 0:
            return pos + axis_dir * wpp * self.SCREEN_AXIS_LENGTH
        return pos + axis_dir * t_axis

    def _project_points_to_screen_np(self, points: np.ndarray, vp_mat: Mat4, vw: int, vh: int) -> np.ndarray:
        d = vp_mat._d
        ones = np.ones((points.shape[0], 1), dtype=FLOAT_T)
        hp = np.hstack([points, ones])
        cx = hp[:, 0]*d[0,0] + hp[:, 1]*d[1,0] + hp[:, 2]*d[2,0] + d[3,0]
        cy = hp[:, 0]*d[0,1] + hp[:, 1]*d[1,1] + hp[:, 2]*d[2,1] + d[3,1]
        cw = hp[:, 0]*d[0,3] + hp[:, 1]*d[1,3] + hp[:, 2]*d[2,3] + d[3,3]
        valid = np.abs(cw) > 1e-6
        sx = np.full_like(cx, np.nan)
        sy = np.full_like(cy, np.nan)
        inv_w = np.where(valid, 1.0 / cw, 0.0)
        sx = (cx * inv_w + 1.0) * 0.5 * vw
        sy = (1.0 - cy * inv_w) * 0.5 * vh
        sx[~valid] = np.nan
        sy[~valid] = np.nan
        return np.column_stack([sx, sy])

    def _get_axis_directions(self, transform, cam=None):
        if self._orientation_lock and self._orientation_lock_cache is not None:
            return self._orientation_lock_cache
        if self._multigizmo_enabled:
            align = self._multigizmo_alignment
            if align == "view" and cam is not None:
                r = cam._right() if hasattr(cam, "_right") else Vec3.right()
                u = cam._up() if hasattr(cam, "_up") else Vec3.up()
                f = -cam.forward if hasattr(cam, "forward") else Vec3(0,0,1)
                return r, u, f
            if align == "custom" and self._custom_matrix is not None:
                try:
                    m = self._custom_matrix._d
                    rx = Vec3(float(m[0,0]), float(m[0,1]), float(m[0,2])).normalized()
                    ry = Vec3(float(m[1,0]), float(m[1,1]), float(m[1,2])).normalized()
                    rz = Vec3(float(m[2,0]), float(m[2,1]), float(m[2,2])).normalized()
                    return rx, ry, rz
                except Exception:
                    pass
            if align == "world":
                return Vec3.right(), Vec3.up(), Vec3(0, 0, 1)
            if align == "local":
                return transform.right, transform.up, -transform.forward
        if self._space == GizmoSpace.LOCAL:
            return transform.right, transform.up, -transform.forward
        else:
            return Vec3.right(), Vec3.up(), Vec3(0, 0, 1)

    def _get_perpendiculars(self, v: Vec3):
        if abs(v.x) < 0.9:
            ref = Vec3(1, 0, 0)
        else:
            ref = Vec3(0, 1, 0)
        p1 = v.cross(ref).normalized()
        p2 = v.cross(p1).normalized()
        return p1, p2

    def _get_rotate_lines_batch(self, pos, transform, cam, vw, vh):
        batch = self._batch
        segs = 64
        active = self._active_axis if self._dragging else self._hover_axis
        rx, ry, rz = self._get_axis_directions(transform)
        if self._space == GizmoSpace.LOCAL:
            circle_defs = [(GizmoAxis.X, rx), (GizmoAxis.Y, ry), (GizmoAxis.Z, rz)]
        else:
            circle_defs = [(GizmoAxis.X, Vec3(1,0,0)), (GizmoAxis.Y, Vec3(0,1,0)), (GizmoAxis.Z, Vec3(0,0,1))]
        vp = self._vp_mat_cache
        world_radius = self._wpp_cache * self.SCREEN_AXIS_LENGTH * 0.85
        for axis_id, normal in circle_defs:
            color = AXIS_HIGHLIGHT if active == axis_id else AXIS_COLORS[axis_id]
            p1, p2 = self._get_perpendiculars(normal)
            radius = world_radius
            angles = np.linspace(0.0, 2.0 * math.pi, segs + 1, endpoint=True)
            pts = np.empty((segs + 1, 3), dtype=FLOAT_T)
            p1a = np.array([p1.x, p1.y, p1.z], dtype=FLOAT_T)
            p2a = np.array([p2.x, p2.y, p2.z], dtype=FLOAT_T)
            pos_a = np.array([pos.x, pos.y, pos.z], dtype=FLOAT_T)
            cos_a = np.cos(angles)
            sin_a = np.sin(angles)
            pts[:, 0] = pos_a[0] + p1a[0] * cos_a * radius + p2a[0] * sin_a * radius
            pts[:, 1] = pos_a[1] + p1a[1] * cos_a * radius + p2a[1] * sin_a * radius
            pts[:, 2] = pos_a[2] + p1a[2] * cos_a * radius + p2a[2] * sin_a * radius
            sp = self._project_points_to_screen_np(pts, vp, vw, vh)
            valid = ~np.isnan(sp[:, 0])
            for i in range(segs):
                if valid[i] and valid[i+1]:
                    s = Vec3(float(pts[i,0]), float(pts[i,1]), float(pts[i,2]))
                    e = Vec3(float(pts[i+1,0]), float(pts[i+1,1]), float(pts[i+1,2]))
                    batch.append(s, e, color)
        view_color = AXIS_HIGHLIGHT if active == GizmoAxis.ALL else [0.85, 0.85, 0.85, 1.0]
        view_normal = cam.forward
        p1, p2 = self._get_perpendiculars(view_normal)
        outer_radius = world_radius * 1.18
        angles = np.linspace(0.0, 2.0 * math.pi, segs + 1, endpoint=True)
        pts = np.empty((segs + 1, 3), dtype=FLOAT_T)
        p1a = np.array([p1.x, p1.y, p1.z], dtype=FLOAT_T)
        p2a = np.array([p2.x, p2.y, p2.z], dtype=FLOAT_T)
        pos_a = np.array([pos.x, pos.y, pos.z], dtype=FLOAT_T)
        cos_a = np.cos(angles)
        sin_a = np.sin(angles)
        pts[:, 0] = pos_a[0] + p1a[0] * cos_a * outer_radius + p2a[0] * sin_a * outer_radius
        pts[:, 1] = pos_a[1] + p1a[1] * cos_a * outer_radius + p2a[1] * sin_a * outer_radius
        pts[:, 2] = pos_a[2] + p1a[2] * cos_a * outer_radius + p2a[2] * sin_a * outer_radius
        sp = self._project_points_to_screen_np(pts, vp, vw, vh)
        valid = ~np.isnan(sp[:, 0])
        for i in range(segs):
            if valid[i] and valid[i+1]:
                s = Vec3(float(pts[i,0]), float(pts[i,1]), float(pts[i,2]))
                e = Vec3(float(pts[i+1,0]), float(pts[i+1,1]), float(pts[i+1,2]))
                batch.append(s, e, view_color)

    def _get_vertex_rotate_lines_batch(self, pos, transform, cam, vw, vh):
        batch = self._batch
        segs = 32
        active = self._active_axis if self._dragging else self._hover_axis
        active_op = getattr(self, '_active_op' if self._dragging else '_hover_op', 'rotate')
        if active_op not in ('rotate', 'translate'):
            active = GizmoAxis.NONE
        rx, ry, rz = self._get_axis_directions(transform, cam)
        if self._multigizmo_alignment == "view" and cam is not None:
            rx, ry, rz = self._get_axis_directions(transform, cam)
        elif self._space == GizmoSpace.LOCAL or self._multigizmo_alignment == "local":
            rx, ry, rz = self._get_axis_directions(transform, cam)
        else:
            rx, ry, rz = Vec3.right(), Vec3.up(), Vec3(0, 0, 1)
        circle_defs = [(GizmoAxis.X, rx), (GizmoAxis.Y, ry), (GizmoAxis.Z, rz)]
        vp = self._vp_mat_cache
        inv_vp = self._inv_vp_cache
        cam_fwd = self._cam_fwd_cache
        world_radius = self._wpp_cache * self.SCREEN_AXIS_LENGTH * 0.72
        for axis_id, normal in circle_defs:
            is_active = (active == axis_id and active_op == 'rotate')
            color = AXIS_HIGHLIGHT if is_active else AXIS_COLORS[axis_id]
            p1, p2 = self._get_perpendiculars(normal)
            p1n = p1.normalized()
            p2n = p2.normalized()
            angles = np.linspace(0.0, math.pi * 0.5, segs + 1, endpoint=True)
            pts = np.empty((segs + 1, 3), dtype=FLOAT_T)
            p1a = np.array([p1n.x, p1n.y, p1n.z], dtype=FLOAT_T)
            p2a = np.array([p2n.x, p2n.y, p2n.z], dtype=FLOAT_T)
            pos_a = np.array([pos.x, pos.y, pos.z], dtype=FLOAT_T)
            cos_a = np.cos(angles)
            sin_a = np.sin(angles)
            pts[:, 0] = pos_a[0] + p1a[0] * cos_a * world_radius + p2a[0] * sin_a * world_radius
            pts[:, 1] = pos_a[1] + p1a[1] * cos_a * world_radius + p2a[1] * sin_a * world_radius
            pts[:, 2] = pos_a[2] + p1a[2] * cos_a * world_radius + p2a[2] * sin_a * world_radius
            sp = self._project_points_to_screen_np(pts, vp, vw, vh)
            valid = ~np.isnan(sp[:, 0])
            for i in range(segs):
                if valid[i] and valid[i+1]:
                    s = Vec3(float(pts[i,0]), float(pts[i,1]), float(pts[i,2]))
                    e = Vec3(float(pts[i+1,0]), float(pts[i+1,1]), float(pts[i+1,2]))
                    batch.append(s, e, color)
            end_pt = pos + p2n * world_radius
            end_sp = self._project_to_screen(end_pt, vp, vw, vh)
            if end_sp is not None:
                scale_color = AXIS_COLORS[axis_id]
                if is_active:
                    scale_color = AXIS_HIGHLIGHT
                half_px = 6.0
                scale_pt = pos + p2n * world_radius * 1.08
                scale_sp = self._project_to_screen(scale_pt, vp, vw, vh)
                if scale_sp is not None:
                    self._add_cube_handle(scale_pt, scale_sp, half_px, inv_vp, cam_fwd, vw, vh, scale_color)

    def _pick_rotation_axis(self, mx: int, my: int, transform, cam: SceneCamera, vp_mat: Mat4, vw: int, vh: int) -> GizmoAxis:
        pos = transform.position + self._pivot_offset
        if self._space == GizmoSpace.LOCAL:
            rx, ry, rz = self._get_axis_directions(transform)
            circle_defs = [(GizmoAxis.X, rx), (GizmoAxis.Y, ry), (GizmoAxis.Z, rz)]
        else:
            circle_defs = [(GizmoAxis.X, Vec3(1,0,0)), (GizmoAxis.Y, Vec3(0,1,0)), (GizmoAxis.Z, Vec3(0,0,1))]
        best_axis = GizmoAxis.NONE
        best_dist = self.PICK_THRESHOLD
        segs = 64
        d_mat = vp_mat._d
        px, py, pz = pos.x, pos.y, pos.z
        for axis_id, normal in circle_defs:
            p1, p2 = self._get_perpendiculars(normal)
            radius = self._wpp_cache * self.SCREEN_AXIS_LENGTH * 0.85
            p1x, p1y, p1z = p1.x * radius, p1.y * radius, p1.z * radius
            p2x, p2y, p2z = p2.x * radius, p2.y * radius, p2.z * radius
            angles = np.linspace(0.0, 2.0 * math.pi, segs + 1, endpoint=True)
            cos_a = np.cos(angles)
            sin_a = np.sin(angles)
            wxs = px + p1x * cos_a + p2x * sin_a
            wys = py + p1y * cos_a + p2y * sin_a
            wzs = pz + p1z * cos_a + p2z * sin_a
            cxs = wxs*d_mat[0,0]+wys*d_mat[1,0]+wzs*d_mat[2,0]+d_mat[3,0]
            cys = wxs*d_mat[0,1]+wys*d_mat[1,1]+wzs*d_mat[2,1]+d_mat[3,1]
            cws = wxs*d_mat[0,3]+wys*d_mat[1,3]+wzs*d_mat[2,3]+d_mat[3,3]
            valid = np.abs(cws) > 1e-6
            inv_w = np.where(valid, 1.0 / np.where(valid, cws, 1.0), 0.0)
            sxs = (cxs * inv_w + 1.0) * 0.5 * vw
            sys_ = (1.0 - cys * inv_w) * 0.5 * vh
            min_d = float('inf')
            for i in range(segs):
                if not valid[i] or not valid[i+1]: continue
                ax, ay = sxs[i], sys_[i]
                bx, by = sxs[i+1], sys_[i+1]
                ddx, ddy = bx - ax, by - ay
                len_sq = ddx*ddx + ddy*ddy
                if len_sq < 1e-6:
                    dd = math.sqrt((mx-ax)**2 + (my-ay)**2)
                else:
                    t = max(0.0, min(1.0, ((mx-ax)*ddx + (my-ay)*ddy) / len_sq))
                    dd = math.sqrt((mx - ax - t*ddx)**2 + (my - ay - t*ddy)**2)
                if dd < min_d: min_d = dd
            if min_d < best_dist:
                best_dist = min_d
                best_axis = axis_id
        sp_center = self._project_to_screen(pos, vp_mat, vw, vh)
        if sp_center is not None:
            outer_px = self.SCREEN_AXIS_LENGTH * 0.85 * 1.18
            dist = math.sqrt((mx - sp_center[0])**2 + (my - sp_center[1])**2)
            if outer_px - self.PICK_THRESHOLD < dist < outer_px + self.PICK_THRESHOLD:
                view_dist = abs(dist - outer_px)
                if view_dist < best_dist:
                    best_axis = GizmoAxis.ALL
        return best_axis

    def _apply_rotate(self, transform, cam: SceneCamera, mx: int, my: int, vw: int, vh: int):
        pos = self._drag_entity_start_pos + self._pivot_offset
        axis_dir = self._drag_axis_dir
        ray_origin, ray_dir = self._screen_to_ray(mx, my, cam, vw, vh)
        hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, axis_dir)
        if not hit:
            return
        initial_hit = self._drag_hit_start
        c2i = initial_hit - pos
        c2c = hit - pos
        initial_proj = c2i - axis_dir * c2i.dot(axis_dir)
        current_proj = c2c - axis_dir * c2c.dot(axis_dir)
        il = initial_proj.length()
        cl = current_proj.length()
        if il < 1e-6 or cl < 1e-6:
            return
        id_vec = initial_proj * (1.0 / il)
        cd_vec = current_proj * (1.0 / cl)
        angle = math.degrees(math.atan2(id_vec.cross(cd_vec).dot(axis_dir), id_vec.dot(cd_vec)))
        snap_active = self._snap_enabled and not self._ctrl_down
        if snap_active and self._snap_rotate > 0:
            angle = self._apply_snap(angle, self._snap_rotate, "rot")
        self._delta_text = f"\u0394 {angle:+.1f}\u00b0"
        is_local = self._space == GizmoSpace.LOCAL
        entity = self._entity
        if is_local and self._active_axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
            local_axis = {GizmoAxis.X: Vec3(1,0,0), GizmoAxis.Y: Vec3(0,1,0), GizmoAxis.Z: Vec3(0,0,1)}[self._active_axis]
            dq = Quat.from_axis_angle(local_axis, angle)
            transform.local_rotation = (self._drag_start_rot * dq).normalized()
        else:
            world_axis = axis_dir
            if self._active_axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
                world_axis = {GizmoAxis.X: Vec3(1,0,0), GizmoAxis.Y: Vec3(0,1,0), GizmoAxis.Z: Vec3(0,0,1)}[self._active_axis] if not is_local else axis_dir
                if not is_local:
                    world_axis = {GizmoAxis.X: Vec3(1,0,0), GizmoAxis.Y: Vec3(0,1,0), GizmoAxis.Z: Vec3(0,0,1)}[self._active_axis]
            dq = Quat.from_axis_angle(world_axis, angle)
            if entity and entity.parent:
                pt = entity.parent.transform
                if pt:
                    pt._update_world_matrix()
                    pw = pt._world_matrix
                    _, prot, _ = pw.decompose()
                    prot = prot.normalized()
                    dq_world = dq
                    new_world = dq_world * (prot * self._drag_start_rot)
                    new_local = prot.conjugate() * new_world
                    transform.local_rotation = new_local.normalized()
                    return
            transform.local_rotation = (dq * self._drag_start_rot).normalized()
