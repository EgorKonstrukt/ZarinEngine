from __future__ import annotations
import math
from typing import TYPE_CHECKING
from core.math3d import Vec3
from core.components.rendering.camera import CameraProjection
if TYPE_CHECKING:
    from core.ecs import Entity


def get_camera_frustum_lines(
    entity: Entity,
) -> list[tuple[Vec3, Vec3, list[float]]]:
    tr = entity.get_component_by_name("Transform")
    if not tr:
        return []
    cam = entity.get_component_by_name("Camera")
    if not cam:
        return []
    near = cam.near
    far = cam.far
    aspect = 16.0 / 9.0
    if cam.projection == CameraProjection.ORTHOGRAPHIC:
        half_w = cam.ortho_size * aspect * 0.5
        half_h = cam.ortho_size * 0.5
        half_w_near = half_w_far = half_w
        half_h_near = half_h_far = half_h
    else:
        fov_rad = math.radians(cam.fov)
        half_h_near = math.tan(fov_rad * 0.5) * near
        half_w_near = half_h_near * aspect
        half_h_far = math.tan(fov_rad * 0.5) * far
        half_w_far = half_h_far * aspect
    pos = tr.position
    fwd = tr.forward
    up = tr.up
    right = tr.right
    def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
        return pos + right * lx + up * ly + (-fwd) * lz
    corners = [
        local_to_world(-half_w_near,  half_h_near, -near),
        local_to_world( half_w_near,  half_h_near, -near),
        local_to_world( half_w_near, -half_h_near, -near),
        local_to_world(-half_w_near, -half_h_near, -near),
        local_to_world(-half_w_far,  half_h_far,  -far),
        local_to_world( half_w_far,  half_h_far,  -far),
        local_to_world( half_w_far, -half_h_far,  -far),
        local_to_world(-half_w_far, -half_h_far,  -far),
    ]
    color = [0.3, 0.7, 1.0, 0.6]
    lines: list[tuple[Vec3, Vec3, list[float]]] = []
    near_idx = [0, 1, 2, 3]
    far_idx = [4, 5, 6, 7]
    for i in range(4):
        j = (i + 1) % 4
        lines.append((corners[near_idx[i]], corners[near_idx[j]], color))
        lines.append((corners[far_idx[i]], corners[far_idx[j]], color))
        lines.append((corners[near_idx[i]], corners[far_idx[i]], color))
    return lines
