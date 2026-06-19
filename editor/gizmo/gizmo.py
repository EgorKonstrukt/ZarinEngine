from __future__ import annotations
import math
import numpy as np
from enum import Enum
from typing import Optional, TYPE_CHECKING
from core.math3d import Vec3, Mat4, Quat
if TYPE_CHECKING:
    from core.ecs import Entity
    from editor.scene_camera import SceneCamera
class GizmoMode(Enum):
    NONE = "none"
    TRANSLATE = "translate"
    ROTATE = "rotate"
    SCALE = "scale"
class GizmoSpace(Enum):
    WORLD = "world"
    LOCAL = "local"
class GizmoAxis(Enum):
    NONE = 0
    X = 1
    Y = 2
    Z = 3
    XY = 4
    XZ = 5
    YZ = 6
    ALL = 7
AXIS_COLORS = {
    GizmoAxis.X: [0.900, 0.050, 0.050, 1.0],
    GizmoAxis.Y: [0.388, 0.900, 0.050, 1.0],
    GizmoAxis.Z: [0.050, 0.388, 0.921, 1.0],
    GizmoAxis.XY: [0.050, 0.388, 0.921, 0.4],
    GizmoAxis.XZ: [0.388, 0.792, 0.050, 0.4],
    GizmoAxis.YZ: [0.900, 0.050, 0.050, 0.4],
    GizmoAxis.ALL: [1.0, 1.0, 1.0, 1.0],
}
AXIS_HIGHLIGHT = [1.0, 0.835, 0.0, 1.0]
class Gizmo:
    HANDLE_SIZE = 0.1
    BASE_AXIS_LENGTH = 1.0
    PLANE_HANDLE_SIZE = 0.22
    PICK_THRESHOLD = 30.0
    ARROW_SIZE_RATIO = 0.2
    CENTER_HANDLE_SIZE = 0.14
    SCREEN_AXIS_LENGTH = 100.0
    def load_config(self, config) -> None:
        self.HANDLE_SIZE = config.get("gizmo.handle_size", self.HANDLE_SIZE)
        self.BASE_AXIS_LENGTH = config.get("gizmo.base_axis_length", self.BASE_AXIS_LENGTH)
        self.PLANE_HANDLE_SIZE = config.get("gizmo.plane_handle_size", self.PLANE_HANDLE_SIZE)
        self.PICK_THRESHOLD = config.get("gizmo.pick_threshold", self.PICK_THRESHOLD)
        self.ARROW_SIZE_RATIO = config.get("gizmo.arrow_size_ratio", self.ARROW_SIZE_RATIO)
        self.CENTER_HANDLE_SIZE = config.get("gizmo.center_handle_size", self.CENTER_HANDLE_SIZE)
        self.SCREEN_AXIS_LENGTH = config.get("gizmo.screen_axis_length", self.SCREEN_AXIS_LENGTH)
        self._smooth_snap_enabled = config.get("gizmo.smooth_snap", True)
        self._smooth_snap_speed = config.get("gizmo.smooth_snap_speed", 0.25)
        self._show_delta_label = config.get("gizmo.show_delta_label", True)
    def __init__(self):
        self._mode: GizmoMode = GizmoMode.TRANSLATE
        self._space: GizmoSpace = GizmoSpace.WORLD
        self._entity: Optional[Entity] = None
        self._active_axis: GizmoAxis = GizmoAxis.NONE
        self._hover_axis: GizmoAxis = GizmoAxis.NONE
        self._dragging: bool = False
        self._drag_start_mouse: tuple[int, int] = (0, 0)
        self._drag_start_pos: Vec3 = Vec3.zero()
        self._drag_start_rot: Quat = Quat.identity()
        self._drag_start_scale: Vec3 = Vec3.one()
        self._drag_axis_dir: Vec3 = Vec3.zero()
        self._drag_hit_start: Vec3 = Vec3.zero()
        self._drag_entity_start_pos: Vec3 = Vec3.zero()
        self._drag_plane_axes: tuple[Vec3, Vec3] = (Vec3.zero(), Vec3.zero())
        self._snap_translate: float = 0.0
        self._snap_rotate: float = 0.0
        self._snap_scale: float = 0.0
        self._snap_enabled: bool = True
        self._pivot_offset: Vec3 = Vec3.zero()
        self._visual_center: Vec3 | None = None
        self._ctrl_down: bool = False
        self._delta_text: str = ""
        self._drag_delta: Vec3 = Vec3.zero()
        self._smooth_snap_enabled: bool = True
        self._show_delta_label: bool = True
        self._smooth_snap_speed: float = 0.25
        self._snap_state: dict[str, float] = {}
        self._snap_counter: int = 0
    @property
    def mode(self) -> GizmoMode: return self._mode
    @mode.setter
    def mode(self, v: GizmoMode): self._mode = v
    @property
    def space(self) -> GizmoSpace: return self._space
    @space.setter
    def space(self, v: GizmoSpace): self._space = v
    @property
    def entity(self) -> Optional[Entity]: return self._entity
    @entity.setter
    def entity(self, v: Optional[Entity]): self._entity = v
    @property
    def snap_enabled(self) -> bool: return self._snap_enabled
    @snap_enabled.setter
    def snap_enabled(self, v: bool): self._snap_enabled = v
    @property
    def snap_translate(self) -> float: return self._snap_translate
    @snap_translate.setter
    def snap_translate(self, v: float): self._snap_translate = v
    @property
    def snap_rotate(self) -> float: return self._snap_rotate
    @snap_rotate.setter
    def snap_rotate(self, v: float): self._snap_rotate = v
    @property
    def snap_scale(self) -> float: return self._snap_scale
    @snap_scale.setter
    def snap_scale(self, v: float): self._snap_scale = v
    @property
    def ctrl_down(self) -> bool: return self._ctrl_down
    @ctrl_down.setter
    def ctrl_down(self, v: bool): self._ctrl_down = v
    @property
    def delta_text(self) -> str: return self._delta_text
    @property
    def show_delta_label(self) -> bool: return self._show_delta_label
    @show_delta_label.setter
    def show_delta_label(self, v: bool): self._show_delta_label = v
    @property
    def smooth_snap_enabled(self) -> bool: return self._smooth_snap_enabled
    @smooth_snap_enabled.setter
    def smooth_snap_enabled(self, v: bool): self._smooth_snap_enabled = v
    def _snap_key(self) -> str:
        self._snap_counter += 1
        return f"{self._mode.value}_{self._active_axis.value}_{self._snap_counter}"

    def _apply_snap(self, value: float, snap: float, key: str = "") -> float:
        if snap <= 0: return value
        snapped = round(value / snap) * snap
        if self._smooth_snap_enabled:
            if key not in self._snap_state:
                self._snap_state[key] = snapped
            smooth_factor = 1.0 - math.exp(-self._smooth_snap_speed * 12.0)
            cur = self._snap_state[key]
            cur += (snapped - cur) * smooth_factor
            if abs(cur - snapped) < 0.0001:
                cur = snapped
            self._snap_state[key] = cur
            return cur
        return snapped
    def _get_world_per_pixel(self, cam: SceneCamera, entity_pos: Vec3, vh: int) -> float:
        if cam.is_orthographic or cam.is_2d_mode:
            half_size = cam._ortho_zoom_distance * math.tan(math.radians(cam.DEFAULT_FOV) * 0.5)
            return (2.0 * half_size) / max(1, vh)
        cam_dir = cam.forward
        view_dist = max((entity_pos - cam.position).dot(cam_dir), 0.1)
        fov_rad = math.radians(cam.fov)
        return (2.0 * view_dist * math.tan(fov_rad * 0.5)) / max(1, vh)
    def _screen_axis_tip(self, pos: Vec3, axis_dir: Vec3, cam: SceneCamera, vw: int, vh: int) -> Vec3:
        vp = cam.get_view_matrix() * cam.get_projection_matrix(vw / max(1, vh))
        sp_base = self._project_to_screen(pos, vp, vw, vh)
        if sp_base is None:
            return pos + axis_dir * self.BASE_AXIS_LENGTH
        eps_pos = pos + axis_dir * self._get_world_per_pixel(cam, pos, vh) * 10.0
        sp_eps = self._project_to_screen(eps_pos, vp, vw, vh)
        if sp_eps is None:
            return pos + axis_dir * self.BASE_AXIS_LENGTH
        dx = sp_eps[0] - sp_base[0]
        dy = sp_eps[1] - sp_base[1]
        screen_len = math.sqrt(dx * dx + dy * dy)
        if screen_len < 1e-8:
            return pos + axis_dir * self._get_world_per_pixel(cam, pos, vh) * self.SCREEN_AXIS_LENGTH
        sx = sp_base[0] + dx / screen_len * self.SCREEN_AXIS_LENGTH
        sy = sp_base[1] + dy / screen_len * self.SCREEN_AXIS_LENGTH
        ray_o, ray_d = self._screen_to_ray(sx, sy, cam, vw, vh)
        n = ray_d.cross(axis_dir)
        n_len_sq = n.dot(n)
        if n_len_sq < 1e-12:
            cam_fwd = cam.forward
            denom = ray_d.dot(cam_fwd)
            if abs(denom) < 1e-8:
                return pos + axis_dir * self._get_world_per_pixel(cam, pos, vh) * self.SCREEN_AXIS_LENGTH
            t = (pos - ray_o).dot(cam_fwd) / denom
            if t < 0:
                return pos + axis_dir * self._get_world_per_pixel(cam, pos, vh) * self.SCREEN_AXIS_LENGTH
            return ray_o + ray_d * t
        p = pos - ray_o
        t_axis = p.cross(ray_d).dot(n) / n_len_sq
        if t_axis < 0:
            return pos + axis_dir * self._get_world_per_pixel(cam, pos, vh) * self.SCREEN_AXIS_LENGTH
        return pos + axis_dir * t_axis
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
    def _ray_plane_intersect(self, ray_origin: Vec3, ray_dir: Vec3,
                              plane_point: Vec3, plane_normal: Vec3) -> Optional[Vec3]:
        denom = plane_normal.dot(ray_dir)
        if abs(denom) < 1e-6:
            return None
        t = (plane_point - ray_origin).dot(plane_normal) / denom
        if t < 0:
            return None
        return ray_origin + ray_dir * t
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
    def _get_axis_directions(self, transform):
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
    def get_gizmo_lines(self, cam: SceneCamera, viewport_w: int = 800, viewport_h: int = 600) -> list:
        if not self._entity or self._mode == GizmoMode.NONE:
            return []
        t = self._entity.get_component_by_name("Transform")
        if not t:
            return []
        pos = self._visual_center if self._visual_center is not None else t.position + self._pivot_offset
        if self._mode == GizmoMode.TRANSLATE:
            return self._get_translate_lines(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.ROTATE:
            return self._get_rotate_lines(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.SCALE:
            return self._get_scale_lines(pos, t, cam, viewport_w, viewport_h)
        return []
    def _get_translate_lines(self, pos, transform, cam, vw, vh) -> list:
        lines = []
        rx, ry, rz = self._get_axis_directions(transform)
        active = self._active_axis if self._dragging else self._hover_axis
        vp = cam.get_view_matrix() * cam.get_projection_matrix(vw / max(1, vh))
        inv_vp = vp.inverted()
        cam_fwd = cam.forward
        tip_x = self._screen_axis_tip(pos, rx, cam, vw, vh)
        tip_y = self._screen_axis_tip(pos, ry, cam, vw, vh)
        tip_z = self._screen_axis_tip(pos, rz, cam, vw, vh)
        entity_sp = self._project_to_screen(pos, vp, vw, vh)
        tip_sp_x = self._project_to_screen(tip_x, vp, vw, vh)
        tip_sp_y = self._project_to_screen(tip_y, vp, vw, vh)
        tip_sp_z = self._project_to_screen(tip_z, vp, vw, vh)
        arrow_len_px = self.ARROW_SIZE_RATIO * self.SCREEN_AXIS_LENGTH
        ph_px = self.PLANE_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / self.BASE_AXIS_LENGTH
        is_2d = cam.is_2d_mode if cam else False
        color = AXIS_HIGHLIGHT if active == GizmoAxis.X else AXIS_COLORS[GizmoAxis.X]
        lines.append((pos, tip_x, color))
        if entity_sp and tip_sp_x:
            lines.extend(self._get_arrow_head_screen(tip_x, tip_sp_x, entity_sp, arrow_len_px, inv_vp, cam_fwd, vw, vh, color))
        color = AXIS_HIGHLIGHT if active == GizmoAxis.Y else AXIS_COLORS[GizmoAxis.Y]
        lines.append((pos, tip_y, color))
        if entity_sp and tip_sp_y:
            lines.extend(self._get_arrow_head_screen(tip_y, tip_sp_y, entity_sp, arrow_len_px, inv_vp, cam_fwd, vw, vh, color))
        if not is_2d:
            color = AXIS_HIGHLIGHT if active == GizmoAxis.Z else AXIS_COLORS[GizmoAxis.Z]
            lines.append((pos, tip_z, color))
            if entity_sp and tip_sp_z:
                lines.extend(self._get_arrow_head_screen(tip_z, tip_sp_z, entity_sp, arrow_len_px, inv_vp, cam_fwd, vw, vh, color))
            color = AXIS_HIGHLIGHT if active == GizmoAxis.XZ else AXIS_COLORS[GizmoAxis.XZ]
            if entity_sp and tip_sp_x and tip_sp_z:
                lines.extend(self._get_plane_handle_screen(pos, entity_sp, tip_sp_x, tip_sp_z, ph_px, inv_vp, cam_fwd, vw, vh, color))
            color = AXIS_HIGHLIGHT if active == GizmoAxis.YZ else AXIS_COLORS[GizmoAxis.YZ]
            if entity_sp and tip_sp_y and tip_sp_z:
                lines.extend(self._get_plane_handle_screen(pos, entity_sp, tip_sp_y, tip_sp_z, ph_px, inv_vp, cam_fwd, vw, vh, color))
        color = AXIS_HIGHLIGHT if active == GizmoAxis.XY else AXIS_COLORS[GizmoAxis.XY]
        if entity_sp and tip_sp_x and tip_sp_y:
            lines.extend(self._get_plane_handle_screen(pos, entity_sp, tip_sp_x, tip_sp_y, ph_px, inv_vp, cam_fwd, vw, vh, color))
        center_color = AXIS_HIGHLIGHT if active == GizmoAxis.ALL else [1.0, 1.0, 1.0, 0.8]
        lines.extend(self._get_translate_center_lines(pos, entity_sp, inv_vp, cam_fwd, vw, vh, center_color))
        return lines
    def _get_translate_center_lines(self, pos, center_sp, inv_vp, cam_fwd, vw, vh, color) -> list:
        if not center_sp:
            return []
        half_px = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH * 0.5
        cx, cy = center_sp
        corners_sp = [
            (cx - half_px, cy - half_px),
            (cx + half_px, cy - half_px),
            (cx + half_px, cy + half_px),
            (cx - half_px, cy + half_px),
        ]
        corners_w = [self._screen_pos_to_world(sx, sy, pos, inv_vp, cam_fwd, vw, vh) for sx, sy in corners_sp]
        lines = []
        for i in range(4):
            lines.append((corners_w[i], corners_w[(i + 1) % 4], color))
        return lines
    def _get_arrow_head_screen(self, tip_w: Vec3, tip_sp: tuple, entity_sp: tuple,
                                arrow_len_px: float, inv_vp: Mat4, cam_fwd: Vec3,
                                vw: int, vh: int, color: list) -> list:
        dx = tip_sp[0] - entity_sp[0]
        dy = tip_sp[1] - entity_sp[1]
        screen_len = math.sqrt(dx * dx + dy * dy)
        if screen_len < 1e-8:
            return []
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
        return [
            (tip_w2, f1_w, color),
            (tip_w2, f2_w, color),
            (f1_w, f2_w, color),
        ]
    def _get_plane_handle_screen(self, center_w: Vec3, center_sp: tuple,
                                  axis1_sp: tuple, axis2_sp: tuple, size_px: float,
                                  inv_vp: Mat4, cam_fwd: Vec3,
                                  vw: int, vh: int, color: list) -> list:
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
        corners_sp = [
            (ox, oy),
            (ox + d1x * size_px, oy + d1y * size_px),
            (ox + d1x * size_px + d2x * size_px, oy + d1y * size_px + d2y * size_px),
            (ox + d2x * size_px, oy + d2y * size_px),
        ]
        corners_w = []
        for sx, sy in corners_sp:
            corners_w.append(self._screen_pos_to_world(sx, sy, center_w, inv_vp, cam_fwd, vw, vh))
        lines = []
        for i in range(4):
            lines.append((corners_w[i], corners_w[(i + 1) % 4], color))
        return lines
    def _get_rotate_lines(self, pos, transform, cam, vw, vh) -> list:
        lines = []
        segs = 64
        active = self._active_axis if self._dragging else self._hover_axis
        rx, ry, rz = self._get_axis_directions(transform)
        if self._space == GizmoSpace.LOCAL:
            circle_defs = [
                (GizmoAxis.X, rx),
                (GizmoAxis.Y, ry),
                (GizmoAxis.Z, rz),
            ]
        else:
            circle_defs = [
                (GizmoAxis.X, Vec3(1,0,0)),
                (GizmoAxis.Y, Vec3(0,1,0)),
                (GizmoAxis.Z, Vec3(0,0,1)),
            ]
        for axis_id, normal in circle_defs:
            color = AXIS_HIGHLIGHT if active == axis_id else AXIS_COLORS[axis_id]
            p1, p2 = self._get_perpendiculars(normal)
            tip1 = self._screen_axis_tip(pos, p1, cam, vw, vh)
            tip2 = self._screen_axis_tip(pos, p2, cam, vw, vh)
            radius = min((tip1 - pos).length(), (tip2 - pos).length()) * 0.9
            pts = []
            for i in range(segs + 1):
                ang = 2 * math.pi * i / segs
                pt = pos + p1 * (radius * math.cos(ang)) + p2 * (radius * math.sin(ang))
                pts.append(pt)
            for i in range(segs):
                lines.append((pts[i], pts[i + 1], color))
        return lines
    def _get_scale_lines(self, pos, transform, cam, vw, vh) -> list:
        lines = []
        rx, ry, rz = self._get_axis_directions(transform)
        active = self._active_axis if self._dragging else self._hover_axis
        vp = cam.get_view_matrix() * cam.get_projection_matrix(vw / max(1, vh))
        inv_vp = vp.inverted()
        cam_fwd = cam.forward
        tip_x = self._screen_axis_tip(pos, rx, cam, vw, vh)
        tip_y = self._screen_axis_tip(pos, ry, cam, vw, vh)
        tip_z = self._screen_axis_tip(pos, rz, cam, vw, vh)
        entity_sp = self._project_to_screen(pos, vp, vw, vh)
        tip_sp_x = self._project_to_screen(tip_x, vp, vw, vh)
        tip_sp_y = self._project_to_screen(tip_y, vp, vw, vh)
        tip_sp_z = self._project_to_screen(tip_z, vp, vw, vh)
        half_px = self.CENTER_HANDLE_SIZE * self.SCREEN_AXIS_LENGTH / (self.BASE_AXIS_LENGTH * 2.0)
        color = AXIS_HIGHLIGHT if active == GizmoAxis.X else AXIS_COLORS[GizmoAxis.X]
        lines.append((pos, tip_x, color))
        if tip_sp_x:
            wpp_x = self._get_world_per_pixel(cam, tip_x, vh)
            lines.extend(self._get_cube_handle_screen(tip_x, tip_sp_x, half_px, inv_vp, cam_fwd, wpp_x, vw, vh, color))
        color = AXIS_HIGHLIGHT if active == GizmoAxis.Y else AXIS_COLORS[GizmoAxis.Y]
        lines.append((pos, tip_y, color))
        if tip_sp_y:
            wpp_y = self._get_world_per_pixel(cam, tip_y, vh)
            lines.extend(self._get_cube_handle_screen(tip_y, tip_sp_y, half_px, inv_vp, cam_fwd, wpp_y, vw, vh, color))
        color = AXIS_HIGHLIGHT if active == GizmoAxis.Z else AXIS_COLORS[GizmoAxis.Z]
        lines.append((pos, tip_z, color))
        if tip_sp_z:
            wpp_z = self._get_world_per_pixel(cam, tip_z, vh)
            lines.extend(self._get_cube_handle_screen(tip_z, tip_sp_z, half_px, inv_vp, cam_fwd, wpp_z, vw, vh, color))
        color = AXIS_HIGHLIGHT if active == GizmoAxis.ALL else AXIS_COLORS[GizmoAxis.ALL]
        if entity_sp:
            wpp_center = self._get_world_per_pixel(cam, pos, vh)
            lines.extend(self._get_cube_handle_screen(pos, entity_sp, half_px * 1.2, inv_vp, cam_fwd, wpp_center, vw, vh, color))
        return lines
    def _get_cube_handle_screen(self, center_w: Vec3, center_sp: tuple,
                                 half_px: float, inv_vp: Mat4, cam_fwd: Vec3,
                                 wpp: float, vw: int, vh: int, color: list) -> list:
        cx, cy = center_sp
        corners_sp = [
            (cx - half_px, cy - half_px),
            (cx + half_px, cy - half_px),
            (cx + half_px, cy + half_px),
            (cx - half_px, cy + half_px),
        ]
        corners_w = [self._screen_pos_to_world(sx, sy, center_w, inv_vp, cam_fwd, vw, vh) for sx, sy in corners_sp]
        return [
            (corners_w[0], corners_w[1], color),
            (corners_w[1], corners_w[2], color),
            (corners_w[2], corners_w[3], color),
            (corners_w[3], corners_w[0], color),
            (corners_w[0], corners_w[2], color),
        ]
    def _pick_axis(self, mx: int, my: int, transform, cam: SceneCamera, vw: int, vh: int) -> GizmoAxis:
        pos = transform.position + self._pivot_offset
        vp_mat = cam.get_view_matrix() * cam.get_projection_matrix(vw / max(1, vh))
        if self._mode == GizmoMode.ROTATE:
            return self._pick_rotation_axis(mx, my, transform, cam, vp_mat, vw, vh)
        rx, ry, rz = self._get_axis_directions(transform)
        is_2d = cam.is_2d_mode
        sp_start = self._project_to_screen(pos, vp_mat, vw, vh)
        def _scr_dir(axis):
            eps = pos + axis * 0.001
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
            tip1 = self._screen_axis_tip(pos, p1, cam, vw, vh)
            tip2 = self._screen_axis_tip(pos, p2, cam, vw, vh)
            radius = min((tip1 - pos).length(), (tip2 - pos).length()) * 0.9
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
        return best_axis
    def on_mouse_press(self, mx: int, my: int, cam: SceneCamera, viewport_w: int, viewport_h: int) -> bool:
        if not self._entity or self._mode == GizmoMode.NONE:
            return False
        t = self._entity.get_component_by_name("Transform")
        if not t:
            return False
        axis = self._pick_axis(mx, my, t, cam, viewport_w, viewport_h)
        if axis == GizmoAxis.NONE:
            return False
        self._active_axis = axis
        self._dragging = True
        self._drag_start_mouse = (mx, my)
        self._drag_start_pos = Vec3(*t.position.to_list()) + self._pivot_offset
        self._drag_start_rot = Quat(*t.local_rotation.to_list())
        self._drag_start_scale = Vec3(*t.local_scale.to_list())
        self._drag_entity_start_pos = Vec3(*t.position.to_list())
        pos = t.position + self._pivot_offset
        rx, ry, rz = self._get_axis_directions(t)
        ray_origin, ray_dir = self._screen_to_ray(mx, my, cam, viewport_w, viewport_h)
        if self._mode == GizmoMode.TRANSLATE:
            if axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
                axis_dir = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}[axis]
                self._drag_axis_dir = axis_dir
                plane_normal = self._best_translate_plane_normal(axis_dir, cam.forward)
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                if hit is None:
                    t = self._closest_point_ray_to_line(ray_origin, ray_dir, pos, axis_dir)
                    hit = (ray_origin + ray_dir * t) if t is not None else pos
                self._drag_hit_start = hit
            elif axis in (GizmoAxis.XY, GizmoAxis.XZ, GizmoAxis.YZ):
                plane_map = {GizmoAxis.XY: (rx, ry), GizmoAxis.XZ: (rx, rz), GizmoAxis.YZ: (ry, rz)}
                a1, a2 = plane_map[axis]
                self._drag_plane_axes = (a1, a2)
                plane_normal = a1.cross(a2).normalized()
                self._drag_axis_dir = plane_normal
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                self._drag_hit_start = hit if hit else pos
            elif axis == GizmoAxis.ALL:
                plane_normal = cam.forward
                self._drag_axis_dir = plane_normal
                self._drag_plane_axes = (rx, ry)
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                self._drag_hit_start = hit if hit else pos
        elif self._mode == GizmoMode.ROTATE:
            if axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
                axis_dir = {GizmoAxis.X: Vec3(1,0,0), GizmoAxis.Y: Vec3(0,1,0), GizmoAxis.Z: Vec3(0,0,1)}[axis]
                if self._space == GizmoSpace.LOCAL:
                    axis_dir = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}[axis]
                self._drag_axis_dir = axis_dir
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, axis_dir)
                self._drag_hit_start = hit if hit else pos
        elif self._mode == GizmoMode.SCALE:
            if axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
                axis_dir = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}[axis]
                self._drag_axis_dir = axis_dir
                plane_normal = cam.forward
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                self._drag_hit_start = hit if hit else pos
            elif axis == GizmoAxis.ALL:
                self._drag_axis_dir = Vec3.zero()
                plane_normal = cam.forward
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                self._drag_hit_start = hit if hit else pos
        return True
    def on_mouse_release(self):
        self._visual_center = None
        if self._dragging and self._entity:
            t = self._entity.get_component_by_name("Transform")
            if t:
                from core.commands import SetComponentCommand, get_history
                from core.components import Transform as TransformComponent
                if self._mode == GizmoMode.TRANSLATE:
                    if not getattr(self, '_multi_undo_active', False):
                        new_pos = t.position
                        if (new_pos - self._drag_entity_start_pos).length() > 1e-8:
                            get_history().execute(SetComponentCommand(
                                self._entity, TransformComponent, "position",
                                self._drag_entity_start_pos, new_pos))
                elif self._mode == GizmoMode.ROTATE:
                    if not getattr(self, '_multi_undo_active', False):
                        new_rot = t.local_rotation
                        get_history().execute(SetComponentCommand(
                            self._entity, TransformComponent, "local_rotation",
                            self._drag_start_rot, new_rot))
                elif self._mode == GizmoMode.SCALE:
                    if not getattr(self, '_multi_undo_active', False):
                        new_scale = t.local_scale
                        get_history().execute(SetComponentCommand(
                            self._entity, TransformComponent, "local_scale",
                            self._drag_start_scale, new_scale))
        self._dragging = False
        self._active_axis = GizmoAxis.NONE
        self._delta_text = ""
        self._drag_delta = Vec3.zero()
        self._snap_state.clear()
        self._snap_counter = 0
    def on_mouse_move(self, mx: int, my: int, cam: SceneCamera, viewport_w: int, viewport_h: int):
        if self._dragging and self._entity:
            t = self._entity.get_component_by_name("Transform")
            if t:
                if self._mode == GizmoMode.TRANSLATE:
                    self._apply_translate(t, cam, mx, my, viewport_w, viewport_h)
                elif self._mode == GizmoMode.ROTATE:
                    self._apply_rotate(t, cam, mx, my, viewport_w, viewport_h)
                elif self._mode == GizmoMode.SCALE:
                    self._apply_scale(t, cam, mx, my, viewport_w, viewport_h)
        elif self._entity:
            t = self._entity.get_component_by_name("Transform")
            if t:
                new_hover = self._pick_axis(mx, my, t, cam, viewport_w, viewport_h)
                if new_hover != self._hover_axis:
                    self._hover_axis = new_hover
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
            self._delta_text = f"Δ {axis_delta:+.3f}"
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
                self._delta_text = f"Δ {delta.x:+.3f}, {delta.y:+.3f}, {delta.z:+.3f}"
            else:
                d1 = delta.dot(a1)
                d2 = delta.dot(a2)
                if snap_active and self._snap_translate > 0:
                    d1 = self._apply_snap(d1, self._snap_translate, f"tp_{self._active_axis.value}_1")
                    d2 = self._apply_snap(d2, self._snap_translate, f"tp_{self._active_axis.value}_2")
                self._drag_delta = a1 * d1 + a2 * d2
                self._delta_text = f"Δ {d1:+.3f}, {d2:+.3f}"
            new_world_pos = self._drag_entity_start_pos + self._drag_delta
        else:
            return
        entity = self._entity
        if entity and entity.parent:
            pt = entity.parent.get_component_by_name("Transform")
            if pt:
                from core.math_helpers import mat4_inv_fast
                from core.math3d import FLOAT_TYPE
                import numpy as np
                pt._update_world_matrix()
                inv = mat4_inv_fast(pt._world_matrix._d)
                world_arr = np.array([new_world_pos.x, new_world_pos.y, new_world_pos.z, 1.0], dtype=FLOAT_TYPE)
                local_arr = world_arr @ inv.T
                transform.local_position = Vec3(float(local_arr[0]), float(local_arr[1]), float(local_arr[2]))
                return
        transform.position = new_world_pos
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
        self._delta_text = f"Δ {angle:+.1f}°"
        dq = Quat.from_axis_angle(axis_dir, angle)
        if self._space == GizmoSpace.LOCAL:
            transform.local_rotation = (self._drag_start_rot * dq).normalized()
        else:
            transform.local_rotation = (dq * self._drag_start_rot).normalized()
    def _apply_scale(self, transform, cam: SceneCamera, mx: int, my: int, vw: int, vh: int):
        pos = self._drag_entity_start_pos + self._pivot_offset
        ray_origin, ray_dir = self._screen_to_ray(mx, my, cam, vw, vh)
        snap_active = self._snap_enabled and not self._ctrl_down
        if self._active_axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
            axis_dir = self._drag_axis_dir
            plane_normal = cam.forward
            hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
            if not hit:
                return
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
            self._delta_text = f"Δ {delta_val:+.3f}"
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
            self._delta_text = f"Δ {scale_factor-1.0:+.3f}"
            transform.local_scale = new_s