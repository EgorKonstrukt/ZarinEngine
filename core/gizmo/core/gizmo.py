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
from core.gizmo.core.batch import GpuGizmoBatch, FLOAT_T, DEF_CAP
from core.gizmo.core.translate import TranslateMixin
from core.gizmo.core.rotate import RotateMixin
from core.gizmo.core.scale import ScaleMixin
if TYPE_CHECKING:
    from core.ecs import Entity
    from editor.cam import SceneCamera

class Gizmo(TranslateMixin, RotateMixin, ScaleMixin):
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
        self._multigizmo_enabled = config.get("gizmo.multigizmo_enabled", False)
        self._multigizmo_alignment = config.get("gizmo.multigizmo_alignment", "local")
        self._orientation_lock = config.get("gizmo.multigizmo_orientation_lock", False)
        self._multigizmo_visible = config.get("gizmo.multigizmo_visible", True)
        self._snap_enabled = config.get("toolbar.snap", self._snap_enabled)
        self._snap_translate = float(config.get("toolbar.snap_translate", self._snap_translate))
        self._snap_rotate = float(config.get("toolbar.snap_rotate", self._snap_rotate))
        self._snap_scale = float(config.get("toolbar.snap_scale", self._snap_scale))

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
        self._shift_down: bool = False
        self._delta_text: str = ""
        self._drag_delta: Vec3 = Vec3.zero()
        self._smooth_snap_enabled: bool = True
        self._show_delta_label: bool = True
        self._smooth_snap_speed: float = 0.25
        self._multigizmo_enabled: bool = False
        self._multigizmo_alignment: str = "local"
        self._orientation_lock: bool = False
        self._multigizmo_visible: bool = True
        self._active_op: str = "translate"
        self._hover_op: str = "translate"
        self._orientation_lock_cache: Optional[tuple[Vec3, Vec3, Vec3]] = None
        self._custom_matrix: Optional[Mat4] = None
        self._snap_state: dict[str, float] = {}
        self._snap_counter: int = 0
        self._batch: GpuGizmoBatch = GpuGizmoBatch(DEF_CAP)
        self._vp_mat_cache: Optional[Mat4] = None
        self._inv_vp_cache: Optional[Mat4] = None
        self._cam_fwd_cache: Vec3 = Vec3.zero()
        self._wpp_cache: float = 0.01

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
    def shift_down(self) -> bool: return self._shift_down

    @shift_down.setter
    def shift_down(self, v: bool): self._shift_down = v

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

    @property
    def multigizmo_enabled(self) -> bool: return self._multigizmo_enabled

    @multigizmo_enabled.setter
    def multigizmo_enabled(self, v: bool): self._multigizmo_enabled = bool(v)

    @property
    def multigizmo_visible(self) -> bool: return self._multigizmo_visible

    @multigizmo_visible.setter
    def multigizmo_visible(self, v: bool): self._multigizmo_visible = bool(v)

    @property
    def alignment(self) -> str: return self._multigizmo_alignment

    @alignment.setter
    def alignment(self, v: str): self._multigizmo_alignment = str(v)

    @property
    def orientation_lock(self) -> bool: return self._orientation_lock

    @orientation_lock.setter
    def orientation_lock(self, v: bool): self._orientation_lock = bool(v)

    @property
    def custom_matrix(self) -> Optional[Mat4]: return self._custom_matrix

    @custom_matrix.setter
    def custom_matrix(self, v: Optional[Mat4]): self._custom_matrix = v

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

    def _is_multigizmo_active(self) -> bool:
        return self._multigizmo_enabled and self._multigizmo_visible and self._mode != GizmoMode.NONE

    def get_gizmo_lines(self, cam: SceneCamera, viewport_w: int = 800, viewport_h: int = 600) -> list:
        if not self._entity or self._mode == GizmoMode.NONE:
            return []
        if self._multigizmo_enabled and not self._multigizmo_visible:
            return []
        t = self._entity.transform
        if not t:
            return []
        self._update_cache(cam, viewport_w, viewport_h)
        pos = self._visual_center if self._visual_center is not None else t.position + self._pivot_offset
        self._batch.clear()
        if self._is_multigizmo_active():
            self._get_multigizmo_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.TRANSLATE:
            self._get_translate_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.ROTATE:
            self._get_rotate_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.SCALE:
            self._get_scale_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.MULTI:
            self._get_multigizmo_lines_batch(pos, t, cam, viewport_w, viewport_h)
        starts, ends, colors = self._batch.get_arrays()
        out = []
        for i in range(len(starts)):
            out.append((
                Vec3(float(starts[i,0]), float(starts[i,1]), float(starts[i,2])),
                Vec3(float(ends[i,0]), float(ends[i,1]), float(ends[i,2])),
                [float(colors[i,0]), float(colors[i,1]), float(colors[i,2]), float(colors[i,3])],
            ))
        return out

    def get_gizmo_arrays(self, cam: SceneCamera, viewport_w: int = 800, viewport_h: int = 600):
        if not self._entity or self._mode == GizmoMode.NONE:
            return None
        if self._multigizmo_enabled and not self._multigizmo_visible:
            return None
        t = self._entity.transform
        if not t:
            return None
        self._update_cache(cam, viewport_w, viewport_h)
        pos = self._visual_center if self._visual_center is not None else t.position + self._pivot_offset
        self._batch.clear()
        if self._is_multigizmo_active():
            self._get_multigizmo_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.TRANSLATE:
            self._get_translate_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.ROTATE:
            self._get_rotate_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.SCALE:
            self._get_scale_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.MULTI:
            self._get_multigizmo_lines_batch(pos, t, cam, viewport_w, viewport_h)
        return self._batch.get_arrays()

    def get_gizmo_flat_verts(self, cam: SceneCamera, viewport_w: int = 800, viewport_h: int = 600) -> Optional[np.ndarray]:
        if not self._entity or self._mode == GizmoMode.NONE:
            return None
        if self._multigizmo_enabled and not self._multigizmo_visible:
            return None
        t = self._entity.transform
        if not t:
            return None
        self._update_cache(cam, viewport_w, viewport_h)
        pos = self._visual_center if self._visual_center is not None else t.position + self._pivot_offset
        self._batch.clear()
        if self._is_multigizmo_active():
            self._get_multigizmo_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.TRANSLATE:
            self._get_translate_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.ROTATE:
            self._get_rotate_lines_batch(pos, t, cam, viewport_w, viewport_h)
        elif self._mode == GizmoMode.SCALE:
            self._get_scale_lines_batch(pos, t, cam, viewport_w, viewport_h)
        return self._batch.get_flat_verts()

    def on_mouse_press(self, mx: int, my: int, cam: SceneCamera, viewport_w: int, viewport_h: int) -> bool:
        if not self._entity or self._mode == GizmoMode.NONE:
            return False
        t = self._entity.transform
        if not t:
            return False
        axis = self._pick_axis(mx, my, t, cam, viewport_w, viewport_h)
        if axis == GizmoAxis.NONE:
            return False
        self._active_axis = axis
        if self._is_multigizmo_active():
            self._active_op = getattr(self, '_hover_op', 'translate')
        else:
            mode_to_op = {GizmoMode.TRANSLATE: 'translate', GizmoMode.ROTATE: 'rotate', GizmoMode.SCALE: 'scale'}
            self._active_op = mode_to_op.get(self._mode, 'translate')
            if self._mode == GizmoMode.MULTI:
                self._active_op = getattr(self, '_hover_op', 'translate')
        self._dragging = True
        self._drag_start_mouse = (mx, my)
        self._drag_start_pos = Vec3(*t.position.to_list()) + self._pivot_offset
        self._drag_start_rot = Quat(*t.local_rotation.to_list())
        self._drag_start_scale = Vec3(*t.local_scale.to_list())
        self._drag_entity_start_pos = Vec3(*t.position.to_list())
        if self._orientation_lock:
            rx0, ry0, rz0 = self._get_axis_directions(t, cam)
            self._orientation_lock_cache = (rx0, ry0, rz0)
        pos = t.position + self._pivot_offset
        rx, ry, rz = self._get_axis_directions(t, cam)
        ray_origin, ray_dir = self._screen_to_ray(mx, my, cam, viewport_w, viewport_h)
        op = getattr(self, '_active_op', 'translate')
        if op == 'translate':
            if axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
                axis_dir = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}[axis]
                self._drag_axis_dir = axis_dir
                plane_normal = self._best_translate_plane_normal(axis_dir, cam.forward)
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                if hit is None:
                    tt = self._closest_point_ray_to_line(ray_origin, ray_dir, pos, axis_dir)
                    hit = (ray_origin + ray_dir * tt) if tt is not None else pos
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
        elif op == 'rotate':
            if axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z, GizmoAxis.ALL):
                if axis == GizmoAxis.ALL:
                    axis_dir = cam.forward
                else:
                    axis_dir = {GizmoAxis.X: Vec3(1,0,0), GizmoAxis.Y: Vec3(0,1,0), GizmoAxis.Z: Vec3(0,0,1)}[axis]
                    if self._space == GizmoSpace.LOCAL or (self._is_multigizmo_active() and self._multigizmo_alignment == "local"):
                        axis_dir = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}[axis]
                self._drag_axis_dir = axis_dir
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, axis_dir)
                self._drag_hit_start = hit if hit else pos
        elif op == 'scale':
            if self._shift_down:
                axis = GizmoAxis.ALL
                self._active_axis = GizmoAxis.ALL
            if axis in (GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z):
                axis_dir = {GizmoAxis.X: rx, GizmoAxis.Y: ry, GizmoAxis.Z: rz}[axis]
                self._drag_axis_dir = axis_dir
                plane_normal = self._best_translate_plane_normal(axis_dir, cam.forward)
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                if hit is None:
                    tt = self._closest_point_ray_to_line(ray_origin, ray_dir, pos, axis_dir)
                    hit = (ray_origin + ray_dir * tt) if tt is not None else pos
                self._drag_hit_start = hit if hit else pos
            elif axis == GizmoAxis.ALL:
                self._drag_axis_dir = Vec3.zero()
                plane_normal = cam.forward
                hit = self._ray_plane_intersect(ray_origin, ray_dir, pos, plane_normal)
                self._drag_hit_start = hit if hit else pos
        return True

    def on_mouse_release(self):
        self._visual_center = None
        if not self._orientation_lock:
            self._orientation_lock_cache = None
        if self._dragging and self._entity:
            t = self._entity.transform
            if t:
                from core.foundation.cmd import SetComponentCommand, get_history
                from core.components import Transform as TransformComponent
                op = getattr(self, '_active_op', 'translate')
                is_multi = self._is_multigizmo_active() or self._mode == GizmoMode.MULTI
                check_op = op if is_multi else {GizmoMode.TRANSLATE: 'translate', GizmoMode.ROTATE: 'rotate', GizmoMode.SCALE: 'scale'}.get(self._mode, 'translate')
                if check_op == 'translate':
                    if not getattr(self, '_multi_undo_active', False):
                        new_pos = t.position
                        if (new_pos - self._drag_entity_start_pos).length() > 1e-8:
                            get_history().execute(SetComponentCommand(
                                self._entity, TransformComponent, "position",
                                self._drag_entity_start_pos, new_pos))
                elif check_op == 'rotate':
                    if not getattr(self, '_multi_undo_active', False):
                        new_rot = t.local_rotation
                        get_history().execute(SetComponentCommand(
                            self._entity, TransformComponent, "local_rotation",
                            self._drag_start_rot, new_rot))
                elif check_op == 'scale':
                    if not getattr(self, '_multi_undo_active', False):
                        new_scale = t.local_scale
                        get_history().execute(SetComponentCommand(
                            self._entity, TransformComponent, "local_scale",
                            self._drag_start_scale, new_scale))
        self._dragging = False
        self._active_axis = GizmoAxis.NONE
        self._active_op = "translate"
        self._delta_text = ""
        self._drag_delta = Vec3.zero()
        self._snap_state.clear()
        self._snap_counter = 0

    def on_mouse_move(self, mx: int, my: int, cam: SceneCamera, viewport_w: int, viewport_h: int):
        if self._dragging and self._entity:
            t = self._entity.transform
            if t:
                if self._is_multigizmo_active():
                    op = getattr(self, '_active_op', 'translate')
                    if op == 'translate':
                        self._apply_translate(t, cam, mx, my, viewport_w, viewport_h)
                    elif op == 'rotate':
                        self._apply_rotate(t, cam, mx, my, viewport_w, viewport_h)
                    elif op == 'scale':
                        self._apply_scale(t, cam, mx, my, viewport_w, viewport_h)
                elif self._mode == GizmoMode.TRANSLATE:
                    self._apply_translate(t, cam, mx, my, viewport_w, viewport_h)
                elif self._mode == GizmoMode.ROTATE:
                    self._apply_rotate(t, cam, mx, my, viewport_w, viewport_h)
                elif self._mode == GizmoMode.SCALE:
                    self._apply_scale(t, cam, mx, my, viewport_w, viewport_h)
                elif self._mode == GizmoMode.MULTI:
                    op = getattr(self, '_active_op', 'translate')
                    if op == 'translate':
                        self._apply_translate(t, cam, mx, my, viewport_w, viewport_h)
                    elif op == 'rotate':
                        self._apply_rotate(t, cam, mx, my, viewport_w, viewport_h)
                    elif op == 'scale':
                        self._apply_scale(t, cam, mx, my, viewport_w, viewport_h)
        elif self._entity:
            t = self._entity.transform
            if t:
                new_hover = self._pick_axis(mx, my, t, cam, viewport_w, viewport_h)
                if new_hover != self._hover_axis:
                    self._hover_axis = new_hover
                if self._is_multigizmo_active():
                    pass
