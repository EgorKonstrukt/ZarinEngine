from __future__ import annotations
import math
import numpy as np
from editor.gizmo.api import Gizmos


_BOX_EDGES = np.array([
    (0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)
], dtype=np.int32)

_BOX_CORNERS = np.array([
    [-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
    [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],
], dtype=np.float32)


def _quat_to_mat3(rot) -> np.ndarray:
    x, y, z, w = rot.x, rot.y, rot.z, rot.w
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return np.array([
        [1-2*(yy+zz), 2*(xy-wz), 2*(xz+wy)],
        [2*(xy+wz), 1-2*(xx+zz), 2*(yz-wx)],
        [2*(xz-wy), 2*(yz+wx), 1-2*(xx+yy)],
    ], dtype=np.float32)


def _xfm(local: np.ndarray, pos: np.ndarray, R: np.ndarray, sc: np.ndarray) -> np.ndarray:
    return local * sc @ R.T + pos


def _make_color(color: list[float], n: int) -> np.ndarray:
    c = np.empty((n, 4), dtype=np.float32)
    c[:] = color
    return c


def box_lines(center: tuple[float, float, float],
              size: tuple[float, float, float],
              color: list[float],
              pos, rot, sc,
              ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    R, T, S = _quat_to_mat3(rot), np.array([pos.x, pos.y, pos.z], dtype=np.float32), np.array([sc.x, sc.y, sc.z], dtype=np.float32)
    c = np.array([center[0], center[1], center[2]], dtype=np.float32)
    h = np.array([size[0]*0.5, size[1]*0.5, size[2]*0.5], dtype=np.float32)
    corners = _BOX_CORNERS * h + c
    corners = _xfm(corners, T, R, S)
    return corners[_BOX_EDGES[:, 0]], corners[_BOX_EDGES[:, 1]], _make_color(color, 12)


def rect_lines(center: tuple[float, float, float],
               size: tuple[float, float],
               color: list[float],
               pos, rot, sc,
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    R, T, S = _quat_to_mat3(rot), np.array([pos.x, pos.y, pos.z], dtype=np.float32), np.array([sc.x, sc.y, sc.z], dtype=np.float32)
    c = np.array([center[0], center[1], center[2]], dtype=np.float32)
    hx, hy = size[0]*0.5, size[1]*0.5
    corners = np.array([[-hx,-hy,0],[hx,-hy,0],[hx,hy,0],[-hx,hy,0]], dtype=np.float32) + c
    corners = _xfm(corners, T, R, S)
    edges = np.array([(0,1),(1,2),(2,3),(3,0)], dtype=np.int32)
    return corners[edges[:, 0]], corners[edges[:, 1]], _make_color(color, 4)


def sphere_rings(center: tuple[float, float, float],
                 radius: float,
                 color: list[float],
                 pos, rot, sc,
                 segments: int = 24,
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    R, T, S = _quat_to_mat3(rot), np.array([pos.x, pos.y, pos.z], dtype=np.float32), np.array([sc.x, sc.y, sc.z], dtype=np.float32)
    c = np.array([center[0], center[1], center[2]], dtype=np.float32)
    r = radius * max(S[0], S[1], S[2])
    theta = np.linspace(0, 2*math.pi, segments+1, dtype=np.float32)
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    total = segments*3
    starts = np.empty((total, 3), dtype=np.float32)
    ends = np.empty((total, 3), dtype=np.float32)
    base = np.zeros((segments+1, 3), dtype=np.float32)
    base[:, 1] = ct; base[:, 2] = st; ring = _xfm(base + c, T, R, S)
    starts[:segments] = ring[:-1]; ends[:segments] = ring[1:]
    base[:] = 0; base[:, 0] = ct; base[:, 2] = st; ring = _xfm(base + c, T, R, S)
    starts[segments:2*segments] = ring[:-1]; ends[segments:2*segments] = ring[1:]
    base[:] = 0; base[:, 0] = ct; base[:, 1] = st; ring = _xfm(base + c, T, R, S)
    starts[2*segments:] = ring[:-1]; ends[2*segments:] = ring[1:]
    return starts, ends, _make_color(color, total)


def capsule_lines(center: tuple[float, float, float],
                  radius: float,
                  height: float,
                  direction: int,
                  color: list[float],
                  pos, rot, sc,
                  segments: int = 20,
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    R, T, S = _quat_to_mat3(rot), np.array([pos.x, pos.y, pos.z], dtype=np.float32), np.array([sc.x, sc.y, sc.z], dtype=np.float32)
    c = np.array([center[0], center[1], center[2]], dtype=np.float32)
    r = radius
    half_h = max(0, height * 0.5 - radius)
    dir_idx = direction if direction < 3 else 1
    axis_vecs = [np.array([1,0,0], dtype=np.float32), np.array([0,1,0], dtype=np.float32), np.array([0,0,1], dtype=np.float32)]
    axis = axis_vecs[dir_idx]
    theta = np.linspace(0, 2*math.pi, segments+1, dtype=np.float32)
    ct = np.cos(theta)*r; st = np.sin(theta)*r
    total = 0
    for ring_axis in range(3):
        if ring_axis != dir_idx:
            total += segments * 2
    total += 8
    starts = np.empty((total, 3), dtype=np.float32)
    ends = np.empty((total, 3), dtype=np.float32)
    idx = 0
    for ring_axis in range(3):
        if ring_axis == dir_idx:
            continue
        u = np.array([0,1,0] if ring_axis == 0 else [1,0,0], dtype=np.float32)
        v = np.array([0,0,1] if ring_axis == 2 else [0,1,0], dtype=np.float32)
        if ring_axis == 1:
            u = np.array([1,0,0], dtype=np.float32); v = np.array([0,0,1], dtype=np.float32)
        top_off = c + axis * half_h
        bot_off = c - axis * half_h
        pts = (u * ct[:, None] + v * st[:, None])[:, :3]
        pts_top = _xfm(pts + top_off, T, R, S)
        pts_bot = _xfm(pts + bot_off, T, R, S)
        n = segments
        starts[idx:idx+n] = pts_top[:-1]; ends[idx:idx+n] = pts_top[1:]; idx += n
        starts[idx:idx+n] = pts_bot[:-1]; ends[idx:idx+n] = pts_bot[1:]; idx += n
    theta8 = np.linspace(0, 2*math.pi, 9, dtype=np.float32)[:-1]
    ct8 = np.cos(theta8)*r; st8 = np.sin(theta8)*r
    u = np.array([0,1,0] if dir_idx == 0 else [1,0,0], dtype=np.float32)
    v = np.array([0,0,1] if dir_idx == 2 else [0,1,0], dtype=np.float32)
    if dir_idx == 1:
        u = np.array([1,0,0], dtype=np.float32); v = np.array([0,0,1], dtype=np.float32)
    pts = (u * ct8[:, None] + v * st8[:, None])[:, :3]
    pts_top = _xfm(pts + top_off, T, R, S)
    pts_bot = _xfm(pts + bot_off, T, R, S)
    starts[idx:idx+8] = pts_top; ends[idx:idx+8] = pts_bot
    return starts, ends, _make_color(color, total)


def circle_lines(center: tuple[float, float, float],
                 radius: float,
                 color: list[float],
                 pos, rot, sc,
                 segments: int = 24,
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    R, T, S = _quat_to_mat3(rot), np.array([pos.x, pos.y, pos.z], dtype=np.float32), np.array([sc.x, sc.y, sc.z], dtype=np.float32)
    c = np.array([center[0], center[1], center[2]], dtype=np.float32)
    r = radius * max(S[0], S[1])
    theta = np.linspace(0, 2*math.pi, segments+1, dtype=np.float32)
    pts = np.zeros((segments+1, 3), dtype=np.float32)
    pts[:, 0] = np.cos(theta)*r; pts[:, 1] = np.sin(theta)*r
    pts = _xfm(pts + c, T, R, S)
    return pts[:-1], pts[1:], _make_color(color, segments)


def edge_pairs(edge_verts_np: np.ndarray,
               color: list[float],
               pos, rot, sc,
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    R, T, S = _quat_to_mat3(rot), np.array([pos.x, pos.y, pos.z], dtype=np.float32), np.array([sc.x, sc.y, sc.z], dtype=np.float32)
    n = edge_verts_np.shape[0]
    verts = edge_verts_np.reshape(-1, 3)
    transformed = verts * S @ R + T
    starts = transformed[0::2].reshape(n, 3)
    ends = transformed[1::2].reshape(n, 3)
    return starts, ends, _make_color(color, n)


def submit(primitives: list[tuple[np.ndarray, np.ndarray, np.ndarray] | None]) -> None:
    filtered = [p for p in primitives if p is not None]
    if not filtered:
        return
    if len(filtered) == 1:
        s, e, c = filtered[0]
        if s.shape[0] > 0:
            Gizmos.draw_lines(s, e, c)
        return
    sizes = [p[0].shape[0] for p in filtered]
    total = sum(sizes)
    if total == 0:
        return
    starts = np.empty((total, 3), dtype=np.float32)
    ends = np.empty((total, 3), dtype=np.float32)
    colors = np.empty((total, 4), dtype=np.float32)
    off = 0
    for i, n in enumerate(sizes):
        if n == 0:
            continue
        s, e, c = filtered[i]
        starts[off:off+n] = s
        ends[off:off+n] = e
        colors[off:off+n] = c
        off += n
    Gizmos.draw_lines(starts, ends, colors)
